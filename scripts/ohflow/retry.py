"""May this step have another attempt, and why.

One pure function decides, and it returns its reason whichever way it goes. The
reason is recorded in the run log on the step, so a run can always answer why a step did or
did not run again. Nothing here touches the filesystem or the clock, so the
whole decision is testable without an engine.

A retry answers one thing: a gate reached a verdict and the verdict was no.
Everything else has its own answer elsewhere. A provider that never answered
defers the step, and `workflow.auto_resume` restarts it in an auto-resume pass. A run that aborted stops.

The tokens in `RetryPolicy.on` are a whitelist and there are three forms.

    timeout          the engine's execution timeout fired for this step
    agent_error      the step recorded an error of its own
    gate:<check>     that named check failed, in the spelling
                     `GateReport.failed_names()` already produces

**Coverage must be complete.** The token set describing this execution's
failures must be non-empty and every token in it must appear in `retry.on`. One
matching check does not authorise a retry of an unrelated failure beside it. An
agent that errors usually fails its `final_message_matches` check as well, so
its token set is `{agent_error, gate:final_message_matches}` and a workflow that
wants to retry it lists both.
"""

from __future__ import annotations

from . import failure as ohfail
from . import attempts
from .run_log import RunState
from .workflow import FORBIDDEN_RETRY_ON, Step

__all__ = ["TIMEOUT", "AGENT_ERROR", "BARE_TOKENS", "failure_tokens",
           "should_retry"]

TIMEOUT = "timeout"
AGENT_ERROR = "agent_error"

#: The tokens that are not a gate check name.
BARE_TOKENS = frozenset({TIMEOUT, AGENT_ERROR})

#: A verdict was reached and it was no. `deferred` is not here on purpose.
RETRYABLE_STATUSES = frozenset({"failed", "timeout", "quarantined"})


def failure_tokens(*, status: str, error: str | None, report,
                   kind: str) -> set[str]:
    """Every independent reason this execution did not succeed.

    Each one must be covered by `retry.on` before a retry is allowed.

    An execution timeout names `timeout` and nothing else from the error string. The
    engine writes its own sentence there - "execution timeout 5400s exceeded" plus
    the agent's last words - so a workflow that selects `timeout` would otherwise
    have to select `agent_error` as well, for a string the engine composed
    rather than a fault of the agent's own. Gate checks that failed beside the
    timeout still need their own selectors.
    """
    tokens: set[str] = set()
    if status == "timeout":
        tokens.add(TIMEOUT)
    elif error and kind == "agent":
        tokens.add(AGENT_ERROR)
    if report is not None:
        tokens.update(report.failed_names())
    return tokens


def should_retry(step: Step, *, status: str, error: str | None, report,
                 abort_victim: bool, aborted: bool, state: RunState,
                 coord: str, fingerprint: str | None,
                 auto_resume: int = 0, killed: bool = False) -> tuple[bool, str]:
    """Decide, and say why. Returns `(retry, reason)`.

    The refusals are checked in this order, and the first one answers.
    """
    if aborted:
        return False, "no retry: the run aborted"

    if killed:
        return False, ("no retry: ohflow kill ended this execution; "
                       "`run --resume` starts the step again")

    if abort_victim:
        # It may already have called the provider. It reached no verdict, and a
        # retry answers a verdict.
        return False, "no retry: the run's abort killed this execution"

    if status == "deferred":
        return False, ("no retry: the step was deferred on a transient fault "
                       "and reached no verdict; auto-resume owns it")

    if status not in RETRYABLE_STATUSES:
        return False, f"no retry: status {status!r} is not a failure"

    if step.kind != "agent":
        # A command, a merge and a bare gate are deterministic, which is why
        # `failure.classify` calls their failures structural without reading any
        # text. Repeating a merge that already conflicted gives that conflict
        # again. `workflow.validate` refuses `retry.max > 0` on these, so this is a
        # guard and not a path.
        return False, (f"no retry: a {step.kind!r} step is deterministic and "
                       f"repeating it gives the same answer")

    if step.retry.max <= 0:
        return False, "no retry: the step declares no retry budget"

    failed = set(report.failed_names()) if report is not None else set()
    forbidden = sorted(failed & FORBIDDEN_RETRY_ON)
    if forbidden:
        # This beats every selector. Those two mean the agent did the wrong
        # thing, and the same brief produces the same wrong thing.
        return False, (f"no retry: {', '.join(forbidden)} failed, and that "
                       f"means the agent did the wrong thing")

    tokens = failure_tokens(status=status, error=error, report=report,
                            kind=step.kind)
    if not tokens:
        return False, "no retry: nothing named this execution's failure"

    allowed = set(step.retry.on)
    uncovered = sorted(tokens - allowed)
    if uncovered:
        return False, (f"no retry: {', '.join(uncovered)} not in retry.on "
                       f"{sorted(allowed)}; every failure must be covered")

    signature = ohfail.provider_structural(error)
    if signature:
        # Checked whatever the tokens say, including for an execution timeout whose
        # text carries the refusal. Sending the same brief to a provider that
        # answered 401 spends a second call to hear 401 again, and a context
        # window already exceeded is exceeded again by the same brief.
        return False, (f"no retry: the provider refused structurally "
                       f"({signature!r}), and repeating the request cannot "
                       f"change that")

    return attempts.may_start(state, coord, fingerprint, start_kind="retry",
                              retry_max=step.retry.max, auto_resume=auto_resume)
