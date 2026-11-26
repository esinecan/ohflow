import { DurableObject } from "cloudflare:workers";
import AGENTS from "../snapshot/AGENTS.md";
import CHROMIUM from "../snapshot/box-chromium.sh";
import VERSIONS from "../snapshot/box-versions.sh";
import GATEWAY from "../snapshot/box/mcp-gateway.mjs";
import BOOT from "../snapshot/box/harness-boot.mjs";
import BOX_SKILLS from "../snapshot/box/box-skills.mjs";
import SERVERS from "../snapshot/box/mcp-servers.json";
import { AGENT_USER, BASE_IMAGE, BOX_PATH, boxFiles, gitIdentity, newestSnapshot, recipe, recipeKey } from "../snapshot/recipe.mjs";

const OPERATOR = typeof PI_CLOUD_OPERATOR === "undefined" ? {} : PI_CLOUD_OPERATOR;
const FILES = boxFiles({ agents: AGENTS, versions: VERSIONS, chromium: CHROMIUM, gateway: GATEWAY, servers: SERVERS, boot: BOOT, skills: BOX_SKILLS }, OPERATOR);
export const BOX_AGENTS = FILES.agents;
export const BOX_MCP = JSON.parse(FILES.servers);
export const BOX_ENV = { PATH: BOX_PATH, HOME: "/root" };
export const BOX_GIT_IDENTITY = gitIdentity(OPERATOR.git_identity);
export const SNAPSHOT_OBJECT = "default";
const STEPS = recipe(FILES, OPERATOR.snapshot, BOX_GIT_IDENTITY);
const NEEDS_TOKEN = STEPS.some((step) => step.secret);
const STEP_TIMEOUT_MS = 20 * 60_000;
const BEAT_MS = 15_000;
const BUILD_INSTANCE = "standard-3";
const CHECK_INSTANCE = "standard-1";
const IDLE = ["sleep", "infinity"];

let keyPromise;
export function boxKey() {
	keyPromise ??= recipeKey(STEPS);
	return keyPromise;
}

async function run(container, command, { env = {}, stdin, user, timeoutMs = STEP_TIMEOUT_MS } = {}) {
	const agent = user === "agent";
	const process = await container.exec([...command], {
		env: { ...BOX_ENV, DEBIAN_FRONTEND: "noninteractive", ...(agent ? { HOME: "/home/agent" } : {}), ...env },
		stderr: "combined",
		...(agent ? { user: AGENT_USER, cwd: "/home/agent" } : {}),
		...(stdin === undefined ? {} : { stdin: new Blob([stdin]).stream() }),
	});
	const timer = setTimeout(() => process.kill(9), timeoutMs);
	try {
		const output = await process.output();
		return { exitCode: output.exitCode, text: new TextDecoder().decode(output.stdout) };
	} finally {
		clearTimeout(timer);
	}
}

async function ready(container) {
	const deadline = Date.now() + 120_000;
	for (;;) {
		try {
			if ((await run(container, ["true"], { timeoutMs: 10_000 })).exitCode === 0) return;
		} catch (error) {
			if (Date.now() > deadline) throw error;
		}
		await new Promise((resolve) => setTimeout(resolve, 1000));
	}
}

function tail(text, lines = 20) {
	return text.trim().split("\n").slice(-lines).join("\n");
}

export class SnapshotBuilder extends DurableObject {
	async built() {
		const key = await boxKey();
		return { key, image: BASE_IMAGE, record: (await this.ctx.storage.get(`snapshot:${key}`)) ?? null };
	}

	async current() {
		const own = await this.built();
		if (own.record) return { ...own, built: true };
		const stored = await this.ctx.storage.list({ prefix: "snapshot:" });
		return { ...own, built: false, record: newestSnapshot(stored) };
	}

	async mcpTools(key) {
		return (await this.ctx.storage.get(`mcp-tools:${key}`)) ?? null;
	}

	async keepMcpTools(key, servers) {
		await this.ctx.storage.put(`mcp-tools:${key}`, servers);
	}

	async fresh(options) {
		const container = this.ctx.container;
		if (container.running) await container.destroy().catch(() => {});
		container.start(options);
		await ready(container);
		return container;
	}

