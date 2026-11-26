import { DurableObject } from "cloudflare:workers";
import { Workspace, WorkspaceProxy } from "@cloudflare/computer";
import { ContainerBackend, withWorkspaceContainer } from "@cloudflare/computer/backends/container";
import { createGitClient } from "@cloudflare/computer/git";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { createModels } from "@earendil-works/pi-ai/models";
import { deepseekProvider } from "@earendil-works/pi-ai/providers/deepseek";
import { zaiProvider } from "@earendil-works/pi-ai/providers/zai";
import { ZAI_MODELS } from "@earendil-works/pi-ai/providers/zai.models";
import { createRegistry, Harness } from "@earendil-works/pi-durable";
import { PiHarness, ROOT_SESSION, skills } from "agents/harness/pi";
import { Lifecycle } from "agents/lifecycle";
import { createAI } from "agents/models/pi-ai";
import { workspace as skillsWorkspace } from "agents/skills";
import { entrySummary, PiEventWriter } from "../../host/src/pi-events.mjs";
import { BOX_SUMMARY, boxEgress, codemodeFactory, createMcpExtensions, GATEWAY_PORT, gatewayCall, GatewayLost, listGatewayTools, mcpToolNames, secretNeedles, selectTools } from "./mcp.mjs";
import { CliAgent, CliEgress, CodexLogin } from "./cli.mjs";
import { boxLastLook } from "./last-look.mjs";
import { iterationLimit } from "./limits.mjs";
import { BOX_ENV, BOX_GIT_IDENTITY, SNAPSHOT_OBJECT, SnapshotBuilder } from "./snapshot.mjs";
import { pinSkills, SKILLS_ROOT, SkillsMirror, skillsMirror, skillsMount } from "./skills.mjs";
import {
	allowedRepo,
	BOX_SECTION,
	BRANCH,
	createGitTools,
	createWorkspaceTools,
	exists,
	githubAuth,
	OUT_DIR,
	REPO_DIR,
	WORKSPACE_SECTION,
} from "./workspace.mjs";

export { CliAgent, CliEgress, CodexLogin, SkillsMirror, SnapshotBuilder, WorkspaceProxy };

const WAIT_MS = 25_000;
const BEAT_MS = 15_000;
const STEP_KEY = "ohflow.step";
const SKILLS_KEY = "ohflow.skills";
const METER_KEY = "ohflow.container";
const STEP_INSTANCE = "standard-1";
const THINKING = new Set(["off", "minimal", "low", "medium", "high", "xhigh", "max"]);
const COMPUTERD = ["/usr/local/bin/computerd"];
const GATEWAY_START =
	"mkdir -p /tmp/mcp-gateway && setsid node /usr/local/lib/box/mcp-gateway.mjs >>/tmp/mcp-gateway/gateway.log 2>&1 </dev/null & echo started";
const BOX_PROBE =
	"ps -eo pid,ppid,args | head -40; echo ---; ls -l /etc/cloudflare/certs 2>&1; echo ---; tail -20 /tmp/mcp-gateway/*.log 2>&1; echo ---; (ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null) | head";
const CA_FILE = "/etc/cloudflare/certs/cloudflare-containers-ca.crt";
const GATEWAY_WAIT_MS = 30_000;
const CONNECT_MS = 120_000;
const SNAPSHOT_ROUTE = /^\/snapshot(?:\/(build|verify))?$/;
const SKILLS_ROUTE = /^\/skills(?:\/(sync))?$/;
const ROUTE = /^\/attempts\/([^/]+)\/(submit|wait|messages|pending|step|events|abort|transcript|crash|stop-container|files|secret-scan|probe)$/;
const CLI_ROUTE = /^\/(claude|codex|echo)\/attempts\/([^/]+)\/(step|events|abort|transcript|stop-container|probe|out\/[A-Za-z0-9._-]+)$/;
const OUT_ROUTE =/^\/attempts\/([^/]+)\/out\/([A-Za-z0-9._-]+)$/;
const TEST_ACTIONS = new Set(["crash", "stop-container", "files", "secret-scan", "probe"]);
const SECRET_SCAN =
	"grep -rlsF -f - --exclude-dir=proc --exclude-dir=sys --exclude-dir=dev --exclude-dir=run / /proc/[0-9]*/environ /proc/[0-9]*/cmdline; echo grep_exit=$?";

