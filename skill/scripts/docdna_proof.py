#!/usr/bin/env python3
"""Validate and render DocDNA product claim evidence.

Implements: P-MUST-02
"""

import argparse
import errno
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import time


SCHEMA = 1
TOOL = "docdna_proof"

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.normpath(os.path.join(HERE, ".."))
CHECKOUT_ROOT = os.path.normpath(os.path.join(SKILL_ROOT, ".."))
CHECKOUT_LAYOUT = (os.path.basename(SKILL_ROOT) == "skill"
                   and os.path.isfile(os.path.join(CHECKOUT_ROOT, "install.sh")))
PROJECT_ROOT = CHECKOUT_ROOT if CHECKOUT_LAYOUT else SKILL_ROOT
REGISTRY_PATH = os.path.join(SKILL_ROOT, "catalog", "proofs.json")
WORKFLOWS_PATH = (os.path.join(CHECKOUT_ROOT, "proof", "replay", "golden-workflows.json")
                  if CHECKOUT_LAYOUT else None)

PROMOTION_REQUIREMENTS = (
    ("shipped", "implementation"),
    ("unit-tested", "unit-test"),
    ("install-tested", "install-test"),
    ("artifact-proven", "artifact"),
    ("replay-tested", "replay"),
    ("measured", "measurement"),
    ("adjudicated", "adjudication"),
    ("host-capture-ready", "capture-procedure"),
    ("host-captured", "host-capture"),
    ("external-tool-dependent", "external-dependency"),
)
EVIDENCE_LEVELS = tuple(level for level, _ in PROMOTION_REQUIREMENTS)
EVIDENCE_KINDS = tuple(kind for _, kind in PROMOTION_REQUIREMENTS)
REQUIRED_EVIDENCE = dict(PROMOTION_REQUIREMENTS)
CORE_MODES = ("survey", "backfill", "check", "runtime")
COMMAND_SCHEMAS = {
    "survey": {
        "script": "skill/scripts/docdna_scan.py",
        "flags": {"--json": None},
    },
    "backfill": {
        "script": "skill/scripts/docdna_backfill.py",
        "flags": {"--json": None, "--verify": "repo-path"},
    },
    "check": {
        "script": "skill/scripts/docdna_check.py",
        "flags": {"--json": None, "--no-write": None, "--fail-on": ("never",)},
    },
}
ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
REPLAY_TIMEOUT_SECONDS = 30
MAX_CONTROL_BYTES = 1024 * 1024
MAX_CHILD_OUTPUT_BYTES = 256 * 1024
MAX_CHILD_ERROR_TEXT = 2000
READ_CHUNK_BYTES = 64 * 1024
PROCESS_GRACE_SECONDS = 0.25
INSTALLED_BOUNDARY = ("installed validation checks registry schema and promotion structure only; "
                      "checkout-only evidence paths and golden replays are not shipped or revalidated")

REGISTRY_KEYS = frozenset(("schema", "evidence_levels", "promotion_requirements", "claims"))
PROMOTION_KEYS = frozenset(("requires_evidence",))
CLAIM_KEYS = frozenset(("id", "mode", "claim", "evidence_level", "boundary", "evidence",
                        "corpus", "limitations", "replay_id"))
EVIDENCE_KEYS = frozenset(("kind", "path"))
WORKFLOW_ROOT_KEYS = frozenset(("schema", "workflows"))
WORKFLOW_COMMON_KEYS = frozenset(("id", "mode", "expected_exit", "assertions"))
ASSERTION_KEYS = frozenset(("path", "equals", "length"))


def control_signature(details):
    return (details.st_dev, details.st_ino, details.st_size, details.st_mtime_ns)


