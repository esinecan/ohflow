const EMITTED_KINDS = new Set(["pi.user", "pi.assistant", "pi.tool-result"]);

export class PiEventWriter {
	constructor(write) {
		this.write = write;
		this.entries = new Set();
		this.calls = new Map();
		this.ended = new Set();
		this.outputs = new Map();
	}

	emit(event) {
		this.write(`${JSON.stringify({ ...event, t: Date.now() })}\n`);
	}

	entry(entry, extra = {}) {
		if (!entry || this.entries.has(entry.id) || !EMITTED_KINDS.has(entry.kind)) return;
		this.entries.add(entry.id);
		const message = entry.model?.[0];
		if (!message) return;
		const entryId = entry.id;
		if (entry.kind === "pi.assistant") {
			for (const block of message.content ?? []) if (block.type === "toolCall") this.calls.set(block.id, block);
			this.emit({ type: "message_end", message, entryId, ...extra });
		} else if (entry.kind === "pi.user") {
			this.emit({ type: "message_end", message, entryId, ...extra });
		} else if (!this.ended.has(message.toolCallId)) {
			if (!this.calls.get(message.toolCallId)?.started) {
				const call = this.calls.get(message.toolCallId);
				this.emit({ type: "tool_execution_start", toolCallId: message.toolCallId, toolName: message.toolName, args: call?.arguments ?? {}, entryId, ...extra });
			}
			this.ended.add(message.toolCallId);
			this.emit({ type: "tool_execution_end", toolCallId: message.toolCallId, toolName: message.toolName, result: { content: message.content ?? [] }, isError: Boolean(message.isError), entryId, ...extra });
		}
	}

	replay(entries, extra = { replayed: true }) {
		for (const entry of entries) this.entry(entry, extra);
	}

	running(slots) {
		for (const slot of slots ?? []) {
			if (slot.entry || slot.status === "done" || this.ended.has(slot.callId)) continue;
			const call = this.calls.get(slot.callId) ?? {};
			if (call.started) {
				if (slot.output && slot.output !== this.outputs.get(slot.callId)) {
					this.outputs.set(slot.callId, slot.output);
					this.emit({ type: "tool_execution_update", toolCallId: slot.callId, toolName: slot.name, partialResult: { content: [{ type: "text", text: slot.output }] } });
				}
				continue;
			}
			this.calls.set(slot.callId, { ...call, started: true });
			this.emit({ type: "tool_execution_start", toolCallId: slot.callId, toolName: slot.name, args: call.arguments ?? {} });
			if (slot.output) {
				this.outputs.set(slot.callId, slot.output);
				this.emit({ type: "tool_execution_update", toolCallId: slot.callId, toolName: slot.name, partialResult: { content: [{ type: "text", text: slot.output }] } });
			}
		}
	}

	event(event) {
		switch (event.type) {
			case "message_end":
				this.entry(event.entry);
				break;
			case "entry_appended":
				if (event.entry?.kind === "pi.tool-result") this.entry(event.entry);
				break;
			case "tool_execution_start": {
				if (event.parentToolCallId) break;
				const call = this.calls.get(event.toolCallId) ?? {};
				this.calls.set(event.toolCallId, { ...call, started: true });
				this.emit({ type: "tool_execution_start", toolCallId: event.toolCallId, toolName: event.toolName, args: event.args ?? {} });
				break;
			}
			case "tool_execution_update": {
				if (event.parentToolCallId || !event.output) break;
				const before = this.outputs.get(event.toolCallId) ?? "";
				const text = "set" in event.output ? event.output.set : before.slice(event.output.trimStart ?? 0) + (event.output.append ?? "");
				this.outputs.set(event.toolCallId, text);
				this.emit({ type: "tool_execution_update", toolCallId: event.toolCallId, toolName: event.toolName, partialResult: { content: [{ type: "text", text }] } });
				break;
			}
			case "tool_execution_end":
				if (event.parentToolCallId) break;
				if (event.entry) this.entry(event.entry);
				else if (!this.ended.has(event.toolCallId)) {
					this.ended.add(event.toolCallId);
					this.emit({ type: "tool_execution_end", toolCallId: event.toolCallId, toolName: event.toolName, result: { content: [{ type: "text", text: "the tool task ended without a result" }] }, isError: true });
				}
				break;
			case "auto_retry_start":
				this.emit({ type: "auto_retry_start", attempt: event.attempt, errorMessage: event.errorMessage });
				break;
			case "task_failed":
				this.emit({ type: "durable_task_failed", kind: event.kind, message: event.message });
				break;
		}
	}
}

export function entrySummary(entry) {
	if (entry.kind === "pi.system") return "";
	const parts = [];
	for (const message of entry.model ?? []) {
		const role = message.isError ? `${message.role} error` : message.role;
		const content = typeof message.content === "string" ? [{ type: "text", text: message.content }] : (message.content ?? []);
		for (const item of content) {
			if (item.type === "text") parts.push(`${role}: ${item.text.slice(0, 400)}`);
			else if (item.type === "toolCall") parts.push(`${role} calls ${item.name} ${JSON.stringify(item.arguments).slice(0, 300)}`);
			else if (item.type !== "thinking") parts.push(`${role} ${item.type}`);
		}
	}
	return parts.join(" | ");
}
