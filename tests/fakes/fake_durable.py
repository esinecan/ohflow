"""A fake `ssh` and `scp` for the durable harness executor.

`OHFLOW_DURABLE_SSH` and `OHFLOW_DURABLE_SCP` both point here. The box is one
temp directory (`OHFLOW_FAKE_DURABLE_HOME`) holding the real host's layout:

    <home>/.pi-durable/ohflow-host/<version>/   the installed host
    <home>/.pi-durable/ohflow/<key>/            spec.json, brief.md, session.sqlite ...

`ssh <box> node` with the installer on stdin writes the bundled files where
the real installer does and prints `durable_host`. `prepare` and `run` refuse a host script that is not
installed, as node would.

`prepare` prints `durable_prepared`. `run` reads the spec the adapter sent,
replays one of the three recordings in `tests/fixtures/durable`, commits one
file on the step's branch in the test's bare Origin and prints a `durable_end`
naming that commit. `OHFLOW_FAKE_DURABLE_SCENARIO` selects the behaviour:

- `success`  replay `single-events.jsonl`, commit, `durable_end`.
- `killed`   replay `killed-events.jsonl`, leave `session.sqlite` behind and
             exit 255 with no `durable_end`: what a dropped ssh connection
             looks like to the runner.
- `reattach` replay `reattach-events.jsonl` (the replayed transcript, the
             interrupted tool result, the rerun), commit, `durable_end`.

`ssh <box> exit` answers 0 and `ssh <box> node --version` prints a version
(`OHFLOW_FAKE_DURABLE_NODE_VERSION`, v24.11.1 by default), because the box this
fake plays is up.
"""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "durable"
HOME = Path(os.environ["OHFLOW_FAKE_DURABLE_HOME"])
SCENARIO = os.environ.get("OHFLOW_FAKE_DURABLE_SCENARIO", "success")
WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def positional(argv):
    """The argv without ssh/scp options and their values."""
    out, i = [], 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-o", "-P", "-p", "-i", "-l"):
            i += 2
            continue
        if arg.startswith("-") and arg != "-":
            i += 1
            continue
        out.append(arg)
        i += 1
    return out


