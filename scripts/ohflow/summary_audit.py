"""The suite's check on every summary the engine writes.

The audit does work only when `OHFLOW_TEST_SUMMARY_SCHEMA` is set. Normal
runs do not set it and take no validation dependency. The test runner sets it before discovery executes, so child CLI and
detached Python processes inherit the same check.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SUMMARY_AUDIT_SCHEMA_ENV = "OHFLOW_TEST_SUMMARY_SCHEMA"
SUMMARY_AUDIT_LOG_ENV = "OHFLOW_TEST_SUMMARY_AUDIT_LOG"


class SummarySchemaAuditError(AssertionError):
    """Test-only suite audit rejected a summary at the write."""


def audit_summary(run_dir: Path, summary: dict[str, Any]) -> None:
    """Validate one summary when the suite's audit is enabled."""
    raw_schema = os.environ.get(SUMMARY_AUDIT_SCHEMA_ENV)
    if not raw_schema:
        return
    from . import gates as ohgates
    schema = json.loads(Path(raw_schema).read_text(encoding="utf-8"))
    errors = ohgates._validate_schema(summary, schema)
    record = json.dumps({
        "pid": os.getpid(),
        "run_dir": str(run_dir),
        "passed": not errors,
        "errors": errors,
    }, separators=(",", ":")) + "\n"
    raw_log = os.environ.get(SUMMARY_AUDIT_LOG_ENV)
    if raw_log:
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        fd = os.open(raw_log, flags, 0o600)
        try:
            os.write(fd, record.encode("utf-8"))
        finally:
            os.close(fd)
    if errors:
        raise SummarySchemaAuditError(
            "Engine summary violated references/summary.schema.json: "
            + "; ".join(errors))
