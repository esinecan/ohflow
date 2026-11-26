import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

if (process.platform !== "win32") process.exit(0);
const root = dirname(fileURLToPath(import.meta.url));
const csc = join(process.env.WINDIR ?? "C:\\Windows", "Microsoft.NET", "Framework64", "v4.0.30319", "csc.exe");
if (!existsSync(csc)) {
	console.error(`csc not found at ${csc}`);
	process.exit(1);
}
mkdirSync(join(root, "bin"), { recursive: true });
const out = join(root, "bin", "winjob.exe");
execFileSync(csc, ["/nologo", "/optimize+", "/target:exe", `/out:${out}`, join(root, "native", "winjob.cs")], { stdio: ["ignore", process.stderr, process.stderr], windowsHide: true });
console.error(`built ${out}`);
