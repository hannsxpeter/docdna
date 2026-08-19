"""P-MUST-04: standalone read-only status behavior."""

import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "skill" / "scripts" / "docdna_status.py"


def load_status():
    spec = importlib.util.spec_from_file_location("docdna_status_tests", str(STATUS_PATH))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(root):
    rows = []
    for current, dirs, files in os.walk(str(root)):
        dirs.sort()
        files.sort()
        rel_dir = os.path.relpath(current, str(root))
        for name in files:
            path = Path(current) / name
            rel = os.path.normpath(os.path.join(rel_dir, name))
            if path.is_symlink():
                rows.append((rel, "symlink", os.readlink(str(path))))
            else:
                rows.append((rel, "file", path.read_bytes()))
    return rows


def manifest(rows=None, assumptions=None, open_questions=None, tripwires=None):
    payload = {
        "schema": 1,
        "root": "/ignored-by-status",
        "repo_head": "abc1234",
        "generated_by": "docdna_select 1.3.0",
        "generated_at": "2026-08-19T00:00:00Z",
        "documents": rows or [],
        "excluded": [],
        "assumptions": assumptions or [],
        "open_questions": open_questions or [],
        "drift": [],
    }
    if tripwires is not None:
        payload["tripwires"] = tripwires
    return payload


def row(doc_id, status="pending", sensitivity="public", state="absent", extra=None):
    value = {
        "id": doc_id,
        "title": doc_id,
        "stage": "build",
        "path": "docs/build/%s.md" % doc_id.split(".")[-1],
        "write_status": status,
        "sensitivity": sensitivity,
        "state": state,
        "action": "write",
        "verdict": "required",
    }
    value.update(extra or {})
    return value


