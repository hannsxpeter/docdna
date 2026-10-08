#!/usr/bin/env python3
"""Validate and render docdna product claim evidence."""

import argparse
import errno
import json
import os
import selectors
import signal
import stat
import subprocess
import sys
import time


# The shared validator lives beside this script. Importing it must not leave bytecode in an
# installed skill directory, which this command promises not to modify.
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from docdna_fs import bind_root
from docdna_runtime import (INSTALLED_PROOF_BOUNDARY, PROOF_LEVELS, PROOF_PROMOTIONS,
                            validate_proof_contract)


SCHEMA = 1
TOOL = "docdna_proof"

SKILL_ROOT = os.path.normpath(os.path.join(HERE, ".."))
CHECKOUT_ROOT = os.path.normpath(os.path.join(SKILL_ROOT, ".."))
CHECKOUT_LAYOUT = (os.path.basename(SKILL_ROOT) == "skill"
                   and os.path.isfile(os.path.join(CHECKOUT_ROOT, "install.sh")))
PROJECT_ROOT = CHECKOUT_ROOT if CHECKOUT_LAYOUT else SKILL_ROOT
REGISTRY_PATH = os.path.join(SKILL_ROOT, "catalog", "proofs.json")
WORKFLOWS_PATH = (os.path.join(CHECKOUT_ROOT, "proof", "replay", "golden-workflows.json")
                  if CHECKOUT_LAYOUT else None)

REPLAY_TIMEOUT_SECONDS = 30
MAX_CONTROL_BYTES = 1024 * 1024
MAX_CHILD_OUTPUT_BYTES = 256 * 1024
MAX_CHILD_ERROR_TEXT = 2000
READ_CHUNK_BYTES = 64 * 1024
PROCESS_GRACE_SECONDS = 0.25


def control_signature(details):
    return (details.st_dev, details.st_ino, details.st_size, details.st_mtime_ns)


def read_control(path, max_bytes=MAX_CONTROL_BYTES):
    path_details = os.lstat(path)
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


def validate_registry(registry, root, workflows):
    """Validate proof data with the shared runtime contract.

    With golden workflows, the project root is bound and every evidence, script, and operand
    path is inspected below it without following a symlink. Without them, as in an installed
    skill, only the registry structure and lexical path safety are checked.
    """
    if workflows is None:
        return validate_proof_contract(registry)
    checkout_root = bind_root(os.path.abspath(root))
    try:
        return validate_proof_contract(registry, workflows, checkout_root)
    finally:
        checkout_root.close()


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
    except (OSError, ValueError):
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
              for level, kind in PROOF_PROMOTIONS]
    report = {"schema": SCHEMA, "tool": TOOL, "evidence_levels": levels,
              "claims": claim_rows(registry["claims"]),
              "replay": replays,
              "summary": {"status": status, "claims": len(registry["claims"]),
                          "evidence_levels": len(PROOF_LEVELS), "replays": len(replays),
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
    parser = argparse.ArgumentParser(description="Validate and display docdna product claim proofs.")
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
        validation = validate_registry(registry, args.root, workflows)
    except (OSError, ValueError, TypeError, RecursionError) as error:
        sys.stderr.write("docdna_proof: %s\n" % error)
        return 2
    if validation["errors"]:
        for error in validation["errors"]:
            sys.stderr.write("docdna_proof: %s\n" % error)
        return 2

    replays = replay_workflows(workflows, os.path.abspath(args.root)) if workflows is not None else []
    boundary = ({"mode": "installed-registry", "boundary": INSTALLED_PROOF_BOUNDARY}
                if portable else None)
    report = render_report(registry, replays, boundary)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        sys.stdout.write(render_text(report))
    return 0 if report["summary"]["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
