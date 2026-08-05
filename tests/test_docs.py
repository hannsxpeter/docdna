import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skill" / "SKILL.md"
SCRIPTS = ROOT / "skill" / "scripts"
WORKFLOWS = ROOT / ".github" / "workflows"
INSTALLER = ROOT / "install.sh"
LLMS = ROOT / "skill" / "scripts" / "docdna_llms.py"
BACKFILL = ROOT / "skill" / "scripts" / "docdna_backfill.py"
FS = ROOT / "skill" / "scripts" / "docdna_fs.py"
SCAN = ROOT / "skill" / "scripts" / "docdna_scan.py"
SELECT = ROOT / "skill" / "scripts" / "docdna_select.py"

MAX_DESCRIPTION = 1536
MAX_SKILL_LINES = 300

SKIP_DIRS = {".git", "design", "__pycache__", ".pytest_cache", "node_modules"}
LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"^\s*(?:```|~~~)")
SCRIPT_NAME = re.compile(r"docdna_[a-z_]+\.py")
SCRIPT_PATH = re.compile(r"skill/scripts/[A-Za-z0-9_.\-]+")
SOURCE_PATH = re.compile(r"\$SRC_DIR/([A-Za-z0-9_./\-]+)")
SKIP_LINK = ("http://", "https://", "mailto:", "tel:", "#", "<")

EM_DASH = "\u2014"
EN_DASH = "\u2013"
EMOJI_RANGES = ((0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0xFE00, 0xFE0F))


def text_of(path):
    raw = path.read_bytes()
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repo_files():
    files = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if set(path.relative_to(ROOT).parts[:-1]) & SKIP_DIRS:
            continue
        files.append(path)
    return files


def documented_files():
    files = [ROOT / "README.md", SKILL, ROOT / "CONTRIBUTING.md"]
    files.extend(sorted((ROOT / "docs").rglob("*.md")))
    return [path for path in files if path.is_file()]


def frontmatter(path):
    lines = (text_of(path) or "").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    data = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return data
        if line[:1] in (" ", "\t") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return None


def links(text):
    found = []
    fence = False
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fence = not fence
            continue
        if fence:
            continue
        for target in LINK.findall(line):
            found.append((number, target))
    return found


def relative_link(target):
    if target.startswith(SKIP_LINK) or "://" in target:
        return None
    clean = target.split("#", 1)[0].split("?", 1)[0]
    return clean or None


def is_emoji(point):
    for low, high in EMOJI_RANGES:
        if low <= point <= high:
            return True
    return False


def offenders(text):
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for char in line:
            if char in (EM_DASH, EN_DASH) or is_emoji(ord(char)):
                found.append("line %d: U+%04X" % (number, ord(char)))
    return found


class SkillDocumentTests(unittest.TestCase):
    def test_skill_frontmatter_carries_a_name_and_a_description(self):
        data = frontmatter(SKILL)

        self.assertIsNotNone(data, "skill/SKILL.md has no terminated frontmatter block")
        self.assertEqual(data.get("name"), "docdna")
        self.assertTrue(data.get("description"))
        self.assertIn("allowed-tools", data)

    def test_skill_description_stays_under_the_limit(self):
        description = frontmatter(SKILL)["description"]

        self.assertLess(len(description), MAX_DESCRIPTION,
                        "description is %d characters" % len(description))

    def test_skill_md_stays_under_three_hundred_lines(self):
        count = len(SKILL.read_text(encoding="utf-8").splitlines())

        self.assertLess(count, MAX_SKILL_LINES, "skill/SKILL.md is %d lines" % count)

    def test_backfill_cli_documents_safe_stub_retention_as_the_default(self):
        text = SKILL.read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("| `docdna_backfill.py`"))

        self.assertIn("--delete-stub", row)
        self.assertIn("--keep", row)
        self.assertIn("default", row)
        self.assertIn("retained by default", text)


