#!/usr/bin/env python3
"""Report deterministic health for a DocDNA checkout or installed skill.

Implements: P-MUST-03
"""

import argparse
import json
import os
import sys


sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

REGISTRY_PATH = "catalog/runtimes.json"
MAX_MEMBER_BYTES = 5 * 1024 * 1024
BOOTSTRAP_ERROR = None
try:
    from docdna_fs import (FileTooLarge, RepositoryRoot, bind_root, control_file_exists,
                           parse_json, path_stat, read_text, root_identity, root_is_current)
    from docdna_runtime import (INSTALLED_PROOF_BOUNDARY, MAX_MEMBER_BYTES, REGISTRY_PATH,
                                RuntimeRegistryError, load_registry, validate_proof_contract)
except (ImportError, SyntaxError) as error:
    BOOTSTRAP_ERROR = error


SCHEMA = 1
TOOL = "docdna_doctor"
SKILL_ROOT = os.path.normpath(os.path.join(HERE, ".."))
RESOURCE_SECTIONS = ("runtime_members", "registries", "templates", "references")
REPAIR = ("Reinstall DocDNA from trusted release bytes, then from the skill directory run: "
          "python3 scripts/docdna_doctor.py --json")
CHECKOUT_PROOF_BOUNDARY = (
    "source checkout validation checks evidence paths and replay IDs against the registered "
    "golden workflow fixture without executing commands or target repository code")


def check_result(ident, status, summary, details=None, remediation=None):
    row = {"id": ident, "status": status, "summary": summary}
    if details is not None:
        row["details"] = details
    if remediation is not None:
        row["remediation"] = remediation
    return row


def resource_rows(registry):
    rows = []
    for section in RESOURCE_SECTIONS:
        for item in registry[section]:
            rows.append((section, item))
    return rows


def resource_path(registry, ident):
    for item in registry["registries"]:
        if item["id"] == ident:
            return item["path"]
    raise RuntimeRegistryError("smoke check names unknown registry %s" % ident)


def _read_bound(root, path, max_bytes=MAX_MEMBER_BYTES):
    if not control_file_exists(root, path):
        return None
    return read_text(root, path, max_bytes=max_bytes)


def check_runtime_registry(registry, smoke):
    return check_result(smoke["id"], "pass", "runtime registry schema is valid",
                        {"schema": registry["schema"], "source": resource_path(registry,
                                                                                smoke["target"])})


def check_python(registry, smoke):
    minimum = tuple(registry[smoke["target"]])
    supported = sys.version_info[:2] >= minimum
    details = {"minimum": "%d.%d" % minimum, "running_supported": supported}
    if supported:
        return check_result(smoke["id"], "pass",
                            "Python meets the declared %d.%d minimum" % minimum, details)
    return check_result(
        smoke["id"], "fail", "Python is older than the declared %d.%d minimum" % minimum,
        details, "Install Python %d.%d or newer, then rerun the doctor." % minimum)


def check_members(registry, smoke, skill_root):
    missing = []
    malformed = []
    unsafe = []
    failures = []
    for section, item in resource_rows(registry):
        path = item["path"]
        try:
            source = _read_bound(skill_root, path)
        except FileTooLarge as error:
            reason = "exceeds %d bytes (found %d)" % (MAX_MEMBER_BYTES, error.size)
            unsafe.append({"path": path, "reason": reason})
            failures.append({"path": path, "reason": reason, "status": "error"})
            continue
        except (OSError, UnicodeError, ValueError) as error:
            unsafe.append({"path": path, "reason": str(error)})
            failures.append({"path": path, "reason": str(error), "status": "error"})
            continue
        if source is None:
            missing.append(path)
            failures.append({"path": path, "reason": "missing", "status": "fail"})
            continue
        if section == "runtime_members":
            try:
                compile(source, path, "exec")
            except (SyntaxError, ValueError, TypeError) as error:
                malformed.append({"path": path, "reason": str(error)})
                failures.append({"path": path, "reason": str(error), "status": "fail"})

    details = {"registered": len(resource_rows(registry)), "missing": missing,
               "malformed": malformed, "unsafe": unsafe, "failures": failures}
    if unsafe:
        return check_result(smoke["id"], "error",
                            "%d registered resource(s) could not be read safely" % len(unsafe),
                            details, REPAIR)
    if missing or malformed:
        count = len(missing) + len(malformed)
        return check_result(smoke["id"], "fail",
                            "%d registered runtime resource(s) failed validation" % count,
                            details, REPAIR)
    return check_result(smoke["id"], "pass",
                        "%d registered runtime resources are present and readable"
                        % details["registered"], details)


