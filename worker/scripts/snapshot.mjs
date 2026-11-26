import { spawnSync } from "node:child_process";
import { appendFileSync } from "node:fs";
import { recipeKey } from "../snapshot/recipe.mjs";
import { recipeSteps } from "./recipe-files.mjs";
import { loadSettings, settingsFile, workerUrl } from "./settings.mjs";

const USAGE = "usage: node scripts/snapshot.mjs key | status | build [--force] [--log <file>] | verify, each with [--settings <file>]";
const settings = loadSettings({ local: settingsFile() });
const needsToken = recipeSteps(settings).some((step) => step.secret);
const command = process.argv[2];
const url = command === "key" ? null : workerUrl(settings);

function arg(name) {
	const index = process.argv.indexOf(name);
	return index < 0 ? undefined : process.argv[index + 1];
}

function headers() {
	const token = process.env.PI_CLOUD_TOKEN;
	if (!token) throw new Error("PI_CLOUD_TOKEN is not set");
	return { authorization: `Bearer ${token}`, "content-type": "application/json", "user-agent": "pi-cloud-snapshot/1" };
}

function setupToken() {
	if (!needsToken) return undefined;
	const run = spawnSync("gh", ["auth", "token"], { encoding: "utf8" });
	const token = run.stdout.trim();
	if (run.status !== 0 || !token) throw new Error("gh auth token printed no token");
	return token;
}

if (command === "key") {
	console.log(await recipeKey(recipeSteps(settings)));
} else if (command === "status") {
	const response = await fetch(`${url}/snapshot`, { headers: headers() });
	console.log(JSON.stringify(await response.json(), null, 2));
} else if (command === "verify") {
	const response = await fetch(`${url}/snapshot/verify`, { method: "POST", headers: headers(), body: JSON.stringify({ token: setupToken() }) });
	const body = await response.json();
	console.log(JSON.stringify(body, null, 2));
	if (!response.ok) process.exit(1);
} else if (command === "build") {
	const log = arg("--log");
	const response = await fetch(`${url}/snapshot/build`, {
		method: "POST",
		headers: headers(),
		body: JSON.stringify({ token: setupToken(), force: process.argv.includes("--force") }),
	});
	if (!response.ok) throw new Error(`build answered ${response.status}: ${await response.text()}`);
	const decoder = new TextDecoder();
	let buffer = "";
	let failed = true;
	for await (const chunk of response.body) {
		buffer += decoder.decode(chunk, { stream: true });
		let newline;
		while ((newline = buffer.indexOf("\n")) >= 0) {
			const text = buffer.slice(0, newline);
			buffer = buffer.slice(newline + 1);
			if (!text.trim()) continue;
			const event = JSON.parse(text);
			if (event.type === "snapshot") failed = false;
			if (event.type === "beat") continue;
			const line = `${new Date(event.t).toISOString()} ${JSON.stringify(event)}`;
			console.log(line);
			if (log) appendFileSync(log, `${line}\n`);
		}
	}
	if (failed) process.exit(1);
} else {
	console.error(USAGE);
	process.exit(2);
}
