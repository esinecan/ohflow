export const BASE_IMAGE = "cloudflare/debian-trixie";
export const AGENT_USER = "10001:10001";
export const BOX_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin";

export function gitIdentity(value) {
	const identity = value ?? { name: "ohflow", email: "ohflow@users.noreply.github.com" };
	for (const key of ["name", "email"]) {
		if (typeof identity[key] !== "string" || !identity[key].trim() || /[\x00-\x1f\x7f<>]/.test(identity[key])) {
			throw new Error(`git_identity.${key} must be a nonempty single-line Git identity value`);
		}
	}
	return { name: identity.name.trim(), email: identity.email.trim() };
}

export const PINS = {
	computerd: "sha256:97b9722806c3af678d17d0fd2c9a60f34794ef50efade2870f2d48d9151f8299",
	uv: "0.13.8",
	pnpm: "10.23.0",
	pi: "1.4.0",
	codex: "0.160.0",
	claude: "2.1.295",
	sequentialThinking: "2026.7.4",
	braveSearch: "2.1.0",
	playwrightMcp: "0.0.85",
	agents: "0.30.1",
	python: {
		pymupdf: "2.1",
		pillow: "13.0.0",
		pdfplumber: "0.11.10",
		pypdf: "7.1.1",
		"python-docx": "1.2.0",
		openpyxl: "3.1.5",
		"python-pptx": "1.0.2",
		beautifulsoup4: "4.15.0",
		"yt-dlp": "2026.10.26",
	},
};

const APT = [
	"git", "ca-certificates", "curl", "gh", "ripgrep", "jq", "python3", "python3-venv", "pandoc",
	"ffmpeg", "sqlite3", "fuse3", "libfuse2t64", "xz-utils", "unzip", "procps", "file", "python3-pip",
	"poppler-utils", "tesseract-ocr", "tesseract-ocr-deu", "tesseract-ocr-eng", "antiword",
];

const RETRY = 'retry() { "$@" || { echo "retrying: $*" >&2; sleep 3; "$@"; }; }';

function pyPins(names) {
	return names.map((name) => `${name}==${PINS.python[name]}`).join(" ");
}

const PY_SYSTEM = "uv pip install --system --break-system-packages";

const GIT_AUTH =
	'git -c credential.helper= -c "http.https://github.com/.extraheader=Authorization: Basic $(printf \'x-access-token:%s\' "$GH_SETUP_TOKEN" | base64 -w0)"';

function sh(script) {
	return ["bash", "-euo", "pipefail", "-c", script];
}

const REPO = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const SHA = /^[0-9a-f]{40}$/;
const NAME = /^[A-Za-z0-9][A-Za-z0-9_.-]*$/;
export const SKILLS_DIR = "/opt/agent-skills";
const HOMES = "/root /home/agent";
export const SNAPSHOT_DEFAULTS = { skills: null, repos: [], mcp_servers: {} };

function checkedRepo(entry, what) {
	if (!entry || typeof entry !== "object") throw new Error(`${what} must be an object with repo and sha`);
	if (typeof entry.repo !== "string" || !REPO.test(entry.repo)) throw new Error(`${what}.repo must be <owner>/<name>, got ${JSON.stringify(entry.repo)}`);
	if (typeof entry.sha !== "string" || !SHA.test(entry.sha)) throw new Error(`${what}.sha must be a full 40-character commit id, got ${JSON.stringify(entry.sha)}`);
	return { repo: entry.repo, sha: entry.sha };
}

export function snapshotSettings(raw) {
	const settings = { ...SNAPSHOT_DEFAULTS, ...(raw ?? {}) };
	const skills = settings.skills ? checkedRepo(settings.skills, "snapshot.skills") : null;
	if (!Array.isArray(settings.repos)) throw new Error("snapshot.repos must be a list");
	const repos = settings.repos.map((entry, index) => {
		const { repo, sha } = checkedRepo(entry, `snapshot.repos[${index}]`);
		const name = entry.name ?? repo.split("/")[1];
		if (!NAME.test(name)) throw new Error(`snapshot.repos[${index}].name must be a folder name, got ${JSON.stringify(name)}`);
		const build = entry.build ?? [];
		if (!Array.isArray(build) || build.some((line) => typeof line !== "string")) throw new Error(`snapshot.repos[${index}].build must be a list of shell lines`);
		return { repo, sha, name, build };
	});
	const servers = settings.mcp_servers ?? {};
	if (typeof servers !== "object" || Array.isArray(servers)) throw new Error("snapshot.mcp_servers must be an object of MCP server entries");
	return { skills, repos, mcp_servers: servers };
}

