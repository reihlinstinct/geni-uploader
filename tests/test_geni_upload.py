import argparse
import json
import os
import sys
import tempfile
import unittest
from typing import ClassVar

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import geni_upload as g

MANIFEST = {
    "targets": [
        {
            "profile_id": "123",
            "expect_name": "Tamar Vardi",
            "documents": [
                {
                    "title": "Doc A",
                    "source_url": "https://x/1",
                    "description": "d",
                    "labels": "source",
                }
            ],
            "photos": [],
        },
    ]
}


def _manifest_file(data):
    import yaml

    d = tempfile.mkdtemp()  # private dir: upload-status.yaml sits beside it
    path = os.path.join(d, "manifest.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)
    return path


def _run_args(**kw):
    d = {
        "confirm": "YES",
        "manifest": None,
        "state": tempfile.mktemp(),
        "token_file": None,
        "smoke": False,
        "log": None,
        "no_repo_sync": True,
    }
    d.update(kw)
    return argparse.Namespace(**d)


class ManifestTests(unittest.TestCase):
    def test_valid_manifest_loads(self):
        m = g.load_manifest(_manifest_file(MANIFEST))
        self.assertEqual(len(m["targets"]), 1)

    def test_missing_manifest_helpful_error(self):
        # Regression 2026-10-25: default-branch clone lacked the package and
        # the user saw a raw FileNotFoundError traceback. Must be a clear
        # ApiError naming the path and the GENI_UPLOAD_REF branch check.
        missing = os.path.join(tempfile.mkdtemp(), "no-such-manifest.yaml")
        try:
            g.load_manifest(missing)
            self.fail("expected ApiError")
        except g.ApiError as e:
            msg = str(e)
            self.assertIn("manifest not found", msg)
            self.assertIn(missing, msg)
            self.assertIn("GENI_UPLOAD_REF", msg)

    def test_repo_relative_asset_path_does_not_resolve(self):
        # Regression 2026-10-25: a repo-relative file path must NOT resolve
        # (paths are joined against the manifest directory, not the repo
        # root or cwd); the failure must be the clean "file not found".
        bad = {
            "targets": [
                {
                    "profile_id": "123",
                    "expect_name": "Tamar Vardi",
                    "documents": [],
                    "photos": [
                        {
                            "title": "Scan",
                            "description": "d",
                            "file": "scripts/geni_upload/packages/x/scan.jpg",
                        }
                    ],
                }
            ]
        }
        try:
            g.load_manifest(_manifest_file(bad))
            self.fail("expected ApiError")
        except g.ApiError as e:
            self.assertIn("file not found", str(e))

    def test_missing_profile_id_rejected(self):
        bad = {"targets": [{"expect_name": "Tamar Vardi"}]}
        with self.assertRaises(g.ApiError):
            g.load_manifest(_manifest_file(bad))

    def test_missing_title_rejected(self):
        bad = {
            "targets": [
                {
                    "profile_id": "1",
                    "expect_name": "Tamar Vardi",
                    "documents": [{"source_url": "https://x"}],
                }
            ]
        }
        with self.assertRaises(g.ApiError):
            g.load_manifest(_manifest_file(bad))

    def test_bare_first_name_rejected(self):
        bad = {"targets": [{"profile_id": "1", "expect_name": "Tamar", "documents": []}]}
        with self.assertRaises(g.ApiError):
            g.load_manifest(_manifest_file(bad))

    def test_document_needs_anchor(self):
        bad = {
            "targets": [
                {"profile_id": "1", "expect_name": "Tamar Vardi", "documents": [{"title": "X"}]}
            ]
        }
        with self.assertRaises(g.ApiError):
            g.load_manifest(_manifest_file(bad))


class NameMatchTests(unittest.TestCase):
    def test_full_name_token_match(self):
        self.assertTrue(g.name_matches("Tamar Sara Ruth Vardi", "Tamar Vardi"))

    def test_wrong_person_rejected(self):
        self.assertFalse(g.name_matches("Tamar Noy", "Tamar Vardi"))

    def test_missing_token_rejected(self):
        self.assertFalse(g.name_matches("Tamar Vardi", "Tamar Regina Vardi"))


class ExecuteTests(unittest.TestCase):
    def test_non_allowlisted_refused(self):
        with self.assertRaises(g.ApiError):
            g.execute("POST", "profile_add", "https://x", "tok", {})

    def test_post_network_error_is_uncertain_not_retried(self):
        import urllib.error

        calls = []

        def boom(req, data=None, timeout=None):
            calls.append(1)
            raise urllib.error.URLError("timeout")

        orig = g.urllib.request.urlopen
        g.urllib.request.urlopen = boom
        try:
            with self.assertRaises(g.UncertainWrite):
                g.execute("POST", "document_add", "https://x", "tok", {"title": "t"})
        finally:
            g.urllib.request.urlopen = orig
        self.assertEqual(len(calls), 1)  # no retry of a mutation

    def test_get_retries_then_succeeds(self):
        import urllib.error

        calls = []

        class R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"ok": true}'

        def flaky(req, data=None, timeout=None):
            calls.append(1)
            if len(calls) < 2:
                raise urllib.error.URLError("blip")
            return R()

        orig = g.urllib.request.urlopen
        g.urllib.request.urlopen = flaky
        g.time.sleep = lambda s: None
        try:
            self.assertEqual(g.execute("GET", "profile", "https://x", "tok"), {"ok": True})
        finally:
            g.urllib.request.urlopen = orig
        self.assertEqual(len(calls), 2)


