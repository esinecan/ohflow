"""Keep independent channel observations tied to an original immutable bundle."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from release.package import digest, encoded, verify

CHANNELS = ("skillsmp", "skills-sh", "anthropic", "openai")
STATES = ("published", "pending_review", "pending_indexing", "failed", "manual_action", "unknown")


def desired(bundle):
    manifest = verify(bundle)
    return {"version": manifest["version"], "source_sha": manifest["source_sha"],
            "tag": manifest["tag"], "package_sha256": manifest["package"]["sha256"],
            "manifest_sha256": digest((bundle / "manifest.json").read_bytes())}


def alignment(record):
    observed = record["observed"]
    expected = record["desired"]
    keys = ("version", "source_sha", "package_sha256")
    if any(observed.get(k) is not None and observed[k] != expected[k] for k in keys):
        return "drift"
    return "verified" if all(observed.get(k) == expected[k] for k in keys) else "unknown"


def initialize(bundle, directory):
    identity = desired(bundle)
    directory.mkdir(parents=True, exist_ok=True)
    for channel in CHANNELS:
        path = directory / f"{channel}.json"
        if path.exists():
            record = json.loads(path.read_bytes())
            if record["desired"] != identity or record["channel"] != channel:
                raise ValueError(f"{channel}: use a separate status directory for each release")
            continue
        record = {"schema": 1, "channel": channel, "desired": identity,
                  "observed": {"version": None, "source_sha": None, "ref": None, "package_sha256": None},
                  "status": "unknown", "alignment": "unknown", "attempts": []}
        path.write_bytes(encoded(record))


def load_record(bundle, directory, channel):
    record = json.loads((directory / f"{channel}.json").read_bytes())
    if record.get("schema") != 1 or record["channel"] != channel or record["desired"] != desired(bundle):
        raise ValueError("Channel retry source differs from the original bundle")
    return record


def observe(bundle, directory, channel, status, evidence, note, observed):
    if status not in STATES or not evidence.startswith("https://") or not note.strip():
        raise ValueError("An attempt requires a supported status, HTTPS evidence URL and actionable note")
    record = load_record(bundle, directory, channel)
    record["status"], record["observed"] = status, observed
    record["alignment"] = alignment(record)
    record["attempts"].append({"at": datetime.now(timezone.utc).isoformat(), "status": status,
                               "evidence": evidence, "note": note, "observed": observed,
                               "alignment": record["alignment"]})
    (directory / f"{channel}.json").write_bytes(encoded(record))
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "status", "retry", "record"))
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--channel", choices=CHANNELS)
    parser.add_argument("--status", choices=STATES)
    parser.add_argument("--evidence")
    parser.add_argument("--note")
    for key in ("version", "source-sha", "ref", "package-sha256"):
        parser.add_argument(f"--observed-{key}")
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize(args.bundle, args.records)
        elif args.command in ("retry", "record") and not args.channel:
            parser.error("--channel is required")
        if args.command == "record":
            observed = {key: getattr(args, f"observed_{key}") for key in ("version", "source_sha", "ref", "package_sha256")}
            result = observe(args.bundle, args.records, args.channel, args.status, args.evidence or "",
                             args.note or "", observed)
        elif args.command == "retry":
            result = load_record(args.bundle, args.records, args.channel)
            manifest = verify(args.bundle)
            result = {"channel": args.channel, "desired": result["desired"],
                      "package": str((args.bundle / manifest["package"]["file"]).resolve()),
                      "manifest": str((args.bundle / "manifest.json").resolve())}
        else:
            result = [load_record(args.bundle, args.records, channel) for channel in CHANNELS]
        print(encoded(result).decode(), end="")
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"CHANNEL FAIL: {error}\n")


if __name__ == "__main__":
    main()
