"""Run one Claude Code or Codex step in the pi-cloud Worker's `ContainerHarness` object.

The `claude-cloud` and `codex-cloud` harness executors are the `pi-cloud`
executor with another object behind the same Worker. Each attempt is one
`CliAgent` Durable Object named `<kind>:<key>`, reached under
`<pi_cloud.url>/<kind>/attempts/<key>/...`. The object starts the CLI in a
container restored from the default snapshot, clones the step's start commit
into `/workspace/repo`, pushes the transport branch, and streams pi's event
shapes, so `pi_cloud_runner`'s adapter, its client and `pi_runner`'s readers
serve these executors unchanged. This module adds what differs: the route
prefix, the branch prefix, the model rules and the refusals.

The CLI signs in with the operator's subscription. The Worker holds the Claude Code
token and the Codex login and writes them into the request headers outside
the container, so `api_key_env` stays empty.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from . import pi_cloud_runner as pc
from .cli_harness_executor import CliHarnessExecutor, recover_cli_result
from .harness_executor import AgentLaunchError
from .paths import win
from .signed_in import runner_main
from . import remote_git

__all__ = ["CliCloud"]

MODEL_RULES = {
    "claude": (re.compile(r"claude-[\w.-]+|opus|sonnet|haiku"),
               "a Claude model id such as claude-haiku-4-5-20251001, or the "
               "alias opus, sonnet or haiku"),
    "codex": (re.compile(r"[\w.-]+"), "a Codex model id such as gpt-5.6-luna"),
}


def _on_subscription(result: dict[str, Any]) -> dict[str, Any]:
    """The CLI runs on the operator's subscription, which bills no tokens:
    the model cost is a known zero, whatever the Worker's stream carried."""
    result["cost"] = 0.0
    result["cost_source"] = "subscription"
    return result


def _recover(spec: dict[str, Any], out_dir: Path, events: list[Mapping[str, Any]],
             fallback_error: str) -> tuple[dict[str, Any], str | None]:
    result, final = pc._recover(spec, out_dir, events, fallback_error)
    return _on_subscription(result), final


