"""A fake `node` for the durable harness executor on box `local`.

`OHFLOW_DURABLE_NODE` points here. This machine's home is the temp directory
`OHFLOW_FAKE_DURABLE_HOME`, as the box's is for `fake_durable.py`:

- no argument, the installer on stdin: unpack the bundle under
  `<home>/.pi-durable/ohflow-host/<version>/` and print `durable_host`;
- `--version`: print a version;
- `<host>/ohflow-step.mjs local <step folder>`: refuse a host that is not
  installed, then play `OHFLOW_FAKE_DURABLE_SCENARIO` in the worktree that
  `spec.durable.work` names: `success` and `reattach` commit one file there,
  replay their recording and end with `durable_end`; `killed` replays its
  recording, leaves `session.sqlite` behind and exits 255.

Every invocation appends its argv to `<home>/node-calls.jsonl`.
"""

import json
import sys
from pathlib import Path

import fake_durable as box


def log_call():
    box.HOME.mkdir(parents=True, exist_ok=True)
    with (box.HOME / "node-calls.jsonl").open("a", encoding="utf-8") as calls:
        calls.write(json.dumps(sys.argv[1:]) + "\n")


def commit_in(work, key):
    box.git("config", "user.name", "fake durable host", cwd=work)
    box.git("config", "user.email", "durable@localhost", cwd=work)
    (work / "rollcall").mkdir(exist_ok=True)
    (work / "rollcall" / f"{key}.md").write_text(
        f"# {key}\nfake local durable work\n", encoding="utf-8")
    box.git("add", "-A", cwd=work)
    box.git("commit", "-m", "rollcall: local durable fake", cwd=work)
    return box.git("rev-parse", "HEAD", cwd=work)


def replay(path, folder, spec, start, head):
    durable = spec.get("durable") or {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        kind = record.get("type")
        if kind == "durable_start":
            record.update(key=durable.get("key"), dir=str(folder), local=True,
                          reattach=box.SCENARIO == "reattach")
        elif kind == "durable_end":
            record.update(start=start, branch=None, head=head, dirty=[],
                          pushed=False, local=True,
                          session=str(folder / "session.sqlite"))
        box.emit(record)


def run_local(folder):
    folder = Path(folder)
    spec = json.loads((folder / "spec.json").read_text(encoding="utf-8"))
    work = Path(spec["durable"]["work"])
    start = box.git("rev-parse", "HEAD", cwd=work)
    if box.SCENARIO == "killed":
        for line in (box.FIXTURES / "killed-events.jsonl").read_text(
                encoding="utf-8").splitlines():
            if line.strip():
                sys.stdout.write(line + "\n")
        sys.stdout.flush()
        (folder / "session.sqlite").write_bytes(b"")
        raise SystemExit(255)
    head = commit_in(work, spec["durable"]["key"])
    fixture = ("reattach-events.jsonl" if box.SCENARIO == "reattach"
               else "single-events.jsonl")
    replay(box.FIXTURES / fixture, folder, spec, start, head)
    (folder / "session.sqlite").write_bytes(b"")
    (folder / "transcript.md").write_text(
        "# transcript\n\nthe fake local durable host ran the step\n", encoding="utf-8")
    (folder / "usage.json").write_text(json.dumps({"scenario": box.SCENARIO}),
                                       encoding="utf-8")
    raise SystemExit(0)


def main(argv):
    log_call()
    if argv == ["--version"]:
        box.node_version()
    if not argv:
        box.install(box.HOME)
    if len(argv) == 3 and argv[1] == "local":
        box.require_host(argv[0])
        run_local(argv[2])
    sys.stderr.write(f"fake node: unsupported argv {argv!r}\n")
    raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
