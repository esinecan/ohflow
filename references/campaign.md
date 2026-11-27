# Campaign: a whole design, milestone by milestone, judged by fresh agents

A **campaign** delivers a design document end to end. It is a list of milestones. Each
milestone is one ohflow workflow run. After each run, a **judge** reads a judge packet and
returns a judge decision: PASS, REVISE or ESCALATE. On REVISE the judge has already changed the
milestone's inputs. The campaign controller commits that change and resumes the run. On PASS the
campaign's integration branch moves forward (the milestone landing) and the next milestone
starts. Nobody from the authoring session is needed at a milestone boundary.

Controller: `scripts/ohflow/campaign.py`, class `CampaignController`. Verb: `python3 -m ohflow.cli campaign ...`.
Tests: `tests/test_campaign_01_loop.py`. `ohflow construct` writes a campaign from a bundle of
milestone specs: [construct](construct.md).

## The loop

```text
              +------------------------------------------------------------------+
              |                       one milestone round                        |
              |                                                                  |
 integration  |  workflow run --> acceptance checks --> packet --> judge         |
 branch  ---> |  (controller        (charter, spec,      (fresh    (decision)    |
              |   runs them itself)  evidence, lineage)   agent)        |        |
              |        ^                                                |        |
              |        +---- resume <-- commit <-- REVISE <-------------+        |
              +------------------------------------------------------------------+
                    PASS: the integration branch fast-forwards (milestone landing)
                    ESCALATE: ESCALATION.md, stop
```

## Layout

A campaign is its own git repository, in a folder the operator chooses, such as `~/workflows/<name>/`.

```text
<name>/
  campaign.py                 build(args) -> Campaign
  charter.md                  the operator's words, verbatim, then the bar
  contracts.md                the interfaces parallel steps share; optional; the judge may not change it
  milestones/<id>/
    spec.md                   the milestone spec; the judge may not change it
    workflow.py               build(args) -> Workflow; the judge may change it
    briefs/*.md               read by workflow.py; the judge may change them
    runs/<id>/                the ohflow run directory (git-ignored)
    judge/                    git-ignored, with everything under it
    judge/rNN/packet.md       what the judge of round NN read
    judge/rNN/judge-handover.md   what the judge of round NN left for the next one
    judge/rNN/run/            the judge's own ohflow run
  campaign.jsonl              the campaign log (git-ignored, append-only)
  campaign-status.json        where the campaign is now, with the dashboard URL (git-ignored)
  .watch.<name>.json          a `campaign watch` cursor (git-ignored)
  ESCALATION.md               present only while a milestone waits for the operator (git-ignored)
```

`ohflow campaign` writes the `.gitignore` entries itself. They also cover `campaign.log`,
`campaign.pid`, `campaign.log.launch.*` and `__pycache__/`.

The judge's own run holds one agent step with no worktree, so the judge works in this repository.
Every judge revision is one git commit in this repository. The campaign log names the commit, the
round and the decision. One commit has no campaign log event: when `campaign run` starts on a
dirty tree, it first commits that tree as `campaign <name>: inputs before the run`. To find
where a bad outcome came from, read the campaign log, then `git log -p milestones/<id>/`, then
the packet of the round that approved it.

## Write the charter

The charter is the first thing every judge reads. It is the bar they judge against.

1. Paste the operator's request verbatim under `## The operator's words`. Do not paraphrase it. A judge
   three milestones later reads the words, not a summary of them.
2. Under `## The bar`, list what "ready to ship" means for this delivery. Take each item
   from his words. Example: "an architecture pass, then a smoke test after it", "the CLI
   and MCP tool policies checked", "the README, the docs and the repo-packed skills updated".
3. Under `## Decisions already made`, list what is settled and who settled it. A judge
   treats these as fixed.
4. Under `## Stop and ask`, list the decisions that belong to the operator. A judge ESCALATEs on
   these.

## Write the contracts

