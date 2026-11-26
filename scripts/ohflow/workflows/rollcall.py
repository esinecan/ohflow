"""The roll call: seven scenarios of one trivial task, as ohflow workflows.

Every agent writes who it is, commits that file, and ends with a JSON report.
The harness executor records what the harness announced, and `rollcall_matches` fails a
report that names a tool or server the harness never announced. The matrix
runner `ohflow rollcall` runs these workflows; `ohflow.rollcall` owns the matrices.
How to run and read it: `CONTRIBUTING.md`, "Testing with live agents".

Scenarios, chosen with `--args scenario=<name>`:

- `single`    one gated agent on one harness executor.
- `fanout`    one agent per harness executor and per `count`, each in its own worktree.
- `relay`     agents in series; each appends to one shared `ROLLCALL.md`.
- `merge`     `fanout`, one merge per agent into `integration`, then one
              consolidator that writes `ROLLCALL.md` as a table.
- `retry`     the first attempt fails a gate on purpose. The failure line
              of its hidden `file_contains` check carries the wanted text.
              The retry reads that text in its position block.
- `review`    an agent on one harness executor, then a reviewer on another that ends with
              a `VERDICT:` line.
- `campaign`  the milestone workflow of a one-milestone campaign. Its first brief
              misses a required line, and a judge must repair the brief.
- `silent`    `single`, but the agent first runs one command that prints nothing
              for twice the stall limit (plus 10 s). The agent must survive it:
              an open tool call suspends the stall clock. The stall limit is
              `SILENT_STALL_S` unless `stall_timeout_s` is given.

`r0`, `r1` and `r2` are aliases of `fanout`, `relay` and `merge`.

Arguments: `repo` (required), `scenario`, `harness_executors` (comma list), `count` (agents
per harness executor), `consolidator`, `reviewer`, `judge` (each a harness executor), `agent_profile`
(`hermetic` for claude and codex), `carry_context`, `durable_box` (the box a durable
agent runs on, `local` or an ssh host alias; `durable.box` in the ohflow settings by default), `config` (a JSON file of
model overrides), `base`, `prefix`, `wt_root`, `execution_timeout_s`,
`stall_timeout_s` (replaces the per harness executor `STALL_S` table; codex gets 600 s
and `pi` and `claude` get 180 s),
`max_iterations` (default 30: an agent that looks up its own facts needs more
than the 5 to 9 calls of an agent that is told where they come from),
`max_parallel`.

    python -m ohflow.cli validate --workflow <this file> \\
        --args repo=<scratch repo> --args scenario=merge --args harness_executors=pi,claude
"""

import json
from dataclasses import dataclass
from pathlib import Path
from dataclasses import replace

# Absolute, like every other workflow module: `load_workflow` imports a workflow by file
# path, so the module has no parent package.
from ohflow import settings
from ohflow.harness_executors import CAP_STALL, harness_executor_info
from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow,
                             RetryPolicy, Step, ToolPolicy, AgentSpec,
                             WorktreeSpec, clean_commit_checks, house_checks,
                             HandoverSpec)

SCHEMA_PATH = (Path(__file__).resolve().parents[3] / "references" / "examples" /
               "rollcall" / "rollcall.schema.json")
ROLLCALL_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

ZAI_URL = "https://api.z.ai/api/coding/paas/v4"
ZAI_KEY = "ZAI_CODING_CN_API_KEY"

