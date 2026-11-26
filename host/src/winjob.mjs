import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const winjobExe = join(dirname(fileURLToPath(import.meta.url)), "..", "bin", "winjob.exe");
let attached = false;

export function requireWinjob() {
	if (!existsSync(winjobExe)) throw new Error(`${winjobExe} is missing; run npm run build:winjob`);
}

export function attachKillOnClose() {
	if (attached) return;
	requireWinjob();
	execFileSync(winjobExe, ["attach", String(process.pid)], { windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
	attached = true;
}
