import { DurableObject, WorkerEntrypoint } from "cloudflare:workers";
import { ContainerHarness, echoAgent } from "agents/harness/container";
import { Lifecycle } from "agents/lifecycle";
import { CLI_HOSTS, PINS } from "../snapshot/recipe.mjs";
import { boxEgress, EGRESS_HOSTS } from "./mcp.mjs";
import { BOX_ENV, BOX_MCP, SNAPSHOT_OBJECT } from "./snapshot.mjs";
import { boxLastLook } from "./last-look.mjs";
import { iterationLimit } from "./limits.mjs";
import { pinSkills, skillsMirror, skillsResponse, skillsUrl } from "./skills.mjs";
import { allowedRepo, BRANCH, OUT_DIR, pushedRefs, REPO_DIR, refusedPush } from "./workspace.mjs";

const HARNESS_IMAGE = "cloudflare/debian-trixie";
const HARNESS_DAEMON = "d45c6a8182ef9070";
const SEED_KEY = "container-harness:snapshot";
const STEP_KEY = "ohflow.step";
const USAGE_KEY = "ohflow.usage";
const METER_KEY = "ohflow.container";
const END_KEY = "ohflow.end";
const OUT_KEY = "ohflow.out";
const LIMIT_KEY = "ohflow.limit";
const TURN_LIMIT = "turn_limit";
const INSTANCE = "standard-1";
const CA_FILE = "/etc/cloudflare/certs/cloudflare-containers-ca.crt";
const AGENT_USER = "10001:10001";
const AGENT_ENV = { PATH: BOX_ENV.PATH, HOME: "/home/agent" };
const BEAT_MS = 15_000;
const CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann";
const CODEX_REFRESH_URL = "https://auth.openai.com/oauth/token";
const CODEX_REFRESH_BEFORE_MS = 3 * 24 * 3600_000;
const CLAUDE_PLACEHOLDER = "sk-ant-oat01-harness-egress-placeholder";
const DROP_HEADERS = ["host", "authorization", "x-api-key", "cookie", "chatgpt-account-id", "cf-aig-authorization"];
const OUT_LIMIT = 256 * 1024;
const COLLECT_OUT = `const fs = require("fs"); const dir = ${JSON.stringify(OUT_DIR)}; const out = {}; for (const name of fs.existsSync(dir) ? fs.readdirSync(dir) : []) { const path = dir + "/" + name; const stat = fs.statSync(path); if (stat.isFile() && stat.size <= ${OUT_LIMIT}) out[name] = fs.readFileSync(path, "utf8"); } process.stdout.write(JSON.stringify(out));`;
const KINDS = {
	echo: { model: /^$/ },
	claude: { model: /^claude-[\w.-]+$/ },
	codex: { model: /^[\w.-]+$/ },
};