Two steps in one phase run in parallel, and neither sees the other's work. The contracts file
fixes the interfaces they share, so each step builds against the same names and signatures and the
branches fit at the merge.

1. Write `contracts.md` in the campaign root. `Campaign.contracts` names another path, relative
   to the root. A named file that is missing, or a path that leaves the root, fails
   `campaign validate`. A campaign without the file runs as before.
2. State each interface one step makes and another uses: function signatures, file formats,
   CLI verbs and flags, schema fields, error codes. Name the owner of each.
3. Leave out anything that only one step touches. That belongs in its brief.

The controller passes the path to every milestone workflow as the `contracts` argument, and the
workflow loader reads the file into `Workflow.contracts`. Every step's position block then
carries the path, the full text, the rule that the contracts are fixed, and the order to stop
and report in its handover when a contract is unworkable, instead of working around it. A step
without a handover reports in its final message, and the judge packet then carries each such
message under `## Step handovers`. The text is part of each step's fingerprint, so an edited
contract reruns every step. The judge packet carries the file under `## The contracts`. A step
that reports a contract unworkable is a `spec` finding and an ESCALATE.

The judge may not edit the file. After every judge run, whatever the decision, the controller
restores it and keeps the judge's edit in a git stash entry named `judge edit to <path> on
<id> rNN`. ESCALATION.md names the edit, and a REVISE that made it escalates. A PASS lands
with the file restored, although the judge packet says that an edit escalates.

## Write a milestone

- **`spec.md`** states scope and the acceptance checks. A mechanical check names a command and the
  output that means pass. A rubric check, a `- rubric:` line, names what no command decides, and
  the judge grades it. Copy the acceptance rows of the design document into it.
  The judge may not edit `spec.md`, so a wrong milestone spec is an escalation, never a
  quiet rewrite.
- **`workflow.py`** builds an ordinary ohflow workflow. It receives these arguments besides the
  milestone's own `args`: `campaign_root`, `milestone`, `integration_branch`, `integration_sha`,
  `round`, and `contracts` when the campaign has a contracts file. Every worktree bases on `args["integration_branch"]`. One worktree checks out the
  milestone's output branch (`Milestone.output_branch`), and the workflow's last merge step
  leaves the finished work there.
- **Briefs** live in `briefs/` and `workflow.py` reads them from disk. A brief that is a file
  is a brief the judge can revise.
- **`acceptance_checks`** are commands the controller runs itself, after the run and before the
  judge. `cwd="land"` runs in the worktree that holds the output branch. A PASS over a failing
  acceptance check is refused.

A milestone that changes more than one repository is in
[Land in several workspaces](#land-in-several-workspaces).

## Land in several workspaces

A campaign that changes one repository sets `Campaign.repo`, and that form works as the
sections above describe. A campaign that changes several declares them as
[workspaces](ohflow.md#workspaces) and leaves `repo` unset:

```python
Campaign(
    name="api-and-docs", root=root, charter="charter.md",
    workspaces=(Workspace("api", api), Workspace("docs", docs, base_branch="trunk"),
                Workspace("notes", root.parent / "notes", owned=True)),
    integration_branch="campaign/api-and-docs",
    milestones=(Milestone(id="m1", title="the endpoint and its page",
                          workflow="milestones/m1/workflow.py",
                          spec="milestones/m1/spec.md", output_branch="m1/out",
                          args={"api": str(api), "docs": str(docs)}),),
)
```

- **Each workspace has its own integration branch.** `Campaign.integration_branch` is one name,
  and the controller creates a branch of that name in every workspace, at that workspace's
  `base_branch`. One workspace so keeps one branch and one diff. The controller creates the
  repository of an owned workspace before it creates the branch. `integration_base` belongs to
  the one-repository form.
- **`Milestone.output_branch` is one name too.** The milestone's workflow declares its own
  workspaces, with the paths that the milestone's `args` carry, and one worktree on the output
  branch in each workspace it writes in. Every worktree bases on `args["integration_branch"]`,
  which exists in each workspace. `args["integration_sha"]` is the default workspace's commit.
- **A PASS lands the milestone in every workspace it wrote in.** Those are the workspaces where
  the workflow has a worktree on the output branch. The controller matches a workflow's
  workspace to a campaign's workspace by its path, so the two may give it different names. A
  milestone that writes in one workspace moves that workspace's integration branch alone.
- **The landing moves every branch or none.** The controller checks in each workspace that the
  output branch exists and contains the integration branch. A refusal in one workspace
  escalates and leaves every integration branch where it was.
- **An acceptance check names its workspace.** `cwd="land"` and `cwd="repo"` mean the default
  workspace, the first one. `cwd="land:<workspace>"` runs in the worktree that holds the output
  branch in that workspace, and `cwd="repo:<workspace>"` runs in its repository. `{base}` in
  its command is the commit of the integration branch in that workspace, so the check runs only
  the tests the milestone's change reaches ([ohflow](ohflow.md#gate-checks)).
- **The packet and the campaign log name each workspace.** The packet lists every workspace
  with its integration branch, says where the milestone lands, and carries one section "The
  product change in workspace `<name>`" for each. `campaign_started`, `milestone_started` and
  `campaign_delivered` add `integration_shas`, a commit for each workspace, and
  `milestone_landed` adds `workspaces`, the commit before and after for each.

`campaign validate` refuses `repo` beside `workspaces`, a workspace that is no git repository
(an owned workspace whose folder is absent or empty passes), two workspaces on one path, an
acceptance check that names an undeclared workspace, a worktree on the output branch in a
repository that is no workspace of the campaign, and a milestone whose workflow has no worktree
on its output branch in any workspace. `campaign run` stops on the last two before the round
starts, as on a preflight fault: no judge runs and no revision is spent.

Done when `campaign validate` prints `CAMPAIGN OK`, and after the run
`git -C <workspace> log -1 <integration branch>` shows the milestone's commit in each
workspace it wrote in.

## Finishing milestones

Add a smoke-test milestone when the product has a CLI verb or MCP tool that a user drives. Its
milestone spec asks to build, install and start the product the way a user does, drive every new CLI verb
and MCP tool once against a real target, and record the transcript. Add an architecture pass, a
documents pass or a parity milestone only when the operator asks.

## The judge

`Campaign.judge` defaults to `default_judge()`: the claude harness executor, the judge model, effort
high, `max_iterations=400`, the signed-in harness's usual setup. The judge model is the operator setting
`campaign.judge_model`. Its base value is the tier `heavy`, which the claude harness executor
resolves through the setting `tiers.heavy.claude`. It also takes the tier `light` or a model id. A value that is not a non-empty
string is refused when the campaign file is loaded, before any milestone runs. The usual setup gives the
judge the operator's skills and MCP servers, but the judge needs none of them to write its handover. A milestone may name its own judge in `Milestone.judge`. A codex or
pi judge is an `AgentSpec` with that harness executor, and it does not read the setting.

Each round's judge runs in a workflow run of its own, under `Campaign.judge_execution_timeout_s`.

The judge's instructions are `JUDGE_ROLE` in `campaign.py`. They set the price of a REVISE
(one more round, the p50 wall time plus the p50 check time of the run's estimate, or "an
unknown number of minutes" without an estimate (`round_minutes`), so a REVISE is for a finding that would
cost the operator more than that, and the rest are notes), the evidence rule (read the check
logs and the diff, and rerun no check that passed), the rubric
rule (grade each `- rubric:` line of the milestone spec, and PASS only when each is met), the write
scope (the milestone directory, not `spec.md`, never the product), the cause word per
finding, and the ending: write the judge handover to the named path, then answer with the
decision JSON.

The judge brief carries the handover's format, so the judge invokes no skill for it. The
handover has a `# ` title, a lead paragraph, and the seven headings of the
[step handover](step-handover.md) contract in order: State, Done and undone, Decisions,
Verified and assumed, Tried and failed, Open, Next. Its answer rules are the step handover's:
`not established` for an unknown, exact paths and commands, `[verified]` or `[assumed]` per
finding, "already done, do not repeat" on a completed side effect, no secrets. The headings
come from `handover.CORE`, so the two contracts cannot drift apart.

