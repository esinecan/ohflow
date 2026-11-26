import { createPiTools } from "@cloudflare/computer/tools/pi-ai";
import { BOX_AGENTS } from "./snapshot.mjs";

export const REPO_DIR = "/workspace/repo";
export const OUT_DIR = "/workspace/out";
const SHELL_BACKEND = "container-shell";
const REPLAY_SAFE = new Set(["read", "ls", "find", "grep", "write", "delete"]);
export const BRANCH = /^ohflow\/[\w.\/-]+$/;

export const WORKSPACE_SECTION = {
	key: "workspace",
	tag: false,
	render: () =>
		[
			"You work in the box, a Debian Linux container started from the default snapshot. It has no general Internet access: outbound HTTPS reaches only the hosts its MCP servers need, through the Worker. The box rules below list its programs.",
			`When ${REPO_DIR} already holds a clone, it is your task's repository, checked out on your task's branch: work there, record your work with git_commit, and do not clone again or switch branches. The branch is pushed for you when you finish.`,
			`Otherwise clone the repository with git_clone; it lands in ${REPO_DIR}. Create your branch with git_branch before you change files. Branch names start with ohflow/.`,
			"Use read, write and edit for files, and exec for commands such as tests.",
			"Record your work with git_commit and publish it with git_push. Nothing else reaches GitHub.",
		].join("\n"),
};

export const BOX_SECTION = {
	key: "box",
	tag: false,
	render: () => BOX_AGENTS,
};

function text(message, isError = false) {
	return { output: [{ type: "text", text: message }], isError };
}

function guarded(execute) {
	return async (args, api, context) => {
		try {
			return await execute(args, api, context);
		} catch (error) {
			return text(String(error?.message ?? error), true);
		}
	};
}

export function createWorkspaceTools(workspace) {
	const { tools, execute } = createPiTools({
		workspace,
		shell: {
			defaultBackend: SHELL_BACKEND,
			backends: {
				[SHELL_BACKEND]: {
					description: `Bash in the box, a Debian Linux container with the programs of the default snapshot, without general Internet access. The repository is at ${REPO_DIR}.`,
				},
			},
		},
	});
	return tools.map((tool) => ({
		name: tool.name,
		description: tool.description,
		parameters: tool.parameters,
		...(tool.constrainedSampling ? { constrainedSampling: tool.constrainedSampling } : {}),
		replay: REPLAY_SAFE.has(tool.name) ? "safe" : "unsafe",
		async execute(args, api, context) {
			const { content, isError } = await execute(
				{ id: api.callId, name: tool.name, arguments: args },
				{ abortSignal: context.abortSignal },
			);
			return { output: content, isError };
		},
	}));
}

const REPO_ANSWERS = new Map();
const REPO_ANSWER_MS = 60_000;

export async function allowedRepo(env, url) {
	const match = /^(?:https:\/\/github\.com\/|git@github\.com:|ssh:\/\/git@github\.com\/)([\w.-]+\/[\w.-]+?)(?:\.git)?\/?$/.exec(url ?? "");
	if (!match) return { error: `${url} is not a GitHub repository URL` };
	const repo = match[1];
	const owner = (env.GIT_OWNER ?? "").toLowerCase();
	if (!owner || repo.split("/")[0].toLowerCase() !== owner) return { error: `${repo} is not owned by ${env.GIT_OWNER ?? "the GIT_OWNER var, which is unset"}` };
	if (!env.GITHUB_TOKEN) return { error: "The Worker has no GITHUB_TOKEN." };
	const key = repo.toLowerCase();
	const cached = REPO_ANSWERS.get(key);
	if (cached && cached.until > Date.now()) return cached.answer;
	const response = await fetch(`https://api.github.com/repos/${repo}`, {
		headers: { authorization: `Bearer ${env.GITHUB_TOKEN}`, accept: "application/vnd.github+json", "user-agent": "pi-cloud" },
	});
	let answer;
	if (response.status === 404) answer = { error: `${repo} is not reachable with the Worker's GitHub token; add it to the token's repository access` };
	else if (!response.ok) return { error: `GitHub answered ${response.status} for ${repo}` };
	else {
		const data = await response.json();
		answer = data.private ? { repo: data.full_name } : { error: `${repo} is public; a cloud step clones private repositories only` };
	}
	REPO_ANSWERS.set(key, { answer, until: Date.now() + REPO_ANSWER_MS });
	return answer;
}

const PUSH_PREFIX = "refs/heads/ohflow/";

