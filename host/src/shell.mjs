import { existsSync } from "node:fs";
import { delimiter, join } from "node:path";

const GIT_BASH = ["C:\\Program Files\\Git\\bin\\bash.exe", "C:\\Program Files (x86)\\Git\\bin\\bash.exe"];

function onPath(name) {
	for (const dir of (process.env.PATH ?? "").split(delimiter)) {
		if (!dir) continue;
		const candidate = join(dir, name);
		if (existsSync(candidate)) return candidate;
	}
	return undefined;
}

export function shellPath(env = process.env, platform = process.platform) {
	const named = env.OHFLOW_BASH || env.CLAUDE_CODE_GIT_BASH_PATH;
	if (named) return named;
	if (platform === "win32") {
		const found = GIT_BASH.find((path) => existsSync(path));
		if (found) return found;
		throw new Error("no Git Bash found; set OHFLOW_BASH or CLAUDE_CODE_GIT_BASH_PATH to bash.exe");
	}
	const found = onPath("bash") ?? (existsSync("/bin/bash") ? "/bin/bash" : undefined);
	if (found) return found;
	throw new Error("no bash on PATH; set OHFLOW_BASH to a bash executable");
}
