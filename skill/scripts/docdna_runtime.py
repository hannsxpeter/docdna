#!/usr/bin/env python3
"""Load and validate the shared DocDNA runtime registry.

Implements: P-MUST-03
"""

import os
import re
import stat
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from docdna_fs import (FileTooLarge, RepositoryRoot, bind_root, open_root, parse_json,
                       read_text)


SCHEMA = 1
REGISTRY_PATH = "catalog/runtimes.json"
MAX_REGISTRY_BYTES = 1024 * 1024
MAX_MEMBER_BYTES = 5 * 1024 * 1024
ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")

ROOT_FIELDS = frozenset(("schema", "minimum_python", "platform_support", "host_targets",
                         "wiring_surfaces", "runtime_members", "registries", "templates",
                         "references", "smoke_checks"))
PLATFORM_FIELDS = frozenset(("family", "support_level", "requirements"))
HOST_FIELDS = frozenset(("id", "label", "support_level", "install", "wiring",
                         "host_parity"))
INSTALL_FIELDS = frozenset(("support", "selector", "default_location"))
WIRING_FIELDS = frozenset(("support", "surfaces"))
PARITY_FIELDS = frozenset(("status", "boundary"))
SURFACE_FIELDS = frozenset(("id", "paths"))
MEMBER_FIELDS = frozenset(("id", "kind", "path"))
RESOURCE_FIELDS = frozenset(("id", "path"))
SMOKE_FIELDS = frozenset(("id", "kind", "target", "checkout_target"))

SMOKE_KINDS = {
    "runtime-registry": "registry",
    "python-compatibility": "python",
    "runtime-members": "members",
    "proof-registry": "proof-installed-registry",
}