def _read_proof_input(root, path):
    return _read_bound(root, path)


def _parse_mapping(raw, path):
    value = parse_json(raw, path)
    if not isinstance(value, dict):
        raise ValueError("%s must contain one JSON object" % path)
    return value


def _installed_proof_mode(path):
    return {"path": path, "validation_mode": "installed-registry",
            "boundary": INSTALLED_PROOF_BOUNDARY,
            "evidence_paths_validated": False, "replay_ids_validated": False}


def _checkout_proof_mode(path, workflows):
    return {"path": path, "validation_mode": "source-checkout",
            "boundary": CHECKOUT_PROOF_BOUNDARY, "workflows": workflows,
            "evidence_paths_validated": False, "replay_ids_validated": False}


def check_proof_registry(registry, smoke, skill_root, checkout_root=None):
    path = resource_path(registry, smoke["target"])
    workflows_path = smoke["checkout_target"] if checkout_root is not None else None
    mode = (_checkout_proof_mode(path, workflows_path) if checkout_root is not None
            else _installed_proof_mode(path))
    try:
        raw = _read_proof_input(skill_root, path)
    except FileTooLarge as error:
        return check_result(
            smoke["id"], "error", "proof registry exceeds its bounded read limit",
            dict(mode, bytes=error.size), REPAIR)
    except (OSError, UnicodeError, ValueError) as error:
        return check_result(smoke["id"], "error", "proof registry could not be read safely",
                            dict(mode, reason=str(error)), REPAIR)
    if raw is None:
        return check_result(smoke["id"], "fail", "proof registry is missing",
                            mode, REPAIR)
    try:
        proof_registry = _parse_mapping(raw, path)
    except (TypeError, ValueError, RecursionError) as error:
        return check_result(smoke["id"], "error", "proof registry is invalid",
                            dict(mode, errors=[str(error)]), REPAIR)
    if checkout_root is None:
        workflows = None
    else:
        try:
            workflow_raw = _read_proof_input(checkout_root, workflows_path)
        except FileTooLarge as error:
            return check_result(
                smoke["id"], "error", "golden workflow fixture exceeds its bounded read limit",
                dict(mode, bytes=error.size), REPAIR)
        except (OSError, UnicodeError, ValueError) as error:
            return check_result(smoke["id"], "error",
                                "golden workflow fixture could not be read safely",
                                dict(mode, reason=str(error)), REPAIR)
        if workflow_raw is None:
            return check_result(smoke["id"], "fail", "golden workflow fixture is missing",
                                mode, REPAIR)
        try:
            workflows = _parse_mapping(workflow_raw, workflows_path)
        except (TypeError, ValueError, RecursionError) as error:
            return check_result(smoke["id"], "error", "golden workflow fixture is invalid",
                                dict(mode, errors=[str(error)]), REPAIR)
        if not root_is_current(checkout_root):
            return check_result(smoke["id"], "error",
                                "source checkout changed before proof validation",
                                mode, REPAIR)
    try:
        validation = validate_proof_contract(proof_registry, workflows, checkout_root)
    except (TypeError, ValueError, RecursionError) as error:
        return check_result(smoke["id"], "error", "proof validation could not complete",
                            dict(mode, errors=[str(error)]), REPAIR)
    if checkout_root is not None and not root_is_current(checkout_root):
        return check_result(smoke["id"], "error",
                            "source checkout changed during proof validation",
                            mode, REPAIR)
    if validation["errors"]:
        missing_only = all("does not exist" in error for error in validation["errors"])
        status = "fail" if missing_only else "error"
        summary = ("proof evidence is missing" if missing_only
                   else "proof registry or golden workflow fixture is invalid")
        return check_result(smoke["id"], status, summary,
                            dict(mode, errors=validation["errors"]), REPAIR)
    if checkout_root is not None:
        mode["evidence_paths_validated"] = True
        mode["replay_ids_validated"] = True
        return check_result(
            smoke["id"], "pass", "proof registry, evidence paths, and replay IDs are valid",
            dict(mode, claims=len(validation["claims"])))
    return check_result(
        smoke["id"], "pass", "proof registry is valid in installed-registry mode",
        dict(mode, claims=len(validation["claims"])))


