import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { boxFiles, gitIdentity, newestSnapshot, recipe, recipeKey, snapshotSettings } from "../snapshot/recipe.mjs";
import { recipeFiles, recipeSteps } from "../scripts/recipe-files.mjs";
import { githubRepo, loadSettings, merge, operatorDefine, ownedBy, WORKER_DIR } from "../scripts/settings.mjs";

const NOWHERE = join(WORKER_DIR, "test", "no-such-file");
const shipped = () => loadSettings({ local: NOWHERE, rules: NOWHERE });
const SHA = "0123456789abcdef0123456789abcdef01234567";

test("the operator Git identity reaches the Worker and changes the snapshot key", async () => {
	const identity = { name: "exampleagent", email: "agent@example.invalid" };
	const settings = { ...shipped(), git_identity: identity };
	assert.deepEqual(operatorDefine(settings).git_identity, identity);
	assert.notEqual(await recipeKey(recipeSteps(settings)), await recipeKey(recipeSteps(shipped())));
	assert.deepEqual(gitIdentity(null), { name: "ohflow", email: "ohflow@users.noreply.github.com" });
	for (const value of [{}, { name: "", email: "a@b" }, { name: "agent\nextra", email: "a@b" }, { name: "agent", email: "a<b>" }]) {
		assert.throws(() => operatorDefine({ ...settings, git_identity: value }), /git_identity/);
	}
});

