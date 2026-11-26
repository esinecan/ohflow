"""Suite-wide summary validation, inherited by child Python processes."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from ohflow import summary_audit


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "references" / \
    "summary.schema.json"


class SummarySchemaAudit:
    """Enable the test-only report audit and count its JSONL receipts."""

    def __init__(self) -> None:
        self.checked = 0
        self.rejected = 0
        self.records: list[dict] = []
        self._old_schema = None
        self._old_log = None
        self._log_path: Path | None = None

    def __enter__(self):
        fd, raw_path = tempfile.mkstemp(prefix="ohflow-summary-audit-",
                                        suffix=".jsonl")
        os.close(fd)
        self._log_path = Path(raw_path)
        self._old_schema = os.environ.get(summary_audit.SUMMARY_AUDIT_SCHEMA_ENV)
        self._old_log = os.environ.get(summary_audit.SUMMARY_AUDIT_LOG_ENV)
        os.environ[summary_audit.SUMMARY_AUDIT_SCHEMA_ENV] = str(SCHEMA_PATH)
        os.environ[summary_audit.SUMMARY_AUDIT_LOG_ENV] = str(self._log_path)
        return self

    def __exit__(self, *_exc) -> None:
        assert self._log_path is not None
        try:
            self.records = [json.loads(line) for line in
                            self._log_path.read_text(encoding="utf-8").splitlines()
                            if line.strip()]
            self.checked = len(self.records)
            self.rejected = sum(not record["passed"] for record in self.records)
        finally:
            self._log_path.unlink(missing_ok=True)
            if self._old_schema is None:
                os.environ.pop(summary_audit.SUMMARY_AUDIT_SCHEMA_ENV, None)
            else:
                os.environ[summary_audit.SUMMARY_AUDIT_SCHEMA_ENV] = self._old_schema
            if self._old_log is None:
                os.environ.pop(summary_audit.SUMMARY_AUDIT_LOG_ENV, None)
            else:
                os.environ[summary_audit.SUMMARY_AUDIT_LOG_ENV] = self._old_log
