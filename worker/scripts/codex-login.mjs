import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadSettings, settingsFile, workerUrl } from "./settings.mjs";

const url = workerUrl(loadSettings({ local: settingsFile() }));
const token = process.env.PI_CLOUD_TOKEN;
if (!token) {
	console.error("PI_CLOUD_TOKEN is not set");
	process.exit(2);
}
const headers = { authorization: `Bearer ${token}`, "content-type": "application/json", "user-agent": "pi-cloud-codex-login/1" };

if (process.argv[2] === "status") {
	const response = await fetch(`${url}/codex/login`, { headers });
	console.log(JSON.stringify(await response.json(), null, 2));
	process.exit(response.ok ? 0 : 1);
}

const home = mkdtempSync(join(tmpdir(), "codex-cloud-login-"));
try {
	writeFileSync(join(home, "config.toml"), 'cli_auth_credentials_store = "file"\n');
	console.log("A browser window opens for the ChatGPT sign-in. This login is for the pi-cloud Worker only.");
	const login = spawnSync("codex", ["login"], { stdio: "inherit", shell: process.platform === "win32", env: { ...process.env, CODEX_HOME: home } });
	if (login.status !== 0) throw new Error(`codex login exited ${login.status}`);
	const auth = JSON.parse(readFileSync(join(home, "auth.json"), "utf8"));
	if (auth.auth_mode !== "chatgpt") throw new Error(`codex login stored auth_mode ${auth.auth_mode}, expected chatgpt`);
	const response = await fetch(`${url}/codex/login`, { method: "POST", headers, body: JSON.stringify(auth) });
	const body = await response.json();
	if (!response.ok) throw new Error(`the Worker answered ${response.status}: ${body.error ?? JSON.stringify(body)}`);
	console.log(`The Worker holds the Codex login: ${JSON.stringify(body)}`);
} catch (error) {
	console.error(String(error?.message ?? error));
	process.exitCode = 1;
} finally {
	rmSync(home, { recursive: true, force: true });
}