class StatusCliTests(unittest.TestCase):
    def run_status(self, repo, json_output=True):
        command = [sys.executable, str(STATUS_PATH)]
        if json_output:
            command.append("--json")
        command.append(str(repo))
        return subprocess.run(command, capture_output=True, text=True)

    def make_repo(self, payload=None, files=None, repo_name="repo"):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        repo = Path(tmp) / repo_name
        repo.mkdir()
        if payload is not None:
            target = repo / ".docdna" / "manifest.json"
            target.parent.mkdir()
            target.write_text(json.dumps(payload), encoding="utf-8")
        for rel, content in (files or {}).items():
            target = repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return repo

    def test_status_with_no_manifest_is_read_only_and_names_survey_as_next(self):
        repo = self.make_repo()
        before = snapshot(repo)

        first = self.run_status(repo)
        second = self.run_status(repo)

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(snapshot(repo), before)
        self.assertFalse((repo / ".docdna").exists())
        report = json.loads(first.stdout)
        self.assertEqual(report["mode"], "status")
        self.assertTrue(report["read_only"])
        self.assertEqual(report["summary"]["manifest"], "absent")
        self.assertEqual(report["next_action"]["id"], "survey")
        self.assertEqual(report["next_action"]["lane"], "read-only")
        self.assertIn("docdna_scan.py", report["next_action"]["command"])
        self.assertNotIn("next_actions", report)

    def test_status_prefers_verify_for_written_or_in_progress_document(self):
        rows = [row("build.verified", "verified"), row("build.pending"),
                row("build.written", "written"), row("build.progress", "in-progress")]
        files = {"docs/build/written.md": "written\n",
                 "docs/build/progress.md": "in progress\n"}
        repo = self.make_repo(manifest(rows), files)

        process = self.run_status(repo)

        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads(process.stdout)
        self.assertEqual(report["next_action"]["id"], "verify:build.written")
        self.assertEqual(report["next_action"]["lane"], "local-helper")
        self.assertIn("--verify docs/build/written.md", report["next_action"]["command"])
        self.assertEqual(list(report).count("next_action"), 1)

    def test_status_never_calls_select_scan_branch_commit_delete_write_or_target_commands(self):
        status = load_status()
        payload = manifest([row("build.written", "written")])
        repo = self.make_repo(payload, {"docs/build/written.md": "content\n"})
        before = snapshot(repo)

        with mock.patch("subprocess.run", side_effect=AssertionError("command executed")), \
                mock.patch("os.mkdir", side_effect=AssertionError("directory created")), \
                mock.patch("os.unlink", side_effect=AssertionError("file deleted")), \
                mock.patch("builtins.open", side_effect=AssertionError("unbounded open used")):
            report = status.inspect_status(str(repo))

        self.assertEqual(report["next_action"]["id"], "verify:build.written")
        self.assertEqual(snapshot(repo), before)
        for name in ("run_select", "run_scan", "make_branch", "commit_document",
                     "write_manifest", "set_status"):
            self.assertFalse(hasattr(status, name), name)

    def test_status_prioritizes_manual_gates_before_safe_local_helpers(self):
        status = load_status()
        written = row("build.written", "written")
        public = row("build.pending")
        sensitive = row("build.sensitive", sensitivity="restricted")
        refused = row("build.refused", "failed", extra={"status": "refused",
                                                          "blockers": ["owner needed"]})
        verified = row("build.verified", "verified")

        cases = [
            (manifest([written], tripwires={"firing": [{"id": "operate.oncall"}]}),
             "tripwire:operate.oncall", "manual-gated"),
            (manifest([written], assumptions=[{"answer": "q2_operator",
                                               "counterfactual": "Confirm deployment.",
                                               "becomes_required": 1}]),
             "assumption:q2_operator", "manual-gated"),
            (manifest([written, refused]), "refusal:build.refused", "manual-gated"),
            (manifest([written, sensitive]), "sensitive:build.sensitive", "manual-gated"),
            (manifest([written]), "verify:build.written", "local-helper"),
            (manifest([public]), "packet:build.pending", "agent-ready"),
            (manifest([verified]), "check", "read-only"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "docs" / "build").mkdir(parents=True)
            (repo / "docs" / "build" / "written.md").write_text("content\n",
                                                                   encoding="utf-8")
            for payload, expected_id, expected_lane in cases:
                action = status.select_next_action(str(repo), payload)
                self.assertEqual(action["id"], expected_id)
                self.assertEqual(action["lane"], expected_lane)

    def test_status_text_and_json_are_stable_and_expose_all_lanes(self):
        repo = self.make_repo(manifest([row("build.pending")]))

        json_first = self.run_status(repo)
        json_second = self.run_status(repo)
        text_first = self.run_status(repo, json_output=False)
        text_second = self.run_status(repo, json_output=False)

        self.assertEqual(json_first.returncode, 0, json_first.stderr)
        self.assertEqual(text_first.returncode, 0, text_first.stderr)
        self.assertEqual(json_first.stdout, json_second.stdout)
        self.assertEqual(text_first.stdout, text_second.stdout)
        self.assertIn("one next action", text_first.stdout.lower())
        self.assertIn("agent-ready", text_first.stdout)

    def test_status_rejects_invalid_or_unsafe_manifest_with_exit_two(self):
        invalid = self.make_repo()
        control = invalid / ".docdna" / "manifest.json"
        control.parent.mkdir()
        control.write_text("{not json", encoding="utf-8")
        invalid_process = self.run_status(invalid)

        self.assertEqual(invalid_process.returncode, 2)
        self.assertIn("docdna_status:", invalid_process.stderr)

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            unsafe = base / "repo"
            (unsafe / ".docdna").mkdir(parents=True)
            outside = base / "outside.json"
            outside.write_text(json.dumps(manifest()), encoding="utf-8")
            os.symlink(str(outside), str(unsafe / ".docdna" / "manifest.json"))
            before = outside.read_bytes()

            unsafe_process = self.run_status(unsafe)

            self.assertEqual(unsafe_process.returncode, 2)
            self.assertEqual(outside.read_bytes(), before)

        ambiguous = self.make_repo(manifest([row("build.unsafe", extra={
            "path": "docs/../outside.md",
        })]))
        ambiguous_process = self.run_status(ambiguous)

        self.assertEqual(ambiguous_process.returncode, 2)
        self.assertIn("repository", ambiguous_process.stderr)

    def test_status_accepts_catalog_directory_paths_without_losing_directory_intent(self):
        status = load_status()
        rows = [
            row("decide.adr", extra={"stage": "decide", "path": "docs/adr/"}),
            row("decide.design-proposal", extra={
                "stage": "decide",
                "path": "docs/decide/proposals/",
            }),
        ]
        repo = self.make_repo(manifest(rows))
        before = snapshot(repo)

        process = self.run_status(repo)

        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads(process.stdout)
        self.assertEqual(list(report).count("next_action"), 1)
        self.assertNotIn("next_actions", report)
        self.assertEqual(status.repository_relative("docs/adr/"), "docs/adr/")
        self.assertEqual(status.repository_relative("docs/decide/proposals/"),
                         "docs/decide/proposals/")
        self.assertEqual(snapshot(repo), before)

    def test_status_commands_expose_argv_and_quote_every_hostile_argument(self):
        repo = self.make_repo(repo_name="repo with spaces $(not-executed)")

        process = self.run_status(repo)

        self.assertEqual(process.returncode, 0, process.stderr)
        action_row = json.loads(process.stdout)["next_action"]
        self.assertIsInstance(action_row["argv"], list)
        self.assertEqual(action_row["argv"][-1], str(repo))
        self.assertEqual(action_row["command"],
                         " ".join(shlex.quote(value) for value in action_row["argv"]))
        self.assertFalse((repo.parent / "not-executed").exists())

    def test_status_rejects_malformed_consumed_fields_without_a_traceback(self):
        invalid_rows = [
            row("build.bad", extra={"blockers": "owner needed"}),
            row("build.bad", extra={"blockers": [4]}),
            row("build.bad", extra={"status": ["refused"]}),
            row("build.bad", extra={"sensitivity": ["public"]}),
        ]
        payloads = [manifest([bad]) for bad in invalid_rows]
        payloads += [
            manifest([], assumptions=[{"answer": "q1", "counterfactual": ["bad"],
                                       "becomes_required": 4}]),
            manifest([], assumptions=[{"answer": "q1", "counterfactual": "text",
                                       "becomes_required": "4"}]),
            manifest([], open_questions=[{"answer": 4, "prompt": "Question?",
                                          "becomes_required": 1}]),
            manifest([], open_questions=[{"answer": "q1", "prompt": 4,
                                          "becomes_required": 1}]),
            manifest([], open_questions=[{"answer": "q1", "prompt": "Question?",
                                          "becomes_required": True}]),
            manifest([], tripwires={"firing": [{"id": 4}]}),
        ]

        for index, payload in enumerate(payloads):
            with self.subTest(index=index):
                repo = self.make_repo(payload)
                process = self.run_status(repo)
                self.assertEqual(process.returncode, 2, process.stdout)
                self.assertIn("docdna_status:", process.stderr)
                self.assertNotIn("Traceback", process.stderr)

    def test_status_rejects_nul_and_control_characters_before_building_argv(self):
        for character in ("\x00", "\x01", "\n", "\x7f", "\x85"):
            with self.subTest(codepoint=ord(character)):
                payload = manifest([row("build.control", extra={
                    "path": "docs/build/bad%sname.md" % character,
                })])
                repo = self.make_repo(payload)
                before = snapshot(repo)

                process = self.run_status(repo)

                self.assertEqual(process.returncode, 2, process.stdout)
                self.assertIn("docdna_status:", process.stderr)
                self.assertNotIn("Traceback", process.stderr)
                if character != "\n":
                    self.assertNotIn(character, process.stderr)
                self.assertEqual(snapshot(repo), before)

    def test_status_rejects_controls_in_document_ids_before_building_argv(self):
        for character in ("\x00", "\x01", "\x7f", "\x85"):
            with self.subTest(codepoint=ord(character)):
                payload = manifest([row("build.bad%sid" % character, extra={
                    "path": "docs/build/safe.md",
                })])
                repo = self.make_repo(payload)
                before = snapshot(repo)

                process = self.run_status(repo)

                self.assertEqual(process.returncode, 2, process.stdout)
                self.assertIn("docdna_status:", process.stderr)
                self.assertNotIn("Traceback", process.stderr)
                self.assertNotIn(character, process.stderr)
                self.assertEqual(snapshot(repo), before)

    def test_status_reproduces_verdict_and_declared_impact_priority(self):
        status = load_status()
        optional = row("build.optional", extra={"verdict": "optional"})
        required_first = row("build.z-required", extra={"verdict": "required"})
        required_second = row("build.a-required", extra={"verdict": "required"})
        recommended = row("build.recommended", extra={"verdict": "recommended"})
        documents = manifest([optional, required_first, required_second, recommended])

        document_action = status.select_next_action("/tmp", documents)

        self.assertEqual(document_action["id"], "packet:build.z-required")

        questions = manifest([], open_questions=[
            {"answer": "q-low", "prompt": "Low?", "becomes_required": 1},
            {"answer": "q-high", "prompt": "High?", "becomes_required": 9},
        ])
        self.assertEqual(status.select_next_action("/tmp", questions)["id"],
                         "question:q-high")

        assumptions = manifest([], assumptions=[
            {"answer": "q-low", "counterfactual": "Low.", "becomes_required": 1},
            {"answer": "q-tie-first", "counterfactual": "First.", "becomes_required": 9},
            {"answer": "q-tie-second", "counterfactual": "Second.", "becomes_required": 9},
        ])
        self.assertEqual(status.select_next_action("/tmp", assumptions)["id"],
                         "assumption:q-tie-first")


if __name__ == "__main__":
    unittest.main()
