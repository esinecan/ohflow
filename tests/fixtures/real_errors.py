"""Real provider and agent error text, lifted from a preserved run.

Nothing in this file was written by hand. Every string below was copied out of

    ~/ohflow-home/workflows/sample-architecture-map/runs/r-20260916-120343

on **2026-09-16**, by reading that run's `journal.jsonl` and its step
`result.json` files. The copy names the home folder `<user>`, the run store
`ohflow-home` and the workflow `sample-architecture-map`, and every other byte
is the run's own. That run is read-only preserved evidence and this suite
never opens it again: the strings live here so the tests keep working on a
machine that has never seen it.

The run itself: workflow `sample-architecture-map`, phase `01.evidence-scouts`, nine
agent steps against `openai/glm-5.3-flash` at
`https://api.z.ai/api/coding/paas/v4`, `max_parallel` 3. Three steps produced
their own failures and the six that had not started yet were killed by the
phase's `abort` policy.

Why real text matters here. `ohflow.failure.classify` decides between a pause
and a total abort by matching a regular expression against whatever the provider
and the SDK happened to write. Invented text proves the regular expression
matches the invention. These four strings are what a live Z.AI rate limit, a
Windows terminal fault and an abort cascade actually looked like.

One property no hand-written string would have reproduced: the SDK prints its
errors through `rich`, which hard-wraps them into a box at the console width.
`Rate limit reached for requests` therefore arrives split across two lines with
box-drawing characters and column padding in between. A pattern that required
that whole phrase on one line would not match the real text.
"""

from __future__ import annotations

__all__ = [
    "SCOUT2_RATE_LIMIT_RESULT_ERROR",
    "SCOUT3_RATE_LIMIT_LOG_TAIL",
    "SCOUT1_TERMINAL_FAULT_LOG_TAIL",
    "ABORT_VICTIM_ERROR",
    "CP1252_KILLER_LINES",
    "PROVENANCE",
    "PI_PHASE0_RATE_LIMIT_ERROR",
    "PI_PHASE0_UNAUTHORIZED_ERROR",
    "PI_PHASE0_BAD_REQUEST_ERROR",
    "PI_PHASE0_PROVIDER_PROVENANCE",
]


# ---------------------------------------------------------------------------
# 1. The clearest live rate limit in the run.
#
# Source: phases/01.evidence-scouts/02.scout-agent-lifecycle/result.json, key
# "error". The agent's own child process wrote this: it caught the exception
# from `Conversation.run()` and recorded the text. The step ran 1606.1 s and
# spent 4,920,983 prompt tokens before the provider refused it.
#
# `failure.classify` must call this TRANSIENT. In the run it did not, the phase
# aborted, and six untouched steps died with it.
SCOUT2_RATE_LIMIT_RESULT_ERROR = 'ConversationRunError: Conversation run failed for id=c52c8fb8-864c-464a-a773-8b9e63efe22b: litellm.RateLimitError: RateLimitError: OpenAIException - Rate limit reached for requests\n\nConversation logs are stored at: C:\\Users\\<user>\\ohflow-home\\workflows\\sample-architecture-map\\runs\\r-20260916-120343\\phases\\01.evidence-scouts\\02.scout-agent-lifecycle\\conversations\\c52c8fb8864c464aa7738b9e63efe22b\n\nTo help debug this issue, please file a bug report at:\n  https://github.com/OpenHands/software-agent-sdk/issues/new\nand attach the conversation logs from the directory above.'


# ---------------------------------------------------------------------------
# 2. The same rate limit, seen the other way: through a killed child's log.
#
# Source: journal.jsonl, the `step_finished` event for
# 01.evidence-scouts/03.scout-temporal, key payload.error. The child exited
# non-zero without writing result.json, so `HostHarnessExecutor.collect` returned the last
# 2000 characters of logs/host_runner.err.log and the engine prefixed its own
# sentence. The provider's words are at the very end, wrapped by `rich`.
#
# This is the string the execution-timeout fix exists for: the engine used to replace
# it with its own timeout sentence, leaving the classifier nothing to read.
SCOUT3_RATE_LIMIT_LOG_TAIL = 'host_runner exited 1\n                             │   213 │   def send_ke │                         \n                             │   214 │   │   """Send │                         \n                             │   215 │   │   if self │                         \n                             │ > 216 │   │   │   rai │                         \n                             │   217 │   │           │                         \n                             │   218 │   │   upper = │                         \n                             │   219 │   │   ctrl =  │                         \n                             └───────────────────────┘                         \n                             RuntimeError: Cannot send                         \n                             keys: PowerShell process                          \n                             is not running                                    \n[09/16/26 12:07:05] INFO     Auto-detected: Using                factory.py:156\n                             WindowsTerminal (PowerShell                       \n                             backend)                                          \n[09/16/26 12:07:07] INFO     Terminal session reset successfully    impl.py:412\n                             with working_dir:                                 \n                             C:\\Users\\<user>\\ohflow-home\\wo                    \n                             rkflows\\sample-architecture-map\\worktr            \n                             ees\\temporal                                      \n[09/16/26 12:31:22] ERROR    litellm.RateLimitError:         retry_mixin.py:140\n                             RateLimitError: OpenAIException                   \n                             - Rate limit reached for                          \n                             requests. Attempt #1 | You can                    \n                             customize retry values in the                     \n                             configuration.                                    \n'


