import { randomUUID } from "node:crypto";
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { createModels } from "@earendil-works/pi-ai/models";
import { deepseekProvider } from "@earendil-works/pi-ai/providers/deepseek";
import { zaiProvider } from "@earendil-works/pi-ai/providers/zai";
import { createRegistry, Harness } from "@earendil-works/pi-durable";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { HostExecutionEnv } from "./env.mjs";
import { releaseLock, takeLock } from "./lock.mjs";
import { entrySummary } from "./pi-events.mjs";
import { shellPath } from "./shell.mjs";
import { skillsExtension } from "./skills.mjs";
import { hostExtension } from "./tools.mjs";
import { attachKillOnClose } from "./winjob.mjs";

export const context = BACKGROUND_CONTEXT;
export const LADDER = ["zai/glm-5.3-flash", "deepseek/deepseek-flash", "zai/glm-5.3"];

let writeLog = (line) => process.stdout.write(line);

export function setLogWriter(writer) {
	writeLog = writer;
}

export function log(ev, data = {}) {
	writeLog(`${JSON.stringify({ t: Date.now(), pid: process.pid, ev, ...data })}\n`);
}

export function createHostModels() {
	const models = createModels();
	models.setProvider(zaiProvider());
	models.setProvider(deepseekProvider());
	return models;
}

export function parseModel(name) {
	const match = /^([^/\s]+)\/([^/\s]+)$/.exec(String(name ?? ""));
	if (!match) throw new Error(`model must be provider/id, such as ${LADDER[0]}; got ${JSON.stringify(name)}`);
	const ref = { provider: match[1], modelId: match[2] };
	if (!createHostModels().getModel(ref.provider, ref.modelId)) {
		throw new Error(`unknown model ${name}; the host serves ${LADDER.join(", ")} and the other zai and deepseek models`);
	}
	return ref;
}

export function callSpaceFor(file) {
	const sidecar = `${file}.callspace`;
	if (existsSync(file) && existsSync(sidecar)) return readFileSync(sidecar, "utf8").trim();
	const space = randomUUID();
	writeFileSync(sidecar, `${space}\n`);
	return space;
}

export async function closeHost(harness, file) {
	try {
		await harness.close(context);
	} finally {
		releaseLock(file);
	}
}

export async function openHost(file, { cwd = process.cwd(), tools, writeScope, bashCapSeconds = 300, skills = [], lockWaitSeconds = 0 } = {}) {
	mkdirSync(dirname(resolve(file)), { recursive: true });
	await takeLock(file, { waitSeconds: lockWaitSeconds });
	callSpaceFor(file);
	if (process.platform === "win32") attachKillOnClose();
	const models = createHostModels();
	const refusals = `${file}.refusals.jsonl`;
	const registry = createRegistry();
	if (skills.length) {
		registry.install(skillsExtension(skills));
		log("skills", { skills });
	}
	registry.install(
		hostExtension({
			role: "step",
			tools,
			writeScope,
			bashCapSeconds,
			onRefusal: (refusal) => {
				appendFileSync(refusals, `${JSON.stringify({ t: Date.now(), ...refusal })}\n`);
				log("refusal", refusal);
			},
			onCap: (cap) => log("command_cap", cap),
		}),
	);
	const shell = shellPath();
	const scratch = join(dirname(resolve(file)), `${basename(file, ".sqlite")}.scratch`);
	const storage = await openNodeSqliteStorage(file);
	return Harness.open(
		storage,
		{
			models,
			registry,
			env: ({ conversationId, cwd: agentCwd }) =>
				new HostExecutionEnv({ cwd: resolve(agentCwd ?? cwd), shellPath: shell, shellEnv: { GIT_PAGER: "cat" }, scratch: join(scratch, String(conversationId)) }),
			onReport: (error, info) => log("report", { type: info.type, message: String(error?.message ?? error) }),
		},
		context,
	);
}

export async function transcript(conversation) {
	const view = await conversation.viewState(context);
	const entries = view.value.entries.map((entry) => ({ kind: entry.kind, text: entrySummary(entry) }));
	view.dispose();
	return entries;
}
