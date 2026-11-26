"""How many times has this work been tried, and may it be tried again.

Every answer in this module is read from the run log. Nothing is counted in
memory, because a counter held in one supervisor process resets when that
process is killed, and a bound that resets is not a bound. A run directory can
be resumed by hand an hour later and it still knows what it already spent.

The key is the pair `(coordinate, fingerprint)`, and the pair is what makes the
counting honest. The coordinate alone would carry a spent budget across a workflow
edit, punishing new work for an old failure. The fingerprint alone would lose
track of a step that moved. Together they name one piece of work: edit the
brief and the fingerprint changes, so the work is a new revision with a fresh
budget, and the earlier attempt directories stay on disk beside it.

**Only an execution that started is counted.** A cached step, an abort victim
recorded before it got its turn, and a phase policy relabelling a verdict all
write `attempt_finished` with no `attempt_started` before it. None of them spent an
agent, and `RunLog.replay` marks them `started: False`.

Three diagnostic counters, answering different questions.

  judged_failures       an execution reached a verdict and the verdict was no.
                        `failed`, `timeout`, `quarantined`.
  transient_deferrals   an execution was deferred on a transient fault. It
                        reached no verdict; the provider never gave it one.
  abort_victims         the run's abort killed the execution. It may already
                        have called the provider. It reached no verdict, so
                        the exclusion does not count it; a started one still
                        spends a start from the total.

**Exclusion is on the total.** `failed_executions` is the sum of the first two,
and two of them exclude the work. A judged failure followed by a transient
deferral is two failed executions of unchanged work, and a third start would
spend a provider call to learn what the first two already said.

Three bounds, and they are checked together.

  per kind     `retry` starts may not pass `step.retry.max`, and `auto_resume`
               starts may not pass `workflow.auto_resume`. Each knob limits its
               own kind, so `auto_resume=1` never authorises a retry and
               `retry.max=1` never authorises an auto-resume pass. A `reattach`
               start has no per-kind budget: it is a supervisor death or a host
               loss answered by continuing the same attempt, not a new
               decision by the workflow's author.
  total        every execution of this work, whatever started it:
               `1 + retry.max + auto_resume + MANUAL_RECOVERY_ALLOWANCE`.
               This is the bound that catches a supervisor interrupted over
               and over, where nothing ever records a failure status. A
               reattach spends a start from it, exactly as an abort victim
               killed in flight does, and it does not advance the exclusion,
               so a step whose own work keeps killing its supervisor stops
               when its starts run out.
  exclusion    two failed executions of unchanged work, checked first.

`MANUAL_RECOVERY_ALLOWANCE` is why manual resume is not unlimited and is also
not zero. At the defaults `retry.max=0, auto_resume=0` the total budget is two
executions, which is the initial run plus the one manual recovery `--resume`
allows today. Without the allowance the budget would be one and `--resume`
would be a no-op for a rate-limited step.
"""

from __future__ import annotations

from typing import Any

from .run_log import RunState

__all__ = [
    "JUDGED_FAILURE_STATUSES", "EXCLUSION_THRESHOLD",
    "MANUAL_RECOVERY_ALLOWANCE", "AUTOMATIC_KINDS",
    "executions", "attempts", "judged_failures", "transient_deferrals",
    "failed_executions", "abort_victims", "starts_of_kind",
    "automatic_starts", "next_attempt", "excluded", "exclusion_reason",
    "execution_budget", "may_start",
]

#: A verdict was reached and it was no.
JUDGED_FAILURE_STATUSES = frozenset({"failed", "timeout", "quarantined"})

#: Two failed executions of unchanged work is enough. The third try spends a
#: provider call to learn what the first two already said.
EXCLUSION_THRESHOLD = 2

#: One manual recovery per piece of work, on top of the automatic budget. A
#: human's `--resume` is a fresh decision, and it is still finite.
MANUAL_RECOVERY_ALLOWANCE = 1

#: Starts the engine makes by itself.
AUTOMATIC_KINDS = ("retry", "auto_resume")


def _key(coord: str, fingerprint: str | None) -> str:
    return f"{coord}@{fingerprint}"


def executions(state: RunState, coord: str,
               fingerprint: str | None = None) -> list[dict[str, Any]]:
    """Every execution that actually started at this coordinate, oldest first.

    With a fingerprint, only the executions of that revision of the work.
    Records `RunLog.replay` marked `started: False` are left out: nothing
    launched for them.
    """
    out = [e for e in state.executions
           if e.get("coord") == coord and e.get("started")]
    if fingerprint is not None:
        out = [e for e in out if e.get("fingerprint") == fingerprint]
    return out


def attempts(state: RunState, coord: str,
             fingerprint: str | None = None) -> int:
    """How many executions ever started, whatever became of them.

    An execution with no ending counts. The supervisor was killed while an agent
    was running, and that agent may have left side effects behind, so it spent
    a turn and the next execution is a new attempt rather than a repeat of it.
    """
    return len(executions(state, coord, fingerprint))


def judged_failures(state: RunState, coord: str,
                    fingerprint: str | None = None) -> int:
    return sum(1 for e in executions(state, coord, fingerprint)
               if e.get("status") in JUDGED_FAILURE_STATUSES
               and not e.get("abort_victim"))


