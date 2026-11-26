"""The pi guard blocks stray writes and bounds shell execution in flight."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from support import TempCase


class PiGuardTests(TempCase):

    def node_guard(self):
        # pi loads this extension through its TS runtime. Plain Node needs an
        # ESM suffix; exercise the same source without relying on parent config.
        original = Path(__file__).parents[1] / "scripts" / "ohflow" / "ohflow-guard.ts"
        guard = self.tmp / "guard.mjs"
        guard.write_bytes(original.read_bytes())
        return guard

    def test_guard_enforces_write_scope_timeout_and_noninteractive_git(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is unavailable")
        guard = self.node_guard()
        workspace = self.tmp / "workspace"
        (workspace / "src" / "nested").mkdir(parents=True)
        outside = self.tmp / "outside.txt"
        script = r'''
import { pathToFileURL } from "node:url";
let hook;
const pi = { on(name, handler) { if (name === "tool_call") hook = handler; } };
const mod = await import(pathToFileURL(process.argv[1]).href);
mod.default(pi);
const call = async (toolName, input) => ({ input, result: await hook({toolName, input}) });
const rows = {};
rows.editOk = await call("edit", {path: "src/nested/ok.py"});
rows.rootPy = await call("edit", {path: "src/root.py"});
rows.crossSlash = await call("write", {path: "tree/a/b.txt"});
rows.charClass = await call("write", {path: "docs/file7.md"});
rows.writeDenied = await call("write", {path: process.argv[3]});
rows.traversalDenied = await call("edit", {path: "../escape.py"});
rows.bashLong = await call("bash", {command: "echo ok", timeout: 999});
rows.bashMissing = await call("bash", {command: "echo ok"});
rows.gitPager = process.env.GIT_PAGER;
process.stdout.write(JSON.stringify(rows));
'''
        env = {
            **__import__("os").environ,
            "OHFLOW_WORKSPACE": str(workspace),
            "OHFLOW_WRITE_SCOPE": json.dumps(["src/**/*.py", "tree/*.txt",
                                         "docs/file[0-9].md"]),
            "OHFLOW_BASH_TIMEOUT_S": "23",
        }
        proc = subprocess.run(
            [node, "--input-type=module", "-e", script, str(guard),
             str(workspace), str(outside)],
            check=True, capture_output=True, text=True, env=env,
        )
        rows = json.loads(proc.stdout)
        self.assertNotIn("result", rows["editOk"])
        self.assertTrue(rows["rootPy"]["result"]["block"])
        self.assertNotIn("result", rows["crossSlash"])
        self.assertNotIn("result", rows["charClass"])
        self.assertTrue(rows["writeDenied"]["result"]["block"])
        self.assertTrue(rows["traversalDenied"]["result"]["block"])
        self.assertEqual(rows["bashLong"]["input"]["timeout"], 23)
        self.assertEqual(rows["bashMissing"]["input"]["timeout"], 23)
        self.assertEqual(rows["gitPager"], "cat")

    def test_guard_resolves_existing_symlink_parents(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unavailable")
        node = shutil.which("node")
        if not node:
            self.skipTest("node is unavailable")
        guard = self.node_guard()
        workspace = self.tmp / "workspace"
        outside = self.tmp / "outside"
        workspace.mkdir()
        outside.mkdir()
        link = workspace / "owned-link"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError:
            made = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
                capture_output=True, text=True)
            if made.returncode:
                self.skipTest(f"directory link unavailable: {made.stderr}")
        # A POSIX symlink goes with unlink; a Windows junction goes with rmdir.
        self.addCleanup(lambda: (link.unlink() if link.is_symlink()
                                 and os.name != "nt" else link.rmdir())
                        if link.exists() else None)
        script = r'''
import { pathToFileURL } from "node:url";
let hook;
const pi = { on(name, handler) { if (name === "tool_call") hook = handler; } };
const mod = await import(pathToFileURL(process.argv[1]).href);
mod.default(pi);
process.stdout.write(JSON.stringify(await hook({
  toolName: "write", input: {path: "owned-link/escape.txt"}
})));
'''
        env = {**os.environ, "OHFLOW_WORKSPACE": str(workspace),
               "OHFLOW_WRITE_SCOPE": json.dumps(["owned-link/**"])}
        proc = subprocess.run([node, "--input-type=module", "-e", script,
                               str(guard)], check=True, capture_output=True,
                              text=True, env=env)
        self.assertTrue(json.loads(proc.stdout)["block"])

    def test_only_the_exact_handover_file_is_allowed_outside_worktree(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is unavailable")
        workspace = self.tmp / "workspace"
        attempt = self.tmp / "attempt"
        workspace.mkdir()
        attempt.mkdir()
        script = r'''
import { pathToFileURL } from "node:url";
let hook;
const pi = { on(name, handler) { if (name === "tool_call") hook = handler; } };
(await import(pathToFileURL(process.argv[1]).href)).default(pi);
const rows = [];
for (const path of process.argv.slice(2)) {
 rows.push((await hook({toolName: "write", input: {path}})) || null);
}
process.stdout.write(JSON.stringify(rows));
'''
        env = {**os.environ, "OHFLOW_WORKSPACE": str(workspace),
               "OHFLOW_WRITE_SCOPE": "[]", "OHFLOW_ATTEMPT_DIR": str(attempt)}
        def check(paths):
            proc = subprocess.run([node, "--input-type=module", "-e", script,
                                   str(self.node_guard()), *map(str, paths)],
                                  env=env, check=True, capture_output=True, text=True)
            return json.loads(proc.stdout)
        rows = check([attempt / "handover.md", attempt / "spec.json",
                      attempt / "sub" / "handover.md", self.tmp / "handover.md"])
        self.assertIsNone(rows[0])
        self.assertTrue(all(row["block"] for row in rows[1:]))
        outside = self.tmp / "outside.md"
        outside.write_text("untouched", encoding="utf-8")
        try:
            os.symlink(outside, attempt / "handover.md")
        except OSError:
            self.skipTest("file symlink creation is unavailable; exact paths were checked")
        self.assertTrue(check([attempt / "handover.md"])[0]["block"])

    def test_real_pi_delivers_guard_mutated_timeout_to_bash_executor(self):
        """A real pi turn, backed by a local deterministic provider."""
        pi_exe = shutil.which("pi.cmd") or shutil.which("pi")
        bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if not pi_exe or not bash.exists():
            self.skipTest("real pi or Git Bash is unavailable")
        guard = Path(__file__).parents[1] / "scripts" / "ohflow" / "ohflow-guard.ts"
        calls = []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                return

            def do_POST(self):
                size = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(size) or b"{}")
                calls.append(body)
                has_result = any(message.get("role") == "tool"
                                 for message in body.get("messages", []))
                if has_result:
                    chunks = [
                        {"id": "guard-2", "object": "chat.completion.chunk",
                         "created": 1, "model": "guard", "choices": [{
                             "index": 0, "delta": {"content": "DONE"},
                             "finish_reason": None}]},
                        {"id": "guard-2", "object": "chat.completion.chunk",
                         "created": 1, "model": "guard", "choices": [{
                             "index": 0, "delta": {}, "finish_reason": "stop"}]},
                    ]
                else:
                    chunks = [
                        {"id": "guard-1", "object": "chat.completion.chunk",
                         "created": 1, "model": "guard", "choices": [{
                             "index": 0, "delta": {"role": "assistant",
                                 "tool_calls": [{"index": 0, "id": "call_guard",
                                     "type": "function", "function": {
                                         "name": "bash", "arguments": json.dumps({
                                             "command": "sleep 1", "timeout": 999})}}]},
                             "finish_reason": None}]},
                        {"id": "guard-1", "object": "chat.completion.chunk",
                         "created": 1, "model": "guard", "choices": [{
                             "index": 0, "delta": {},
                             "finish_reason": "tool_calls"}]},
                    ]
                data = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
                data += "data: [DONE]\n\n"
                encoded = data.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                self.wfile.flush()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(thread.join, 5)

        agent = self.tmp / "agent"
        agent.mkdir()
        (agent / "settings.json").write_text(json.dumps({
            "defaultProvider": "guard-test", "defaultModel": "guard",
            "defaultThinkingLevel": "off", "quietStartup": True,
            "retry": {"enabled": False, "maxRetries": 0,
                      "provider": {"maxRetries": 0}},
            "shellPath": str(bash).replace("\\", "/"),
        }), encoding="utf-8")
        (agent / "models.json").write_text(json.dumps({"providers": {
            "guard-test": {"api": "openai-completions",
                "apiKey": "$GUARD_TEST_KEY",
                "baseUrl": f"http://127.0.0.1:{server.server_address[1]}/v1",
                "models": [{"id": "guard", "name": "guard",
                            "reasoning": False, "input": ["text"]}]}}}),
            encoding="utf-8")
        env = {**os.environ, "PI_CODING_AGENT_DIR": str(agent),
               "PI_OFFLINE": "1", "GUARD_TEST_KEY": "test-only",
               "OHFLOW_WORKSPACE": str(self.tmp), "OHFLOW_WRITE_SCOPE": "[]",
               "OHFLOW_BASH_TIMEOUT_S": "0.05"}
        kwargs = ({"creationflags": subprocess.CREATE_NO_WINDOW}
                  if os.name == "nt" else {})
        proc = subprocess.run([
            pi_exe, "--mode", "json", "-p", "--model", "guard-test/guard",
            "--no-extensions", "--no-skills", "--no-prompt-templates",
            "--no-context-files", "--no-themes", "--offline", "--no-session",
            "--tools", "bash", "-e", str(guard), "--", "Run the requested check."],
            cwd=self.tmp, env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=20, **kwargs)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        events = [json.loads(line) for line in proc.stdout.splitlines()
                  if line.startswith("{")]
        ended = [event for event in events
                 if event.get("type") == "tool_execution_end"]
        self.assertEqual(len(ended), 1, proc.stdout)
        rendered = json.dumps(ended[0])
        self.assertIn("0.05 seconds", rendered)
        self.assertTrue(ended[0]["isError"], ended[0])
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    import unittest
    unittest.main()
