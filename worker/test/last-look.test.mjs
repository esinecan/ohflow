import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { boxLastLook, LAST_LOOK, LAST_LOOK_LIMIT, LAST_LOOK_TIMEOUT_MS, lastLook } from "../src/last-look.mjs";

const never = () => new Promise(() => {});

test("the last look runs one sh command and keeps its text with the time it was taken", async () => {
	const calls = [];
	const look = await lastLook(async (command) => {
		calls.push(command);
		return { exitCode: 0, text: "box: up 12.0 s, load 0.50 0.40 0.30, cores 1, first process: computerd" };
	}, () => 1794769303000);
	assert.deepEqual(calls, [["sh", "-c", LAST_LOOK]]);
	assert.equal(look.at, 1794769303000);
	assert.equal(look.took_ms, 0);
	assert.equal(look.exit, 0);
	assert.equal(look.truncated, false);
	assert.match(look.text, /^box: up 12\.0 s/);
});

test("a long listing is cut at the limit and says so", async () => {
	const look = await lastLook(async () => ({ exitCode: 0, text: "x".repeat(LAST_LOOK_LIMIT + 50) }));
	assert.equal(look.text.length, LAST_LOOK_LIMIT);
	assert.equal(look.truncated, true);
});

test("a look that fails is an error record and never throws", async () => {
	const look = await lastLook(async () => {
		throw new Error("the container is gone");
	});
	assert.equal(look.error, "the container is gone");
	assert.equal(look.text, undefined);
});

test("a container that is not running gives no look", async () => {
	assert.equal(await boxLastLook(null, {}), null);
	assert.equal(await boxLastLook({ running: false }, {}), null);
});

test("a running container is asked through exec", async () => {
	const seen = [];
	const container = {
		running: true,
		async exec(command, options) {
			seen.push({ command, options });
			return { kill() {}, output: async () => ({ exitCode: 0, stdout: new TextEncoder().encode("load 0.1\n") }) };
		},
	};
	const look = await boxLastLook(container, { PATH: "/usr/bin" });
	assert.equal(look.text, "load 0.1");
	assert.deepEqual(seen[0].options, { env: { PATH: "/usr/bin" }, stderr: "combined" });
});

test("the whole look is bounded: an exec that never answers ends as an error at the limit", async () => {
	const started = Date.now();
	const look = await boxLastLook({ running: true, exec: never }, {}, 80);
	assert.ok(Date.now() - started < 2000, "the look returned at its limit");
	assert.match(look.error, /did not answer in 80 ms/);
	assert.equal(look.text, undefined);
});

test("a command whose output never settles is killed at the limit, and a kill that throws changes nothing", async () => {
	let kills = 0;
	const container = {
		running: true,
		async exec() {
			return {
				kill() {
					kills += 1;
					throw new Error("no such process");
				},
				output: never,
			};
		},
	};
	const look = await boxLastLook(container, {}, 80);
	assert.match(look.error, /did not answer in 80 ms/);
	assert.equal(kills, 1);
});

test("a process that exec hands over after the limit is killed at once", async () => {
	let kills = 0;
	let hand;
	const container = {
		running: true,
		exec: () =>
			new Promise((resolve) => {
				hand = () => resolve({ kill: () => (kills += 1), output: never });
			}),
	};
	const look = await boxLastLook(container, {}, 50);
	assert.match(look.error, /did not answer/);
	hand();
	await new Promise((resolve) => setTimeout(resolve, 20));
	assert.equal(kills, 1);
});

test("a container whose state cannot be read gives an error record", async () => {
	const container = {
		get running() {
			throw new Error("the container binding is gone");
		},
	};
	const look = await boxLastLook(container, {});
	assert.equal(look.error, "the container binding is gone");
});

test("the limit leaves the abort post of ohflow, which waits 60 s, time to stop the container", () => {
	assert.ok(LAST_LOOK_TIMEOUT_MS <= 15_000);
});

const sh = process.platform === "win32" ? null : "sh";

test("the script is valid sh", { skip: !sh && "no sh on this machine's PATH for node" }, () => {
	const parsed = spawnSync(sh, ["-n", "-c", LAST_LOOK]);
	assert.equal(parsed.status, 0, String(parsed.stderr));
});

test("on Linux the look reads alone: rates since boot and over its own second, the first process, the lookup of the box's own name, and zombies apart from live processes", { skip: process.platform !== "linux" && "the script reads /proc" }, () => {
	const ran = spawnSync(sh, ["-c", LAST_LOOK], { encoding: "utf8" });
	assert.equal(ran.status, 0, ran.stderr);
	assert.match(ran.stdout, /^box: up [\d.]+ s, load .* cores \d+, first process: \S/m);
	assert.match(ran.stdout, /^name lookup of the box's own hostname (answered|gave no answer in 2 s|found no such name); the hosts file names it on \d+ line\(s\)$/m);
	assert.match(ran.stdout, /^machine cpu, since boot: user \d+% system \d+% idle \d+% iowait \d+% steal \d+%$/m);
	assert.match(ran.stdout, /^machine cpu, last 1 s: user \d+% /m);
	assert.match(ran.stdout, /^container cpu limit \(cpu\.max/m);
	assert.match(ran.stdout, /^processes: \d+ live \(\d+ running, \d+ blocked in the kernel\), \d+ zombies, \d+ kernel threads left out$/m);
	assert.match(ran.stdout, /^\s*PID\s+PPID\s+PGID\s+STAT/m);
	assert.ok(ran.stdout.length < LAST_LOOK_LIMIT, "an idle machine's look fits the limit");
});