def emit(record):
    sys.stdout.write(json.dumps(record, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def remote_path(text, base):
    """`box:<path>` as a local path under the fake's home, or None for local."""
    if ":" in text and not text[1:2] == ":":
        box, _, rest = text.partition(":")
        if box and not box.startswith(("/", "\\")):
            return base / rest
    return None


def git(*args, cwd=None):
    done = subprocess.run(["git", *args], cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", creationflags=WINDOW)
    if done.returncode != 0:
        sys.stderr.write(done.stderr or done.stdout)
        raise SystemExit(3)
    return done.stdout.strip()


def do_scp(argv):
    words = positional(argv)
    sources, target = words[:-1], words[-1]
    far = [w for w in sources if remote_path(w, HOME) is not None]
    if far:                                             # copy down off the box
        for word in sources:
            src = remote_path(word, HOME)
            if src is None or not src.is_file():
                sys.stderr.write(f"{word}: no such file\n")
                raise SystemExit(1)
            dest = Path(target)
            if dest.is_dir():
                dest = dest / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
        raise SystemExit(0)
    folder = remote_path(target, HOME)                  # copy up onto the box
    folder.mkdir(parents=True, exist_ok=True)
    for word in sources:                                # local files
        dest = folder / Path(word).name
        dest.write_bytes(Path(word).read_bytes())
    raise SystemExit(0)


def replay(path, spec, key, head, session):
    """The recording with this attempt's own key, dir, branch and commit."""
    durable = spec.get("durable") or {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        kind = record.get("type")
        if kind == "durable_start":
            record.update(key=key,
                          dir=str((session.parent).resolve()),
                          reattach=SCENARIO == "reattach")
        elif kind == "durable_end":
            record.update(start=durable.get("start_sha"),
                          branch=durable.get("branch"), head=head,
                          session=str(session.resolve()))
        emit(record)


def commit_on_branch(spec, work, key):
    durable = spec.get("durable") or {}
    if not (work / ".git").exists():
        git("clone", "--no-checkout", durable["remote_url"], str(work))
    git("checkout", "--detach", durable["start_sha"], cwd=work)
    git("config", "user.name", "fake durable host", cwd=work)
    git("config", "user.email", "durable@localhost", cwd=work)
    (work / "rollcall").mkdir(exist_ok=True)
    (work / "rollcall" / f"{key}.md").write_text(
        f"# {key}\nfake durable work\n", encoding="utf-8")
    git("add", "-A", cwd=work)
    git("commit", "-m", "rollcall: durable fake", cwd=work)
    git("push", "--force", "origin", f"HEAD:refs/heads/{durable['branch']}",
        cwd=work)
    return git("rev-parse", "HEAD", cwd=work)


def do_run(key):
    folder = HOME / ".pi-durable" / "ohflow" / key
    spec = json.loads((folder / "spec.json").read_text(encoding="utf-8"))
    if SCENARIO == "killed":
        for line in (FIXTURES / "killed-events.jsonl").read_text(
                encoding="utf-8").splitlines():
            if line.strip():
                sys.stdout.write(line + "\n")
        sys.stdout.flush()
        (folder / "session.sqlite").write_bytes(b"")
        (folder / "transcript.md").write_text(
            "# transcript (interrupted)\n", encoding="utf-8")
        raise SystemExit(255)
    head = commit_on_branch(spec, folder / "work", key)
    fixture = ("reattach-events.jsonl" if SCENARIO == "reattach"
               else "single-events.jsonl")
    replay(FIXTURES / fixture, spec, key, head, folder / "session.sqlite")
    (folder / "session.sqlite").write_bytes(b"")
    (folder / "transcript.md").write_text(
        "# transcript\n\nthe fake durable host ran the step\n",
        encoding="utf-8")
    (folder / "usage.json").write_text(json.dumps({"scenario": SCENARIO}),
                                       encoding="utf-8")
    (folder / "handover.md").write_text("## Next\nreattach through the fake\n",
                                        encoding="utf-8")
    raise SystemExit(0)


BUNDLE_PREFIX = "const BUNDLE = "


def install(base):
    """Unpack the installer's bundle the way `install.cjs` does."""
    program = sys.stdin.buffer.read().decode("utf-8")
    first = program.splitlines()[0] if program else ""
    if not first.startswith(BUNDLE_PREFIX) or not first.endswith(";"):
        sys.stderr.write("fake node: stdin holds no BUNDLE line\n")
        raise SystemExit(1)
    bundle = json.loads(first[len(BUNDLE_PREFIX):-1])
    folder = base / ".pi-durable" / "ohflow-host" / bundle["version"]
    fresh = not (folder / ".version").is_file()
    for name, data in bundle["files"].items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(data))
    (folder / ".version").write_text(bundle["version"] + "\n", encoding="utf-8")
    emit({"type": "durable_host", "dir": str(folder.resolve()),
          "version": bundle["version"], "installed": fresh})
    raise SystemExit(0)


def node_version():
    sys.stdout.write(os.environ.get("OHFLOW_FAKE_DURABLE_NODE_VERSION", "v24.11.1") + "\n")
    raise SystemExit(0)


def require_host(script):
    if not script.endswith("ohflow-step.mjs") or not Path(script).is_file():
        sys.stderr.write(f"Error: Cannot find module '{script}'\n")
        raise SystemExit(1)


def do_ssh(argv):
    words = positional(sys.argv[1:])
    box = words[0] if words else ""
    command = words[1:]
    if command == ["exit"]:
        raise SystemExit(0)
    if command == ["node"] and "--version" in argv:
        node_version()
    if command == ["node"]:
        install(HOME)
    if len(command) >= 4 and command[0] == "node":
        require_host(command[1])
    if len(command) >= 3 and command[-2] == "prepare":
        folder = HOME / ".pi-durable" / "ohflow" / command[-1]
        folder.mkdir(parents=True, exist_ok=True)
        emit({"type": "durable_prepared", "key": command[-1],
              "dir": str(folder.resolve()),
              "session": (folder / "session.sqlite").exists(), "host": "fake"})
        raise SystemExit(0)
    if len(command) >= 3 and command[-2] == "run":
        do_run(command[-1])
    sys.stderr.write(f"fake ssh: unsupported command {command!r}\n")
    raise SystemExit(1)


def main():
    words = positional(sys.argv[1:])
    if any(remote_path(w, HOME) is not None for w in words):
        do_scp(sys.argv[1:])
    do_ssh(sys.argv[1:])


if __name__ == "__main__":
    main()
