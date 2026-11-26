import { mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

export const SKILLS_DIR = "/opt/agent-skills";
export const PIN_FILE = "/etc/agent-box/skills.json";
const FETCH_MS = 20_000;

function pinOf(url) {
	const target = new URL(url);
	return { sha: target.pathname.slice(1), names: (target.searchParams.get("names") ?? "").split(",").filter(Boolean) };
}

function held(pinFile) {
	try {
		return JSON.parse(readFileSync(pinFile, "utf8"));
	} catch {
		return null;
	}
}

function checkedPath(path, names) {
	const parts = String(path).split("/");
	if (parts.length < 2 || parts.some((part) => !part || part === "." || part === ".." || part.includes("\\"))) throw new Error(`the skills route sent the path ${JSON.stringify(path)}`);
	if (!names.includes(parts[0])) throw new Error(`the skills route sent ${path}, outside the named skills`);
	return parts.join("/");
}

async function* lines(body) {
	const decoder = new TextDecoder();
	let buffer = "";
	for await (const chunk of body) {
		buffer += decoder.decode(chunk, { stream: true });
		let newline;
		while ((newline = buffer.indexOf("\n")) >= 0) {
			const text = buffer.slice(0, newline);
			buffer = buffer.slice(newline + 1);
			if (text.trim()) yield JSON.parse(text);
		}
	}
	if (buffer.trim()) yield JSON.parse(buffer);
}

export async function fetchSkills({ url, dir = SKILLS_DIR, pinFile = PIN_FILE, fetch = globalThis.fetch }) {
	const pin = pinOf(url);
	const before = held(pinFile);
	if (before?.sha === pin.sha && JSON.stringify(before.names) === JSON.stringify(pin.names)) return { ...before, present: true };
	const response = await fetch(url, { signal: AbortSignal.timeout(FETCH_MS) });
	if (!response.ok) throw new Error(`the skills route answered ${response.status}: ${(await response.text()).trim().slice(0, 300)}`);
	const stage = `${dir}.incoming`;
	rmSync(stage, { recursive: true, force: true });
	mkdirSync(stage, { recursive: true });
	let files = 0;
	let last = null;
	for await (const entry of lines(response.body)) {
		if (entry.error) throw new Error(`the skills route failed: ${entry.error}`);
		if (entry.done) {
			last = entry;
			continue;
		}
		const data = Buffer.from(entry.data, "base64");
		const target = `${stage}/${checkedPath(entry.path, pin.names)}`;
		mkdirSync(dirname(target), { recursive: true });
		writeFileSync(target, data, { mode: data.subarray(0, 2).toString("latin1") === "#!" ? 0o755 : 0o644 });
		files += 1;
	}
	if (!last) throw new Error("the skills route ended before its last line");
	if (last.files !== files || files === 0) throw new Error(`the skills route announced ${last.files} files and sent ${files}`);
	rmSync(dir, { recursive: true, force: true });
	renameSync(stage, dir);
	const record = { ...pin, files, at: new Date().toISOString() };
	mkdirSync(dirname(pinFile), { recursive: true });
	writeFileSync(pinFile, `${JSON.stringify(record)}\n`);
	return record;
}