class RunTests(unittest.TestCase):
    def setUp(self):
        self.manifest = _manifest_file(MANIFEST)
        self.posts = []
        self.listings = {("123", "documents"): set(), ("123", "photos"): set()}
        self.pending = []
        g.time.sleep = lambda s: None

        def fake_execute(method, kind, url, token=None, data=None):
            if (method, kind) not in g.ALLOWLIST:
                raise g.ApiError("refused")
            if kind == "profile":
                return {"display_name": "Tamar Sara Ruth Vardi"}
            if kind in ("profile_documents", "profile_photos"):
                k = ("123", "documents" if kind == "profile_documents" else "photos")
                return {
                    "results": [
                        {"title": t[0], "source_url": t[1] if len(t) > 1 else None}
                        for t in self.listings[k]
                    ]
                }
            if kind in ("document_add", "photo_add"):
                self.posts.append((kind, url, data))
                self.pending.append(data)
                return {"id": "999"}
            if kind in ("document_tag", "photo_tag"):
                self.posts.append((kind, url, data))
                for d in self.pending:  # tag makes it visible in the listing
                    k = ("123", "documents" if kind == "document_tag" else "photos")
                    self.listings[k].add(
                        (d.get("title"), d.get("source_url"))
                        if kind == "document_tag"
                        else (d.get("title"),)
                    )
                self.pending = []
                return {}
            raise AssertionError(kind)

        self.fake = fake_execute
        g.execute = fake_execute

    def tearDown(self):
        import importlib

        importlib.reload(g)

    def test_run_refused_without_token(self):
        os.environ.pop("GENI_ACCESS_TOKEN", None)
        args = _run_args(manifest=self.manifest)
        self.assertEqual(g.cmd_run(args), 2)

    def test_run_refused_without_confirm(self):
        os.environ["GENI_ACCESS_TOKEN"] = "tok"
        args = _run_args(confirm="", manifest=self.manifest)
        self.assertEqual(g.cmd_run(args), 2)

    def test_upload_then_tag_url(self):
        os.environ["GENI_ACCESS_TOKEN"] = "tok"
        args = _run_args(manifest=self.manifest)
        self.assertEqual(g.cmd_run(args), 0)
        kinds = [p[0] for p in self.posts]
        self.assertEqual(kinds, ["document_add", "document_tag"])
        self.assertIn("document-999/tag/profile-123", self.posts[1][1])

    def test_state_skip_on_rerun(self):
        os.environ["GENI_ACCESS_TOKEN"] = "tok"
        args = _run_args(manifest=self.manifest)
        g.cmd_run(args)
        n = len(self.posts)
        args2 = _run_args(manifest=self.manifest, state=args.state)
        g.cmd_run(args2)
        self.assertEqual(len(self.posts), n)  # nothing re-sent

    def test_server_listing_skip_without_state(self):
        os.environ["GENI_ACCESS_TOKEN"] = "tok"
        self.listings[("123", "documents")].add(("Doc A", "https://x/1"))
        args = _run_args(manifest=self.manifest)
        g.cmd_run(args)
        self.assertEqual(self.posts, [])

    def test_uncertain_write_reconciled_no_resend(self):
        os.environ["GENI_ACCESS_TOKEN"] = "tok"
        orig = self.fake
        calls = {"add": 0}

        def flaky(method, kind, url, token=None, data=None):
            if kind == "document_add":
                calls["add"] += 1
                self.listings[("123", "documents")].add(("Doc A", "https://x/1"))
                raise g.UncertainWrite("timeout after send")
            return orig(method, kind, url, token, data)

        g.execute = flaky
        args = _run_args(manifest=self.manifest)
        self.assertEqual(g.cmd_run(args), 0)
        self.assertEqual(calls["add"], 1)  # mutation sent once, reconciled via listing
        with open(args.state, encoding="utf-8") as f:
            state = json.load(f)
        self.assertEqual(len(state["uploaded"]), 1)

    def test_uncertain_write_not_found_stops(self):
        os.environ["GENI_ACCESS_TOKEN"] = "tok"

        def flaky(method, kind, url, token=None, data=None):
            if kind == "document_add":
                raise g.UncertainWrite("timeout after send")
            return self.fake(method, kind, url, token, data)

        g.execute = flaky
        args = _run_args(manifest=self.manifest)
        self.assertEqual(g.cmd_run(args), 3)  # uncertain-write stop, no retry


class StatePreflightTests(unittest.TestCase):
    def test_preflight_rejects_unwritable_dir(self):
        d = tempfile.mkdtemp()
        os.chmod(d, 0o555)
        try:
            with self.assertRaises(g.ApiError):
                g.preflight_state_writable(os.path.join(d, "s.json"))
        finally:
            os.chmod(d, 0o755)

    def test_preflight_accepts_writable_dir(self):
        d = tempfile.mkdtemp()
        g.preflight_state_writable(os.path.join(d, "s.json"))

    def test_run_preflights_before_any_network(self):
        calls = []
        orig = g.execute
        g.execute = lambda *a, **k: calls.append(a)
        d = tempfile.mkdtemp()
        os.chmod(d, 0o555)
        try:
            args = _run_args(manifest=_manifest_file(MANIFEST), state=os.path.join(d, "s.json"))
            old = os.environ.get("GENI_ACCESS_TOKEN")
            os.environ["GENI_ACCESS_TOKEN"] = "t"
            try:
                rc = g.cmd_run(args)
            finally:
                if old is None:
                    del os.environ["GENI_ACCESS_TOKEN"]
                else:
                    os.environ["GENI_ACCESS_TOKEN"] = old
            self.assertEqual(rc, 1)
            self.assertEqual(calls, [], "no network call may happen before state preflight passes")
        finally:
            g.execute = orig
            os.chmod(d, 0o755)


