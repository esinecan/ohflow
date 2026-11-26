"""Build the hermetic tool, skill, model, and MCP tool policy for one pi attempt."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from . import proc
from .paths import bash_exe, posix
from .workflow import mcp_matches_glob
from .signed_in import executable_argv

DEFAULT_TOOLS = ("read", "bash", "edit", "write", "grep", "find", "ls")
SHARED_TOOLS = {
    "terminal": ("bash",),
    "file_editor": ("read", "edit", "write"),
    "task_tracker": (),
}
BUILTIN_BASE_URLS = {
    "zai": "https://api.z.ai/api/coding/paas/v4",
}
MCP_EXTENSION = "builtin:mcp"
MAX_TOOL_NAME_LENGTH = 64
DISCOVERY_TIMEOUT_S = 60


@dataclass(frozen=True)
class PiToolPolicy:
    tools: tuple[str, ...]
    exclude_tools: tuple[str, ...]
    skill_paths: tuple[Path, ...]
    extension_paths: tuple[Path, ...]
    builtin_extensions: tuple[str, ...]
    mcp_config_path: Path | None
    mcp_allow: tuple[str, ...]
    mcp_block: tuple[str, ...]
    offered_tools: tuple[str, ...]


def _unique(items) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item) for item in items if item))


def qualified_tool_name(address: str) -> str:
    """Translate an ohflow ``server.tool`` address to pi's built-in MCP tool name."""
    server, dot, tool = str(address).partition(".")
    if not dot or not server or not tool:
        raise ValueError(f"MCP tool address must be server.tool, got {address!r}")
    name = re.sub(r"[^A-Za-z0-9_]", "_", f"mcp__{server}__{tool}")
    if len(name) <= MAX_TOOL_NAME_LENGTH:
        return name
    digest = hashlib.sha256(f"{server}\0{tool}".encode("utf-8")).hexdigest()[:8]
    return f"{name[:MAX_TOOL_NAME_LENGTH - len(digest) - 1]}_{digest}"


def _refuse_collisions(addresses: tuple[str, ...]) -> None:
    by_name: dict[str, str] = {}
    for address in addresses:
        canonical = qualified_tool_name(address)
        previous = by_name.get(canonical)
        if previous is not None and previous != address:
            raise ValueError(
                f"pi tool-name collision: {previous!r} and {address!r} both "
                f"become {canonical!r}")
        by_name[canonical] = address


def _guard_path() -> Path:
    return Path(__file__).with_name("ohflow-guard.ts").resolve()


def _mapped_tools(tool_policy: Mapping[str, Any]) -> tuple[str, ...]:
    selected = tool_policy.get("only") or ()
    if not selected:
        return DEFAULT_TOOLS
    mapped: list[str] = []
    for name in selected:
        mapped.extend(SHARED_TOOLS.get(str(name), (str(name),)))
    return _unique(mapped)


def _direct_tools(allow: tuple[str, ...]) -> dict[str, list[str]]:
    direct: dict[str, list[str]] = {}
    for address in allow:
        server, _, tool = address.partition(".")
        direct.setdefault(server, [])
        if tool not in direct[server]:
            direct[server].append(tool)
    return direct


