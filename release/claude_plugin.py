"""Generate the Claude plugin for Anthropic's directory from one verified bundle, and keep it on its branch."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import zipfile

from release import channels
from release.package import encoded, smoke_installed, verify

BRANCH = "claude-plugin"
SKILL = "skills/ohflow"
TEMPLATE = "release/claude"
LEFT_OUT = ("tests", ".github", "release")
IMAGES = {".png": (b"\x89PNG\r\n\x1a\n", b"IEND\xaeB`\x82"), ".jpg": (b"\xff\xd8", b"\xff\xd9"),
          ".jpeg": (b"\xff\xd8", b"\xff\xd9"), ".gif": (b"GIF8", b";"), ".webp": (b"RIFF", b"")}
FONTS = {".woff", ".woff2", ".ttf", ".otf"}
MAX_FILES = 512
MAX_TEXT = 256 * 1024
MAX_FILE = 5 * 1024 * 1024
NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
DEVICE = re.compile(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?")
SYSTEM = {".DS_Store", "Thumbs.db", "desktop.ini", "__MACOSX"}
LOCKS = ("package-lock.json", "npm-shrinkwrap.json", "bun.lock", "bun.lockb")


def bundle_files(bundle):
    manifest = verify(bundle)
    files = {}
    with zipfile.ZipFile(bundle / manifest["package"]["file"]) as archive:
        for info in archive.infolist():
            mode = 0o755 if (info.external_attr >> 16) & 0o111 else 0o644
            files[info.filename[len("ohflow/"):]] = (archive.read(info), mode)
    return manifest, files


def metadata(template, version):
    data = json.loads(template)
    if "version" in data:
        raise ValueError(f"{TEMPLATE}/plugin.json must leave version to the release")
    return {**data, "version": version}


def generate(bundle):
    manifest, files = bundle_files(bundle)
    template = {name[len(TEMPLATE) + 1:]: data for name, (data, _) in files.items()
                if name.startswith(TEMPLATE + "/")}
    if set(template) != {"plugin.json", "README.md"}:
        raise ValueError(f"{TEMPLATE}/ must hold exactly plugin.json and README.md")
    tree = {".claude-plugin/plugin.json": (encoded(metadata(template["plugin.json"], manifest["version"])), 0o644),
            "README.md": (template["README.md"], 0o644),
            "LICENSE": (files["LICENSE"][0], 0o644)}
    for name, entry in files.items():
        if PurePosixPath(name).parts[0] not in LEFT_OUT:
            tree[f"{SKILL}/{name}"] = entry
    problems = check(tree)
    if problems:
        raise ValueError("The Claude plugin breaks directory rules: " + "; ".join(problems))
    return manifest, dict(sorted(tree.items()))


def words(markdown):
    return len(re.sub(r"(?ms)^```.*?^```[^\n]*", "", markdown).split())


def is_text(data):
    if b"\0" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def check(tree):
    try:
        meta = json.loads(tree[".claude-plugin/plugin.json"][0])
    except (KeyError, ValueError):
        return [".claude-plugin/plugin.json is missing or is not JSON"]
    problems = []
    if not isinstance(meta.get("name"), str) or not NAME.fullmatch(meta["name"]):
        problems.append("plugin.json name must be lowercase letters, digits and hyphens, up to 64")
    problems += [f"plugin.json lacks {key}" for key in ("description", "author", "version") if not meta.get(key)]
    readme = tree.get("README.md")
    if not readme or words(readme[0].decode("utf-8", "replace")) < 40:
        problems.append("README.md needs 40 words outside code blocks")
    if "LICENSE" not in tree and not meta.get("license"):
        problems.append("the plugin needs a LICENSE file or a license field")
    if len(tree) > MAX_FILES:
        problems.append(f"{len(tree)} files: more than {MAX_FILES} holds every version for a reviewer")
    if "CLAUDE.md" in tree:
        problems.append("CLAUDE.md at the plugin root never loads")
    if "package.json" in tree and any(lock in tree for lock in LOCKS):
        problems.append("a package.json with a lockfile at the plugin root is held for a reviewer")
    folded = {}
    for name, (data, _) in tree.items():
        path = PurePosixPath(name)
        if path.parts[0] == "bin":
            problems.append("a top-level bin/ stops claude.ai and Cowork from installing the plugin")
        for depth, part in enumerate(path.parts, 1):
            if (part in SYSTEM or ":" in part or part != part.rstrip(". ") or DEVICE.fullmatch(part)):
                problems.append(f"{name}: a name that Windows or macOS refuses")
            prefix = "/".join(path.parts[:depth])
            other = folded.setdefault(prefix.lower(), prefix)
            if other != prefix:
                problems.append(f"{prefix} and {other} differ only by case")
        suffix = path.suffix.lower()
        if len(data) >= MAX_FILE:
            problems.append(f"{name}: {len(data)} bytes, at or over 5 MiB")
        if suffix in IMAGES:
            head, tail = IMAGES[suffix]
            if not data.startswith(head) or not data.endswith(tail):
                problems.append(f"{name}: an incomplete image is held for a reviewer")
            continue
        if suffix in FONTS:
            continue
        if len(data) > MAX_TEXT:
            problems.append(f"{name}: {len(data)} bytes, over 256 KiB, is held for a reviewer")
        if not is_text(data):
            problems.append(f"{name}: a binary file is held for a reviewer")
        elif path.name == ".gitattributes" and rewriting_attributes(data.decode("utf-8")):
            problems.append(f"{name}: export-ignore, export-subst and filter stop validation")
    return sorted(set(problems))


def rewriting_attributes(text):
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        for token in line.split()[1:]:
            if not token.startswith(("-", "!")) and token.split("=", 1)[0] in ("export-ignore", "export-subst", "filter"):
                return True
    return False


def blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def git_mode(mode):
    return "100755" if mode & 0o111 else "100644"


def tree_sha(tree):
    root = {}
    for name, (data, mode) in tree.items():
        *folders, leaf = name.split("/")
        node = root
        for folder in folders:
            node = node.setdefault(folder, {})
        node[leaf] = (git_mode(mode), blob_sha(data))

    def hashed(node):
        entries = []
        for name, value in node.items():
            if isinstance(value, dict):
                entries.append(((name + "/").encode(), b"40000 " + name.encode() + b"\0" + bytes.fromhex(hashed(value))))
            else:
                entries.append((name.encode(), value[0].encode() + b" " + name.encode() + b"\0" + bytes.fromhex(value[1])))
        body = b"".join(entry for _, entry in sorted(entries))
        return hashlib.sha1(b"tree %d\0" % len(body) + body).hexdigest()

    return hashed(root)


def write(tree, out):
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"{out} already holds files")
    for name, (data, mode) in tree.items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(mode)


def read(directory):
    return {path.relative_to(directory).as_posix(): (path.read_bytes(), 0o755 if path.stat().st_mode & 0o111 else 0o644)
            for path in sorted(directory.rglob("*")) if path.is_file()}


def smoke(directory):
    problems = check(read(directory))
    if problems:
        raise ValueError("The Claude plugin breaks directory rules: " + "; ".join(problems))
    with tempfile.TemporaryDirectory(prefix="ohflow-claude-plugin-") as scratch:
        root = Path(scratch)
        shutil.copytree(directory, root / "plugin")
        smoke_installed(root / "plugin" / SKILL, root)


def generation(version):
    return int(version.rsplit(".", 1)[1])


def tip_identity(api, commit):
    tree = api.request(f"/git/commits/{commit}")["tree"]["sha"]
    listing = api.request(f"/git/trees/{tree}?recursive=1")
    entry = next((e for e in listing["tree"] if e["path"] == f"{SKILL}/RELEASE.json"), None)
    if listing.get("truncated") or entry is None:
        raise ValueError(f"{BRANCH} holds no readable {SKILL}/RELEASE.json. Restore the managed branch.")
    blob = api.request(f"/git/blobs/{entry['sha']}")
    return tree, json.loads(base64.b64decode(blob["content"]))


def publish(reader, writer, repository, bundle):
    manifest, tree = generate(bundle)
    expected = tree_sha(tree)
    version, source = manifest["version"], manifest["source_sha"]
    result = {"version": version, "source_sha": source, "branch": BRANCH}
    current = reader.request(f"/git/ref/heads/{BRANCH}", missing=True)
    parent = current["object"]["sha"] if current else None
    if parent:
        held_tree, held = tip_identity(reader, parent)
        if generation(held["version"]) > generation(version):
            return {**result, "result": "stale", "commit": parent, "tree": held_tree,
                    "url": f"https://github.com/{repository}/commit/{parent}"}
        if held["version"] == version:
            if held_tree != expected or held.get("source_sha") != source:
                raise ValueError(f"{BRANCH} already holds {version} with other content. Never overwrite it.")
            return {**result, "result": "same", "commit": parent, "tree": held_tree,
                    "url": f"https://github.com/{repository}/commit/{parent}"}
    source_tree = reader.request(f"/git/commits/{source}")["tree"]["sha"]
    known = {e["sha"] for e in reader.request(f"/git/trees/{source_tree}?recursive=1")["tree"] if e["type"] == "blob"}
    entries = []
    for name, (data, mode) in tree.items():
        sha = blob_sha(data)
        if sha not in known:
            created = writer.request("/git/blobs", "POST", {"content": base64.b64encode(data).decode("ascii"),
                                                             "encoding": "base64"})
            if created["sha"] != sha:
                raise ValueError(f"Blob readback differs: {name}")
            known.add(sha)
        entries.append({"path": name, "mode": git_mode(mode), "type": "blob", "sha": sha})
    made = writer.request("/git/trees", "POST", {"tree": entries})["sha"]
    if made != expected:
        raise ValueError("The created tree differs from the generated plugin")
    message = (f"ohflow {version} from {source}\n\nGenerated by release.claude_plugin from ohflow-v{version}. "
               "Change ohflow on main, never on this branch.\n")
    commit = writer.request("/git/commits", "POST", {"message": message, "tree": made,
                                                     "parents": [parent] if parent else []})["sha"]
    if parent:
        writer.request(f"/git/refs/heads/{BRANCH}", "PATCH", {"sha": commit, "force": False})
    else:
        writer.request("/git/refs", "POST", {"ref": f"refs/heads/{BRANCH}", "sha": commit})
    if reader.request(f"/git/ref/heads/{BRANCH}")["object"]["sha"] != commit:
        raise ValueError(f"{BRANCH} ref readback differs. Retry the original run.")
    return {**result, "result": "advance" if parent else "create", "commit": commit, "tree": made,
            "url": f"https://github.com/{repository}/commit/{commit}"}


def record(bundle, records, promotion):
    written = json.loads(promotion.read_bytes()).get("claude_plugin")
    if not written:
        return None
    note = (f"{written['result']}: {BRANCH} commit {written['commit']} holds {written['version']} from "
            f"{written['source_sha']}. The directory scans the branch, and Anthropic's publish setting decides "
            "when the version goes live. Read the listing state in the developer portal.")
    observed = {"version": None, "source_sha": None, "ref": BRANCH, "package_sha256": None}
    return channels.observe(bundle, records, "anthropic", "unknown", written["url"], note, observed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--bundle", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    sub.add_parser("smoke").add_argument("--tree", type=Path, required=True)
    note = sub.add_parser("record")
    note.add_argument("--bundle", type=Path, required=True)
    note.add_argument("--records", type=Path, required=True)
    note.add_argument("--promotion", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "build":
            manifest, tree = generate(args.bundle)
            write(tree, args.out)
            print(f"CLAUDE PLUGIN OK: {manifest['version']} {manifest['source_sha']} "
                  f"{len(tree)} files, tree {tree_sha(tree)}")
        elif args.command == "smoke":
            smoke(args.tree)
            print(f"CLAUDE PLUGIN SMOKE OK: {args.tree}")
        else:
            result = record(args.bundle, args.records, args.promotion)
            print("CLAUDE PLUGIN RECORD: " + (result["attempts"][-1]["note"] if result else "no plugin write to record"))
    except subprocess.CalledProcessError as error:
        parser.exit(1, f"CLAUDE PLUGIN FAIL: {error}\n{(error.stdout or b'').decode('utf-8', errors='replace')}\n"
                    f"{(error.stderr or b'').decode('utf-8', errors='replace')}\n")
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, f"CLAUDE PLUGIN FAIL: {error}\n")


if __name__ == "__main__":
    main()
