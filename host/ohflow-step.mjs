import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { tether } from "./src/tether.mjs";

export const STEPS = join(homedir(), ".pi-durable", "ohflow");
const here = dirname(fileURLToPath(import.meta.url));
const TOOL_NAMES = { terminal: ["bash"], file_editor: ["read", "write", "edit"], read: ["read"], write: ["write"], edit: ["edit"], bash: ["bash"] };

const emit = (event) => process.stdout.write(`${JSON.stringify(event)}\n`);

export function hostVersion() {
	const file = join(here, ".version");
	return existsSync(file) ? readFileSync(file, "utf8").trim() : "source";
}

function stepDir(key) {
	if (!/^[A-Za-z0-9._-]+$/.test(key ?? "")) throw new Error(`attempt key must match [A-Za-z0-9._-]+, got ${JSON.stringify(key)}`);
	return join(STEPS, key);
}

function git(args, cwd) {
	const result = spawnSync("git", args, { cwd, encoding: "utf8", windowsHide: true, env: { ...process.env, GIT_TERMINAL_PROMPT: "0" } });
	if (result.status !== 0) throw new Error(`git ${args.join(" ")} exited ${result.status}: ${(result.stderr || result.stdout).trim()}`);
	return result.stdout.trim();
}

function toolList(only) {
	if (!only?.length) return undefined;
	const names = new Set();
	for (const name of only) {
		const mapped = TOOL_NAMES[name];
		if (!mapped) throw new Error(`tools.only names ${name}; the durable host knows ${Object.keys(TOOL_NAMES).join(", ")}`);
		for (const tool of mapped) names.add(tool);
	}
	return [...names];
}

function checkout(work, durable) {
	if (!existsSync(join(work, ".git"))) {
		git(["clone", "--quiet", "--single-branch", "--branch", durable.branch, durable.remote_url, work], dirname(work));
	}
	const head = git(["rev-parse", "HEAD"], work);
	if (!durable.reattach && head !== durable.start_sha) throw new Error(`the clone of ${durable.branch} is at ${head}, not at the start commit ${durable.start_sha}`);
	return head;
}

function state(work) {
	return { head: git(["rev-parse", "HEAD"], work), dirty: git(["status", "--porcelain"], work).split("\n").filter(Boolean) };
}

function publish(work, branch) {
	const now = state(work);
	git(["push", "--quiet", "--force", "origin", `HEAD:refs/heads/${branch}`], work);
	return { ...now, pushed: true };
}

async function drive({ dir, work, spec, reattach }) {
	const { closeHost, context, openHost, parseModel, transcript } = await import("./src/host.mjs");
	const { PiEventWriter, streamPiEvents } = await import("./src/events.mjs");
	const file = join(dir, "session.sqlite");
	const durable = spec.durable ?? {};
	const model = parseModel(spec.model?.model);
	const thinkingLevel = spec.model?.params?.thinking;
	const harness = await openHost(file, {
		cwd: work,
		tools: toolList(spec.tools?.only),
		writeScope: spec.write_scope?.length ? spec.write_scope : undefined,
		bashCapSeconds: durable.command_cap_s ?? 300,
		skills: spec.skills ?? [],
		lockWaitSeconds: reattach ? 60 : 0,
	});
	const root = await harness.root(context, { agent: { model, cwd: work, ...(thinkingLevel ? { thinkingLevel } : {}) } });
	await root.configure({ model, ...(thinkingLevel ? { thinkingLevel } : {}) }, context);
	const writer = new PiEventWriter((line) => process.stdout.write(line));
	const stream = await streamPiEvents(harness, root, context, writer);
	const brief = readFileSync(join(dir, "brief.md"), "utf8");
	const submission = await root.submit({ type: "input", content: brief, requestId: "ohflow-brief" }, context);
	const settled = await submission.wait(context);
	await stream.finish();
	const usage = await harness.usage(context);
	writeFileSync(join(dir, "usage.json"), JSON.stringify(usage, null, 2));
	const lines = (await transcript(root)).filter((entry) => entry.text).map((entry) => `- ${entry.kind}: ${entry.text}`);
	writeFileSync(join(dir, "transcript.md"), `# ${spec.coord ?? dir}\n\nSession: ${file}\n\n${lines.join("\n")}\n`);
	await closeHost(harness, file);
	return { settled, usage, session: file };
}

async function run(key) {
	const dir = stepDir(key);
	const spec = JSON.parse(readFileSync(join(dir, "spec.json"), "utf8"));
	const durable = spec.durable;
	const work = join(dir, "work");
	const reattach = existsSync(join(dir, "session.sqlite"));
	emit({ type: "durable_start", key, dir, reattach, host: hostVersion(), node: process.versions.node });
	const startHead = checkout(work, { ...durable, reattach });
	const { settled, usage, session } = await drive({ dir, work, spec, reattach });
	const pushed = publish(work, durable.branch);
	emit({ type: "durable_end", status: settled.status, reason: settled.reason, start: startHead, branch: durable.branch, session, ...pushed, usage });
}

async function local(path) {
	if (!path || !isAbsolute(path)) throw new Error(`local needs the absolute step folder, got ${JSON.stringify(path)}`);
	const dir = resolve(path);
	const spec = JSON.parse(readFileSync(join(dir, "spec.json"), "utf8"));
	const work = spec.durable?.work;
	if (!work || !existsSync(work)) throw new Error(`spec.durable.work names no folder on this machine: ${JSON.stringify(work)}`);
	const reattach = existsSync(join(dir, "session.sqlite"));
	emit({ type: "durable_start", key: spec.durable?.key ?? null, dir, reattach, local: true, host: hostVersion(), node: process.versions.node });
	const startHead = state(work).head;
	const { settled, usage, session } = await drive({ dir, work, spec, reattach });
	emit({ type: "durable_end", status: settled.status, reason: settled.reason, start: startHead, branch: null, session, ...state(work), pushed: false, local: true, usage });
}

async function main([mode, arg]) {
	if (mode === "prepare") {
		const dir = stepDir(arg);
		mkdirSync(dir, { recursive: true });
		emit({ type: "durable_prepared", key: arg, dir, session: existsSync(join(dir, "session.sqlite")), host: hostVersion() });
		return;
	}
	if (mode === "run") {
		tether();
		return run(arg);
	}
	if (mode === "local") {
		tether({ intervalMs: 0 });
		return local(arg);
	}
	throw new Error("usage: node ohflow-step.mjs prepare|run <key> | local <step folder>");
}

try {
	await main(process.argv.slice(2));
	process.exit(0);
} catch (error) {
	emit({ type: "durable_error", name: error?.name, message: String(error?.message ?? error) });
	process.exit(1);
}