#: The cheap route of each harness executor. `--config` overrides any of them.
MODELS = {
    "pi": ModelConfig(model="zai/glm-5.3-flash", base_url=ZAI_URL,
                      api_key_env=ZAI_KEY, params={"thinking": "low"}),
    "claude": ModelConfig(model="claude-haiku-4-5-20251001", base_url="",
                          api_key_env=""),
    # The largest-quota model on the Plus seat.
    "codex": ModelConfig(model="gpt-5.6-luna", base_url="", api_key_env="",
                         params={"reasoning_effort": "low"}),
    # The durable host holds the Z.AI key on its own box, so no key variable.
    "durable": ModelConfig(model="zai/glm-5.3-flash", base_url="",
                           api_key_env="", params={"thinking": "low"}),
    # The pi-cloud Worker holds the Z.AI key in its own environment, so no
    # key variable here either; its preflight checks PI_CLOUD_TOKEN instead.
    "pi-cloud": ModelConfig(model="zai/glm-5.3-flash", base_url="",
                            api_key_env="", params={"thinking": "low"}),
    # The Worker holds the subscription logins, so no key variable.
    "claude-cloud": ModelConfig(model="claude-haiku-4-5-20251001", base_url="",
                                api_key_env=""),
    "codex-cloud": ModelConfig(model="gpt-5.6-luna", base_url="", api_key_env=""),
}
ORDER = ("pi", "claude", "codex")

#: Seconds of silence that stop an agent, per harness executor. Codex reasons for minutes
#: without an event, and 180 s killed it in the first live matrix. The workflow
#: argument `stall_timeout_s` replaces the table for every harness executor that takes one.
STALL_S = {"pi": 180, "claude": 180, "codex": 600, "durable": 180,
           "pi-cloud": 180, "claude-cloud": 600, "codex-cloud": 600}

SCENARIOS = ("single", "fanout", "relay", "merge", "retry", "review", "campaign",
             "silent")
ALIASES = {"r0": "fanout", "r1": "relay", "r2": "merge"}

#: The profile that only claude and codex take among the roll-call harness executors.
HERMETIC_HARNESS_EXECUTORS = ("claude", "codex")

PRESENT = r'"status"\s*:\s*"PRESENT"'
VERDICT = r"^VERDICT:\s*(PASS|FAIL)\s*$"

#: The retry scenario's gate wants this text in the agent's file. The brief does
#: not name it. Only the failure line of the first attempt does.
RETRY_TOKEN = "ROLLCALL-RETRY-5K2M"

#: The silent scenario: the stall limit, and the line its command prints only
#: when it ends. The agent copies the line into its file, so the gate proves the
#: agent waited for the whole silent command.
SILENT_STALL_S = 45
SILENT_TOKEN = "SILENT-DONE-8R3V"

SILENT_STEP = """0. Before step 1, run this exact command once, in one tool call, and wait
   until it finishes. It prints nothing for about {secs} seconds, then one line.
   Do not run it in the background and do not interrupt it:

       python -c "import time; time.sleep({secs}); print('{token}')"

   If the shell answers that `python` is not found, run the same command with
   `python3` in place of `python`.

   In step 1, add the line it printed as the last line of your file.

"""

#: The campaign scenario's gate wants this line. The first brief omits it.
CAMPAIGN_LINE = "Campaign-Token: M5-ROLLCALL"

REPORT = """# Your report

The `harness_executor` value is already filled in by the run: copy it unchanged.
Fill each other value from your own system prompt, your tool list and your
working directory. Write `unknown` for a value they do not show. Do not search
the disk, the environment or the run directory for it.

End your last message with one fenced json block and nothing after it. The
block opens with a line of three backticks and the word `json`. It closes with a
line of three backticks. A bare JSON object without those two lines fails the
gate.

```json
{{"harness_executor": "{harness_executor}", "status": "PRESENT", "harness": "<harness name and version>",
 "model": "<your model>", "tools": ["<each built-in tool name>"],
 "mcp_servers": ["<each MCP server name>"],
 "cannot": "<one sentence: what you cannot do in this signed-in harness>"}}
```

`tools` holds your built-in tools only, each name exactly as your harness
spells it. Leave every MCP tool out of `tools`; name its server once in
`mcp_servers` instead. Copy each server name from your tool list: for a tool
named `mcp__<server>__<tool>` or `mcp__<server>.<tool>`, the server name is the
`<server>` part, exactly, without the `mcp__` prefix.
Write no wildcard and no pattern. List a tool or a server only when your own
tool list shows it. Do not guess and do not compose names.
"""

ENTRY = """- Harness: your harness name and version
- Model: your model
- Working directory: the absolute path you are working in
- Tools: the names of your built-in tools
- MCP servers: the names of the MCP servers you can see
- Cannot: one sentence on what you cannot do in this signed-in harness"""

