"""Rehearse packaging and promotion against isolated git history and an API fixture."""
import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit
import zipfile

from release import channels, claude_plugin, package, promote

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "example/ohflow"
JOBS = ("suite (ubuntu-latest)", "suite (windows-latest)", "release candidate",
        "package smoke (ubuntu-latest)", "package smoke (windows-latest)")


class GitHubTransportTests(unittest.TestCase):
    def download(self, path):
        api = promote.GitHub(REPOSITORY, "test-token")
        api.opener = Mock()
        api.opener.open.return_value = io.BytesIO(b"archive bytes")
        self.assertEqual(api.request(path, binary=True), b"archive bytes")
        return api.opener.open.call_args.args[0]

    def test_actions_archive_negotiates_json_api_before_binary_redirect(self):
        request = self.download("/actions/artifacts/7/zip")
        self.assertEqual(request.get_header("Accept"), "application/vnd.github+json")

    def test_release_asset_negotiates_octet_stream(self):
        request = self.download("/releases/assets/7")
        self.assertEqual(request.get_header("Accept"), "application/octet-stream")

    def test_cross_host_download_redirect_removes_authorization(self):
        request = self.download("/actions/artifacts/7/zip")
        redirect = promote.Redirect()
        redirected = redirect.redirect_request(request, None, 302, "Found", {},
                                                 "https://release-assets.githubusercontent.com/archive.zip")
        self.assertIsNone(redirected.get_header("Authorization"))
        same_host = redirect.redirect_request(request, None, 302, "Found", {},
                                                "https://api.github.com/another-path")
        self.assertEqual(same_host.get_header("Authorization"), "Bearer test-token")
        with self.assertRaisesRegex(ValueError, "outside HTTPS"):
            redirect.redirect_request(request, None, 302, "Found", {}, "http://example.invalid/archive.zip")