The handover opens with one paragraph right under its `# ` title that names the decision
and the reason for it. That lead paragraph is the reason `campaign history` prints for the
round: the text between the title line and the next line that starts with `#`. A handover
without one prints `the handover has no lead paragraph`. The `summary` of the decision JSON
is never shown in its place.

The cause word of a finding is one of six: `brief` (the agent was not told), `distribution`
(ownership or order was wrong), `tool_policy` (wrong tools or model), `gate` (the check held the
wrong thing), `product` (the code is wrong and the brief was right, so a fix step follows) or
`spec` (the spec or the milestone spec is wrong). A `spec` cause is an ESCALATE, because the
spec is not the judge's to change.

The decision JSON follows `DECISION_SCHEMA`: `decision` (PASS, REVISE or ESCALATE),
`summary`, `findings`, `revisions` and `question_for_operator`. The findings are fields of
that JSON, each with a severity, a cause word and evidence. The judge writes no findings
file. Its file edits are revisions to the milestone's briefs, `workflow.py` and other inputs,
each named in `revisions` with its reason.

The judge's step gate checks two things: the decision matches `DECISION_SCHEMA`, and the
handover file exists. One retry covers a judge that answered before writing it.

## Intervention by kind of objective

Every campaign and every run serves an objective of one kind, and the kind sets how far an
upper rank may stop or change work in flight. An upper rank is the orchestrator agent, a judge
or the operator. The operator names the kind with one sentence on why in the bill at hand-over
([monitor-a-run](monitor-a-run.md#at-hand-over-write-the-bill)), and in a campaign also in the
charter under `## Decisions already made`, so that every judge reads both at each check-in. A
kind is a delivery or an empirical procedure. The kind changes as the work moves on: a
calibration that found its design is committed as an empirical procedure.

**A delivery is open to revision at any time.** Its wanted effect is known and fairly
deterministic: a feature, a fix, a document. Search, research and producing a specific output
count as delivery.

- A deviation or a design flaw aborts the run at once for a fix. A deviation is work that left
  its plan, such as a step that ignored its brief. A design flaw is a wrong plan, such as a
  workflow that checks the wrong thing, a gate that tests the wrong file or an experiment that
  measures the wrong quantity.
- After a miss, where the plan was right and followed and the result still misses the goal, an
  upper rank may replan, pause, continue, or propose a restart of the whole run to the operator.
- In a campaign, the judge's REVISE replans the milestone's inputs and its ESCALATE pauses for
  the operator. A restart of the whole campaign is the operator's decision.
- A build whose benefit nobody knows yet is still a delivery, and it may pivot mid-flow when a
  result shows where the benefit lies.

**An empirical procedure is fixed once committed.** A hypothesis test or an A/B test puts a
control arm and an experiment arm through the same procedure, and following that procedure to
the end is the buy-in the experiment requires. It fixes its procedure up front.

- An upper rank stops it only for a deviation, such as an arm that did not follow the procedure
  or a measurement that did not record. A miss, a disappointing or surprising result, is the
  experiment's result and stops nothing.
- Only a change to the procedure fixes a design flaw. It restarts every arm, so that the arms
  stay comparable, and that restart is the operator's decision. Results from the old procedure
  stay out of the comparison.
- In a campaign, the judge of an empirical milestone REVISEs only to fix a deviation.
  A REVISE that changes the procedure changes the input of every arm's step, so that every arm
  gets a new fingerprint and runs again. Otherwise the judge decides PASS or ESCALATE.

## What the controller refuses

Each refusal writes `ESCALATION.md`, opens with the `operator.escalation_marker` setting (`ACTION NEEDED FROM THE OPERATOR` in the base settings), runs
`Campaign.on_escalate`, or the command in the `operator.on_escalate` setting when the campaign
names none, and exits 3. An ESCALATE decision takes the same path. Every
refusal and every ESCALATE leaves the milestone in the one state `escalated`, and the `why`
string in the campaign log and in `campaign-status.json` carries the reason.

**A run that did not start is not judged.** When a milestone's run fails preflight (or its run
directory is not its own), the controller stops before any judge runs. It writes `ESCALATION.md`
with the problem, sets the state in `campaign-status.json` to `preflight_failed` with the
problem lines, appends a `preflight_failed` event to the campaign log (no `judged`, no `escalated`),
runs `Campaign.on_escalate`, or `operator.on_escalate` when the campaign names none, and
exits 3. No revision is spent and the milestone stays
`running`. Fix the problem and `run` again: the same round starts, and the leftovers of the
failed start move to `<run-dir>.not-started-NN`. No `grant` is needed. Each round loads the
milestone workflow once.

**A run that paused is not judged.** When a provider defers a step (a rate limit, a usage
limit, an outage) and the run ends `paused`, the controller stops before any judge runs. It
writes `ESCALATION.md` with each deferred step and the provider's own error text, which
usually names the reset time, sets the state in `campaign-status.json` to `paused`, appends a
`run_paused` event (no `judged`), runs `Campaign.on_escalate`, or `operator.on_escalate`
when the campaign names none, and exits 3. No revision is spent
and the milestone stays `running`. After the limit resets, `run` again: the same round
resumes its run directory, and each deferred step starts again only while
`ohflow.attempts.may_start` allows it. Judged failures and transient deferrals of unchanged
work count together, and two of them exclude the step, also on resume. A step that has spent
`1 + retry.max + auto_resume + 1` executions does not start either. A refused step is
recorded `failed` (`quarantined` under a quarantine phase policy) with the line
`not started - <reason>`, the run ends, and the judge decides the round. To try that work
again, a REVISE changes the step's brief, which gives the work a new fingerprint and a fresh
budget. No `grant` is needed. Example: cdp-mode m1b on
2026-10-03, where Z.AI's 5-hour usage limit stopped the implementer after 21 minutes.

| The judge did this | Why it is refused |
|---|---|
| edited a path outside `milestones/<id>/`, or `spec.md` | the target and the other milestones are not its to change |
| edited `contracts.md`, under any decision | every step of every milestone builds against it. A contract change is the operator's. The controller restores the file and stashes the edit |
| REVISE with no changed file | the resume would repeat the last run |
| REVISE after the budget (`max_revisions`, default 2) is spent | the edit is kept on branch `campaign-proposal/<id>-rNN` for the operator |
| PASS while an acceptance check failed or a step did not pass | the decision is a claim and the check is the evidence |
| PASS when the output branch does not contain the integration branch, in any workspace the milestone lands in | the milestone landing would drop work, so no workspace's integration branch moves |
| gave no valid decision after its retry | nothing to act on |

A PASS with edits is undone with `git stash`, so a PASS never changes an input.

## Run it

Commands run from the `scripts/` folder of your ohflow clone with `PYTHONPATH=.`.

```bash
python3 -m ohflow.cli campaign validate --campaign <root>/campaign.py
python3 -m ohflow.cli campaign run --campaign <root>/campaign.py --detach [--hold] [--pilot]
python3 -m ohflow.cli campaign status --campaign <root>/campaign.py
python3 -m ohflow.cli campaign watch --campaign <root>/campaign.py [--timeout S]
python3 -m ohflow.cli campaign history --campaign <root> [--milestone <id>] [--json]
python3 -m ohflow.cli campaign estimate --campaign <root>/campaign.py [--history DIR] [--json]
python3 -m ohflow.cli campaign grant --campaign <root>/campaign.py --milestone <id> --revisions 1
```

`validate` builds every milestone's workflow with first-round arguments, so a workflow error
shows before anything runs. `run` continues from the first milestone that has not passed,
and a milestone that was mid-run resumes its run directory. After an escalation, act on
`ESCALATION.md`, then `grant` one revision and `run` again. A grant adds to the milestone's
revision budget and reopens it. It resets no spent revision and no step's execution allowance.

`run --hold` holds the campaign's first fresh round for `ohflow go --run <run-dir>`. The first
round of a later milestone, and a round that a judge's revision starts, go ahead unless the
estimate exceeds the first round's actual minutes by half: the `round_s` of the first
`judged` event in the campaign log. With no estimate or no recorded first round, it holds.
A round after a revision resumes the milestone's run directory, and its run holds before it
continues. The controller knows that round because it recorded the revision in the same
`campaign run`. When a `campaign run` starts again on a milestone whose run directory holds a
run log, its first round is a resume after an interruption, and that resume never holds. The
controller writes `held` and the `go` command into `campaign-status.json`, says
`held; release it with ...` in the campaign log, and `campaign watch` reads
`<milestone> held · run <dir> · go: <command>` on line one until the release, when
`campaign-status.json` reads `running` again. While held, the run itself reads `held` in
`ohflow status` and on its dashboard. Judge runs never hold.

`run --pilot` implies `--hold`. A fresh round whose workflow declares
[units](ohflow.md#units-and-unit-paths) runs its [pilot](ohflow.md#pilot-a-run-over-many-units)
first, then holds. A fresh round of a workflow without units holds. The campaign log says
`the pilot runs first, then held; release it with ...`. A round that a revision starts runs no
pilot, because its run resumes. It only holds. A resume after an interruption neither pilots
nor holds.

`campaign watch` prints the campaign's one-line status, then one line per campaign log event and
each new dashboard URL since this watcher's last call. While a judge runs, line one reads
`<milestone> judging round N`. It names the judge run directory, and ends `· starting`
until that directory exists. The first call prints at most ten campaign log events, the newest, and
says how many it left out. A dashboard URL appears only while its run is live: the milestone
run, then the latest judge run. The cursor lives in
the campaign root under a name (`--cursor`, default `agent`), in `.watch.<name>.json`.
`ohflow campaign` adds `.watch.*.json` to the campaign's `.gitignore`, so a cursor never
counts as a judge's stray edit: poll with this verb while a judge runs. It exits `0` when the campaign
is delivered, `1` when it ended otherwise and `10` when it returns with the campaign still
going.

`campaign history` lists every judged round, read from the campaign's files only, and it starts
nothing. `--campaign` takes the campaign module or the campaign folder, so a campaign whose
module no longer imports still reads. It reads both spellings of the campaign log: `round`,
`decision` and `milestone_landed`, and the older `attempt`, `verdict` and `milestone_passed`.
Line one is `HISTORY <name>: <M> milestones, <R> rounds, <k> REVISE, <e> ESCALATE · campaign.jsonl`. Then each
milestone's rounds and events print together, in campaign log order:

```text
<id> round <n>: <DECISION> · checks <p>/<t> passed (failed: <names>) · revision <sha> · run <dir> · campaign.jsonl:<line>
  reason: <the handover's lead paragraph> · <handover path>
<id> escalated: <why> · campaign.jsonl:<line>
<id> granted <n> revisions · campaign.jsonl:<line>
<id> landed · campaign.jsonl:<line>
```

The checks come from the round's `packet.md`: `checks none` when the milestone defines none,
`checks unknown` when the packet is missing. `NO DECISION` is a judge that gave none. A reason
is cut to 300 characters, but its path is never cut. The whole text stops at 8,000 characters
with `(cut at 8,000 characters; narrow with --milestone or read --json)`. `--json` carries
every round in full. It exits `1` when the folder has no campaign log or `--milestone` names
a milestone with no round or event.

`run --detach` starts the controller through the same helper as `ohflow run --detach`, and prints the
launch method it used (`direct`, `breakaway` or `wmi`) in a `"launch_method"` key. When no launch
method works it prints guidance and exits `1`. The launch methods are in [ohflow](ohflow.md#run-it).

The process that runs the campaign writes its own pid to `campaign.pid` when it starts, and the
printed `"pid"` is the pid of that record. The process that `run --detach` launches is a wrapper
around the campaign under the `wmi` launch method, where it is a `cmd.exe`, and under a Windows
virtual environment, where it is the interpreter's redirector, so its pid can name a process that
has exited while the campaign runs on. The launcher waits up to 20 s for a `campaign.pid` other than
the one it found before the launch. When none arrives by then, or the launched process dies first,
the launcher writes and prints the launched pid.

**Heartbeat.** `campaign-status.json` names the milestone, the round, the state
(`running`, `held`, `judging`, `escalated`, `preflight_failed`, `paused`, `delivered`) and, only while that
run's dashboard is live, its URL. The campaign log gains a line per run, decision and commit. Poll
both every twenty minutes: a status file older than the current run's execution timeout, or a
campaign log that stops growing across two polls, is a stall.

The campaign log moves only between runs. A quiet campaign log is normal while a run goes. The stall
signal inside a run is that run's own `ohflow watch --run <run dir>`. The run directory is in
the first line of `campaign watch`. The campaign-level stall is a `campaign watch` whose first
line names the same run and state across polls for longer than that run's execution timeout.

## Estimate the campaign

`campaign estimate` forecasts the whole campaign before it starts: the minutes, tokens and
cost of every milestone that has not landed. It reads files only, starts nothing and runs no
git. The forecast is the sum over the milestones of `(1 + r) x E(m)`.

`E(m)` is the [run estimate](ohflow.md#estimate-a-run) of the milestone's workflow, built with
the arguments its round 1 receives and an empty `integration_sha`, as `campaign validate`
builds it. `--history DIR` (repeatable, else `OHFLOW_HISTORY`) names where the finished runs
are. With neither, the verb prints `estimate: no history given (--history DIR or
OHFLOW_HISTORY)` and exits 0, as `ohflow estimate` does. The `checks p50` column is the
milestone's gate-check time from the same run estimate.

`r` is the median number of REVISE rounds one milestone takes. One REVISE decision resumes
the milestone's run once, so a milestone's sample is the count of its `judged` rounds whose
decision was REVISE. A milestone that passed at its first judging counts 0. Only a milestone
that reached a PASS or an escalation is a sample: one still running has spent an unknown part
of its revisions. The samples come from every `campaign.jsonl` up to four levels under the
`--history` directories and from the campaign's own log. With no finished milestone anywhere,
`r` is 0 and the output says that no campaign history was found.

A resume re-runs only the steps whose fingerprints changed, so `(1 + r) x E(m)` prices every
revised round as a whole run and is an upper bound. A milestone that already landed in the
campaign's own log counts 0 and is marked `landed`, so the total is the work that is left.

Line one is `CAMPAIGN ESTIMATE <name>: ~<p50> (p50) to <p80> (p80), <tokens> tokens, <cost>
for <n> milestones left, confidence <ok|low>; REVISE median <r> over <k> finished milestones,
x<1 + r>; <a> attempts from <s> summaries`. With no matching history, line one is
`CAMPAIGN ESTIMATE <name>: no history matched some step; <a> attempts from <s> summaries`. Under it, one row per milestone with its scaled numbers, its factor, `landed` or
`left`, and one `total` row. `--json` carries each milestone's own run estimate besides the
scaled numbers, the REVISE counts the median rests on and the campaign logs they came from.
It exits 0, the no-history line included.

## Limits

- Every new try at a milestone resumes its one run directory. A judge that wants a step to
  start over changes that step's brief or adds a step. There is no fresh-run decision.
- A step that needs the operator's hands cannot run unattended. Put it in the milestone spec as an
  ESCALATE point with the one action the operator must take. Example: route B of the CDP design
  needs a person to click "Allow" per connection.
- Judges run in the signed-in harness's usual setup, so each judge session also runs that
  harness's session-end hooks, including memory capture.