def _write_mcp_config(path: Path, servers: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def prepare_pi_tool_policy(spec: Mapping[str, Any], attempt_dir: Path) -> PiToolPolicy:
    """Materialize one attempt's explicit pi tool policy without global state."""
    attempt_dir = Path(attempt_dir)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    tool_policy = spec.get("tools") or {}
    tools = _mapped_tools(tool_policy)
    skills_root = spec.get("skills_dir")
    skill_paths = tuple(Path(str(skills_root)) / str(name)
                        for name in (spec.get("skills") or ()))
    mcp_servers = spec.get("mcp_config") or {}
    mcp_path: Path | None = None
    if mcp_servers:
        mcp_path = attempt_dir / "pi-agent" / "mcp.json"
        _write_mcp_config(mcp_path, {
            str(name): {**dict(mcp_servers[name]), "exposure": "hidden"}
            for name in mcp_servers})
    return PiToolPolicy(
        tools=tools,
        exclude_tools=(),
        skill_paths=skill_paths,
        extension_paths=(_guard_path(),),
        builtin_extensions=(MCP_EXTENSION,) if mcp_servers else (),
        mcp_config_path=mcp_path,
        mcp_allow=_unique(tool_policy.get("allow") or ()),
        mcp_block=_unique(tool_policy.get("block") or ()),
        offered_tools=tools,
    )


def write_pi_agent_dir(spec: Mapping[str, Any], attempt_dir: Path) -> Path:
    """Write a new agent directory that cannot inherit the user's pi rig."""
    attempt_dir = Path(attempt_dir)
    agent_dir = attempt_dir / "pi-agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    model_spec = spec.get("model") or {}
    provider, slash, model_id = str(model_spec.get("model") or "").partition("/")
    if not slash:
        raise ValueError("pi model must be provider/id")
    thinking = str((model_spec.get("params") or {}).get("thinking") or "low")
    settings = {
        "defaultProvider": provider,
        "defaultModel": model_id,
        "defaultThinkingLevel": thinking,
        "quietStartup": True,
        "retry": {
            "enabled": False,
            "maxRetries": 0,
            "baseDelayMs": 50,
            "provider": {"maxRetries": 0, "maxRetryDelayMs": 1000},
        },
        "shellPath": posix(bash_exe()),
    }
    (agent_dir / "settings.json").write_text(
        json.dumps(settings, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    base_url = str(model_spec.get("base_url") or "").rstrip("/")
    built_in = BUILTIN_BASE_URLS.get(provider, "").rstrip("/")
    models_path = agent_dir / "models.json"
    if base_url and base_url != built_in:
        api_key_env = str(model_spec.get("api_key_env") or "")
        custom = {
            "providers": {
                provider: {
                    "api": "openai-completions",
                    "apiKey": f"${api_key_env}",
                    "baseUrl": base_url,
                    "models": [{
                        "id": model_id,
                        "name": model_id,
                        "reasoning": True,
                        "input": ["text", "image"],
                    }],
                }
            }
        }
        models_path.write_text(json.dumps(custom, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        # ModelConfig has no catalog metadata fields. Record that explicitly so
        # collection cannot mistake pi's zero-cost default for a quoted price.
        (agent_dir / "ohflow-model.json").write_text(json.dumps({
            "provider": provider,
            "model": model_id,
            "cost_source": "unpriced",
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        models_path.unlink(missing_ok=True)
        (agent_dir / "ohflow-model.json").unlink(missing_ok=True)
    return agent_dir


def _listed_servers(listing: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(entry.get("name")): entry for entry in listing.get("servers") or ()
            if isinstance(entry, Mapping)}


def _discovery_problems(listing: Mapping[str, Any],
                        servers: tuple[str, ...]) -> list[str]:
    problems = [str(error) for error in listing.get("errors") or ()]
    listed = _listed_servers(listing)
    for server in servers:
        entry = listed.get(server)
        if entry is None:
            problems.append(f"server {server!r} is not listed")
        elif entry.get("state") != "connected":
            error = str(entry.get("error") or "").strip().splitlines()
            problems.append(f"server {server!r} is {entry.get('state')}"
                            + (f": {error[0]}" if error else ""))
    return problems


def _listed_addresses(listing: Mapping[str, Any],
                      servers: tuple[str, ...]) -> tuple[str, ...]:
    listed = _listed_servers(listing)
    return tuple(f"{server}.{tool}" for server in servers
                 for tool in (listed.get(server) or {}).get("tools") or ()
                 if isinstance(tool, str) and tool)


def _selected_addresses(addresses: tuple[str, ...], allow: tuple[str, ...],
                        block: tuple[str, ...]) -> tuple[str, ...]:
    selected = tuple(
        address for address in addresses
        if (not allow or any(mcp_matches_glob(pattern, address)
                             for pattern in allow))
        and not any(mcp_matches_glob(pattern, address) for pattern in block)
    )
    unmatched = tuple(pattern for pattern in allow
                      if not any(mcp_matches_glob(pattern, address)
                                 for address in addresses))
    if unmatched:
        raise ValueError(f"MCP allow patterns matched no tools: {list(unmatched)!r}")
    return selected


def discover_mcp(tool_policy: PiToolPolicy, env: Mapping[str, str],
                 attempt_dir: Path) -> PiToolPolicy:
    if tool_policy.mcp_config_path is None:
        return tool_policy
    config = json.loads(tool_policy.mcp_config_path.read_text(encoding="utf-8"))
    definitions = config.get("mcpServers") or {}
    servers = tuple(definitions)
    child_env = dict(env)
    child_env["PI_CODING_AGENT_DIR"] = str(tool_policy.mcp_config_path.parent)
    command = [*executable_argv("OHFLOW_PI_EXE", "pi", path_fallback=True),
               "mcp", "list", "--json"]
    log_dir = Path(attempt_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        completed = proc.run_managed(command, env=child_env,
                                     timeout=DISCOVERY_TIMEOUT_S, cwd=Path(attempt_dir))
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"pi mcp list did not finish within {DISCOVERY_TIMEOUT_S} s") from None
    (log_dir / "mcp-list.json").write_text(completed.stdout, encoding="utf-8")
    (log_dir / "mcp-list.stderr.log").write_text(completed.stderr, encoding="utf-8")
    try:
        listing = json.loads(completed.stdout)
    except json.JSONDecodeError:
        detail = (completed.stderr or completed.stdout).strip()[-1000:]
        raise RuntimeError(
            f"pi mcp list exited {completed.returncode} without a JSON listing: "
            f"{detail}") from None
    problems = _discovery_problems(listing, servers)
    if problems or completed.returncode:
        raise RuntimeError(
            f"pi mcp list exited {completed.returncode}: "
            + ("; ".join(problems) or completed.stderr.strip()[-1000:]))
    addresses = _listed_addresses(listing, servers)
    _refuse_collisions(addresses)
    selected = _selected_addresses(addresses, tool_policy.mcp_allow, tool_policy.mcp_block)
    direct = _direct_tools(selected)
    for server, definition in definitions.items():
        definition["exposure"] = "hidden"
        definition["toolExposure"] = {tool: "direct" for tool in direct.get(server, ())}
        if not direct.get(server):
            definition["enabled"] = False
    _write_mcp_config(tool_policy.mcp_config_path, definitions)
    canonical = tuple(qualified_tool_name(address) for address in selected)
    blocked = tuple(address for address in addresses if address not in selected)
    return replace(
        tool_policy,
        tools=_unique((*tool_policy.tools, *canonical)),
        exclude_tools=_unique(qualified_tool_name(address) for address in blocked),
        offered_tools=_unique((*tool_policy.tools, *canonical)),
    )
