const { existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } = require("node:fs");
const { homedir } = require("node:os");
const { dirname, join } = require("node:path");
const { spawnSync } = require("node:child_process");

const emit = (event) => process.stdout.write(`${JSON.stringify(event)}\n`);

function installed(dir) {
	const file = join(dir, ".version");
	return existsSync(file) && readFileSync(file, "utf8").trim() === BUNDLE.version;
}

function settle(staging, dir) {
	for (let tries = 0; ; tries += 1) {
		try {
			renameSync(staging, dir);
			return true;
		} catch (error) {
			if (installed(dir)) {
				rmSync(staging, { recursive: true, force: true });
				return false;
			}
			if (tries >= 10) throw error;
			Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500);
		}
	}
}

try {
	const [major, minor] = process.versions.node.split(".").map(Number);
	if (major < 22 || (major === 22 && minor < 19)) throw new Error(`node ${process.versions.node} is below 22.19, which the durable host needs`);
	const base = process.env.OHFLOW_DURABLE_HOST_HOME || join(homedir(), ".pi-durable", "ohflow-host");
	const dir = join(base, BUNDLE.version);
	if (installed(dir)) {
		emit({ type: "durable_host", dir, version: BUNDLE.version, installed: false, node: process.versions.node });
		process.exit(0);
	}
	const staging = `${dir}.part-${process.pid}`;
	rmSync(staging, { recursive: true, force: true });
	for (const [path, data] of Object.entries(BUNDLE.files)) {
		const target = join(staging, path);
		mkdirSync(dirname(target), { recursive: true });
		writeFileSync(target, Buffer.from(data, "base64"));
	}
	const npm = spawnSync("npm", ["ci", "--omit=dev", "--no-audit", "--no-fund"], { cwd: staging, stdio: ["ignore", 2, 2], shell: true, windowsHide: true });
	if (npm.status !== 0) {
		rmSync(staging, { recursive: true, force: true });
		throw new Error(`npm ci for the durable host exited ${npm.status ?? npm.error?.message}`);
	}
	writeFileSync(join(staging, ".version"), `${BUNDLE.version}\n`);
	const fresh = settle(staging, dir);
	emit({ type: "durable_host", dir, version: BUNDLE.version, installed: fresh, node: process.versions.node });
} catch (error) {
	emit({ type: "durable_error", name: error?.name, message: String(error?.message ?? error) });
	process.exit(1);
}
