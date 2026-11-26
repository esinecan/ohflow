"""A fake harness executor that does the roll-call task: write a file, commit, report JSON.

`FakeHarnessExecutor` runs no process and changes no file, so a roll-call gate (commits
past the start, a clean tree, ownership) would always fail against it.
`RollcallHarnessExecutor` reads the brief of each step, does what the brief asks in the
step's worktree, and answers with the report block the workflow's schema wants.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

from support import FakeHarnessExecutor, AgentScript  # noqa: E402

JUDGE_STEP = "01.judge/01.judge"
HARNESS_EXECUTORS = ("pi", "claude", "codex")

ENTRY = ("- Harness: fake harness 1.0\n- Model: fake/deterministic\n"
         "- Working directory: {cwd}\n- Tools: terminal\n- MCP servers: none\n"
         "- Cannot: reach a real model\n")


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "user.name=fake agent",
                           "-c", "user.email=fake@localhost", *args],
                          cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8")
    return done.stdout.strip()


def report(harness_executor: str) -> dict:
    return {"harness_executor": harness_executor, "status": "PRESENT", "harness": "fake harness 1.0",
            "model": "fake/deterministic", "tools": [], "mcp_servers": [],
            "cannot": "reach a real model"}


class RollcallHarnessExecutor(FakeHarnessExecutor):
    """Does the task of each roll-call brief. `skip` names step ids whose
    agent commits nothing, so their gate fails."""

    def __init__(self, *, judge: AgentScript | None = None,
                 skip: tuple[str, ...] = (), preflight_faults=(), **kw):
        scripts = {JUDGE_STEP: judge} if judge is not None else {}
        super().__init__(scripts=scripts, **kw)
        self.skip = set(skip)
        self.faults = list(preflight_faults)
        self.attempts: dict[str, int] = {}

    def preflight(self) -> list[str]:
        return list(self.faults)

    def launch(self, spec: dict, out_dir: Path):
        handle = super().launch(spec, out_dir)
        if JUDGE_STEP in spec["coord"]:
            return handle
        sid = spec["coord"].split("/")[-1].split(".", 1)[1]
        self.attempts[sid] = self.attempts.get(sid, 0) + 1
        brief = (Path(out_dir) / "brief.md").read_text(encoding="utf-8")
        position = Path(out_dir) / "position.md"
        position_text = (position.read_text(encoding="utf-8")
                         if position.exists() else "")
        cwd = Path(spec["workspace"])
        final, structured = self._work(spec, sid, brief, position_text, cwd)
        script = AgentScript(final_text=final, structured=structured,
                             tokens={"prompt_tokens": 1000,
                                     "completion_tokens": 500})
        if "Your handover, read by" in position_text:
            from ohflow.handover import CORE, AUDIENCES
            headings = [h for h, _ in CORE]
            headings += [h for audience in AUDIENCES.values() for h, _ in audience
                         if f"## {h}\n" in position_text]
            token = re.search(r"Relay token: (RELAY-\S+)", brief)
            script.files = {"handover.md": "\n".join(
                f"## {h}\n{token.group(1) if h == 'Next' and token else 'not established'}\n"
                for h in headings)}
        script.launches = handle.launch_index
        handle.script = script
        return handle

    def _work(self, spec, sid, brief, position_text, cwd):
        harness_executor = spec["harness_executor"]
        if "You review one roll-call file" in brief:
            return "The file is right.\nVERDICT: PASS\n", None
        done = "```json\n" + json.dumps(report(harness_executor)) + "\n```\n"
        if sid in self.skip:
            return done, report(harness_executor)
        if "You consolidate a roll call" in brief:
            ids = sorted(p.stem for p in (cwd / "rollcall").glob("*.md"))
            rows = "".join(f"| {i} | fake harness 1.0 | fake | 1 | 0 |\n"
                           for i in ids)
            (cwd / "ROLLCALL.md").write_text(
                "# Roll call\n\n| agent | harness | model | tools | mcp servers |\n"
                "|---|---|---|---|---|\n" + rows, encoding="utf-8")
            self._commit(cwd, "ROLLCALL.md", "rollcall: consolidate")
        elif "relay roll call" in brief:
            path = cwd / "ROLLCALL.md"
            text = path.read_text(encoding="utf-8") if path.exists() \
                else "# Roll call\n"
            handed = position_text.split("Your handover, read by", 1)[0]
            token = re.search(r"RELAY-\d+-a91c7e", handed)
            path.write_text(text + f"\n## {sid}\n" + ENTRY.format(cwd=cwd)
                            + "- Previous: fake harness 1.0\n"
                            + (f"- Previous token: {token.group(0)}\n" if token else ""),
                            encoding="utf-8")
            self._commit(cwd, "ROLLCALL.md", f"rollcall relay: {sid}")
        else:
            body = f"# {sid}\n\n" + ENTRY.format(cwd=cwd)
            token = re.search(r"ROLLCALL-RETRY-\w+", position_text)
            if token:
                body += f"{token.group(0)}\n"
            line = re.search(r"Campaign-Token: \S+", brief)
            if line:
                body += f"{line.group(0)}\n"
            target = cwd / "rollcall" / f"{sid}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            self._commit(cwd, f"rollcall/{sid}.md", f"rollcall: {sid}")
        return done, report(harness_executor)

    @staticmethod
    def _commit(cwd: Path, path: str, message: str) -> None:
        git(cwd, "add", path)
        git(cwd, "commit", "-m", message)


def resolver(harness_executor: FakeHarnessExecutor, bad: dict | None = None):
    """A harness executor resolver. `bad` maps a harness executor name to a harness executor of its own."""
    bad = bad or {}
    return lambda name: bad.get(name, harness_executor)


def write_config(path: Path, name: str = "fake-config") -> str:
    """A `--config` file that points every harness executor at the test's fake key."""
    harness_executors = {harness_executor: {"model": "fake/deterministic",
                                            "base_url": "http://127.0.0.1:0/never-called",
                                            "api_key_env": "OHFLOW_TEST_FAKE_KEY"} for harness_executor in HARNESS_EXECUTORS}
    path.write_text(json.dumps({"name": name, "harness_executors": harness_executors}),
                    encoding="utf-8")
    return str(path)