class GitHubFixture:
    """Remote operations, including GitHub's non-force ancestry condition."""
    def __init__(self, repo, main, source, bundle):
        self.repo, self.main, self.source = repo, main, source
        self.release_ref = None
        self.tags, self.releases, self.assets = {}, {}, {}
        self.writes = []
        self.immutable = True
        self.fail_upload = False
        self.race_to = None
        self.plugin_ref = None
        self.blobs, self.trees, self.commits = {}, {}, {}
        self.rules = promote.rulesets(42)
        self.jobs = [{"id": i + 1, "run_attempt": 1, "name": name, "conclusion": "success"}
                     for i, name in enumerate(JOBS)]
        self.run = {"id": 100, "event": "push", "head_branch": "main", "status": "completed",
                    "conclusion": "success", "path": ".github/workflows/ci.yml", "run_attempt": 1,
                    "repository": {"full_name": REPOSITORY}, "head_repository": {"full_name": REPOSITORY},
                    "head_sha": source, "html_url": "https://example.invalid/suite/100"}
        self.artifact = {"id": 7, "name": "release-candidate-100-1", "expired": False}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for path in bundle.iterdir():
                archive.writestr(path.name, path.read_bytes())
        self.candidate = buffer.getvalue()

    def ancestor(self, older, newer):
        return subprocess.run(["git", "-C", str(self.repo), "merge-base", "--is-ancestor", older, newer],
                              capture_output=True).returncode == 0

    def blob(self, sha):
        if sha not in self.blobs:
            try:
                self.blobs[sha] = package.git(self.repo, "cat-file", "blob", sha)
            except subprocess.CalledProcessError:
                raise ValueError(f"GitHub POST /git/trees: HTTP 422, no blob {sha}") from None
        return self.blobs[sha]

    def git_request(self, path, method, data):
        if path == f"/git/ref/heads/{claude_plugin.BRANCH}":
            return {"object": {"sha": self.plugin_ref}} if self.plugin_ref else None
        if path.startswith("/git/commits/") and method == "GET":
            sha = path.rsplit("/", 1)[1]
            tree = (self.commits[sha]["tree"] if sha in self.commits
                    else package.git(self.repo, "rev-parse", f"{sha}^{{tree}}").decode().strip())
            return {"sha": sha, "tree": {"sha": tree}}
        if path.startswith("/git/trees/") and method == "GET":
            sha = path.split("/")[3].split("?")[0]
            if sha in self.trees:
                return {"sha": sha, "tree": deepcopy(self.trees[sha]), "truncated": False}
            rows = package.git(self.repo, "ls-tree", "-r", sha).decode().splitlines()
            return {"sha": sha, "truncated": False,
                    "tree": [{"mode": m, "type": t, "sha": s, "path": p}
                             for m, t, s, p in (r.split(None, 3) for r in rows)]}
        if path.startswith("/git/blobs/"):
            return {"content": base64.b64encode(self.blob(path.rsplit("/", 1)[1])).decode(), "encoding": "base64"}
        if path == "/git/blobs" and method == "POST":
            content = base64.b64decode(data["content"])
            sha = claude_plugin.blob_sha(content)
            self.blobs[sha] = content
            return {"sha": sha}
        if path == "/git/trees" and method == "POST":
            files = {e["path"]: (self.blob(e["sha"]), 0o755 if e["mode"] == "100755" else 0o644) for e in data["tree"]}
            sha = claude_plugin.tree_sha(files)
            self.trees[sha] = sorted(deepcopy(data["tree"]), key=lambda e: e["path"])
            return {"sha": sha}
        if path == "/git/commits" and method == "POST":
            sha = hashlib.sha1(json.dumps([data, len(self.commits)]).encode()).hexdigest()
            self.commits[sha] = deepcopy(data)
            return {"sha": sha}
        if path == f"/git/refs/heads/{claude_plugin.BRANCH}" and method == "PATCH":
            if data["force"] or self.commits.get(data["sha"], {}).get("parents") != [self.plugin_ref]:
                raise ValueError("GitHub rejected a non-fast-forward plugin write")
            self.plugin_ref = data["sha"]
            return {}
        return NotImplemented

    def pages(self, path, key=None):
        if path == "/rulesets":
            return [{"id": i, "name": r["name"]} for i, r in enumerate(self.rules)]
        if "/jobs" in path:
            return self.jobs
        if path.endswith("/artifacts"):
            return [self.artifact]
        if path == "/releases":
            return list(self.releases.values())
        if path.startswith("/releases/") and path.endswith("/assets"):
            release_id = int(path.split("/")[2])
            return [{"id": i, "name": a["name"]} for i, a in self.assets.items() if a["release_id"] == release_id]
        raise AssertionError(f"unhandled pages: {path}")

    def request(self, path, method="GET", data=None, binary=False, missing=False):
        if method != "GET":
            self.writes.append((path, method, data))
        if path == "/actions/runs/100":
            return deepcopy(self.run)
        if path == "/actions/artifacts/7/zip":
            return self.candidate
        if path.startswith("/rulesets/"):
            return deepcopy(self.rules[int(path.rsplit("/", 1)[1])])
        if path == "/immutable-releases":
            return {"enabled": self.immutable}
        if path == "/git/ref/heads/main":
            return {"object": {"sha": self.main}}
        if path == "/git/ref/heads/release":
            return {"object": {"sha": self.release_ref}} if self.release_ref else None
        if path.startswith("/compare/"):
            older, newer = path.rsplit("/", 1)[1].split("...")
            status = ("identical" if older == newer else "ahead" if self.ancestor(older, newer)
                      else "behind" if self.ancestor(newer, older) else "diverged")
            return {"status": status}
        if path.startswith("/git/ref/tags/"):
            sha = self.tags.get(path.rsplit("/", 1)[1])
            return {"object": {"sha": sha}} if sha else None
        handled = self.git_request(path, method, data)
        if handled is not NotImplemented:
            return handled
        if path == "/git/refs" and method == "POST":
            if data["ref"] == "refs/heads/release":
                if self.release_ref:
                    raise ValueError("concurrent creation rejected")
                self.release_ref = data["sha"]
            elif data["ref"] == f"refs/heads/{claude_plugin.BRANCH}":
                if self.plugin_ref:
                    raise ValueError("concurrent creation rejected")
                self.plugin_ref = data["sha"]
            else:
                self.tags[data["ref"].rsplit("/", 1)[1]] = data["sha"]
            return {}
        if path == "/git/refs/heads/release" and method == "PATCH":
            if data["force"] or not self.ancestor(self.release_ref, data["sha"]):
                raise ValueError("GitHub rejected a regressing write")
            self.release_ref = data["sha"]
            return {}
        if path.startswith("/releases/tags/"):
            return deepcopy(self.releases.get(path.rsplit("/", 1)[1]))
        if path == "/releases" and method == "POST":
            record = {**data, "id": len(self.releases) + 1, "immutable": False,
                      "upload_url": f"https://uploads.github.com/release/{len(self.releases)+1}{{?name}}",
                      "html_url": "https://example.invalid/release/" + data["tag_name"]}
            self.releases[data["tag_name"]] = record
            return deepcopy(record)
        if path.startswith("https://uploads.github.com/"):
            if self.fail_upload:
                self.fail_upload = False
                raise ValueError("simulated interrupted upload")
            parsed = urlsplit(path)
            asset_id = len(self.assets) + 1
            self.assets[asset_id] = {"name": parse_qs(parsed.query)["name"][0], "data": data,
                                     "release_id": int(parsed.path.rsplit("/", 1)[1])}
            return {"id": asset_id}
        if path.startswith("/releases/assets/"):
            return self.assets[int(path.rsplit("/", 1)[1])]["data"]
        if path.startswith("/releases/") and method == "PATCH":
            record = next(r for r in self.releases.values() if r["id"] == int(path.rsplit("/", 1)[1]))
            record.update(data, immutable=self.immutable)
            if self.race_to:
                self.release_ref = self.race_to
            return deepcopy(record)
        raise AssertionError(f"unhandled request: {method} {path}")


