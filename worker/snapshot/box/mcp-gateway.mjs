import { spawn } from "node:child_process";
import { createWriteStream, mkdirSync, readFileSync } from "node:fs";
import { createServer } from "node:http";
import { join } from "node:path";

const CONFIG = process.env.MCP_GATEWAY_CONFIG ?? "/etc/agent-box/mcp-servers.json";
const PORT = Number(process.env.MCP_GATEWAY_PORT ?? 8800);
const HOST = process.env.MCP_GATEWAY_HOST ?? "0.0.0.0";
const LOG_DIR = process.env.MCP_GATEWAY_LOGS ?? "/tmp/mcp-gateway";
const PROTOCOL = "2025-06-18";
const ROUTE = /^\/mcp\/([A-Za-z0-9._-]+)\/?$/;

const config = JSON.parse(readFileSync(CONFIG, "utf8"));
mkdirSync(LOG_DIR, { recursive: true });

class Child {
	constructor(name, spec) {
		this.name = name;
		this.spec = spec;
		this.proc = null;
		this.ready = null;
		this.pending = new Map();
		this.nextId = 1;
	}

	start() {
		if (this.ready) return this.ready;
		const { command, args = [], env = {}, cwd } = this.spec;
		const proc = spawn(command, args, { cwd, env: { ...process.env, ...env }, stdio: ["pipe", "pipe", "pipe"] });
		this.proc = proc;
		proc.stderr.pipe(createWriteStream(join(LOG_DIR, `${this.name}.log`), { flags: "a" }));
		proc.stdin.on("error", () => {});
		let buffer = "";
		proc.stdout.setEncoding("utf8");
		proc.stdout.on("data", (chunk) => {
			buffer += chunk;
			for (let end = buffer.indexOf("\n"); end >= 0; end = buffer.indexOf("\n")) {
				const line = buffer.slice(0, end).trim();
				buffer = buffer.slice(end + 1);
				if (line) this.receive(line);
			}
		});
		const gone = (why) => {
			if (this.proc !== proc) return;
			this.proc = null;
			this.ready = null;
			for (const waiter of this.pending.values()) waiter.reject(new Error(`MCP server ${this.name} ${why}`));
			this.pending.clear();
		};
		proc.on("exit", (code, signal) => gone(`exited with ${signal ?? code}`));
		proc.on("error", (error) => gone(`did not start: ${error.message}`));
		const ready = this.request("initialize", {
			protocolVersion: PROTOCOL,
			capabilities: {},
			clientInfo: { name: "box-mcp-gateway", version: "1" },
		}).then((reply) => {
			if (reply.error) throw new Error(`MCP server ${this.name} refused initialize: ${reply.error.message}`);
			this.send({ jsonrpc: "2.0", method: "notifications/initialized" });
			return reply.result;
		});
		ready.catch(() => {
			if (this.proc === proc) proc.kill();
		});
		this.ready = ready;
		return ready;
	}

	send(message) {
		this.proc?.stdin.write(`${JSON.stringify(message)}\n`);
	}

	request(method, params, signal) {
		return new Promise((resolve, reject) => {
			if (!this.proc) return reject(new Error(`MCP server ${this.name} is not running`));
			const id = this.nextId++;
			this.pending.set(id, { resolve, reject });
			this.send({ jsonrpc: "2.0", id, method, ...(params === undefined ? {} : { params }) });
			signal?.addEventListener(
				"abort",
				() => {
					if (!this.pending.delete(id)) return;
					this.send({ jsonrpc: "2.0", method: "notifications/cancelled", params: { requestId: id, reason: "the HTTP client went away" } });
					reject(new Error("cancelled"));
				},
				{ once: true },
			);
		});
	}

	receive(line) {
		let message;
		try {
			message = JSON.parse(line);
		} catch {
			return;
		}
		if (message.method && message.id !== undefined) {
			this.send({ jsonrpc: "2.0", id: message.id, error: { code: -32601, message: `box-mcp-gateway does not answer ${message.method}` } });
			return;
		}
		if (message.id === undefined || message.method) return;
		const waiter = this.pending.get(message.id);
		if (!waiter) return;
		this.pending.delete(message.id);
		waiter.resolve(message);
	}
}

const children = new Map(Object.entries(config.mcpServers ?? {}).map(([name, spec]) => [name, new Child(name, spec)]));

async function answer(child, message, signal) {
	if (message?.jsonrpc !== "2.0" || typeof message.method !== "string") {
		return { jsonrpc: "2.0", id: message?.id ?? null, error: { code: -32600, message: "not a JSON-RPC 2.0 request" } };
	}
	if (message.id === undefined || message.id === null) return null;
	const reply = (body) => ({ jsonrpc: "2.0", id: message.id, ...body });
	try {
		if (message.method === "ping") return reply({ result: {} });
		const init = await child.start();
		if (message.method === "initialize") return reply({ result: init });
		const response = await child.request(message.method, message.params, signal);
		return reply(response.error ? { error: response.error } : { result: response.result });
	} catch (error) {
		return reply({ error: { code: -32603, message: String(error?.message ?? error) } });
	}
}

function send(res, status, body, headers = {}) {
	const text = body === undefined ? "" : JSON.stringify(body);
	res.writeHead(status, { ...(text ? { "content-type": "application/json" } : {}), ...headers });
	res.end(text);
}

const server = createServer((req, res) => {
	const url = new URL(req.url, "http://box");
	if (url.pathname === "/health") {
		return send(res, 200, {
			servers: [...children.keys()],
			running: [...children.values()].filter((child) => child.proc).map((child) => child.name),
		});
	}
	const match = url.pathname.match(ROUTE);
	if (!match) return send(res, 404, { error: `no route ${url.pathname}` });
	const child = children.get(match[1]);
	if (!child) return send(res, 404, { error: `no MCP server ${match[1]}; the gateway serves ${[...children.keys()].join(", ")}` });
	if (req.method !== "POST") return send(res, 405, { error: "the gateway answers POST only" }, { allow: "POST" });
	const gone = new AbortController();
	res.on("close", () => {
		if (!res.writableFinished) gone.abort();
	});
	let body = "";
	req.setEncoding("utf8");
	req.on("data", (chunk) => {
		body += chunk;
	});
	req.on("end", async () => {
		let parsed;
		try {
			parsed = JSON.parse(body);
		} catch {
			return send(res, 400, { jsonrpc: "2.0", id: null, error: { code: -32700, message: "the body is not JSON" } });
		}
		const batch = Array.isArray(parsed);
		const replies = (await Promise.all((batch ? parsed : [parsed]).map((message) => answer(child, message, gone.signal)))).filter(Boolean);
		if (gone.signal.aborted) return;
		if (replies.length === 0) return send(res, 202);
		send(res, 200, batch ? replies : replies[0]);
	});
});

function stop() {
	for (const child of children.values()) child.proc?.kill();
	process.exit(0);
}
process.on("SIGTERM", stop);
process.on("SIGINT", stop);
server.listen(PORT, HOST, () => {
	console.log(`box-mcp-gateway on ${HOST}:${PORT} serves ${[...children.keys()].join(", ")}`);
});