PROOF_PROMOTIONS = (
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
PROOF_LEVELS = tuple(item[0] for item in PROOF_PROMOTIONS)
PROOF_KINDS = tuple(item[1] for item in PROOF_PROMOTIONS)
PROOF_REQUIRED = dict(PROOF_PROMOTIONS)
PROOF_MODES = ("survey", "backfill", "check", "runtime")
PROOF_REGISTRY_FIELDS = frozenset(("schema", "evidence_levels", "promotion_requirements",
                                   "claims"))
PROOF_PROMOTION_FIELDS = frozenset(("requires_evidence",))
PROOF_CLAIM_FIELDS = frozenset(("id", "mode", "claim", "evidence_level", "boundary",
                                "evidence", "corpus", "limitations", "replay_id"))
PROOF_EVIDENCE_FIELDS = frozenset(("kind", "path"))
WORKFLOW_ROOT_FIELDS = frozenset(("schema", "workflows"))
WORKFLOW_FIELDS = frozenset(("id", "mode", "expected_exit", "assertions"))
WORKFLOW_ASSERTION_FIELDS = frozenset(("path", "equals", "length"))
WORKFLOW_COMMANDS = {
    "survey": {"script": "skill/scripts/docdna_scan.py", "flags": {"--json": None}},
    "backfill": {"script": "skill/scripts/docdna_backfill.py",
                 "flags": {"--json": None, "--verify": "repo-path"}},
    "check": {"script": "skill/scripts/docdna_check.py",
              "flags": {"--json": None, "--no-write": None,
                        "--fail-on": ("never",)}},
}
INSTALLED_PROOF_BOUNDARY = (
    "installed validation checks registry schema and promotion structure only; "
    "checkout-only evidence paths and golden replays are not shipped or revalidated")


class RuntimeRegistryError(ValueError):
    """The runtime registry is malformed or cannot be read safely."""


def _error(message):
    raise RuntimeRegistryError(message)


def _object(value, where, fields):
    if not isinstance(value, dict):
        _error("%s must be an object" % where)
    extras = sorted(set(value) - fields)
    if extras:
        _error("%s has undeclared field %s" % (where, extras[0]))
    return value


def _string(value, where):
    if not isinstance(value, str) or not value.strip():
        _error("%s must be a non-empty string" % where)
    return value


def _identifier(value, where):
    value = _string(value, where)
    if ID_RE.fullmatch(value) is None:
        _error("%s must be a lowercase dotted identifier" % where)
    return value


def _array(value, where):
    if not isinstance(value, list):
        _error("%s must be an array" % where)
    return value


def _string_array(value, where, allow_empty=False):
    rows = _array(value, where)
    if not allow_empty and not rows:
        _error("%s must not be empty" % where)
    for index, row in enumerate(rows, 1):
        _string(row, "%s item %d" % (where, index))
    if len(rows) != len(set(rows)):
        _error("%s contains a duplicate" % where)
    return rows


def _safe_path(value, where):
    value = _string(value, where)
    if (os.path.isabs(value) or "\\" in value or "\x00" in value
            or value == "." or value == ".."):
        _error("%s must be a safe relative path" % where)
    normalized = os.path.normpath(value)
    if normalized != value or normalized.startswith(".." + os.sep):
        _error("%s must be a safe relative path" % where)
    return value


def _first_duplicate(values):
    seen = set()
    for value in values:
        if value in seen:
            return value
        seen.add(value)
    return None


def _duplicates(values):
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        else:
            seen.add(value)
    return sorted(duplicates)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _schema_one(value):
    return type(value) is int and value == 1


def _undeclared(value, allowed, where):
    return ["%s has undeclared field %s" % (where, field)
            for field in sorted(set(value) - allowed)]


def inspect_bound_path(root, relative):
    """Return file, directory, other, or None without following any symlink."""
    relative = _safe_path(relative, "proof path")
    parts = relative.split(os.sep)
    descriptor = open_root(root)
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        for part in parts[:-1]:
            try:
                before = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                return None
            except OSError as error:
                raise RuntimeRegistryError("unsafe proof path %s: %s" % (relative, error))
            if stat.S_ISLNK(before.st_mode):
                raise RuntimeRegistryError("proof path %s refuses symlink component %s"
                                           % (relative, part))
            if not stat.S_ISDIR(before.st_mode):
                return None
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except OSError as error:
                raise RuntimeRegistryError("unsafe proof path %s: %s" % (relative, error))
            after = os.fstat(child)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                os.close(child)
                raise RuntimeRegistryError("proof path %s changed while opening" % relative)
            os.close(descriptor)
            descriptor = child
        try:
            details = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise RuntimeRegistryError("unsafe proof path %s: %s" % (relative, error))
        if stat.S_ISLNK(details.st_mode):
            raise RuntimeRegistryError("proof path %s refuses symlink" % relative)
        if stat.S_ISREG(details.st_mode):
            return "file"
        if stat.S_ISDIR(details.st_mode):
            return "directory"
        return "other"
    finally:
        os.close(descriptor)


def _workflow_command_errors(workflow, checkout_root, where):
    errors = []
    mode = workflow.get("mode")
    schema = WORKFLOW_COMMANDS.get(mode)
    if schema is None:
        return errors
    command = workflow.get("command")
    if (not isinstance(command, list) or not command
            or not all(_text(argument) for argument in command)):
        return ["%s command must be a non-empty string list" % where]

    script = command[0]
    if script != schema["script"]:
        errors.append("%s command must use %s" % (where, schema["script"]))
    else:
        try:
            script_kind = inspect_bound_path(checkout_root, script)
        except RuntimeRegistryError as error:
            errors.append("%s command script %s" % (where, error))
        else:
            if script_kind != "file":
                errors.append("%s command script %s does not exist" % (where, script))

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
    repo = None
    if len(operands) != 1:
        errors.append("%s command needs exactly one repository operand" % where)
    else:
        repo = operands[0]
        try:
            repo_kind = inspect_bound_path(checkout_root, repo)
        except RuntimeRegistryError as error:
            errors.append("%s operand %s" % (where, error))
        else:
            if repo_kind != "directory":
                errors.append("%s operand %s is not a repository directory" % (where, repo))

    for flag, value_schema in schema["flags"].items():
        if flag not in seen or value_schema is None:
            continue
        value = seen[flag]
        if value_schema == "repo-path":
            if repo is None:
                continue
            try:
                combined = os.path.normpath(os.path.join(repo, value))
                if combined != os.path.join(repo, value):
                    raise RuntimeRegistryError("proof path must be normalized")
                value_kind = inspect_bound_path(checkout_root, combined)
            except RuntimeRegistryError as error:
                errors.append("%s flag %s path %s is unsafe: %s"
                              % (where, flag, value, error))
            else:
                if value_kind != "file":
                    errors.append("%s flag %s path %s does not exist" % (where, flag, value))
        elif value not in value_schema:
            errors.append("%s flag %s value must be %s"
                          % (where, flag, ", ".join(value_schema)))
    return errors


def _validate_workflows(workflows, checkout_root):
    errors = _undeclared(workflows, WORKFLOW_ROOT_FIELDS, "golden workflows")
    if not _schema_one(workflows.get("schema")):
        errors.append("golden workflows schema must be 1")
    rows = workflows.get("workflows")
    if not isinstance(rows, list):
        return errors + ["golden workflows must be a list"], set()
    ids = []
    modes = []
    for index, workflow in enumerate(rows, 1):
        where = "workflow %d" % index
        if not isinstance(workflow, dict):
            errors.append("%s must be an object" % where)
            continue
        ident = workflow.get("id")
        mode = workflow.get("mode")
        if not _text(ident) or ID_RE.fullmatch(ident) is None:
            errors.append("%s has an invalid id" % where)
        else:
            ids.append(ident)
            where = "workflow %s" % ident
        if mode not in PROOF_MODES:
            errors.append("%s has an invalid mode" % where)
        else:
            modes.append(mode)
        allowed = WORKFLOW_FIELDS | ({"builtin"} if mode == "runtime" else {"command"})
        errors.extend(_undeclared(workflow, allowed, where))
        if mode == "runtime":
            if workflow.get("builtin") != "proof-registry":
                errors.append("%s must use builtin proof-registry" % where)
            if "command" in workflow:
                errors.append("%s may not declare a command" % where)
        elif isinstance(mode, str) and mode in WORKFLOW_COMMANDS:
            errors.extend(_workflow_command_errors(workflow, checkout_root, where))
        expected_exit = workflow.get("expected_exit")
        if isinstance(expected_exit, bool) or not isinstance(expected_exit, int):
            errors.append("%s expected_exit must be an integer" % where)
        assertions = workflow.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            errors.append("%s assertions must be a non-empty list" % where)
        else:
            for number, assertion in enumerate(assertions, 1):
                label = "%s assertion %d" % (where, number)
                if not isinstance(assertion, dict) or not _text(assertion.get("path")):
                    errors.append("%s is invalid" % label)
                    continue
                errors.extend(_undeclared(assertion, WORKFLOW_ASSERTION_FIELDS, label))
                operators = set(assertion) & {"equals", "length"}
                if len(operators) != 1:
                    errors.append("%s needs exactly one operator" % label)
                if "length" in assertion:
                    length = assertion["length"]
                    if isinstance(length, bool) or not isinstance(length, int) or length < 0:
                        errors.append("%s length must be a non-negative integer" % label)
    for ident in _duplicates(ids):
        errors.append("duplicate workflow id %s" % ident)
    if tuple(modes) != PROOF_MODES:
        errors.append(
            "golden workflows must name survey, backfill, check, and runtime once in order")
    return errors, set(ids)


def validate_proof_contract(registry, workflows=None, checkout_root=None):
    """Validate proof data without importing or executing any registered command."""
    errors = _undeclared(registry, PROOF_REGISTRY_FIELDS, "proof registry")
    if not _schema_one(registry.get("schema")):
        errors.append("proof registry schema must be 1")
    levels = registry.get("evidence_levels")
    if not isinstance(levels, list) or tuple(levels) != PROOF_LEVELS:
        errors.append("evidence_levels must match the closed vocabulary in schema order")
    promotions = registry.get("promotion_requirements")
    if not isinstance(promotions, dict):
        promotions = {}
        errors.append("promotion_requirements must be an object")
    if set(promotions) != set(PROOF_LEVELS):
        errors.append("promotion_requirements must name every evidence level exactly once")
    for level in PROOF_LEVELS:
        rule = promotions.get(level)
        if isinstance(rule, dict):
            errors.extend(_undeclared(rule, PROOF_PROMOTION_FIELDS,
                                      "promotion requirement %s" % level))
        if rule != {"requires_evidence": [PROOF_REQUIRED[level]]}:
            errors.append("promotion requirement %s must be %s"
                          % (level, PROOF_REQUIRED[level]))

    workflow_ids = None
    if workflows is not None:
        if checkout_root is None or not isinstance(checkout_root, RepositoryRoot):
            raise RuntimeRegistryError("checkout proof validation requires a bound root")
        workflow_errors, workflow_ids = _validate_workflows(workflows, checkout_root)
        errors.extend(workflow_errors)

    claims = registry.get("claims")
    if not isinstance(claims, list) or not claims:
        return {"errors": errors + ["claims must be a non-empty list"], "claims": []}
    ids = []
    modes = []
    for index, claim in enumerate(claims, 1):
        where = "claim %d" % index
        if not isinstance(claim, dict):
            errors.append("%s must be an object" % where)
            continue
        ident = claim.get("id")
        if not _text(ident) or ID_RE.fullmatch(ident) is None:
            errors.append("%s has an invalid id" % where)
        else:
            ids.append(ident)
            where = "claim %s" % ident
        errors.extend(_undeclared(claim, PROOF_CLAIM_FIELDS, where))
        for field in ("claim", "boundary"):
            if not _text(claim.get(field)):
                errors.append("%s needs a non-empty %s" % (where, field))
        mode = claim.get("mode")
        if mode not in PROOF_MODES:
            errors.append("%s has an invalid mode" % where)
        else:
            modes.append(mode)
        level = claim.get("evidence_level")
        if level not in PROOF_LEVELS:
            errors.append("%s has an invalid evidence_level" % where)
        evidence = claim.get("evidence")
        kinds = set()
        if not isinstance(evidence, list) or not evidence:
            errors.append("%s needs at least one evidence record" % where)
            evidence = []
        for number, item in enumerate(evidence, 1):
            label = "%s evidence %d" % (where, number)
            if not isinstance(item, dict):
                errors.append("%s must be an object" % label)
                continue
            errors.extend(_undeclared(item, PROOF_EVIDENCE_FIELDS, label))
            kind = item.get("kind")
            relative = item.get("path")
            if kind not in PROOF_KINDS:
                errors.append("%s has an invalid kind" % label)
            else:
                kinds.add(kind)
            try:
                _safe_path(relative, "%s path" % label)
                state = (inspect_bound_path(checkout_root, relative)
                         if checkout_root is not None else None)
            except RuntimeRegistryError as error:
                errors.append("%s %s" % (label, error))
            else:
                if checkout_root is not None and state not in ("file", "directory"):
                    errors.append("%s path %s does not exist" % (where, relative))
        required = PROOF_REQUIRED.get(level) if isinstance(level, str) else None
        if required is not None and required not in kinds:
            errors.append("%s cannot use %s without evidence kind %s"
                          % (where, level, required))
        replay_id = claim.get("replay_id")
        if level == "replay-tested" and not _text(replay_id):
            errors.append("%s needs replay_id at replay-tested" % where)
        if replay_id is not None and not _text(replay_id):
            errors.append("%s replay_id must be a string" % where)
        elif replay_id is not None and workflow_ids is not None and replay_id not in workflow_ids:
            errors.append("%s names unknown replay_id %s" % (where, replay_id))
        if level in ("measured", "adjudicated"):
            for field in ("corpus", "limitations"):
                if not _text(claim.get(field)):
                    errors.append("%s needs %s at %s" % (where, field, level))
    for ident in _duplicates(ids):
        errors.append("duplicate claim id %s" % ident)
    if ids != sorted(ids):
        errors.append("claims must be sorted by id")
    if set(modes) != set(PROOF_MODES):
        errors.append("claims must cover survey, backfill, check, and runtime")
    return {"errors": errors, "claims": claims}


def _unique_sorted(rows, where, key):
    values = [row[key] for row in rows]
    duplicate = _first_duplicate(values)
    if duplicate is not None:
        _error("duplicate %s %s %s" % (where, key, duplicate))
    if values != sorted(values):
        _error("%s must be sorted by %s" % (where, key))


def _validate_platform(value):
    value = _object(value, "platform_support", PLATFORM_FIELDS)
    if value.get("family") != "posix":
        _error("platform_support family must be posix")
    if value.get("support_level") != "supported":
        _error("platform_support support_level must be supported")
    _string_array(value.get("requirements"), "platform_support requirements")


def _validate_surfaces(rows):
    rows = _array(rows, "wiring_surfaces")
    for index, row in enumerate(rows, 1):
        where = "wiring surface %d" % index
        row = _object(row, where, SURFACE_FIELDS)
        _identifier(row.get("id"), "%s id" % where)
        paths = _string_array(row.get("paths"), "%s paths" % where)
        for number, path in enumerate(paths, 1):
            _safe_path(path, "%s path %d" % (where, number))
    _unique_sorted(rows, "wiring surfaces", "id")
    return set(row["id"] for row in rows)


def _validate_hosts(rows, surface_ids):
    rows = _array(rows, "host_targets")
    selectors = []
    for index, row in enumerate(rows, 1):
        where = "host target %d" % index
        row = _object(row, where, HOST_FIELDS)
        _identifier(row.get("id"), "%s id" % where)
        _string(row.get("label"), "%s label" % where)

        install = _object(row.get("install"), "%s install" % where, INSTALL_FIELDS)
        install_support = install.get("support")
        if install_support not in ("supported", "not-supported"):
            _error("%s install support is invalid" % where)
        if install_support == "supported":
            selectors.append(_identifier(install.get("selector"), "%s install selector" % where))
            _string(install.get("default_location"), "%s install default_location" % where)
        elif install.get("selector") is not None or install.get("default_location") is not None:
            _error("%s unsupported install must use null selector and location" % where)

        wiring = _object(row.get("wiring"), "%s wiring" % where, WIRING_FIELDS)
        if wiring.get("support") not in ("supported", "not-supported"):
            _error("%s wiring support is invalid" % where)
        surfaces = _string_array(wiring.get("surfaces"), "%s wiring surfaces" % where,
                                 allow_empty=wiring.get("support") == "not-supported")
        if wiring.get("support") == "supported" and not surfaces:
            _error("%s supported wiring needs a surface" % where)
        if wiring.get("support") == "not-supported" and surfaces:
            _error("%s unsupported wiring cannot name a surface" % where)
        unknown = sorted(set(surfaces) - surface_ids)
        if unknown:
            _error("%s names unknown wiring surface %s" % (where, unknown[0]))

        support_pair = (install_support, wiring.get("support"))
        levels = {("supported", "supported"): "install-and-wiring",
                  ("supported", "not-supported"): "install-only",
                  ("not-supported", "supported"): "wiring-only"}
        if support_pair not in levels:
            _error("%s must declare install support, wiring support, or both" % where)
        expected_level = levels[support_pair]
        if row.get("support_level") != expected_level:
            _error("%s support_level must be %s" % (where, expected_level))

        parity = _object(row.get("host_parity"), "%s host_parity" % where, PARITY_FIELDS)
        if parity.get("status") != "not-verified":
            _error("%s host parity status must be not-verified" % where)
        boundary = _string(parity.get("boundary"), "%s host parity boundary" % where)
        if "host parity" not in boundary:
            _error("%s host parity boundary must state its limit" % where)
    _unique_sorted(rows, "host targets", "id")
    if len(selectors) != len(set(selectors)):
        _error("host targets contain a duplicate install selector")


def _validate_members(rows):
    rows = _array(rows, "runtime_members")
    for index, row in enumerate(rows, 1):
        where = "runtime member %d" % index
        row = _object(row, where, MEMBER_FIELDS)
        _identifier(row.get("id"), "%s id" % where)
        if row.get("kind") not in ("command", "module"):
            _error("%s kind is invalid" % where)
        path = _safe_path(row.get("path"), "%s path" % where)
        if not path.startswith("scripts/docdna_") or not path.endswith(".py"):
            _error("%s path must name a DocDNA Python script" % where)
    _unique_sorted(rows, "runtime members", "path")
    ids = [row["id"] for row in rows]
    duplicate = _first_duplicate(ids)
    if duplicate is not None:
        _error("duplicate runtime member id %s" % duplicate)


def _validate_resources(rows, name, prefix, suffix):
    rows = _array(rows, name)
    for index, row in enumerate(rows, 1):
        where = "%s item %d" % (name, index)
        row = _object(row, where, RESOURCE_FIELDS)
        _identifier(row.get("id"), "%s id" % where)
        path = _safe_path(row.get("path"), "%s path" % where)
        if not path.startswith(prefix) or not path.endswith(suffix):
            _error("%s path must stay under %s and end in %s" % (where, prefix, suffix))
    _unique_sorted(rows, name, "path")
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        _error("%s contains a duplicate id" % name)


def _validate_smoke_checks(rows, registry):
    rows = _array(rows, "smoke_checks")
    ids = []
    registry_ids = set(row["id"] for row in registry["registries"])
    for index, row in enumerate(rows, 1):
        where = "smoke check %d" % index
        row = _object(row, where, SMOKE_FIELDS)
        ident = _identifier(row.get("id"), "%s id" % where)
        ids.append(ident)
        if SMOKE_KINDS.get(ident) != row.get("kind"):
            _error("%s kind does not match check id %s" % (where, ident))
        target = _string(row.get("target"), "%s target" % where)
        if ident in ("runtime-registry", "proof-registry") and target not in registry_ids:
            _error("%s names unknown registry %s" % (where, target))
        if ident == "python-compatibility" and target != "minimum_python":
            _error("%s must target minimum_python" % where)
        if ident == "runtime-members" and target != "runtime_members":
            _error("%s must target runtime_members" % where)
        if ident == "proof-registry":
            _safe_path(row.get("checkout_target"), "%s checkout_target" % where)
        elif "checkout_target" in row:
            _error("%s may not declare checkout_target" % where)
    if ids != list(SMOKE_KINDS):
        _error("smoke_checks must name the four required checks in stable order")


def validate_registry(registry):
    """Validate a decoded registry and return it unchanged."""
    registry = _object(registry, "runtime registry", ROOT_FIELDS)
    if type(registry.get("schema")) is not int or registry.get("schema") != SCHEMA:
        _error("runtime registry schema must be %d" % SCHEMA)
    minimum = registry.get("minimum_python")
    if (not isinstance(minimum, list) or len(minimum) != 2
            or any(type(part) is not int or part < 0 for part in minimum)
            or minimum != [3, 8]):
        _error("minimum_python must be [3, 8]")
    _validate_platform(registry.get("platform_support"))
    surface_ids = _validate_surfaces(registry.get("wiring_surfaces"))
    _validate_hosts(registry.get("host_targets"), surface_ids)
    _validate_members(registry.get("runtime_members"))
    _validate_resources(registry.get("registries"), "registries", "catalog/", ".json")
    _validate_resources(registry.get("templates"), "templates", "templates/", ".md")
    _validate_resources(registry.get("references"), "references", "references/", ".md")
    _validate_smoke_checks(registry.get("smoke_checks"), registry)
    return registry


def load_registry(skill_root, registry_path=REGISTRY_PATH):
    """Read a bounded registry below a bound skill root and validate it."""
    owns_root = False
    try:
        registry_path = _safe_path(registry_path, "runtime registry path")
        if isinstance(skill_root, RepositoryRoot):
            root = skill_root
        else:
            try:
                root = bind_root(os.path.abspath(skill_root))
                owns_root = True
            except (OSError, ValueError):
                raise RuntimeRegistryError("unsafe runtime skill root")
        try:
            raw = read_text(root, registry_path, max_bytes=MAX_REGISTRY_BYTES)
        finally:
            if owns_root:
                root.close()
        return validate_registry(parse_json(raw, registry_path))
    except FileTooLarge as error:
        raise RuntimeRegistryError("runtime registry %s exceeds %d bytes (found %d)"
                                   % (registry_path, MAX_REGISTRY_BYTES, error.size))
    except RuntimeRegistryError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise RuntimeRegistryError("unsafe or invalid runtime registry %s: %s"
                                   % (registry_path, error))


def command_paths(registry):
    """Return command paths in registry order."""
    return [row["path"] for row in registry["runtime_members"] if row["kind"] == "command"]


def install_targets(registry):
    """Return only installer selectors with declared install support."""
    return [row["install"]["selector"] for row in registry["host_targets"]
            if row["install"]["support"] == "supported"]


def wiring_target_ids(registry):
    """Return registry-owned wiring target identifiers."""
    return [row["id"] for row in registry["wiring_surfaces"]]