CHECKERS = {
    "registry": check_runtime_registry,
    "python": check_python,
    "members": check_members,
    "proof-installed-registry": check_proof_registry,
}


def _bind_report_root(path, label):
    try:
        return bind_root(os.path.abspath(path))
    except (OSError, ValueError):
        raise RuntimeRegistryError("unsafe or unavailable %s" % label)


def _bind_checkout_root(skill_root):
    if os.path.basename(os.path.normpath(str(skill_root))) != "skill":
        raise RuntimeRegistryError("--source-checkout requires a skill directory named skill")
    checkout = _bind_report_root(os.path.dirname(os.path.normpath(str(skill_root))),
                                 "source checkout root")
    try:
        if not control_file_exists(checkout, "install.sh"):
            raise RuntimeRegistryError(
                "--source-checkout requires install.sh beside the skill directory")
        skill_details = path_stat(checkout, "skill")
        if (skill_details is None
                or (skill_details.st_dev, skill_details.st_ino) != root_identity(skill_root)):
            raise RuntimeRegistryError(
                "--source-checkout skill directory does not match its bound checkout root")
        return checkout
    except RuntimeRegistryError:
        checkout.close()
        raise
    except (OSError, ValueError):
        checkout.close()
        raise RuntimeRegistryError("unsafe source checkout marker")


def _build_report_bound(skill_root, registry_path, checkout_root=None):
    registry = load_registry(skill_root, registry_path)
    checks = []
    for smoke in registry["smoke_checks"]:
        checker = CHECKERS[smoke["kind"]]
        if smoke["kind"] == "members":
            result = checker(registry, smoke, skill_root)
        elif smoke["kind"] == "proof-installed-registry":
            result = checker(registry, smoke, skill_root, checkout_root)
        else:
            result = checker(registry, smoke)
        checks.append(result)
    summary = dict((status, sum(row["status"] == status for row in checks))
                   for status in ("pass", "fail", "error"))
    summary["total"] = len(checks)
    verdict = "error" if summary["error"] else ("fail" if summary["fail"] else "pass")
    return {"schema": SCHEMA, "tool": TOOL, "read_only": True, "verdict": verdict,
            "checks": checks, "summary": summary}


def build_report(skill_root=SKILL_ROOT, registry_path=REGISTRY_PATH, source_checkout=False):
    skill_binding = _bind_report_root(skill_root, "skill root")
    checkout_binding = None
    try:
        if source_checkout:
            checkout_binding = _bind_checkout_root(skill_binding)
        return _build_report_bound(skill_binding, registry_path, checkout_binding)
    finally:
        if checkout_binding is not None:
            checkout_binding.close()
        skill_binding.close()


def render_text(report):
    lines = ["docdna doctor: %s" % report["verdict"].upper(),
             "checks: %(pass)d pass, %(fail)d fail, %(error)d error" % report["summary"]]
    for row in report["checks"]:
        lines.append("%s %s: %s" % (row["status"].upper(), row["id"], row["summary"]))
        if "remediation" in row:
            lines.append("  remediation: %s" % row["remediation"])
    lines.append("")
    return "\n".join(lines)


def exit_code(report):
    if report["summary"]["error"]:
        return 2
    if report["summary"]["fail"]:
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check the installed DocDNA runtime without writing.")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument(
        "--skill-root", default=SKILL_ROOT,
        help="skill directory containing catalog, scripts, references, and templates")
    parser.add_argument("--registry", default=REGISTRY_PATH,
                        help="skill-relative runtime registry path")
    parser.add_argument("--source-checkout", action="store_true",
                        help="validate checkout-only proof evidence and golden workflow contracts")
    args = parser.parse_args(argv)
    if BOOTSTRAP_ERROR is not None:
        missing = getattr(BOOTSTRAP_ERROR, "name", None)
        known = {"docdna_runtime": "scripts/docdna_runtime.py",
                 "docdna_fs": "scripts/docdna_fs.py"}
        if missing in known:
            message = "missing bootstrap runtime member %s" % known[missing]
        else:
            message = "invalid bootstrap runtime member"
        sys.stderr.write("docdna_doctor: %s. %s\n" % (message, REPAIR))
        return 1
    try:
        report = build_report(args.skill_root, args.registry, args.source_checkout)
    except RuntimeRegistryError as error:
        sys.stderr.write("docdna_doctor: %s\nremediation: %s\n" % (error, REPAIR))
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        sys.stdout.write(render_text(report))
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