CLEAN = ("Author it clean: no `Co-Authored-By` line naming a model, no "
         "generated-with footer.")

SOLO_BRIEF = """# Task

You are one agent in a roll call. Your harness executor is `{harness_executor}`. Your agent id is
`{sid}`. Report for duty.

1. Create the file `rollcall/{sid}.md`. Its first line is `# {sid}`. Then write
   these lines, filled in:

{entry}

2. Commit only that file. The commit message is `rollcall: {sid}`. {clean}
{more}
Change no other file.

""" + REPORT

RETRY_MORE = """3. The position block above may list a failure from an earlier attempt.
   If it does, read it, fix exactly that in the same file, and commit again.
"""

RELAY_BRIEF = """# Task

You are one agent in a relay roll call. Your harness executor is `{harness_executor}`. Your agent id
is `{sid}`. You are agent {n} of {total}. The position block above says who
went before you.

1. Open `ROLLCALL.md` in the root of this worktree. {create}
2. Append one section at the end of the file. Its heading line is `## {sid}`.
   Under it, write these lines, filled in:

{entry}
- Previous: {previous}

3. Do not change, reorder or delete any line that is already in the file.
4. Commit only `ROLLCALL.md`. The commit message is `rollcall relay: {sid}`.
   {clean}

""" + REPORT

CONSOLIDATE_BRIEF = """# Task

You consolidate a roll call. The files `rollcall/<id>.md` in this worktree
were written by {count} agents: {ids}.

1. Read every `rollcall/*.md` file.
2. Write `ROLLCALL.md` in the root of this worktree. Its first line is
   `# Roll call`. Then one markdown table with this header row:

   | agent | harness | model | tools | mcp servers |

   and one row per agent, in the order {ids}. The `agent` cell holds only the
   agent id. The `tools` and `mcp servers` cells hold a count.
3. Commit only `ROLLCALL.md`. The commit message is `rollcall: consolidate`.
   {clean}

""" + REPORT

REVIEW_BRIEF = """# Task

You review one roll-call file. Another agent wrote `rollcall/{sid}.md` in this
worktree and committed it.

1. Read `rollcall/{sid}.md`. Change no file and make no commit.
2. Check two facts. The first line is `# {sid}`. The file has a Harness line, a
   Model line and a Tools line.
3. End your reply with exactly one line, and nothing after it:
   `VERDICT: PASS` when both facts hold, or `VERDICT: FAIL` when one does not.
"""

MILESTONE_SPEC = f"""# Milestone m1: one agent reports for duty

The product workflow runs one agent. It writes `rollcall/{{sid}}.md` and commits.

The gate needs the line `{CAMPAIGN_LINE}` in that file. The agent learns that
line only from `briefs/impl.md`.

Judge the run:

- The gate failed on that line, and `briefs/impl.md` does not tell the agent to
  write it. Return REVISE. Edit `briefs/impl.md` only: add one numbered step that
  tells the agent to add the line `{CAMPAIGN_LINE}` to its file before it commits.
  Change no other file.
- The gate passed and the file holds the line. Return PASS.
- Anything else: return ESCALATE and say why.
"""

CHARTER = """# Roll-call campaign

One milestone proves the campaign loop: run, judge, revise, rerun, land.
Keep every change small. Touch only the milestone directory.
"""

MILESTONE_WORKFLOW = '''"""The m1 workflow of the roll-call campaign: it reads its brief from briefs/impl.md."""
from pathlib import Path

from ohflow.workflows.rollcall import build_milestone


def build(args):
    brief = (Path(__file__).resolve().parent / "briefs" /
             "impl.md").read_text(encoding="utf-8")
    return build_milestone(args, brief)
'''


# ------------------------------------------------------------------ arguments


def _text_list(value) -> tuple[str, ...]:
    return tuple(x.strip() for x in str(value).split(",") if x.strip())


