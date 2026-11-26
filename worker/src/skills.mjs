import { DurableObject } from "cloudflare:workers";
import { mirroredFiles, SKILL_NAME } from "./skills-feed.mjs";

export { pinSkills, SKILL_NAME, skillsResponse, skillsUrl } from "./skills-feed.mjs";
export const SKILLS_ROOT = "/workspace/.agents/skills";
export const SKILLS_OBJECT = "agent-skills";
const REPO = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const CHECK_MS = 60_000;
const MAX_FILE_BYTES = 512 * 1024;
const KEEP_VERSIONS = 3;
const COMPLETE_KEY = "complete";
const CHECKED_KEY = "checked";
const SCHEMA = [
	"CREATE TABLE IF NOT EXISTS files (sha TEXT NOT NULL, path TEXT NOT NULL, dir TEXT NOT NULL, data BLOB NOT NULL, PRIMARY KEY (sha, path))",
	"CREATE TABLE IF NOT EXISTS versions (sha TEXT PRIMARY KEY, record TEXT NOT NULL, at INTEGER NOT NULL)",
];

function paxPath(text) {
	for (const line of text.split("\n")) {
		const match = /^\d+ path=(.*)$/.exec(line);
		if (match) return match[1];
	}
	return null;
}

class ByteReader {
	constructor(stream) {
		this.reader = stream.getReader();
		this.chunks = [];
		this.length = 0;
		this.done = false;
	}

	async fill(count) {
		while (this.length < count && !this.done) {
			const { value, done } = await this.reader.read();
			if (done) this.done = true;
			else if (value.length) {
				this.chunks.push(value);
				this.length += value.length;
			}
		}
		return this.length >= count;
	}

	async consume(count, copy) {
		const out = copy ? new Uint8Array(count) : null;
		let at = 0;
		while (at < count) {
			if (!(await this.fill(1))) return null;
			const head = this.chunks[0];
			const part = Math.min(head.length, count - at);
			out?.set(head.subarray(0, part), at);
			if (part === head.length) this.chunks.shift();
			else this.chunks[0] = head.subarray(part);
			this.length -= part;
			at += part;
		}
		return out ?? true;
	}

	take(count) {
		return this.consume(count, true);
	}

	skip(count) {
		return this.consume(count, false);
	}
}

export async function* tarEntries(stream, want) {
	const input = new ByteReader(stream);
	const decoder = new TextDecoder();
	let longPath = null;
	for (;;) {
		const header = await input.take(512);
		if (!header || header.every((byte) => byte === 0)) return;
		const field = (start, length) => decoder.decode(header.subarray(start, start + length)).split("\0")[0];
		const size = parseInt(field(124, 12).trim() || "0", 8);
		const type = String.fromCharCode(header[156] || 48);
		const padded = Math.ceil(size / 512) * 512;
		if (type === "x") {
			const data = await input.take(padded);
			longPath = paxPath(decoder.decode(data.subarray(0, size)));
			continue;
		}
		if (type === "g") {
			await input.skip(padded);
			continue;
		}
		const prefix = field(257, 6).startsWith("ustar") ? field(345, 155) : "";
		const name = field(0, 100);
		const path = longPath ?? (prefix ? `${prefix}/${name}` : name);
		longPath = null;
		if (type !== "0" || !want(path, size)) {
			await input.skip(padded);
			continue;
		}
		const data = await input.take(padded);
		yield { path, data: data.subarray(0, size) };
	}
}

export function skillsSource(env) {
	const repo = env.SKILLS_REPO;
	if (!repo || !REPO.test(repo)) throw new Error(`the Worker's SKILLS_REPO var is ${repo ? `not <owner>/<name>: ${repo}` : "unset"}, so no skills repo is mirrored`);
	const rootSkill = env.SKILLS_ROOT_SKILL || null;
	if (rootSkill && !SKILL_NAME.test(rootSkill)) throw new Error(`the Worker's SKILLS_ROOT_SKILL var is not a skill name: ${rootSkill}`);
	return { repo, rootSkill };
}

export function mirroredPath(path, size, rootSkill = null) {
	const inside = path.split("/").slice(1);
	const parts = rootSkill ? [rootSkill, ...inside] : inside;
	if (parts.length < 2) return null;
	if (parts.some((part) => !part || part.startsWith("."))) return null;
	if (!SKILL_NAME.test(parts[0])) return null;
	if (size > MAX_FILE_BYTES) return null;
	return parts.join("/");
}

export class SkillsMirror extends DurableObject {
	syncing = null;

	constructor(ctx, env) {
		super(ctx, env);
		for (const statement of SCHEMA) ctx.storage.sql.exec(statement);
	}

	sql(query, ...args) {
		return this.ctx.storage.sql.exec(query, ...args).toArray();
	}

	async github(path, accept) {
		if (!this.env.GITHUB_TOKEN) throw new Error("the Worker has no GITHUB_TOKEN, so the skills repo cannot be mirrored");
		return fetch(`https://api.github.com${path}`, {
			headers: { authorization: `Bearer ${this.env.GITHUB_TOKEN}`, accept, "user-agent": "pi-cloud", "x-github-api-version": "2022-11-28" },
		});
	}

	async headSha() {
		const { repo } = skillsSource(this.env);
		const response = await this.github(`/repos/${repo}/commits/main`, "application/vnd.github.sha");
		if (!response.ok) throw new Error(`GitHub head of ${repo} answered ${response.status}`);
		return (await response.text()).trim();
	}