class ReleaseFoundation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix="ohflow-release-tests-")
        cls.root = Path(cls.scratch.name)
        cls.repo = cls.root / "source"
        cls.repo.mkdir()
        names = package.git(ROOT, "ls-files", "--cached", "--others", "--exclude-standard").decode().splitlines()
        for name in names:
            destination = cls.repo / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        package.git(cls.repo, "init", "-q", "-b", "main")
        cls.executables = [line.split("\t", 1)[1] for line in package.git(ROOT, "ls-files", "--stage").decode().splitlines()
                           if line.startswith("100755 ")]
        cls.old = cls.commit("Source fixture")
        readme = cls.repo / "README.md"
        readme.write_bytes(readme.read_bytes() + b"\nRelease fixture change.\n")
        cls.new = cls.commit("Small change")
        package.git(cls.repo, "revert", "--no-commit", cls.new)
        cls.revert = cls.commit("Revert small change")
        package.git(cls.repo, "checkout", "-q", "-b", "side", cls.old)
        readme.write_bytes(readme.read_bytes() + b"\nDivergent fixture change.\n")
        cls.side = cls.commit("Side branch change")
        package.git(cls.repo, "checkout", "-q", "main")

    @classmethod
    def commit(cls, message):
        package.git(cls.repo, "add", ".")
        for executable in cls.executables:
            package.git(cls.repo, "update-index", "--chmod=+x", executable)
        package.git(cls.repo, "-c", "user.name=Release test", "-c", "user.email=release@example.invalid",
                    "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "-qm", message)
        return package.git(cls.repo, "rev-parse", "HEAD").decode().strip()

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.bundle = self.directory / "bundle"
        self.manifest = package.build(self.repo, self.new, self.bundle)
        self.api = GitHubFixture(self.repo, self.revert, self.new, self.bundle)
        self.download = self.directory / "download"
        self.download.mkdir()

    def promote(self, policy=None):
        return promote.promote(self.api, self.api, REPOSITORY, 100, 42, self.download, policy)

    def audited_policy(self):
        for i, rule in enumerate(self.api.rules):
            rule['updated_at'] = f'2026-11-27T12:00:0{i}.001Z'
        return promote.attest_rules(self.api, 42)

    def test_exact_committed_source_and_deterministic_bytes(self):
        other = self.directory / "other"
        original = (self.repo / "README.md").read_bytes()
        try:
            (self.repo / "README.md").write_bytes(b"uncommitted operator change")
            package.build(self.repo, self.new, other)
        finally:
            (self.repo / "README.md").write_bytes(original)
        for path in self.bundle.iterdir():
            self.assertEqual(path.read_bytes(), (other / path.name).read_bytes())
        self.assertEqual(package.verify(other)["source_sha"], self.new)

    def test_package_installs_away_from_checkout(self):
        self.assertEqual(package.smoke(self.bundle)["source_sha"], self.new)

    def test_install_preserves_executable_mode_and_refuses_overwrite(self):
        destination = self.directory / "installed"
        installed = package.install(self.bundle, destination)
        self.assertEqual(json.loads((installed / "RELEASE.json").read_bytes())["source_sha"], self.new)
        with zipfile.ZipFile(self.bundle / self.manifest["package"]["file"]) as archive:
            self.assertEqual((archive.getinfo("ohflow/scripts/ohflow/shell_tee.sh").external_attr >> 16) & 0o777, 0o755)
        with self.assertRaises(FileExistsError):
            package.install(self.bundle, destination)

    def test_tampered_package_is_rejected_before_writes(self):
        self.api.candidate = self.api.candidate.replace(b'"schema": 1', b'"schema": 0')
        with self.assertRaises((ValueError, zipfile.BadZipFile)):
            self.promote()
        self.assertEqual(self.api.writes, [])

    def test_valid_package_from_another_source_cannot_use_this_run(self):
        other = self.directory / "other"
        package.build(self.repo, self.old, other)
        self.api = GitHubFixture(self.repo, self.revert, self.new, other)
        with self.assertRaisesRegex(ValueError, "does not match validated"):
            self.promote()
        self.assertEqual(self.api.writes, [])

    def test_missing_companion_is_rejected(self):
        files = {name: (self.repo / name).read_bytes() for name in package.REQUIRED}
        del files["host/install.cjs"]
        with self.assertRaisesRegex(ValueError, "missing companion"):
            package.validate_files(files)

    def test_failed_cancelled_unvalidated_fork_and_pr_runs_do_not_write(self):
        for change in ({"conclusion": "failure"}, {"conclusion": "cancelled"}, {"status": "in_progress"},
                       {"event": "pull_request"}, {"event": "workflow_dispatch"}, {"head_branch": "feature"},
                       {"path": ".github/workflows/other.yml"}, {"head_repository": {"full_name": "fork/ohflow"}}):
            with self.subTest(change=change):
                saved = deepcopy(self.api.run)
                self.api.run.update(change)
                with self.assertRaises(ValueError):
                    self.promote()
                self.assertEqual(self.api.writes, [])
                self.api.run = saved

    def test_missing_or_failed_smoke_is_not_eligible(self):
        self.api.jobs[-1]["conclusion"] = "skipped"
        with self.assertRaisesRegex(ValueError, "Required validation"):
            self.promote()
        self.assertEqual(self.api.writes, [])

    def test_partial_smoke_rerun_reuses_the_original_candidate(self):
        self.api.run["run_attempt"] = 2
        self.api.jobs.append({"id": 10, "run_attempt": 2, "name": JOBS[-1], "conclusion": "success"})
        self.assertEqual(self.promote()["result"], "create")

    def test_github_copied_jobs_keep_the_original_candidate_artifact(self):
        self.api.run["run_attempt"] = 2
        self.api.jobs.extend({"id": 10 + i, "run_attempt": 2, "name": name, "conclusion": "success"}
                             for i, name in enumerate(JOBS))
        self.assertEqual(self.promote()["result"], "create")
        self.assertEqual(self.api.artifact["name"], "release-candidate-100-1")

    def test_newer_failed_job_cannot_reuse_an_older_success(self):
        self.api.jobs.append({"id": 10, "run_attempt": 2, "name": JOBS[-1], "conclusion": "failure"})
        with self.assertRaisesRegex(ValueError, "Required validation"):
            self.promote()
        self.assertEqual(self.api.writes, [])

    def test_missing_expired_or_wrong_attempt_artifact_is_rejected(self):
        for change in ({"expired": True}, {"name": "release-candidate-100-2"}):
            with self.subTest(change=change):
                saved = deepcopy(self.api.artifact)
                self.api.artifact.update(change)
                with self.assertRaisesRegex(ValueError, "missing/expired"):
                    self.promote()
                self.assertEqual(self.api.writes, [])
                self.api.artifact = saved

    def test_bypassing_humans_and_mutable_releases_fail_before_writes(self):
        self.api.rules[0]["bypass_actors"].append({"actor_type": "RepositoryRole", "actor_id": 5, "bypass_mode": "always"})
        with self.assertRaisesRegex(ValueError, "unexpected bypass_actors"):
            self.promote()
        self.api.rules = promote.rulesets(42)
        self.api.immutable = False
        with self.assertRaisesRegex(ValueError, "Enable immutable"):
            self.promote()
        self.assertEqual(self.api.writes, [])

    def test_redacted_actors_require_an_owner_audit(self):
        policy = self.audited_policy()
        for rule in self.api.rules:
            del rule['bypass_actors']
        with self.assertRaisesRegex(ValueError, 'redacted'):
            self.promote()
        self.assertEqual(self.api.writes, [])
        self.assertEqual(self.promote(policy)['result'], 'create')

    def test_changed_ruleset_timestamp_rejects_old_audit(self):
        policy = self.audited_policy()
        for rule in self.api.rules:
            del rule['bypass_actors']
        self.api.rules[0]['updated_at'] = '2026-11-27T12:00:00.002Z'
        with self.assertRaisesRegex(ValueError, 'differs from its owner audit'):
            self.promote(policy)
        self.assertEqual(self.api.writes, [])

    def test_rule_audit_compares_instants_across_api_timezones(self):
        policy = self.audited_policy()
        for i, rule in enumerate(self.api.rules):
            del rule['bypass_actors']
            rule['updated_at'] = f'2026-11-27T13:00:0{i}.001+01:00'
        self.assertEqual(self.promote(policy)['result'], 'create')

    def test_rule_audit_rejects_a_timestamp_without_timezone(self):
        policy = self.audited_policy()
        for rule in self.api.rules:
            del rule['bypass_actors']
        policy['rulesets'][0]['updated_at'] = '2026-11-27T12:00:00.001'
        with self.assertRaisesRegex(ValueError, 'requires a timezone'):
            self.promote(policy)
        self.assertEqual(self.api.writes, [])

    def test_audit_requires_visible_actors(self):
        self.audited_policy()
        del self.api.rules[0]['bypass_actors']
        with self.assertRaisesRegex(ValueError, 'redacted'):
            promote.attest_rules(self.api, 42)

    def test_audit_cannot_authorize_another_app_or_added_actor(self):
        policy = self.audited_policy()
        for rule in self.api.rules:
            del rule['bypass_actors']
        wrong_app = deepcopy(policy)
        wrong_app['app_id'] = 43
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.promote(wrong_app)
        wrong_actor = deepcopy(policy)
        wrong_actor['rulesets'][0]['bypass_actors'].append({'actor_type': 'RepositoryRole', 'actor_id': 5, 'bypass_mode': 'always'})
        with self.assertRaisesRegex(ValueError, 'differs from its owner audit'):
            self.promote(wrong_actor)
        self.assertEqual(self.api.writes, [])

    def test_success_initializes_release_only_after_immutable_assets(self):
        result = self.promote()
        self.assertEqual(result["result"], "create")
        self.assertEqual(self.api.release_ref, self.new)
        self.assertTrue(self.api.releases[self.manifest["tag"]]["immutable"])
        self.assertEqual(len(self.api.assets), 2)
        refs = [data["ref"] for path, method, data in self.api.writes if path == "/git/refs"]
        self.assertEqual(refs[-2:], ["refs/heads/release", f"refs/heads/{claude_plugin.BRANCH}"])
        uploads = [i for i, (path, _, _) in enumerate(self.api.writes) if path.startswith("https://uploads.")]
        release = next(i for i, (_, _, data) in enumerate(self.api.writes)
                       if isinstance(data, dict) and data.get("ref") == "refs/heads/release")
        self.assertLess(max(uploads), release)

    def test_forward_update_is_not_forced(self):
        self.api.release_ref = self.old
        self.assertEqual(self.promote()["result"], "advance")
        patches = [data for path, method, data in self.api.writes if path == "/git/refs/heads/release"]
        self.assertEqual(patches, [{"sha": self.new, "force": False}])

    def test_late_older_job_cannot_regress_newer_release(self):
        self.api.release_ref = self.revert
        self.assertEqual(self.promote()["result"], "stale")
        self.assertEqual(self.api.writes, [])
        self.assertEqual(self.api.release_ref, self.revert)

    def test_candidate_removed_from_main_history_cannot_promote(self):
        self.api.main = self.side
        with self.assertRaisesRegex(ValueError, "no longer in main"):
            self.promote()
        self.assertEqual(self.api.writes, [])

    def test_divergent_managed_branch_is_never_forced(self):
        self.api.release_ref = self.side
        with self.assertRaisesRegex(ValueError, "diverged"):
            self.promote()
        self.assertEqual(self.api.writes, [])

    def test_existing_asset_with_different_bytes_stops_retry(self):
        self.promote()
        self.api.assets[1]["data"] = b"a different manifest"
        count = len(self.api.writes)
        with self.assertRaisesRegex(ValueError, "Existing release asset differs"):
            self.promote()
        self.assertEqual(len(self.api.writes), count)

    def test_race_during_upload_rechecks_before_ref_update(self):
        self.api.release_ref, self.api.race_to = self.old, self.revert
        self.assertEqual(self.promote()["result"], "stale")
        self.assertEqual(self.api.release_ref, self.revert)
        self.assertFalse(any(path == "/git/refs/heads/release" for path, _, _ in self.api.writes))

    def test_partial_upload_retry_preserves_original_bytes_and_is_idempotent(self):
        self.api.fail_upload = True
        with self.assertRaisesRegex(ValueError, "interrupted upload"):
            self.promote()
        self.assertIsNone(self.api.release_ref)
        self.assertEqual(self.promote()["result"], "create")
        count = len(self.api.writes)
        self.assertEqual(self.promote()["result"], "same")
        self.assertEqual(len(self.api.writes), count)
        for asset in self.api.assets.values():
            self.assertEqual(asset["data"], (self.bundle / asset["name"]).read_bytes())

    def test_conflicting_immutable_tag_does_not_advance_release(self):
        self.api.tags[self.manifest["tag"]] = self.old
        with self.assertRaisesRegex(ValueError, "another source"):
            self.promote()
        self.assertIsNone(self.api.release_ref)

    def test_revert_is_a_new_version_with_original_file_content(self):
        old_bundle, reverted = self.directory / "old", self.directory / "reverted"
        old = package.build(self.repo, self.old, old_bundle)
        new = package.build(self.repo, self.revert, reverted)
        self.assertNotEqual(old["version"], new["version"])
        self.assertNotEqual(old["source_sha"], new["source_sha"])
        self.assertEqual(old["source_files"], new["source_files"])
        self.api = GitHubFixture(self.repo, self.revert, self.revert, reverted)
        self.api.release_ref = self.new
        self.assertEqual(self.promote()["result"], "advance")

    def test_channels_keep_unknowns_and_retry_the_original_bundle(self):
        records = self.directory / "status"
        channels.initialize(self.bundle, records)
        channels.initialize(self.bundle, records)
        observed = {"version": None, "source_sha": None, "ref": None, "package_sha256": None}
        record = channels.observe(self.bundle, records, "skillsmp", "pending_indexing",
                                  "https://example.invalid/listing", "Indexer does not expose its source SHA", observed)
        self.assertEqual(record["alignment"], "unknown")
        self.assertEqual(len(record["attempts"]), 1)
        self.assertEqual(channels.load_record(self.bundle, records, "skillsmp")["desired"]["source_sha"], self.new)
        other = self.directory / "other"
        package.build(self.repo, self.revert, other)
        with self.assertRaisesRegex(ValueError, "differs"):
            channels.load_record(other, records, "skillsmp")

    def test_channel_drift_and_full_alignment_are_distinct(self):
        expected = channels.desired(self.bundle)
        observed = {key: expected[key] for key in ("version", "source_sha", "package_sha256")}
        self.assertEqual(channels.alignment({"desired": expected, "observed": observed}), "verified")
        observed["source_sha"] = self.old
        self.assertEqual(channels.alignment({"desired": expected, "observed": observed}), "drift")

    def plugin_tree(self, bundle=None):
        return claude_plugin.generate(bundle or self.bundle)[1]

    def test_claude_plugin_is_generated_from_the_bundle_alone(self):
        tree = self.plugin_tree()
        self.assertEqual(tree, self.plugin_tree())
        self.assertEqual(claude_plugin.check(tree), [])
        meta = json.loads(tree[".claude-plugin/plugin.json"][0])
        self.assertEqual((meta["name"], meta["version"]), ("ohflow", self.manifest["version"]))
        identity = json.loads(tree[f"{claude_plugin.SKILL}/RELEASE.json"][0])
        self.assertEqual(identity["source_sha"], self.new)
        source = claude_plugin.bundle_files(self.bundle)[1]
        self.assertEqual(tree["README.md"], source["release/claude/README.md"])
        self.assertEqual(tree["LICENSE"], source["LICENSE"])
        skill = {name[len(claude_plugin.SKILL) + 1:] for name in tree if name.startswith(claude_plugin.SKILL + "/")}
        kept = {name for name in self.manifest["source_files"]
                if Path(name).parts[0] not in claude_plugin.LEFT_OUT}
        self.assertEqual(skill, kept | {"RELEASE.json"})
        self.assertEqual(tree[f"{claude_plugin.SKILL}/scripts/ohflow/shell_tee.sh"][1], 0o755)
        self.assertLessEqual(len(tree), claude_plugin.MAX_FILES)

    def test_claude_plugin_tree_hash_matches_git(self):
        repo = self.directory / "hash"
        package.git(self.directory, "init", "-q", str(repo))
        tree = self.plugin_tree()
        staging = self.directory / "objects"
        lines = []
        for i, (name, (data, mode)) in enumerate(tree.items()):
            path = staging / str(i)
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
            lines.append((name, mode, path))
        shas = subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--no-filters", "--stdin-paths"],
                              input="\n".join(str(p) for _, _, p in lines).encode(), capture_output=True,
                              check=True).stdout.decode().split()
        index = "".join(f"{claude_plugin.git_mode(mode)} {sha}\t{name}\n" for (name, mode, _), sha in zip(lines, shas))
        subprocess.run(["git", "-C", str(repo), "update-index", "--add", "--index-info"], input=index.encode(),
                       check=True, capture_output=True)
        written = package.git(repo, "write-tree").decode().strip()
        self.assertEqual(claude_plugin.tree_sha(tree), written)

    def test_claude_plugin_check_names_each_directory_rule(self):
        base = self.plugin_tree()
        meta = json.loads(base[".claude-plugin/plugin.json"][0])
        breaks = {
            "more than 512": {f"skills/ohflow/extra/{i}.md": (b"x", 0o644) for i in range(400)},
            "over 256 KiB": {"skills/ohflow/big.md": (b"x" * (256 * 1024 + 1), 0o644)},
            "binary file": {"skills/ohflow/icon.ico": (b"\x00\x01", 0o644)},
            "incomplete image": {"skills/ohflow/shot.png": (b"\x89PNG\r\n\x1a\n" + b"cut", 0o644)},
            "top-level bin/": {"bin/ohflow": (b"#!/bin/sh\n", 0o755)},
            "Windows or macOS refuses": {"skills/ohflow/con.md": (b"x", 0o644)},
            "differ only by case": {"Skills/other.md": (b"x", 0o644)},
            "40 words": {"README.md": (b"# ohflow\n\nToo short.\n", 0o644)},
            "lowercase letters": {".claude-plugin/plugin.json": (package.encoded({**meta, "name": "OhFlow"}), 0o644)},
            "export-ignore": {"skills/ohflow/.gitattributes": (b"docs/ export-ignore\n", 0o644)},
            "lockfile": {"package.json": (b"{}", 0o644), "package-lock.json": (b"{}", 0o644)},
        }
        for words, change in breaks.items():
            with self.subTest(rule=words):
                problems = claude_plugin.check({**base, **change})
                self.assertTrue(any(words in problem for problem in problems), problems)
        unlicensed = {name: entry for name, entry in base.items() if name != "LICENSE"}
        unlicensed[".claude-plugin/plugin.json"] = (package.encoded({k: v for k, v in meta.items() if k != "license"}), 0o644)
        self.assertTrue(any("LICENSE" in p for p in claude_plugin.check(unlicensed)))
        self.assertFalse(claude_plugin.rewriting_attributes("# a filter comment\n*.sh text eol=lf\n*.bin -filter\n"))
        with self.assertRaisesRegex(ValueError, "leave version"):
            claude_plugin.metadata(package.encoded({**meta}), "0.0.9")

    def test_claude_plugin_skill_runs_from_a_clean_path(self):
        out = self.directory / "plugin"
        claude_plugin.write(self.plugin_tree(), out)
        claude_plugin.smoke(out)
        with self.assertRaisesRegex(ValueError, "already holds"):
            claude_plugin.write(self.plugin_tree(), out)

    def test_promotion_writes_the_claude_plugin_branch_after_release(self):
        result = self.promote()["claude_plugin"]
        self.assertEqual(result["result"], "create")
        self.assertEqual(self.api.plugin_ref, result["commit"])
        commit = self.api.commits[result["commit"]]
        self.assertEqual(commit["parents"], [])
        self.assertEqual(commit["tree"], claude_plugin.tree_sha(self.plugin_tree()))
        self.assertTrue(commit["message"].startswith(f"ohflow {self.manifest['version']} from {self.new}"))
        uploaded = [data for path, _, data in self.api.writes if path == "/git/blobs"]
        self.assertLess(len(uploaded), len(self.plugin_tree()))

    def test_promotion_retry_keeps_the_claude_plugin_commit(self):
        first = self.promote()["claude_plugin"]
        count = len(self.api.writes)
        second = self.promote()["claude_plugin"]
        self.assertEqual((second["result"], second["commit"]), ("same", first["commit"]))
        self.assertEqual(len(self.api.writes), count)

    def test_claude_plugin_branch_moves_forward_and_never_back(self):
        old = self.directory / "old"
        package.build(self.repo, self.old, old)
        first = claude_plugin.publish(self.api, self.api, REPOSITORY, old)
        second = claude_plugin.publish(self.api, self.api, REPOSITORY, self.bundle)
        self.assertEqual((first["result"], second["result"]), ("create", "advance"))
        self.assertEqual(self.api.commits[second["commit"]]["parents"], [first["commit"]])
        self.assertIn((f"/git/refs/heads/{claude_plugin.BRANCH}", "PATCH", {"sha": second["commit"], "force": False}),
                      self.api.writes)
        count = len(self.api.writes)
        late = claude_plugin.publish(self.api, self.api, REPOSITORY, old)
        self.assertEqual((late["result"], self.api.plugin_ref), ("stale", second["commit"]))
        self.assertEqual(len(self.api.writes), count)

    def test_same_version_with_other_content_is_never_overwritten(self):
        claude_plugin.publish(self.api, self.api, REPOSITORY, self.bundle)
        changed = self.plugin_tree()
        changed["README.md"] = (changed["README.md"][0] + b"\nHand edit.\n", 0o644)
        entries = []
        for name, (data, mode) in changed.items():
            self.api.blobs[claude_plugin.blob_sha(data)] = data
            entries.append({"path": name, "mode": claude_plugin.git_mode(mode), "type": "blob",
                            "sha": claude_plugin.blob_sha(data)})
        tree = self.api.request("/git/trees", "POST", {"tree": entries})["sha"]
        self.api.plugin_ref = self.api.request("/git/commits", "POST", {"tree": tree, "parents": [self.api.plugin_ref],
                                                                       "message": "hand edit"})["sha"]
        with self.assertRaisesRegex(ValueError, "other content"):
            claude_plugin.publish(self.api, self.api, REPOSITORY, self.bundle)

    def test_missing_claude_plugin_ruleset_stops_promotion_before_writes(self):
        self.api.rules = [r for r in self.api.rules if r["name"] != "ohflow claude-plugin branch"]
        with self.assertRaisesRegex(ValueError, "Install active ruleset 'ohflow claude-plugin branch'"):
            self.promote()
        self.assertEqual(self.api.writes, [])

    def test_anthropic_record_names_the_plugin_commit_and_keeps_unknowns(self):
        result = self.promote()
        promotion = self.directory / "promotion.json"
        promotion.write_bytes(package.encoded(result))
        records = self.directory / "status"
        channels.initialize(self.bundle, records)
        record = claude_plugin.record(self.bundle, records, promotion)
        self.assertEqual((record["status"], record["alignment"]), ("unknown", "unknown"))
        self.assertEqual(record["observed"]["ref"], claude_plugin.BRANCH)
        self.assertEqual(record["attempts"][-1]["evidence"], result["claude_plugin"]["url"])
        promotion.write_bytes(package.encoded({"result": "stale"}))
        self.assertIsNone(claude_plugin.record(self.bundle, records, promotion))


if __name__ == "__main__":
    unittest.main()
