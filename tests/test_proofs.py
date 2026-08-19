"""P-MUST-02: product claims resolve to inspectable evidence and replayable proof."""

import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "skill" / "catalog" / "proofs.json"
PROOF_SCRIPT = ROOT / "skill" / "scripts" / "docdna_proof.py"
WORKFLOWS = ROOT / "proof" / "replay" / "golden-workflows.json"
EXPECTED_JSON = ROOT / "proof" / "replay" / "expected-proof-output.json"
EXPECTED_TEXT = ROOT / "proof" / "replay" / "expected-proof-output.txt"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
INSTALLER = ROOT / "install.sh"
CONTROL_LIMIT = 1024 * 1024

EVIDENCE_LEVELS = (
    "shipped",
    "unit-tested",
    "install-tested",
    "artifact-proven",
    "replay-tested",
    "measured",
    "adjudicated",
    "host-capture-ready",
    "host-captured",
    "external-tool-dependent",
)
CORE_MODES = ("survey", "backfill", "check", "runtime")


def load_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_proof():
    spec = importlib.util.spec_from_file_location("docdna_proof_contract", str(PROOF_SCRIPT))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def proof_cli(*args):
    return subprocess.run([sys.executable, str(PROOF_SCRIPT)] + list(args), cwd=str(ROOT),
                          text=True, capture_output=True)


def clone(value):
    return json.loads(json.dumps(value))