export async function harnessSetupKey(steps) {
	const text = JSON.stringify({
		image: HARNESS_IMAGE,
		steps: steps.map((step) => [step.user ?? "root", ...step.command]),
		daemon: HARNESS_DAEMON,
	});
	const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
	return [...new Uint8Array(digest)].slice(0, 16).map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function cliKind(name) {
	const kind = String(name ?? "").split(":")[0];
	return Object.hasOwn(KINDS, kind) ? kind : null;
}

function npmStep(pkg) {
	return { name: `install ${pkg}`, command: ["npm", "install", "--global", "--no-fund", "--no-audit", pkg] };
}

function route(host, upstream) {
	return { host, upstream, headers: {}, strip: [] };
}

function stringList(value) {
	return value == null || (Array.isArray(value) && value.every((item) => typeof item === "string"));
}

function agentFor(kind) {
	const git = route(CLI_HOSTS.github, "https://github.com");
	const skills = route(CLI_HOSTS.skills, `https://${CLI_HOSTS.skills}`);
	if (kind === "claude") {
		return {
			adapter: "claude-code",
			image: { kind: "managed", setup: [npmStep(`@anthropic-ai/claude-code@${PINS.claude}`)] },
			env: {
				ANTHROPIC_BASE_URL: `http://${CLI_HOSTS.anthropic}`,
				CLAUDE_CODE_OAUTH_TOKEN: CLAUDE_PLACEHOLDER,
				DISABLE_AUTOUPDATER: "1",
				CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
				NODE_EXTRA_CA_CERTS: CA_FILE,
			},
			egress: [route(CLI_HOSTS.anthropic, "https://api.anthropic.com"), git, skills],
		};
	}
	if (kind === "codex") {
		return {
			adapter: "codex",
			image: { kind: "managed", setup: [npmStep(`@openai/codex@${PINS.codex}`)] },
			env: { NODE_EXTRA_CA_CERTS: CA_FILE },
			egress: [route(CLI_HOSTS.chatgpt, "https://chatgpt.com"), git, skills],
		};
	}
	return { ...echoAgent(), env: {}, egress: [git, skills] };
}

function forward(request, upstream, set) {
	const url = new URL(request.url);
	const headers = new Headers(request.headers);
	for (const name of DROP_HEADERS) headers.delete(name);
	for (const [name, value] of Object.entries(set)) headers.set(name, value);
	const body = request.method === "GET" || request.method === "HEAD" ? undefined : request.body;
	return fetch(`${upstream}${url.pathname}${url.search}`, { method: request.method, headers, body, redirect: "manual" });
}

async function githubRequest(env, request) {
	const url = new URL(request.url);
	const match = /^\/([\w.-]+\/[\w.-]+?)(?:\.git)?\/(info\/refs|git-upload-pack|git-receive-pack)$/.exec(url.pathname);
	if (!match) return { error: `pi-cloud egress refuses ${url.pathname}; a step reaches only git's smart HTTP routes` };
	const { error } = await allowedRepo(env, `https://github.com/${match[1]}`);
	if (error) return { error: `pi-cloud egress refuses ${match[1]}: ${error}` };
	if (match[2] !== "git-receive-pack") return { request };
	const body = new Uint8Array(await request.arrayBuffer());
	let commands = body;
	if (/gzip/i.test(request.headers.get("content-encoding") ?? "")) {
		commands = new Uint8Array(await new Response(new Blob([body]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer());
	}
	const { refs, error: broken } = pushedRefs(commands);
	if (broken) return { error: `pi-cloud egress refuses the push: ${broken}` };
	const refused = refusedPush(refs);
	if (refused.length) return { error: `pi-cloud egress refuses a push to ${refused.join(", ")}; a step pushes only branches under ohflow/` };
	return { request: new Request(request, { body }) };
}

export class CliEgress extends WorkerEntrypoint {
	async fetch(request) {
		const url = new URL(request.url);
		const kind = this.ctx.props?.kind;
		if (url.hostname === CLI_HOSTS.anthropic && kind === "claude") {
			if (!this.env.CLAUDE_CODE_OAUTH_TOKEN) return new Response("pi-cloud has no Worker secret CLAUDE_CODE_OAUTH_TOKEN\n", { status: 502 });
			const token = this.env.CLAUDE_CODE_OAUTH_TOKEN.replace(/\s+/g, "");
			const response = await forward(request, "https://api.anthropic.com", { authorization: `Bearer ${token}` });
			if (!response.ok) console.warn(`[cli-egress] anthropic ${request.method} ${url.pathname} answered ${response.status}`);
			return response;
		}
		if (url.hostname === CLI_HOSTS.chatgpt && kind === "codex") {
			const login = await this.env.CODEX_LOGIN.getByName("default").token();
			if (login.error) return new Response(`${login.error}\n`, { status: 502 });
			return forward(request, "https://chatgpt.com", { authorization: `Bearer ${login.access}`, "chatgpt-account-id": login.account });
		}
		if (url.hostname === CLI_HOSTS.github) {
			const checked = await githubRequest(this.env, request);
			if (checked.error) return new Response(`${checked.error}\n`, { status: 403 });
			return forward(checked.request, "https://github.com", { authorization: `Basic ${btoa(`x-access-token:${this.env.GITHUB_TOKEN}`)}` });
		}
		if (url.hostname === CLI_HOSTS.skills) return skillsResponse(() => skillsMirror(this.env.SKILLS_MIRROR), request);
		return boxEgress(this.env, request);
	}
}

function jwtClaims(token) {
	try {
		const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
		return JSON.parse(atob(part + "=".repeat((4 - (part.length % 4)) % 4)));
	} catch {
		return {};
	}
}

export class CodexLogin extends DurableObject {
	refreshing = null;

	async seed(auth) {
		const tokens = auth?.tokens;
		if (!tokens?.access_token || !tokens?.refresh_token || !tokens?.account_id) return { status: 400, error: "auth.json must hold tokens.access_token, tokens.refresh_token and tokens.account_id" };
		await this.ctx.storage.put("login", {
			access: tokens.access_token,
			refresh: tokens.refresh_token,
			id: tokens.id_token ?? null,
			account: tokens.account_id,
			refreshedAt: Date.now(),
		});
		return this.status();
	}

	async status() {
		const login = await this.ctx.storage.get("login");
		if (!login) return { seeded: false };
		const claims = jwtClaims(login.access);
		return { seeded: true, expires_at: claims.exp ? new Date(claims.exp * 1000).toISOString() : null, refreshed_at: new Date(login.refreshedAt).toISOString() };
	}

	async token() {
		let login = await this.ctx.storage.get("login");
		if (!login) return { error: "pi-cloud holds no Codex login; run worker/scripts/codex-login.mjs" };
		const exp = (jwtClaims(login.access).exp ?? 0) * 1000;
		if (exp - Date.now() < CODEX_REFRESH_BEFORE_MS) {
			this.refreshing ??= this.refresh(login).finally(() => {
				this.refreshing = null;
			});
			const refreshed = await this.refreshing;
			if (refreshed.error) return refreshed;
			login = refreshed;
		}
		return { access: login.access, account: login.account };
	}

	async refresh(login) {
		const response = await fetch(CODEX_REFRESH_URL, {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify({ client_id: CODEX_CLIENT_ID, grant_type: "refresh_token", refresh_token: login.refresh, scope: "openid profile email" }),
		});
		if (!response.ok) return { error: `the Codex login refresh answered ${response.status}; run worker/scripts/codex-login.mjs again` };
		const body = await response.json();
		const next = {
			...login,
			access: body.access_token ?? login.access,
			refresh: body.refresh_token ?? login.refresh,
			id: body.id_token ?? login.id,
			refreshedAt: Date.now(),
		};
		await this.ctx.storage.put("login", next);
		return next;
	}
}

function zeroUsage() {
	return { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { total: 0 } };
}

function stringOf(value) {
	if (value === undefined || value === null) return "";
	return typeof value === "string" ? value : JSON.stringify(value);
}

function toolStart(part) {
	return { type: "tool_execution_start", toolCallId: part.toolCallId, toolName: part.toolName, args: part.input && typeof part.input === "object" ? part.input : { input: part.input } };
}

function toolEnd(message, part) {
	return {
		type: "tool_execution_end",
		entryId: `${message.id}:${part.toolCallId}`,
		toolCallId: part.toolCallId,
		toolName: part.toolName,
		isError: part.state === "error",
		result: { content: [{ type: "text", text: stringOf(part.output).slice(0, 4000) }] },
	};
}

function piContent(parts) {
	return parts.flatMap((part) => {
		if (part.type === "text") return [{ type: "text", text: part.text }];
		if (part.type === "reasoning") return [{ type: "thinking", thinking: part.text }];
		if (part.type === "tool") return [{ type: "toolCall", id: part.toolCallId, name: part.toolName, arguments: part.input }];
		return [];
	});
}

function transcriptLines(messages, settled, usage) {
	const assistants = messages.filter((message) => message.role === "assistant");
	const last = assistants.at(-1);
	const lines = [];
	for (const message of assistants) {
		for (const part of message.parts) {
			if (part.type !== "tool") continue;
			lines.push(toolStart(part));
			if (part.state !== "running") lines.push(toolEnd(message, part));
		}
		const content = piContent(message.parts);
		const final = message === last;
		if (final && settled?.text) {
			for (let index = content.length - 1; index >= 0; index -= 1) if (content[index].type === "text") content.splice(index, 1);
			content.push({ type: "text", text: settled.text });
		}
		const tokens = final && usage ? { ...zeroUsage(), input: usage.input, output: usage.output, totalTokens: usage.input + usage.output } : zeroUsage();
		const toolUse = message.parts.some((part) => part.type === "tool") && !final;
		lines.push({
			type: "message_end",
			entryId: message.id,
			message: {
				role: "assistant",
				content,
				usage: tokens,
				stopReason: final && settled?.status === "unanswered" ? "error" : toolUse ? "toolUse" : "stop",
				...(final && settled?.status === "unanswered" ? { errorMessage: settled.reason ?? "unanswered" } : {}),
				timestamp: message.createdAt,
			},
		});
	}
	return lines;
}

export class CliAgent extends DurableObject {
	kind = cliKind(this.ctx.id.name);
	agent = agentFor(this.kind);
	harness = new ContainerHarness({
		container: this.containerHandle(),
		agent: this.agent,
		egress: (init) => this.ctx.exports.CliEgress({ props: { kind: this.kind, routes: init.props.routes } }),
		instance: INSTANCE,
		enableInternet: false,
		idleTimeoutMs: 10 * 60_000,
		startTimeoutMs: 180_000,
		onContainerLost: "fail",
	});
	lifecycle = Lifecycle.install(this).use(this.harness);
	feed = null;
	seen = new Set();

	constructor(ctx, env) {
		super(ctx, env);
		ctx.blockConcurrencyWhile(async () => {
			const step = await ctx.storage.get(STEP_KEY);
			if (step) this.applyStep(step);
		});
	}

	containerHandle() {
		const real = this.ctx.container;
		return new Proxy(real, {
			get: (target, prop) => {
				if (prop === "start") {
					return (options) => {
						const started = target.start(options);
						this.ctx.waitUntil(this.onLaunch(target));
						return started;
					};
				}
				const value = Reflect.get(target, prop, target);
				return typeof value === "function" ? value.bind(target) : value;
			},
		});
	}

	async onLaunch(container) {
		const meter = (await this.ctx.storage.get(METER_KEY)) ?? { instance: INSTANCE, seconds: 0, launches: 0, open_since: null };
		const now = Date.now();
		if (meter.open_since) meter.seconds += (now - meter.open_since) / 1000;
		meter.open_since = now;
		meter.launches += 1;
		await this.ctx.storage.put(METER_KEY, meter);
		const egress = this.ctx.exports.CliEgress({ props: { kind: this.kind } });
		for (const host of EGRESS_HOSTS) {
			await container.interceptOutboundHttps(host, egress).catch((error) => console.warn(`[cli] HTTPS intercept of ${host} failed: ${error?.message ?? error}`));
		}
	}

	async closeMeter(stop) {
		const container = this.ctx.container;
		const running = Boolean(container?.running);
		if (stop && running) await container.destroy().catch(() => {});
		const meter = (await this.ctx.storage.get(METER_KEY)) ?? { instance: INSTANCE, seconds: 0, launches: 0, open_since: null };
		if (meter.open_since && (stop || !running)) {
			meter.seconds += Math.max(0, (Date.now() - meter.open_since) / 1000);
			meter.open_since = null;
			await this.ctx.storage.put(METER_KEY, meter);
		}
		return { durable_object_id: this.ctx.id.toString(), instance: meter.instance, seconds: Math.round(meter.seconds * 10) / 10, launches: meter.launches, stopped: stop && running };
	}

	applyStep(step) {
		Object.assign(this.agent.env, {
			OHFLOW_REPO_URL: `http://${CLI_HOSTS.github}/${step.repo}.git`,
			OHFLOW_BRANCH: step.branch,
			OHFLOW_START_SHA: step.start_sha,
		});
		if (step.skills?.sha) this.agent.env.OHFLOW_SKILLS_URL = skillsUrl(CLI_HOSTS.skills, step.skills);
		if (step.model) this.agent.model = step.model;
		if (this.kind === "claude" && step.max_iterations) this.agent.options = { ...(this.agent.options ?? {}), maxTurns: step.max_iterations };
		this.limit = step.max_iterations ?? null;
		this.operationId = step.operationId;
	}

	async countToolCall(toolCallId) {
		if (this.kind !== "codex" || !this.limit) return;
		this.toolCalls = (this.toolCalls ?? new Set()).add(toolCallId);
		if (this.toolCalls.size <= this.limit || this.limitHit) return;
		this.limitHit = true;
		await this.ctx.storage.put(LIMIT_KEY, { limit: this.limit, tool_calls: this.toolCalls.size });
		await this.harness.abort({ operationId: this.operationId });
	}

	async seed() {
		const box = await this.env.SNAPSHOT.getByName(SNAPSHOT_OBJECT).current();
		if (!box.record) return { status: 503, error: `no default snapshot is built, and the current key is ${box.key}; run worker/scripts/snapshot.mjs build` };
		const key = await harnessSetupKey(this.agent.image.setup);
		const record = await this.ctx.storage.get(SEED_KEY);
		if (!record || record.key !== key) await this.ctx.storage.put(SEED_KEY, { key, snapshot: { id: box.record.id }, usedAt: Date.now() });
		return { key, box: box.record.key, snapshot: box.record.id };
	}

	async exec(command, { user, timeoutMs = 120_000 } = {}) {
		const agent = user === "agent";
		const process = await this.ctx.container.exec(command, {
			env: agent ? AGENT_ENV : BOX_ENV,
			stderr: "combined",
			...(agent ? { user: AGENT_USER, cwd: REPO_DIR } : {}),
		});
		const timer = setTimeout(() => process.kill(9), timeoutMs);
		try {
			const output = await process.output();
			return { exitCode: output.exitCode, text: new TextDecoder().decode(output.stdout).trim() };
		} finally {
			clearTimeout(timer);
		}
	}

	async step({ operationId, brief, model, remote_url, branch, start_sha, skills: skillNames, max_iterations }) {
		if (!this.kind || this.kind === "echo") return { status: 400, error: "this object runs no CLI; its name must start with claude: or codex:" };
		if (typeof operationId !== "string" || !operationId) return { status: 400, error: "operationId is required" };
		if (typeof brief !== "string" || !brief) return { status: 400, error: "brief is required" };
		if (typeof model !== "string" || !KINDS[this.kind].model.test(model)) return { status: 400, error: `model must be a ${this.kind} model name, got ${JSON.stringify(model)}` };
		const { repo, error: refused } = await allowedRepo(this.env, remote_url);
		if (refused) return { status: 403, error: refused };
		if (!BRANCH.test(branch ?? "")) return { status: 400, error: `branch must start with ohflow/, got ${JSON.stringify(branch)}` };
		if (!/^[0-9a-f]{40}$/.test(start_sha ?? "")) return { status: 400, error: "start_sha must be a 40-digit commit id" };
		if (!stringList(skillNames)) return { status: 400, error: "skills must be a list of skill folder names in the skills repo the Worker mirrors" };
		const { limit, error: badLimit } = iterationLimit(max_iterations);
		if (badLimit) return { status: 400, error: badLimit };
		const stored = await this.ctx.storage.get(STEP_KEY);
		if (stored && stored.operationId !== operationId) return { status: 409, error: `this object already runs operation ${stored.operationId}` };
		let step = stored;
		if (!step) {
			if (!this.env.GITHUB_TOKEN) return { status: 500, error: "The Worker has no GITHUB_TOKEN." };
			const seed = await this.seed();
			if (seed.error) return seed;
			const skills = await pinSkills(() => skillsMirror(this.env.SKILLS_MIRROR), skillNames);
			if (skills.error) return skills;
			step = { operationId, repo, branch, start_sha, model, max_iterations: limit, snapshot: { key: seed.box, id: seed.snapshot }, skills };
			await this.ctx.storage.put(STEP_KEY, step);
			this.applyStep(step);
		}
		await this.ensureFeed();
		const receipt = await this.harness.submit(brief, { operationId });
		return { ...receipt, reattach: Boolean(stored), model: step.model, max_iterations: step.max_iterations ?? null, branch, start_sha, snapshot: step.snapshot.key, skills: step.skills ?? { sha: null, names: [] }, tools: [], mcp_servers: this.mcpServers() };
	}

	mcpServers() {
		return Object.keys(BOX_MCP.mcpServers);
	}

	async ensureFeed() {
		if (this.feed) return this.feed;
		const listeners = new Set();
		const stream = await this.harness.session().events();
		this.feed = { stream, listeners };
		stream.start((events) => {
			this.ctx.waitUntil(this.onEvents(events, listeners));
		});
		return this.feed;
	}

	async onEvents(events, listeners) {
		const lines = [];
		for (const event of events) {
			if (event.type === "usage") {
				const usage = (await this.ctx.storage.get(USAGE_KEY)) ?? { input: 0, output: 0, notional_cost_usd: 0 };
				usage.input += event.inputTokens ?? 0;
				usage.output += event.outputTokens ?? 0;
				usage.notional_cost_usd += event.costUsd ?? 0;
				await this.ctx.storage.put(USAGE_KEY, usage);
			} else if (event.type === "message" && event.message.role === "assistant") {
				for (const part of event.message.parts) {
					if (part.type !== "tool") continue;
					if (!this.seen.has(`start:${part.toolCallId}`)) {
						this.seen.add(`start:${part.toolCallId}`);
						lines.push(toolStart(part));
						await this.countToolCall(part.toolCallId);
					}
					if (part.state !== "running" && !this.seen.has(`end:${part.toolCallId}`)) {
						this.seen.add(`end:${part.toolCallId}`);
						lines.push(toolEnd(event.message, part));
					}
				}
			} else if (event.type === "container") {
				if (event.status === "lost" || event.status === "stopped") await this.closeMeter(false);
				lines.push({ type: "pi_cloud_container", status: event.status });
			} else if (event.type === "log" && event.level !== "info") {
				lines.push({ type: "pi_cloud_log", level: event.level, message: String(event.message).slice(0, 2000) });
			}
		}
		for (const line of lines) for (const listener of listeners) listener(line);
	}

	async publish(step) {
		if (!this.ctx.container?.running) return { head: null, dirty: null, pushed: false, push_error: "the container stopped before the result was pushed" };
		const clone = await this.exec(["sh", "-c", `cat ${OUT_DIR}/.box-clone-error 2>/dev/null`]);
		if (clone.text) return { head: null, dirty: null, pushed: false, push_error: `clone_failed: ${clone.text}` };
		const skills = await this.exec(["sh", "-c", `cat ${OUT_DIR}/.box-skills-error 2>/dev/null`]);
		if (skills.text) return { head: null, dirty: null, pushed: false, push_error: `skills_failed: ${skills.text}` };
		const head = await this.exec(["git", "-C", REPO_DIR, "rev-parse", "HEAD"], { user: "agent" });
		const status = await this.exec(["git", "-C", REPO_DIR, "status", "--porcelain"], { user: "agent" });
		const push = await this.exec(["git", "-C", REPO_DIR, "push", "--quiet", "origin", `HEAD:refs/heads/${step.branch}`], { user: "agent", timeoutMs: 300_000 });
		return {
			head: head.exitCode === 0 ? head.text : null,
			dirty: status.text ? status.text.split("\n") : [],
			pushed: push.exitCode === 0,
			...(push.exitCode === 0 ? {} : { push_error: push.text.slice(-800) }),
		};
	}

	async collectOut() {
		if (!this.ctx.container?.running) return;
		const result = await this.exec(["node", "-e", COLLECT_OUT]);
		if (result.exitCode !== 0) return;
		try {
			await this.ctx.storage.put(OUT_KEY, JSON.parse(result.text));
		} catch {}
	}

	async finish(step, settled) {
		const existing = await this.ctx.storage.get(END_KEY);
		if (existing) return existing;
		const git = await this.publish(step);
		await this.collectOut();
		const container = await this.closeMeter(true);
		const usage = (await this.ctx.storage.get(USAGE_KEY)) ?? { input: 0, output: 0, notional_cost_usd: 0 };
		const limited = settled.status !== "done" && Boolean((await this.ctx.storage.get(LIMIT_KEY)) || /^error_max_turns\b/.test(settled.reason ?? ""));
		const end = {
			type: "pi_cloud_end",
			operationId: step.operationId,
			status: settled.status,
			reason: limited ? TURN_LIMIT : (settled.reason ?? null),
			start: step.start_sha,
			branch: step.branch,
			...git,
			usage: { input: usage.input, output: usage.output, cacheRead: 0, cacheWrite: 0, totalTokens: usage.input + usage.output, cost: { total: 0 }, notional_cost_usd: usage.notional_cost_usd },
			container,
		};
		await this.ctx.storage.put(END_KEY, { ...end, settled });
		return { ...end, settled };
	}

	async events(operationId) {
		const step = await this.ctx.storage.get(STEP_KEY);
		const op = operationId || step?.operationId;
		const encoder = new TextEncoder();
		const { readable, writable } = new TransformStream();
		const out = writable.getWriter();
		const gone = new AbortController();
		out.closed.catch(() => gone.abort());
		const line = (event) => {
			if (!gone.signal.aborted) out.write(encoder.encode(`${JSON.stringify({ ...event, t: Date.now() })}\n`)).catch(() => gone.abort());
		};
		const run = async () => {
			let beat;
			let listener;
			try {
				if (!step || !op) throw new Error("this object holds no ohflow step; POST step first");
				line({ type: "pi_cloud_start", operationId: op, harness: this.kind, branch: step.branch, start: step.start_sha, model: step.model, max_iterations: step.max_iterations ?? null, snapshot: step.snapshot?.key ?? null, skills: step.skills ?? { sha: null, names: [] }, tools: [], mcp_servers: this.mcpServers(), durable_object_id: this.ctx.id.toString(), instance: INSTANCE });
				const done = await this.ctx.storage.get(END_KEY);
				if (!done) {
					const feed = await this.ensureFeed();
					listener = (event) => line(event);
					feed.listeners.add(listener);
					beat = setInterval(() => line({ type: "pi_cloud_beat" }), BEAT_MS);
				}
				const settled = done?.settled ?? (await this.harness.wait(op, { signal: gone.signal }));
				const end = await this.finish(step, settled);
				const usage = { input: end.usage.input, output: end.usage.output };
				for (const event of transcriptLines(await this.harness.messages(), settled, usage)) line(event);
				const { settled: _settled, ...visible } = end;
				line(visible);
			} catch (error) {
				if (!gone.signal.aborted) line({ type: "pi_cloud_error", name: error?.name, message: String(error?.message ?? error) });
			} finally {
				clearInterval(beat);
				if (listener) this.feed?.listeners.delete(listener);
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
		const usage = await this.ctx.storage.get(USAGE_KEY);
		return {
			operationId: op,
			aborted,
			container: await this.closeMeter(true),
			usage: usage ? { input: usage.input, output: usage.output, notional_cost_usd: usage.notional_cost_usd } : null,
			last_look,
		};
	}

	async transcript(name) {
		const step = await this.ctx.storage.get(STEP_KEY);
		const lines = [];
		for (const message of await this.harness.messages()) {
			for (const part of message.parts) {
				if (part.type === "text") lines.push(`- ${message.role}: ${part.text}`);
				else if (part.type === "tool") lines.push(`- tool ${part.toolName} (${part.state}): ${stringOf(part.input).slice(0, 300)}`);
			}
		}
		return `# ${name}\n\nHarness: ${this.kind}\nOperation: ${step?.operationId ?? "none"}\n\n${lines.join("\n")}\n`;
	}

	async outFile(file) {
		const files = (await this.ctx.storage.get(OUT_KEY)) ?? {};
		return Object.hasOwn(files, file) ? files[file] : null;
	}

	async stopContainer() {
		const container = this.ctx.container;
		if (!container?.running) return { running: false };
		await container.destroy();
		return { running: true, stopped: true };
	}

	async probe(text) {
		const seed = await this.seed();
		if (seed.error) return seed;
		const started = Date.now();
		const answer = await this.harness.prompt(text);
		const seconds = Math.round((Date.now() - started) / 1000);
		const record = await this.ctx.storage.get(SEED_KEY);
		const check = this.ctx.container?.running
			? (await this.exec(["sh", "-c", "test -f /etc/agent-box/AGENTS.md && echo default-snapshot; tail -5 /tmp/box-boot.log 2>&1; ps -eo args | grep -E '[m]cp-gateway|[d]aemon' | head"])).text
			: null;
		return { seed, seconds, result: { status: answer.status, reason: answer.reason ?? null, text: answer.text ?? null }, record, check };
	}
}