def transient_deferrals(state: RunState, coord: str,
                        fingerprint: str | None = None) -> int:
    return sum(1 for e in executions(state, coord, fingerprint)
               if e.get("status") == "deferred" and not e.get("abort_victim"))


def failed_executions(state: RunState, coord: str,
                      fingerprint: str | None = None) -> int:
    """Every execution that started and did not succeed, abort victims apart.

    Exclusion counts this, not either half. A judged failure followed by a
    transient deferral is two failures of unchanged work.
    """
    return (judged_failures(state, coord, fingerprint)
            + transient_deferrals(state, coord, fingerprint))


def abort_victims(state: RunState, coord: str,
                  fingerprint: str | None = None) -> int:
    """Recorded so a run can be read afterwards. The exclusion never counts it."""
    return sum(1 for e in executions(state, coord, fingerprint)
               if e.get("abort_victim"))


def starts_of_kind(state: RunState, coord: str, fingerprint: str | None,
                   kind: str) -> int:
    return sum(1 for e in executions(state, coord, fingerprint)
               if e.get("start_kind") == kind)


def automatic_starts(state: RunState, coord: str,
                     fingerprint: str | None = None) -> int:
    """Starts the engine made by itself, of either kind."""
    return sum(1 for e in executions(state, coord, fingerprint)
               if e.get("start_kind") in AUTOMATIC_KINDS)


def next_attempt(state: RunState, coord: str) -> int:
    """One past the highest attempt number any execution ever started with.

    Numbering runs across fingerprints and across resumes on purpose. An attempt
    number names a directory, and a directory that once held an agent's output
    is never written into again. A cached step and an abort victim that never
    got its turn consume no number, because nothing was written for them.
    """
    highest = 0
    for e in executions(state, coord):
        value = e.get("attempt")
        if isinstance(value, int) and value > highest:
            highest = value
    return highest + 1


def excluded(state: RunState, coord: str, fingerprint: str | None) -> bool:
    """Has this work already been shut out of the rest of the run.

    True when a `work_excluded` event named it, and true when the counters say
    it has earned one. The second half matters on a resume: the exclusion is
    recomputed from the same run log the engine wrote, so a run resumed from a
    directory whose exclusion event was never reached still refuses the work.
    """
    if _key(coord, fingerprint) in state.exclusions:
        return True
    return failed_executions(state, coord, fingerprint) >= EXCLUSION_THRESHOLD


def exclusion_reason(state: RunState, coord: str,
                     fingerprint: str | None) -> str | None:
    """One line naming what reached the threshold, or None."""
    recorded = state.exclusions.get(_key(coord, fingerprint))
    if recorded and recorded.get("reason"):
        return str(recorded["reason"])
    total = failed_executions(state, coord, fingerprint)
    if total < EXCLUSION_THRESHOLD:
        return None
    judged = judged_failures(state, coord, fingerprint)
    deferred = transient_deferrals(state, coord, fingerprint)
    short = fingerprint[:12] if fingerprint else "no fingerprint"
    return (f"excluded: {total} failed executions of unchanged work "
            f"({judged} judged, {deferred} transient, work {short})")


def execution_budget(retry_max: int, auto_resume: int) -> int:
    """Every execution one piece of work may ever have in one run directory.

    The three parts add. They do not multiply: an auto-resume pass does not hand the step a
    fresh retry budget, because that would make the worst case the product of
    two numbers a workflow author chose independently.
    """
    return (1 + max(0, int(retry_max)) + max(0, int(auto_resume))
            + MANUAL_RECOVERY_ALLOWANCE)


def may_start(state: RunState, coord: str, fingerprint: str | None, *,
              start_kind: str, retry_max: int, auto_resume: int) -> tuple[bool, str]:
    """May this execution start. Returns the decision and the reason for it.

    The reason is returned either way, so a run can always answer why a step did
    or did not run again.
    """
    if excluded(state, coord, fingerprint):
        return False, exclusion_reason(state, coord, fingerprint) or "excluded"

    if start_kind == "retry":
        used = starts_of_kind(state, coord, fingerprint, "retry")
        if used >= max(0, int(retry_max)):
            return False, (f"retry budget spent: {used} of {retry_max} "
                           f"retries used for this work")
    elif start_kind == "auto_resume":
        used = starts_of_kind(state, coord, fingerprint, "auto_resume")
        if used >= max(0, int(auto_resume)):
            return False, (f"auto-resume budget spent: {used} of "
                           f"{auto_resume} auto-resume passes used for this work")

    # The total catches what no per-kind counter can: a supervisor interrupted
    # over and over records executions that never reach a failure status, so
    # exclusion never fires and every per-kind budget stays untouched.
    budget = execution_budget(retry_max, auto_resume)
    started = attempts(state, coord, fingerprint)
    if started >= budget:
        return False, (f"execution budget spent: {started} of {budget} "
                       f"executions of this work "
                       f"(1 initial + {retry_max} retries + {auto_resume} "
                       f"auto-resume passes + {MANUAL_RECOVERY_ALLOWANCE} manual recovery)")

    return True, (f"{start_kind} start, execution {started + 1} of {budget}, "
                  f"attempt {next_attempt(state, coord)}")
