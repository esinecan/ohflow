"""Build and verify the complete portable skill from one immutable git commit."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile

REQUIRED = (
    "SKILL.md", "README.md", "LICENSE", "CONTEXT.md", "ohflow.settings.json",
    "scripts/ohflow/cli.py", "scripts/ohflow/run-hidden.vbs",
    "host/package.json", "host/package-lock.json", "host/install.cjs",
    "worker/package.json", "worker/package-lock.json", "worker/snapshot/recipe.mjs",
    "references/ohflow.md", "references/quickstart.md",
    "examples/quickstart/specs/bundle.md",
)
SHA = re.compile(r"[0-9a-f]{40}")


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def safe_name(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or ".." in path.parts or "\\" in name
            or ":" in name or path.as_posix() != name):
        raise ValueError(f"unsafe archive path: {name}")
    return name


def validate_files(files):
    missing = set(REQUIRED) - files.keys()
    if missing:
        raise ValueError(f"missing companion files: {sorted(missing)}")
    skill = files["SKILL.md"].decode("utf-8")
    front = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", skill, re.S)
    if (not front or not re.search(r"(?m)^name: ohflow\r?$", front[1])
            or not re.search(r"(?m)^description: \S.+", front[1])):
        raise ValueError("SKILL.md requires name and description front matter")
    for name in files:
        safe_name(name)
        if (name in {"ohflow.settings.local.json", "worker/pi-cloud.settings.local.json",
                     "worker/snapshot/AGENTS.local.md", "references/local.md"}
                or "node_modules" in PurePosixPath(name).parts
                or "__pycache__" in PurePosixPath(name).parts):
            raise ValueError(f"operator/build file in package: {name}")
    for folder in ("host", "worker"):
        metadata = json.loads(files[f"{folder}/package.json"])
        lock = json.loads(files[f"{folder}/package-lock.json"])
        if metadata.get("name") != lock.get("name") or not metadata.get("version"):
            raise ValueError(f"invalid {folder} package metadata")
        for key in ("dependencies", "devDependencies"):
            if metadata.get(key, {}) != lock["packages"][""].get(key, {}):
                raise ValueError(f"{folder} dependency lock differs: {key}")
    # Every local Markdown file reference must have its companion in the archive.
    for name, data in files.items():
        if not (name == "SKILL.md" or name.startswith("references/")) or not name.endswith(".md"):
            continue
        text = re.sub(r"(?ms)^```.*?^```[^\n]*", "", data.decode("utf-8"))
        for target in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", text):
            target = target.split("#", 1)[0].split(' "', 1)[0]
            if not target or re.match(r"[a-zA-Z][\w+.-]*:", target) or target.startswith(("/", "~", "<")):
                continue
            import posixpath
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            if resolved not in files and not any(p.startswith(resolved + "/") for p in files):
                raise ValueError(f"{name}: absent linked companion {target}")


def build(root: Path, source: str, out: Path):
    if git(root, "rev-parse", "--is-shallow-repository").strip() == b"true":
        raise ValueError("Fetch complete git history before deriving a release version")
    sha = git(root, "rev-parse", "--verify", f"{source}^{{commit}}").decode().strip()
    generation = int(git(root, "rev-list", "--count", sha))
    identity = {"schema": 1, "source_sha": sha, "version": f"0.0.{generation}"}
    files, modes = {}, {}
    with tarfile.open(fileobj=io.BytesIO(git(root, "archive", "--format=tar", sha))) as archive:
        for member in archive:
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"only regular source files can be packaged: {member.name}")
            name = safe_name(member.name)
            files[name] = archive.extractfile(member).read()
            modes[name] = 0o755 if member.mode & 0o111 else 0o644
    if "RELEASE.json" in files:
        raise ValueError("RELEASE.json is generated, and must not be committed")
    validate_files(files)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted([*files, "RELEASE.json"]):
            info = zipfile.ZipInfo(f"ohflow/{name}", date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100000 | modes.get(name, 0o644)) << 16
            archive.writestr(info, encoded(identity) if name == "RELEASE.json" else files[name])
    package = payload.getvalue()
    filename = f"ohflow-{identity['version']}.zip"
    manifest = {**identity, "tag": f"ohflow-v{identity['version']}",
                "package": {"file": filename, "sha256": digest(package), "size": len(package)},
                "source_files": {name: digest(data) for name, data in sorted(files.items())}}
    out.mkdir(parents=True, exist_ok=True)
    (out / filename).write_bytes(package)
    (out / "manifest.json").write_bytes(encoded(manifest))
    return manifest


def verify(bundle: Path, expected_sha: str | None = None):
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    sha, version = manifest["source_sha"], manifest["version"]
    if (manifest.get("schema") != 1 or not SHA.fullmatch(sha)
            or not re.fullmatch(r"0\.0\.[1-9][0-9]*", version)
            or manifest.get("tag") != f"ohflow-v{version}"):
        raise ValueError("invalid manifest identity")
    if expected_sha and sha != expected_sha:
        raise ValueError("manifest source does not match validated commit")
    package = manifest["package"]
    if package["file"] != f"ohflow-{version}.zip":
        raise ValueError("unexpected package name")
    data = (bundle / package["file"]).read_bytes()
    if digest(data) != package["sha256"] or len(data) != package["size"]:
        raise ValueError("package checksum/size differs from manifest")
    files = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate package paths")
        for info in archive.infolist():
            name = safe_name(info.filename)
            if not name.startswith("ohflow/") or (info.external_attr >> 16) & 0o170000 != 0o100000:
                raise ValueError(f"unexpected package entry: {name}")
            files[name[len("ohflow/"):]] = archive.read(info)
    identity = {key: manifest[key] for key in ("schema", "source_sha", "version")}
    if files.pop("RELEASE.json", None) != encoded(identity):
        raise ValueError("installed release identity differs")
    if {name: digest(data) for name, data in files.items()} != manifest["source_files"]:
        raise ValueError("archive files differ from manifest")
    validate_files(files)
    return manifest


def install(bundle: Path, destination: Path):
    """Install into a new directory, preserving committed executable permissions."""
    manifest = verify(bundle)
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(bundle / manifest["package"]["file"]) as archive:
        for info in archive.infolist():
            target = destination / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
            target.chmod((info.external_attr >> 16) & 0o777)
    return destination / "ohflow"


def smoke_installed(installed: Path, root: Path):
    # No checkout, network, model login, inherited import path or local settings.
    import os
    env = dict(os.environ, PYTHONPATH=str(installed / "scripts"), PYTHONUTF8="1",
               OHFLOW_SETTINGS=str(installed / "ohflow.settings.json"))
    app = installed / "examples/quickstart/app"
    git(app, "init", "-q", "-b", "main")
    git(app, "add", ".")
    git(app, "-c", "user.name=Release smoke", "-c", "user.email=release@example.invalid",
        "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "-qm", "Quickstart fixture")
    subprocess.run([sys.executable, "-m", "ohflow.cli", "--help"], cwd=root,
                   env=env, check=True, capture_output=True, timeout=60)
    subprocess.run([sys.executable, "-m", "ohflow.cli", "construct", "--bundle",
                    str(installed / "examples/quickstart/specs"), "--out", str(root / "campaign")],
                   cwd=root, env=env, check=True, capture_output=True, timeout=60)
    subprocess.run(["node", "--check", str(installed / "host/install.cjs")],
                   check=True, capture_output=True, timeout=60)
    subprocess.run(["node", "--check", str(installed / "worker/snapshot/recipe.mjs")],
                   check=True, capture_output=True, timeout=60)


def smoke(bundle: Path):
    manifest = verify(bundle)
    with tempfile.TemporaryDirectory(prefix="ohflow-install-") as directory:
        root = Path(directory)
        smoke_installed(install(bundle, root / "skills"), root)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("build")
    make.add_argument("--repo", type=Path, default=Path.cwd())
    make.add_argument("--source", default="HEAD")
    make.add_argument("--out", type=Path, required=True)
    for command in ("verify", "smoke"):
        sub.add_parser(command).add_argument("--bundle", type=Path, required=True)
    unpack = sub.add_parser("install")
    unpack.add_argument("--bundle", type=Path, required=True)
    unpack.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "install":
            result = verify(args.bundle)
            print(f"Installed: {install(args.bundle, args.destination)}")
        else:
            result = build(args.repo, args.source, args.out) if args.command == "build" else globals()[args.command](args.bundle)
    except subprocess.CalledProcessError as error:
        parser.exit(1, f"RELEASE FAIL: {error}\n{(error.stdout or b'').decode('utf-8', errors='replace')}\n"
                    f"{(error.stderr or b'').decode('utf-8', errors='replace')}\n")
    except (ValueError, OSError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        parser.exit(1, f"RELEASE FAIL: {error}\n")
    print(f"RELEASE OK: {result['version']} {result['source_sha']}")


if __name__ == "__main__":
    main()