def read_control(path, max_bytes=MAX_CONTROL_BYTES):
    try:
        path_details = os.lstat(path)
    except OSError:
        raise
    if stat.S_ISLNK(path_details.st_mode):
        raise ValueError("control file %s refuses symbolic links" % path)
    if not stat.S_ISREG(path_details.st_mode):
        raise ValueError("control file %s must be a regular file" % path)
    if path_details.st_size > max_bytes:
        raise ValueError("control file %s exceeds %d bytes" % (path, max_bytes))

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise ValueError("control file %s refuses symbolic links" % path)
        raise
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("control file %s must be a regular file" % path)
        if (before.st_dev, before.st_ino) != (path_details.st_dev, path_details.st_ino):
            raise ValueError("control file %s changed before reading" % path)
        if before.st_size > max_bytes:
            raise ValueError("control file %s exceeds %d bytes" % (path, max_bytes))
        chunks = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(READ_CHUNK_BYTES, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("control file %s exceeds %d bytes" % (path, max_bytes))
        after = os.fstat(descriptor)
        if control_signature(before) != control_signature(after) or total != after.st_size:
            raise ValueError("control file %s changed while reading" % path)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def read_json(path):
    raw = read_control(path)
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("control file %s is not UTF-8: %s" % (path, error))
    data = json.loads(decoded)
    if not isinstance(data, dict):
        raise ValueError("%s must contain one JSON object" % path)
    return data


def text(value):
    return isinstance(value, str) and bool(value.strip())


def schema_one(value):
    return isinstance(value, int) and not isinstance(value, bool) and value == SCHEMA


def undeclared_fields(value, allowed, where):
    return ["%s has undeclared field %s" % (where, field)
            for field in sorted(set(value) - allowed)]


def duplicate_values(values):
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        else:
            seen.add(value)
    return sorted(duplicates)


def safe_evidence_path(root, relative):
    if not text(relative) or os.path.isabs(relative):
        return None
    normalized = os.path.normpath(relative)
    if normalized == ".." or normalized.startswith(".." + os.sep):
        return None
    root_real = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_real, normalized))
    try:
        inside = os.path.commonpath((root_real, candidate)) == root_real
    except ValueError:
        inside = False
    return candidate if inside else None


def command_path(root, relative):
    candidate = safe_evidence_path(root, relative)
    if candidate is None:
        return None, None
    return os.path.normpath(relative), candidate


def parse_replay_command(workflow, root, where):
    errors = []
    mode = workflow.get("mode")
    schema = COMMAND_SCHEMAS.get(mode)
    if schema is None:
        return errors
    command = workflow.get("command")
    if not isinstance(command, list) or not command or not all(text(arg) for arg in command):
        return ["%s command must be a non-empty string list" % where]

    script_normalized, script_path = command_path(root, command[0])
    if script_normalized != schema["script"]:
        errors.append("%s command must use %s" % (where, schema["script"]))
    elif not os.path.isfile(script_path):
        errors.append("%s command script %s does not exist" % (where, command[0]))

    seen = {}
    operands = []
    index = 1
    while index < len(command):
        token = command[index]
        if not token.startswith("-"):
            operands.append(token)
            index += 1
            continue
        if token not in schema["flags"]:
            errors.append("%s does not allow flag %s" % (where, token))
            index += 1
            continue
        if token in seen:
            errors.append("%s repeats flag %s" % (where, token))
            index += 1
            continue
        value_schema = schema["flags"][token]
        if value_schema is None:
            seen[token] = True
            index += 1
            continue
        if index + 1 >= len(command) or command[index + 1].startswith("-"):
            errors.append("%s flag %s needs a value" % (where, token))
            index += 1
            continue
        seen[token] = command[index + 1]
        index += 2

    for flag in schema["flags"]:
        if flag not in seen:
            errors.append("%s command needs flag %s" % (where, flag))
    if len(operands) != 1:
        errors.append("%s command needs exactly one repository operand" % where)
        repo_path = None
    else:
        operand = operands[0]
        _, repo_path = command_path(root, operand)
        if repo_path is None:
            errors.append("%s operand %s must stay inside the project" % (where, operand))
        elif not os.path.isdir(repo_path):
            errors.append("%s operand %s is not a repository directory" % (where, operand))

    for flag, value_schema in schema["flags"].items():
        if flag not in seen or value_schema is None:
            continue
        value = seen[flag]
        if value_schema == "repo-path":
            if repo_path is None:
                continue
            _, candidate = command_path(repo_path, value)
            if candidate is None:
                errors.append("%s flag %s path %s must stay inside the repository"
                              % (where, flag, value))
            elif not os.path.isfile(candidate):
                errors.append("%s flag %s path %s does not exist" % (where, flag, value))
        elif value not in value_schema:
            errors.append("%s flag %s value must be %s"
                          % (where, flag, ", ".join(value_schema)))
    return errors


