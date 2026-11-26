import { spawn } from "node:child_process";
import { existsSync, rmSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";
import { snapshotSettings } from "../snapshot/recipe.mjs";
import {
	DEFAULT_NAME,
	deployedUrl,
	loadSettings,
	operatorDefine,
	recordUrl,
	SANDBOX_CONFIG,
	settingsFile,
	skillsSource,
	WORKER_CONFIG,
	WORKER_DIR,
	workerConfigs,
	workerName,
} from "./settings.mjs";

const USAGE = "usage: node scripts/deploy.mjs [--dry-run] [--only sandbox|worker] [--settings <file>]";
const dryRun = process.argv.includes("--dry-run");
const onlyAt = process.argv.indexOf("--only");
const only = onlyAt < 0 ? null : process.argv[onlyAt + 1];
if (only && !["sandbox", "worker"].includes(only)) {
	console.error(USAGE);
	process.exit(2);
}

const wrangler = join(WORKER_DIR, "node_modules", "wrangler", "bin", "wrangler.js");
if (!existsSync(wrangler)) {
	console.error(`wrangler is not installed: run npm ci in ${WORKER_DIR}`);
	process.exit(2);
}

const settingsPath = settingsFile();
const settings = loadSettings({ local: settingsPath });
snapshotSettings(settings.snapshot);
const name = workerName(settings);
const configs = workerConfigs(name);
console.log(`Worker: ${name}, code mode Worker: ${configs.sandbox.name}`);
const env = { ...process.env };
if (settings.account_id) env.CLOUDFLARE_ACCOUNT_ID = settings.account_id;

const vars = {};
if (settings.git_owner) vars.GIT_OWNER = settings.git_owner;
else console.warn(`git_owner is unset in ${settingsPath}: the Worker refuses every step's repo until it is set`);
const skills = skillsSource(settings);
if (skills.repo) {
	vars.SKILLS_REPO = skills.repo;
	if (skills.rootSkill) vars.SKILLS_ROOT_SKILL = skills.rootSkill;
	console.log(`skills mirror: ${skills.repo}${skills.rootSkill ? ` (the repo root is the skill ${skills.rootSkill})` : ""}${skills.derived ? ", from this checkout's origin" : ""}`);
} else {
	const why = skills.foreign ? `this checkout's origin ${skills.foreign} is not owned by git_owner` : "this checkout's origin is not a GitHub repo of git_owner";
	console.warn(`no skills repo: ${why}. Set skills_repo to a repo you control; a step that names a skill is refused`);
}

const generated = [];
function configFile(base, config) {
	let file = base;
	if (name !== DEFAULT_NAME) {
		file = join(base, "..", "wrangler.generated.json");
		writeFileSync(file, `${JSON.stringify(config, null, "\t")}\n`);
		generated.push(file);
	}
	return relative(WORKER_DIR, file).replaceAll("\\", "/");
}

function wranglerRun(args) {
	console.log(`> wrangler ${args.map((arg) => (arg.length > 80 ? `${arg.slice(0, 77)}...` : arg)).join(" ")}`);
	return new Promise((done) => {
		const child = spawn(process.execPath, [wrangler, ...args], { cwd: WORKER_DIR, env, stdio: ["inherit", "pipe", "inherit"] });
		let output = "";
		child.stdout.on("data", (chunk) => {
			process.stdout.write(chunk);
			output += chunk;
		});
		child.on("close", (status) => done({ status: status ?? 1, output }));
	});
}

const dry = (outdir) => (dryRun ? ["--dry-run", "--outdir", join(WORKER_DIR, "dist", outdir)] : []);

let status = 0;
try {
	if (only !== "worker") {
		const config = configFile(SANDBOX_CONFIG, configs.sandbox);
		({ status } = await wranglerRun(["deploy", "-c", config, ...dry("sandbox")]));
	}
	if (status === 0 && only !== "sandbox") {
		const args = ["deploy"];
		if (name !== DEFAULT_NAME) args.push("-c", configFile(WORKER_CONFIG, configs.worker));
		args.push(...dry("worker"));
		for (const [key, value] of Object.entries(vars)) args.push("--var", `${key}:${value}`);
		args.push("--define", `PI_CLOUD_OPERATOR:${JSON.stringify(operatorDefine(settings))}`);
		const run = await wranglerRun(args);
		status = run.status;
		const url = status === 0 && !dryRun ? deployedUrl(run.output, name) : null;
		if (url) {
			recordUrl(name, url);
			console.log(`recorded ${url} for ${name}`);
		}
	}
} finally {
	for (const file of generated) rmSync(file, { force: true });
}
process.exit(status);
