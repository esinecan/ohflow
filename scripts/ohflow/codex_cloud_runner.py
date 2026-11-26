"""The `codex-cloud` harness executor: Codex in the pi-cloud Worker; see `cli_cloud_runner`."""

from __future__ import annotations

from .cli_cloud_runner import CliCloud

CLOUD = CliCloud("codex")
EVENT_LOG = CLOUD.event_log
agent_errors = CLOUD.agent_errors
usage = CLOUD.usage
activity = CLOUD.activity
resume_target = CLOUD.resume_target
reattach_target = CLOUD.reattach_target
transcript = CLOUD.transcript
preflight = CLOUD.preflight
make_harness_executor = CLOUD.make_harness_executor
main = CLOUD.main

if __name__ == "__main__":
    raise SystemExit(main())