class VerificationAndLogTests(unittest.TestCase):
    def setUp(self):
        self.manifest = _manifest_file(MANIFEST)
        self.posts = []
        self.listings = {("123", "documents"): set(), ("123", "photos"): set()}
        g.time.sleep = lambda s: None
        os.environ["GENI_ACCESS_TOKEN"] = "tok-secret-abc"

        def fake_execute(method, kind, url, token=None, data=None):
            if kind == "profile":
                return {"display_name": "Tamar Sara Ruth Vardi"}
            if kind in ("profile_documents", "profile_photos"):
                k = ("123", "documents" if kind == "profile_documents" else "photos")
                return {
                    "results": [
                        {"title": t[0], "source_url": t[1] if len(t) > 1 else None}
                        for t in self.listings[k]
                    ]
                }
            if kind in ("document_add", "photo_add"):
                self.posts.append((kind, url, data))
                return {"id": "999"}
            if kind in ("document_tag", "photo_tag"):
                self.posts.append((kind, url, data))
                return {}  # tag acknowledged, but listing NEVER shows it
            raise AssertionError(kind)

        g.execute = fake_execute

    def tearDown(self):
        import importlib

        importlib.reload(g)
        os.environ.pop("GENI_ACCESS_TOKEN", None)

    def test_unverified_post_stops_exit4_not_done(self):
        args = _run_args(manifest=self.manifest)
        rc = g.cmd_run(args)
        self.assertEqual(rc, 4)
        kinds = [p[0] for p in self.posts]
        self.assertEqual(kinds, ["document_add", "document_tag"], "no blind retry of the mutation")
        with open(args.state, encoding="utf-8") as f:
            state = json.load(f)
        self.assertEqual(state["uploaded"], [], "unverified item must not be done")

    def test_log_file_written_and_privacy_safe(self):
        args = _run_args(manifest=self.manifest)
        g.cmd_run(args)
        log_path = os.path.join(os.path.dirname(os.path.abspath(args.state)), "geni-upload-run.log")
        with open(log_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("run start", content)
        self.assertIn("exit 4", content)
        self.assertNotIn("tok-secret-abc", content)
        self.assertNotIn("Authorization", content)


class RepoSyncTests(unittest.TestCase):
    """Repo-backed completion tracking (upload-status.yaml next to the
    manifest) and best-effort commit+push after verified uploads."""

    def setUp(self):
        self.manifest = _manifest_file(MANIFEST)
        self.posts = []
        self.listings = {("123", "documents"): set(), ("123", "photos"): set()}
        self.pending = []
        g.time.sleep = lambda s: None
        os.environ["GENI_ACCESS_TOKEN"] = "tok"

        def fake_execute(method, kind, url, token=None, data=None):
            if kind == "profile":
                return {"display_name": "Tamar Sara Ruth Vardi"}
            if kind in ("profile_documents", "profile_photos"):
                k = ("123", "documents" if kind == "profile_documents" else "photos")
                return {
                    "results": [
                        {"title": t[0], "source_url": t[1] if len(t) > 1 else None}
                        for t in self.listings[k]
                    ]
                }
            if kind in ("document_add", "photo_add"):
                self.posts.append((kind, url, data))
                self.pending.append(data)
                return {"id": "999"}
            if kind in ("document_tag", "photo_tag"):
                self.posts.append((kind, url, data))
                for d in self.pending:
                    k = ("123", "documents" if kind == "document_tag" else "photos")
                    self.listings[k].add(
                        (d.get("title"), d.get("source_url"))
                        if kind == "document_tag"
                        else (d.get("title"),)
                    )
                self.pending = []
                return {}
            raise AssertionError(kind)

        g.execute = fake_execute

    def tearDown(self):
        import importlib

        importlib.reload(g)
        os.environ.pop("GENI_ACCESS_TOKEN", None)

    def test_preseeded_status_skips_with_server_proof(self):
        key = "123:documents:Doc A"
        g.save_status(
            self.manifest,
            {
                "items": {
                    key: {
                        "status": "uploaded",
                        "object_id": "document-1",
                        "verified_at": "2026-10-25T00:00:00Z",
                        "verified_by": "get-readback",
                    }
                }
            },
        )
        self.listings[("123", "documents")].add(("Doc A", "https://x/1"))
        args = _run_args(manifest=self.manifest)
        self.assertEqual(g.cmd_run(args), 0)
        self.assertEqual(self.posts, [], "server-confirmed item must not be re-uploaded")

    def test_stale_status_without_server_proof_blocks_no_reupload(self):
        key = "123:documents:Doc A"
        g.save_status(
            self.manifest,
            {
                "items": {
                    key: {
                        "status": "uploaded",
                        "object_id": "document-1",
                        "verified_at": "2026-10-25T00:00:00Z",
                        "verified_by": "get-readback",
                    }
                }
            },
        )
        args = _run_args(manifest=self.manifest)  # listing stays EMPTY
        self.assertEqual(g.cmd_run(args), 3)
        self.assertEqual(
            self.posts, [], "status not confirmed by the server must NEVER auto-reupload"
        )
        status = g.load_status(self.manifest)
        self.assertEqual(status["items"][key]["status"], "uncertain")

    def test_verified_upload_writes_status_file(self):
        args = _run_args(manifest=self.manifest)
        self.assertEqual(g.cmd_run(args), 0)
        status = g.load_status(self.manifest)
        rec = status["items"]["123:documents:Doc A"]
        self.assertEqual(rec["status"], "uploaded")
        self.assertEqual(rec["object_id"], "999")
        self.assertEqual(rec["verified_by"], "get-readback")

    def test_sync_commits_and_pushes_to_remote(self):
        import subprocess as sp

        base = tempfile.mkdtemp()
        remote = os.path.join(base, "remote.git")
        work = os.path.join(base, "work")
        sp.run(["git", "init", "-q", "--bare", remote], check=True)
        sp.run(["git", "clone", "-q", remote, work], check=True)
        sp.run(["git", "-C", work, "checkout", "-qb", "main"], check=True)
        manifest = os.path.join(work, "manifest.yaml")
        sp.run(["cp", self.manifest, manifest], check=True)
        sp.run(["git", "-C", work, "add", "manifest.yaml"], check=True)
        sp.run(
            [
                "git",
                "-C",
                work,
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "commit",
                "-qm",
                "init",
            ],
            check=True,
        )
        sp.run(["git", "-C", work, "push", "-qu", "origin", "main"], check=True)
        args = _run_args(manifest=manifest, no_repo_sync=False)
        self.assertEqual(g.cmd_run(args), 0)
        shown = sp.run(
            ["git", "-C", remote, "show", "main:upload-status.yaml"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("Doc A", shown.stdout)
        self.assertIn("get-readback", shown.stdout)

    def test_push_failure_does_not_fail_run_or_reupload(self):
        # not a git repo at all: sync is skipped, run still succeeds
        args = _run_args(manifest=self.manifest, no_repo_sync=False)
        self.assertEqual(g.cmd_run(args), 0)
        self.assertEqual(len([p for p in self.posts if p[0] == "document_add"]), 1)


class SyncFailureTests(unittest.TestCase):
    def setUp(self):
        self.manifest = _manifest_file(MANIFEST)
        self.posts = []
        self.listings = {("123", "documents"): set(), ("123", "photos"): set()}
        self.pending = []
        g.time.sleep = lambda s: None
        os.environ["GENI_ACCESS_TOKEN"] = "tok"

        def fake_execute(method, kind, url, token=None, data=None):
            if kind == "profile":
                return {"display_name": "Tamar Sara Ruth Vardi"}
            if kind in ("profile_documents", "profile_photos"):
                k = ("123", "documents" if kind == "profile_documents" else "photos")
                return {
                    "results": [
                        {"title": t[0], "source_url": t[1] if len(t) > 1 else None}
                        for t in self.listings[k]
                    ]
                }
            if kind in ("document_add", "photo_add"):
                self.posts.append((kind, url, data))
                self.pending.append(data)
                return {"id": "999"}
            if kind in ("document_tag", "photo_tag"):
                self.posts.append((kind, url, data))
                for d in self.pending:
                    k = ("123", "documents" if kind == "document_tag" else "photos")
                    self.listings[k].add(
                        (d.get("title"), d.get("source_url"))
                        if kind == "document_tag"
                        else (d.get("title"),)
                    )
                self.pending = []
                return {}
            raise AssertionError(kind)

        g.execute = fake_execute

    def tearDown(self):
        import importlib

        importlib.reload(g)
        os.environ.pop("GENI_ACCESS_TOKEN", None)

    def _git_repo_with_failing_push(self):
        import subprocess as sp

        work = tempfile.mkdtemp()
        sp.run(["git", "init", "-q", work], check=True)  # no remote: push fails
        manifest = os.path.join(work, "manifest.yaml")
        sp.run(["cp", self.manifest, manifest], check=True)
        return manifest

    def test_push_failure_exits_5_loudly(self):
        manifest = self._git_repo_with_failing_push()
        args = _run_args(manifest=manifest, no_repo_sync=False)
        rc = g.cmd_run(args)
        self.assertEqual(rc, 5)
        # item verified on Geni and marked locally despite the push failure
        status = g.load_status(manifest)
        self.assertIn("123:documents:Doc A", status["items"])

    def test_next_run_retries_failed_sync(self):
        """Container flow: run 1's status push fails; run 2 starts from a
        FRESH clone (remote lacks the status commit) with the persistent
        /state file - it must resync without re-uploading."""
        import subprocess as sp

        base = tempfile.mkdtemp()
        remote = os.path.join(base, "remote.git")
        work1 = os.path.join(base, "work1")
        sp.run(["git", "init", "-q", "--bare", remote], check=True)
        sp.run(["git", "clone", "-q", remote, work1], check=True)
        sp.run(["git", "-C", work1, "checkout", "-qb", "main"], check=True)
        manifest1 = os.path.join(work1, "manifest.yaml")
        sp.run(["cp", self.manifest, manifest1], check=True)
        sp.run(["git", "-C", work1, "add", "manifest.yaml"], check=True)
        sp.run(
            [
                "git",
                "-C",
                work1,
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "commit",
                "-qm",
                "init",
            ],
            check=True,
        )
        sp.run(["git", "-C", work1, "push", "-qu", "origin", "main"], check=True)
        # break pushes, then run 1: upload verified locally, push fails
        sp.run(
            ["git", "-C", work1, "remote", "set-url", "origin", os.path.join(base, "broken.git")],
            check=True,
        )
        args = _run_args(manifest=manifest1, no_repo_sync=False)
        self.assertEqual(g.cmd_run(args), 5)
        n_posts = len(self.posts)
        # run 2: fresh clone from the real remote + the persistent state file
        work2 = os.path.join(base, "work2")
        sp.run(["git", "clone", "-q", "-b", "main", remote, work2], check=True)
        manifest2 = os.path.join(work2, "manifest.yaml")
        args2 = _run_args(manifest=manifest2, state=args.state, no_repo_sync=False)
        self.assertEqual(g.cmd_run(args2), 0)
        self.assertEqual(len(self.posts), n_posts, "no re-upload during resync")
        shown = sp.run(
            ["git", "--git-dir", remote, "show", "main:upload-status.yaml"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("Doc A", shown.stdout)


class UncertainBlockTests(unittest.TestCase):
    def setUp(self):
        self.manifest = _manifest_file(MANIFEST)
        self.posts = []
        self.listings = {("123", "documents"): set(), ("123", "photos"): set()}
        self.pending = []
        self.fail_adds = True
        g.time.sleep = lambda s: None
        os.environ["GENI_ACCESS_TOKEN"] = "tok"

        def fake_execute(method, kind, url, token=None, data=None):
            if kind == "profile":
                return {"display_name": "Tamar Sara Ruth Vardi"}
            if kind in ("profile_documents", "profile_photos"):
                k = ("123", "documents" if kind == "profile_documents" else "photos")
                return {
                    "results": [
                        {"title": t[0], "source_url": t[1] if len(t) > 1 else None}
                        for t in self.listings[k]
                    ]
                }
            if kind in ("document_add", "photo_add"):
                self.posts.append((kind, url, data))
                if self.fail_adds:
                    raise g.UncertainWrite("timeout after send")
                self.pending.append(data)
                return {"id": "999"}
            if kind in ("document_tag", "photo_tag"):
                self.posts.append((kind, url, data))
                for d in self.pending:
                    k = ("123", "documents" if kind == "document_tag" else "photos")
                    self.listings[k].add(
                        (d.get("title"), d.get("source_url"))
                        if kind == "document_tag"
                        else (d.get("title"),)
                    )
                self.pending = []
                return {}
            raise AssertionError(kind)

        g.execute = fake_execute

    def tearDown(self):
        import importlib

        importlib.reload(g)
        os.environ.pop("GENI_ACCESS_TOKEN", None)

    def test_uncertain_marked_and_blocked_next_run(self):
        args = _run_args(manifest=self.manifest)
        self.assertEqual(g.cmd_run(args), 3)
        status = g.load_status(self.manifest)
        self.assertEqual(status["items"]["123:documents:Doc A"]["status"], "uncertain")
        self.fail_adds = False
        n = len(self.posts)
        args2 = _run_args(manifest=self.manifest, state=args.state)
        self.assertEqual(g.cmd_run(args2), 0)
        self.assertEqual(
            len(self.posts), n, "uncertain item must stay BLOCKED until manually resolved"
        )

    def test_resolved_uncertain_retries(self):
        args = _run_args(manifest=self.manifest)
        self.assertEqual(g.cmd_run(args), 3)
        key = "123:documents:Doc A"
        st = g.load_status(self.manifest)
        st["items"][key]["status"] = "not_found"  # explicit user resolution
        g.save_status(self.manifest, st)
        self.fail_adds = False
        args2 = _run_args(manifest=self.manifest, state=args.state)
        self.assertEqual(g.cmd_run(args2), 0)
        self.assertIn("document_add", [p[0] for p in self.posts])


class ConcurrencyTests(unittest.TestCase):
    def test_lock_refuses_second_run(self):
        import fcntl

        os.environ["GENI_ACCESS_TOKEN"] = "tok"
        manifest = _manifest_file(MANIFEST)
        args = _run_args(manifest=manifest)
        lock_path = os.path.join(os.path.dirname(os.path.abspath(args.state)), ".geni-upload.lock")
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        fd = open(lock_path, "w")  # noqa: SIM115 - lock fd must stay open for flock
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            self.assertEqual(g.cmd_run(args), 6)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()


class EntrypointStaticTests(unittest.TestCase):
    def setUp(self):
        here = os.path.join(os.path.dirname(__file__), "..", "entrypoint.sh")
        with open(os.path.abspath(here), encoding="utf-8") as f:
            self.sh = f.read()

    def test_repo_url_validated_github_only(self):
        self.assertIn("https://github.com/*/*.git", self.sh)

    def test_expect_sha_supported(self):
        self.assertIn("GENI_UPLOAD_EXPECT_SHA", self.sh)
        self.assertIn("rev-parse HEAD", self.sh)

    def test_askpass_prompt_aware_github_only(self):
        self.assertIn("*github.com*)", self.sh)
        self.assertIn("*) exit 1", self.sh)

    def test_executes_pinned_tool_not_clone_code(self):
        self.assertIn("exec python /opt/geni_upload.py", self.sh)
        self.assertNotIn("scripts/geni_upload/geni_upload.py", self.sh)


if __name__ == "__main__":
    unittest.main()


class PlanVerdictTests(unittest.TestCase):
    """Regression 2026-10-25: plan printed 'PLAN (VERIFIED)' BEFORE the
    profile GETs, so a run whose every GET returned 401 still showed a
    VERIFIED header. The verdict must reflect actual results."""

    def _args(self, manifest_path, token_file=None):
        return argparse.Namespace(manifest=manifest_path, token_file=token_file)

    def _patch(self, verify):
        self._orig_verify = g.verify_profile
        self._orig_list = g.list_tagged
        g.verify_profile = verify
        g.list_tagged = lambda token, pid, kind: []

    def tearDown(self):
        if hasattr(self, "_orig_verify"):
            g.verify_profile = self._orig_verify
            g.list_tagged = self._orig_list

    def _run_plan(self, token):
        import contextlib
        import io

        os.environ.pop("GENI_ACCESS_TOKEN", None)
        path = _manifest_file(MANIFEST)
        tf = None
        if token is not None:
            fd, tf = tempfile.mkstemp()
            os.write(fd, token.encode())
            os.close(fd)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = g.cmd_plan(self._args(path, token_file=tf))
        return rc, buf.getvalue()

    def test_401_never_prints_verified_and_exits_1(self):
        def boom(token, pid, expect):
            raise g.ApiError("GET https://www.geni.com/api/profile-123 -> HTTP 401")

        self._patch(boom)
        rc, out = self._run_plan("dummy-token")
        self.assertEqual(rc, 1)
        self.assertNotIn("VERIFIED", out.splitlines()[0])
        self.assertNotIn("PLAN (VERIFIED)", out)
        self.assertIn("verification: FAILED", out)

    def test_all_ok_prints_verdict_and_exits_0(self):
        self._patch(lambda token, pid, expect: "Tamar Vardi")
        rc, out = self._run_plan("dummy-token")
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines()[0], "PLAN:")
        self.assertIn("verification: OK", out)

    def test_no_token_skips_verification(self):
        rc, out = self._run_plan(None)
        self.assertEqual(rc, 0)
        self.assertIn("verification: SKIPPED", out)


class RateLimitTests(unittest.TestCase):
    """2026-10-25: a live plan run tripped Geni's rate limit (HTTP 429).
    The client must pace requests and must STOP on 429 - never auto-retry
    (the user's standing stop-on-throttle rule)."""

    def setUp(self):
        self._saved = dict(g._RATE)
        g._RATE.update({"min_interval": 10.0, "last": 0.0, "retry_after": 0.0})
        self.sleeps = []
        self._orig_sleep = g._sleep
        g._sleep = self.sleeps.append
        self._orig_urlopen = g.urllib.request.urlopen

    def tearDown(self):
        g._RATE.update(self._saved)
        g._sleep = self._orig_sleep
        g.urllib.request.urlopen = self._orig_urlopen

    class _R:
        def __init__(self, headers=None):
            self.headers = headers or {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true}'

    def _http429(self, headers=None):
        import io

        return g.urllib.error.HTTPError(
            "https://x", 429, "Too Many", headers, io.BytesIO(b'{"error":{}}')
        )

    def test_429_stops_without_retry(self):
        calls = []

        def boom(req, data=None, timeout=None):
            calls.append(1)
            raise self._http429()

        g.urllib.request.urlopen = boom
        with self.assertRaises(g.ApiError) as ctx:
            g.execute("GET", "profile", "https://x", "tok")
        self.assertEqual(len(calls), 1)  # no automatic retry
        self.assertIn("STOPPING", str(ctx.exception))

    def test_429_records_cooldown_from_window_header(self):
        def boom(req, data=None, timeout=None):
            raise self._http429({"X-API-Rate-Window": "30"})

        g.urllib.request.urlopen = boom
        before = g.time.time()
        with self.assertRaises(g.ApiError):
            g.execute("GET", "profile", "https://x", "tok")
        self.assertGreaterEqual(g._RATE["retry_after"], before + 30)

    def test_pacing_sleeps_between_requests(self):
        g.urllib.request.urlopen = lambda req, data=None, timeout=None: self._R()
        g.execute("GET", "profile", "https://x", "tok")  # first: last=0, no wait
        g.execute("GET", "profile", "https://x", "tok")  # second: must pace
        self.assertTrue(
            any(w >= 9 for w in self.sleeps), f"expected a pacing sleep >= ~10s, got {self.sleeps}"
        )

    def test_rate_headers_adapt_interval_and_cooldown(self):
        g._update_rate(
            {"X-API-Rate-Limit": "6", "X-API-Rate-Window": "60", "X-API-Rate-Remaining": "0"}
        )
        self.assertEqual(g._RATE["min_interval"], 10.0)
        self.assertGreater(g._RATE["retry_after"], g.time.time() + 59)
        g._update_rate(None)  # tolerated
        g._update_rate({"X-API-Rate-Limit": "garbage"})  # tolerated


class NameSurfaceTests(unittest.TestCase):
    """2026-10-25: live Geni profiles whose PAGE HEADINGS exactly match
    expect_name ('Dana Anna Alon (Peled)', 'David Menachem Alon')
    were SKIPPED because the API display_name is first+last only (public
    client fixture schema: middle/maiden/nick/per-language are separate
    fields). verify_profile must match against all canonical name fields
    of the SAME profile - and still reject the wrong person."""

    MARRIED_SUBJ: ClassVar = {
        "display_name": "Dana Alon",
        "first_name": "Dana",
        "middle_name": "Anna",
        "last_name": "Alon",
        "maiden_name": "Peled",
        "names": {"he-IL": {"first_name": "דנה", "last_name": "אלון"}},
    }
    HEBREW_SUBJ: ClassVar = {
        "display_name": "דוד אלון",
        "names": {"en": {"first_name": "David", "middle_name": "Menachem", "last_name": "Alon"}},
    }
    WRONG: ClassVar = {
        "display_name": "Ruti Alon",
        "first_name": "Ruti",
        "last_name": "Alon",
        "maiden_name": "Berger",
    }

    def test_married_and_maiden_tokens_match(self):
        self.assertTrue(
            g.name_matches(g.profile_name_surface(self.MARRIED_SUBJ), "Dana Anna Peled")
        )

    def test_hebrew_display_latin_fields_match(self):
        self.assertTrue(
            g.name_matches(g.profile_name_surface(self.HEBREW_SUBJ), "David Menachem Alon")
        )

    def test_wrong_person_still_rejected(self):
        self.assertFalse(g.name_matches(g.profile_name_surface(self.WRONG), "Dana Anna Peled"))

    def test_missing_token_still_rejected(self):
        p = {
            "display_name": "Dana Alon",
            "first_name": "Dana",
            "last_name": "Alon",
        }  # no Anna, no Peled anywhere
        self.assertFalse(g.name_matches(g.profile_name_surface(p), "Dana Anna Peled"))

    def test_empty_profile_rejected(self):
        self.assertFalse(g.name_matches(g.profile_name_surface({}), "Dana Anna Peled"))

    def test_mismatch_logs_observed_name_fields(self):
        # 2026-10-25: the live plan SKIPPED all 3 targets with no usable
        # diagnostic ("no recorded name ... matches"). The mismatch error
        # must carry the observed name fields so the encrypted log shows
        # the real response shape; the public Actions log never sees it.
        p = {
            "display_name": "שרה לוי",
            "first_name": "שרה",
            "last_name": "לוי",
            "names": {"en": {"first_name": "Sara", "last_name": "Levi"}},
            "birth": {"date": "1900"},
            "gender": "female",
        }
        orig = g.execute
        g.execute = lambda *a, **k: p
        try:
            with self.assertRaises(g.ApiError) as cm:
                g.verify_profile("tok", "123", "Dana Tzionit")
        finally:
            g.execute = orig
        msg = str(cm.exception)
        fields_part, _, keys_part = msg.partition("; response keys:")
        self.assertIn("שרה", fields_part)
        self.assertIn("first_name", fields_part)
        self.assertIn("Sara", fields_part)
        self.assertNotIn("1900", fields_part)  # names only: no birth data
        self.assertNotIn("gender", fields_part)
        # key NAMES only in the keys segment - never values
        self.assertIn('"birth"', keys_part)
        self.assertIn('"gender"', keys_part)
        self.assertNotIn("1900", keys_part)
        self.assertNotIn("female", keys_part)

    def test_mismatch_observed_fields_sorted_and_compact(self):
        p = {"display_name": "X Y", "maiden_name": "Z", "nicknames": ["Xi"], "names": {}}
        orig = g.execute
        g.execute = lambda *a, **k: p
        try:
            with self.assertRaises(g.ApiError) as cm:
                g.verify_profile("tok", "9", "No Such")
        finally:
            g.execute = orig
        msg = str(cm.exception)
        fields_part = msg.split("; response keys:")[0]
        self.assertIn('"display_name": "X Y"', fields_part)
        self.assertIn('"maiden_name": "Z"', fields_part)
        self.assertNotIn('"names"', fields_part)  # empty dict omitted (quoted key;
        # "nicknames" legitimately contains the substring)


class PlanThrottleAbortTests(unittest.TestCase):
    """Review MAJOR 1 (2026-10-25): cmd_plan caught the 429 ApiError per
    target and CONTINUED to the next profile - automatic continuation
    after a throttle. A 429 must abort the whole plan: no further
    requests may leave the process."""

    def setUp(self):
        self._saved = dict(g._RATE)
        g._RATE.update({"min_interval": 0.0, "last": 0.0, "retry_after": 0.0})
        self._orig_sleep = g._sleep
        g._sleep = lambda s: None

    def tearDown(self):
        g._RATE.update(self._saved)
        g._sleep = self._orig_sleep

    def test_429_aborts_plan_no_further_requests(self):
        two = {
            "targets": [
                {
                    "profile_id": "123",
                    "expect_name": "Tamar Vardi",
                    "documents": [{"title": "A", "source_url": "https://x/1"}],
                },
                {
                    "profile_id": "456",
                    "expect_name": "Second Person",
                    "documents": [{"title": "B", "source_url": "https://x/2"}],
                },
            ]
        }
        path = _manifest_file(two)
        requests = []

        def fake_execute(method, kind, url, token=None, data=None):
            requests.append(url)
            if "profile-123" in url:
                raise g.ThrottledError("GET ... -> HTTP 429 ... STOPPING")
            return {"display_name": "Second Person"}

        orig = g.execute
        g.execute = fake_execute
        try:
            fd, tf = tempfile.mkstemp()
            os.write(fd, b"tok")
            os.close(fd)
            args = argparse.Namespace(manifest=path, token_file=tf)
            with self.assertRaises(g.ThrottledError):
                g.cmd_plan(args)
        finally:
            g.execute = orig
        self.assertEqual(len(requests), 1, f"requests after throttle: {requests}")

    def test_throttled_is_apierror_for_main_exit1(self):
        self.assertTrue(issubclass(g.ThrottledError, g.ApiError))

    def test_nonstring_name_fields_tolerated(self):
        p = {
            "display_name": "Dana Alon",
            "name": {"structured": True},
            "first_name": ["Dana"],
            "middle_name": "Anna",
            "maiden_name": "Peled",
        }
        self.assertTrue(g.name_matches(g.profile_name_surface(p), "Dana Anna Peled"))


class ResponseKeysDiagnosticTests(unittest.TestCase):
    """2026-10-25: a live diagnostic plan produced EMPTY observed name
    fields ({}) for all targets - the live GET profile response matches
    no assumed schema (absent OR wrong-typed fields; cause not yet
    isolated). observed_response_keys logs top-level key NAMES ONLY
    (never values) to distinguish an error envelope, a results wrapper,
    an empty body, and an unexpected profile schema."""

    def test_error_envelope_shape(self):
        p = {"error": {"type": "ApiException", "message": "secret detail"}}
        keys = g.observed_response_keys(p)
        self.assertIn('"error"', keys)
        self.assertNotIn("secret detail", keys)
        self.assertNotIn("ApiException", keys)

    def test_results_wrapper_shape(self):
        p = {"results": [{"display_name": "Should Not Leak"}]}
        keys = g.observed_response_keys(p)
        self.assertEqual(
            keys,
            '{"keys": ["results"], "results_len": 1, "results_type": "list"}',
        )
        self.assertNotIn("Should Not Leak", keys)

    def test_results_empty_shape(self):
        # an id not resolving visibly: documented dispatcher behaviour is
        # an EMPTY results set - must surface as len 0, contents never logged
        keys = g.observed_response_keys({"results": []})
        self.assertEqual(
            keys,
            '{"keys": ["results"], "results_len": 0, "results_type": "list"}',
        )

    def test_empty_body_shape(self):
        self.assertEqual(g.observed_response_keys({}), '{"keys": []}')

    def test_profile_schema_keys_sorted(self):
        keys = g.observed_response_keys({"last_name": "x", "id": "p-1", "display_name": "y"})
        self.assertEqual(keys, '{"keys": ["display_name", "id", "last_name"]}')

    def test_non_dict_response(self):
        self.assertEqual(g.observed_response_keys([1, 2]), '{"_type": "list"}')


class WhoamiTests(unittest.TestCase):
    """geni-uploader#11: shape-only whoami diagnostic. The log/print surface
    must carry key NAMES and value TYPES only - never response values."""

    def tearDown(self):
        import importlib
        importlib.reload(g)

    def _patch(self, response):
        def fake_execute(method, kind, url, token=None, data=None):
            assert (method, kind) == ("GET", "user")
            assert url.endswith("/api/user"), url
            return response
        g.execute = fake_execute

    def test_shape_keys_and_types_only_no_values(self):
        secret_vals = ["ZZSECRET-EMAIL@example.invalid", "ZZSECRETNAME",
                       "9000000000000000001"]
        self._patch({"id": secret_vals[2], "guid": "zz-secret-guid",
                     "name": secret_vals[1], "email": secret_vals[0],
                     "curated": True})
        shape = g.diagnose_whoami("tok")
        rendered = json.dumps(shape, sort_keys=True)
        self.assertEqual(shape, {"curated": "bool", "email": "str",
                                 "guid": "str", "id": "str", "name": "str"})
        for v in secret_vals + ["zz-secret-guid"]:
            self.assertNotIn(v, rendered)

    def test_non_dict_response_reported_as_shape(self):
        self._patch(["unexpected", "list"])
        shape = g.diagnose_whoami("tok")
        self.assertEqual(shape, {"<non-dict response>": "list"})

    def test_empty_dict_is_valid_shape(self):
        self._patch({})
        self.assertEqual(g.diagnose_whoami("tok"), {})

    def test_cmd_whoami_requires_token(self):
        os.environ.pop("GENI_ACCESS_TOKEN", None)
        args = argparse.Namespace(token_file=None)
        with self.assertRaises(g.ApiError):
            g.cmd_whoami(args)

    def test_cmd_whoami_prints_shape_no_values(self):
        self._patch({"id": "zz-secret-id", "name": "ZZSECRETNAME"})
        os.environ["GENI_ACCESS_TOKEN"] = "tok"
        try:
            args = argparse.Namespace(token_file=None)
            import contextlib
            import io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(g.cmd_whoami(args), 0)
            out = buf.getvalue()
            self.assertIn('"id": "str"', out)
            self.assertIn('"name": "str"', out)
            self.assertNotIn("zz-secret-id", out)
            self.assertNotIn("ZZSECRETNAME", out)
            self.assertIn("No writes performed.", out)
        finally:
            os.environ.pop("GENI_ACCESS_TOKEN", None)

    def test_user_get_is_allowlisted(self):
        self.assertIn(("GET", "user"), g.ALLOWLIST)


class ContrastDiagnosticTest(unittest.TestCase):
    """geni-uploader#11: shape-only endpoint contrast diagnostic. Output must
    carry keys/lengths/booleans only - never response values (ids, names)."""

    def tearDown(self):
        import importlib
        importlib.reload(g)

    def _manifest(self, tmp, pids):
        path = os.path.join(tmp, "m.yaml")
        with open(path, "w") as f:
            f.write("targets:\n")
            f.writelines(f'  - profile_id: "{pid}"\n'
                        f'    expect_name: "ZZSENTINEL PERSONA"\n' for pid in pids)
        return path

    def _patch_execute(self, responses, calls):
        def fake_execute(method, kind, url, token=None, data=None):
            calls.append((method, kind, url))
            return responses.pop(0)
        g.execute = fake_execute

    def _run(self, responses, pids=("1000000000000000001",)):
        import contextlib
        import io
        import tempfile
        calls = []
        self._patch_execute(list(responses), calls)
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                token_file=None, manifest=self._manifest(tmp, pids))
            os.environ["GENI_ACCESS_TOKEN"] = "tok"
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.assertEqual(g.cmd_contrast(args), 0)
            finally:
                os.environ.pop("GENI_ACCESS_TOKEN", None)
        return buf.getvalue(), calls

    def test_envelope_managed_id_drives_singular_contrast_no_values(self):
        served = "9000000000000000007"
        out, calls = self._run([
            {"results": [{"id": served}]},                 # managed-profiles
            {"id": served, "name": "ZZSERVEDNAME"},        # singular served id
            {"results": []},                               # bulk targets: miss
        ])
        kinds = [k for _, k, _ in calls]
        self.assertEqual(kinds, ["user_managed_profiles", "profile", "profile"])
        self.assertTrue(calls[1][2].endswith(f"/api/profile-{served}"))
        self.assertIn("ids=1000000000000000001", calls[2][2])
        self.assertIn('"results_len": 0', out)
        self.assertIn('"bare_nonempty_id_name": true', out)
        self.assertIn("No writes performed.", out)
        self.assertNotIn(served, out)
        self.assertNotIn("ZZSERVEDNAME", out)

    def test_bare_object_managed_form_supported(self):
        served = "9000000000000000008"
        out, _calls = self._run([
            {"id": served},                                # bare-object collapse
            {"results": []},                               # singular: miss too
            {"results": [{"id": "9000000000000000001",
                          "name": "ZZTARGETNAME"}]},       # bulk: serves
        ])
        # fields=id probe: id present, name absent by request
        self.assertIn('"bare_nonempty_id_name": false', out)
        self.assertIn('"keys": ["id"]', out)
        self.assertIn('"results_len": 1', out)
        self.assertIn('"all_items_nonempty_id_name": true', out)
        self.assertNotIn("ZZTARGETNAME", out)
        self.assertNotIn(served, out)

    def test_empty_managed_skips_singular_contrast(self):
        out, calls = self._run([
            {"results": []},                               # nothing served
            {"results": []},                               # bulk: miss
        ])
        self.assertEqual(len(calls), 2)
        self.assertIn("SKIPPED", out)

    def test_non_dict_payloads_reported_as_shapes(self):
        # non-dict managed-profiles response -> singular contrast SKIPPED,
        # so only two calls happen; both reported as type shapes.
        out, calls = self._run([["unexpected"], "plain"])
        self.assertEqual(len(calls), 2)
        self.assertIn('"top_type": "list"', out)
        self.assertIn('"top_type": "str"', out)
        self.assertIn("SKIPPED", out)

    def test_requires_token(self):
        import tempfile
        os.environ.pop("GENI_ACCESS_TOKEN", None)
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                token_file=None, manifest=self._manifest(tmp, ("1",)))
            with self.assertRaises(g.ApiError):
                g.cmd_contrast(args)

    def test_allowlist_covers_managed_profiles(self):
        self.assertIn(("GET", "user_managed_profiles"), g.ALLOWLIST)

    def test_bulk_url_multi_target_literal_commas(self):
        pids = ("1000000000000000001", "1000000000000000002",
                "1000000000000000003")
        _out, calls = self._run([
            {"results": [{"id": "9000000000000000007"}]},
            {"results": []},
            {"results": []},
        ], pids=pids)
        bulk_url = calls[2][2]
        self.assertIn("ids=1000000000000000001,1000000000000000002,"
                      "1000000000000000003", bulk_url)
        self.assertNotIn("%2C", bulk_url.upper())
