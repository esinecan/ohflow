"""Why a step failed: transient or structural.

A phase policy of `abort` is the right answer to an agent that did the wrong
thing. It is the wrong answer to a provider that answered 429. In the Cortea
run three agents hit a rate limit after 27 minutes each, the abort fired, and
the six agents that had not started yet died in about a second each without
ever calling the provider. The work was lost for a reason that had nothing to
do with the work.

This module names the difference.

  transient   the step never got a fair turn: rate limit, provider overload,
              5xx, a dropped or timed-out connection. Waiting can change the
              answer.
  structural  the step got its turn and the answer was no: a failed gate, a
              schema violation, an auth rejection, a bad brief, a non-zero exit
              from a deterministic command. Waiting changes nothing.

Two rules hold the line:

  * An `ownership` or `no_ai_attribution` gate failure is structural whatever
    the error text says. Those two mean the agent did the wrong thing, and
    `workflow.FORBIDDEN_RETRY_ON` already forbids retrying them.
  * Text that matches nothing is structural. The default must never weaken an
    abort; a new transient signature is a deliberate addition to this file.

An agent can outlive `execution_timeout_s` while the provider is rate-limiting
it, and the engine then kills it. That kill is not a verdict on the work, so an
agent timeout is classified from its text like any other agent failure, and
unrecognised text is still structural. A `command`, `merge` or `gate` timeout
stays structural without reading any text: those are deterministic and their
clock running out is the answer.
"""

from __future__ import annotations

import re

from .workflow import FORBIDDEN_RETRY_ON

__all__ = ["TRANSIENT", "STRUCTURAL", "classify", "explain",
           "provider_structural"]

TRANSIENT = "transient"
STRUCTURAL = "structural"

# Checked first. A structural signature beats a transient one in the same text,
# because "401 while retrying after a 429" is an auth problem.
_STRUCTURAL = re.compile(
    r"authenticationerror"
    r"|permissiondeniederror"
    r"|invalid[ _-]?api[ _-]?key|incorrect api key|invalid_api_key"
    r"|\b(401|403|404|400)\b"
    r"|unauthorized|forbidden"
    r"|contextwindowexceeded|context_length_exceeded|maximum context length"
    r"|badrequesterror|invalidrequesterror"
    r"|model_not_found|notfounderror"
    r"|insufficient_quota"          # an empty account; waiting does not fill it
    , re.IGNORECASE)

_TRANSIENT = re.compile(
    r"ratelimiterror|rate[ _-]?limit|\b429\b|too many requests|usage limit"
    r"|overloaded|overloadederror|server is busy|capacity"
    r"|serviceunavailable|service unavailable|temporarily unavailable"
    r"|internalservererror|internal server error|bad gateway|gateway time-?out"
    r"|\b(500|502|503|504)\b"
    r"|apiconnectionerror|connectionerror|apierror: connection"
    r"|connection reset|connection aborted|connection refused"
    r"|remote end closed|broken pipe"
    r"|read timed out|readtimeout|request timed out|timeouterror"
    r"|econnreset|etimedout|socket hang up"
    , re.IGNORECASE)


def classify(*, error: str | None, report=None, kind: str = "agent",
             status: str = "failed") -> str:
    """Name the failure. Returns `TRANSIENT` or `STRUCTURAL`.

    `error` is the step's error string, `report` its `gates.GateReport`,
    `kind` the step kind, `status` the status the engine computed before this
    call.
    """
    if report is not None and set(report.failed_names()) & FORBIDDEN_RETRY_ON:
        return STRUCTURAL

    # A command, a merge and a bare gate are deterministic. Their exit code is
    # the answer, and so is their clock running out.
    if kind in ("command", "merge", "gate"):
        return STRUCTURAL

    # Every remaining case, the engine's own execution timeout included, is read from
    # the text. `status` is kept in the signature because a caller passes it and
    # because a future rule may need it.
    _ = status
    text = error or ""
    if not text.strip():
        # No error at all means the gate judged real work and said no.
        return STRUCTURAL
    if _STRUCTURAL.search(text):
        return STRUCTURAL
    if _TRANSIENT.search(text):
        return TRANSIENT
    return STRUCTURAL


def explain(error: str | None) -> str | None:
    """The transient signature that matched, for the run log. None if none did."""
    m = _TRANSIENT.search(error or "")
    return m.group(0) if m else None


def provider_structural(error: str | None) -> str | None:
    """The recognised structural provider signature in this text, or None.

    `classify` answers a different question. It calls a plain failed gate
    structural too, because waiting changes nothing about a gate that said no.
    This one answers whether the provider itself refused in a way that repeating
    the request cannot fix: a rejected key, a 400, 401, 403 or 404, a context
    window already exceeded, an account with no quota left.

    `ohflow.retry` uses it to stop an `agent_error` selector from authorising a
    retry of one of those. Sending the same brief to a provider that answered
    401 spends a second call to hear 401 again.
    """
    m = _STRUCTURAL.search(error or "")
    return m.group(0) if m else None
