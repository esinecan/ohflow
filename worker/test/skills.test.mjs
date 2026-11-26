import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fetchSkills } from "../snapshot/box/box-skills.mjs";
import { CLI_HOSTS } from "../snapshot/recipe.mjs";
import { recipeSteps } from "../scripts/recipe-files.mjs";
import { loadSettings, WORKER_DIR } from "../scripts/settings.mjs";
import { pinSkills, skillsResponse, skillsUrl } from "../src/skills-feed.mjs";

const SHA = "0123456789abcdef0123456789abcdef01234567";
const OLD = "fedcba9876543210fedcba9876543210fedcba98";
const NOWHERE = join(WORKER_DIR, "test", "no-such-file");
const bytes = (text) => new TextEncoder().encode(text);

function mirrorOf(files, sha = SHA) {
	const calls = [];
	const stub = {
		calls,
		async sync() {
			calls.push("sync");
			return { sha, skills: [...new Set(Object.keys(files).map((path) => path.split("/")[0]))].sort() };
		},
		async current() {
			calls.push("current");
			return { sha: OLD, skills: [] };
		},
		async manifest(at, names) {
			if (at !== sha) return [];
			return Object.entries(files)
				.filter(([path]) => names.includes(path.split("/")[0]))
				.map(([path, data]) => ({ path, size: data.length }));
		},
		async read(at, paths) {
			calls.push(["read", paths.length]);
			return paths.map((path) => ({ path, data: at === sha ? (files[path] ?? null) : null }));
		},
	};
	return stub;
}

function tempBox() {
	const root = mkdtempSync(join(tmpdir(), "box-skills-"));
	return { root, dir: join(root, "agent-skills").replaceAll("\\", "/"), pinFile: join(root, "etc", "skills.json") };
}

const FILES = {
	"alpha/SKILL.md": bytes("# alpha\n"),
	"alpha/scripts/run.sh": bytes("#!/bin/sh\necho alpha\n"),
	"alpha/data/blob.bin": new Uint8Array(70_000).map((_, index) => index % 251),
	"beta/SKILL.md": bytes("# beta\n"),
	"gamma/SKILL.md": bytes("# gamma\n"),
};

test("a pin syncs the mirror and reads the commit it then holds", async () => {
	const stub = mirrorOf(FILES);
	const pin = await pinSkills(() => stub, ["beta", "alpha", "beta"]);
	assert.deepEqual(pin, { sha: SHA, names: ["alpha", "beta"] });
	assert.deepEqual(stub.calls, ["sync"]);
});

test("a pin of no skill asks the mirror nothing", async () => {
	const stub = mirrorOf(FILES);
	assert.deepEqual(await pinSkills(() => stub, []), { sha: null, names: [] });
	assert.deepEqual(await pinSkills(() => stub, undefined), { sha: null, names: [] });
	assert.deepEqual(stub.calls, []);
});

test("a pin refuses a bad name and a skill the commit lacks", async () => {
	const stub = mirrorOf(FILES);
	const bad = await pinSkills(() => stub, ["../etc"]);
	assert.equal(bad.status, 400);
	assert.deepEqual(stub.calls, []);
	const missing = await pinSkills(() => stub, ["alpha", "delta"]);
	assert.equal(missing.status, 400);
	assert.match(missing.error, /0123456789ab has no skill delta/);
});

test("the box writes exactly the named skills of the pinned commit", async () => {
	const stub = mirrorOf(FILES);
	const box = tempBox();
	try {
		mkdirSync(join(box.dir, "stale"), { recursive: true });
		writeFileSync(join(box.dir, "stale", "SKILL.md"), "old\n");
		const url = skillsUrl(CLI_HOSTS.skills, { sha: SHA, names: ["alpha", "beta"] });
		assert.equal(url, `http://skills.harness.internal/${SHA}?names=alpha,beta`);
		const fetch = (target) => skillsResponse(() => stub, new Request(target));
		const got = await fetchSkills({ url, dir: box.dir, pinFile: box.pinFile, fetch });
		assert.equal(got.files, 4);
		assert.equal(readFileSync(join(box.dir, "alpha", "SKILL.md"), "utf8"), "# alpha\n");
		assert.deepEqual(new Uint8Array(readFileSync(join(box.dir, "alpha", "data", "blob.bin"))), FILES["alpha/data/blob.bin"]);
		assert.equal(readFileSync(join(box.dir, "beta", "SKILL.md"), "utf8"), "# beta\n");
		assert.equal(existsSync(join(box.dir, "gamma")), false);
		assert.equal(existsSync(join(box.dir, "stale")), false);
		const record = JSON.parse(readFileSync(box.pinFile, "utf8"));
		assert.deepEqual({ sha: record.sha, names: record.names, files: record.files }, { sha: SHA, names: ["alpha", "beta"], files: 4 });
		const reads = stub.calls.length;
		const again = await fetchSkills({ url, dir: box.dir, pinFile: box.pinFile, fetch });
		assert.equal(again.present, true);
		assert.equal(stub.calls.length, reads);
	} finally {
		rmSync(box.root, { recursive: true, force: true });
	}
});

