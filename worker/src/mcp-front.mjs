const MAX_NAME = 64;

export function mcpGlobRegex(pattern) {
	let out = "";
	for (let index = 0; index < pattern.length; index += 1) {
		const char = pattern[index];
		if (char === "*" && pattern[index + 1] === "*") {
			out += ".*";
			index += 1;
		} else if (char === "*") out += "[^.]*";
		else if (char === "?") out += "[^.]";
		else out += char.replace(/[.+^${}()|[\]\\/-]/g, "\\$&");
	}
	return new RegExp(`^${out}$`);
}

export function mcpMatchesGlob(pattern, address) {
	return mcpGlobRegex(pattern).test(address);
}

export function selectTools(servers, { allow = [], block = [] } = {}) {
	const selected = {};
	const addresses = [];
	for (const [server, entry] of Object.entries(servers)) {
		for (const tool of entry.tools ?? []) {
			const address = `${server}.${tool.name}`;
			addresses.push(address);
			if (allow.length && !allow.some((pattern) => mcpMatchesGlob(pattern, address))) continue;
			if (block.some((pattern) => mcpMatchesGlob(pattern, address))) continue;
			(selected[server] ??= []).push(tool);
		}
	}
	const unmatched = allow.filter((pattern) => !addresses.some((address) => mcpMatchesGlob(pattern, address)));
	return { selected, unmatched };
}

function hash8(text) {
	let value = 0x811c9dc5;
	for (const char of text) {
		value ^= char.codePointAt(0);
		value = Math.imul(value, 0x01000193) >>> 0;
	}
	return value.toString(16).padStart(8, "0");
}

export function namespacePrefix(server) {
	return `mcp__${server}__`.replace(/[^A-Za-z0-9_]/g, "_");
}

export function toolName(server, tool) {
	const name = `mcp__${server}__${tool}`.replace(/[^A-Za-z0-9_]/g, "_");
	if (name.length <= MAX_NAME) return name;
	return `${name.slice(0, MAX_NAME - 9)}_${hash8(`${server}\0${tool}`)}`;
}

export function mcpToolNames(selected) {
	return Object.entries(selected).flatMap(([server, tools]) => tools.map((tool) => toolName(server, tool.name)));
}

function toContent(result) {
	const content = [];
	for (const block of result.content ?? []) {
		if (block.type === "text") content.push({ type: "text", text: block.text });
		else if (block.type === "image") content.push({ type: "image", data: block.data, mimeType: block.mimeType });
		else if (block.type === "resource" && typeof block.resource?.text === "string") content.push({ type: "text", text: block.resource.text });
		else content.push({ type: "text", text: `[${block.type} ${block.uri ?? block.resource?.uri ?? ""}]` });
	}
	if (content.length === 0 && result.structuredContent !== undefined) content.push({ type: "text", text: JSON.stringify(result.structuredContent) });
	return content;
}

function parameters(schema) {
	const { $schema, ...rest } = schema ?? {};
	return { ...rest, type: "object", properties: rest.properties ?? {} };
}

function text(message, isError = false) {
	return { output: [{ type: "text", text: message }], isError };
}

export class McpCallText extends Error {
	constructor(message, options) {
		super(message, options);
		this.name = "McpCallText";
	}
}

export function createMcpExtensions({ selected, call, summary, codemode, place = "" }) {
	const tools = [];
	const counts = [];
	const names = new Map();
	for (const [server, list] of Object.entries(selected)) {
		for (const tool of list) {
			const address = `${server}.${tool.name}`;
			const name = toolName(server, tool.name);
			if (names.has(name)) throw new Error(`MCP tool name collision: ${names.get(name)} and ${address} both become ${name}`);
			names.set(name, address);
			tools.push({
				name,
				description: `[${server}] ${tool.description ?? tool.name}`,
				parameters: parameters(tool.inputSchema),
				replay: "unsafe",
				callers: ["tools"],
				async execute(args, api, context) {
					let result;
					try {
						result = await call(server, tool.name, args ?? {}, context.abortSignal);
					} catch (error) {
						if (context.abortSignal?.aborted) throw error;
						if (error instanceof McpCallText || error?.name === "McpCallText") return text(error.message, true);
						return text(`${address} failed: ${String(error?.message ?? error)}`, true);
					}
					const output = toContent(result);
					return result.isError === true ? { output: [{ type: "text", text: `${address} returned an error` }, ...output], isError: true } : { output, isError: false };
				},
			});
		}
		counts.push(`${server} (${list.length})`);
	}
	const rendered = summary(counts.join(", "));
	const mcp = {
		name: "mcp",
		tools,
		sections: [{ key: "mcp", tag: false, render: () => rendered }],
	};
	const namespaces = Object.keys(selected).map((server) => ({ name: server, description: `MCP server ${server}${place ? ` ${place}` : ""}`, prefix: namespacePrefix(server) }));
	return [mcp, codemode(namespaces)];
}