def validate_workflows(data, root):
    errors = undeclared_fields(data, WORKFLOW_ROOT_KEYS, "golden workflows")
    if not schema_one(data.get("schema")):
        errors.append("golden workflows schema must be 1")
    workflows = data.get("workflows")
    if not isinstance(workflows, list):
        return errors + ["golden workflows must be a list"]
    ids = []
    modes = []
    for index, workflow in enumerate(workflows):
        where = "workflow %d" % (index + 1)
        if not isinstance(workflow, dict):
            errors.append("%s must be an object" % where)
            continue
        ident = workflow.get("id")
        mode = workflow.get("mode")
        if not text(ident) or ID_RE.fullmatch(ident) is None:
            errors.append("%s has an invalid id" % where)
        else:
            ids.append(ident)
            where = "workflow %s" % ident
        if mode not in CORE_MODES:
            errors.append("%s has an invalid mode" % where)
        else:
            modes.append(mode)
        allowed = WORKFLOW_COMMON_KEYS | ({"builtin"} if mode == "runtime" else {"command"})
        errors.extend(undeclared_fields(workflow, allowed, where))
        if mode == "runtime":
            if workflow.get("builtin") != "proof-registry":
                errors.append("%s must use builtin proof-registry" % where)
            if "command" in workflow:
                errors.append("%s may not declare a command" % where)
        elif isinstance(mode, str) and mode in COMMAND_SCHEMAS:
            errors.extend(parse_replay_command(workflow, root, where))
        expected_exit = workflow.get("expected_exit")
        if isinstance(expected_exit, bool) or not isinstance(expected_exit, int):
            errors.append("%s expected_exit must be an integer" % where)
        assertions = workflow.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            errors.append("%s assertions must be a non-empty list" % where)
        else:
            for number, assertion in enumerate(assertions, 1):
                if not isinstance(assertion, dict) or not text(assertion.get("path")):
                    errors.append("%s assertion %d is invalid" % (where, number))
                    continue
                errors.extend(undeclared_fields(assertion, ASSERTION_KEYS,
                                                "%s assertion %d" % (where, number)))
                operators = set(assertion) & {"equals", "length"}
                if len(operators) != 1:
                    errors.append("%s assertion %d needs exactly one operator" % (where, number))
                if "length" in assertion:
                    length = assertion["length"]
                    if isinstance(length, bool) or not isinstance(length, int) or length < 0:
                        errors.append("%s assertion %d length must be a non-negative integer"
                                      % (where, number))
    for ident in duplicate_values(ids):
        errors.append("duplicate workflow id %s" % ident)
    if tuple(modes) != CORE_MODES:
        errors.append("golden workflows must name survey, backfill, check, and runtime once in order")
    return errors