class ProofRegistryTests(unittest.TestCase):
    def cli_with(self, registry=None, workflows=None):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            registry_path = directory / "proofs.json"
            workflow_path = directory / "workflows.json"
            registry_path.write_text(json.dumps(registry or load_json(REGISTRY)), encoding="utf-8")
            workflow_path.write_text(json.dumps(workflows or load_json(WORKFLOWS)),
                                     encoding="utf-8")
            return proof_cli("--json", "--registry", str(registry_path),
                             "--workflows", str(workflow_path), "--root", str(ROOT))

    def assert_invalid(self, process, fragment):
        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, "")
        self.assertIn(fragment, process.stderr)
        self.assertNotIn("Traceback", process.stderr)

    def assert_process_gone(self, pid):
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        os.kill(pid, signal.SIGKILL)
        self.fail("replay descendant %d is still running" % pid)

    def test_registry_has_unique_claims_and_closed_evidence_levels(self):
        registry = load_json(REGISTRY)

        self.assertEqual(registry["schema"], 1)
        self.assertEqual(tuple(registry["evidence_levels"]), EVIDENCE_LEVELS)
        self.assertEqual(set(registry["promotion_requirements"]), set(EVIDENCE_LEVELS))
        claim_ids = [claim["id"] for claim in registry["claims"]]
        self.assertEqual(claim_ids, sorted(claim_ids))
        self.assertEqual(len(claim_ids), len(set(claim_ids)))
        self.assertTrue(set(claim["evidence_level"] for claim in registry["claims"])
                        <= set(EVIDENCE_LEVELS))

        report = load_proof().validate_registry(registry, str(ROOT), load_json(WORKFLOWS))
        self.assertEqual(report["errors"], [])
        rendered = load_proof().render_report(registry, [])
        self.assertEqual([level["id"] for level in rendered["evidence_levels"]],
                         list(EVIDENCE_LEVELS))

    def test_every_claim_evidence_path_exists(self):
        registry = load_json(REGISTRY)
        requirements = registry["promotion_requirements"]

        for claim in registry["claims"]:
            evidence = claim["evidence"]
            kinds = set(item["kind"] for item in evidence)
            required = set(requirements[claim["evidence_level"]]["requires_evidence"])
            self.assertTrue(required <= kinds, claim["id"])
            for item in evidence:
                path = ROOT / item["path"]
                self.assertTrue(path.exists(), "%s names missing %s" % (claim["id"], path))

        broken = json.loads(json.dumps(registry))
        broken["claims"][0]["evidence"] = [
            {"kind": "implementation", "path": "proof/does-not-exist.json"}
        ]
        report = load_proof().validate_registry(broken, str(ROOT), load_json(WORKFLOWS))
        self.assertTrue(any("does not exist" in error for error in report["errors"]))

    def test_measurement_and_adjudication_claims_name_corpus_and_boundary(self):
        registry = load_json(REGISTRY)
        selected = [claim for claim in registry["claims"]
                    if claim["evidence_level"] in ("measured", "adjudicated")]

        self.assertEqual(set(claim["evidence_level"] for claim in selected),
                         {"measured", "adjudicated"})
        for claim in selected:
            self.assertTrue(claim["corpus"].strip(), claim["id"])
            self.assertTrue(claim["boundary"].strip(), claim["id"])
            self.assertTrue(claim["limitations"].strip(), claim["id"])

    def test_proof_command_emits_stable_text_and_json(self):
        first_json = proof_cli("--json")
        second_json = proof_cli("--json")

        self.assertEqual(first_json.returncode, 0, first_json.stderr)
        self.assertEqual(first_json.stdout, second_json.stdout)
        payload = json.loads(first_json.stdout)
        self.assertEqual(payload, load_json(EXPECTED_JSON))
        self.assertEqual(first_json.stdout, EXPECTED_JSON.read_text(encoding="utf-8"))
        self.assertEqual(payload["tool"], "docdna_proof")
        self.assertEqual(payload["summary"]["status"], "pass")
        self.assertEqual(payload["summary"]["claims"], len(payload["claims"]))
        self.assertEqual(payload["summary"]["replays_passed"], 4)

        first_text = proof_cli()
        second_text = proof_cli()
        self.assertEqual(first_text.returncode, 0, first_text.stderr)
        self.assertEqual(first_text.stdout, second_text.stdout)
        self.assertEqual(first_text.stdout, EXPECTED_TEXT.read_text(encoding="utf-8"))
        self.assertIn("claim matrix", first_text.stdout)
        self.assertIn("golden replay", first_text.stdout)

        registry = load_json(REGISTRY)
        registry["claims"].append(dict(registry["claims"][0]))
        with tempfile.TemporaryDirectory() as tmp:
            invalid = Path(tmp) / "proofs.json"
            invalid.write_text(json.dumps(registry), encoding="utf-8")
            process = proof_cli("--json", "--registry", str(invalid), "--root", str(ROOT))
        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, "")
        self.assertIn("duplicate claim id", process.stderr)

    def test_malformed_registry_types_exit_2_without_traceback(self):
        malformed = []
        registry = load_json(REGISTRY)

        wrong_schema = clone(registry)
        wrong_schema["schema"] = []
        malformed.append((wrong_schema, "proof registry schema must be 1"))

        float_schema = clone(registry)
        float_schema["schema"] = 1.0
        malformed.append((float_schema, "proof registry schema must be 1"))

        wrong_levels = clone(registry)
        wrong_levels["evidence_levels"] = {"shipped": True}
        malformed.append((wrong_levels, "evidence_levels must match"))

        wrong_requirement = clone(registry)
        wrong_requirement["promotion_requirements"]["shipped"]["requires_evidence"] = {
            "kind": "implementation"
        }
        malformed.append((wrong_requirement, "promotion requirement shipped"))

        wrong_replay_id = clone(registry)
        wrong_replay_id["claims"][0]["replay_id"] = {"id": "golden.backfill"}
        malformed.append((wrong_replay_id, "replay_id must be a string"))

        wrong_evidence = clone(registry)
        wrong_evidence["claims"][0]["evidence"] = {"kind": "replay"}
        malformed.append((wrong_evidence, "needs at least one evidence record"))

        wrong_level = clone(registry)
        wrong_level["claims"][0]["evidence_level"] = {"level": "replay-tested"}
        malformed.append((wrong_level, "invalid evidence_level"))

        wrong_record = clone(registry)
        wrong_record["claims"][0]["evidence"] = [None]
        malformed.append((wrong_record, "evidence 1 must be an object"))

        for candidate, fragment in malformed:
            with self.subTest(fragment=fragment):
                self.assert_invalid(self.cli_with(registry=candidate), fragment)

    def test_malformed_workflow_types_exit_2_without_traceback(self):
        malformed = []
        workflows = load_json(WORKFLOWS)

        float_schema = clone(workflows)
        float_schema["schema"] = 1.0
        malformed.append((float_schema, "golden workflows schema must be 1"))

        wrong_collection = clone(workflows)
        wrong_collection["workflows"] = {"golden.survey": {}}
        malformed.append((wrong_collection, "golden workflows must be a list"))

        wrong_mode = clone(workflows)
        wrong_mode["workflows"][0]["mode"] = {"mode": "survey"}
        malformed.append((wrong_mode, "invalid mode"))

        wrong_command = clone(workflows)
        wrong_command["workflows"][0]["command"] = {"script": "docdna_scan.py"}
        malformed.append((wrong_command, "command must be a non-empty string list"))

        wrong_assertion = clone(workflows)
        wrong_assertion["workflows"][0]["assertions"][0]["length"] = {}
        del wrong_assertion["workflows"][0]["assertions"][0]["equals"]
        malformed.append((wrong_assertion, "length must be a non-negative integer"))

        for candidate, fragment in malformed:
            with self.subTest(fragment=fragment):
                self.assert_invalid(self.cli_with(workflows=candidate), fragment)

    def test_ids_require_a_full_string_match(self):
        registry = load_json(REGISTRY)
        invalid_claim = clone(registry)
        claim = next(row for row in invalid_claim["claims"]
                     if row["id"] == "runtime.proof-command")
        claim["id"] = "runtime.proof-command\n"

        self.assert_invalid(self.cli_with(registry=invalid_claim), "claim 7 has an invalid id")

        workflows = load_json(WORKFLOWS)
        invalid_workflow = clone(workflows)
        invalid_workflow["workflows"][0]["id"] = "golden.survey\n"
        self.assert_invalid(self.cli_with(workflows=invalid_workflow),
                            "workflow 1 has an invalid id")

    def test_undeclared_registry_and_replay_fields_exit_2_without_traceback(self):
        registry = load_json(REGISTRY)
        registry_cases = []

        top_level = clone(registry)
        top_level["future"] = True
        registry_cases.append((top_level, "proof registry has undeclared field future"))

        promotion = clone(registry)
        promotion["promotion_requirements"]["shipped"]["note"] = "extra"
        registry_cases.append((promotion,
                               "promotion requirement shipped has undeclared field note"))

        claim_field = clone(registry)
        claim_field["claims"][0]["display"] = "extra"
        registry_cases.append((claim_field,
                               "claim backfill.boundary-verification has undeclared field display"))

        evidence_field = clone(registry)
        evidence_field["claims"][0]["evidence"][0]["note"] = "extra"
        registry_cases.append((evidence_field,
                               "claim backfill.boundary-verification evidence 1 has undeclared field note"))

        for candidate, fragment in registry_cases:
            with self.subTest(fragment=fragment):
                self.assert_invalid(self.cli_with(registry=candidate), fragment)

        workflows = load_json(WORKFLOWS)
        workflow_cases = []

        replay_top = clone(workflows)
        replay_top["future"] = True
        workflow_cases.append((replay_top, "golden workflows has undeclared field future"))

        replay_row = clone(workflows)
        replay_row["workflows"][0]["shell"] = True
        workflow_cases.append((replay_row,
                               "workflow golden.survey has undeclared field shell"))

        replay_assertion = clone(workflows)
        replay_assertion["workflows"][0]["assertions"][0]["tolerance"] = 1
        workflow_cases.append((replay_assertion,
                               "workflow golden.survey assertion 1 has undeclared field tolerance"))

        for candidate, fragment in workflow_cases:
            with self.subTest(fragment=fragment):
                self.assert_invalid(self.cli_with(workflows=candidate), fragment)

    def test_altered_promotion_mapping_and_missing_promotion_evidence_exit_2(self):
        registry = load_json(REGISTRY)

        altered = clone(registry)
        altered["promotion_requirements"]["shipped"]["requires_evidence"] = ["unit-test"]
        self.assert_invalid(self.cli_with(registry=altered),
                            "promotion requirement shipped must be implementation")

        missing = clone(registry)
        claim = next(row for row in missing["claims"] if row["id"] == "runtime.proof-command")
        claim["evidence"] = [{"kind": "artifact", "path": "proof/runtime/README.md"}]
        self.assert_invalid(self.cli_with(registry=missing),
                            "cannot use shipped without evidence kind implementation")

    def test_invalid_replay_declarations_and_normalized_path_escapes_exit_2(self):
        workflows = load_json(WORKFLOWS)

        unknown_flag = clone(workflows)
        unknown_flag["workflows"][0]["command"].insert(1, "--write")
        self.assert_invalid(self.cli_with(workflows=unknown_flag), "does not allow flag --write")

        escaped = clone(workflows)
        escaped["workflows"][0]["command"][-1] = "proof/../../../tmp"
        self.assert_invalid(self.cli_with(workflows=escaped),
                            "operand proof/../../../tmp must stay inside the project")

        escaped_flag = clone(workflows)
        escaped_flag["workflows"][1]["command"][3] = "proof/../../../tmp"
        self.assert_invalid(self.cli_with(workflows=escaped_flag),
                            "flag --verify path proof/../../../tmp must stay inside")

        invalid_value = clone(workflows)
        invalid_value["workflows"][2]["command"][4] = "major"
        self.assert_invalid(self.cli_with(workflows=invalid_value),
                            "flag --fail-on value must be never")

    def test_replay_mismatch_exits_1_with_stable_failure_report(self):
        workflows = load_json(WORKFLOWS)
        changed = clone(workflows)
        changed["workflows"][0]["assertions"][1]["equals"] = 999

        first = self.cli_with(workflows=changed)
        second = self.cli_with(workflows=changed)
        self.assertEqual(first.returncode, 1)
        self.assertEqual(first.stderr, "")
        self.assertEqual(first.stdout, second.stdout)
        payload = json.loads(first.stdout)
        self.assertEqual(payload["summary"]["status"], "fail")
        self.assertEqual(payload["summary"]["replays_passed"], 3)
        self.assertEqual(payload["replay"][0]["errors"],
                         ["inventory.counts.total did not equal the saved outcome"])

    def test_ci_compares_stable_proof_artifacts_in_every_python_job(self):
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("python skill/scripts/docdna_proof.py --json", workflow)
        self.assertIn("proof/replay/expected-proof-output.json", workflow)
        self.assertIn("proof/replay/expected-proof-output.txt", workflow)

    def test_control_json_rejects_oversize_fifo_and_symlink_without_hanging(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            oversized = directory / "oversized.json"
            oversized.write_bytes(b"{" + b" " * (CONTROL_LIMIT + 1) + b"}")
            oversized_result = proof_cli("--json", "--registry", str(oversized),
                                         "--workflows", str(WORKFLOWS),
                                         "--root", str(ROOT))
            self.assert_invalid(oversized_result, "exceeds 1048576 bytes")

            linked = directory / "linked.json"
            linked.symlink_to(REGISTRY)
            linked_result = proof_cli("--json", "--registry", str(linked),
                                      "--workflows", str(WORKFLOWS), "--root", str(ROOT))
            self.assert_invalid(linked_result, "refuses symbolic links")

            fifo = directory / "proofs.fifo"
            os.mkfifo(str(fifo))
            command = [sys.executable, str(PROOF_SCRIPT), "--json", "--registry", str(fifo),
                       "--workflows", str(WORKFLOWS), "--root", str(ROOT)]
            fifo_result = subprocess.run(command, cwd=str(ROOT), text=True,
                                         capture_output=True, timeout=2)
            self.assert_invalid(fifo_result, "must be a regular file")

    def test_control_json_rejects_a_file_changed_during_read(self):
        proof = load_proof()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "control.json"
            path.write_text('{"schema": 1}\n', encoding="utf-8")
            initial = os.stat(str(path))
            changed = mock.Mock(st_mode=initial.st_mode, st_size=initial.st_size,
                                st_dev=initial.st_dev, st_ino=initial.st_ino,
                                st_mtime_ns=initial.st_mtime_ns + 1)
            with mock.patch.object(proof.os, "fstat", side_effect=[initial, changed]):
                with self.assertRaisesRegex(ValueError, "changed while reading"):
                    proof.read_json(str(path))

    def test_subprocess_output_and_decoding_are_bounded(self):
        proof = load_proof()
        noisy = proof.run_bounded(
            [sys.executable, "-c",
             "import sys; sys.stdout.write('x' * 4096); sys.stderr.write('useful child error')"],
            str(ROOT), timeout_seconds=2, output_limit=1024)

        self.assertTrue(noisy["output_exceeded"])
        self.assertLessEqual(len(noisy["stdout"].encode("utf-8")), 1024)
        self.assertIn("useful child error", noisy["stderr"])
        self.assertIn("exceeded 1024 bytes", noisy["error"])

        undecodable = proof.run_bounded(
            [sys.executable, "-c", "import os; os.write(1, b'\\xff')"],
            str(ROOT), timeout_seconds=2, output_limit=1024)
        self.assertIn("stdout was not valid UTF-8", undecodable["error"])

        missing = proof.run_bounded(["/path/that/does/not/exist"], str(ROOT),
                                    timeout_seconds=2, output_limit=1024)
        self.assertIn("could not start", missing["error"])

    def test_subprocess_timeout_terminates_the_process_group(self):
        proof = load_proof()
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "child.pid"
            code = ("import subprocess,sys,time; "
                    "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
                    "open(sys.argv[1],'w').write(str(child.pid)); time.sleep(30)")
            result = proof.run_bounded([sys.executable, "-c", code, str(pid_path)], str(ROOT),
                                       timeout_seconds=0.25, output_limit=1024)

            self.assertTrue(result["timed_out"])
            self.assertIn("timed out", result["error"])
            child_pid = int(pid_path.read_text(encoding="utf-8"))
            for _ in range(20):
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.05)
            else:
                self.fail("timed-out replay child %d is still running" % child_pid)

    def test_timeout_escalates_after_leader_exit_and_closed_pipes(self):
        proof = load_proof()
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "descendant.pid"
            descendant = ("import os,signal,sys,time; "
                          "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                          "os.close(1); os.close(2); "
                          "open(sys.argv[1],'w').write(str(os.getpid())); time.sleep(30)")
            leader = ("import subprocess,sys,time; "
                      "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]]); "
                      "time.sleep(30)")
            result = proof.run_bounded(
                [sys.executable, "-c", leader, descendant, str(pid_path)], str(ROOT),
                timeout_seconds=0.5, output_limit=1024)

            self.assertTrue(result["timed_out"])
            descendant_pid = int(pid_path.read_text(encoding="utf-8"))
            self.assert_process_gone(descendant_pid)

    def test_output_overflow_escalates_after_leader_exit_and_closed_pipes(self):
        proof = load_proof()
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "descendant.pid"
            descendant = ("import os,signal,sys,time; "
                          "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                          "os.close(1); os.close(2); "
                          "open(sys.argv[1],'w').write(str(os.getpid())); time.sleep(30)")
            leader = ("import os,subprocess,sys,time; "
                      "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]]); "
                      "[(time.sleep(.01)) for _ in range(100) if not os.path.exists(sys.argv[2])]; "
                      "sys.stdout.write('x' * 4096); sys.stdout.flush(); time.sleep(30)")
            result = proof.run_bounded(
                [sys.executable, "-c", leader, descendant, str(pid_path)], str(ROOT),
                timeout_seconds=2, output_limit=1024)

            self.assertTrue(result["output_exceeded"])
            descendant_pid = int(pid_path.read_text(encoding="utf-8"))
            self.assert_process_gone(descendant_pid)

    def test_proof_command_validates_an_isolated_installed_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "skills"
            environment = dict(os.environ, CLAUDE_SKILLS_DIR=str(destination))
            installed = subprocess.run([str(INSTALLER), "claude"], cwd=str(ROOT),
                                       env=environment, text=True, capture_output=True)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            installed_root = destination / "docdna"
            before = sorted(str(path.relative_to(installed_root))
                            for path in installed_root.rglob("*") if path.is_file())

            process = subprocess.run(
                [sys.executable, str(installed_root / "scripts" / "docdna_proof.py"), "--json"],
                cwd=str(tmp), text=True, capture_output=True)
            after = sorted(str(path.relative_to(installed_root))
                           for path in installed_root.rglob("*") if path.is_file())

        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(before, after)
        payload = json.loads(process.stdout)
        self.assertEqual(payload["validation"]["mode"], "installed-registry")
        self.assertEqual(payload["summary"]["replays"], 0)
        self.assertIn("checkout-only evidence paths", payload["validation"]["boundary"])
        host_claim = next(row for row in payload["claims"]
                          if row["id"] == "runtime.host-capture-procedure")
        self.assertIn("source checkout", host_claim["boundary"])

    def test_each_core_mode_has_an_inspectable_bundle(self):
        registry = load_json(REGISTRY)

        self.assertEqual(set(claim["mode"] for claim in registry["claims"]), set(CORE_MODES))
        for mode in CORE_MODES:
            bundle = ROOT / "proof" / mode / "README.md"
            text = bundle.read_text(encoding="utf-8")
            self.assertIn("Raw evidence", text)
            self.assertIn("Reproduce", text)
            self.assertIn("Non-claims", text)
            self.assertIn("python3", text)

    def test_golden_workflows_replay_expected_mode_results(self):
        workflows = load_json(WORKFLOWS)
        proof = load_proof()
        results = proof.replay_workflows(workflows, str(ROOT))

        self.assertEqual([workflow["mode"] for workflow in workflows["workflows"]],
                         list(CORE_MODES))
        self.assertEqual([result["status"] for result in results], ["pass"] * 4)
        self.assertEqual([result["id"] for result in results],
                         [workflow["id"] for workflow in workflows["workflows"]])


if __name__ == "__main__":
    unittest.main()