class CompatibilityContractTests(unittest.TestCase):
    def test_ci_exercises_python_3_8_and_latest(self):
        workflow = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")

        self.assertIn('python-version: "${{ matrix.python }}"', workflow)
        self.assertRegex(workflow, r"python:\s*\[\s*\"3\.8\"\s*,\s*\"3\.x\"\s*\]")

    def test_runtime_contract_names_posix_and_does_not_claim_windows_support(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        skill = SKILL.read_text(encoding="utf-8")

        for text in (readme, contributing, skill):
            self.assertIn("POSIX", text)
            self.assertIn("Windows is not supported", text)


class GeneratedArtifactContractTests(unittest.TestCase):
    def test_ci_checks_committed_artifacts_before_the_pipeline_mutates_them(self):
        workflow = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        gate = workflow.index("Committed generated artifacts match the code")
        pipeline = workflow.index("Run the whole pipeline on this repository")
        gate_body = workflow[gate:pipeline]

        self.assertLess(gate, pipeline)
        self.assertIn("cp DOCDNA.md", gate_body)
        self.assertIn("cp llms.txt", gate_body)
        self.assertIn("diff", gate_body)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("fetch-tags: true", workflow)

    def test_committed_llms_text_does_not_embed_volatile_generation_metadata(self):
        llms = load("docdna_llms_contract", LLMS)
        manifest = {"archetype": {"primary": "solo-utility"}, "generated_by": "docdna v1.2.0",
                    "generated_at": "2026-08-05", "repo_head": "abc1234"}
        with tempfile.TemporaryDirectory() as tmp:
            lines = llms.blockquote(tmp, manifest, 1)

        text = "\n".join(lines)
        self.assertNotIn("abc1234", text)
        self.assertNotIn("2026-08-05", text)

    def test_llms_project_name_survives_a_renamed_checkout(self):
        llms = load("docdna_llms_repository_name", LLMS)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "renamed-checkout"
            root.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
            origin = str(Path(tmp) / "docdna") + "/."
            subprocess.run(["git", "remote", "add", "origin", origin], cwd=str(root), check=True)

            self.assertEqual(llms.repository_name(str(root)), "docdna")

    def test_race_safe_reader_enforces_its_limit_after_opening_the_file(self):
        fs = load("docdna_fs_growth_limit", FS)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "growing.txt"
            path.write_text("1234", encoding="utf-8")
            original = fs._open_regular

            def grow_after_open(repo, candidate):
                descriptor, details = original(repo, candidate)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("5678")
                return descriptor, details

            with mock.patch.object(fs, "_open_regular", side_effect=grow_after_open):
                with self.assertRaises(fs.FileTooLarge):
                    fs.read_text(str(root), "growing.txt", max_bytes=4)

    def test_shared_reads_keep_the_original_root_when_its_path_is_replaced(self):
        fs = load("docdna_fs_read_root_swap", FS)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            root.mkdir()
            (root / "value.txt").write_text("original\n", encoding="utf-8")
            moved = base / "repo-original"
            replacement = base / "replacement"
            replacement.mkdir()
            (replacement / "value.txt").write_text("outside-marker\n", encoding="utf-8")
            original = fs._parts

            def swap_after_validation(repo, candidate):
                result = original(repo, candidate)
                root.rename(moved)
                replacement.rename(root)
                return result

            with mock.patch.object(fs, "_parts", side_effect=swap_after_validation):
                text = fs.read_text(str(root), "value.txt")

            self.assertEqual(text, "original\n")

    def test_shared_writes_keep_the_original_root_when_its_path_is_replaced(self):
        fs = load("docdna_fs_write_root_swap", FS)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            root.mkdir()
            (root / "value.txt").write_text("old\n", encoding="utf-8")
            moved = base / "repo-original"
            replacement = base / "replacement"
            replacement.mkdir()
            (replacement / "value.txt").write_text("outside-marker\n", encoding="utf-8")
            original = fs._parts

            def swap_after_validation(repo, candidate):
                result = original(repo, candidate)
                root.rename(moved)
                replacement.rename(root)
                return result

            with mock.patch.object(fs, "_parts", side_effect=swap_after_validation):
                fs.write_text(str(root), "value.txt", "new\n")

            self.assertEqual((moved / "value.txt").read_text(encoding="utf-8"), "new\n")
            self.assertEqual((root / "value.txt").read_text(encoding="utf-8"),
                             "outside-marker\n")

    def test_shared_unlink_keeps_the_original_root_when_its_path_is_replaced(self):
        fs = load("docdna_fs_unlink_root_swap", FS)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            root.mkdir()
            (root / "value.txt").write_text("original\n", encoding="utf-8")
            moved = base / "repo-original"
            replacement = base / "replacement"
            replacement.mkdir()
            (replacement / "value.txt").write_text("outside-marker\n", encoding="utf-8")
            original = fs._parts
            _, identity = fs.read_text_with_identity(str(root), "value.txt")

            def swap_after_validation(repo, candidate):
                result = original(repo, candidate)
                root.rename(moved)
                replacement.rename(root)
                return result

            with mock.patch.object(fs, "_parts", side_effect=swap_after_validation):
                fs.unlink_file(str(root), "value.txt", identity)

            self.assertFalse((moved / "value.txt").exists())
            self.assertEqual((root / "value.txt").read_text(encoding="utf-8"),
                             "outside-marker\n")

    def test_stable_symlink_repository_roots_are_supported(self):
        fs = load("docdna_fs_stable_root_symlink", FS)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "repo"
            root.mkdir()
            link = base / "repo-link"
            os.symlink(str(root), str(link))
            (root / "value.txt").write_text("original\n", encoding="utf-8")

            self.assertEqual(fs.read_text(str(link), "value.txt"), "original\n")
            fs.write_text(str(link), "value.txt", "updated\n")
            self.assertEqual((root / "value.txt").read_text(encoding="utf-8"), "updated\n")

    def test_root_binding_rejects_an_ancestor_directory_swap(self):
        fs = load("docdna_fs_ancestor_swap", FS)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            anchor = base / "anchor"
            root = anchor / "repo"
            root.mkdir(parents=True)
            (root / "value.txt").write_text("original\n", encoding="utf-8")
            moved = base / "anchor-original"
            replacement = base / "replacement"
            (replacement / "repo").mkdir(parents=True)
            (replacement / "repo" / "value.txt").write_text("outside-marker\n",
                                                              encoding="utf-8")
            original = fs.os.path.realpath
            swapped = {"done": False}

            def swap_before_resolution(path):
                if not swapped["done"]:
                    swapped["done"] = True
                    os.rename(str(anchor), str(moved))
                    os.rename(str(replacement), str(anchor))
                return original(path)

            with mock.patch.object(fs.os.path, "realpath", side_effect=swap_before_resolution):
                with self.assertRaises(ValueError):
                    fs.read_text(str(root), "value.txt")

    def test_fifo_inputs_are_refused_without_blocking(self):
        fs = load("docdna_fs_fifo", FS)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.mkfifo(str(root / "evil.py"))

            self.assertTrue(fs.path_exists(str(root), "evil.py"))
            self.assertFalse(fs.is_file(str(root), "evil.py"))
            with self.assertRaises(ValueError):
                fs.read_text(str(root), "evil.py")

    def test_walk_closes_all_descriptors_when_a_nested_listing_fails(self):
        fs = load("docdna_fs_walk_cleanup", FS)
        for fail_at in (1, 2):
            with self.subTest(listing=fail_at), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "nested").mkdir()
                before = len(os.listdir("/dev/fd"))
                original = fs._LISTDIR
                calls = {"count": 0}

                def fail_listing(descriptor):
                    calls["count"] += 1
                    if calls["count"] == fail_at:
                        raise OSError("injected listing failure")
                    return original(descriptor)

                with mock.patch.object(fs, "_LISTDIR", side_effect=fail_listing):
                    with self.assertRaises((OSError, ValueError)):
                        fs.walk_paths(str(root))
                self.assertEqual(len(os.listdir("/dev/fd")), before)

    def test_atomic_write_closes_its_descriptor_when_mode_preservation_fails(self):
        fs = load("docdna_fs_fchmod_cleanup", FS)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "private.txt"
            path.write_text("old\n", encoding="utf-8")
            before = len(os.listdir("/dev/fd"))

            with mock.patch.object(fs.os, "fchmod", side_effect=OSError("injected failure")):
                with self.assertRaises(ValueError):
                    fs.write_text(str(root), "private.txt", "new\n")

            self.assertEqual(len(os.listdir("/dev/fd")), before)
            self.assertEqual(path.read_text(encoding="utf-8"), "old\n")

    def test_atomic_replacement_preserves_an_existing_files_mode(self):
        fs = load("docdna_fs_output_mode", FS)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "private.txt"
            path.write_text("old\n", encoding="utf-8")
            path.chmod(0o600)

            fs.write_text(str(root), "private.txt", "new\n")

            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_safe_unlink_refuses_an_in_place_edit_after_verification(self):
        fs = load("docdna_fs_unlink_edit", FS)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "value.txt"
            path.write_text("verified\n", encoding="utf-8")
            _, identity = fs.read_text_with_identity(str(root), "value.txt")
            path.write_text("modified\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                fs.unlink_file(str(root), "value.txt", identity)
            self.assertEqual(path.read_text(encoding="utf-8"), "modified\n")

    def test_safe_unlink_refuses_an_append_during_digest_validation(self):
        fs = load("docdna_fs_unlink_append", FS)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "value.txt"
            path.write_text("verified\n", encoding="utf-8")
            _, identity = fs.read_text_with_identity(str(root), "value.txt")
            writer = os.open(str(path), os.O_WRONLY | os.O_APPEND)
            original = fs.os.read
            appended = {"done": False}

            def append_before_read(descriptor, size):
                if not appended["done"]:
                    appended["done"] = True
                    os.write(writer, b"human edit\n")
                return original(descriptor, size)

            try:
                with mock.patch.object(fs.os, "read", side_effect=append_before_read):
                    with self.assertRaises(ValueError):
                        fs.unlink_file(str(root), "value.txt", identity)
            finally:
                os.close(writer)
            self.assertIn("human edit", path.read_text(encoding="utf-8"))

    def test_safe_unlink_restores_a_replacement_captured_after_verification(self):
        fs = load("docdna_fs_unlink_replacement", FS)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "value.txt"
            saved = root / "verified.txt"
            path.write_text("verified\n", encoding="utf-8")
            _, identity = fs.read_text_with_identity(str(root), "value.txt")
            original_parent = fs._open_parent
            swapped = {"done": False}

            def replace_before_capture(repo, candidate, create=False, root_descriptor=None):
                result = original_parent(repo, candidate, create, root_descriptor)
                if not swapped["done"]:
                    swapped["done"] = True
                    os.rename(str(path), str(saved))
                    path.write_text("human replacement\n", encoding="utf-8")
                return result

            with mock.patch.object(fs, "_open_parent", side_effect=replace_before_capture):
                with self.assertRaises(ValueError):
                    fs.unlink_file(str(root), "value.txt", identity)

            self.assertEqual(path.read_text(encoding="utf-8"), "human replacement\n")
            self.assertEqual(saved.read_text(encoding="utf-8"), "verified\n")

    def test_llms_summary_reads_have_an_explicit_size_limit(self):
        llms = load("docdna_llms_summary_limit", LLMS)
        with mock.patch.object(llms, "safe_read_text", return_value="# title\n") as reader:
            llms.first_paragraph("/repo", "README.md")

        self.assertIn("max_bytes", reader.call_args.kwargs)
        self.assertGreater(reader.call_args.kwargs["max_bytes"], 0)

    def test_llms_sidecar_quotes_repository_controlled_yaml_scalars(self):
        llms = load("docdna_llms_yaml_scalar", LLMS)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = {"schema": 1, "repo_head": "abc123",
                        "documents": [{"id": llms.OUTPUT_ID,
                                       "title": "index\ninjected: true",
                                       "owner_candidate": "false # comment"}],
                        "excluded": []}

            llms.write_sidecar(str(root), manifest)

            text = (root / ".docdna/meta/build.llms-txt.yml").read_text(encoding="utf-8")
            self.assertNotIn("\ninjected: true\n", text)
            self.assertIn('title: "index\\ninjected: true"', text)
            self.assertIn('owner_candidate: "false # comment"', text)

    def test_manifest_shape_errors_are_concise_at_consumer_clis(self):
        scripts = (LLMS, BACKFILL)
        manifests = (
            {"schema": 1, "interview": {}, "archetype": {},
             "documents": [{"because": 1}], "excluded": []},
            {"schema": 1, "interview": {}, "archetype": {},
             "documents": [{"id": "build.llms-txt", "title": None, "stage": "build"}],
             "excluded": []},
            {"schema": 1, "interview": {}, "archetype": {},
             "documents": [{"id": "build.llms-txt", "title": "Index", "stage": None,
                            "state": "present-fresh", "path": "README.md"}],
             "excluded": []},
        )
        for script in scripts:
            for manifest in manifests:
                with self.subTest(script=script.name, manifest=manifest), \
                        tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    metadata = root / ".docdna"
                    metadata.mkdir()
                    (metadata / "manifest.json").write_text(json.dumps(manifest),
                                                             encoding="utf-8")

                    process = subprocess.run([sys.executable, str(script), str(root)],
                                             capture_output=True, text=True)

                    self.assertEqual(process.returncode, 2)
                    self.assertNotIn("Traceback", process.stderr)

    def test_llms_pipeline_does_not_follow_a_manifest_document_symlink_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            repo.mkdir()
            marker = "external-llms-summary-marker"
            outside = base / "outside.md"
            outside.write_text(marker + "\n", encoding="utf-8")
            os.symlink(str(outside), str(repo / "README.md"))
            subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
            subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True)
            scan_path = base / "scan.json"
            with scan_path.open("w", encoding="utf-8") as handle:
                subprocess.run([sys.executable, str(SCAN), "--json", str(repo)], stdout=handle,
                               check=True)
            subprocess.run([sys.executable, str(SELECT), "--unattended", "--scan",
                            str(scan_path), str(repo)], stdout=subprocess.PIPE, check=True)
            subprocess.run([sys.executable, str(LLMS), str(repo)], stdout=subprocess.PIPE,
                           check=True)

            output = (repo / "llms.txt").read_text(encoding="utf-8")

            self.assertNotIn(marker, output)

    def test_llms_pipeline_does_not_read_a_denied_file_through_an_internal_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            repo.mkdir()
            marker = "private-inrepo-marker"
            (repo / ".env").write_text(marker + "\n", encoding="utf-8")
            os.symlink(".env", str(repo / "README.md"))
            subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
            subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True)
            scan_path = base / "scan.json"
            with scan_path.open("w", encoding="utf-8") as handle:
                subprocess.run([sys.executable, str(SCAN), "--json", str(repo)], stdout=handle,
                               check=True)
            scan_text = scan_path.read_text(encoding="utf-8")
            subprocess.run([sys.executable, str(SELECT), "--unattended", "--scan",
                            str(scan_path), str(repo)], stdout=subprocess.PIPE, check=True)
            subprocess.run([sys.executable, str(LLMS), str(repo)], stdout=subprocess.PIPE,
                           check=True)

            output = (repo / "llms.txt").read_text(encoding="utf-8")

            self.assertNotIn(marker, scan_text)
            self.assertNotIn(marker, output)

    def test_llms_refuses_a_manifest_symlink_to_a_denied_internal_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            metadata = repo / ".docdna"
            metadata.mkdir(parents=True)
            marker = "private-manifest-marker"
            payload = {"schema": 1, "generated_by": marker, "documents": [], "excluded": [],
                       "archetype": {"primary": "solo-utility"}}
            (repo / ".env").write_text(json.dumps(payload), encoding="utf-8")
            os.symlink("../.env", str(metadata / "manifest.json"))

            process = subprocess.run([sys.executable, str(LLMS), str(repo)], capture_output=True,
                                     text=True)

            self.assertEqual(process.returncode, 2)
            self.assertNotIn(marker, process.stdout)
            self.assertFalse((repo / "llms.txt").exists())

    def test_llms_refuses_a_hardlinked_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            metadata = repo / ".docdna"
            metadata.mkdir(parents=True)
            marker = "private-hardlinked-manifest-marker"
            payload = {"schema": 1, "generated_by": marker, "documents": [], "excluded": [],
                       "archetype": {"primary": "solo-utility"}}
            outside = base / "outside-manifest.json"
            outside.write_text(json.dumps(payload), encoding="utf-8")
            os.link(str(outside), str(metadata / "manifest.json"))

            process = subprocess.run([sys.executable, str(LLMS), str(repo)], capture_output=True,
                                     text=True)

            self.assertEqual(process.returncode, 2)
            self.assertNotIn(marker, process.stdout)
            self.assertFalse((repo / "llms.txt").exists())

    def test_llms_pipeline_reads_an_allowed_tracked_internal_symlink_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            marker = "safe-inrepo-document-marker"
            target = repo / "docs" / "README-source.md"
            target.parent.mkdir()
            target.write_text(marker + "\n", encoding="utf-8")
            os.symlink("docs/README-source.md", str(repo / "README.md"))
            subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
            subprocess.run(["git", "add", "README.md", "docs/README-source.md"],
                           cwd=str(repo), check=True)
            scan_path = Path(tmp) / "scan.json"
            with scan_path.open("w", encoding="utf-8") as handle:
                subprocess.run([sys.executable, str(SCAN), "--json", str(repo)], stdout=handle,
                               check=True)
            subprocess.run([sys.executable, str(SELECT), "--unattended", "--scan",
                            str(scan_path), str(repo)], stdout=subprocess.PIPE, check=True)
            subprocess.run([sys.executable, str(LLMS), str(repo)], stdout=subprocess.PIPE,
                           check=True)

            output = (repo / "llms.txt").read_text(encoding="utf-8")

            self.assertIn(marker, output)

    def test_llms_pipeline_does_not_read_a_hardlinked_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            repo.mkdir()
            readme = repo / "README.md"
            readme.write_text("benign tracked content\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
            subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True)
            readme.unlink()
            marker = "llms-hardlink-marker"
            outside = base / "outside.md"
            outside.write_text(marker + "\n", encoding="utf-8")
            os.link(str(outside), str(readme))
            scan_path = base / "scan.json"
            with scan_path.open("w", encoding="utf-8") as handle:
                subprocess.run([sys.executable, str(SCAN), "--json", str(repo)], stdout=handle,
                               check=True)
            subprocess.run([sys.executable, str(SELECT), "--unattended", "--scan",
                            str(scan_path), str(repo)], stdout=subprocess.PIPE, check=True)
            subprocess.run([sys.executable, str(LLMS), str(repo)], stdout=subprocess.PIPE,
                           check=True)

            output = (repo / "llms.txt").read_text(encoding="utf-8")

            self.assertNotIn(marker, output)

    def test_llms_rejects_a_lexically_external_manifest_path(self):
        llms = load("docdna_llms_lexical_containment", LLMS)
        manifest = {"documents": [{"id": "build.readme", "title": "README",
                                    "stage": "build", "state": "present-fresh",
                                    "path": "../outside.md"}]}
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (Path(tmp) / "outside.md").write_text("external lexical marker\n", encoding="utf-8")

            sections, skipped = llms.collect(str(repo), manifest)

            self.assertEqual(sections, {})
            self.assertEqual(skipped["missing_file"], 1)

    def test_llms_directory_summary_does_not_inspect_external_symlink_children(self):
        llms = load("docdna_llms_directory_containment", LLMS)
        manifest = {"documents": [{"id": "build.docs", "title": "Docs",
                                    "stage": "build", "state": "present-fresh",
                                    "path": "docs/"}]}
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            docs = repo / "docs"
            docs.mkdir(parents=True)
            outside = Path(tmp) / "outside.md"
            outside.write_text("external child marker\n", encoding="utf-8")
            os.symlink(str(outside), str(docs / "external.md"))

            sections, skipped = llms.collect(str(repo), manifest)

            self.assertEqual(sections["build"][0]["summary"], "0 files in this directory.")
            self.assertEqual(skipped["missing_file"], 0)

    def test_llms_refuses_output_symlinks_without_touching_external_targets(self):
        llms = load("docdna_llms_output_containment", LLMS)
        manifest = {"documents": [], "excluded": []}
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            repo.mkdir()
            outside = base / "outside.txt"
            outside.write_text("untouched\n", encoding="utf-8")
            os.symlink(str(outside), str(repo / "llms.txt"))

            with self.assertRaises(ValueError):
                llms.write_output(str(repo), "generated\n")

            self.assertEqual(outside.read_text(encoding="utf-8"), "untouched\n")

        for rel in (".docdna", ".docdna/meta"):
            with self.subTest(path=rel), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                repo = base / "repo"
                repo.mkdir()
                outside = base / "outside-meta"
                outside.mkdir()
                target = repo / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(str(outside), str(target))

                with self.assertRaises(ValueError):
                    llms.write_sidecar(str(repo), manifest)

                self.assertFalse((outside / (llms.OUTPUT_ID + ".yml")).exists())

    def test_llms_sidecar_write_resists_a_parent_symlink_swap_after_validation(self):
        llms = load("docdna_llms_sidecar_race", LLMS)
        manifest = {"documents": [], "excluded": []}
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            meta = repo / ".docdna" / "meta"
            meta.mkdir(parents=True)
            outside = base / "outside-meta"
            outside.mkdir()
            external = outside / (llms.OUTPUT_ID + ".yml")
            external.write_text("untouched\n", encoding="utf-8")
            original = llms.output_path
            calls = {"count": 0}

            def swap_parent(root, rel):
                path = original(root, rel)
                calls["count"] += 1
                if calls["count"] == 3:
                    meta.rename(repo / ".docdna" / "meta-original")
                    os.symlink(str(outside), str(meta))
                return path

            error = None
            with mock.patch.object(llms, "output_path", side_effect=swap_parent):
                try:
                    llms.write_sidecar(str(repo), manifest)
                except (OSError, ValueError) as caught:
                    error = caught

            self.assertIsNotNone(error)
            self.assertEqual(external.read_text(encoding="utf-8"), "untouched\n")

    def test_llms_replaces_a_hardlinked_output_without_modifying_the_external_inode(self):
        llms = load("docdna_llms_hardlink", LLMS)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            repo.mkdir()
            external = base / "outside-llms.txt"
            external.write_text("untouched\n", encoding="utf-8")
            os.link(str(external), str(repo / "llms.txt"))

            llms.write_output(str(repo), "generated index\n")

            self.assertEqual(external.read_text(encoding="utf-8"), "untouched\n")
            self.assertEqual((repo / "llms.txt").read_text(encoding="utf-8"),
                             "generated index\n")