export function pushedRefs(bytes) {
	const decoder = new TextDecoder();
	const refs = [];
	let at = 0;
	while (at + 4 <= bytes.length) {
		const size = Number.parseInt(decoder.decode(bytes.subarray(at, at + 4)), 16);
		if (Number.isNaN(size)) return { error: "the push request is not in pkt-line form" };
		if (size === 0) return { refs };
		if (size < 4 || at + size > bytes.length) return { error: "the push request holds a broken pkt-line" };
		const line = decoder.decode(bytes.subarray(at + 4, at + size)).split("\0")[0].replace(/\n$/, "");
		at += size;
		if (line.startsWith("shallow ")) continue;
		const parts = line.split(" ");
		if (parts.length !== 3) return { error: `the push request holds an unknown command ${JSON.stringify(line.slice(0, 80))}` };
		refs.push(parts[2]);
	}
	return { refs };
}

export function refusedPush(refs) {
	return refs.filter((ref) => !ref.startsWith(PUSH_PREFIX));
}

export function githubAuth(env) {
	return { Authorization: `Basic ${btoa(`x-access-token:${env.GITHUB_TOKEN}`)}` };
}

export async function exists(workspace, path) {
	return workspace.fs.stat(path).then(
		() => true,
		() => false,
	);
}

export function createGitTools(workspace, env) {
	return [
		{
			name: "git_clone",
			description: `Clone an allowed GitHub repository (https://github.com/<owner>/<repo>) into ${REPO_DIR}.`,
			parameters: {
				type: "object",
				properties: { url: { type: "string" }, ref: { type: "string" } },
				required: ["url"],
			},
			replay: "safe",
			execute: guarded(async ({ url, ref }) => {
				const { repo, error } = await allowedRepo(env, url);
				if (error) return text(error, true);
				if (await exists(workspace, `${REPO_DIR}/.git`)) return text(`${REPO_DIR} already holds a clone.`);
				await workspace.git.clone({
					url: `https://github.com/${repo}.git`,
					dir: REPO_DIR,
					depth: 50,
					headers: githubAuth(env),
					...(ref ? { ref } : {}),
				});
				return text(`Cloned ${repo} into ${REPO_DIR}.`);
			}),
		},
		{
			name: "git_branch",
			description: "Create a branch whose name starts with ohflow/ and check it out, or check it out if it exists.",
			parameters: { type: "object", properties: { name: { type: "string" } }, required: ["name"] },
			replay: "safe",
			execute: guarded(async ({ name }) => {
				if (!BRANCH.test(name ?? "")) return text("A branch name must start with ohflow/.", true);
				const branches = await workspace.git.branchList({ dir: REPO_DIR });
				if (!branches.includes(name)) await workspace.git.branch({ dir: REPO_DIR, name });
				await workspace.git.checkout({ dir: REPO_DIR, ref: name });
				return text(`On branch ${name}.`);
			}),
		},
		{
			name: "git_commit",
			description: "Stage every change in the repository and commit it with the given message.",
			parameters: { type: "object", properties: { message: { type: "string" } }, required: ["message"] },
			replay: "unsafe",
			execute: guarded(async ({ message }) => {
				const branch = await workspace.git.currentBranch({ dir: REPO_DIR });
				if (!BRANCH.test(branch ?? "")) return text("Commit only on an ohflow/ branch; run git_branch first.", true);
				await workspace.git.add({ dir: REPO_DIR, paths: ["."], all: true });
				const { oid } = await workspace.git.commit({ dir: REPO_DIR, message });
				return text(`Committed ${oid.slice(0, 7)} on ${branch}.`);
			}),
		},
		{
			name: "git_push",
			description: "Push the current ohflow/ branch to origin. It never force-pushes.",
			parameters: { type: "object", properties: {} },
			replay: "safe",
			execute: guarded(async () => {
				if (!env.GITHUB_TOKEN) return text("The Worker has no GITHUB_TOKEN.", true);
				const branch = await workspace.git.currentBranch({ dir: REPO_DIR });
				if (!BRANCH.test(branch ?? "")) return text("Push only an ohflow/ branch.", true);
				const result = await workspace.git.push({ dir: REPO_DIR, remote: "origin", ref: branch, headers: githubAuth(env) });
				if (!result.ok) return text(`Push failed: ${result.error ?? JSON.stringify(result.refs)}`, true);
				return text(`Pushed ${branch}.`);
			}),
		},
	];
}
