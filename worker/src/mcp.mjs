import { createCodemodeExtension } from "@earendil-works/pi-durable/codemode";
import { RemoteCodemodeSandbox } from "@earendil-works/pi-codemode/portable";
import { BOX_MCP } from "./snapshot.mjs";
import { McpCallText } from "./mcp-front.mjs";

export { createMcpExtensions, mcpGlobRegex, mcpMatchesGlob, mcpToolNames, namespacePrefix, selectTools, toolName } from "./mcp-front.mjs";

export const GATEWAY_PORT = 8800;
const SECRETS = Object.entries(BOX_MCP.secrets ?? {});
export const EGRESS_HOSTS =[...new Set(SECRETS.flatMap(([, rule]) => rule.hosts))];

export class GatewayLost extends Error {
	constructor(message, options) {
		super(message, options);
		this.name = "GatewayLost";
	}
}

export async function rpc(post, server, method, params, signal) {
	const response = await post(`/mcp/${encodeURIComponent(server)}`, { jsonrpc: "2.0", id: 1, method, params }, signal);
	if (response.error) throw new Error(`${server} ${method}: ${response.error.message ?? JSON.stringify(response.error)}`);
	return response.result;
}

export async function listGatewayTools(health, post) {
	const { servers: names } = await health();
	const servers = {};
	for (const server of names) {
		try {
			const tools = [];
			let cursor;
			do {
				const page = await rpc(post, server, "tools/list", cursor ? { cursor } : {});
				tools.push(...(page.tools ?? []));
				cursor = page.nextCursor;
			} while (cursor);
			servers[server] = { tools };
		} catch (error) {
			servers[server] = { error: String(error?.message ?? error) };
		}
	}
	return servers;
}

export const BOX_SUMMARY = (counts) =>
	[
		`MCP servers run in the box behind box-mcp-gateway; with their tool counts: ${counts}.`,
		"Their tools are functions for codemode scripts only, named tools.mcp__<server>__<tool>(args), with dashes in a server name written as underscores.",
		'Call them from the codemode tool; a script finds them with searchTools("<words>") and describeNamespace("<server>").',
		"A result that starts with interrupted: means the box stopped during the call; the call may have partly run.",
	].join("\n");

export function gatewayCall(post, interrupted) {
	return async (server, tool, args, signal) => {
		try {
			return await rpc(post, server, "tools/call", { name: tool, arguments: args }, signal);
		} catch (error) {
			if (signal?.aborted) throw error;
			if (error instanceof GatewayLost || (await interrupted())) {
				throw new McpCallText(`interrupted: the box container stopped during the call to ${server}.${tool}; the call may have partly run. Calling it again starts a fresh box, and any state the server held in memory is gone.`, { cause: error });
			}
			throw error;
		}
	};
}

export function codemodeFactory(remote) {
	return (namespaces) => createCodemodeExtension({ sandbox: new RemoteCodemodeSandbox({ timeoutMs: 10 * 60_000, remote }), models: false, namespaces });
}

export async function boxEgress(env, request) {
	const url = new URL(request.url);
	const rules = SECRETS.filter(([, rule]) => rule.hosts.includes(url.hostname));
	if (url.protocol !== "https:" || rules.length === 0) {
		return new Response(`pi-cloud egress refuses ${url.protocol}//${url.host}; the box reaches only https://${EGRESS_HOSTS.join(", https://")}\n`, { status: 403 });
	}
	const headers = new Headers(request.headers);
	for (const [name, rule] of rules) {
		const value = headers.get(rule.header);
		if (!value?.includes(rule.placeholder)) continue;
		if (!env[name]) return new Response(`pi-cloud has no Worker secret ${name}\n`, { status: 502 });
		headers.set(rule.header, value.replaceAll(rule.placeholder, env[name]));
	}
	return fetch(new Request(url, { method: request.method, headers, body: request.body, redirect: "manual" }));
}

export function secretNeedles(env) {
	return SECRETS.map(([name, rule]) => ({ name, placeholder: rule.placeholder, value: env[name] ?? null }));
}
