"""The shipped surface of ohflow holds no value of one operator's machine.

An operator's own values live in `ohflow.settings.local.json`,
`references/local.md` and the Worker's `worker/pi-cloud.settings.local.json`
and `worker/snapshot/AGENTS.local.md`, which git ignores. Everything else under ohflow
that git would commit, outside the recorded evidence, is the shipped surface:
the code, the shipped settings, the skill and its references, the setup
examples and the test code.

Two rules hold on that surface:

- No absolute path names a real home directory. The setup examples and the
  tests use the placeholder users `<user>`, `alex` and `agent`.
- No line holds a token from the operator's private token list. The list
  names the operator's hosts, accounts and people, so it lives outside the
  repository: `OHFLOW_LEAK_TOKENS`, else `~/.config/ohflow/leak-tokens.txt`,
  one literal per line, matched case-insensitively between non-letters. The
  public repository's own name, `PUBLIC_REPOSITORY`, is no token. On a
  machine with no list that half of the scan is skipped and says so.

Recorded evidence is out of scope: `docs/`, the design-review captures in
`.impeccable/`, the run briefs and reviews in
`references/examples/`, and `tests/fixtures/`. The release extraction reviews
it separately, because a recording keeps the paths it was taken with.
"""

from __future__ import annotations

import os
import re
import subprocess
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]

SCANNED_SUFFIXES = {".py", ".ts", ".sh", ".js", ".mjs", ".vbs", ".json",
                    ".html", ".css", ".md", ".ps1", ".toml", ".txt"}
EVIDENCE_PREFIXES = ("docs/", "references/examples/", "tests/fixtures/", ".impeccable/")
PLACEHOLDER_USERS = {"alice", "alex", "agent", "someone", "<user>", "user"}

PUBLIC_REPOSITORY = re.compile(re.escape("esinecan/ohflow"), re.IGNORECASE)

HOME_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/]+Users[\\/]+|/Users/|/home/)([^\\/\s\"'`]+)")


def token_file() -> Path:
    raw = os.environ.get("OHFLOW_LEAK_TOKENS")
    if raw:
        return Path(raw)
    return Path.home() / ".config" / "ohflow" / "leak-tokens.txt"


def shipped_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "-C", str(SKILL), "ls-files", "--cached", "--others",
         "--exclude-standard", "--", "."],
        capture_output=True, text=True, check=True, encoding="utf-8").stdout
    files = []
    for rel in listed.splitlines():
        if rel.startswith(EVIDENCE_PREFIXES):
            continue
        path = SKILL / rel
        if path == Path(__file__).resolve():
            continue
        if path.suffix.lower() in SCANNED_SUFFIXES and path.is_file():
            files.append(path)
    return files


def lines_of(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), 1):
        yield number, line


def where(path: Path, number: int, line: str) -> str:
    return f"{path.relative_to(SKILL).as_posix()}:{number}: {line.strip()[:120]}"


class ShippedSurface(unittest.TestCase):

    def setUp(self):
        self.files = shipped_files()

    def test_the_surface_is_found(self):
        names = {p.relative_to(SKILL).as_posix() for p in self.files}
        self.assertIn("SKILL.md", names)
        self.assertIn("ohflow.settings.json", names)
        self.assertIn("scripts/ohflow/settings.py", names)
        self.assertNotIn("ohflow.settings.local.json", names)
        self.assertNotIn("references/local.md", names)
        self.assertIn("worker/pi-cloud.settings.json", names)
        self.assertIn("worker/snapshot/recipe.mjs", names)
        self.assertNotIn("worker/pi-cloud.settings.local.json", names)
        self.assertNotIn("worker/snapshot/AGENTS.local.md", names)

    def test_no_path_names_a_real_home_directory(self):
        hits = []
        for path in self.files:
            for number, line in lines_of(path):
                for match in HOME_PATH.finditer(line):
                    if match.group(1).lower() not in PLACEHOLDER_USERS:
                        hits.append(where(path, number, line))
        self.assertEqual(hits, [], "a shipped file names a real home directory")

    def test_no_line_holds_a_private_token(self):
        source = token_file()
        if not source.is_file():
            self.skipTest(f"no private token list at {source}")
        tokens = [t.strip() for t in source.read_text(encoding="utf-8").splitlines()
                  if t.strip() and not t.startswith("#")]
        pattern = re.compile(
            r"(?<![A-Za-z])(?:" + "|".join(re.escape(t) for t in tokens) + r")(?![A-Za-z])",
            re.IGNORECASE)
        hits = []
        for path in self.files:
            for number, line in lines_of(path):
                if pattern.search(PUBLIC_REPOSITORY.sub("", line)):
                    hits.append(where(path, number, line))
        self.assertEqual(hits, [], f"a shipped file holds a token from {source}")


if __name__ == "__main__":
    unittest.main()
