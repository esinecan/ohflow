import { DatabaseSync } from "node:sqlite";

const held = new Map();

export class HostLocked extends Error {
	constructor(file, cause) {
		super(`${file} has another owner: ${cause.message}`, { cause });
		this.name = "HostLocked";
	}
}

function tryLock(path) {
	const db = new DatabaseSync(path);
	try {
		db.exec("PRAGMA busy_timeout = 0");
		db.exec("BEGIN EXCLUSIVE");
		return db;
	} catch (error) {
		db.close();
		throw error;
	}
}

export async function takeLock(file, { waitSeconds = 0 } = {}) {
	const path = `${file}.lock`;
	if (held.has(path)) return;
	const deadline = Date.now() + waitSeconds * 1000;
	for (;;) {
		try {
			held.set(path, tryLock(path));
			return;
		} catch (error) {
			if (Date.now() >= deadline) throw new HostLocked(file, error);
			await new Promise((done) => setTimeout(done, 500));
		}
	}
}

export function releaseLock(file) {
	const path = `${file}.lock`;
	const db = held.get(path);
	if (!db) return;
	held.delete(path);
	try {
		db.exec("ROLLBACK");
	} catch {}
	db.close();
}