	async mirror(sha) {
		const started = Date.now();
		this.sql("DELETE FROM files WHERE sha = ?", sha);
		const { repo, rootSkill } = skillsSource(this.env);
		const response = await this.github(`/repos/${repo}/tarball/${sha}`, "application/vnd.github+json");
		if (!response.ok) throw new Error(`GitHub tarball of ${repo} at ${sha} answered ${response.status}`);
		const skills = new Set();
		const entries = tarEntries(response.body.pipeThrough(new DecompressionStream("gzip")), (path, size) => mirroredPath(path, size, rootSkill) !== null);
		for await (const { path, data } of entries) {
			const rel = mirroredPath(path, data.length, rootSkill);
			const dir = rel.split("/")[0];
			if (rel === `${dir}/SKILL.md`) skills.add(dir);
			this.sql("INSERT OR REPLACE INTO files (sha, path, dir, data) VALUES (?, ?, ?, ?)", sha, rel, dir, data);
		}
		for (const { dir } of this.sql("SELECT DISTINCT dir FROM files WHERE sha = ?", sha)) {
			if (!skills.has(dir)) this.sql("DELETE FROM files WHERE sha = ? AND dir = ?", sha, dir);
		}
		const totals = this.sql("SELECT COUNT(*) AS files, COALESCE(SUM(LENGTH(data)), 0) AS bytes FROM files WHERE sha = ?", sha)[0];
		const record = { sha, skills: [...skills].sort(), files: totals.files, bytes: totals.bytes, seconds: Math.round((Date.now() - started) / 100) / 10, at: new Date().toISOString() };
		this.sql("INSERT OR REPLACE INTO versions (sha, record, at) VALUES (?, ?, ?)", sha, JSON.stringify(record), Date.now());
		await this.ctx.storage.put(COMPLETE_KEY, record);
		for (const old of this.sql("SELECT sha FROM versions ORDER BY at DESC LIMIT -1 OFFSET ?", KEEP_VERSIONS)) {
			this.sql("DELETE FROM files WHERE sha = ?", old.sha);
			this.sql("DELETE FROM versions WHERE sha = ?", old.sha);
		}
		return record;
	}

	syncTo(sha) {
		if (this.syncing?.sha !== sha) {
			const earlier = this.syncing?.done.catch(() => {}) ?? Promise.resolve();
			const done = earlier
				.then(() => this.mirror(sha))
				.finally(() => {
					if (this.syncing?.done === done) this.syncing = null;
				});
			this.syncing = { sha, done };
		}
		return this.syncing.done;
	}

	async check() {
		const checked = (await this.ctx.storage.get(CHECKED_KEY)) ?? 0;
		if (Date.now() - checked < CHECK_MS) return null;
		await this.ctx.storage.put(CHECKED_KEY, Date.now());
		const head = await this.headSha();
		const complete = await this.ctx.storage.get(COMPLETE_KEY);
		if (complete?.sha !== head) await this.ctx.storage.setAlarm(Date.now());
		return head;
	}

	async current() {
		const complete = await this.ctx.storage.get(COMPLETE_KEY);
		try {
			const head = await this.check();
			if (!complete) return await this.syncTo(head ?? (await this.headSha()));
		} catch (error) {
			if (!complete) throw error;
			return { ...complete, error: String(error?.message ?? error) };
		}
		return complete;
	}

	async sync() {
		const head = await this.headSha();
		await this.ctx.storage.put(CHECKED_KEY, Date.now());
		const complete = await this.ctx.storage.get(COMPLETE_KEY);
		if (complete?.sha === head) return { ...complete, reused: true };
		return this.syncTo(head);
	}

	async alarm() {
		await this.sync();
	}

	manifest(sha, names) {
		if (!names) return this.sql("SELECT path, LENGTH(data) AS size FROM files WHERE sha = ? ORDER BY path", sha);
		const wanted = new Set(names);
		return this.sql("SELECT path, dir, LENGTH(data) AS size FROM files WHERE sha = ? ORDER BY path", sha)
			.filter((row) => wanted.has(row.dir))
			.map(({ path, size }) => ({ path, size }));
	}

	read(sha, paths) {
		return paths.map((path) => {
			const row = this.sql("SELECT data FROM files WHERE sha = ? AND path = ?", sha, path)[0];
			return { path, data: row ? new Uint8Array(row.data) : null };
		});
	}
}

export function skillsMirror(binding) {
	return binding.getByName(SKILLS_OBJECT);
}

export function skillsMount({ mirror, pin, log = console }) {
	let pinned;
	const resolve = async () => {
		pinned ??= await pin();
		return pinned;
	};
	return {
		kind: "agent-skills",
		mode: "read-only",
		strategy: "eager",
		version: async () => {
			try {
				const { sha, names } = await resolve();
				return sha ? `${sha}:${names ? names.join(",") : "*"}` : "none";
			} catch (error) {
				log.error?.(JSON.stringify({ ev: "skills_version_error", message: String(error?.message ?? error) }));
				return "none";
			}
		},
		async materialize(api) {
			try {
				const { sha, names } = await resolve();
				if (!sha) return;
				const stub = mirror();
				for await (const { path, data } of mirroredFiles(stub, sha, await stub.manifest(sha, names))) {
					await api.writeFile(`${api.root}/${path}`, new Response(data).body);
				}
			} catch (error) {
				log.error?.(JSON.stringify({ ev: "skills_materialize_error", message: String(error?.message ?? error) }));
			}
		},
	};
}

export function keepMkdirOfExistingDirs(workspace) {
	const fs = workspace.fs;
	const mkdir = fs.mkdir.bind(fs);
	fs.mkdir = async (path, options = {}) => {
		if (options.recursive) {
			const found = await fs.stat(path).catch(() => null);
			if (found?.isDirectory) return;
		}
		return mkdir(path, options);
	};
	return workspace;
}
