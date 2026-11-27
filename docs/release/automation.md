# Validated releases

`main` integrates changes. The release workflow advances `release` to an exact commit from
`main` after its source tests and package checks pass. The default branch stays `main`.
Feature work goes through a pull request to `main`.

The suite runs on every push to `main` and every pull request, including changes to Markdown.
It runs the source suite and Worker tests on Ubuntu and Windows, builds one portable ZIP,
then installs that same ZIP in a temporary directory on both systems. The install check loads
the CLI, constructs the quickstart campaign and checks the companion Node entry points.
It needs no model login and starts no agents. Host deployment and vendor installation checks
belong to the packages that use those services.

## Source and package identity

The version is `0.0.N`, where `N` is the number of commits reachable from the source commit.
Every descendant has a larger count. Full git history is required. A revert is another commit
with another version, even when it restores the files of an earlier release. These versions
identify releases and make no API compatibility promise.

The builder reads `git archive` of the full source SHA. Local edits never enter the package.
The ZIP contains the complete committed repository under `ohflow/`, including `scripts/`,
`host/`, `worker/`, `references/`, examples and settings. It also contains generated
`RELEASE.json` with the version and source SHA. Timestamps, file order and permissions are
fixed, and ZIP storage uses no compressor whose output might vary across versions.

The adjacent `manifest.json` records the version, immutable tag, full source SHA, package size,
package SHA-256 and every source file's SHA-256. The tag is `ohflow-v0.0.N`. No version file is
committed back to `main`, so a promotion cannot cause another version commit.

Both install jobs consume the candidate built after the source suites. The publisher reuses
that candidate from the successful suite run. It never rebuilds it. A partial CI rerun may reuse
earlier passing jobs and the candidate from its original job attempt, but the latest execution
of every required job must pass.

## Enable the publisher

The publisher requires a dedicated GitHub App installed only on this repository. Give it
Contents write, Workflows write and Administration read. Contents writes tags, release assets
and the release branch. Workflows permits advancing a ref when the validated commit includes
workflow files. Administration read checks that release immutability is enabled. It has no
administration write permission. The workflow's ordinary token has Contents read and Actions
read for validation evidence.

1. Create and install the App. Store its numeric App ID in the repository variable
   `OHFLOW_RELEASE_APP_ID` and its private key in the Actions secret
   `OHFLOW_RELEASE_APP_PRIVATE_KEY`. The workflow requests a short-lived token for this repository.
2. Generate the three ref ruleset templates, substituting the App's ID:

   ```bash
   python -m release.promote --rulesets 123456
   ```

   Import each object as a separate active repository ruleset. `ohflow release branch` restricts
   creation, updates and deletion of `refs/heads/release`, with only this App allowed to bypass.
   `ohflow release tag creation` restricts creation of `refs/tags/ohflow-v*` to the App.
   `ohflow immutable release tags` restricts updates and deletion of those tags with no bypass.
   Audit them with an owner token using `GITHUB_REPOSITORY=owner/repo`, `GH_TOKEN` and
   `python -m release.promote --attest-rulesets 123456`. Store the resulting JSON in the
   repository variable `OHFLOW_RELEASE_RULESET_POLICY`.
   The audit requires visible bypass actors and rejects additional actors. GitHub omits these
   lists from the release App's response, so the publisher checks the audited ruleset IDs and
   server update timestamps alongside their live protections. Any edit requires another audit.
   The App keeps Administration read. An audit created from redacted actor lists is rejected.
3. Enable release immutability in repository Settings, General, Releases. Verify it with
   `gh api repos/esinecan/ohflow/immutable-releases`, which must report `enabled: true`.
   [GitHub documents the setting and its effect on assets and tags](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).
4. Review and merge the release implementation through a pull request. Its merge commit runs
   the full suite. That successful push run supplies the first candidate and initializes
   `release`. An older suite run without a candidate is ineligible.

Keep the App key in Actions secrets. An administrator can change repository rules, so an
administrative change still requires review. Routine human pushes cannot update the managed refs.

## Promotion and recovery

`release.yml` runs after `suite` completes on `main`. The publisher checks the run's repository,
event, branch, workflow path, conclusion, required jobs, original candidate attempt and source SHA.
A pull request, fork, failed run, cancelled run or skipped package check cannot promote.
The publisher uses code from the trusted default branch and executes no downloaded artifact.
[The workflow-run event has separate permissions from the workflow it follows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run).

