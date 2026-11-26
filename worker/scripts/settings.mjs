import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gitIdentity } from "../snapshot/recipe.mjs";

export const WORKER_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
export const SHIPPED_FILE = join(WORKER_DIR, "pi-cloud.settings.json");
export const LOCAL_FILE = join(WORKER_DIR, "pi-cloud.settings.local.json");
export const RULES_FILE = join(WORKER_DIR, "snapshot", "AGENTS.local.md");
export const URLS_FILE = join(WORKER_DIR, ".pi-cloud-urls.json");
export const WORKER_CONFIG = join(WORKER_DIR, "wrangler.jsonc");
export const SANDBOX_CONFIG = join(WORKER_DIR, "sandbox", "wrangler.jsonc");
export const DEFAULT_NAME = "pi-cloud";
const NAME = /^[a-z0-9](?:[a-z0-9-]{0,52}[a-z0-9])?$/;

function isObject(value) {
	return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function merge(base, over) {
	if (!isObject(base) || !isObject(over)) return over === undefined ? base : over;
	const out = { ...base };
	for (const [key, value] of Object.entries(over)) out[key] = merge(base[key], value);
	return out;
}

function readText(file) {
	return readFileSync(file, "utf8").replace(/\r\n/g, "\n");
}

export function loadSettings({ local = LOCAL_FILE, rules = RULES_FILE } = {}) {
	const shipped = JSON.parse(readText(SHIPPED_FILE));
	const own = existsSync(local) ? JSON.parse(readText(local)) : {};
	return { ...merge(shipped, own), rules: existsSync(rules) ? readText(rules) : "" };
}

export function operatorDefine(settings) {
	return { snapshot: settings.snapshot, rules: settings.rules, git_identity: gitIdentity(settings.git_identity) };
}

export function settingsFile(argv = process.argv) {
	const at = argv.indexOf("--settings");
	if (at < 0) return LOCAL_FILE;
	const file = argv[at + 1];
	if (!file || file.startsWith("--")) throw new Error("--settings needs a settings file");
	if (!existsSync(file)) throw new Error(`no settings file ${resolve(file)}`);
	return resolve(file);
}

export function workerName(settings) {
	const name = settings.name ?? DEFAULT_NAME;
	if (typeof name !== "string" || !NAME.test(name)) {
		throw new Error(`name ${JSON.stringify(name)} is not a Worker name: lowercase letters, digits and inner dashes, at most 54 characters`);
	}
	return name;
}

export function codemodeName(name) {
	return `${name}-codemode`;
}

export function readConfigs() {
	return { worker: JSON.parse(readText(WORKER_CONFIG)), sandbox: JSON.parse(readText(SANDBOX_CONFIG)) };
}

export function workerConfigs(name, base = readConfigs()) {
	const codemode = codemodeName(name);
	const bindings = base.worker.durable_objects.bindings.map((binding) =>
		binding.script_name === base.sandbox.name ? { ...binding, script_name: codemode } : binding,
	);
	return {
		worker: { ...base.worker, name, durable_objects: { ...base.worker.durable_objects, bindings } },
		sandbox: { ...base.sandbox, name: codemode },
	};
}

export function deployedUrl(output, name) {
	return new RegExp(`https://${name}[.][a-z0-9-]+[.]workers[.]dev`).exec(output)?.[0] ?? null;
}

function recordedUrls(file) {
	return existsSync(file) ? JSON.parse(readText(file)) : {};
}

export function recordUrl(name, url, file = URLS_FILE) {
	writeFileSync(file, `${JSON.stringify({ ...recordedUrls(file), [name]: url }, null, "\t")}\n`);
}

export function workerUrl(settings, { recorded = URLS_FILE } = {}) {
	const name = workerName(settings);
	const url = process.env.PI_CLOUD_URL ?? settings.url ?? recordedUrls(recorded)[name];
	if (!url) throw new Error(`no URL for the Worker ${name}: deploy it with scripts/deploy.mjs, which records its address, or set PI_CLOUD_URL or "url" in the settings`);
	return url.replace(/\/$/, "");
}

function git(args) {
	const run = spawnSync("git", ["-C", join(WORKER_DIR, ".."), ...args], { encoding: "utf8" });
	return run.status === 0 ? run.stdout.trim() : null;
}

export function githubRepo(url) {
	const match = /github\.com[:/]([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?\/?$/.exec(url ?? "");
	return match ? `${match[1]}/${match[2]}` : null;
}

export function ownedBy(repo, owner) {
	return Boolean(owner) && repo.split("/")[0].toLowerCase() === String(owner).toLowerCase();
}

export function skillsSource(settings) {
	if (settings.skills_repo) return { repo: settings.skills_repo, rootSkill: settings.skills_root_skill ?? null, derived: false };
	const repo = githubRepo(git(["remote", "get-url", "origin"]));
	const prefix = git(["rev-parse", "--show-prefix"]);
	if (!repo || prefix === null) return { repo: null, rootSkill: null, derived: true };
	if (!ownedBy(repo, settings.git_owner)) return { repo: null, rootSkill: null, derived: true, foreign: repo };
	if (prefix === "") {
		const skill = existsSync(join(WORKER_DIR, "..", "SKILL.md")) ? readText(join(WORKER_DIR, "..", "SKILL.md")) : "";
		const name = /^name:\s*["']?([A-Za-z0-9._-]+)/m.exec(skill)?.[1] ?? null;
		return { repo, rootSkill: name, derived: true };
	}
	if (/^[^/]+\/$/.test(prefix)) return { repo, rootSkill: null, derived: true };
	return { repo: null, rootSkill: null, derived: true };
}
