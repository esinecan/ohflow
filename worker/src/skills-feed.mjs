export const SKILL_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const SHA_PATH = /^\/([0-9a-f]{40})$/;
const READ_BATCH_BYTES = 4 * 1024 * 1024;
const BASE64_CHUNK = 0x8000;

export async function pinSkills(mirror, names) {
	if (names == null || names.length === 0) return { sha: null, names: [] };
	const bad = names.filter((name) => !SKILL_NAME.test(name));
	if (bad.length) return { status: 400, error: `skill names must match ${SKILL_NAME}, got ${JSON.stringify(bad)}` };
	const synced = await mirror().sync();
	const missing = names.filter((name) => !synced.skills.includes(name));
	if (missing.length) return { status: 400, error: `the skills repo at ${synced.sha.slice(0, 12)} has no skill ${missing.join(", ")}` };
	return { sha: synced.sha, names: [...new Set(names)].sort() };
}

export function skillsUrl(host, pin) {
	return `http://${host}/${pin.sha}?names=${pin.names.join(",")}`;
}

export async function* mirroredFiles(stub, sha, entries) {
	const batches = [[]];
	let size = 0;
	for (const entry of entries) {
		if (size + entry.size > READ_BATCH_BYTES && batches.at(-1).length) {
			batches.push([]);
			size = 0;
		}
		batches.at(-1).push(entry.path);
		size += entry.size;
	}
	for (const batch of batches) {
		if (!batch.length) continue;
		for (const { path, data } of await stub.read(sha, batch)) {
			if (data) yield { path, data };
		}
	}
}

function base64(bytes) {
	let text = "";
	for (let at = 0; at < bytes.length; at += BASE64_CHUNK) text += String.fromCharCode(...bytes.subarray(at, at + BASE64_CHUNK));
	return btoa(text);
}

export function skillsFeed(stub, sha, entries) {
	const encoder = new TextEncoder();
	const files = mirroredFiles(stub, sha, entries);
	const line = (value) => encoder.encode(`${JSON.stringify(value)}\n`);
	let count = 0;
	return new ReadableStream({
		async pull(controller) {
			try {
				const { value, done } = await files.next();
				if (done) {
					controller.enqueue(line({ done: true, sha, files: count }));
					controller.close();
					return;
				}
				count += 1;
				controller.enqueue(line({ path: value.path, data: base64(value.data) }));
			} catch (error) {
				controller.enqueue(line({ error: String(error?.message ?? error) }));
				controller.close();
			}
		},
	});
}

export async function skillsResponse(mirror, request) {
	const url = new URL(request.url);
	const sha = SHA_PATH.exec(url.pathname)?.[1];
	const names = (url.searchParams.get("names") ?? "").split(",").filter(Boolean);
	if (request.method !== "GET" || !sha || names.length === 0 || names.some((name) => !SKILL_NAME.test(name))) {
		return new Response("the skills route takes GET /<40-digit commit id>?names=<skill>,<skill>\n", { status: 400 });
	}
	const stub = mirror();
	const entries = await stub.manifest(sha, names);
	const held = new Set(entries.map((entry) => entry.path.split("/")[0]));
	const missing = names.filter((name) => !held.has(name));
	if (missing.length) return new Response(`the skills mirror holds no ${missing.join(", ")} at ${sha.slice(0, 12)}\n`, { status: 404 });
	return new Response(skillsFeed(stub, sha, entries), {
		headers: { "content-type": "application/x-ndjson", "cache-control": "no-store", "content-encoding": "identity" },
	});
}
