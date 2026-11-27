"""Publish an original successful main suite artifact, then advance release."""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from release.package import encoded, verify


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise ValueError("GitHub download redirected outside HTTPS")
        result = super().redirect_request(request, fp, code, msg, headers, newurl)
        if urllib.parse.urlsplit(request.full_url).netloc != urllib.parse.urlsplit(newurl).netloc:
            result.remove_header("Authorization")
        return result


class GitHub:
    def __init__(self, repository, token):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
            raise ValueError("invalid repository")
        self.base = f"https://api.github.com/repos/{repository}"
        self.token = token
        self.opener = urllib.request.build_opener(Redirect())

    def request(self, path, method="GET", data=None, binary=False, missing=False):
        url = path if path.startswith("https://") else self.base + path
        # Upload URLs originate in the trusted GitHub release response.
        if urllib.parse.urlsplit(url).hostname not in ("api.github.com", "uploads.github.com"):
            raise ValueError("unexpected GitHub API host")
        body = data if isinstance(data, bytes) else encoded(data) if data is not None else None
        headers = {"Authorization": f"Bearer {self.token}",
                   "Accept": "application/octet-stream" if binary else "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ohflow-release"}
        if body is not None:
            headers["Content-Type"] = "application/octet-stream" if isinstance(data, bytes) else "application/json"
        try:
            with self.opener.open(urllib.request.Request(url, data=body, headers=headers, method=method), timeout=120) as response:
                raw = response.read()
                return raw if binary else json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            if missing and error.code == 404:
                return None
            raise ValueError(f"GitHub {method} {urllib.parse.urlsplit(url).path}: HTTP {error.code}. "
                             "Check app permissions/rules, then retry the original suite run.") from error

    def pages(self, path, key=None):
        rows = []
        for page in range(1, 101):
            data = self.request(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
            part = data[key] if key else data
            rows.extend(part)
            if len(part) < 100:
                return rows
        raise ValueError(f"pagination limit exceeded: {path}")


def rulesets(app_id):
    def rule(name, target, include, types, bypass):
        return {"name": name, "target": target, "enforcement": "active",
                "conditions": {"ref_name": {"include": [include], "exclude": []}},
                "bypass_actors": bypass, "rules": [{"type": kind} for kind in types]}
    app = [{"actor_id": app_id, "actor_type": "Integration", "bypass_mode": "always"}]
    return [rule("ohflow release branch", "branch", "refs/heads/release", ["creation", "update", "deletion"], app),
            rule("ohflow release tag creation", "tag", "refs/tags/ohflow-v*", ["creation"], app),
            rule("ohflow immutable release tags", "tag", "refs/tags/ohflow-v*", ["update", "deletion"], [])]


def check_rules(api, app_id):
    available = api.pages("/rulesets")
    for expected in rulesets(app_id):
        match = next((r for r in available if r["name"] == expected["name"]), None)
        if not match:
            raise ValueError(f"Install active ruleset '{expected['name']}' before promotion")
        actual = api.request(f"/rulesets/{match['id']}")
        for key in ("target", "enforcement", "conditions", "bypass_actors"):
            if actual.get(key) != expected[key]:
                raise ValueError(f"Ruleset '{expected['name']}' has unexpected {key}")
        if not {r["type"] for r in expected["rules"]} <= {r["type"] for r in actual["rules"]}:
            raise ValueError(f"Ruleset '{expected['name']}' does not protect the required operations")


def validated_run(api, repository, run_id):
    run = api.request(f"/actions/runs/{run_id}")
    expected = {"event": "push", "head_branch": "main", "status": "completed",
                "conclusion": "success", "path": ".github/workflows/ci.yml"}
    if any(run.get(key) != value for key, value in expected.items()):
        raise ValueError("Only a completed successful push-to-main suite run is eligible")
    if run.get("repository", {}).get("full_name") != repository or run.get("head_repository", {}).get("full_name") != repository:
        raise ValueError("The validation run belongs to another repository/fork")
    if not re.fullmatch(r"[0-9a-f]{40}", run.get("head_sha", "")):
        raise ValueError("Validation run has no full source SHA")
    jobs = api.pages(f"/actions/runs/{run_id}/jobs?filter=all", "jobs")
    for name in ("suite (ubuntu-latest)", "suite (windows-latest)", "release candidate",
                 "package smoke (ubuntu-latest)", "package smoke (windows-latest)"):
        matches = [job for job in jobs if job["name"] == name]
        latest = max(matches, key=lambda job: job["id"]) if matches else None
        if latest is None or latest.get("conclusion") != "success":
            raise ValueError(f"Required validation did not pass: {name}")
        if name == "release candidate":
            # GitHub copies successful jobs into a partial rerun with fresh IDs and
            # the new attempt number, although their artifact was not rebuilt.
            run["candidate_attempts"] = sorted({job["run_attempt"] for job in matches
                                               if job.get("conclusion") == "success"
                                               and job["run_attempt"] <= run["run_attempt"]}, reverse=True)
    return run


def candidate_artifact(run, artifacts):
    for attempt in run["candidate_attempts"]:
        name = f"release-candidate-{run['id']}-{attempt}"
        matches = [a for a in artifacts if a["name"] == name]
        if len(matches) > 1:
            raise ValueError(f"Ambiguous candidate artifact: {name}")
        if matches and not matches[0].get("expired"):
            return matches[0]
    raise ValueError(f"Original candidate for run {run['id']} is missing/expired. "
                     "Use retained GitHub release assets for channel retries.")


def download_candidate(api, run, destination):
    artifact = candidate_artifact(run, api.pages(f"/actions/runs/{run['id']}/artifacts", "artifacts"))
    raw = api.request(f"/actions/artifacts/{artifact['id']}/zip", binary=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != 2 or "manifest.json" not in names or not all(re.fullmatch(r"manifest\.json|ohflow-0\.0\.[1-9][0-9]*\.zip", n) for n in names):
            raise ValueError("Candidate artifact must contain exactly the manifest and portable package")
        for name in names:
            (destination / name).write_bytes(archive.read(name))
    return verify(destination, run["head_sha"])


def is_ancestor(api, older, newer):
    return api.request(f"/compare/{older}...{newer}")["status"] in ("ahead", "identical")


def forward(api, source):
    main = api.request("/git/ref/heads/main")["object"]["sha"]
    if not is_ancestor(api, source, main):
        raise ValueError("Candidate is no longer in main history. Restore main history before promoting.")
    current = api.request("/git/ref/heads/release", missing=True)
    if not current:
        return "create"
    old = current["object"]["sha"]
    if old == source:
        return "same"
    if is_ancestor(api, source, old):
        return "stale"
    if not is_ancestor(api, old, source):
        raise ValueError("release and candidate diverged. Restore the managed branch, never force promotion.")
    return "advance"


def publish_assets(api, manifest, bundle):
    tag, sha = manifest["tag"], manifest["source_sha"]
    ref = api.request(f"/git/ref/tags/{tag}", missing=True)
    if ref and ref["object"]["sha"] != sha:
        raise ValueError("Immutable tag already points to another source")
    if not ref:
        api.request("/git/refs", "POST", {"ref": f"refs/tags/{tag}", "sha": sha})
    release = api.request(f"/releases/tags/{tag}", missing=True)
    if release is None:
        # Drafts are not returned by releases/tags on every token/API combination.
        release = next((r for r in api.pages("/releases") if r["tag_name"] == tag), None)
    if release is None:
        release = api.request("/releases", "POST", {"tag_name": tag, "target_commitish": sha,
                              "name": tag, "draft": True,
                              "body": f"Validated source: `{sha}`.\n\nPackage SHA-256: `{manifest['package']['sha256']}`.\n\nSee manifest.json for every source file checksum."})
    assets = api.pages(f"/releases/{release['id']}/assets")
    for name in ("manifest.json", manifest["package"]["file"]):
        expected = (bundle / name).read_bytes()
        asset = next((a for a in assets if a["name"] == name), None)
        if asset:
            actual = api.request(f"/releases/assets/{asset['id']}", binary=True)
            if actual != expected:
                raise ValueError(f"Existing release asset differs: {name}. Never overwrite it.")
        elif release["draft"]:
            upload = release["upload_url"].split("{", 1)[0]
            uploaded = api.request(upload + "?name=" + urllib.parse.quote(name), "POST", expected)
            if api.request(f"/releases/assets/{uploaded['id']}", binary=True) != expected:
                raise ValueError(f"Uploaded asset readback differs: {name}")
        else:
            raise ValueError(f"Published release is missing {name}. Stop and investigate.")
    if release["draft"]:
        release = api.request(f"/releases/{release['id']}", "PATCH", {"draft": False})
    if release.get("immutable") is not True:
        raise ValueError("Enable immutable releases in repository Settings > General > Releases before publishing. "
                         "This published version is mutable and release was not advanced. Review it before retrying.")
    return release["html_url"]


def promote(reader, writer, repository, run_id, app_id, bundle):
    run = validated_run(reader, repository, run_id)
    manifest = download_candidate(reader, run, bundle)
    check_rules(writer, app_id)
    if writer.request("/immutable-releases").get("enabled") is not True:
        raise ValueError("Enable immutable releases in repository Settings > General > Releases before promotion")
    decision = forward(reader, manifest["source_sha"])
    if decision == "stale":
        return {"result": "stale", "source_sha": manifest["source_sha"]}
    release_url = publish_assets(writer, manifest, bundle)
    # Re-read after uploads. A late job cannot reset a newer ref even if serialization fails.
    decision = forward(reader, manifest["source_sha"])
    if decision == "create":
        writer.request("/git/refs", "POST", {"ref": "refs/heads/release", "sha": manifest["source_sha"]})
    elif decision == "advance":
        writer.request("/git/refs/heads/release", "PATCH", {"sha": manifest["source_sha"], "force": False})
    if decision != "stale" and reader.request("/git/ref/heads/release")["object"]["sha"] != manifest["source_sha"]:
        raise ValueError("Release ref readback differs. Retry the original run.")
    return {"result": decision, "version": manifest["version"], "source_sha": manifest["source_sha"],
            "package_sha256": manifest["package"]["sha256"], "release_url": release_url,
            "validation_url": run["html_url"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rulesets", type=int, metavar="APP_ID", help="print ruleset import templates")
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--out", type=Path, default=Path("release-result"))
    args = parser.parse_args()
    if args.rulesets:
        print(encoded(rulesets(args.rulesets)).decode(), end="")
        return
    if not args.run_id:
        parser.error("--run-id is required")
    try:
        repository = os.environ["GITHUB_REPOSITORY"]
        reader = GitHub(repository, os.environ["GH_TOKEN"])
        writer = GitHub(repository, os.environ["RELEASE_TOKEN"])
        app_id = int(os.environ["RELEASE_APP_ID"])
        args.out.mkdir(parents=True, exist_ok=True)
        # Keep original bundle for downstream channel jobs, with no rebuild.
        result = promote(reader, writer, repository, args.run_id, app_id, args.out)
        (args.out / "promotion.json").write_bytes(encoded(result))
        print(encoded(result).decode(), end="")
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as report:
                report.write("## Release promotion\n\n```json\n" + encoded(result).decode() + "```\n")
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, f"PROMOTION FAIL: {error}\n")


if __name__ == "__main__":
    main()