One concurrency group serializes publishers. GitHub does not guarantee their order, so the
publisher also checks ancestry and rejects a delayed older commit. It creates the immutable tag,
uploads both assets to a draft release, checks the uploaded bytes and publishes the release.
It verifies that the published release is immutable, re-reads the managed branch, then advances
it without force. The branch never points at a version whose assets are still being uploaded.
An interrupted publisher can leave a draft or a complete release awaiting branch advancement.

Retry the original suite run ID after correcting the reported configuration or upload failure:

```bash
gh workflow run release.yml -f validation_run_id=123456789
```

Existing tags must match the original source SHA, and existing assets must match its original
bytes. The publisher refuses to replace either. A repeated successful promotion makes no writes.
If a newer source has already reached `release`, the older retry reports `stale`.
Candidate artifacts are retained for 90 days. A missing or expired candidate stops promotion.
Published release assets remain the source for later channel retries.

To recover from a bad release, revert the change on `main` through a pull request. Its validation
produces a new version. Never move an old tag or reset `release` backwards. A history rewrite or
a divergent managed branch stops promotion and requires investigation.

Each publisher reports its source, version, checksum, validation URL and release URL in the job
summary and `promotion.json`. The `release-result` Actions artifact also keeps the original bundle
and channel records, including files left by a partial failure. A failure message names the
configuration or identity check to fix before retrying.

## Four distribution channels

All four channels receive the same desired version, source SHA, tag and package checksum.
Their own jobs select that immutable identity once. They must never resolve a moving branch
separately at different stages. A supported Git install pins the exact tag or SHA from the
manifest. Vendor packages must record this identity when their channel task defines their format.

`release.channels` keeps one JSON record per channel in a directory for one release. Initialize
it from the original bundle, or download the ZIP and `manifest.json` from its GitHub release first:

```bash
python -m release.package verify --bundle bundle
python -m release.package install --bundle bundle --destination installed-skills
python -m release.channels init --bundle bundle --records status
python -m release.channels status --bundle bundle --records status
python -m release.channels retry --bundle bundle --records status --channel skills-sh
```

`install` writes `installed-skills/ohflow/`, preserves executable permissions and refuses to
overwrite an existing destination. Point the harness's skill loader at that installed directory.

`retry` prints the original artifact path and expected checksums after verifying both the bundle
and the channel's desired source. It performs no vendor request. A channel adapter consumes
that result, submits through its verified vendor interface and records the attempt:

```bash
python -m release.channels record --bundle bundle --records status --channel skillsmp \
  --status pending_indexing --evidence https://example.com/listing \
  --note "Refresh requested. Indexer exposes no source SHA or checksum."
```

Each attempt records its UTC time, status, evidence URL, note and observed identity. Supported
statuses are `published`, `pending_review`, `pending_indexing`, `failed`, `manual_action` and
`unknown`. Record observed values with `--observed-version`, `--observed-source-sha`,
`--observed-ref` and `--observed-package-sha256` only when the channel exposes evidence for them.
Unknown values stay null. Alignment is `verified` only when version, SHA and checksum all match,
`drift` when an observed identity conflicts, and `unknown` when the evidence is incomplete.

Preserve each channel's JSON file as that job's evidence and pass the same file to its next
attempt. Independent jobs own different files, so they need no shared mutable status document.
The initial release-result artifact records desired identities with unknown observations.
Publication, review and indexing can finish at different times.

| Channel | What its adapter must prove |
|---|---|
| SkillsMP | Listing, refresh mechanism and supported branch selection. Default-branch-only indexing requires an explicit source exception. |
| skills.sh | A tag or SHA-qualified install, complete companion files and the actual update path. |
| Anthropic | Supported plugin format, tracked Git source, review settings and actual automatic update support. |
| OpenAI | Eligibility, supported package format and verified submission/update controls. Portal-only steps stay manual. |

These adapters own their credentials and vendor manifests. Package creation alone proves no
directory listing, and a listing without source evidence proves no alignment.

## Local rehearsal

Run `python tests/run_tests.py -k release_foundation`. Its isolated git history contains a small
change and a revert. An API fixture rehearses successful initialization, forward promotion,
failed and cancelled validation, missing smoke checks, wrong source, stale and racing jobs,
partial upload recovery, immutable identity conflicts and independent channel retries. The same
tests install the archive outside the checkout and check deterministic bytes despite local edits.

These checks cover the publisher's decisions. The production acceptance check follows merge:
observe the actual Actions run, immutable release and protected branch, install its downloaded
package, retry the original run and retain its job summary. Then use a reviewed small Markdown
change and its revert to verify automatic advancement without breaking public `main`.
