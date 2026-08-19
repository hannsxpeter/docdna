"""P-MUST-03: one registry drives a deterministic, read-only runtime doctor."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skill"
REGISTRY = SKILL_ROOT / "catalog" / "runtimes.json"
RUNTIME_SCRIPT = SKILL_ROOT / "scripts" / "docdna_runtime.py"
DOCTOR_SCRIPT = SKILL_ROOT / "scripts" / "docdna_doctor.py"
CHECK_IDS = ["runtime-registry", "python-compatibility", "runtime-members", "proof-registry"]


def load_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_runtime():
    spec = importlib.util.spec_from_file_location("docdna_runtime_contract", str(RUNTIME_SCRIPT))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_doctor():
    spec = importlib.util.spec_from_file_location("docdna_doctor_contract", str(DOCTOR_SCRIPT))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(root):
    result = {}
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            result[relative] = ("symlink", os.readlink(str(path)))
        elif path.is_file():
            result[relative] = ("file", path.read_bytes())
        elif path.is_dir():
            result[relative] = ("dir", None)
    return result


def copy_skill(destination):
    shutil.copytree(str(SKILL_ROOT), str(destination),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def copy_checkout(destination):
    destination.mkdir()
    (destination / "install.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    copy_skill(destination / "skill")
    shutil.copytree(str(ROOT / "proof"), str(destination / "proof"))
    evidence = (
        "tests/test_regression.py",
        "tests/test_drift.py",
        "tests/test_proofs.py",
        "tests/fixtures/documented_repo",
        "tests/fixtures/internal_service",
    )
    for relative in evidence:
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(str(source), str(target))
        else:
            shutil.copy2(str(source), str(target))


def doctor_cli(script, *args, cwd=None):
    return subprocess.run([sys.executable, str(script)] + list(args), cwd=cwd,
                          text=True, capture_output=True)


class RuntimeRegistryTests(unittest.TestCase):
    def test_runtime_registry_names_every_shipped_command_once(self):
        registry = load_json(REGISTRY)

        command_paths = [row["path"] for row in registry["runtime_members"]
                         if row["kind"] == "command"]
        shipped_commands = sorted(
            "scripts/" + path.name
            for path in (SKILL_ROOT / "scripts").glob("docdna_*.py")
            if 'if __name__ == "__main__":' in path.read_text(encoding="utf-8")
        )

        self.assertEqual(registry["schema"], 1)
        self.assertEqual(registry["minimum_python"], [3, 8])
        self.assertEqual(command_paths, sorted(command_paths))
        self.assertEqual(command_paths, shipped_commands)
        self.assertEqual(len(command_paths), len(set(command_paths)))

        member_paths = [row["path"] for row in registry["runtime_members"]]
        shipped_members = sorted("scripts/" + path.name
                                 for path in (SKILL_ROOT / "scripts").glob("docdna_*.py"))
        self.assertEqual(member_paths, shipped_members)
        self.assertEqual(len(member_paths), len(set(member_paths)))

        inventories = (
            ("registries", "catalog", "*.json"),
            ("templates", "templates", "*.md"),
            ("references", "references", "*.md"),
        )
        for section, directory, pattern in inventories:
            registered = [row["path"] for row in registry[section]]
            shipped = sorted(str(path.relative_to(SKILL_ROOT))
                             for path in (SKILL_ROOT / directory).rglob(pattern))
            self.assertEqual(registered, shipped, section)

        install_targets = [host["install"]["selector"] for host in registry["host_targets"]
                           if host["install"]["support"] == "supported"]
        self.assertEqual(sorted(install_targets), ["claude", "codex", "cursor", "windsurf"])

        wiring_ids = [surface["id"] for surface in registry["wiring_surfaces"]]
        self.assertEqual(wiring_ids,
                         ["agents", "cascade", "claude", "copilot", "cursor", "gemini"])
        for host in registry["host_targets"]:
            self.assertIn(host["support_level"], ("install-and-wiring", "wiring-only"))
            self.assertEqual(host["host_parity"]["status"], "not-verified")
            self.assertIn("host parity", host["host_parity"]["boundary"])

    def test_runtime_loader_is_bounded_strict_and_reusable(self):
        runtime = load_runtime()
        registry = runtime.load_registry(str(SKILL_ROOT))

        self.assertEqual(registry, load_json(REGISTRY))
        self.assertEqual(runtime.command_paths(registry), [
            row["path"] for row in registry["runtime_members"] if row["kind"] == "command"
        ])
        self.assertEqual(runtime.install_targets(registry),
                         ["claude", "codex", "cursor", "windsurf"])
        self.assertEqual(runtime.wiring_target_ids(registry),
                         ["agents", "cascade", "claude", "copilot", "cursor", "gemini"])
        self.assertNotIn(".count(", RUNTIME_SCRIPT.read_text(encoding="utf-8"))

        duplicate = json.loads(json.dumps(registry))
        duplicate["runtime_members"].append(dict(duplicate["runtime_members"][0]))
        with self.assertRaisesRegex(runtime.RuntimeRegistryError, "duplicate runtime member"):
            runtime.validate_registry(duplicate)

        extra = json.loads(json.dumps(registry))
        extra["future"] = True
        with self.assertRaisesRegex(runtime.RuntimeRegistryError, "undeclared field future"):
            runtime.validate_registry(extra)

        overclaim = json.loads(json.dumps(registry))
        overclaim["host_targets"][0]["host_parity"]["status"] = "verified"
        with self.assertRaisesRegex(runtime.RuntimeRegistryError, "host parity status"):
            runtime.validate_registry(overclaim)

    def test_runtime_loader_rejects_unsafe_and_oversized_registry_input(self):
        runtime = load_runtime()
        registry = load_json(REGISTRY)

        unsafe_member = json.loads(json.dumps(registry))
        unsafe_member["runtime_members"][0]["path"] = "../outside.py"
        with self.assertRaisesRegex(runtime.RuntimeRegistryError, "safe relative path"):
            runtime.validate_registry(unsafe_member)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "catalog").mkdir()
            oversized = root / "catalog" / "runtimes.json"
            with oversized.open("wb") as handle:
                handle.truncate(runtime.MAX_REGISTRY_BYTES + 1)
            with self.assertRaisesRegex(runtime.RuntimeRegistryError, "exceeds"):
                runtime.load_registry(str(root))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "catalog").mkdir()
            outside = root / "outside.json"
            outside.write_text(json.dumps(registry), encoding="utf-8")
            os.symlink(str(outside), str(root / "catalog" / "runtimes.json"))
            with self.assertRaisesRegex(runtime.RuntimeRegistryError, "unsafe"):
                runtime.load_registry(str(root))


class DoctorHealthyTests(unittest.TestCase):
    def assert_healthy(self, process, validation_mode):
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        payload = json.loads(process.stdout)
        self.assertEqual(payload["schema"], 1)
        self.assertEqual(payload["tool"], "docdna_doctor")
        self.assertEqual(payload["verdict"], "pass")
        self.assertEqual([row["id"] for row in payload["checks"]], CHECK_IDS)
        self.assertEqual([row["status"] for row in payload["checks"]], ["pass"] * 4)
        self.assertEqual(payload["summary"],
                         {"error": 0, "fail": 0, "pass": 4, "total": 4})
        proof = next(row for row in payload["checks"] if row["id"] == "proof-registry")
        self.assertEqual(proof["details"]["validation_mode"], validation_mode)
        return payload

    def test_doctor_passes_from_checkout_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / "checkout"
            copy_checkout(checkout)
            skill_root = checkout / "skill"
            before = snapshot(checkout)

            process = doctor_cli(skill_root / "scripts" / "docdna_doctor.py", "--json",
                                 "--source-checkout", cwd=str(Path(tmp)))
            after = snapshot(checkout)

        self.assertEqual(before, after)
        payload = self.assert_healthy(process, "source-checkout")
        proof = payload["checks"][-1]
        self.assertEqual(proof["details"]["workflows"],
                         "proof/replay/golden-workflows.json")
        self.assertIs(proof["details"]["evidence_paths_validated"], True)
        self.assertIs(proof["details"]["replay_ids_validated"], True)
        self.assertIn("without executing", proof["details"]["boundary"])

    def test_doctor_passes_from_isolated_installed_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed_root = Path(tmp) / "consumer" / "docdna"
            installed_root.parent.mkdir()
            copy_skill(installed_root)
            before = snapshot(installed_root)

            process = doctor_cli(installed_root / "scripts" / "docdna_doctor.py", "--json",
                                 cwd=str(Path(tmp)))
            after = snapshot(installed_root)

        self.assertEqual(before, after)
        payload = self.assert_healthy(process, "installed-registry")
        proof = payload["checks"][-1]
        self.assertNotIn("workflows", proof["details"])
        self.assertIs(proof["details"]["evidence_paths_validated"], False)
        self.assertIs(proof["details"]["replay_ids_validated"], False)
        self.assertIn("checkout-only evidence", proof["details"]["boundary"])

    def test_default_mode_does_not_infer_checkout_from_directory_names_or_install_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "consumer"
            parent.mkdir()
            (parent / "install.sh").write_text("unrelated\n", encoding="utf-8")
            installed_root = parent / "skill"
            copy_skill(installed_root)

            process = doctor_cli(installed_root / "scripts" / "docdna_doctor.py", "--json",
                                 cwd=str(Path(tmp)))

        payload = self.assert_healthy(process, "installed-registry")
        self.assertNotIn("workflows", payload["checks"][-1]["details"])

    def test_doctor_emits_stable_json_and_text_verdicts(self):
        first_json = doctor_cli(DOCTOR_SCRIPT, "--json", cwd=str(ROOT))
        second_json = doctor_cli(DOCTOR_SCRIPT, "--json", cwd=str(ROOT.parent))
        first_text = doctor_cli(DOCTOR_SCRIPT, cwd=str(ROOT))
        second_text = doctor_cli(DOCTOR_SCRIPT, cwd=str(ROOT.parent))

        self.assertEqual(first_json.returncode, 0, first_json.stderr)
        self.assertEqual(first_json.stdout, second_json.stdout)
        self.assertEqual(first_text.returncode, 0, first_text.stderr)
        self.assertEqual(first_text.stdout, second_text.stdout)
        payload = json.loads(first_json.stdout)
        self.assertIs(payload["read_only"], True)
        self.assertEqual(first_text.stdout, (
            "docdna doctor: PASS\n"
            "checks: 4 pass, 0 fail, 0 error\n"
            "PASS runtime-registry: runtime registry schema is valid\n"
            "PASS python-compatibility: Python meets the declared 3.8 minimum\n"
            "PASS runtime-members: %d registered runtime resources are present and readable\n"
            "PASS proof-registry: proof registry is valid in installed-registry mode\n"
        ) % payload["checks"][2]["details"]["registered"])
        self.assertNotIn(str(ROOT), first_json.stdout + first_text.stdout)

        source_json = doctor_cli(DOCTOR_SCRIPT, "--json", "--source-checkout", cwd=str(ROOT))
        source = json.loads(source_json.stdout)
        self.assertEqual(source_json.returncode, 0, source_json.stderr)
        self.assertEqual(source["checks"][-1]["details"]["validation_mode"],
                         "source-checkout")


class DoctorFailureTests(unittest.TestCase):
    def test_doctor_fails_when_a_registered_member_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed_root = Path(tmp) / "docdna"
            copy_skill(installed_root)
            missing = "scripts/docdna_llms.py"
            (installed_root / missing).unlink()
            before = snapshot(installed_root)

            process = doctor_cli(installed_root / "scripts" / "docdna_doctor.py", "--json",
                                 cwd=str(Path(tmp)))
            after = snapshot(installed_root)

        self.assertEqual(before, after)
        self.assertEqual(process.returncode, 1, process.stderr)
        self.assertEqual(process.stderr, "")
        payload = json.loads(process.stdout)
        self.assertEqual(payload["verdict"], "fail")
        failed = next(row for row in payload["checks"] if row["id"] == "runtime-members")
        self.assertEqual(failed["status"], "fail")
        self.assertEqual(failed["details"]["failures"],
                         [{"path": missing, "reason": "missing", "status": "fail"}])
        self.assertIn("python3 scripts/docdna_doctor.py --json", failed["remediation"])
        self.assertNotIn("Traceback", process.stdout + process.stderr)

    def test_doctor_reports_a_missing_bootstrap_member_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed_root = Path(tmp) / "docdna"
            copy_skill(installed_root)
            (installed_root / "scripts" / "docdna_runtime.py").unlink()

            process = doctor_cli(installed_root / "scripts" / "docdna_doctor.py", "--json",
                                 cwd=str(Path(tmp)))

        self.assertEqual(process.returncode, 1)
        self.assertEqual(process.stdout, "")
        self.assertIn("missing bootstrap runtime member scripts/docdna_runtime.py",
                      process.stderr)
        self.assertIn("Reinstall DocDNA", process.stderr)
        self.assertNotIn("Traceback", process.stderr)

    def test_doctor_rejects_invalid_runtime_or_proof_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed_root = Path(tmp) / "docdna"
            copy_skill(installed_root)
            runtime_registry = load_json(installed_root / "catalog" / "runtimes.json")
            runtime_registry["future"] = True
            (installed_root / "catalog" / "runtimes.json").write_text(
                json.dumps(runtime_registry), encoding="utf-8")

            invalid_runtime = doctor_cli(installed_root / "scripts" / "docdna_doctor.py",
                                         "--json", cwd=str(Path(tmp)))

        self.assertEqual(invalid_runtime.returncode, 2)
        self.assertEqual(invalid_runtime.stdout, "")
        self.assertIn("undeclared field future", invalid_runtime.stderr)
        self.assertIn("remediation:", invalid_runtime.stderr)
        self.assertIn("python3 scripts/docdna_doctor.py --json", invalid_runtime.stderr)
        self.assertNotIn("Traceback", invalid_runtime.stderr)

        with tempfile.TemporaryDirectory() as tmp:
            installed_root = Path(tmp) / "docdna"
            copy_skill(installed_root)
            (installed_root / "catalog" / "proofs.json").write_text("{", encoding="utf-8")
            before = snapshot(installed_root)

            invalid_proof = doctor_cli(installed_root / "scripts" / "docdna_doctor.py", "--json",
                                       cwd=str(Path(tmp)))
            after = snapshot(installed_root)

        self.assertEqual(before, after)
        self.assertEqual(invalid_proof.returncode, 2)
        self.assertEqual(invalid_proof.stderr, "")
        payload = json.loads(invalid_proof.stdout)
        self.assertEqual([row["id"] for row in payload["checks"]], CHECK_IDS)
        proof = payload["checks"][-1]
        self.assertEqual(proof["status"], "error")
        self.assertEqual(proof["details"]["validation_mode"], "installed-registry")
        self.assertTrue(proof["remediation"])
        self.assertNotIn("Traceback", invalid_proof.stdout)

    def test_doctor_rejects_unsafe_oversized_and_malformed_members_without_writing(self):
        cases = ("unsafe", "oversized", "malformed")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                installed_root = Path(tmp) / "docdna"
                copy_skill(installed_root)
                member = installed_root / "scripts" / "docdna_llms.py"
                outside = Path(tmp) / "outside.py"
                if case == "unsafe":
                    member.unlink()
                    outside.write_text("outside_marker = True\n", encoding="utf-8")
                    os.symlink(str(outside), str(member))
                    expected_code = 2
                    expected_status = "error"
                elif case == "oversized":
                    with member.open("wb") as handle:
                        handle.truncate(5 * 1024 * 1024 + 1)
                    expected_code = 2
                    expected_status = "error"
                else:
                    member.write_text("def malformed(\n", encoding="utf-8")
                    expected_code = 1
                    expected_status = "fail"
                before = snapshot(Path(tmp))

                process = doctor_cli(installed_root / "scripts" / "docdna_doctor.py", "--json",
                                     cwd=str(Path(tmp)))
                after = snapshot(Path(tmp))

            self.assertEqual(before, after)
            self.assertEqual(process.returncode, expected_code, process.stderr)
            self.assertEqual(process.stderr, "")
            payload = json.loads(process.stdout)
            self.assertEqual(payload["verdict"], expected_status)
            check = next(row for row in payload["checks"] if row["id"] == "runtime-members")
            self.assertEqual(check["status"], expected_status)
            self.assertEqual(check["details"]["failures"][0]["path"],
                             "scripts/docdna_llms.py")
            self.assertEqual(check["details"]["failures"][0]["status"], expected_status)
            self.assertIn("python3 scripts/docdna_doctor.py --json", check["remediation"])
            self.assertNotIn(str(Path(tmp)), process.stdout)

    def test_doctor_rejects_unsafe_oversized_and_malformed_runtime_registries(self):
        for case in ("unsafe", "oversized", "malformed"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                installed_root = Path(tmp) / "docdna"
                copy_skill(installed_root)
                registry = installed_root / "catalog" / "runtimes.json"
                if case == "unsafe":
                    process = doctor_cli(installed_root / "scripts" / "docdna_doctor.py",
                                         "--json", "--registry", "../outside.json",
                                         cwd=str(Path(tmp)))
                else:
                    if case == "oversized":
                        with registry.open("wb") as handle:
                            handle.truncate(1024 * 1024 + 1)
                    else:
                        registry.write_text("{", encoding="utf-8")
                    process = doctor_cli(installed_root / "scripts" / "docdna_doctor.py",
                                         "--json", cwd=str(Path(tmp)))

            self.assertEqual(process.returncode, 2)
            self.assertEqual(process.stdout, "")
            self.assertTrue(process.stderr.startswith("docdna_doctor: "))
            self.assertIn("remediation:", process.stderr)
            self.assertIn("python3 scripts/docdna_doctor.py --json", process.stderr)
            self.assertNotIn("Traceback", process.stderr)

    def test_checkout_doctor_rejects_missing_or_corrupt_proof_fixtures(self):
        cases = {
            "missing-workflows": ("fail", 1),
            "corrupt-workflows": ("error", 2),
            "missing-evidence": ("fail", 1),
            "unknown-replay": ("error", 2),
        }
        for case, (expected_status, expected_code) in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                checkout = Path(tmp) / "checkout"
                copy_checkout(checkout)
                workflows = checkout / "proof" / "replay" / "golden-workflows.json"
                if case == "missing-workflows":
                    workflows.unlink()
                elif case == "corrupt-workflows":
                    workflows.write_text("{", encoding="utf-8")
                elif case == "missing-evidence":
                    (checkout / "proof" / "runtime" / "README.md").unlink()
                else:
                    proof_registry = load_json(checkout / "skill" / "catalog" / "proofs.json")
                    replay_claim = next(row for row in proof_registry["claims"]
                                        if row.get("replay_id"))
                    replay_claim["replay_id"] = "golden.unknown"
                    (checkout / "skill" / "catalog" / "proofs.json").write_text(
                        json.dumps(proof_registry), encoding="utf-8")
                before = snapshot(checkout)

                process = doctor_cli(checkout / "skill" / "scripts" / "docdna_doctor.py",
                                     "--json", "--source-checkout", cwd=str(Path(tmp)))
                after = snapshot(checkout)

            self.assertEqual(before, after)
            self.assertEqual(process.returncode, expected_code, process.stderr)
            self.assertEqual(process.stderr, "")
            payload = json.loads(process.stdout)
            proof = payload["checks"][-1]
            self.assertEqual(proof["id"], "proof-registry")
            self.assertEqual(proof["status"], expected_status)
            self.assertEqual(proof["details"]["validation_mode"], "source-checkout")
            self.assertTrue(proof["remediation"])
            self.assertNotIn("Traceback", process.stdout)

    def test_proof_and_workflow_roots_must_be_json_objects(self):
        wrong_roots = ("[]", '"wrong"', "null")
        for source, body in (("proof", value) for value in wrong_roots):
            with self.subTest(source=source, body=body), tempfile.TemporaryDirectory() as tmp:
                installed_root = Path(tmp) / "docdna"
                copy_skill(installed_root)
                (installed_root / "catalog" / "proofs.json").write_text(body, encoding="utf-8")
                process = doctor_cli(installed_root / "scripts" / "docdna_doctor.py", "--json",
                                     cwd=str(Path(tmp)))

            self.assertEqual(process.returncode, 2, process.stderr)
            self.assertEqual(process.stderr, "")
            payload = json.loads(process.stdout)
            proof = payload["checks"][-1]
            self.assertEqual(proof["status"], "error")
            self.assertIn("must contain one JSON object", " ".join(proof["details"]["errors"]))
            self.assertNotIn("Traceback", process.stdout)

        for source, body in (("workflow", value) for value in wrong_roots):
            with self.subTest(source=source, body=body), tempfile.TemporaryDirectory() as tmp:
                checkout = Path(tmp) / "checkout"
                copy_checkout(checkout)
                (checkout / "proof" / "replay" / "golden-workflows.json").write_text(
                    body, encoding="utf-8")
                process = doctor_cli(checkout / "skill" / "scripts" / "docdna_doctor.py",
                                     "--json", "--source-checkout", cwd=str(Path(tmp)))

            self.assertEqual(process.returncode, 2, process.stderr)
            self.assertEqual(process.stderr, "")
            payload = json.loads(process.stdout)
            proof = payload["checks"][-1]
            self.assertEqual(proof["status"], "error")
            self.assertIn("must contain one JSON object", " ".join(proof["details"]["errors"]))
            self.assertNotIn("Traceback", process.stdout)

    def test_doctor_binds_each_root_once_and_rejects_initial_bind_failure(self):
        doctor = load_doctor()
        real_bind = doctor.bind_root
        real_current = doctor.root_is_current
        with mock.patch.object(doctor, "bind_root", wraps=real_bind) as binding, \
                mock.patch.object(doctor, "root_is_current", wraps=real_current) as current:
            report = doctor.build_report(str(SKILL_ROOT), source_checkout=True)

        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(binding.call_count, 2)
        self.assertEqual(current.call_count, 2)

        with mock.patch.object(doctor, "root_is_current", side_effect=(True, False)):
            changed = doctor.build_report(str(SKILL_ROOT), source_checkout=True)
        self.assertEqual(changed["verdict"], "error")
        self.assertIn("changed during proof validation", changed["checks"][-1]["summary"])

        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            process = doctor_cli(DOCTOR_SCRIPT, "--json", "--skill-root", str(missing),
                                 cwd=str(ROOT))
        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, "")
        self.assertIn("remediation:", process.stderr)
        self.assertNotIn("Traceback", process.stderr)

        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / "checkout"
            copy_checkout(checkout)
            (checkout / "install.sh").unlink()
            outside = Path(tmp) / "outside-install.sh"
            outside.write_text("outside\n", encoding="utf-8")
            os.symlink(str(outside), str(checkout / "install.sh"))
            unsafe_marker = doctor_cli(
                checkout / "skill" / "scripts" / "docdna_doctor.py", "--json",
                "--source-checkout", cwd=str(Path(tmp)))
        self.assertEqual(unsafe_marker.returncode, 2)
        self.assertEqual(unsafe_marker.stdout, "")
        self.assertIn("remediation:", unsafe_marker.stderr)
        self.assertNotIn("Traceback", unsafe_marker.stderr)

    def test_doctor_proof_validation_has_no_write_network_subprocess_or_replay_side_effects(self):
        doctor = load_doctor()
        real_open = open

        def read_only_open(*args, **kwargs):
            mode = kwargs.get("mode", args[1] if len(args) > 1 else "r")
            if any(flag in mode for flag in ("w", "a", "x", "+")):
                raise AssertionError("doctor attempted a write")
            return real_open(*args, **kwargs)

        denied = AssertionError("doctor crossed the proof side-effect boundary")
        with mock.patch("builtins.open", side_effect=read_only_open), \
                mock.patch("socket.socket", side_effect=denied), \
                mock.patch("socket.create_connection", side_effect=denied), \
                mock.patch("os.mkdir", side_effect=denied), \
                mock.patch("os.rename", side_effect=denied), \
                mock.patch("os.unlink", side_effect=denied), \
                mock.patch("os.link", side_effect=denied), \
                mock.patch("subprocess.Popen", side_effect=denied), \
                mock.patch("subprocess.run", side_effect=denied):
            report = doctor.build_report(str(SKILL_ROOT), source_checkout=True)

        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["checks"][-1]["details"]["validation_mode"],
                         "source-checkout")
        doctor_source = DOCTOR_SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("docdna_proof", doctor_source)
        self.assertNotIn("replay_workflows", doctor_source)

    def test_doctor_never_imports_or_executes_the_registered_proof_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed_root = Path(tmp) / "docdna"
            copy_skill(installed_root)
            marker = Path(tmp) / "proof-command-executed"
            malicious = (
                "from pathlib import Path\n"
                "Path(%r).write_text('executed', encoding='utf-8')\n"
                "raise RuntimeError('proof command executed')\n"
            ) % str(marker)
            (installed_root / "scripts" / "docdna_proof.py").write_text(
                malicious, encoding="utf-8")

            process = doctor_cli(installed_root / "scripts" / "docdna_doctor.py", "--json",
                                 cwd=str(Path(tmp)))
            marker_exists = marker.exists()

        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertFalse(marker_exists)
        self.assertNotIn("proof command executed", process.stdout + process.stderr)
        self.assertNotIn("Traceback", process.stdout + process.stderr)
        self.assertEqual(json.loads(process.stdout)["checks"][-1]["status"], "pass")

    def test_source_checkout_rejects_symlinked_evidence_and_workflow_operands(self):
        cases = ("evidence", "workflow-operand")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                checkout = Path(tmp) / "checkout"
                copy_checkout(checkout)
                outside = Path(tmp) / "outside"
                if case == "evidence":
                    outside.write_text("outside evidence\n", encoding="utf-8")
                    target = checkout / "proof" / "runtime" / "README.md"
                    target.unlink()
                else:
                    outside.mkdir()
                    target = checkout / "tests" / "fixtures" / "internal_service"
                    shutil.rmtree(str(target))
                os.symlink(str(outside), str(target))
                before = snapshot(Path(tmp))

                process = doctor_cli(checkout / "skill" / "scripts" / "docdna_doctor.py",
                                     "--json", "--source-checkout", cwd=str(Path(tmp)))
                after = snapshot(Path(tmp))

            self.assertEqual(before, after)
            self.assertEqual(process.returncode, 2, process.stderr)
            self.assertEqual(process.stderr, "")
            payload = json.loads(process.stdout)
            proof = payload["checks"][-1]
            self.assertEqual(proof["status"], "error")
            self.assertIn("symlink", " ".join(proof["details"]["errors"]).lower())
            self.assertNotIn("Traceback", process.stdout)

    def test_source_checkout_uses_bound_root_during_swap_and_restore(self):
        doctor = load_doctor()
        real_validate = doctor.validate_proof_contract
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / "checkout"
            copy_checkout(checkout)
            parked = Path(tmp) / "parked-checkout"
            before = snapshot(checkout)

            def swap_then_validate(proof_registry, workflows, checkout_root):
                self.assertIsInstance(checkout_root, doctor.RepositoryRoot)
                os.rename(str(checkout), str(parked))
                checkout.mkdir()
                try:
                    return real_validate(proof_registry, workflows, checkout_root)
                finally:
                    checkout.rmdir()
                    os.rename(str(parked), str(checkout))

            with mock.patch.object(doctor, "validate_proof_contract",
                                   side_effect=swap_then_validate):
                report = doctor.build_report(str(checkout / "skill"), source_checkout=True)

            after = snapshot(checkout)

        self.assertEqual(before, after)
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["checks"][-1]["details"]["validation_mode"],
                         "source-checkout")

if __name__ == "__main__":
    unittest.main()
