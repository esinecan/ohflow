# Construct a campaign from specs

`ohflow construct` turns a bundle of milestone specs into a [campaign](campaign.md). You, the
orchestrator agent, read the specs with your own connectors: an Atlassian MCP server, `gh issue view`,
a knowledge graph or a folder of specs. You write what you read as a bundle, and `construct` reads only
the bundle. ohflow carries no connector code.

```bash
cd <ohflow clone>/scripts && export PYTHONPATH=.
python3 -m ohflow.cli construct --bundle <bundle> --out <campaign> [--history DIR]
```

Done when the verb prints `CAMPAIGN OK` as its second-to-last line.

## The bundle

```text
<bundle>/
  bundle.md                  the campaign: its name, the operator's words, the workspaces
  contracts.md               optional; a fan-out under contracts needs it
  milestones/<id>/spec.md    one milestone each; the folder names order the milestones
```

A milestone id is lowercase letters, digits and hyphens, such as `04-pi-cloud-transcript`. A field
line is `key: value`; a value in backticks loses them.

### bundle.md

```markdown
# Issues 4 to 6

integration branch: campaign/issues-4-6
kind: delivery

## The operator's words

<the operator's request, verbatim>

## The bar

## Decisions already made

## Stop and ask

## Workspace skills

path: ../skills
base: main
```

