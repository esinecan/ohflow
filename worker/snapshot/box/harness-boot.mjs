import { spawn, spawnSync } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync, openSync, rmSync, writeFileSync } from "node:fs";

const PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin";
const CA_FILE = "/etc/cloudflare/certs/cloudflare-containers-ca.crt";
const AGENT = { uid: 10001, gid: 10001 };
const AGENT_ENV = { PATH, HOME: "/home/agent" };
const REPO = "/workspace/repo";
const OUT = "/workspace/out";
const LOG = "/tmp/box-boot.log";
const SKILLS_ERROR = `${OUT}/.box-skills-error`;
const SKILLS_TRIES = 2;

function log(line) {
	try {
		appendFileSync(LOG, `${new Date().toISOString()} ${line}\n`);
	} catch {}
}

function startGateway() {
	mkdirSync("/tmp/mcp-gateway", { recursive: true });
	const out = openSync("/tmp/mcp-gateway/gateway.log", "a");
	const child = spawn("node", ["/usr/local/lib/box/mcp-gateway.mjs"], {
		env: { PATH, HOME: "/root", NODE_EXTRA_CA_CERTS: CA_FILE },
		detached: true,
		stdio: ["ignore", out, out],
	});
	child.on("error", (error) => log(`gateway did not start: ${error.message}`));
	child.unref();
	log(`gateway started, pid ${child.pid}`);
}

function asAgent(args, cwd = "/workspace") {
	const run = spawnSync(args[0], args.slice(1), { ...AGENT, cwd, env: AGENT_ENV, encoding: "utf8", timeout: 300_000 });
	if (run.status !== 0) throw new Error(`${args.join(" ")} exited ${run.status ?? run.signal}: ${(run.stderr || run.stdout || "").trim().slice(-800)}`);
	return run.stdout.trim();
}

function prepareRepo() {
	const { OHFLOW_REPO_URL: url, OHFLOW_BRANCH: branch, OHFLOW_START_SHA: sha } = process.env;
	if (!url || !branch || !sha) return;
	if (existsSync(`${REPO}/.git`)) {
		log("repo present");
		return;
	}
	try {
		asAgent(["mkdir", "-p", OUT]);
		asAgent(["git", "clone", "--quiet", "--branch", branch, "--single-branch", "--depth", "50", url, REPO]);
		const head = asAgent(["git", "-C", REPO, "rev-parse", "HEAD"]);
		if (head !== sha) throw new Error(`the clone of ${branch} is at ${head}, not at the start commit ${sha}`);
		log(`cloned ${branch} at ${head}`);
	} catch (error) {
		log(`clone failed: ${error.message}`);
		try {
			mkdirSync(OUT, { recursive: true });
			writeFileSync(`${OUT}/.box-clone-error`, `${error.message}\n`);
		} catch {}
	}
}

async function prepareSkills() {
	const url = process.env.OHFLOW_SKILLS_URL;
	if (!url) return;
	let failure;
	for (let attempt = 1; attempt <= SKILLS_TRIES; attempt += 1) {
		try {
			const { fetchSkills } = await import("./box-skills.mjs");
			const got = await fetchSkills({ url });
			rmSync(SKILLS_ERROR, { force: true });
			log(`skills ${got.names.join(",")} at ${got.sha}: ${got.present ? "present" : `${got.files} files`}`);
			return;
		} catch (error) {
			failure = error;
			log(`skills fetch ${attempt} failed: ${error.message}`);
			await new Promise((resolve) => setTimeout(resolve, 2000));
		}
	}
	try {
		mkdirSync(OUT, { recursive: true });
		writeFileSync(SKILLS_ERROR, `${failure.message}\n`);
	} catch {}
}

startGateway();
prepareRepo();
await prepareSkills();
await import("/opt/harness/harness-daemon.mjs");