function sleep(ms) {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

function stringList(value) {
	return value === undefined || (Array.isArray(value) && value.every((item) => typeof item === "string"));
}

function stepModels() {
	const models = createModels();
	models.setProvider(zaiProvider());
	models.setProvider(deepseekProvider());
	return models;
}

function parseModel(name) {
	const match = /^([^/\s]+)\/([^/\s]+)$/.exec(String(name ?? ""));
	if (!match || !stepModels().getModel(match[1], match[2])) return null;
	return { provider: match[1], modelId: match[2] };
}

function fault(status, error) {
	return { status, error };
}

export class StepAgent extends withWorkspaceContainer(class extends DurableObject {}) {
	launch = { entrypoint: COMPUTERD };

	backend = new ContainerBackend({
		container: () => this,
		workspace: { binding: "STEP", id: this.ctx.id.toString() },
		egress: { mode: "http-gateway", gateway: { fetch: (request) => boxEgress(this.env, request) } },
		instance: STEP_INSTANCE,
		connectTimeoutMs: CONNECT_MS,
		containerEnv: { ...BOX_ENV, FUSE_MOUNT: "auto", NODE_EXTRA_CA_CERTS: CA_FILE },
		launch: this.launch,
	});

	workspace = new Workspace({
		storage: this.ctx.storage,
		backends: [this.backend],
		mounts: { [SKILLS_ROOT]: skillsMount({ mirror: () => skillsMirror(this.env.SKILLS_MIRROR), pin: async () => (await this.ctx.storage.get(SKILLS_KEY)) ?? { sha: null, names: [] } }) },
		git: createGitClient(),
		defaultGitIdentity: BOX_GIT_IDENTITY,
	});

	ai = createAI({ binding: this.env.AI });
	baseToolNames = [];
	toolNames = [];
	mcpServers = [];
	registry = this.createToolRegistry();

	harness = new PiHarness({
		harness: async ({ storage, context, onWake }) => {
			await this.installSkills();
			const models = stepModels();
			models.setProvider(this.ai.provider);
			return Harness.open(
				storage,
				{ models, registry: this.registry, onWake, settings: { retry: { maxRetries: 2 } } },
				context,
			);
		},
		defaults: { model: this.defaultModel() },
	});

	lifecycle = Lifecycle.install(this).use(this.harness);

	constructor(ctx, env) {
		super(ctx, env);
		ctx.blockConcurrencyWhile(async () => {
			const step = await ctx.storage.get(STEP_KEY);
			if (step?.snapshot) this.launch.containerSnapshot = { id: step.snapshot.id };
			if (step?.mcp) this.installMcp(step.mcp.selected);
		});
	}

	getWorkspaceContainer() {
		const host = super.getWorkspaceContainer();
		for (const name of ["start", "restart"]) {
			const call = host[name].bind(host);
			host[name] = async (spec) => {
				const prior = await host.exitInfo();
				const runtime = await call(spec);
				if (runtime.outcome !== "adopted") await this.meterLaunch(prior?.exitedAt);
				return runtime;
			};
		}
		return host;
	}

	async meterLaunch(priorExitAt) {
		const now = Date.now();
		const meter = (await this.ctx.storage.get(METER_KEY)) ?? { instance: STEP_INSTANCE, seconds: 0, launches: 0, open_since: null };
		if (meter.open_since) meter.seconds += Math.max(0, ((priorExitAt ?? now) - meter.open_since) / 1000);
		meter.open_since = now;
		meter.launches += 1;
		await this.ctx.storage.put(METER_KEY, meter);
	}

	async stopBox() {
		const running = Boolean(this.ctx.container?.running);
		if (running) await this.ctx.container.destroy().catch(() => {});
		const meter = (await this.ctx.storage.get(METER_KEY)) ?? { instance: STEP_INSTANCE, seconds: 0, launches: 0, open_since: null };
		if (meter.open_since) {
			const exit = running ? null : await super.getWorkspaceContainer().exitInfo();
			meter.seconds += Math.max(0, ((exit?.exitedAt ?? Date.now()) - meter.open_since) / 1000);
			meter.open_since = null;
			await this.ctx.storage.put(METER_KEY, meter);
		}
		return {
			durable_object_id: this.ctx.id.toString(),
			instance: meter.instance,
			seconds: Math.round(meter.seconds * 10) / 10,
			launches: meter.launches,
			stopped: running,
		};
	}

	async installSkills() {
		if (this.skillsInstalled) return;
		this.skillsInstalled = true;
		try {
			await this.workspace.ready();
			this.registry.install(await skills([skillsWorkspace(this.workspace)]));
		} catch (error) {
			console.error(JSON.stringify({ ev: "skills_install_error", message: String(error?.message ?? error) }));
		}
	}

	async pinSkills(names) {
		const pin = await pinSkills(() => skillsMirror(this.env.SKILLS_MIRROR), names);
		if (pin.error) return pin;
		await this.ctx.storage.put(SKILLS_KEY, pin);
		return pin.sha ? pin : { names: [] };
	}

	createToolRegistry() {
		const registry = createRegistry();
		const tools = [...createWorkspaceTools(this.workspace), ...createGitTools(this.workspace, this.env)];
		this.baseToolNames = tools.map((tool) => tool.name);
		this.toolNames = [...this.baseToolNames];
		registry.install({ name: "workspace", sections: [WORKSPACE_SECTION, BOX_SECTION], tools });
		return registry;
	}

	installMcp(selected) {
		if (Object.keys(selected).length === 0) return;
		const extensions = createMcpExtensions({
			selected,
			call: gatewayCall(
				(path, body, signal) => this.gatewayPost(path, body, signal),
				async () => !this.ctx.container?.running,
			),
			summary: BOX_SUMMARY,
			codemode: codemodeFactory(() => this.env.CODEMODE_SANDBOX.getByName(this.ctx.id.toString())),
			place: "in the box",
		});
		for (const extension of extensions) this.registry.install(extension);
		this.toolNames = [...this.baseToolNames, "codemode", ...mcpToolNames(selected)];
		this.mcpServers = Object.keys(selected);
	}

	async startGateway() {
		const process = await this.ctx.container.exec(["sh", "-c", GATEWAY_START], {
			env: { ...BOX_ENV, NODE_EXTRA_CA_CERTS: CA_FILE },
			stderr: "combined",
		});
		const output = await process.output();
		if (output.exitCode !== 0) throw new Error(`box-mcp-gateway did not start: ${new TextDecoder().decode(output.stdout).trim()}`);
	}

	async gatewayHealth() {
		await this.backend.connect();
		const deadline = Date.now() + GATEWAY_WAIT_MS;
		let started = false;
		for (;;) {
			let failure;
			try {
				const response = await this.ctx.container.getTcpPort(GATEWAY_PORT).fetch("http://box/health");
				if (response.ok) return await response.json();
				failure = `HTTP ${response.status}`;
			} catch (error) {
				failure = String(error?.message ?? error);
			}
			if (!this.ctx.container?.running) throw new GatewayLost("the box container is not running");
			if (!started) {
				started = true;
				this.gatewayStart ??= this.startGateway().finally(() => {
					this.gatewayStart = null;
				});
				await this.gatewayStart;
				continue;
			}
			if (Date.now() > deadline) throw new Error(`box-mcp-gateway did not answer on port ${GATEWAY_PORT} within ${GATEWAY_WAIT_MS / 1000} s: ${failure}`);
			await sleep(500);
		}
	}

	async gatewayPost(path, body, signal) {
		await this.gatewayHealth();
		let response;
		try {
			response = await this.ctx.container.getTcpPort(GATEWAY_PORT).fetch(`http://box${path}`, {
				method: "POST",
				headers: { "content-type": "application/json", accept: "application/json, text/event-stream" },
				body: JSON.stringify(body),
				signal,
			});
		} catch (error) {
			if (signal?.aborted) throw error;
			throw new GatewayLost(`the connection to box-mcp-gateway broke: ${String(error?.message ?? error)}`, { cause: error });
		}
		if (!response.ok) {
			const detail = (await response.text().catch(() => "")).slice(0, 500);
			if (!this.ctx.container?.running) throw new GatewayLost(`box-mcp-gateway answered ${response.status} and the container stopped`);
			throw new Error(`box-mcp-gateway answered ${response.status}: ${detail}`);
		}
		return response.json();
	}

	async mcpFor(boxKey, policy) {
		const builder = this.env.SNAPSHOT.getByName(SNAPSHOT_OBJECT);
		let servers = await builder.mcpTools(boxKey);
		if (!servers) {
			servers = await listGatewayTools(
				() => this.gatewayHealth(),
				(path, body, signal) => this.gatewayPost(path, body, signal),
			);
			if (Object.values(servers).every((entry) => entry.tools)) await builder.keepMcpTools(boxKey, servers);
		}
		const { selected, unmatched } = selectTools(servers, policy);
		const errors = Object.fromEntries(Object.entries(servers).filter(([, entry]) => entry.error).map(([server, entry]) => [server, entry.error]));
		return { selected, unmatched, errors, policy };
	}

	async probe() {
		const container = this.ctx.container;
		if (!container?.running) return { running: false, exit: await super.getWorkspaceContainer().exitInfo() };
		const process = await container.exec(["bash", "-c", BOX_PROBE], { env: BOX_ENV, stderr: "combined" });
		return { running: true, text: new TextDecoder().decode((await process.output()).stdout) };
	}

	async secretScan() {
		const container = this.ctx.container;
		if (!container?.running) return { running: false };
		const results = [];
		for (const needle of secretNeedles(this.env)) {
			for (const [kind, value] of [["placeholder", needle.placeholder], ["real value", needle.value]]) {
				if (!value) {
					results.push({ secret: needle.name, kind, skipped: "no value" });
					continue;
				}
				const process = await container.exec(["bash", "-c", SECRET_SCAN], { env: BOX_ENV, stdin: new Blob([value]).stream(), stderr: "combined" });
				const output = await process.output();
				const lines = new TextDecoder().decode(output.stdout).trim().split("\n").filter(Boolean);
				results.push({ secret: needle.name, kind, hits: lines.filter((line) => !line.startsWith("grep_exit=")), grep: lines.find((line) => line.startsWith("grep_exit=")) ?? null });
			}
		}
		const ps = await container.exec(["bash", "-c", "ps -eo pid,args | grep -E 'mcp-gateway|brave|computerd' | grep -v grep"], { env: BOX_ENV, stderr: "combined" });
		return { running: true, results, processes: new TextDecoder().decode((await ps.output()).stdout).trim() };
	}

	defaultModel() {
		if (this.env.MODEL === "zai") return ZAI_MODELS["glm-5.3-flash"];
		return this.ai("@cf/zai-org/glm-5.3-flash");
	}

	fetch(request) {
		return this.backend.handleFetch(request);
	}

	submit(text, operationId, entry) {
		return this.harness.submit(text, { operationId, ...(entry ? { entry } : {}) });
	}

	async wait(operationId, ms) {
		const signal = AbortSignal.timeout(ms);
		try {
			return await this.harness.wait(operationId, { signal });
		} catch (error) {
			if (signal.aborted) return { operationId, status: "pending" };
			throw error;
		}
	}

	messages() {
		return this.harness.messages();
	}

	pending() {
		return this.harness.pending();
	}

	async step({ operationId, brief, model, thinking, remote_url, branch, start_sha, ohflow, tools, skills: skillNames, max_iterations }) {
		if (typeof operationId !== "string" || !operationId) return fault(400, "operationId is required");
		if (typeof brief !== "string" || !brief) return fault(400, "brief is required");
		const ref = parseModel(model);
		if (!ref) return fault(400, `model must be provider/id of a zai or deepseek model the Worker serves, got ${JSON.stringify(model)}`);
		if (thinking != null && !THINKING.has(thinking)) return fault(400, `thinking must be one of ${[...THINKING].join(", ")}, got ${JSON.stringify(thinking)}`);
		const { repo, error: refused } = await allowedRepo(this.env, remote_url);
		if (refused) return fault(403, refused);
		if (!BRANCH.test(branch ?? "")) return fault(400, `branch must start with ohflow/, got ${JSON.stringify(branch)}`);
		if (!/^[0-9a-f]{40}$/.test(start_sha ?? "")) return fault(400, "start_sha must be a 40-digit commit id");
		if (tools != null && (typeof tools !== "object" || !stringList(tools.allow) || !stringList(tools.block))) {
			return fault(400, "tools must be { allow?: string[], block?: string[] } of server.tool globs");
		}
		if (!stringList(skillNames)) return fault(400, "skills must be a list of skill folder names in the skills repo the Worker mirrors");
		const { limit, error: badLimit } = iterationLimit(max_iterations);
		if (badLimit) return fault(400, badLimit);
		const stored = await this.ctx.storage.get(STEP_KEY);
		if (stored && stored.operationId !== operationId) return fault(409, `this object already runs operation ${stored.operationId}`);
		if (!stored) {
			if (!this.env.GITHUB_TOKEN) return fault(500, "The Worker has no GITHUB_TOKEN.");
			const box = await this.env.SNAPSHOT.getByName(SNAPSHOT_OBJECT).current();
			if (!box.record) return fault(503, `no default snapshot is built, and the current key is ${box.key}; run worker/scripts/snapshot.mjs build`);
			const pinned = await this.pinSkills(skillNames);
			if (pinned.error) return pinned;
			this.launch.containerSnapshot = { id: box.record.id };
			if (!(await exists(this.workspace, `${REPO_DIR}/.git`))) {
				await this.workspace.git.clone({
					url: `https://github.com/${repo}.git`,
					dir: REPO_DIR,
					ref: branch,
					singleBranch: true,
					depth: 50,
					headers: githubAuth(this.env),
				});
			}
			const head = await this.workspace.git.revParse({ dir: REPO_DIR, ref: "HEAD" });
			if (head !== start_sha) return fault(409, `the clone of ${branch} is at ${head}, not at the start commit ${start_sha}`);
			const mcp = await this.mcpFor(box.record.key, { allow: tools?.allow ?? [], block: tools?.block ?? [] });
			if (mcp.unmatched.length) return fault(400, `tools.allow patterns matched no MCP tool in the box: ${mcp.unmatched.join(", ")}`);
			this.installMcp(mcp.selected);
			await this.workspace.fs.mkdir(OUT_DIR, { recursive: true });
			const conversation = await this.harness.conversation(ROOT_SESSION);
			await conversation.configure({ model: ref, ...(thinking ? { thinkingLevel: thinking } : {}), ...(limit ? { maxTurns: limit } : {}) }, BACKGROUND_CONTEXT);
			const snapshot = { key: box.record.key, id: box.record.id };
			await this.ctx.storage.put(STEP_KEY, {
				operationId,
				repo,
				branch,
				start_sha,
				model,
				thinking: thinking ?? null,
				max_iterations: limit,
				snapshot,
				skills: pinned,
				mcp: { selected: mcp.selected, errors: mcp.errors, policy: mcp.policy },
			});
		}
		const current = stored ?? (await this.ctx.storage.get(STEP_KEY));
		const snapshot = current.snapshot?.key ?? null;
		const receipt = await this.harness.submit(brief, {
			operationId,
			entry: { kind: "ohflow.brief", data: { ...(ohflow ?? {}), branch, start_sha } },
		});
		return { ...receipt, reattach: Boolean(stored), model, thinking: thinking ?? null, max_iterations: current.max_iterations ?? null, branch, start_sha, snapshot, skills: current.skills ?? { names: [] }, tools: this.toolNames, mcp_servers: this.mcpServers, mcp_errors: current.mcp?.errors ?? {} };
	}

	async publish(step) {
		const git = this.workspace.git;
		const head = await git.revParse({ dir: REPO_DIR, ref: "HEAD" });
		const dirty = (await git.status({ dir: REPO_DIR }))
			.filter((entry) => entry.index !== " " || entry.worktree !== " ")
			.map((entry) => `${entry.worktree === "?" ? "??" : `${entry.index}${entry.worktree}`} ${entry.path}`);
		const current = await git.currentBranch({ dir: REPO_DIR });
		const pushed = await git.push({
			dir: REPO_DIR,
			remote: "origin",
			ref: current ?? "HEAD",
			remoteRef: `refs/heads/${step.branch}`,
			headers: githubAuth(this.env),
		});
		return { head, dirty, pushed: pushed.ok, ...(pushed.ok ? {} : { push_error: pushed.error ?? JSON.stringify(pushed.refs) }) };
	}

	async events(operationId) {
		const step = await this.ctx.storage.get(STEP_KEY);
		const op = operationId || step?.operationId;
		const encoder = new TextEncoder();
		const { readable, writable } = new TransformStream();
		const out = writable.getWriter();
		const gone = new AbortController();
		out.closed.catch(() => gone.abort());
		const write = (text) => {
			if (!gone.signal.aborted) out.write(encoder.encode(text)).catch(() => gone.abort());
		};
		const line = (event) => write(`${JSON.stringify({ ...event, t: Date.now() })}\n`);
		const run = async () => {
			let stream;
			let beat;
			try {
				if (!step || !op) throw new Error("this object holds no ohflow step; POST step first");
				line({ type: "pi_cloud_start", operationId: op, branch: step.branch, start: step.start_sha, model: step.model, thinking: step.thinking, max_iterations: step.max_iterations ?? null, snapshot: step.snapshot?.key ?? null, skills: step.skills ?? { names: [] }, tools: this.toolNames, mcp_servers: this.mcpServers, durable_object_id: this.ctx.id.toString(), instance: STEP_INSTANCE });
				const writer = new PiEventWriter(write);
				stream = await this.harness.session().watch();
				writer.replay(stream.value.entries);
				writer.running(stream.value.docs?.["pi.live"]?.tools);
				stream.start(async (call) => {
					if (call.kind !== "value") return;
					writer.replay(call.value.entries, {});
					writer.running(call.value.docs?.["pi.live"]?.tools);
				});
				beat = setInterval(() => line({ type: "pi_cloud_beat" }), BEAT_MS);
				const settled = await this.harness.wait(op, { signal: gone.signal });
				await stream.stop().catch(() => {});
				stream = undefined;
				writer.replay(await this.harness.messages(), { late: true });
				const git = await this.publish(step);
				const usage = await (await this.harness.pi()).usage(BACKGROUND_CONTEXT);
				const container = await this.stopBox();
				line({ type: "pi_cloud_end", operationId: op, status: settled.status, reason: settled.reason ?? null, start: step.start_sha, branch: step.branch, ...git, usage, container });
			} catch (error) {
				if (!gone.signal.aborted) line({ type: "pi_cloud_error", name: error?.name, message: String(error?.message ?? error) });
			} finally {
				clearInterval(beat);
				await stream?.stop().catch(() => {});
				await out.close().catch(() => {});
			}
		};
		run().catch(() => {});
		return readable;
	}

	async abort(operationId) {
		const step = await this.ctx.storage.get(STEP_KEY);
		const op = operationId || step?.operationId;
		if (!op) return { aborted: false };
		const last_look = await boxLastLook(this.ctx.container, BOX_ENV);
		const aborted = await this.harness.abort({ operationId: op });
		return { operationId: op, aborted, container: await this.stopBox(), last_look };
	}

	async transcript(name) {
		const step = await this.ctx.storage.get(STEP_KEY);
		const lines = (await this.harness.messages())
			.map((entry) => ({ kind: entry.kind, text: entrySummary(entry) }))
			.filter((entry) => entry.text)
			.map((entry) => `- ${entry.kind}: ${entry.text}`);
		return `# ${name}\n\nOperation: ${step?.operationId ?? "none"}\n\n${lines.join("\n")}\n`;
	}

	async outFile(file) {
		const path = `${OUT_DIR}/${file}`;
		if (!(await exists(this.workspace, path))) return null;
		return this.workspace.fs.readFile(path, "utf8");
	}

	crash() {
		this.ctx.abort("test crash");
	}

	async stopContainer() {
		const container = this.ctx.container;
		if (!container?.running) return { running: false };
		await container.destroy();
		return { running: true, stopped: true };
	}

	async files() {
		return this.workspace.fs.readdir(REPO_DIR);
	}
}

async function authorized(request, token) {
	if (!token) return false;
	const given = new TextEncoder().encode(request.headers.get("authorization") ?? "");
	const expected = new TextEncoder().encode(`Bearer ${token}`);
	return given.byteLength === expected.byteLength && crypto.subtle.timingSafeEqual(given, expected);
}

function answer(result) {
	if (result && typeof result.error === "string" && typeof result.status === "number") {
		return Response.json({ error: result.error }, { status: result.status });
	}
	return Response.json(result);
}

export default {
	async fetch(request, env) {
		if (!(await authorized(request, env.OHFLOW_TOKEN))) return new Response("unauthorized", { status: 401 });
		try {
			return await route(request, env);
		} catch (error) {
			return Response.json({ error: String(error?.message ?? error) }, { status: 500 });
		}
	},
};

async function snapshotRoute(request, env, action) {
	const builder = env.SNAPSHOT.getByName(SNAPSHOT_OBJECT);
	if (!action && request.method === "GET") return Response.json(await builder.current());
	if (!action || request.method !== "POST") return new Response("method not allowed", { status: 405 });
	const body = await request.json().catch(() => ({}));
	if (action === "verify") return answer(await builder.verify(body.token));
	const stream = await builder.build(body.token, body.force === true);
	return new Response(stream, {
		headers: { "content-type": "application/x-ndjson", "cache-control": "no-store", "content-encoding": "identity" },
	});
}

async function skillsRoute(request, env, action) {
	const mirror = skillsMirror(env.SKILLS_MIRROR);
	if (!action && request.method === "GET") return Response.json(await mirror.current());
	if (action === "sync" && request.method === "POST") return Response.json(await mirror.sync());
	return new Response("method not allowed", { status: 405 });
}

async function codexLoginRoute(request, env) {
	const login = env.CODEX_LOGIN.getByName("default");
	if (request.method === "GET") return answer(await login.status());
	if (request.method !== "POST") return new Response("method not allowed", { status: 405 });
	return answer(await login.seed(await request.json().catch(() => null)));
}

async function cliRoute(request, env, kind, id, action) {
	const agent = env.CLI.getByName(`${kind}:${id}`);
	if (action.startsWith("out/")) {
		if (request.method !== "GET") return new Response("method not allowed", { status: 405 });
		const text = await agent.outFile(action.slice(4));
		if (text === null) return new Response("not found", { status: 404 });
		return new Response(text, { headers: { "content-type": "text/plain; charset=utf-8" } });
	}
	if (action === "step" && request.method === "POST") return answer(await agent.step(await request.json()));
	if (action === "events" && request.method === "GET") {
		const stream = await agent.events(new URL(request.url).searchParams.get("operationId") ?? "");
		return new Response(stream, {
			headers: { "content-type": "application/x-ndjson", "cache-control": "no-store", "content-encoding": "identity" },
		});
	}
	if (action === "abort" && request.method === "POST") {
		const body = await request.json().catch(() => ({}));
		return Response.json(await agent.abort(body.operationId ?? ""));
	}
	if (action === "transcript" && request.method === "GET") {
		return new Response(await agent.transcript(`${kind}:${id}`), { headers: { "content-type": "text/markdown; charset=utf-8" } });
	}
	if ((action === "stop-container" || action === "probe") && request.method === "POST" && env.TEST_HOOKS === "on") {
		if (action === "stop-container") return Response.json(await agent.stopContainer());
		const body = await request.json().catch(() => ({}));
		return answer(await agent.probe(String(body.text ?? "hello")));
	}
	return new Response("method not allowed", { status: 405 });
}

async function route(request, env) {
	const url = new URL(request.url);
	const snapshot = url.pathname.match(SNAPSHOT_ROUTE);
	if (snapshot) return snapshotRoute(request, env, snapshot[1]);
	if (url.pathname === "/codex/login") return codexLoginRoute(request, env);
	const skillsPath = url.pathname.match(SKILLS_ROUTE);
	if (skillsPath) return skillsRoute(request, env, skillsPath[1]);
	const cli = url.pathname.match(CLI_ROUTE);
	if (cli) return cliRoute(request, env, cli[1], decodeURIComponent(cli[2]), cli[3]);
	const out = url.pathname.match(OUT_ROUTE);
	if (out && request.method === "GET") {
		const text = await env.STEP.getByName(decodeURIComponent(out[1])).outFile(out[2]);
		if (text === null) return new Response("not found", { status: 404 });
		return new Response(text, { headers: { "content-type": "text/plain; charset=utf-8" } });
	}
	const match = url.pathname.match(ROUTE);
	if (!match) return new Response("not found", { status: 404 });
	const name = decodeURIComponent(match[1]);
	const agent = env.STEP.getByName(name);
	const action = match[2];
	if (action === "submit" && request.method === "POST") {
		const body = await request.json();
		if (typeof body.text !== "string" || typeof body.operationId !== "string") {
			return Response.json({ error: "text and operationId are required" }, { status: 400 });
		}
		return Response.json(await agent.submit(body.text, body.operationId, body.entry));
	}
	if (action === "wait" && request.method === "POST") {
		const body = await request.json();
		const ms = Math.min(Number(body.ms) || WAIT_MS, WAIT_MS);
		return Response.json(await agent.wait(body.operationId, ms));
	}
	if (action === "step" && request.method === "POST") return answer(await agent.step(await request.json()));
	if (action === "events" && request.method === "GET") {
		const stream = await agent.events(url.searchParams.get("operationId") ?? "");
		return new Response(stream, {
			headers: { "content-type": "application/x-ndjson", "cache-control": "no-store", "content-encoding": "identity" },
		});
	}
	if (action === "abort" && request.method === "POST") {
		const body = await request.json().catch(() => ({}));
		return Response.json(await agent.abort(body.operationId ?? ""));
	}
	if (action === "transcript" && request.method === "GET") {
		return new Response(await agent.transcript(name), { headers: { "content-type": "text/markdown; charset=utf-8" } });
	}
	if (action === "messages" && request.method === "GET") return Response.json(await agent.messages());
	if (action === "pending" && request.method === "GET") return Response.json(await agent.pending());
	if (TEST_ACTIONS.has(action) && request.method === "POST" && env.TEST_HOOKS === "on") {
		if (action === "crash") {
			await agent.crash().catch(() => {});
			return Response.json({ crashed: true });
		}
		if (action === "stop-container") return Response.json(await agent.stopContainer());
		if (action === "secret-scan") return Response.json(await agent.secretScan());
		if (action === "probe") return Response.json(await agent.probe());
		return Response.json(await agent.files());
	}
	return new Response("method not allowed", { status: 405 });
}
