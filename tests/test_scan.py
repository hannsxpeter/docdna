import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_PATH = ROOT / "skill" / "scripts" / "docdna_scan.py"
SIGNALS_PATH = ROOT / "skill" / "catalog" / "signals.json"
FIXTURES = ROOT / "tests" / "fixtures"

TOP_KEYS = ["commit", "content_fingerprint", "dirty", "drift", "generated", "inventory",
            "ownership", "root", "root_identity", "scan", "schema", "signals", "tool",
            "unknown", "version"]


def load_scan():
    spec = importlib.util.spec_from_file_location("docdna_scan", SCAN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_signals():
    with open(str(SIGNALS_PATH), encoding="utf-8") as handle:
        return json.load(handle)["signals"]


def write(root, rel, body):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def read_ctx(root):
    return {"root": str(root), "cache": {},
            "scan": {"files_read": 0, "files_capped": 0, "files_skipped_large": 0,
                     "files_skipped_outside": 0, "read_errors": 0, "truncated": False}}


def by_id(report):
    return dict((item["id"], item) for item in report["signals"])


def fixture_dirs():
    return sorted(str(path) for path in FIXTURES.iterdir() if path.is_dir())


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.scan = load_scan()

    def test_walk_keeps_github_and_prunes_node_modules_and_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, ".github/workflows/ci.yml", "name: ci\n")
            write(tmp, ".github/CODEOWNERS", "* @team\n")
            write(tmp, "node_modules/left-pad/index.js", "module.exports = 1\n")
            write(tmp, ".git/config", "[core]\n")
            write(tmp, "src/app.js", "console.log(1)\n")
            files, pruned = self.scan.walk_paths(tmp)

            self.assertIn(".github/workflows/ci.yml", files)
            self.assertIn(".github/CODEOWNERS", files)
            self.assertIn("src/app.js", files)
            self.assertEqual(sorted(pruned), [".git", "node_modules"])
            self.assertEqual([rel for rel in files if rel.startswith("node_modules/")], [])
            self.assertEqual([rel for rel in files if rel.startswith(".git/")], [])
            self.assertFalse(self.scan.prune_dir(".github"))
            self.assertTrue(self.scan.prune_dir(".git"))
            self.assertTrue(self.scan.prune_dir("node_modules"))
            self.assertTrue(self.scan.prune_dir(".hidden"))

            report = self.scan.scan(tmp, set(), False, 5)

            self.assertEqual(report["scan"]["index_source"], "walk")
            self.assertEqual(report["scan"]["dirs_pruned"], [".git", "node_modules"])
            self.assertTrue(report["ownership"]["codeowners"])
            self.assertEqual(report["ownership"]["codeowners_path"], ".github/CODEOWNERS")

    def test_deny_read_blocks_env_but_allows_example(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, ".env", "API_KEY=supersecretvalue\n")
            write(tmp, ".env.example", "API_KEY=changeme\n")
            write(tmp, "config/.env.local", "TOKEN=alsosecretvalue\n")

            self.assertTrue(self.scan.denied_read(".env"))
            self.assertTrue(self.scan.denied_read("config/.env.local"))
            self.assertFalse(self.scan.denied_read(".env.example"))
            self.assertFalse(self.scan.denied_read(".env.sample"))
            self.assertFalse(self.scan.denied_read(".env.template"))
            self.assertFalse(self.scan.denied_read("src/app.js"))

            ctx = read_ctx(tmp)

            self.assertIsNone(self.scan.read_text(ctx, ".env"))
            self.assertIsNone(self.scan.read_text(ctx, "config/.env.local"))
            self.assertIn("changeme", self.scan.read_text(ctx, ".env.example"))
            self.assertEqual(ctx["scan"]["files_read"], 1)

            report = self.scan.scan(tmp, set(), False, 5)
            body = json.dumps(report)

            self.assertEqual(report["scan"]["files_total"], 3)
            self.assertEqual(report["scan"]["files_denied"], 2)
            self.assertNotIn("supersecretvalue", body)
            self.assertNotIn("alsosecretvalue", body)

    def test_scanner_refuses_a_tracked_symlink_that_leaves_the_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            repo.mkdir()
            outside = write(base, "outside.py", "from flask import Flask\n"
                                               "app = Flask(__name__)\n"
                                               "@app.get(\"/outside-secret-marker\")\n")
            os.symlink(str(outside), str(repo / "server.py"))
            write(repo, "Procfile", "web: gunicorn server:app\n")
            subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
            subprocess.run(["git", "add", "Procfile", "server.py"], cwd=str(repo), check=True)

            report = self.scan.scan(str(repo), set(), False, 5)
            body = json.dumps(report)

            self.assertNotIn("outside-secret-marker", body)
            self.assertEqual(report["scan"]["files_skipped_outside"], 1)
            self.assertNotEqual(by_id(report)["iface.http"]["state"], "present")

    def test_scanner_refuses_metadata_for_a_document_symlink_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            repo.mkdir()
            outside = write(base, "outside.md", "outside document metadata marker\n")
            os.symlink(str(outside), str(repo / "README.md"))
            subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
            subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True)

            report = self.scan.scan(str(repo), set(), False, 5)
            document = report["inventory"]["docs"][0]

            self.assertEqual(document["path"], "README.md")
            self.assertIsNone(document["bytes"])
            self.assertEqual(report["scan"]["files_skipped_outside"], 1)

    def test_document_links_do_not_traverse_a_symlinked_directory_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            repo.mkdir()
            outside = base / "outside"
            write(outside, "secret.md", "outside linked document\n")
            write(repo, "README.md", "[secret](linked-docs/secret.md)\n")
            os.symlink(str(outside), str(repo / "linked-docs"))
            subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
            subprocess.run(["git", "add", "README.md", "linked-docs"], cwd=str(repo), check=True)

            report = self.scan.scan(str(repo), set(), False, 5)
            document = report["inventory"]["docs"][0]

            self.assertEqual(document["links_out"], 1)
            self.assertEqual(document["links_broken"], 1)

    def test_scanner_reads_a_symlink_that_resolves_inside_the_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = write(root, "src/actual.py", "IN_REPO_MARKER = True\n")
            os.symlink(str(target), str(root / "linked.py"))
            ctx = read_ctx(root)

            text = self.scan.read_text(ctx, "linked.py")

        self.assertIn("IN_REPO_MARKER", text)
        self.assertEqual(ctx["scan"]["files_skipped_outside"], 0)

    def test_no_git_walk_keeps_the_original_root_descriptor_during_a_root_swap(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            root.mkdir()
            (root / "original.txt").write_text("original\n", encoding="utf-8")
            moved = base / "repo-original"
            replacement = base / "replacement"
            replacement.mkdir()
            (replacement / "external.txt").write_text("outside\n", encoding="utf-8")
            filesystem = self.scan.safe_walk_paths.__globals__
            original_listdir = filesystem["_LISTDIR"]
            calls = {"count": 0}

            def swap_after_root_listing(descriptor):
                names = original_listdir(descriptor)
                calls["count"] += 1
                if calls["count"] == 1:
                    root.rename(moved)
                    replacement.rename(root)
                return names

            with mock.patch.dict(filesystem, {"_LISTDIR": swap_after_root_listing}):
                files, _ = self.scan.walk_paths(str(root))

            self.assertEqual(files, ["original.txt"])

    def test_no_git_walk_never_traverses_a_nested_directory_swapped_for_a_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            nested = root / "nested"
            nested.mkdir(parents=True)
            (nested / "original.txt").write_text("original\n", encoding="utf-8")
            moved = root / "nested-original"
            outside = base / "outside"
            outside.mkdir()
            (outside / "external.txt").write_text("outside\n", encoding="utf-8")
            filesystem = self.scan.safe_walk_paths.__globals__
            original_listdir = filesystem["_LISTDIR"]
            calls = {"count": 0}

            def swap_nested_after_root_listing(descriptor):
                names = original_listdir(descriptor)
                calls["count"] += 1
                if calls["count"] == 1:
                    nested.rename(moved)
                    os.symlink(str(outside), str(nested))
                return names

            with mock.patch.dict(filesystem, {"_LISTDIR": swap_nested_after_root_listing}):
                files, _ = self.scan.walk_paths(str(root))

            self.assertNotIn("nested/external.txt", files)

    def test_git_inventory_uses_the_bound_root_during_an_aba_swap(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            replacement = base / "replacement"
            moved = base / "repo-original"
            root.mkdir()
            replacement.mkdir()
            (root / "original.txt").write_text("original\n", encoding="utf-8")
            (replacement / "replacement.txt").write_text("replacement\n", encoding="utf-8")
            for repo, name in ((root, "original.txt"), (replacement, "replacement.txt")):
                subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
                subprocess.run(["git", "add", name], cwd=str(repo), check=True)
            bound = self.scan.safe_bind_root(str(root))
            original_run = subprocess.run

            def swap_only_around_child(command, **kwargs):
                root.rename(moved)
                replacement.rename(root)
                try:
                    return original_run(command, **kwargs)
                finally:
                    root.rename(replacement)
                    moved.rename(root)

            try:
                with mock.patch.object(self.scan.subprocess, "run",
                                       side_effect=swap_only_around_child):
                    files, _ = self.scan.git_paths(bound)
            finally:
                bound.close()

            self.assertEqual(files, ["original.txt"])

    def test_scanner_refuses_to_read_a_fifo_without_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            os.mkfifo(str(repo / "evil.py"))

            process = subprocess.run([sys.executable, str(SCAN_PATH), "--json", str(repo)],
                                     capture_output=True, text=True, timeout=5)

            self.assertEqual(process.returncode, 0, process.stderr)
            payload = json.loads(process.stdout)
            self.assertGreaterEqual(payload["scan"]["read_errors"], 1)

    def test_scanner_applies_read_denial_to_an_internal_symlink_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            write(repo, ".env", "from flask import Flask\n"
                                "app = Flask(__name__)\n"
                                "@app.get('/private-inrepo-marker')\n")
            os.symlink(".env", str(repo / "README.md"))
            write(repo, "Procfile", "web: gunicorn server:app\n")
            subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
            subprocess.run(["git", "add", "README.md", "Procfile"], cwd=str(repo), check=True)

            report = self.scan.scan(str(repo), set(), False, 5)
            body = json.dumps(report)

            self.assertNotIn("private-inrepo-marker", body)
            self.assertNotEqual(by_id(report)["iface.http"]["state"], "present")

    def test_scanner_does_not_read_a_hardlinked_external_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            repo.mkdir()
            outside = write(base, "outside.py", "from flask import Flask\n"
                                                 "app = Flask(__name__)\n"
                                                 "@app.get('/scanner-hardlink-marker')\n")
            os.link(str(outside), str(repo / "server.py"))
            write(repo, "Procfile", "web: gunicorn server:app\n")
            subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
            subprocess.run(["git", "add", "Procfile"], cwd=str(repo), check=True)

            report = self.scan.scan(str(repo), set(), False, 5)
            body = json.dumps(report)

            self.assertNotIn("scanner-hardlink-marker", body)
            self.assertNotEqual(by_id(report)["iface.http"]["state"], "present")

    def test_git_metrics_ignore_a_synthetic_merge_commit_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()

            def git(*args, name="Primary Author", email="primary@example.invalid"):
                command = ["git", "-C", str(repo), "-c", "user.name=" + name,
                           "-c", "user.email=" + email] + list(args)
                return subprocess.run(command, check=True, capture_output=True, text=True)

            git("init", "-q", "-b", "main")
            write(repo, "base.py", "BASE = True\n")
            git("add", "base.py")
            git("commit", "-q", "-m", "base")
            git("checkout", "-q", "-b", "feature")
            write(repo, "feature.py", "FEATURE = True\n")
            git("add", "feature.py")
            git("commit", "-q", "-m", "feature")
            before = self.scan.collect_git(str(repo))
            git("checkout", "-q", "main")
            git("merge", "-q", "--no-ff", "feature", "-m", "synthetic merge",
                name="Synthetic Merge", email="merge@example.invalid")

            after = self.scan.collect_git(str(repo))

            self.assertEqual(after["authors"], before["authors"])
            self.assertEqual(after["authors_window"], before["authors_window"])
            self.assertEqual(after["commits_window"], before["commits_window"])

    def test_git_metrics_ignore_release_tags_on_the_checked_out_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()

            def git(*args):
                command = ["git", "-C", str(repo), "-c", "user.name=Release Author",
                           "-c", "user.email=release@example.invalid"] + list(args)
                return subprocess.run(command, check=True, capture_output=True, text=True)

            git("init", "-q", "-b", "main")
            write(repo, "release.py", "VERSION = 1\n")
            git("add", "release.py")
            git("commit", "-q", "-m", "release candidate")
            before = self.scan.collect_git(str(repo))
            git("tag", "v1.0.0")
            tagged = self.scan.collect_git(str(repo))
            write(repo, "next.py", "NEXT = True\n")
            git("add", "next.py")
            git("commit", "-q", "-m", "next development commit")
            after = self.scan.collect_git(str(repo))

            self.assertEqual(tagged["tags"], before["tags"])
            self.assertEqual(after["tags"], before["tags"] + 1)

    def test_opaque_documents_are_indexed_but_not_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "README.md", "# hi\n")
            (Path(tmp) / "report.docx").write_bytes(b"PK\x03\x04 binary payload")
            (Path(tmp) / "handbook.pdf").write_bytes(b"%PDF-1.7 binary payload")
            report = self.scan.scan(tmp, set(), False, 5)
            inventory = report["inventory"]

            self.assertEqual(sorted(item["path"] for item in inventory["opaque"]),
                             ["handbook.pdf", "report.docx"])
            self.assertEqual(inventory["counts"]["opaque"], 2)
            self.assertEqual(inventory["counts"]["total"], 1)
            self.assertEqual([doc["path"] for doc in inventory["docs"]], ["README.md"])
            for item in inventory["opaque"]:
                self.assertFalse(item["parsed"])
                self.assertTrue(item["bytes"] > 0)
            self.assertEqual(report["scan"]["files_read"], 1)
            self.assertNotIn("binary payload", json.dumps(report))

    def test_git_metadata_degrades_to_null_outside_a_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "README.md", "# hi\n")
            report = self.scan.scan(tmp, set(), False, 5)
            doc = report["inventory"]["docs"][0]
            degraded = [item for item in report["signals"]
                        if item.get("note") == "no git history available"]

            self.assertIsNone(report["commit"])
            self.assertIsNone(report["dirty"])
            self.assertIsNone(doc["last_commit_sha"])
            self.assertIsNone(doc["last_commit_date"])
            self.assertIsNone(doc["days_since_commit"])
            self.assertEqual(report["ownership"]["top_authors"], [])
            self.assertEqual(report["ownership"]["single_author_paths"], [])
            self.assertTrue(degraded)
            for item in degraded:
                self.assertEqual(item["state"], "unknown")
                self.assertIsNone(item["confidence"])
                self.assertEqual(item["evidence"], [])

    def test_every_present_signal_carries_evidence(self):
        # hits means two different things depending on the detector. For path, grep and manifest
        # signals it counts occurrences, so present implies at least one. For git and derived
        # metric signals it carries a measured magnitude, and zero is a real measurement: a
        # repository cloned today has proc.last_commit_days = 0. Requiring hits > 0 there would
        # force the scanner either to report absent when it did successfully measure, which is the
        # absence-of-evidence-as-false error this project refuses, or to inflate the value.
        counting = set()
        for sig in load_signals():
            detect = sig.get("detect") or {}
            if detect.get("kind") in ("path", "grep", "manifest") and not detect.get("metric"):
                counting.add(sig["id"])

        for root in fixture_dirs() + [str(ROOT)]:
            report = self.scan.scan(root, set(), False, 5)
            for item in report["signals"]:
                if item["state"] != "present":
                    continue
                where = "%s: %s" % (os.path.basename(root), item["id"])
                self.assertTrue(item["evidence"], "%s is present with no evidence" % where)
                self.assertIsInstance(item["hits"], int, "%s has a non-integer hits" % where)
                self.assertTrue(item["hits"] >= 0, "%s is present with negative hits" % where)
                if item["id"] in counting:
                    self.assertTrue(item["hits"] > 0, "%s is present with no hits" % where)
                for record in item["evidence"]:
                    self.assertTrue(record.get("path"), "%s has an evidence record with no path"
                                    % where)

    def test_finish_refuses_present_without_evidence(self):
        sig = {"id": "docs.fake", "family": "docs", "label": "fake"}

        with self.assertRaises(ValueError):
            self.scan.finish(sig, "present", 3, [], 5)

    def test_evidence_is_capped_but_hits_are_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("a.sql", "b.sql", "c.sql", "d.sql"):
                write(tmp, name, "CREATE TABLE t (id INT);\n")
            capped = by_id(self.scan.scan(tmp, set(), False, 1))["data.ddl"]
            partial = by_id(self.scan.scan(tmp, set(), False, 3))["data.ddl"]
            full = by_id(self.scan.scan(tmp, set(), False, 5))["data.ddl"]

            self.assertEqual(capped["hits"], 4)
            self.assertEqual(len(capped["evidence"]), 1)
            self.assertTrue(capped["evidence_truncated"])
            self.assertEqual(partial["hits"], 4)
            self.assertEqual(len(partial["evidence"]), 3)
            self.assertTrue(partial["evidence_truncated"])
            self.assertEqual(full["hits"], 4)
            self.assertEqual(len(full["evidence"]), 4)
            self.assertFalse(full["evidence_truncated"])

    def test_max_evidence_holds_for_every_signal(self):
        report = self.scan.scan(str(ROOT), set(), False, 2)
        for item in report["signals"]:
            self.assertTrue(len(item["evidence"]) <= 2, "%s kept %d evidence records"
                            % (item["id"], len(item["evidence"])))
            if item["evidence_truncated"]:
                self.assertEqual(len(item["evidence"]), 2, item["id"])

    def test_json_cli_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "README.md", "# hi\n")
            proc = subprocess.run(
                [sys.executable, str(SCAN_PATH), "--json", "--max-evidence", "2", tmp],
                check=True,
                text=True,
                capture_output=True,
            )
            payload = json.loads(proc.stdout)

            self.assertEqual(sorted(payload), TOP_KEYS)
            self.assertEqual(payload["tool"], "docdna_scan")
            self.assertEqual(payload["schema"], self.scan.SCHEMA)
            self.assertEqual(payload["version"], self.scan.VERSION)
            self.assertRegex(payload["content_fingerprint"], r"^sha256:[0-9a-f]{64}$")
            self.assertTrue(payload["signals"])
            self.assertEqual(payload["root"], os.path.abspath(tmp))

    def test_content_fingerprint_changes_when_the_repository_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "README.md", "# original\n")
            before = self.scan.scan(tmp, set(), False, 5)["content_fingerprint"]
            write(tmp, "package.json", '{"dependencies":{"stripe":"1.0.0"}}\n')
            after = self.scan.scan(tmp, set(), False, 5)["content_fingerprint"]

            self.assertNotEqual(before, after)

    def test_deeply_nested_repository_json_is_ignored_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "package.json", "[" * 1500 + "0" + "]" * 1500)

            process = subprocess.run([sys.executable, str(SCAN_PATH), "--json", tmp],
                                     capture_output=True, text=True)

            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertNotIn("Traceback", process.stderr)
            self.assertEqual(json.loads(process.stdout)["tool"], "docdna_scan")

    def test_text_cli_runs_clean(self):
        proc = subprocess.run(
            [sys.executable, str(SCAN_PATH), str(FIXTURES / "solo_cli")],
            check=True,
            text=True,
            capture_output=True,
        )

        self.assertIn("docdna scan", proc.stdout)
        self.assertIn("I only see documentation committed to this repo.", proc.stdout)
        self.assertEqual(proc.stderr, "")

    def test_gated_signals_report_unknown_not_absent(self):
        signals = json.loads(SIGNALS_PATH.read_text(encoding="utf-8"))["signals"]
        for root in fixture_dirs():
            results = by_id(self.scan.scan(root, set(), False, 5))
            for sig in signals:
                if self.scan.predicate(results, sig.get("gate") or {"always": True}):
                    continue
                self.assertEqual(results[sig["id"]]["state"], "unknown",
                                 "%s: %s reported %s with a gate that did not fire"
                                 % (os.path.basename(root), sig["id"],
                                    results[sig["id"]]["state"]))

        results = by_id(self.scan.scan(str(FIXTURES / "client_spa"), set(), False, 5))

        self.assertEqual(results["iface.http"]["state"], "unknown")
        self.assertEqual(results["iface.http"]["note"], "gate did not fire")
        self.assertEqual(results["data.pii"]["state"], "unknown")
        self.assertEqual(results["data.pii"]["note"], "gate did not fire")


if __name__ == "__main__":
    unittest.main()
