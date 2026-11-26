import { spawnSync } from "node:child_process";
import { appendFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { BOX_PATH, recipeKey } from "../snapshot/recipe.mjs";
import { recipeSteps } from "./recipe-files.mjs";
import { loadSettings, settingsFile } from "./settings.mjs";

const here = dirname(fileURLToPath(import.meta.url));

function arg(name, fallback) {
	const index = process.argv.indexOf(name);
	return index < 0 ? fallback : process.argv[index + 1];
}

const steps = recipeSteps(loadSettings({ local: settingsFile() }));
if (process.argv.includes("--key")) {
	console.log(await recipeKey(steps));
	process.exit(0);
}

const distro = arg("--distro", "boxtest");
const from = Number(arg("--from", "0"));
const log = arg("--log", join(tmpdir(), "try-recipe.log"));
const launcher = `/mnt/c${join(here, "wsl-launch.cjs").slice(2).replaceAll("\\", "/")}`;
const token = spawnSync("gh", ["auth", "token"], { encoding: "utf8" }).stdout.trim();
const beat = (line) => {
	const text = `${new Date().toISOString()} ${line}`;
	console.log(text);
	appendFileSync(log, `${text}\n`);
};

for (const [index, step] of steps.entries()) {
	if (index < from) continue;
	const agent = step.user === "agent";
	const env = [`HOME=${agent ? "/home/agent" : "/root"}`, `PATH=${BOX_PATH}`, "DEBIAN_FRONTEND=noninteractive"];
	const user = agent ? "agent" : "root";
	beat(`start ${index} ${step.name}`);
	const started = Date.now();
	const argv = Buffer.from(JSON.stringify(["env", "-u", "WSLENV", ...env, ...step.command])).toString("base64");
	const run = spawnSync("wsl", ["-d", distro, "-u", user, "--cd", agent ? "/home/agent" : "/root", "--", "/usr/local/bin/node", launcher, argv], {
		input: step.stdin ?? "",
		encoding: "utf8",
		maxBuffer: 256 * 1024 * 1024,
		env: step.secret ? { ...process.env, GH_SETUP_TOKEN: token, WSLENV: "GH_SETUP_TOKEN/u" } : { ...process.env, WSLENV: "" },
	});
	const seconds = Math.round((Date.now() - started) / 1000);
	const tail = `${run.stdout ?? ""}${run.stderr ?? ""}`.trim().split("\n").slice(-15).join("\n");
	beat(`end ${index} ${step.name} exit=${run.status} ${seconds}s`);
	if (run.status !== 0) {
		console.log(tail);
		process.exit(1);
	}
}
beat("recipe done");
