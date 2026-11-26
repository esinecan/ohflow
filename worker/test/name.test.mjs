import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";
import {
	codemodeName,
	DEFAULT_NAME,
	deployedUrl,
	LOCAL_FILE,
	loadSettings,
	readConfigs,
	recordUrl,
	settingsFile,
	WORKER_DIR,
	workerConfigs,
	workerName,
	workerUrl,
} from "../scripts/settings.mjs";

const NOWHERE = join(WORKER_DIR, "test", "no-such-file");
const shipped = () => loadSettings({ local: NOWHERE, rules: NOWHERE });

function withoutUrlEnv(fn) {
	const saved = process.env.PI_CLOUD_URL;
	delete process.env.PI_CLOUD_URL;
	try {
		return fn();
	} finally {
		if (saved !== undefined) process.env.PI_CLOUD_URL = saved;
	}
}

function scratch() {
	return mkdtempSync(join(tmpdir(), "pi-cloud-name-test-"));
}

test("the shipped settings name the Worker pi-cloud", () => {
	assert.equal(DEFAULT_NAME, "pi-cloud");
	assert.equal(workerName(shipped()), "pi-cloud");
	assert.equal(workerName({}), "pi-cloud");
});

test("the default name derives the checked-in configs unchanged", () => {
	const base = readConfigs();
	assert.equal(base.worker.name, "pi-cloud");
	assert.equal(base.sandbox.name, "pi-cloud-codemode");
	assert.deepEqual(workerConfigs(DEFAULT_NAME), base);
});

test("another name renames both Workers and the code mode binding", () => {
	const base = readConfigs();
	const { worker, sandbox } = workerConfigs("ohflow-newcomer-test");
	assert.equal(worker.name, "ohflow-newcomer-test");
	assert.equal(sandbox.name, "ohflow-newcomer-test-codemode");
	assert.equal(codemodeName("ohflow-newcomer-test"), "ohflow-newcomer-test-codemode");
	const binding = worker.durable_objects.bindings.find((entry) => entry.name === "CODEMODE_SANDBOX");
	assert.deepEqual(binding, { name: "CODEMODE_SANDBOX", class_name: "CodemodeSandbox", script_name: "ohflow-newcomer-test-codemode" });
	const others = (bindings) => bindings.filter((entry) => entry.name !== "CODEMODE_SANDBOX");
	assert.deepEqual(others(worker.durable_objects.bindings), others(base.worker.durable_objects.bindings));
	assert.deepEqual(worker.migrations, base.worker.migrations);
	assert.deepEqual(worker.containers, base.worker.containers);
	assert.deepEqual(sandbox.durable_objects, base.sandbox.durable_objects);
	assert.deepEqual(sandbox.migrations, base.sandbox.migrations);
	assert.deepEqual({ ...worker, name: base.worker.name, durable_objects: base.worker.durable_objects }, base.worker);
	assert.deepEqual(readConfigs(), base);
});

test("a name that is not a Worker name is refused", () => {
	for (const name of ["Pi-Cloud", "pi_cloud", "-pi", "pi-", "", "a".repeat(55), 7]) {
		assert.throws(() => workerName({ name }), /not a Worker name/, String(name));
	}
	assert.equal(workerName({ name: "a".repeat(54) }), "a".repeat(54));
});

test("the deploy output gives the address of that name only", () => {
	const output = "Deployed ohflow-newcomer-test-codemode\nUploaded ohflow-newcomer-test\n  https://ohflow-newcomer-test.example.workers.dev\n";
	assert.equal(deployedUrl(output, "ohflow-newcomer-test"), "https://ohflow-newcomer-test.example.workers.dev");
	assert.equal(deployedUrl(output, "pi-cloud"), null);
	assert.equal(deployedUrl("  https://pi-cloudy.example.workers.dev", "pi-cloud"), null);
});

test("the URL is PI_CLOUD_URL, then url, then the address recorded for the name", () => {
	const dir = scratch();
	try {
		const recorded = join(dir, "urls.json");
		recordUrl("pi-cloud", "https://pi-cloud.example.workers.dev", recorded);
		recordUrl("ohflow-newcomer-test", "https://ohflow-newcomer-test.example.workers.dev/", recorded);
		withoutUrlEnv(() => {
			assert.equal(workerUrl({ name: "ohflow-newcomer-test" }, { recorded }), "https://ohflow-newcomer-test.example.workers.dev");
			assert.equal(workerUrl({}, { recorded }), "https://pi-cloud.example.workers.dev");
			assert.equal(workerUrl({ name: "ohflow-newcomer-test", url: "https://x.example/" }, { recorded }), "https://x.example");
			assert.throws(() => workerUrl({ name: "unknown" }, { recorded }), /no URL for the Worker unknown/);
			process.env.PI_CLOUD_URL = "https://env.example";
			try {
				assert.equal(workerUrl({ name: "ohflow-newcomer-test", url: "https://x.example" }, { recorded }), "https://env.example");
			} finally {
				delete process.env.PI_CLOUD_URL;
			}
		});
	} finally {
		rmSync(dir, { recursive: true, force: true });
	}
});

test("--settings names the Worker settings file", () => {
	assert.equal(settingsFile(["node", "deploy.mjs"]), LOCAL_FILE);
	assert.throws(() => settingsFile(["node", "deploy.mjs", "--settings"]), /needs a settings file/);
	assert.throws(() => settingsFile(["node", "deploy.mjs", "--settings", "--dry-run"]), /needs a settings file/);
	assert.throws(() => settingsFile(["node", "deploy.mjs", "--settings", NOWHERE]), /no settings file/);
	const dir = scratch();
	try {
		const file = join(dir, "settings.json");
		writeFileSync(file, JSON.stringify({ name: "ohflow-newcomer-test", account_id: "0123" }));
		assert.equal(settingsFile(["node", "snapshot.mjs", "build", "--settings", file]), resolve(file));
		const settings = loadSettings({ local: file, rules: NOWHERE });
		assert.equal(workerName(settings), "ohflow-newcomer-test");
		assert.equal(settings.account_id, "0123");
		assert.deepEqual(settings.snapshot, shipped().snapshot);
	} finally {
		rmSync(dir, { recursive: true, force: true });
	}
});