test("fresh repos commit with the box identity and can override it locally", () => {
	const root = mkdtempSync(join(tmpdir(), "ohflow-git-identity-"));
	try {
		const identity = { name: "exampleagent", email: "agent@example.invalid" };
		const env = { ...process.env, GIT_CONFIG_SYSTEM: join(root, "system.gitconfig"), GIT_CONFIG_GLOBAL: join(root, "empty.gitconfig") };
		for (const key of Object.keys(env)) {
			if (/^GIT_(AUTHOR|COMMITTER)_/.test(key) || /^GIT_CONFIG_(COUNT|KEY_|VALUE_)/.test(key)) delete env[key];
		}
		const run = (args, cwd = root) => {
			const result = spawnSync("git", args, { cwd, env, encoding: "utf8", timeout: 10_000, windowsHide: true });
			assert.equal(result.status, 0, result.stderr || String(result.error));
			return result.stdout.trim();
		};
		for (const step of recipeSteps({ ...shipped(), git_identity: identity }).filter((step) => step.name.startsWith("set the box Git "))) {
			run(step.command.slice(1));
		}
		for (const user of ["root", "agent"]) {
			const repo = join(root, user);
			mkdirSync(repo);
			run(["init", "-q"], repo);
			run(["-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "Identity check"], repo);
			assert.equal(run(["show", "-s", "--format=%an <%ae>|%cn <%ce>"], repo), "exampleagent <agent@example.invalid>|exampleagent <agent@example.invalid>");
			run(["config", "user.name", "Project author"], repo);
			assert.equal(run(["config", "user.name"], repo), "Project author");
		}
	} finally {
		rmSync(root, { recursive: true, force: true });
	}
});

function operatorSettings() {
	return merge(shipped(), {
		rules: "## Household\n\nA rule of this operator.",
		snapshot: {
			skills: { repo: "alice/skills", sha: SHA },
			repos: [{ repo: "alice/tool", sha: SHA, build: ["npm ci"] }],
			mcp_servers: { tool: { command: "node", args: ["/opt/mcp/tool/server.js"] } },
		},
	});
}

test("the shipped settings clone no repo", () => {
	const steps = recipeSteps(shipped());
	const clones = steps.filter((step) => step.command.join(" ").includes(" clone "));
	assert.deepEqual(clones, []);
	assert.equal(steps.some((step) => step.secret), false);
});

test("the shipped box table serves only the npm servers", () => {
	const servers = JSON.parse(recipeFiles(shipped()).servers).mcpServers;
	assert.deepEqual(Object.keys(servers).sort(), ["brave-search", "playwright", "sequential-thinking"]);
});

test("operator settings add the skills repo, the repos and their servers", () => {
	const settings = operatorSettings();
	const steps = recipeSteps(settings);
	const names = steps.map((step) => step.name);
	assert.ok(names.includes("clone the skills repo"));
	assert.ok(names.includes("install tool"));
	const tool = steps.find((step) => step.name === "install tool").command.join(" ");
	assert.match(tool, /clone --quiet https:\/\/github\.com\/alice\/tool\.git \/opt\/mcp\/tool/);
	assert.match(tool, new RegExp(`checkout --quiet -B main ${SHA}`));
	assert.match(tool, /\(cd \/opt\/mcp\/tool && npm ci\)/);
	const files = recipeFiles(settings);
	assert.ok(JSON.parse(files.servers).mcpServers.tool);
	assert.ok(files.agents.endsWith("A rule of this operator.\n"));
	assert.ok(files.agents.startsWith("# Rules for every agent in the box"));
});

test("the operator's rules and repos change the snapshot key", async () => {
	const plain = await recipeKey(recipeSteps(shipped()));
	const own = await recipeKey(recipeSteps(operatorSettings()));
	assert.match(plain, /^[0-9a-f]{32}$/);
	assert.notEqual(plain, own);
	assert.equal(plain, await recipeKey(recipeSteps(shipped())));
});

test("a repo entry needs an owner/name and a full commit id", () => {
	assert.throws(() => snapshotSettings({ repos: [{ repo: "tool", sha: SHA }] }), /owner/);
	assert.throws(() => snapshotSettings({ repos: [{ repo: "alice/tool", sha: "main" }] }), /40-character/);
	assert.throws(() => snapshotSettings({ repos: [{ repo: "alice/tool; rm -rf /", sha: SHA }] }), /owner/);
	assert.throws(() => snapshotSettings({ skills: { repo: "alice/skills" } }), /40-character/);
});

test("box files stay byte for byte without operator values", () => {
	const files = { agents: "a\n", servers: '{"mcpServers":{}}\n', versions: "", chromium: "", gateway: "", boot: "" };
	assert.deepEqual(boxFiles(files, {}), files);
	assert.equal(recipe(files).length, recipe(files, { repos: [] }).length);
});

test("the fallback snapshot is the newest one built", () => {
	const stored = new Map([
		["snapshot:aaa", { key: "aaa", id: "snap-a", builtAt: "2026-11-14T10:00:00.000Z" }],
		["snapshot:ccc", { key: "ccc", id: "snap-c", builtAt: "2026-11-20T10:00:00.000Z" }],
		["snapshot:bbb", { id: "snap-b", builtAt: "2026-11-21T10:00:00.000Z" }],
		["snapshot:ddd", { key: "ddd", builtAt: "2026-11-22T10:00:00.000Z" }],
	]);
	assert.deepEqual(newestSnapshot(stored), { key: "bbb", id: "snap-b", builtAt: "2026-11-21T10:00:00.000Z" });
	assert.equal(newestSnapshot(new Map()), null);
});

test("settings merge objects and replace lists", () => {
	assert.deepEqual(merge({ a: { b: 1, c: [1] } }, { a: { c: [2] } }), { a: { b: 1, c: [2] } });
	assert.equal(merge({ a: 1 }, { a: null }).a, null);
});

test("a GitHub remote names its owner and repo", () => {
	assert.equal(githubRepo("https://github.com/alice/ohflow.git"), "alice/ohflow");
	assert.equal(githubRepo("git@github.com:alice/ohflow.git"), "alice/ohflow");
	assert.equal(githubRepo("https://github.com/alice/ohflow"), "alice/ohflow");
	assert.equal(githubRepo("https://example.com/alice/ohflow"), null);
});

test("only the operator's own repo becomes the skills repo", () => {
	assert.equal(ownedBy("alice/ohflow", "Alice"), true);
	assert.equal(ownedBy("upstream/ohflow", "alice"), false);
	assert.equal(ownedBy("alice/ohflow", null), false);
});