export function boxFiles(files, operator = {}) {
	const snapshot = snapshotSettings(operator.snapshot);
	const rules = typeof operator.rules === "string" ? operator.rules.trim() : "";
	const agents = rules ? `${files.agents.trimEnd()}\n\n${rules}\n` : files.agents;
	let servers = files.servers;
	if (Object.keys(snapshot.mcp_servers).length) {
		const table = JSON.parse(files.servers);
		table.mcpServers = { ...table.mcpServers, ...snapshot.mcp_servers };
		servers = `${JSON.stringify(table, null, "\t")}\n`;
	}
	return { ...files, agents, servers };
}

function clone(repo, sha, dir) {
	const url = `https://github.com/${repo}.git`;
	return [
		`${GIT_AUTH} clone --quiet ${url} ${dir}`,
		`git -C ${dir} checkout --quiet -B main ${sha}`,
		`test "$(git -C ${dir} rev-parse HEAD)" = ${sha}`,
		`test "$(git -C ${dir} remote get-url origin)" = ${url}`,
	].join(" && ");
}

function repoStep({ repo, sha, name, build }) {
	const dir = `/opt/mcp/${name}`;
	return {
		name: `install ${name}`,
		secret: true,
		command: sh([clone(repo, sha, dir), ...build.map((line) => `(cd ${dir} && ${line})`)].join(" && ")),
	};
}

function skillsStep({ repo, sha }) {
	return {
		name: "clone the skills repo",
		secret: true,
		command: sh(clone(repo, sha, SKILLS_DIR)),
	};
}

const SKILLS_LINKS = {
	name: "link the skills folder",
	command: sh(
		`mkdir -p ${SKILLS_DIR} && for home in ${HOMES}; do mkdir -p $home/.agents $home/.claude && ln -sfn ${SKILLS_DIR} $home/.agents/skills && ln -sfn ${SKILLS_DIR} $home/.claude/skills; done`,
	),
};

const DAEMON_EXTRACT = [
	'const fs = require("fs");',
	'const src = fs.readFileSync(process.argv[1], "utf8");',
	"const match = src.match(/const DAEMON_SOURCE = (\".*\");\\n/);",
	'if (!match) throw new Error("DAEMON_SOURCE not found");',
	"process.stdout.write(JSON.parse(match[1]));",
].join(" ");

export const CLI_HOSTS = {
	anthropic: "anthropic.harness.internal",
	chatgpt: "chatgpt.harness.internal",
	github: "github.harness.internal",
	skills: "skills.harness.internal",
};
export const GATEWAY_URL = "http://127.0.0.1:8800/mcp";
const FAR_FUTURE = 4102444800;

function placeholderJwt(claims) {
	const part = (value) => btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
	return `${part({ alg: "none", typ: "JWT" })}.${part(claims)}.box-placeholder`;
}

export function cliConfigs(serversText) {
	const names = Object.keys(JSON.parse(serversText).mcpServers);
	const claude = {
		hasCompletedOnboarding: true,
		mcpServers: Object.fromEntries(names.map((name) => [name, { type: "http", url: `${GATEWAY_URL}/${name}` }])),
	};
	const codexConfig = [
		'cli_auth_credentials_store = "file"',
		`chatgpt_base_url = "http://${CLI_HOSTS.chatgpt}/backend-api/"`,
		'model_provider = "box"',
		"",
		"[model_providers.box]",
		'name = "ChatGPT through the box egress"',
		`base_url = "http://${CLI_HOSTS.chatgpt}/backend-api/codex"`,
		'wire_api = "responses"',
		"requires_openai_auth = true",
		"supports_websockets = false",
		...names.flatMap((name) => ["", `[mcp_servers.${name}]`, `url = "${GATEWAY_URL}/${name}"`]),
		"",
	].join("\n");
	const auth = {
		"https://api.openai.com/auth": {
			chatgpt_plan_type: "plus",
			chatgpt_account_id: "box-placeholder",
			chatgpt_user_id: "box-placeholder",
			user_id: "box-placeholder",
		},
		email: "box@ohflow.invalid",
		exp: FAR_FUTURE,
		iat: 1794700000,
	};
	const codexAuth = {
		auth_mode: "chatgpt",
		OPENAI_API_KEY: null,
		tokens: {
			id_token: placeholderJwt(auth),
			access_token: placeholderJwt(auth),
			refresh_token: "box-placeholder",
			account_id: "box-placeholder",
		},
		last_refresh: "2099-01-01T00:00:00Z",
	};
	return { claude: `${JSON.stringify(claude, null, 2)}\n`, codexConfig, codexAuth: `${JSON.stringify(codexAuth, null, 2)}\n` };
}