# ---------------------------------------------------------------------------
# 3. A real failure that is NOT transient, from the same phase and the same
#    minute. It is here so a test can prove the classifier still says no.
#
# Source: journal.jsonl, the `step_finished` event for
# 01.evidence-scouts/01.scout-topology, key payload.error. Same shape as the one
# above - a non-zero exit plus a log tail - but the tail carries a Windows
# terminal fault, `RuntimeError: Cannot send keys: PowerShell process is not
# running`, and no rate limit at all. Waiting changes nothing about it.
SCOUT1_TERMINAL_FAULT_LOG_TAIL = 'host_runner exited 1\n                             │ env\\Lib\\site-packages │                         \n                             │ \\openhands\\tools\\term │                         \n                             │ inal\\terminal\\windows │                         \n                             │ _terminal.py:216 in   │                         \n                             │ send_keys             │                         \n                             │                       │                         \n                             │   213 │   def send_ke │                         \n                             │   214 │   │   """Send │                         \n                             │   215 │   │   if self │                         \n                             │ > 216 │   │   │   rai │                         \n                             │   217 │   │           │                         \n                             │   218 │   │   upper = │                         \n                             │   219 │   │   ctrl =  │                         \n                             └───────────────────────┘                         \n                             RuntimeError: Cannot send                         \n                             keys: PowerShell process                          \n                             is not running                                    \n[09/16/26 12:11:21] INFO     Auto-detected: Using                factory.py:156\n                             WindowsTerminal (PowerShell                       \n                             backend)                                          \n[09/16/26 12:11:22] INFO     Terminal session reset successfully    impl.py:412\n                             with working_dir:                                 \n                             C:\\Users\\<user>\\ohflow-home\\wo                    \n                             rkflows\\sample-architecture-map\\worktr            \n                             ees\\topology                                      \n'


# ---------------------------------------------------------------------------
# 4. What an abort victim was recorded as.
#
# Source: journal.jsonl, the `step_finished` events for scouts 4 through 9. All
# six carry status "failed" and this exact error string. None of them ever
# called the provider. Relabelling them `deferred` is the defect this string
# guards.
ABORT_VICTIM_ERROR = 'run aborted'


# ---------------------------------------------------------------------------
# 5. Characters that crashed a console write on this box.
#
# Every one of these appears in the two log tails above. cp1252 is the ANSI code
# page here, it carries none of them, and `print` raises `UnicodeEncodeError` on
# each. That exception killed the thread that was logging, not just the line.
#
# The first entry is a real slice of scout 1's log tail, so the test writes text
# the engine genuinely tried to write.
CP1252_KILLER_LINES = (
    SCOUT1_TERMINAL_FAULT_LOG_TAIL[:400],
    "│ box drawing vertical",
    "─── horizontal rule",
    "└┘ corners",
    "an em dash — and an arrow →",
)


# ---------------------------------------------------------------------------
# 6. pi's byte-exact provider errorMessage values.
#
# Source: the message_end records in Phase 0's raw JSON event streams.  These
# are the values a pi process returns while still exiting zero; the runner must
# therefore classify the event, not infer success from the process exit code.
PI_PHASE0_RATE_LIMIT_ERROR = (
    '429: {"message":"Rate limit reached for requests",'
    '"type":"rate_limit_error","param":null,"code":"rate_limit_exceeded"}'
)
PI_PHASE0_UNAUTHORIZED_ERROR = (
    '401: {"message":"Phase 0 unauthorized",'
    '"type":"authentication_error","param":null,"code":"invalid_api_key"}'
)
PI_PHASE0_BAD_REQUEST_ERROR = (
    '400: {"message":"Phase 0 bad request",'
    '"type":"invalid_request_error","param":null,"code":"bad_request"}'
)

PI_PHASE0_PROVIDER_PROVENANCE = {
    "probe": "part2/01-provider-errors",
    "recorded_on": "2026-09-28",
    "source_root": (
        "~/ohflow-home/experiments/"
        "oh-dispatch-pi-parity-2026-09-27/probes/part2/01-provider-errors"
    ),
    "sources": {
        "PI_PHASE0_RATE_LIMIT_ERROR": "429-disabled/events.jsonl message_end .message.errorMessage",
        "PI_PHASE0_UNAUTHORIZED_ERROR": "401/events.jsonl message_end .message.errorMessage",
        "PI_PHASE0_BAD_REQUEST_ERROR": "400/events.jsonl message_end .message.errorMessage",
    },
}


PROVENANCE = {
    "run": "r-20260916-120343",
    "workflow": "sample-architecture-map",
    "model": "openai/glm-5.3-flash",
    "base_url": "https://api.z.ai/api/coding/paas/v4",
    "lifted_on": "2026-09-16",
    "lifted_from": (
        "~/ohflow-home/workflows/sample-architecture-map/"
        "runs/r-20260916-120343"
    ),
    "sources": {
        "SCOUT2_RATE_LIMIT_RESULT_ERROR":
            "phases/01.evidence-scouts/02.scout-agent-lifecycle/result.json .error",
        "SCOUT3_RATE_LIMIT_LOG_TAIL":
            "journal.jsonl step_finished 01.evidence-scouts/03.scout-temporal .payload.error",
        "SCOUT1_TERMINAL_FAULT_LOG_TAIL":
            "journal.jsonl step_finished 01.evidence-scouts/01.scout-topology .payload.error",
        "ABORT_VICTIM_ERROR":
            "journal.jsonl step_finished 01.evidence-scouts/04..09 .payload.error",
    },
}