class LinkTests(unittest.TestCase):
    def test_relative_markdown_links_resolve(self):
        checked = 0
        broken = []
        for path in documented_files():
            for number, target in links(text_of(path) or ""):
                clean = relative_link(target)
                if clean is None:
                    continue
                checked += 1
                if not (path.parent / clean).resolve().exists():
                    broken.append("%s:%d -> %s" % (path.relative_to(ROOT), number, target))

        self.assertGreater(checked, 0, "no relative markdown links were found to check")
        self.assertEqual(broken, [])


class HouseStyleTests(unittest.TestCase):
    def test_no_file_carries_an_em_dash_an_en_dash_or_an_emoji(self):
        checked = 0
        found = {}
        for path in repo_files():
            text = text_of(path)
            if text is None:
                continue
            checked += 1
            hits = offenders(text)
            if hits:
                found[str(path.relative_to(ROOT))] = hits[:5]

        self.assertGreater(checked, 20, "the walk found almost nothing to check")
        self.assertEqual(found, {})

    def test_the_walk_would_catch_an_offending_character(self):
        self.assertEqual(offenders("a " + EM_DASH + " b"), ["line 1: U+2014"])
        self.assertEqual(offenders("pages 10" + EN_DASH + "15"), ["line 1: U+2013"])
        self.assertEqual(offenders("ship it \U0001F680"), ["line 1: U+1F680"])
        self.assertEqual(offenders("done \u2705"), ["line 1: U+2705"])
        self.assertEqual(offenders("pages 10-15, a - b, ok"), [])