class CliCloud:
    """Everything one cloud CLI executor answers, bound to its kind."""

    def __init__(self, kind: str):
        self.kind = kind
        self.name = f"{kind}-cloud"
        self.module = f"ohflow.{kind}_cloud_runner"
        self.event_log = f"{self.name}-events.jsonl"
        self.branch_prefix = f"ohflow/{self.name}"
        cloud = self

        class Adapter(pc.PiCloudAdapter):
            name = cloud.name
            event_log_name = cloud.event_log
            stderr_log_name = f"{cloud.name}-stderr.log"
            local_limit = False

            def build_result(self, outcome):
                result, final = super().build_result(outcome)
                effective = (result.get("settings") or {}).get("effective")
                if isinstance(effective, dict):
                    effective.pop("thinking", None)
                return _on_subscription(result), final

        self.Adapter = Adapter

    def url(self) -> str:
        return f"{pc.worker_url()}/{self.kind}"

    def agent_errors(self, where: str, agent: Any) -> list[str]:
        """The faults in an agent spec for this executor.

        The object runs one CLI with its subscription login and the box's six
        MCP servers, plus the skills the step names, which the box fetches
        from the Worker's mirror of the operator's skills repository. A model
        param, a key variable, a base URL, a tool policy, workflow MCP servers
        and a skills folder of this machine have no route into it, so each is
        refused with its reason.
        """
        errs: list[str] = []
        name = self.name
        if agent.agent_profile:
            errs.append(f"{where}: {name} agent.agent_profile must be empty; the "
                        f"Worker's box is the only setup, got {agent.agent_profile!r}")
        model = agent.model
        pattern, wanted = MODEL_RULES[self.kind]
        if not isinstance(model.model, str) or not pattern.fullmatch(model.model):
            errs.append(f"{where}: {name} model must be {wanted}, got {model.model!r}")
        if model.params:
            errs.append(f"{where}: {name} takes no model params; got "
                        f"{sorted(map(str, model.params))}")
        if model.base_url:
            errs.append(f"{where}: {name} model base_url must be empty; the "
                        "Worker routes the CLI to its provider")
        if model.extra_body:
            errs.append(f"{where}: {name} refuses ModelConfig.extra_body")
        if model.api_key_env:
            errs.append(f"{where}: {name} model api_key_env must be empty; the "
                        "Worker holds the subscription login")
        tools = agent.tools
        if tools.preset != "default":
            errs.append(f"{where}: {name} supports only tools.preset='default', "
                        f"got {tools.preset!r}")
        if tools.enable_browser:
            errs.append(f"{where}: {name} refuses enable_browser=True; the box "
                        "offers Playwright MCP instead")
        if tools.enable_sub_agents:
            errs.append(f"{where}: {name} refuses enable_sub_agents=True")
        if tools.only:
            errs.append(f"{where}: {name} refuses tools.only; the CLI keeps its "
                        "own tool set")
        if tools.allow or tools.block:
            errs.append(f"{where}: {name} refuses tools.allow and tools.block; "
                        "the CLI gets every MCP server of the box")
        if agent.mcp_config:
            errs.append(f"{where}: {name} refuses mcp_config; the box serves its "
                        "own MCP servers")
        if agent.skills_dir:
            errs.append(f"{where}: {name} refuses skills_dir; the box fetches "
                        "the named skills from the Worker's mirror of the "
                        "skills repository")
        return errs

    def usage(self, attempt_dir: Path):
        event_log = Path(attempt_dir) / "logs" / self.event_log
        if not event_log.is_file():
            return None, f"{self.name} event log is missing ({event_log})"
        return pc.usage_with_abort(
            pc.pi_runner.event_log_usage(event_log, self.name), attempt_dir)

    def activity(self, attempt_dir: Path, *, now: float | None = None,
                 running: bool = True, limit: int = pc.act.DEFAULT_TOOL_CALLS) -> dict:
        import time
        attempt_dir = Path(attempt_dir)
        now = time.time() if now is None else float(now)
        model = pc.act.model_for(attempt_dir)
        with model.lock:
            path = attempt_dir / "logs" / self.event_log
            lines, reset = model.tail.read(path)
            if reset:
                model.reset()
                lines, _ = model.tail.read(path)
            for raw in lines:
                try:
                    event = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(event, dict):
                    pc.pi_runner.apply_pi_event(model, event)
            beat = pc.act.read_json(attempt_dir / "logs" / "heartbeat.json")
            beat_at = pc.act.epoch(beat.get("at")) if isinstance(beat, dict) else None
            note = pc.act.STARTING_NOTE if not model.replied else None
            return pc.act.activity_out(model, harness_executor=self.name,
                                       root=pc.act.worktree_root(attempt_dir), now=now,
                                       running=running, limit=limit,
                                       fallback_at=beat_at, note=note)

    def resume_target(self, prior_result: Mapping[str, Any], attempt_dir: Path) -> str | None:
        return None

    def reattach_target(self, attempt_dir: Path) -> str | None:
        return pc.reattach_target(attempt_dir)

    def transcript(self, attempt_dir: Path, result: Mapping[str, Any],
                   output: Path | None = None):
        """The transcript the Worker served and the runner copied down, else
        the runner's event log: a running attempt has no copy yet, and a
        killed runner never makes one."""
        for path in (Path(attempt_dir) / "transcript.md",
                     Path(attempt_dir) / "logs" / self.event_log):
            if path.is_file():
                return path, None
        return None, f"no {self.name} transcript and no logs/{self.event_log}"

    def preflight(self) -> list[str]:
        """The Worker answers, and for Codex it holds a login."""
        faults = pc.preflight()
        if faults or self.kind != "codex":
            return faults
        try:
            text = pc._send("GET", f"{pc.worker_url()}/codex/login", None,
                            route="GET codex/login", timeout=pc.PREFLIGHT_TIMEOUT_S)
            status = json.loads(text)
        except (RuntimeError, ValueError) as error:
            return [str(error)]
        if not status.get("seeded"):
            return [f"the pi-cloud Worker holds no Codex login; run "
                    f"`node worker/scripts/codex-login.mjs` in the ohflow skill folder"]
        return []

    def recover_result(self, spec_path: Path, out_dir: Path, fallback_error: str) -> dict[str, Any]:
        return recover_cli_result(spec_path, out_dir, fallback_error,
                                  event_log_name=self.event_log, parser=json.loads,
                                  builder=_recover)

    def make_harness_executor(self):
        cloud = self

        class Executor(CliHarnessExecutor):
            def __init__(self):
                super().__init__(name=cloud.name, runner_module=cloud.module,
                                 recovery=cloud.recover_result,
                                 checks=cloud.preflight)

            def launch(self, spec: dict, out_dir: Path):
                out_dir = Path(out_dir)
                try:
                    if spec.get("reattach"):
                        if not (out_dir / "remote.json").is_file():
                            raise ValueError(f"{win(out_dir)} holds no remote.json to reattach")
                    else:
                        workspace = Path(str(spec["workspace"]))
                        remote_url = remote_git.remote_url(workspace)
                        key = remote_git.attempt_key(str(spec["coord"]),
                                                     int(spec.get("attempt") or 1), out_dir)
                        branch = f"{cloud.branch_prefix}/{key}"
                        start_sha = remote_git.push_start(workspace, branch)
                        (out_dir / "remote.json").write_text(json.dumps({
                            "url": cloud.url(), "key": key, "branch": branch,
                            "remote_url": remote_url, "start_sha": start_sha}, indent=2),
                            encoding="utf-8")
                except (ValueError, RuntimeError) as e:
                    raise AgentLaunchError(f"{cloud.name} launch failed: {e}") from e
                return super().launch(spec, out_dir)

            def kill(self, handle) -> None:
                super().kill(handle)
                pc.abort_killed_attempt(handle.out_dir)

        return Executor()

    def main(self, argv: list[str] | None = None) -> int:
        return runner_main(self.Adapter, argv)
