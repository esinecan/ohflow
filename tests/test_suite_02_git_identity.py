"""The suite needed the machine's git identity.

WSL showed 29 failures on a commit that passed elsewhere: the box had no
global `user.name` and `user.email`. `git_repo` named an identity only for its
own first commit. A merge step and a campaign revision commit later through
ohflow's own git calls, which carry no identity, and git refused them.

`git_repo` now writes both names into the repository's own config, which its
worktrees share. Git here reads no global and no system config and may not
guess an identity from the host, so the machine that runs this test cannot
lend one.
"""

from __future__ import annotations

import os
import subprocess

from support import TempCase, git_repo

IDENTITY_VARS = ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                 "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL")


class ARepositoryOfTheSuiteNamesItsOwnIdentity(TempCase):

    def git(self, cwd, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k not in IDENTITY_VARS}
        env.update({
            "GIT_CONFIG_GLOBAL": str(self.tmp / ".gitconfig-none"),
            "GIT_CONFIG_SYSTEM": str(self.tmp / ".gitconfig-none"),
        })
        return subprocess.run(
            ["git", "-C", str(cwd), "-c", "user.useConfigOnly=true", *args],
            capture_output=True, text=True, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_a_commit_needs_no_identity_from_the_machine(self):
        repo = git_repo(self.tmp / "repo")
        done = self.git(repo, "commit", "--allow-empty", "-m", "second")
        self.assertEqual(done.returncode, 0, done.stderr)
        names = self.git(repo, "log", "-1", "--format=%an <%ae> %cn <%ce>")
        self.assertEqual(names.stdout.strip(),
                         "ohflow tests <tests@localhost> "
                         "ohflow tests <tests@localhost>")

    def test_a_merge_in_a_worktree_needs_no_identity_from_the_machine(self):
        repo = git_repo(self.tmp / "repo")
        tree = self.tmp / "integration"
        for args in (("branch", "side"),
                     ("commit", "--allow-empty", "-m", "main moves"),
                     ("worktree", "add", "-q", str(tree), "side"),
                     ("-C", str(tree), "commit", "--allow-empty", "-m", "side moves")):
            done = self.git(repo, *args)
            self.assertEqual(done.returncode, 0, done.stderr)
        done = self.git(tree, "merge", "--no-ff", "-m", "merge main", "main")
        self.assertEqual(done.returncode, 0, done.stderr)
