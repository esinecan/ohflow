import { existsSync, realpathSync } from "node:fs";
import { basename, dirname, isAbsolute, relative, resolve } from "node:path";
import { defineExtension, section } from "@earendil-works/pi-durable";
import { createBashTool, createEditTool, createPowerShellTool, createReadTool, createWriteTool } from "@earendil-works/pi-durable/tools";

export const REPLAY = { read: "safe", write: "unsafe", edit: "unsafe", bash: "unsafe", powershell: "unsafe" };

export const ROLES = {
	seat: ["read", "write", "edit", "bash", "powershell"],
	step: ["read", "write", "edit", "bash"],
};

const makers = { read: createReadTool, write: createWriteTool, edit: createEditTool, bash: createBashTool, powershell: createPowerShellTool };

export function globRegex(pattern) {
	const normalized = String(pattern).replaceAll("\\", "/");
	let source = "";
	for (let index = 0; index < normalized.length; index += 1) {
		const char = normalized[index];
		if (char === "*") source += ".*";
		else if (char === "?") source += ".";
		else if (char === "[") {
			let end = index + 1;
			if (normalized[end] === "!") end += 1;
			if (normalized[end] === "]") end += 1;
			while (end < normalized.length && normalized[end] !== "]") end += 1;
			if (end >= normalized.length) source += "\\[";
			else {
				let body = normalized.slice(index + 1, end);
				let negate = "";
				if (body.startsWith("!")) {
					negate = "^";
					body = body.slice(1);
				} else if (body.startsWith("^")) body = `\\${body}`;
				source += `[${negate}${body.replaceAll("\\", "\\\\")}]`;
				index = end;
			}
		} else source += char.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
	}
	return new RegExp(`^${source}$`, "i");
}

function throughExistingParents(target) {
	const missing = [];
	let cursor = resolve(target);
	while (!existsSync(cursor)) {
		const parent = dirname(cursor);
		if (parent === cursor) break;
		missing.unshift(basename(cursor));
		cursor = parent;
	}
	return resolve(realpathSync.native(cursor), ...missing);
}

export function mayWrite(path, cwd, scope) {
	const root = realpathSync.native(resolve(cwd));
	const target = throughExistingParents(resolve(root, String(path ?? "")));
	const inside = relative(root, target).replaceAll("\\", "/");
	if (!inside || inside === ".." || inside.startsWith("../") || isAbsolute(inside)) return false;
	return scope.some((pattern) => globRegex(pattern).test(inside));
}

function scoped(tool, scope, onRefusal) {
	return {
		...tool,
		execute: async (args, api, context) => {
			const cwd = api.env?.cwd ?? process.cwd();
			if (!mayWrite(args.path, cwd, scope)) {
				onRefusal({ tool: tool.name, path: args.path, cwd, scope, conversation: api.conversationId, call: api.callId });
				throw new Error(`${tool.name} refused: ${args.path} is outside this task's write scope. Allowed paths, relative to ${cwd}: ${scope.join(", ")}`);
			}
			return tool.execute(args, api, context);
		},
	};
}

function capped(tool, cap, onCap) {
	return {
		...tool,
		execute: (args, api, context) => {
			const requested = Number(args.timeout);
			const timeout = Number.isFinite(requested) && requested > 0 ? Math.min(requested, cap) : cap;
			onCap({ tool: tool.name, requested: Number.isFinite(requested) ? requested : null, applied: timeout, call: api.callId });
			return tool.execute({ ...args, timeout }, api, context);
		},
	};
}

export function hostExtension({ role, tools: only, writeScope, bashCapSeconds, onRefusal, onCap }) {
	const allowed = ROLES[role];
	if (!allowed) throw new Error(`unknown role ${role}; known: ${Object.keys(ROLES).join(", ")}`);
	const names = only ?? allowed;
	const outside = names.filter((name) => !allowed.includes(name));
	if (outside.length) throw new Error(`role ${role} has no tool ${outside.join(", ")}; it has ${allowed.join(", ")}`);
	const tools = names.map((name) => {
		let tool = { ...makers[name](), replay: REPLAY[name] };
		if (writeScope && (name === "edit" || name === "write")) tool = scoped(tool, writeScope, onRefusal);
		if (name === "bash" || name === "powershell") tool = capped(tool, bashCapSeconds, onCap);
		return tool;
	});
	const sections = [
		section("working-folder", (input) => input.env?.cwd),
		section("scratch", (input) => (input.env?.scratch ? `Scratch space for temporary files: ${input.env.scratch}` : undefined)),
	];
	if (writeScope) {
		sections.push(section("write-scope", () => `edit and write accept only paths under the working folder that match: ${writeScope.join(", ")}`));
	}
	return defineExtension({ name: "host", tools, sections });
}
