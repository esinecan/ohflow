import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { recipeKey, snapshotSettings } from "../snapshot/recipe.mjs";
import { recipeSteps } from "./recipe-files.mjs";
import { loadSettings, settingsFile } from "./settings.mjs";

const USAGE = "usage: node scripts/pins.mjs [--dry-run] [--settings <file>]";
const SHA = /^[0-9a-f]{40}$/;

export function pinnedRepos(snapshot) {
	const { skills, repos } = snapshotSettings(snapshot);
	return [...(skills ? [{ where: "snapshot.skills", ...skills }] : []), ...repos.map(({ repo, sha }, index) => ({ where: `snapshot.repos[${index}]`, repo, sha }))];
}

export function movedPins(pins, heads) {
	return pins.map((pin) => {
		const head = heads[pin.repo];
		if (!SHA.test(head ?? "")) throw new Error(`no head of main for ${pin.repo}`);
		return { ...pin, head, moved: head !== pin.sha };
	});
}

export function rewritePins(text, pins) {
	let out = text;
	for (const pin of pins) {
		if (!pin.moved) continue;
		if (out.split(pin.sha).length !== 2) throw new Error(`the settings file names ${pin.sha} of ${pin.repo} ${out.split(pin.sha).length - 1} times, so the pin is not moved`);
		out = out.replace(pin.sha, pin.head);
	}
	return out;
}

function gh(args) {
	const run = spawnSync("gh", ["api", ...args], { encoding: "utf8" });
	if (run.status !== 0) throw new Error(`gh api ${args[0]} failed: ${(run.stderr || run.stdout || "").trim().slice(0, 300)}`);
	return run.stdout.trim();
}

function headOf(repo) {
	return gh([`repos/${repo}/commits/main`, "-H", "Accept: application/vnd.github.sha"]);
}

function commitsBetween(repo, from, to) {
	try {
		return Number(gh([`repos/${repo}/compare/${from}...${to}`, "--jq", ".ahead_by"]));
	} catch {
		return null;
	}
}

async function main() {
	if (process.argv.includes("--help")) {
		console.log(USAGE);
		return 0;
	}
	const dryRun = process.argv.includes("--dry-run");
	const file = settingsFile();
	const pins = pinnedRepos(loadSettings({ local: file }).snapshot);
	if (pins.length === 0) {
		console.log(`${file} pins no repo`);
		return 0;
	}
	const heads = Object.fromEntries(pins.map((pin) => [pin.repo, headOf(pin.repo)]));
	const result = movedPins(pins, heads);
	const width = Math.max(...result.map((pin) => pin.repo.length));
	for (const pin of result) {
		const name = pin.repo.padEnd(width);
		if (!pin.moved) {
			console.log(`${name}  ${pin.sha.slice(0, 7)}  at the head of main`);
			continue;
		}
		const count = commitsBetween(pin.repo, pin.sha, pin.head);
		console.log(`${name}  ${pin.sha.slice(0, 7)} -> ${pin.head.slice(0, 7)}  ${count === null ? "commit count unknown" : `${count} commit${count === 1 ? "" : "s"}`}  (${pin.where})`);
	}
	const moved = result.filter((pin) => pin.moved);
	if (moved.length === 0) {
		console.log("every pin is at the head of main; nothing to write");
		return 0;
	}
	if (dryRun) {
		console.log(`--dry-run: ${moved.length} pin${moved.length === 1 ? "" : "s"} would move; ${file} is unchanged`);
		return 0;
	}
	writeFileSync(file, rewritePins(readFileSync(file, "utf8"), moved));
	const key = await recipeKey(recipeSteps(loadSettings({ local: file })));
	console.log(`moved ${moved.length} pin${moved.length === 1 ? "" : "s"} in ${file}`);
	console.log(`the snapshot key is now ${key}; steps start from it after node scripts/deploy.mjs and node scripts/snapshot.mjs build`);
	return 0;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
	try {
		process.exit(await main());
	} catch (error) {
		console.error(String(error?.message ?? error));
		process.exit(1);
	}
}