def validate_registry(registry, root, workflows, check_evidence=True):
    errors = undeclared_fields(registry, REGISTRY_KEYS, "proof registry")
    if not schema_one(registry.get("schema")):
        errors.append("proof registry schema must be 1")
    levels = registry.get("evidence_levels")
    if not isinstance(levels, list) or tuple(levels) != EVIDENCE_LEVELS:
        errors.append("evidence_levels must match the closed vocabulary in schema order")
    requirements = registry.get("promotion_requirements")
    if not isinstance(requirements, dict):
        requirements = {}
        errors.append("promotion_requirements must be an object")
    if set(requirements) != set(EVIDENCE_LEVELS):
        errors.append("promotion_requirements must name every evidence level exactly once")
    for level in EVIDENCE_LEVELS:
        rule = requirements.get(level)
        expected = [REQUIRED_EVIDENCE[level]]
        if isinstance(rule, dict):
            errors.extend(undeclared_fields(rule, PROMOTION_KEYS,
                                            "promotion requirement %s" % level))
        if rule != {"requires_evidence": expected}:
            errors.append("promotion requirement %s must be %s"
                          % (level, REQUIRED_EVIDENCE[level]))

    if workflows is None:
        workflow_ids = None
    else:
        workflow_errors = validate_workflows(workflows, root)
        errors.extend(workflow_errors)
        workflow_rows = workflows.get("workflows")
        if not isinstance(workflow_rows, list):
            workflow_rows = []
        workflow_ids = set(workflow.get("id") for workflow in workflow_rows
                           if isinstance(workflow, dict) and text(workflow.get("id")))

    claims = registry.get("claims")
    if not isinstance(claims, list) or not claims:
        return {"errors": errors + ["claims must be a non-empty list"], "claims": []}
    ids = []
    modes = []
    for index, claim in enumerate(claims):
        where = "claim %d" % (index + 1)
        if not isinstance(claim, dict):
            errors.append("%s must be an object" % where)
            continue
        ident = claim.get("id")
        if not text(ident) or ID_RE.fullmatch(ident) is None:
            errors.append("%s has an invalid id" % where)
        else:
            ids.append(ident)
            where = "claim %s" % ident
        errors.extend(undeclared_fields(claim, CLAIM_KEYS, where))
        for field in ("claim", "boundary"):
            if not text(claim.get(field)):
                errors.append("%s needs a non-empty %s" % (where, field))
        mode = claim.get("mode")
        if mode not in CORE_MODES:
            errors.append("%s has an invalid mode" % where)
        else:
            modes.append(mode)
        level = claim.get("evidence_level")
        if level not in EVIDENCE_LEVELS:
            errors.append("%s has an invalid evidence_level" % where)
        evidence = claim.get("evidence")
        kinds = set()
        if not isinstance(evidence, list) or not evidence:
            errors.append("%s needs at least one evidence record" % where)
            evidence = []
        for number, item in enumerate(evidence, 1):
            if not isinstance(item, dict):
                errors.append("%s evidence %d must be an object" % (where, number))
                continue
            errors.extend(undeclared_fields(item, EVIDENCE_KEYS,
                                            "%s evidence %d" % (where, number)))
            kind = item.get("kind")
            relative = item.get("path")
            if kind not in EVIDENCE_KINDS:
                errors.append("%s evidence %d has an invalid kind" % (where, number))
            else:
                kinds.add(kind)
            candidate = safe_evidence_path(root, relative)
            if candidate is None:
                errors.append("%s evidence %d path must stay inside the project" % (where, number))
            elif check_evidence and not os.path.exists(candidate):
                errors.append("%s evidence path %s does not exist" % (where, relative))
        required = REQUIRED_EVIDENCE.get(level) if isinstance(level, str) else None
        if required is not None and required not in kinds:
            errors.append("%s cannot use %s without evidence kind %s"
                          % (where, level, required))
        replay_id = claim.get("replay_id")
        if level == "replay-tested" and not text(replay_id):
            errors.append("%s needs replay_id at replay-tested" % where)
        if replay_id is not None and not text(replay_id):
            errors.append("%s replay_id must be a string" % where)
        elif replay_id is not None and workflow_ids is not None and replay_id not in workflow_ids:
            errors.append("%s names unknown replay_id %s" % (where, replay_id))
        if level in ("measured", "adjudicated"):
            for field in ("corpus", "limitations"):
                if not text(claim.get(field)):
                    errors.append("%s needs %s at %s" % (where, field, level))

    for ident in duplicate_values(ids):
        errors.append("duplicate claim id %s" % ident)
    if ids != sorted(ids):
        errors.append("claims must be sorted by id")
    if set(modes) != set(CORE_MODES):
        errors.append("claims must cover survey, backfill, check, and runtime")
    return {"errors": errors, "claims": claims}


def resolve_path(payload, dotted):
    current = payload
    for token in dotted.split("."):
        if not isinstance(current, dict) or token not in current:
            raise KeyError(dotted)
        current = current[token]
    return current