def _flag(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _count(name: str, value, default: int) -> int:
    try:
        n = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        raise ValueError(f"roll-call {name} must be a whole number, got "
                         f"{value!r}") from None
    if n < 1:
        raise ValueError(f"roll-call {name} must be 1 or more, got {n}")
    return n


def load_config(path) -> tuple[str, dict[str, ModelConfig]]:
    """`(name, models)`: the table `MODELS` with the overrides of a JSON file.

    The file is `{"name": "...", "harness_executors": {"<harness_executor>": {"model": ..., "base_url":
    ..., "api_key_env": ..., "params": {...}, "extra_body": {...}}}}`. A key
    that is left out keeps the table's value.
    """
    models = dict(MODELS)
    if not path:
        return "default", models
    try:
        data = json.loads(Path(str(path)).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"roll-call config {str(path)!r} cannot be read: {e}") from None
    if not isinstance(data, dict) or not isinstance(data.get("harness_executors", {}), dict):
        raise ValueError(f"roll-call config {str(path)!r} must be an object "
                         f"with a 'harness_executors' object")
    allowed = {"model", "base_url", "api_key_env", "params", "extra_body"}
    for harness_executor, over in data.get("harness_executors", {}).items():
        if harness_executor not in MODELS:
            raise ValueError(f"roll-call config names unknown harness executor {harness_executor!r}; "
                             f"known: {list(MODELS)}")
        if not isinstance(over, dict) or set(over) - allowed:
            raise ValueError(f"roll-call config harness executor {harness_executor!r} may set only "
                             f"{sorted(allowed)}")
        base = models[harness_executor]
        models[harness_executor] = ModelConfig(
            model=over.get("model", base.model),
            base_url=over.get("base_url", base.base_url),
            api_key_env=over.get("api_key_env", base.api_key_env),
            params=over.get("params", base.params),
            extra_body=over.get("extra_body", base.extra_body))
    return str(data.get("name") or Path(str(path)).stem), models


@dataclass(frozen=True)
class Spec:
    """The arguments of one roll-call workflow, checked."""
    scenario: str              # the name the caller gave
    kind: str                  # one of SCENARIOS
    repo: Path
    harness_executors: tuple[str, ...]
    count: int
    consolidator: str
    reviewer: str
    judge: str
    profile: str | None
    carry_context: bool
    durable_box: str
    base: str
    prefix: str
    wt_root: Path
    wall: int
    stall: int | None          # the caller's override; None takes STALL_S
    max_iter: int
    max_parallel: int
    models: dict

    def stall_for(self, harness_executor: str) -> int | None:
        """The stall limit of a step on `harness_executor`; None when the harness executor takes none."""
        if not harness_executor_info(harness_executor).has(CAP_STALL):
            return None
        return self.stall if self.stall is not None else STALL_S[harness_executor]

    @property
    def agents(self) -> list[tuple[str, str]]:
        """`(harness executor, step id)` for every agent, harness executor by harness executor."""
        return [(harness_executor, f"{harness_executor}-{k}") for harness_executor in self.harness_executors
                for k in range(1, self.count + 1)]

    @property
    def harness_executors_needed(self) -> tuple[str, ...]:
        """Every harness executor the workflow starts an agent on, in a stable order."""
        out = list(self.harness_executors)
        extra = {"merge": self.consolidator, "review": self.reviewer,
                 "campaign": self.judge}.get(self.kind)
        if extra and extra not in out:
            out.append(extra)
        return tuple(out)


def normalize(args) -> Spec:
    """Check the arguments and fill the defaults. Raises ValueError."""
    repo = Path(args["repo"])
    given = str(args.get("scenario", "fanout"))
    kind = ALIASES.get(given, given)
    if kind not in SCENARIOS:
        raise ValueError(f"unknown roll-call scenario {given!r}; use one of "
                         f"{list(SCENARIOS)} (aliases: "
                         f"{', '.join(f'{a}={s}' for a, s in ALIASES.items())})")
    harness_executors = _text_list(args.get("harness_executors") or ",".join(ORDER))
    if not harness_executors:
        raise ValueError("roll-call harness executors is empty; name one or more of "
                         f"{list(MODELS)}")
    unknown = [x for x in (*harness_executors,) if x not in MODELS]
    if unknown:
        raise ValueError(f"unknown roll-call harness executors {unknown}; known: {list(MODELS)}")
    if len(set(harness_executors)) != len(harness_executors):
        raise ValueError(f"roll-call harness executors lists a harness executor twice: {list(harness_executors)}; "
                         f"use count for more agents on one harness executor")
    count = _count("count", args.get("count"), 1)

    reviewer_arg = str(args.get("reviewer") or "")
    if kind == "review" and len(harness_executors) == 2 and not reviewer_arg:
        reviewer_arg, harness_executors = harness_executors[1], harness_executors[:1]
    if kind in ("single", "retry", "review", "campaign", "silent") and len(harness_executors) != 1:
        raise ValueError(f"roll-call scenario {given!r} runs on exactly one "
                         f"harness executor, got {list(harness_executors)}")
    if kind in ("single", "retry", "review", "campaign", "silent") and count != 1:
        raise ValueError(f"roll-call scenario {given!r} takes count 1; use "
                         f"fanout for more agents")

    consolidator = str(args.get("consolidator") or
                       ("claude" if "claude" in harness_executors else harness_executors[0]))
    reviewer = reviewer_arg or ("claude" if harness_executors[0] != "claude" else "pi")
    judge = str(args.get("judge") or "claude")
    for role, harness_executor in (("consolidator", consolidator), ("reviewer", reviewer),
                                   ("judge", judge)):
        if harness_executor not in MODELS:
            raise ValueError(f"roll-call {role} {harness_executor!r} is not a harness executor; "
                             f"known: {list(MODELS)}")

    profile = str(args.get("agent_profile") or "").strip() or None
    if profile in ("default", "usual"):
        profile = None
    if profile not in (None, "hermetic"):
        raise ValueError(f"roll-call agent_profile must be 'hermetic' or empty, got "
                         f"{profile!r}")
    durable_box = (str(args.get("durable_box") or "").strip()
                   or str(settings.get("durable.box", "")))
    _name, models = load_config(args.get("config"))
    base = str(args.get("base", "main"))
    return Spec(
        scenario=given, kind=kind, repo=repo, harness_executors=harness_executors, count=count,
        consolidator=consolidator, reviewer=reviewer, judge=judge,
        profile=profile, carry_context=_flag(args.get("carry_context", False)),
        durable_box=durable_box, base=base, prefix=str(args.get("prefix", "rollcall")),
        wt_root=Path(args.get("wt_root", str(repo.parent / f"{repo.name}-rollcall-wt"))),
        wall=int(args.get("execution_timeout_s", 600)),
        stall=(int(args["stall_timeout_s"])
               if args.get("stall_timeout_s") not in (None, "") else None),
        max_iter=int(args.get("max_iterations", 30)),
        max_parallel=int(args.get("max_parallel", 3)), models=models)


def needed_harness_executors(args) -> tuple[str, ...]:
    """The harness executors a test case with these arguments starts agents on."""
    return normalize(args).harness_executors_needed


def judge_spec(args) -> AgentSpec:
    """The judge of the campaign scenario, on the harness executor the arguments name."""
    spec = normalize(args)
    return _agent(spec, spec.judge, "milestone-judge", "")


# ----------------------------------------------------------------------- build


def _agent(spec: Spec, harness_executor: str, role: str, brief: str) -> AgentSpec:
    tools = (ToolPolicy(only=("terminal", "file_editor")) if harness_executor == "pi"
             else ToolPolicy())
    profile = "hermetic" if spec.profile and harness_executor in HERMETIC_HARNESS_EXECUTORS else None
    box = spec.durable_box if harness_executor == "durable" else None
    return AgentSpec(role=role, brief=brief, model=spec.models[harness_executor],
                     harness_executor=harness_executor, tools=tools, max_iterations=spec.max_iter,
                     agent_profile=profile, box=box)


def _step(spec: Spec, sid: str, harness_executor: str, brief: str, *, worktree: str,
          write_scope: tuple[str, ...], checks: tuple[CheckSpec, ...], objective: str,
          depends_on: tuple[str, ...] = (), retry: RetryPolicy | None = None,
          schema: dict | None = ROLLCALL_SCHEMA, role: str | None = None) -> Step:
    return Step(id=sid, kind="agent", worktree=worktree, write_scope=write_scope,
                depends_on=depends_on, execution_timeout_s=spec.wall,
                stall_timeout_s=spec.stall_for(harness_executor), schema=schema,
                objective=objective,
                retry=retry or RetryPolicy(),
                agent=_agent(spec, harness_executor, role or f"rollcall-{harness_executor}", brief),
                gate=GateSpec(checks=checks))


def _report_checks(write_scope: str, harness_executor: str, *, since: str = "base",
                   extra: tuple[CheckSpec, ...] = ()) -> tuple[CheckSpec, ...]:
    return (clean_commit_checks((write_scope,), since=since, marker=PRESENT) +
            (CheckSpec("schema_valid"),
             CheckSpec("rollcall_matches", {"harness_executor": harness_executor})) + extra)


def _wt(spec: Spec, name: str) -> WorktreeSpec:
    return WorktreeSpec(name=name, path=spec.wt_root / name,
                        branch=f"{spec.prefix}-{name}", base=spec.base,
                        node_modules_mode="none")


def _solo(spec: Spec, harness_executor: str, sid: str, *, more: str = "",
          extra: tuple[CheckSpec, ...] = (), since: str = "base",
          retry: RetryPolicy | None = None, brief: str | None = None) -> Step:
    write_scope = f"rollcall/{sid}.md"
    brief = brief if brief is not None else SOLO_BRIEF.format(
        harness_executor=harness_executor, sid=sid, entry=ENTRY, clean=CLEAN, more=more)
    return _step(spec, sid, harness_executor, brief, worktree=sid, write_scope=(write_scope,),
                 checks=_report_checks(write_scope, harness_executor, since=since, extra=extra),
                 objective=f"{sid} reports for duty in {write_scope}", retry=retry)


def _fanout_phase(spec: Spec) -> Phase:
    return Phase(name="Report", on_step_failure="continue", min_success="any",
                 steps=tuple(_solo(spec, harness_executor, sid)
                             for harness_executor, sid in spec.agents))


def _single(spec: Spec):
    harness_executor, sid = spec.agents[0]
    return ([_wt(spec, sid)],
            [Phase(name="Report", steps=(_solo(spec, harness_executor, sid),))])


def _fanout(spec: Spec):
    return [_wt(spec, sid) for _, sid in spec.agents], [_fanout_phase(spec)]


def _relay(spec: Spec):
    total = len(spec.agents)
    phases, previous_id = [], None
    for n, (harness_executor, sid) in enumerate(spec.agents, start=1):
        create = ("It does not exist yet: create it, with the first line "
                  "`# Roll call`." if n == 1 else
                  "It exists; earlier agents wrote their sections.")
        previous = ("none" if n == 1 else
                    "the harness name from the section directly above yours")
        brief = RELAY_BRIEF.format(harness_executor=harness_executor, sid=sid, n=n, total=total,
                                   create=create, entry=ENTRY,
                                   previous=previous, clean=CLEAN)
        token = f"RELAY-{n}-a91c7e"
        if n < total:
            brief += f"\nIn your handover's Next answer, include `Relay token: {token}`. Keep that token out of ROLLCALL.md.\n"
        if previous_id:
            brief += "\nRead the predecessor's handover in Handed to you. Add `- Previous token: <its Relay token>` to your section.\n"
        extra: tuple[CheckSpec, ...] = (
            CheckSpec("command_exit", {
                "cmd": f"test \"$(grep -c '^## ' ROLLCALL.md)\" -eq {n}"}),
            CheckSpec("command_exit", {
                "cmd": (f"git diff --numstat {spec.base}..HEAD | "
                        "awk '$2 != 0 && $2 != \"-\" {bad=1} END {exit bad}'")}),
            CheckSpec("command_exit", {
                "cmd": ("tail -n +$(grep -n '^## ' ROLLCALL.md | tail -1 | "
                        "cut -d: -f1) ROLLCALL.md | grep -q 'Previous: '")}),
        )
        if previous_id:
            extra += (CheckSpec("file_contains", {"path": "ROLLCALL.md", "text": f"Previous token: RELAY-{n-1}-a91c7e", "hidden": True}),)
        step = _step(
            spec, sid, harness_executor, brief, worktree="relay", write_scope=("ROLLCALL.md",),
            depends_on=(previous_id,) if previous_id else (),
            checks=_report_checks("ROLLCALL.md", harness_executor, since="step_start",
                                  extra=extra),
            objective=f"{sid} appends its section to the shared ROLLCALL.md")
        step = replace(step, consumes=(previous_id,) if previous_id else ())
        phases.append(Phase(name=f"Relay {n} {sid}", steps=(step,)))
        previous_id = sid
    return [_wt(spec, "relay")], phases


def _merge(spec: Spec):
    ids = [sid for _, sid in spec.agents]
    worktrees = [_wt(spec, sid) for sid in ids] + [_wt(spec, "integration")]
    merges = Phase(name="Merge", on_step_failure="continue", min_success="any",
                   steps=tuple(Step(
                       id=f"merge-{sid}", kind="merge", worktree="integration",
                       depends_on=(sid,), merge_branch=f"{spec.prefix}-{sid}",
                       merge_message=f"rollcall: merge {sid}") for sid in ids))
    rows = tuple(CheckSpec("command_exit", {
        "cmd": f"grep -qE '^[|] *{sid} *[|]' ROLLCALL.md"}) for sid in ids)
    count = CheckSpec("command_exit", {"cmd": (
        f"test \"$(grep -cE '^[|] *({'|'.join(ids)}) *[|]' ROLLCALL.md)\" "
        f"-eq {len(ids)}")})
    brief = CONSOLIDATE_BRIEF.format(count=len(ids), ids=", ".join(ids),
                                     harness_executor=spec.consolidator, clean=CLEAN)
    consolidate = Phase(name="Consolidate", steps=(_step(
        spec, "consolidate", spec.consolidator, brief, worktree="integration",
        write_scope=("ROLLCALL.md",),
        depends_on=tuple(f"merge-{sid}" for sid in ids) + tuple(ids),
        checks=_report_checks("ROLLCALL.md", spec.consolidator,
                              since="last_merge", extra=rows + (count,)),
        objective=(f"{spec.consolidator} writes ROLLCALL.md as one table, "
                   f"one row per agent"),
        role="rollcall-consolidate"),))
    fanout = _fanout_phase(spec)
    fanout = replace(fanout, steps=tuple(replace(s, handover=HandoverSpec(audience="consolidator")) for s in fanout.steps))
    consolidate = replace(consolidate, steps=tuple(replace(s, consumes=tuple(ids)) for s in consolidate.steps))
    return worktrees, [fanout, merges, consolidate]


def _retry(spec: Spec):
    harness_executor, sid = spec.agents[0]
    write_scope = f"rollcall/{sid}.md"
    wanted = CheckSpec("file_contains", {"path": write_scope, "text": RETRY_TOKEN,
                                         "hidden": True})
    step = _solo(
        spec, harness_executor, sid, more=RETRY_MORE, since="step_start", extra=(wanted,),
        retry=RetryPolicy(max=1, on=("gate:file_contains",),
                          carry_context=spec.carry_context))
    return [_wt(spec, sid)], [Phase(name="Report", steps=(step,))]


def _silent(spec: Spec):
    harness_executor, sid = spec.agents[0]
    stall = spec.stall if spec.stall is not None else SILENT_STALL_S
    secs = 2 * stall + 10
    write_scope = f"rollcall/{sid}.md"
    brief = SOLO_BRIEF.format(harness_executor=harness_executor, sid=sid, entry=ENTRY,
                              clean=CLEAN, more="")
    brief = brief.replace("1. Create the file",
                          SILENT_STEP.format(secs=secs, token=SILENT_TOKEN)
                          + "1. Create the file", 1)
    wanted = CheckSpec("file_contains", {"path": write_scope, "text": SILENT_TOKEN})
    step = _solo(spec, harness_executor, sid, extra=(wanted,), brief=brief)
    if harness_executor_info(harness_executor).has(CAP_STALL):
        step = replace(step, stall_timeout_s=stall)
    step = replace(step, objective=(f"{sid} survives a {secs} s silent command, "
                                    f"then reports in {write_scope}"))
    return [_wt(spec, sid)], [Phase(name="Report", steps=(step,))]


def _review(spec: Spec):
    harness_executor, sid = spec.agents[0]
    agent = Phase(name="Report", steps=(_solo(spec, harness_executor, sid),))
    gate = (CheckSpec("tree_clean"),
            CheckSpec("ownership", {"allowed": [], "since": "step_start"}),
            *house_checks("step_start"),
            CheckSpec("final_message_matches", {"regex": VERDICT}))
    reviewer = _step(
        spec, "reviewer", spec.reviewer, REVIEW_BRIEF.format(sid=sid),
        worktree=sid, write_scope=(), depends_on=(sid,), checks=gate, schema=None,
        objective=f"{spec.reviewer} reviews rollcall/{sid}.md and ends with a VERDICT line",
        role="rollcall-reviewer")
    return [_wt(spec, sid)], [agent, Phase(name="Review", steps=(reviewer,))]


def first_brief(spec: Spec) -> str:
    """The campaign scenario's first brief. It omits the required line."""
    harness_executor, sid = spec.agents[0]
    return SOLO_BRIEF.format(harness_executor=harness_executor, sid=sid, entry=ENTRY, clean=CLEAN,
                             more="")


def _campaign(spec: Spec, brief: str):
    harness_executor, sid = spec.agents[0]
    write_scope = f"rollcall/{sid}.md"
    wanted = CheckSpec("file_contains", {"path": write_scope, "text": CAMPAIGN_LINE,
                                         "hidden": True})
    step = _solo(spec, harness_executor, sid, extra=(wanted,), brief=brief)
    return [_wt(spec, sid)], [Phase(name="Report", steps=(step,))]


def _workflow(spec: Spec, args, name: str, worktrees, phases) -> Workflow:
    return Workflow(name=name, repo=spec.repo, base_branch=spec.base,
                    baseline_cmd=None, max_parallel=spec.max_parallel,
                    args=dict(args), worktrees=tuple(worktrees),
                    phases=tuple(phases))


_BUILDERS = {"single": _single, "fanout": _fanout, "relay": _relay,
             "merge": _merge, "retry": _retry, "review": _review,
             "silent": _silent}


def build(args) -> Workflow:
    spec = normalize(args)
    if spec.kind == "campaign":
        worktrees, phases = _campaign(spec, first_brief(spec))
    else:
        worktrees, phases = _BUILDERS[spec.kind](spec)
    return _workflow(spec, args, f"rollcall-{spec.scenario}", worktrees, phases)


def build_milestone(args, brief: str) -> Workflow:
    """The product workflow of the campaign scenario, with the brief a file holds."""
    spec = normalize({**dict(args), "scenario": "campaign"})
    worktrees, phases = _campaign(spec, brief)
    return _workflow(spec, args, "rollcall-campaign", worktrees, phases)


def campaign_files(args) -> dict[str, str]:
    """The files of the one-milestone campaign repository, by relative path."""
    spec = normalize({**dict(args), "scenario": "campaign"})
    _harness_executor, sid = spec.agents[0]
    return {
        "charter.md": CHARTER,
        "milestones/m1/spec.md": MILESTONE_SPEC.format(sid=sid),
        "milestones/m1/workflow.py": MILESTONE_WORKFLOW,
        "milestones/m1/briefs/impl.md": first_brief(spec),
    }


def output_branch_name(args) -> str:
    """The branch the campaign scenario's agent leaves its work on."""
    spec = normalize({**dict(args), "scenario": "campaign"})
    return f"{spec.prefix}-{spec.agents[0][1]}"