- **The title names the campaign.** Its slug is the campaign's name and the stem of its branches.
- **The fields above the first `##` section are optional.** `integration branch` defaults to
  `campaign/<name>`. `kind` is `delivery` (the default) or `empirical`, as
  [campaign](campaign.md#intervention-by-kind-of-objective) defines them; write the reason for
  the kind under `## Decisions already made`, which the charter carries beside it.
  `judge harness` (`pi`, `claude` or `codex`) and `judge tier` name the judge. When the bundle
  names one of the two, the other is `claude` or `heavy`. When it names neither, the judge is
  `claude` on the tier that the `campaign.judge_model` setting names, `heavy` by default.
- **`## The operator's words` is required.** Every section other than a workspace goes into the
  charter in its order, so write the bar, the decisions and the stop-and-ask points there.
- **Each `## Workspace <name>` declares one [workspace](ohflow.md#workspaces).** `path` is the
  repository, absolute or relative to the bundle. `base` defaults to `main`. `remote` is the URL of
  the workspace's `origin`, and `baseline` is a command that must exit 0 at the base. `owned: yes`
  makes ohflow create the repository; its `path` defaults to `workspaces/<name>` in the campaign.

### spec.md

```markdown
# Strict mode in the config parser

source: https://github.com/acme/parser/issues/12
pattern: implement-and-review
workspaces: app
box: local
harness: pi
tier: heavy
review harness: claude

## Scope

<the task every brief of this milestone carries>

## Acceptance

- command: python -m unittest tests.test_strict
- command in docs: grep -q "Strict mode" README.md
- rubric: The error message names the unknown key and its line number.
```

| Field | What it holds |
|---|---|
| `source` | required: the issue URL, the ticket key or the file path the milestone serves |
| `pattern` | the workflow pattern, one of the six below; none gives `implement-and-review` |
| `workspaces` | the workspaces the milestone uses, comma-separated, the default one first; optional when the bundle declares one |
| `box`, `harness`, `tier` | required for every agent step: the defaults of the milestone's steps |
| `durable` | `yes` runs a `pi` step on box `local` through the durable executor, so it survives a restart |
| `writes` | the write scope of the one agent of `single-agent` and the implementer, comma-separated globs; default `**` |
| `<role> <field>` | a role's own `box`, `harness`, `tier`, `durable` or `workspace`, such as `review harness: codex` |

`## Scope` is required. Its text and the whole milestone spec go into every brief, so a cloud step needs no
local file. A pattern with pieces needs `## Steps`, with one `### <name>` part per step: the part
opens with its own field lines (`workspace`, `writes`, `box`, `harness`, `tier`, `durable`), and its
task follows. A step name is lowercase letters, digits and hyphens. It starts with none of
`merge-`, `check-` and `piece-`, and it is none of `agent`, `implement`, `review` and `consolidate`.

## The workflow patterns

Each milestone names one [workflow pattern](workflow-patterns.md), and one campaign mixes them. The steps of a milestone work on the output branch `milestone/<campaign>/<id>`, one
worktree in each workspace a step writes in, so the campaign lands the milestone in each of them.

| Pattern | Pattern roles | What `construct` builds |
|---|---|---|
| `single-agent` | `agent` | one agent step |
| `relay` | a step per `### ` part, in order | one phase per step; each step consumes the handover of the step before it, and may write in another workspace |
| `fan-out` | a step per `### ` part | the steps in parallel, each on its own branch, then one merge per step into its workspace's output worktree |
| `fan-out-with-consolidation` | parts and `consolidate` | the fan-out, then a consolidator in the output worktree that makes the pieces fit |
| `fan-out-under-contracts` | parts and `review` | the fan-out against `contracts.md`, then one reviewer with a terminal only, whose gate fails on a blocking finding |
| `implement-and-review` | `implement` and `review` | an implementer, then a reviewer with a terminal only, whose gate wants `VERDICT: MERGEABLE` |

The three fan-out patterns declare each part as a unit on the unit path `piece`, so
[`run --pilot`](ohflow.md#pilot-a-run-over-many-units) runs one part end to end first. The other
three patterns have one unit of work, so a pilot would run the whole milestone twice; they hold
instead.

A writing step gets `max_iterations=150` and a reviewer 80; the judge that `construct` writes gets 400.

A change across repositories is `fan-out-under-contracts` with one part per repository: each part
names its workspace, `contracts.md` fixes the interface between them, and a mechanical check that
names the other worktrees runs the tests across them.

## The executor comes from the box and the harness

| Box | Harness | Executor |
|---|---|---|
| `local` | `pi` | `pi`, or `durable` with `durable: yes` |
| `local` | `claude` or `codex` | `claude` or `codex` |
| an ssh host alias | `pi` | `durable` on that box |
| `cloud` | `pi`, `claude` or `codex` | `pi-cloud`, `claude-cloud` or `codex-cloud` |

Any other pair is refused with these valid pairs. A step on an ssh box or a cloud box reads only its
own workspace, and one that writes in an owned workspace needs that workspace's `remote`.

**A tier names no model.** `heavy` and `light` resolve through `tiers.<tier>.<executor>` in the
operator settings ([model tiers](harness-executors.md#model-tiers)). A `pi` step also names the variable
that holds its provider's key: the setting `pi.api_key_env.<provider>`, else `<PROVIDER>_API_KEY`,
and its endpoint from `pi.base_url.<provider>` when that is set.

## Acceptance checks

- **A mechanical check passes when its command exits 0.** `- command: <cmd>` runs in the output worktree of
  the milestone's first written workspace; `- command in <workspace>: <cmd>` names another. In
  `single-agent`, `relay` and `implement-and-review` the command gates the step that writes last
  in its workspace, and the reviewer. In the three fan-out patterns it runs as a `check-` step after
  the merges. The campaign runs it as an acceptance check before the judge. Any command counts, such as `grep`, a linter or a grading script, so prose work has mechanical checks too. The command runs
  once per tree: the reviewer's gate and the acceptance check reuse a pass on the same clean
  tree in the same folder, so a reviewer who commits makes it run again. The implementer runs
  only the tests of the files it changes, and the reviewer and the judge read the logs.
- **A command tests the change, never the whole suite.** The full suite runs in CI after a push,
  as [ohflow](ohflow.md#gate-checks) states. `{base}` in a command is the commit the milestone
  started from, so a runner can select the tests the change reaches; for this repository the
  line is `- command: python3 tests/run_tests.py --changed {base}`. No workspace may
  be named `base`.
- **`{<workspace>}` in a command is that workspace's output worktree.** `construct` writes it as a
  Git Bash path built from `$PWD`, so the same command finds the sibling worktree in the pilot.
- **A rubric check is graded by the judge.** `- rubric: <text>` stays in the milestone spec, and the judge
  passes the milestone only when each rubric check is met. No gate agent exists. Judgment lives in
  rubric checks and reviewer steps, and a step needs neither, because many steps are chores.

## What construct writes

```text
<campaign>/
  campaign.py                the workspaces, the milestones, their acceptance checks, the judge
  charter.md                 the bundle's sections, the kind, and each milestone with its source
  contracts.md               when the bundle has one
  milestones/<id>/
    spec.md                  the milestone spec, verbatim; the judge may not change it
    milestone.json           the workflow pattern, the steps with executor, box and tier, the commands
    workflow.py              builds the workflow from milestone.json through ohflow.patterns
    briefs/<step>.md         one brief per agent step
```

The campaign is a new git repository with nothing committed; the first `campaign run` commits the
inputs. Its `.gitignore` covers `worktrees/` and `workspaces/`, where the runs put their worktrees
and the owned workspaces. A judge's REVISE edits `milestone.json` and the briefs, and the next round
builds the workflow from them. `construct` refuses an `--out` folder that exists and is not empty.

## What it prints

```text
CONSTRUCTED <campaign>: 3 milestones
04-pi-cloud-transcript implement-and-review: VALID 04-pi-cloud-transcript: 2 phases, 2 steps; harness executors claude:1, codex:1
04-pi-cloud-transcript: ESTIMATE 04-pi-cloud-transcript: ~17 min (p50) to 29 min (p80), ...
CAMPAIGN OK
start: python3 -m ohflow.cli campaign run --campaign <campaign>/campaign.py --pilot --detach
```

Line one says the campaign is written. One line per milestone is its `validate` verdict. A milestone
that does not build prints `INVALID` and one indented line per fault. With a history, one line
is its `estimate`; without one, one line says that no history was given. Then
come the `campaign validate` problems and its verdict, and the command that starts the campaign.
It exits 0 on `CAMPAIGN OK` and 2 when a milestone or the campaign does not validate.

**A refused bundle writes nothing.** Line one is `REFUSED <bundle>: N problems`, then one line per
fault, each naming the milestone and the field. The faults include an unknown workflow pattern, a box and
harness with no executor, a tier other than `heavy` or `light`, a workspace the bundle does not
declare, and a missing `source:` line.

## Start the campaign

`campaign run --pilot` runs the pilot of each fresh milestone round whose workflow declares units,
then holds; a round without units holds. `ohflow go --run <run dir>` releases it, as
[campaign](campaign.md#run-it) describes. Read the briefs and the estimate first, and run
`campaign estimate` for the whole forecast.
