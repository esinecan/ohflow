import { existsSync, mkdirSync } from "node:fs";
import { delimiter, extname, isAbsolute, join, resolve } from "node:path";
import { err, ExecutionError } from "@earendil-works/pi-durable/env";
import { NodeExecutionEnv } from "@earendil-works/pi-durable/env/node";
import { winjobExe } from "./winjob.mjs";

function resolveProgram(program, cwd, path) {
	if (isAbsolute(program) || /[\\/]/.test(program)) {
		const full = resolve(cwd, program);
		return existsSync(full) ? full : undefined;
	}
	const extensions = process.platform !== "win32" || extname(program) ? [""] : [".com", ".exe"];
	for (const dir of path.split(delimiter)) {
		if (!dir) continue;
		for (const extension of extensions) {
			const candidate = join(dir, program + extension);
			if (existsSync(candidate)) return candidate;
		}
	}
	return undefined;
}

export class HostExecutionEnv extends NodeExecutionEnv {
	constructor({ scratch, ...options }) {
		super(options);
		if (!options.shellPath) throw new Error("HostExecutionEnv needs shellPath");
		this.bash = options.shellPath;
		this.scratch = scratch;
		if (scratch) mkdirSync(scratch, { recursive: true });
	}

	stopChildren() {
		for (const pid of this.activeChildPids) {
			try {
				process.kill(pid);
			} catch {}
		}
	}

	async exec(command, options, context) {
		const signal = context.abortSignal;
		if (signal?.aborted) return err(new ExecutionError("aborted", "aborted"));
		const [first, ...rest] = typeof command === "string" ? [this.bash, "-c", command] : command;
		const cwd = options?.cwd ?? this.cwd;
		const path = options?.env?.Path ?? options?.env?.PATH ?? process.env.PATH ?? "";
		const program = first === undefined ? undefined : resolveProgram(first, cwd, path);
		if (program === undefined) return err(new ExecutionError("spawn_error", `spawn ${first} ENOENT`));
		const seconds = options?.timeout;
		let timedOut = false;
		const stop = () => this.stopChildren();
		const timer =
			seconds === undefined
				? undefined
				: setTimeout(() => {
						timedOut = true;
						stop();
					}, seconds * 1000);
		signal?.addEventListener("abort", stop, { once: true });
		try {
			const argv = process.platform === "win32" ? [winjobExe, "run", program, ...rest] : [program, ...rest];
			const result = await super.exec(argv, { ...options, timeout: undefined }, context);
			if (!timedOut) return result;
			const error = new ExecutionError("timeout", `timeout:${seconds}`);
			if (result.ok && result.value.spillPath) error.spillPath = result.value.spillPath;
			return err(error);
		} finally {
			clearTimeout(timer);
			signal?.removeEventListener("abort", stop);
		}
	}

	async cleanup(context) {
		this.stopChildren();
		await super.cleanup(context);
	}
}