class ReferenceTests(unittest.TestCase):
    def script_names(self):
        return set(path.name for path in SCRIPTS.glob("docdna_*.py"))

    def test_installer_references_only_files_that_exist(self):
        text = INSTALLER.read_text(encoding="utf-8")
        sources = SOURCE_PATH.findall(text)

        self.assertGreater(len(sources), 0, "the installer names no source paths")
        for rel in sources:
            self.assertTrue((ROOT / rel).exists(), "install.sh names missing %s" % rel)
        for name in set(SCRIPT_NAME.findall(text)):
            self.assertIn(name, self.script_names())

    def test_ci_workflow_references_only_scripts_that_exist(self):
        workflows = sorted(WORKFLOWS.glob("*.yml"))
        referenced = set()

        self.assertGreater(len(workflows), 0, "no workflow files were found")
        for path in workflows:
            text = path.read_text(encoding="utf-8")
            for rel in set(SCRIPT_PATH.findall(text)):
                self.assertTrue((ROOT / rel).is_file(),
                                "%s names missing %s" % (path.name, rel))
                referenced.add(Path(rel).name)
            for name in set(SCRIPT_NAME.findall(text)):
                self.assertIn(name, self.script_names(),
                              "%s names missing %s" % (path.name, name))
        self.assertGreater(len(referenced), 0, "no workflow runs any helper script")

    def test_the_installer_is_executable(self):
        self.assertTrue(INSTALLER.exists(), "install.sh is missing")

        mode = INSTALLER.stat().st_mode
        self.assertTrue(mode & 0o111,
                        "install.sh is mode %o; README documents ./install.sh, which needs +x"
                        % (mode & 0o777))

    def test_ci_workflow_compiles_every_helper(self):
        compiled = set()
        for path in sorted(WORKFLOWS.glob("*.yml")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if "py_compile" not in line:
                    continue
                compiled.update(Path(rel).name for rel in SCRIPT_PATH.findall(line))

        self.assertEqual(compiled, self.script_names())


if __name__ == "__main__":
    unittest.main()