	build(token, force) {
		const encoder = new TextEncoder();
		const { readable, writable } = new TransformStream();
		const out = writable.getWriter();
		const line = (event) => out.write(encoder.encode(`${JSON.stringify({ ...event, t: Date.now() })}\n`)).catch(() => {});
		const work = async () => {
			const beat = setInterval(() => line({ type: "beat" }), BEAT_MS);
			const container = this.ctx.container;
			try {
				const key = await boxKey();
				const stored = await this.ctx.storage.get(`snapshot:${key}`);
				if (stored && !force) {
					line({ type: "snapshot", reused: true, ...stored });
					return;
				}
				if (NEEDS_TOKEN && (typeof token !== "string" || !token)) throw new Error("token is required: the recipe clones private repos with the setup-only GitHub token");
				const started = Date.now();
				line({ type: "build_start", key, image: BASE_IMAGE, steps: STEPS.length });
				await this.fresh({ image: BASE_IMAGE, enableInternet: true, instance: BUILD_INSTANCE, entrypoint: IDLE });
				for (const [index, step] of STEPS.entries()) {
					line({ type: "step_start", index, name: step.name });
					const stepStarted = Date.now();
					const result = await run(container, step.command, {
						stdin: step.stdin,
						user: step.user,
						env: step.secret ? { GH_SETUP_TOKEN: token } : {},
					});
					const seconds = Math.round((Date.now() - stepStarted) / 1000);
					line({ type: "step_end", index, name: step.name, exitCode: result.exitCode, seconds });
					if (result.exitCode !== 0) throw new Error(`${step.name} exited with ${result.exitCode}:\n${tail(result.text)}`);
				}
				const snapshot = await container.snapshotContainer({ name: `box-${key}` });
				const record = { key, id: snapshot.id, size: snapshot.size, builtAt: new Date().toISOString(), seconds: Math.round((Date.now() - started) / 1000) };
				await this.ctx.storage.put(`snapshot:${key}`, record);
				line({ type: "snapshot", reused: false, ...record });
			} catch (error) {
				line({ type: "build_error", message: String(error?.message ?? error) });
			} finally {
				clearInterval(beat);
				if (container.running) await container.destroy().catch(() => {});
				await out.close().catch(() => {});
			}
		};
		work().catch(() => {});
		return readable;
	}

	async verify(token) {
		const { key, record } = await this.built();
		if (!record) return { status: 404, error: `the default snapshot ${key} is not built` };
		if (NEEDS_TOKEN && (typeof token !== "string" || !token)) return { status: 400, error: "token is required: the setup-only GitHub token the build used" };
		const container = await this.fresh({ containerSnapshot: { id: record.id }, enableInternet: false, instance: CHECK_INSTANCE, entrypoint: IDLE });
		try {
			const grep = await run(
				container,
				[
					"bash",
					"-c",
					'if [ -n "$T" ]; then basic=$(printf "x-access-token:%s" "$T" | base64 -w0); grep -rlsF --exclude-dir=proc --exclude-dir=sys --exclude-dir=dev --exclude-dir=run -e "$T" -e "$basic" /; echo "grep_exit=$?"; else echo "no token given"; fi; test ! -e /root/.git-credentials -a ! -e /home/agent/.git-credentials && echo "no .git-credentials"; git config --system --get-regexp "credential|extraheader"; git config --global --get-regexp "credential|extraheader"; for d in /opt/agent-skills /opt/mcp/*; do test -d "$d/.git" && git -C "$d" config --local --get-regexp "credential|extraheader|url"; done',
				],
				{ env: { T: typeof token === "string" ? token : "" } },
			);
			const versions = await run(container, ["box-versions"]);
			const chromium = await run(container, ["box-chromium", "/tmp/box-chromium.png"], { timeoutMs: 120_000 });
			const offline = await run(container, ["bash", "-c", "curl -sS -m 5 https://github.com >/dev/null && echo online || echo offline"]);
			const identityCommand = ["bash", "-euc", 'd=$(mktemp -d); trap \'rm -rf "$d"\' EXIT; git -C "$d" init -q; git -C "$d" -c commit.gpgsign=false commit -q --allow-empty -m "Check box identity"; git -C "$d" show -s --format="%an <%ae>|%cn <%ce>"'];
			const rootIdentity = await run(container, identityCommand);
			const agentIdentity = await run(container, identityCommand, { user: "agent" });
			return { key, snapshot: record.id, grep: grep.text.trim(), versions: { exitCode: versions.exitCode, text: versions.text.trim() }, chromium: { exitCode: chromium.exitCode, text: chromium.text.trim() }, network: offline.text.trim(), git_identity: { expected: BOX_GIT_IDENTITY, root: rootIdentity, agent: agentIdentity } };
		} finally {
			await container.destroy().catch(() => {});
		}
	}
}
