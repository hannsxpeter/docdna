import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_PATH = ROOT / "skill" / "scripts" / "docdna_scan.py"
SIGNALS_PATH = ROOT / "skill" / "catalog" / "signals.json"
FIXTURES = ROOT / "tests" / "fixtures"

TOP_KEYS = ["commit", "dirty", "drift", "generated", "inventory", "ownership", "root", "scan",
            "schema", "signals", "tool", "unknown", "version"]


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
                     "read_errors": 0, "truncated": False}}


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
            self.assertTrue(payload["signals"])
            self.assertEqual(payload["root"], os.path.abspath(tmp))

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