test("a commit the mirror no longer holds leaves the box's skills as they were", async () => {
	const stub = mirrorOf(FILES);
	const box = tempBox();
	try {
		mkdirSync(join(box.dir, "baked"), { recursive: true });
		writeFileSync(join(box.dir, "baked", "SKILL.md"), "baked\n");
		const fetch = (target) => skillsResponse(() => stub, new Request(target));
		const url = skillsUrl(CLI_HOSTS.skills, { sha: OLD, names: ["alpha"] });
		await assert.rejects(fetchSkills({ url, dir: box.dir, pinFile: box.pinFile, fetch }), /answered 404: the skills mirror holds no alpha at fedcba987654/);
		assert.equal(readFileSync(join(box.dir, "baked", "SKILL.md"), "utf8"), "baked\n");
		assert.equal(existsSync(box.pinFile), false);
	} finally {
		rmSync(box.root, { recursive: true, force: true });
	}
});

test("a feed that ends early or leaves the named skills is refused", async () => {
	const box = tempBox();
	const feed = (lines) => async () => new Response(lines.map((line) => `${JSON.stringify(line)}\n`).join(""));
	const url = skillsUrl(CLI_HOSTS.skills, { sha: SHA, names: ["alpha"] });
	const data = btoa("x");
	try {
		mkdirSync(join(box.dir, "baked"), { recursive: true });
		const run = (lines) => fetchSkills({ url, dir: box.dir, pinFile: box.pinFile, fetch: feed(lines) });
		await assert.rejects(run([{ path: "alpha/SKILL.md", data }]), /ended before its last line/);
		await assert.rejects(run([{ path: "alpha/SKILL.md", data }, { done: true, sha: SHA, files: 2 }]), /announced 2 files and sent 1/);
		await assert.rejects(run([{ path: "alpha/../../etc/passwd", data }]), /sent the path/);
		await assert.rejects(run([{ path: "beta/SKILL.md", data }]), /outside the named skills/);
		await assert.rejects(run([{ error: "the mirror broke" }]), /the mirror broke/);
		assert.equal(existsSync(join(box.dir, "baked")), true);
	} finally {
		rmSync(box.root, { recursive: true, force: true });
	}
});

test("the skills route takes only a commit id and skill names", async () => {
	const stub = mirrorOf(FILES);
	const ask = (path, init) => skillsResponse(() => stub, new Request(`http://${CLI_HOSTS.skills}${path}`, init));
	assert.equal((await ask(`/${SHA}`)).status, 400);
	assert.equal((await ask(`/main?names=alpha`)).status, 400);
	assert.equal((await ask(`/${SHA}?names=alpha,../x`)).status, 400);
	assert.equal((await ask(`/${SHA}?names=alpha`, { method: "POST" })).status, 400);
	assert.equal((await ask(`/${SHA}?names=alpha,delta`)).status, 404);
	const ok = await ask(`/${SHA}?names=gamma`);
	assert.equal(ok.status, 200);
	const lines = (await ok.text()).trim().split("\n").map((line) => JSON.parse(line));
	assert.deepEqual(lines, [{ path: "gamma/SKILL.md", data: btoa("# gamma\n") }, { done: true, sha: SHA, files: 1 }]);
});

test("every snapshot links the skills folder and holds the box's skills module", () => {
	const steps = recipeSteps(loadSettings({ local: NOWHERE, rules: NOWHERE }));
	const link = steps.find((step) => step.name === "link the skills folder").command.join(" ");
	assert.match(link, /mkdir -p \/opt\/agent-skills/);
	assert.match(link, /ln -sfn \/opt\/agent-skills \$home\/\.claude\/skills/);
	const boot = steps.find((step) => step.name === "write the ContainerHarness daemon and its boot wrapper");
	const files = JSON.parse(boot.stdin);
	assert.match(files.boot, /OHFLOW_SKILLS_URL/);
	assert.match(files.skills, /export async function fetchSkills/);
	assert.match(boot.command.join(" "), /\/opt\/harness\/box-skills\.mjs/);
});