export function recipe(files, settings, identitySetting) {
	const snapshot = snapshotSettings(settings);
	const identity = gitIdentity(identitySetting);
	return [
		{
			name: "create the agent user and workspace",
			command: [
				"sh",
				"-c",
				"id -u agent >/dev/null 2>&1 || useradd --create-home --uid 10001 --shell /bin/sh agent; mkdir -p /workspace /opt/harness && chown 10001:10001 /workspace",
			],
		},
		{
			name: "install Debian packages",
			command: sh(
				`apt-get update -qq && apt-get install -y -qq --no-install-recommends ${APT.join(" ")} && rm -rf /var/lib/apt/lists/*`,
			),
		},
		{
			name: "set the box Git name",
			command: ["git", "config", "--system", "user.name", identity.name],
		},
		{
			name: "set the box Git email",
			command: ["git", "config", "--system", "user.email", identity.email],
		},
		{
			name: "install uv",
			command: sh(
				`curl -fsSL https://github.com/astral-sh/uv/releases/download/${PINS.uv}/uv-x86_64-unknown-linux-gnu.tar.gz | tar -xz -C /usr/local/bin --strip-components=1 uv-x86_64-unknown-linux-gnu/uv uv-x86_64-unknown-linux-gnu/uvx`,
			),
		},
		{
			name: "install the document tools and yt-dlp",
			command: sh(
				[
					RETRY,
					`retry ${PY_SYSTEM} --no-deps ${pyPins(["pymupdf"])}`,
					`retry ${PY_SYSTEM} ${pyPins(Object.keys(PINS.python).filter((name) => name !== "pymupdf"))}`,
					"python3 -c 'import pymupdf, pdfplumber, pypdf, docx, openpyxl, pptx, bs4, PIL'",
					"yt-dlp --version",
					"pip --version",
				].join("\n"),
			),
		},
		{
			name: "install computerd",
			command: sh(
				[
					"cd /tmp",
					'token=$(curl -fsSL "https://ghcr.io/token?scope=repository:cloudflare/computer-computerd-linux-x64:pull" | jq -r .token)',
					`curl -fsSL -H "Authorization: Bearer $token" -o computerd.tgz https://ghcr.io/v2/cloudflare/computer-computerd-linux-x64/blobs/${PINS.computerd}`,
					`echo "${PINS.computerd.slice(7)}  computerd.tgz" | sha256sum -c --quiet`,
					"tar -xzf computerd.tgz -C / usr/local/bin/computerd",
					"rm computerd.tgz",
					"test -x /usr/local/bin/computerd",
				].join(" && "),
			),
		},
		{
			name: "install the CLIs and the npm MCP servers",
			command: [
				"npm", "install", "--global", "--no-fund", "--no-audit",
				`pnpm@${PINS.pnpm}`,
				`@earendil-works/pi-coding-agent@${PINS.pi}`,
				`@openai/codex@${PINS.codex}`,
				`@anthropic-ai/claude-code@${PINS.claude}`,
				`@modelcontextprotocol/server-sequential-thinking@${PINS.sequentialThinking}`,
				`@brave/brave-search-mcp-server@${PINS.braveSearch}`,
				`@playwright/mcp@${PINS.playwrightMcp}`,
			],
		},
		{
			name: "install headless Chromium",
			command: sh(
				[
					"cli=/usr/local/lib/node_modules/@playwright/mcp/node_modules/playwright/cli.js",
					'test -f "$cli"',
					"PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright node \"$cli\" install --with-deps chromium",
					"rm -rf /var/lib/apt/lists/*",
					`for home in ${HOMES}; do mkdir -p $home/.cache && ln -sfn /opt/ms-playwright $home/.cache/ms-playwright; done`,
				].join(" && "),
			),
		},
		...(snapshot.skills ? [skillsStep(snapshot.skills)] : []),
		SKILLS_LINKS,
		...snapshot.repos.map(repoStep),
		{
			name: "write the box AGENTS.md",
			stdin: files.agents,
			command: sh(
				[
					"mkdir -p /etc/agent-box",
					"cat > /etc/agent-box/AGENTS.md",
					`for home in ${HOMES}; do mkdir -p $home/.pi/agent $home/.codex $home/.claude && ln -sfn /etc/agent-box/AGENTS.md $home/.pi/agent/AGENTS.md && ln -sfn /etc/agent-box/AGENTS.md $home/.codex/AGENTS.md && ln -sfn /etc/agent-box/AGENTS.md $home/.claude/CLAUDE.md; done`,
				].join(" && "),
			),
		},
		{
			name: "write box-versions",
			stdin: files.versions,
			command: sh("cat > /usr/local/bin/box-versions && chmod 755 /usr/local/bin/box-versions"),
		},
		{
			name: "write box-chromium",
			stdin: files.chromium,
			command: sh("cat > /usr/local/bin/box-chromium && chmod 755 /usr/local/bin/box-chromium"),
		},
		{
			name: "write the MCP gateway and its server table",
			stdin: JSON.stringify({ gateway: files.gateway, servers: files.servers }),
			command: sh(
				[
					"mkdir -p /usr/local/lib/box /etc/agent-box",
					"node -e 'const f = JSON.parse(require(\"fs\").readFileSync(0, \"utf8\")); const w = require(\"fs\").writeFileSync; w(\"/usr/local/lib/box/mcp-gateway.mjs\", f.gateway); w(\"/etc/agent-box/mcp-servers.json\", f.servers);'",
					"node --check /usr/local/lib/box/mcp-gateway.mjs",
					"jq -e '.mcpServers | length > 0' /etc/agent-box/mcp-servers.json > /dev/null",
				].join(" && "),
			),
		},
		{
			name: "write the Claude Code and Codex configs",
			stdin: JSON.stringify(cliConfigs(files.servers)),
			command: sh(
				[
					"mkdir -p /home/agent/.codex",
					"node -e 'const f = JSON.parse(require(\"fs\").readFileSync(0, \"utf8\")); const w = require(\"fs\").writeFileSync; w(\"/home/agent/.claude.json\", f.claude); w(\"/home/agent/.codex/config.toml\", f.codexConfig); w(\"/home/agent/.codex/auth.json\", f.codexAuth, { mode: 0o600 });'",
					"jq -e '.mcpServers | length > 0' /home/agent/.claude.json > /dev/null",
				].join(" && "),
			),
		},
		{
			name: "write the ContainerHarness daemon and its boot wrapper",
			stdin: JSON.stringify({ boot: files.boot, skills: files.skills }),
			command: sh(
				[
					"node -e 'const f = JSON.parse(require(\"fs\").readFileSync(0, \"utf8\")); const w = require(\"fs\").writeFileSync; w(\"/opt/harness/daemon.mjs\", f.boot); w(\"/opt/harness/box-skills.mjs\", f.skills);'",
					"cd /tmp",
					`npm pack --silent agents@${PINS.agents} > /dev/null`,
					`tar -xzf agents-${PINS.agents}.tgz package/dist/harness/container/index.js`,
					`node -e '${DAEMON_EXTRACT}' package/dist/harness/container/index.js > /opt/harness/harness-daemon.mjs`,
					`rm -rf package agents-${PINS.agents}.tgz`,
					"node --check /opt/harness/daemon.mjs && node --check /opt/harness/box-skills.mjs && node --check /opt/harness/harness-daemon.mjs",
					"touch /opt/harness/ready",
				].join(" && "),
			),
		},
		{
			name: "hand the agent its home and clear caches",
			command: sh(
				"chown -R 10001:10001 /home/agent && rm -rf /root/.npm /root/.cache/uv /root/.cache/node-gyp /tmp/* /var/lib/apt/lists/*",
			),
		},
	];
}

export function newestSnapshot(stored) {
	const built = [...stored]
		.filter(([, record]) => record?.id)
		.map(([name, record]) => ({ ...record, key: record.key ?? name.slice(name.indexOf(":") + 1) }));
	built.sort((a, b) => String(b.builtAt ?? "").localeCompare(String(a.builtAt ?? "")));
	return built[0] ?? null;
}

export async function recipeKey(steps) {
	const text = JSON.stringify({
		image: BASE_IMAGE,
		steps: steps.map((step) => [step.user ?? "root", step.secret ? "secret" : "", ...step.command, step.stdin ?? ""]),
	});
	const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
	return [...new Uint8Array(digest)]
		.slice(0, 16)
		.map((byte) => byte.toString(16).padStart(2, "0"))
		.join("");
}