def runtime_payload(root):
    registry_path = os.path.join(root, "skill", "catalog", "proofs.json")
    workflows_path = os.path.join(root, "proof", "replay", "golden-workflows.json")
    try:
        registry = read_json(registry_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {"registry_exists": os.path.isfile(registry_path), "registry_schema": None,
                "workflows_exists": os.path.isfile(workflows_path)}
    return {"registry_exists": True, "registry_schema": registry.get("schema"),
            "workflows_exists": os.path.isfile(workflows_path)}


def signal_process_group(process, member):
    try:
        os.killpg(process.pid, member)
    except ProcessLookupError:
        return
    except OSError:
        try:
            if member == signal.SIGTERM:
                process.terminate()
            else:
                process.kill()
        except OSError:
            return


def close_registered(selector):
    for key in list(selector.get_map().values()):
        try:
            selector.unregister(key.fileobj)
        except (KeyError, ValueError):
            pass
        try:
            key.fileobj.close()
        except OSError:
            pass


def run_bounded(command, cwd, timeout_seconds=REPLAY_TIMEOUT_SECONDS,
                output_limit=MAX_CHILD_OUTPUT_BYTES, environment=None):
    result = {"returncode": 126, "pid": None, "stdout": "", "stderr": "",
              "timed_out": False, "output_exceeded": False, "error": None}
    try:
        process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
    except (OSError, ValueError) as error:
        result["error"] = "could not start child command: %s" % error
        return result

    result["pid"] = process.pid
    stream_names = {process.stdout: "stdout", process.stderr: "stderr"}
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    selector = selectors.DefaultSelector()
    for stream, name in stream_names.items():
        selector.register(stream, selectors.EVENT_READ, name)

    started = time.monotonic()
    deadline = started + max(0, timeout_seconds)
    termination_started = None
    killed = False
    errors = []
    try:
        while (selector.get_map() or process.poll() is None
               or (termination_started is not None and not killed)):
            now = time.monotonic()
            if termination_started is None and now >= deadline:
                result["timed_out"] = True
                errors.append("child command timed out after %s seconds" % timeout_seconds)
                signal_process_group(process, signal.SIGTERM)
                termination_started = now
            if (termination_started is not None and not killed
                    and now - termination_started >= PROCESS_GRACE_SECONDS):
                signal_process_group(process, signal.SIGKILL)
                killed = True
            if termination_started is not None and now - termination_started >= 2:
                signal_process_group(process, signal.SIGKILL)
                close_registered(selector)
                break

            wait = 0.05
            if termination_started is None:
                wait = min(wait, max(0, deadline - now))
            events = selector.select(wait) if selector.get_map() else []
            if not events and not selector.get_map():
                time.sleep(wait)
                continue
            for key, _ in events:
                try:
                    chunk = os.read(key.fileobj.fileno(), READ_CHUNK_BYTES)
                except OSError:
                    chunk = b""
                if not chunk:
                    try:
                        selector.unregister(key.fileobj)
                    except (KeyError, ValueError):
                        pass
                    key.fileobj.close()
                    continue
                name = key.data
                remaining = output_limit - len(buffers[name])
                if remaining > 0:
                    buffers[name].extend(chunk[:remaining])
                if len(chunk) > remaining and not result["output_exceeded"]:
                    result["output_exceeded"] = True
                    errors.append("child output exceeded %d bytes" % output_limit)
                    signal_process_group(process, signal.SIGTERM)
                    termination_started = time.monotonic()
    finally:
        close_registered(selector)
        selector.close()

    if process.poll() is None:
        signal_process_group(process, signal.SIGKILL)
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        signal_process_group(process, signal.SIGKILL)
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            errors.append("child process group did not terminate")
    result["returncode"] = process.returncode if process.returncode is not None else 126

    for name in ("stdout", "stderr"):
        try:
            result[name] = bytes(buffers[name]).decode("utf-8")
        except UnicodeDecodeError:
            result[name] = bytes(buffers[name]).decode("utf-8", errors="replace")
            errors.append("child %s was not valid UTF-8" % name)
    result["error"] = "; ".join(errors) if errors else None
    return result


def bounded_child_error(value):
    compact = " ".join(value.strip().splitlines())
    if len(compact) <= MAX_CHILD_ERROR_TEXT:
        return compact
    return compact[:MAX_CHILD_ERROR_TEXT] + "... [truncated]"


def replay_workflows(data, root):
    results = []
    for workflow in data["workflows"]:
        errors = []
        if workflow["mode"] == "runtime":
            payload = runtime_payload(root)
            actual_exit = 0 if all((payload["registry_exists"],
                                    payload["workflows_exists"],
                                    payload["registry_schema"] == SCHEMA)) else 1
        else:
            environment = dict(os.environ)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            child = run_bounded([sys.executable] + workflow["command"], root,
                                timeout_seconds=REPLAY_TIMEOUT_SECONDS,
                                output_limit=MAX_CHILD_OUTPUT_BYTES, environment=environment)
            actual_exit = child["returncode"]
            if child["error"] is not None:
                payload = None
                errors.append(child["error"])
            else:
                try:
                    payload = json.loads(child["stdout"])
                except (TypeError, ValueError):
                    payload = None
                    errors.append("stdout was not JSON")
            if payload is None and not errors:
                payload = None
                errors.append("stdout was not JSON")
        if actual_exit != workflow["expected_exit"]:
            errors.append("exit was %d, expected %d" % (actual_exit, workflow["expected_exit"]))
        for assertion in workflow["assertions"]:
            try:
                actual = resolve_path(payload, assertion["path"])
            except (KeyError, TypeError):
                errors.append("missing result path %s" % assertion["path"])
                continue
            if "equals" in assertion and actual != assertion["equals"]:
                errors.append("%s did not equal the saved outcome" % assertion["path"])
            if "length" in assertion:
                try:
                    length = len(actual)
                except TypeError:
                    errors.append("%s has no length" % assertion["path"])
                else:
                    if length != assertion["length"]:
                        errors.append("%s length was %d, expected %d"
                                      % (assertion["path"], length, assertion["length"]))
        result = {"id": workflow["id"], "mode": workflow["mode"],
                  "status": "pass" if not errors else "fail",
                  "expected_exit": workflow["expected_exit"], "actual_exit": actual_exit,
                  "assertions": len(workflow["assertions"])}
        if errors:
            result["errors"] = errors
            child_stderr = bounded_child_error(child["stderr"]) if workflow["mode"] != "runtime" else ""
            if child_stderr:
                result["child_stderr"] = child_stderr
        results.append(result)
    return results


def claim_rows(claims):
    rows = []
    for claim in claims:
        row = {"id": claim["id"], "mode": claim["mode"],
               "evidence_level": claim["evidence_level"], "claim": claim["claim"],
               "boundary": claim["boundary"],
               "evidence_paths": [item["path"] for item in claim["evidence"]]}
        for field in ("corpus", "limitations", "replay_id"):
            if field in claim:
                row[field] = claim[field]
        rows.append(row)
    return rows


def render_report(registry, replays, validation=None):
    passed = sum(result["status"] == "pass" for result in replays)
    status = "pass" if passed == len(replays) else "fail"
    levels = [{"id": level, "requires_evidence": [kind]}
              for level, kind in PROMOTION_REQUIREMENTS]
    report = {"schema": SCHEMA, "tool": TOOL, "evidence_levels": levels,
              "claims": claim_rows(registry["claims"]),
              "replay": replays,
              "summary": {"status": status, "claims": len(registry["claims"]),
                          "evidence_levels": len(EVIDENCE_LEVELS), "replays": len(replays),
                          "replays_passed": passed}}
    if validation is not None:
        report["validation"] = validation
    return report


def render_text(report):
    lines = ["docdna proof registry %d" % report["schema"],
             "  %-10s: %d" % ("claims", report["summary"]["claims"]),
             "  %-10s: %d of %d passed" % ("replays", report["summary"]["replays_passed"],
                                            report["summary"]["replays"]),
             "", "evidence levels"]
    if "validation" in report:
        lines[2] = "  %-10s: skipped" % "replays"
        lines.insert(3, "  %-10s: %s" % ("validation", report["validation"]["mode"]))
        lines.insert(4, "  %-10s: %s" % ("boundary", report["validation"]["boundary"]))
    for level in report["evidence_levels"]:
        lines.append("  %-34s %s" % (level["id"], ", ".join(level["requires_evidence"])))
    lines.append("")
    lines.append("claim matrix")
    lines.append("  id | evidence level | mode | claim | boundary")
    for claim in report["claims"]:
        lines.append("  %s | %s | %s | %s | %s"
                     % (claim["id"], claim["evidence_level"], claim["mode"], claim["claim"],
                        claim["boundary"]))
    lines.extend(("", "golden replay"))
    for replay in report["replay"]:
        lines.append("  %-34s %-8s %s" % (replay["id"], replay["mode"], replay["status"]))
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate and display DocDNA product claim proofs.")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--registry", default=REGISTRY_PATH,
                        help="proof registry to validate")
    parser.add_argument("--workflows", default=WORKFLOWS_PATH,
                        help="golden workflows to replay")
    parser.add_argument("--root", default=PROJECT_ROOT,
                        help="project root for evidence and replay paths")
    args = parser.parse_args(argv)

    try:
        registry = read_json(os.path.abspath(args.registry))
        workflows = (read_json(os.path.abspath(args.workflows))
                     if args.workflows is not None else None)
        portable = workflows is None
        validation = validate_registry(registry, os.path.abspath(args.root), workflows,
                                       check_evidence=not portable)
    except (OSError, ValueError, TypeError, RecursionError) as error:
        sys.stderr.write("docdna_proof: %s\n" % error)
        return 2
    if validation["errors"]:
        for error in validation["errors"]:
            sys.stderr.write("docdna_proof: %s\n" % error)
        return 2

    replays = replay_workflows(workflows, os.path.abspath(args.root)) if workflows is not None else []
    boundary = {"mode": "installed-registry", "boundary": INSTALLED_BOUNDARY} if portable else None
    report = render_report(registry, replays, boundary)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        sys.stdout.write(render_text(report))
    return 0 if report["summary"]["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
