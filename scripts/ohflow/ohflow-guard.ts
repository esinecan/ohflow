// Small pi extension that enforces the attempt's in-flight safety boundaries.
import path from "node:path";
import fs from "node:fs";

function parseWriteScope() {
  try {
    const value = JSON.parse(process.env.OHFLOW_WRITE_SCOPE || "[]");
    return Array.isArray(value) ? value.map(String) : [];
  } catch {
    return [];
  }
}

function globRegex(pattern) {
  const normalized = String(pattern).replaceAll("\\", "/");
  let source = "";
  for (let index = 0; index < normalized.length; index += 1) {
    const char = normalized[index];
    if (char === "*") {
      source += ".*";
    } else if (char === "?") {
      source += ".";
    } else if (char === "[") {
      let end = index + 1;
      if (normalized[end] === "!") end += 1;
      if (normalized[end] === "]") end += 1;
      while (end < normalized.length && normalized[end] !== "]") end += 1;
      if (end >= normalized.length) {
        source += "\\[";
      } else {
        let body = normalized.slice(index + 1, end);
        let negate = "";
        if (body.startsWith("!")) {
          negate = "^";
          body = body.slice(1);
        } else if (body.startsWith("^")) {
          body = `\\${body}`;
        }
        body = body.replaceAll("\\", "\\\\");
        source += `[${negate}${body}]`;
        index = end;
      }
    } else {
      source += char.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }
  }
  return new RegExp(`^${source}$`);
}

function resolvedThroughExistingParents(target) {
  const missing = [];
  let cursor = path.resolve(target);
  while (!fs.existsSync(cursor)) {
    const parent = path.dirname(cursor);
    if (parent === cursor) break;
    missing.unshift(path.basename(cursor));
    cursor = parent;
  }
  const real = fs.realpathSync.native(cursor);
  return path.resolve(real, ...missing);
}

function mayWrite(inputPath, workspace, writeScope) {
  const attemptDir = process.env.OHFLOW_ATTEMPT_DIR;
  if (attemptDir && inputPath) {
    const named = path.resolve(attemptDir, "handover.md");
    const target = path.resolve(workspace, String(inputPath));
    if (target === named && resolvedThroughExistingParents(target) === named) return true;
  }
  const root = fs.realpathSync.native(path.resolve(workspace));
  const absolute = resolvedThroughExistingParents(
    path.resolve(root, String(inputPath || "")));
  const relative = path.relative(root, absolute).replaceAll("\\", "/");
  if (!relative || relative === ".." || relative.startsWith("../") || path.isAbsolute(relative)) {
    return false;
  }
  return writeScope.some((pattern) => globRegex(pattern).test(relative));
}

function recordCommandTimeCap(requested, applied) {
  const logPath = process.env.OHFLOW_COMMAND_TIME_CAP_LOG;
  if (!logPath) return;
  let context = {};
  try {
    const parsed = JSON.parse(process.env.OHFLOW_COMMAND_TIME_CAP_CONTEXT || "{}");
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) context = parsed;
  } catch {
    context = {};
  }
  fs.mkdirSync(path.dirname(logPath), { recursive: true });
  fs.appendFileSync(
    logPath, `${JSON.stringify({ requested, applied, ...context })}\n`, "utf8");
}

function readGrant() {
  const attemptDir = process.env.OHFLOW_ATTEMPT_DIR;
  if (!attemptDir) return null;
  try {
    const grant = JSON.parse(
      fs.readFileSync(path.join(attemptDir, "budget-grant.json"), "utf8"));
    const tokens = Number(grant?.grant_tokens);
    return Number.isFinite(tokens) ? { tokens, final: grant.final === true } : null;
  } catch {
    return null;
  }
}

function messageTokens(usage) {
  if (!usage || typeof usage !== "object") return 0;
  return ["input", "output", "cacheRead", "cacheWrite"]
    .map((key) => Number(usage[key]))
    .filter((value) => Number.isFinite(value) && value > 0)
    .reduce((sum, value) => sum + value, 0);
}

function recordBudgetStop(used, grant) {
  const attemptDir = process.env.OHFLOW_ATTEMPT_DIR;
  if (!attemptDir) return;
  fs.writeFileSync(
    path.join(attemptDir, "budget-stop.json"),
    `${JSON.stringify({ used_tokens: used, grant_tokens: grant.tokens, final: grant.final })}\n`,
    "utf8");
}

const BUDGET_WAIT_MS = 30000;

export default function ohflowGuard(pi) {
  process.env.GIT_PAGER = "cat";
  const workspace = process.env.OHFLOW_WORKSPACE || process.cwd();
  const writeScope = parseWriteScope();
  const configured = Number(process.env.OHFLOW_BASH_TIMEOUT_S || "300");
  const bashCap = Number.isFinite(configured) && configured > 0 ? configured : 300;
  let used = 0;

  pi.on("message_end", async (event) => {
    if (event.message?.role === "assistant") used += messageTokens(event.message.usage);
    return undefined;
  });

  pi.on("context", async (event, ctx) => {
    let grant = readGrant();
    if (!grant) return undefined;
    const deadline = Date.now() + BUDGET_WAIT_MS;
    while (used >= grant.tokens) {
      if (grant.final || Date.now() >= deadline) {
        recordBudgetStop(used, grant);
        ctx.abort();
        ctx.shutdown();
        return undefined;
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
      grant = readGrant() || grant;
    }
    return undefined;
  });

  pi.on("tool_call", async (event) => {
    if (event.toolName === "edit" || event.toolName === "write") {
      if (!mayWrite(event.input?.path, workspace, writeScope)) {
        return {
          block: true,
          reason: `${event.toolName} path is outside this step's write scope`,
        };
      }
    }
    if (event.toolName === "bash") {
      // This is a duration cap, not a bash sandbox. Repository gates still
      // judge writes performed by shell commands after the agent exits.
      const requested = Number(event.input?.timeout);
      event.input.timeout = Number.isFinite(requested) && requested > 0
        ? Math.min(requested, bashCap)
        : bashCap;
      recordCommandTimeCap(Number.isFinite(requested) ? requested : null,
                       event.input.timeout);
    }
    return undefined;
  });
}
