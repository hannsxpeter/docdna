#!/usr/bin/env python3
"""Turn a docdna scan plus the catalog into .docdna/manifest.json and DOCDNA.md."""

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone

SCHEMA = 1
TOOL = "docdna_select"
VERSION = "1.2.1"

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from docdna_fs import (FileTooLarge, MAX_CONTROL_BYTES,
                       bind_root as safe_bind_root, file_size as safe_file_size,
                       control_file_exists as safe_control_file_exists,
                       is_dir as safe_is_dir,
                       is_file as safe_is_file, listdir as safe_listdir,
                       open_root as safe_open_root,
                       parse_json as safe_parse_json,
                       path_stat as safe_path_stat,
                       path_exists as safe_exists, read_bounded_path as safe_read_bounded_path,
                       read_text as safe_read_text,
                       require_config as safe_require_config,
                       require_manifest as safe_require_manifest,
                       require_root_identity as safe_require_root_identity,
                       require_scan as safe_require_scan,
                       root_is_current as safe_root_is_current,
                       write_text as safe_write_text)
from docdna_unicode import clean_generated_text

CATALOG_DIR = os.path.normpath(os.path.join(HERE, "..", "catalog"))
TEMPLATE_DIR = os.path.normpath(os.path.join(HERE, "..", "templates"))
SCAN_SCRIPT = os.path.join(HERE, "docdna_scan.py")

MANIFEST_REL = os.path.join(".docdna", "manifest.json")
CONFIG_REL = os.path.join(".docdna", "config.json")
REPORT_REL = "DOCDNA.md"

CATALOG_FILES = [("signals", "signals.json", "signals"),
                 ("documents", "documents.json", "documents"),
                 ("rules", "rules.json", "rules"),
                 ("archetypes", "archetypes.json", None),
                 ("interview", "interview.json", "questions")]

STAGES = ("frame", "decide", "design", "build", "verify", "assure", "operate", "serve",
          "govern", "retire")
DURABILITIES = ("durable", "evidence", "transient")
SCOPES = ("repo", "product", "org")
PRODUCIBLES = ("Y", "M", "R")
BACKFILLABILITIES = ("H", "P", "N")
SENSITIVITIES = ("public", "internal", "restricted")
CADENCE_WORDS = ("none", "on-release", "on-change")
CADENCE_ISO = re.compile(r"^P(?=\w)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+S)?)?$")
SIGNAL_STATES = ("present", "absent", "unknown", "hint")
DOC_STATES = ("absent", "present-fresh", "present-drifted", "present-stub", "present-elsewhere")

HINT_MAX_STATE = "hint"
HINT_PROBE_PIN = ("hint", "absent")
HINT_RULE = "A hint may open a question, it may never set a verdict."

VERDICT_RANK = {"not-applicable": 0, "optional": 1, "recommended": 2, "required": 3}
EFFECT_VERDICT = {"require": "required", "recommend": "recommended",
                  "optionalize": "optional", "exclude": "not-applicable"}
SOFT_EFFECTS = ("ask", "note")
LAYER_RANK = {"baseline": 0, "signal": 10, "overlay": 20, "answer": 30, "override": 40}
WRITE_STATUS = ("pending", "in-progress", "written", "verified", "failed")

ACTIONS = {
    ("required", "absent"): "write",
    ("required", "present-fresh"): "adopt",
    ("required", "present-drifted"): "refresh",
    ("required", "present-stub"): "complete",
    ("required", "present-elsewhere"): "confirm",
    ("recommended", "absent"): "offer",
    ("recommended", "present-fresh"): "adopt",
    ("recommended", "present-drifted"): "refresh",
    ("recommended", "present-stub"): "complete",
    ("recommended", "present-elsewhere"): "confirm",
    ("optional", "absent"): "note",
    ("optional", "present-fresh"): "adopt",
    ("optional", "present-drifted"): "note",
    ("optional", "present-stub"): "note",
    ("optional", "present-elsewhere"): "note",
    ("not-applicable", "absent"): "skip",
    ("not-applicable", "present-fresh"): "orphan",
    ("not-applicable", "present-drifted"): "orphan",
    ("not-applicable", "present-stub"): "orphan",
    ("not-applicable", "present-elsewhere"): "skip",
}

SPINE_HOPS = [("delivery", "req", "tc"), ("assurance", "ctl", "evidence"),
              ("abuse", "thr", "tc")]
SPINE_REASON = "no @covers annotations found in the scanned tree; coverage is never estimated"

STUB_BYTES = 400
NEAR_MISS = 1
FAR = 99
MAX_STALE_ROWS = 3
MAX_MISSING_ROWS = 3
MAX_ROW_LINES = 1
MAX_ORPHAN_ROWS = 2
MAX_OPEN_ROWS = 2
MAX_OPEN_EVIDENCE = 3
MAX_TRIPWIRE_ROWS = 1
MAX_TRIPWIRE_TERMS = 2
MAX_ASSUMED_SHOWN = 3
LINE_WIDTH = 100
LABEL_WIDTH = 16
ROW_WIDTH = 22
DIAL_LIMIT = 1

BOUNDARY = ("I only see documentation committed to this repo. If your docs live in Confluence, "
            "SharePoint, or Notion, say so and I will mark those rows present-elsewhere rather "
            "than missing.")

# There is no WRONG NOW section, and the heading is retired rather than left standing for a later
# kind to fill. Its whole value was that a reader could act on every row in it without checking the
# row first, and no drift kind earns that. Both passes were hand adjudicated in full, none sampled,
# but not on the same corpus and the two must not be merged: command-not-found came out at 1 true
# positive of 31 across 51 repositories, with all 27 rows it had reported "high" wrong, while
# path-not-found came out at 5 of 46 on an earlier five-repository holdout, which is the only
# adjudication the path pass has. 28 of the 30 command false positives were documents making no
# claim about the repository they sit in: comparison tables with metasyntactic placeholders, task
# templates, case studies about other repositories, one hypothetical drift example inside an
# instruction about detecting drift. The recall is no better:
# across 77 documented commands in 5 maintained repositories, not one named a missing script, so
# the defect this pass hunts has a base rate near zero. Both passes are leads. Every row is still
# counted, still shown, and still complete in the manifest, under one subordinate section that says
# in plain words what a reader is meant to do with it.
PATH_KIND = "path-not-found"
COMMAND_KIND = "command-not-found"
LEAD_LABEL = "Leads"
STALE_TITLE = "POSSIBLE STALE REFERENCES"
STALE_PATH_NOTE = ("A document may name a path for a reason other than asserting it exists right "
                   "now: an install target, a changelog entry, a fix still to apply.")
STALE_COMMAND_NOTE = ("A document may name a command without claiming this repository runs it: a "
                      "comparison table, a task template, a case study about another repository.")
STALE_READ_NOTE = "These are leads for a human to read, not findings."
STALE_LEDGER_NOTE = "Full list: %s"
# The scanner throws candidates away at its recall gates before it emits a single path finding. When
# it counts what it dropped, say so here in one line: a filtered view presented as a whole one is
# the same overclaim in a smaller font. The count is optional, so a scan that does not carry it
# renders the section unchanged rather than failing.
DISCARD_NOTE = "The path scan is a filtered view: %s never reached this list."

LANG_NAMES = {"c": "C", "cpp": "C++", "cs": "C#", "elixir": "Elixir", "go": "Go", "java": "Java",
              "js": "JavaScript", "kotlin": "Kotlin", "lua": "Lua", "php": "PHP", "py": "Python",
              "rb": "Ruby", "rs": "Rust", "scala": "Scala", "sh": "Shell", "sql": "SQL",
              "svelte": "Svelte", "swift": "Swift", "ts": "TypeScript", "vue": "Vue"}


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def repository_path(root, candidate):
    prefix = os.path.abspath(root)
    target = (os.path.abspath(candidate) if os.path.isabs(candidate)
              else os.path.abspath(os.path.join(prefix, candidate)))
    if target != prefix and not target.startswith(prefix + os.sep):
        return None
    root_real = os.path.realpath(prefix)
    target_real = os.path.realpath(target)
    try:
        if os.path.commonpath([root_real, target_real]) != root_real:
            return None
    except ValueError:
        return None
    return target


def output_path(root, rel):
    if os.path.isabs(rel):
        raise ValueError("output path must be relative to the repository: %s" % rel)
    prefix = os.path.abspath(root)
    target = os.path.abspath(os.path.join(prefix, rel))
    if target != prefix and not target.startswith(prefix + os.sep):
        raise ValueError("output path leaves the repository: %s" % rel)
    current = prefix
    for part in os.path.relpath(target, prefix).split(os.sep):
        if part in ("", "."):
            continue
        current = os.path.join(current, part)
        if os.path.lexists(current) and os.path.islink(current):
            raise ValueError("output path uses a symlink: %s" % rel)
    if repository_path(prefix, target) is None:
        raise ValueError("output path resolves outside the repository: %s" % rel)
    return target


def write_repository_text(root, rel, text):
    descriptor = safe_open_root(root)
    try:
        output_path(root, rel)
        safe_write_text(root, rel, text, root_descriptor=descriptor)
    finally:
        os.close(descriptor)


def load_catalog():
    catalog = {}
    for key, name, payload in CATALOG_FILES:
        data = load_json(os.path.join(CATALOG_DIR, name))
        if data.get("schema") != SCHEMA:
            raise ValueError("catalog %s declares schema %s, this build reads schema %d"
                             % (name, data.get("schema"), SCHEMA))
        catalog[key] = data if payload is None else data[payload]
    catalog["signal_ids"] = set(item["id"] for item in catalog["signals"])
    catalog["doc_ids"] = set(item["id"] for item in catalog["documents"])
    catalog["doc_by_id"] = dict((item["id"], item) for item in catalog["documents"])
    catalog["question_by_id"] = dict((item["id"], item) for item in catalog["interview"])
    catalog["primary_ids"] = set(item["id"] for item in catalog["archetypes"]["primaries"])
    catalog["overlay_ids"] = set(item["id"] for item in catalog["archetypes"]["overlays"])
    catalog["ordered_rules"] = sorted(catalog["rules"],
                                      key=lambda item: (LAYER_RANK.get(item.get("layer"), 0),
                                                        item["id"]))
    return catalog


def leaf_ids(node):
    found = []
    if not isinstance(node, dict):
        return found
    for key in ("signal", "answer", "document", "archetype", "overlay"):
        if key in node:
            found.append(node[key])
    return found


def check_predicate(catalog, node, where, errors):
    if not isinstance(node, dict) or not node:
        errors.append("catalog %s holds a predicate that is not an object" % where)
        return
    if "all" in node or "any" in node:
        children = node.get("all", node.get("any"))
        if not isinstance(children, list):
            errors.append("catalog %s combinator takes a list" % where)
            return
        for child in children:
            check_predicate(catalog, child, where, errors)
        return
    if "not" in node:
        check_predicate(catalog, node["not"], where, errors)
        return
    if "always" in node or "never" in node:
        return
    if "signal" in node:
        if node["signal"] not in catalog["signal_ids"]:
            errors.append("I3 %s names signal %s, absent from signals.json" % (where, node["signal"]))
        if "is" in node and node["is"] not in SIGNAL_STATES:
            errors.append("I3 %s tests signal state %s, outside the four states" % (where, node["is"]))
        if "gte" in node and not isinstance(node["gte"], int):
            errors.append("I3 %s uses a non-integer gte" % where)
        return
    if "answer" in node:
        question = catalog["question_by_id"].get(node["answer"])
        if question is None:
            errors.append("I2 %s names answer %s, absent from interview.json" % (where, node["answer"]))
            return
        wanted = node.get("in") or ([node["is"]] if "is" in node else [])
        for value in wanted:
            if value not in question["answers"]:
                errors.append("I2 %s tests %s=%s, outside that question's answers"
                              % (where, node["answer"], value))
        return
    if "archetype" in node:
        if node["archetype"] not in catalog["primary_ids"] and node["archetype"] != "unknown":
            errors.append("I2 %s names archetype %s, absent from archetypes.json"
                          % (where, node["archetype"]))
        return
    if "overlay" in node:
        if node["overlay"] not in catalog["overlay_ids"]:
            errors.append("I2 %s names overlay %s, absent from archetypes.json"
                          % (where, node["overlay"]))
        return
    if "document" in node:
        if node["document"] not in catalog["doc_ids"]:
            errors.append("I2 %s names document %s, absent from documents.json"
                          % (where, node["document"]))
        return
    errors.append("catalog %s uses an unknown operator: %s" % (where, ", ".join(sorted(node))))


def check_cites(catalog, tokens, where, errors):
    for token in tokens or []:
        if token in catalog["signal_ids"] or token in catalog["question_by_id"]:
            continue
        errors.append("I3 %s cites %s, which is neither a signal id nor a question id"
                      % (where, token))


# I4 is one property stated five times, so it is one function called from five places.
#
# The property: no jurisdiction hint may change any verdict. There are exactly five paths
# from a signal to a verdict, and every one of them is a predicate. rules.json when is the
# obvious one. documents.json selects_on is not, and it sets the baseline verdict directly.
# archetypes.json weights decide the primary, and the primary is the argument to every
# {"archetype": X} rule. archetypes.json overlay when adds documents through adds and feeds
# every {"overlay": X} rule. interview.json default_from is the quietest of the five: it
# resolves an answer, and answers are the strongest layer in the lattice. Guarding one of
# five is not guarding the invariant.
#
# The test is not syntactic. A predicate can consume a hint without ever writing the word,
# because "not" inverts the leaf it wraps: {"not": {"signal": "jur.eu", "is": "absent"}} is
# true exactly when jur.eu is hint, present or unknown. So the check partially evaluates the
# predicate twice, once with the target signal pinned to "hint" and once pinned to "absent",
# folding away the constants that pinning creates and leaving every other term standing as an
# opaque symbol. If the two residuals are the same formula, the target cannot change the
# answer and the predicate is clean. If they differ, it can.
#
# Partial evaluation replaces an earlier version that enumerated the cross product of every
# term the predicate mentioned and bailed out over a world cap. That version rejected any
# rule with more than a handful of leaves while claiming the rule turned on a hint, which was
# not true of the rule and was a worse failure than no check at all. This version is linear
# in the size of the predicate, exact on the property, and has no cap to fail open or shut.
def predicate_leaves(node, out):
    if not isinstance(node, dict) or not node:
        return out
    if "all" in node or "any" in node:
        for child in node.get("all", node.get("any")) or []:
            predicate_leaves(child, out)
        return out
    if "not" in node:
        predicate_leaves(node["not"], out)
        return out
    out.append(node)
    return out


def pinned_signal_leaf(node, state):
    if "gte" in node:
        # gte reads hits, and hits only count when the signal is present. Neither pinned
        # state is present, so a threshold test cannot see a hint at any count.
        return False
    if "is" in node:
        return node["is"] == state
    return state == "present"


def opaque_term(node):
    return ("term", json.dumps(node, sort_keys=True))


def residual(node, target, state):
    if not isinstance(node, dict) or not node:
        raise ValueError("predicate is not an object: %s" % json.dumps(node))
    if "all" in node or "any" in node:
        children = node.get("all", node.get("any"))
        if not isinstance(children, list):
            raise ValueError("predicate combinator takes a list")
        conjunction = "all" in node
        kept = []
        for child in children:
            value = residual(child, target, state)
            if value is True or value is False:
                if value is not conjunction:
                    return value
                continue
            if value not in kept:
                kept.append(value)
        if not kept:
            return conjunction
        if len(kept) == 1:
            return kept[0]
        return ("all" if conjunction else "any", tuple(sorted(kept, key=repr)))
    if "not" in node:
        value = residual(node["not"], target, state)
        if value is True or value is False:
            return not value
        return ("not", value)
    if "always" in node:
        return bool(node["always"])
    if "never" in node:
        return not bool(node["never"])
    if "signal" in node and node["signal"] == target:
        return pinned_signal_leaf(node, state)
    return opaque_term(node)


def hint_capped(catalog):
    return set(signal["id"] for signal in catalog["signals"]
               if signal.get("max_state") == HINT_MAX_STATE)


def hint_dependent_signals(catalog, node):
    capped = hint_capped(catalog)
    found = []
    for leaf in predicate_leaves(node, []):
        target = leaf.get("signal")
        if target is None or target in found:
            continue
        if target not in catalog["signal_ids"]:
            # I3 already reports the unknown id. Naming it twice helps nobody.
            return []
        if target not in capped:
            continue
        try:
            pinned = [residual(node, target, state) for state in HINT_PROBE_PIN]
        except ValueError:
            # The predicate is malformed. check_predicate reports that on its own.
            return []
        if pinned[0] != pinned[1]:
            found.append(target)
    return found


def check_hint_free(catalog, node, where, consequence, errors):
    for signal_id in hint_dependent_signals(catalog, node):
        errors.append("I4 %s turns on hint signal %s, and %s. %s"
                      % (where, signal_id, consequence, HINT_RULE))


def uses_answer(node):
    if not isinstance(node, dict):
        return False
    if "all" in node or "any" in node:
        return any(uses_answer(child) for child in node.get("all", node.get("any")) or [])
    if "not" in node:
        return uses_answer(node["not"])
    return "answer" in node


def template_path(doc):
    slug = doc["id"].split(".", 1)[-1]
    return os.path.join(TEMPLATE_DIR, "%s-%s.md" % (doc["stage"], slug))


def check_documents(catalog, errors):
    seen = set()
    for doc in catalog["documents"]:
        if doc["id"] in seen:
            errors.append("I9 documents.json declares %s twice" % doc["id"])
        seen.add(doc["id"])
        enums = [("stage", STAGES), ("durability", DURABILITIES), ("scope", SCOPES),
                 ("producible", PRODUCIBLES), ("backfillability", BACKFILLABILITIES),
                 ("sensitivity", SENSITIVITIES)]
        for field, allowed in enums:
            if doc.get(field) not in allowed:
                errors.append("I8 %s sets %s=%s, outside its enum"
                              % (doc["id"], field, doc.get(field)))
        cadence = doc.get("cadence")
        if cadence not in CADENCE_WORDS and not CADENCE_ISO.match(str(cadence)):
            errors.append("I8 %s sets cadence=%s, neither an ISO 8601 duration nor %s"
                          % (doc["id"], cadence, "/".join(CADENCE_WORDS)))
        if doc.get("baseline_verdict") not in VERDICT_RANK:
            errors.append("I8 %s sets baseline_verdict=%s, outside the verdict lattice"
                          % (doc["id"], doc.get("baseline_verdict")))
        if doc["scope"] in ("product", "org") and doc.get("system_of_record") != "ask":
            errors.append("I10 %s is %s scoped and sets system_of_record=%s, which must be ask"
                          % (doc["id"], doc["scope"], doc.get("system_of_record")))
        if doc["producible"] in ("M", "R") and os.path.exists(template_path(doc)):
            errors.append("I1 %s is producible %s and must not ship a template, found %s"
                          % (doc["id"], doc["producible"], template_path(doc)))
        where = "documents.json %s.selects_on" % doc["id"]
        check_predicate(catalog, doc["selects_on"], where, errors)
        check_hint_free(catalog, doc["selects_on"], where,
                        "selects_on decides the baseline verdict for %s" % doc["id"], errors)


def check_rules(catalog, errors):
    seen = set()
    for rule in catalog["rules"]:
        where = "rules.json %s" % rule["id"]
        if rule["id"] in seen:
            errors.append("I9 rules.json declares %s twice" % rule["id"])
        seen.add(rule["id"])
        if rule.get("layer") not in LAYER_RANK:
            errors.append("I8 %s sets layer=%s, outside the precedence enum"
                          % (rule["id"], rule.get("layer")))
        if rule.get("effect") not in EFFECT_VERDICT and rule.get("effect") not in SOFT_EFFECTS:
            errors.append("I8 %s sets effect=%s, outside the effect enum"
                          % (rule["id"], rule.get("effect")))
        if not rule.get("because"):
            errors.append("I7 %s carries no because, which is printed verbatim to the user"
                          % rule["id"])
        check_predicate(catalog, rule["when"], where + ".when", errors)
        check_cites(catalog, rule.get("cite"), where + ".cite", errors)
        for doc_id in rule.get("documents") or []:
            if doc_id not in catalog["doc_ids"]:
                errors.append("I2 %s names document %s, absent from documents.json"
                              % (rule["id"], doc_id))
        if rule.get("effect") not in SOFT_EFFECTS:
            check_hint_free(catalog, rule["when"], where + ".when",
                            "effect=%s is a verdict" % rule.get("effect"), errors)
        if rule.get("effect") in ("require", "recommend") and not uses_answer(rule["when"]):
            for doc_id in rule.get("documents") or []:
                doc = catalog["doc_by_id"].get(doc_id)
                if doc is not None and doc["producible"] == "R":
                    errors.append("I6 %s sets %s on refused document %s with no answer term in when"
                                  % (rule["id"], rule["effect"], doc_id))
        if rule.get("effect") == "exclude":
            for field in ("because", "cite", "revisit_when"):
                if not rule.get(field):
                    errors.append("I7 %s excludes without %s" % (rule["id"], field))
            if rule.get("revisit_when"):
                check_predicate(catalog, rule["revisit_when"], where + ".revisit_when", errors)
                # A tripwire tells the reader that a document excluded earlier is now required.
                # That sentence is a verdict wherever it is printed, so a hint may not fire one.
                check_hint_free(catalog, rule["revisit_when"], where + ".revisit_when",
                                "a firing tripwire tells the reader the code now requires %s"
                                % ", ".join(rule.get("documents") or ["the excluded document"]),
                                errors)


def check_archetypes(catalog, errors):
    archetypes = catalog["archetypes"]
    seen = set()
    for primary in archetypes["primaries"]:
        if primary["id"] in seen:
            errors.append("I9 archetypes.json declares primary %s twice" % primary["id"])
        seen.add(primary["id"])
        for weight in primary["weights"]:
            where = "archetypes.json %s.weights" % primary["id"]
            check_predicate(catalog, weight["when"], where, errors)
            check_hint_free(catalog, weight["when"], where,
                            "the archetype score picks the primary and the primary is the "
                            "baseline every rule reads", errors)
        for signal_id in primary.get("requires_absent") or []:
            if signal_id not in catalog["signal_ids"]:
                errors.append("I3 archetype %s requires_absent %s, absent from signals.json"
                              % (primary["id"], signal_id))
            elif signal_id in hint_capped(catalog):
                # requires_absent zeroes an archetype when the signal reaches present, and a
                # hint-capped signal never reaches present. Naming one here reads as a guard and
                # is a rule that can never fire, which is the mirror of letting a hint decide.
                errors.append("I4 archetypes.json %s.requires_absent names hint signal %s, which "
                              "never reaches present, so the guard can never fire. %s"
                              % (primary["id"], signal_id, HINT_RULE))
    seen = set()
    for overlay in archetypes["overlays"]:
        if overlay["id"] in seen:
            errors.append("I9 archetypes.json declares overlay %s twice" % overlay["id"])
        seen.add(overlay["id"])
        where = "archetypes.json %s.when" % overlay["id"]
        check_predicate(catalog, overlay["when"], where, errors)
        check_hint_free(catalog, overlay["when"], where,
                        "an overlay adds documents and every {overlay: %s} rule reads it"
                        % overlay["id"], errors)
        for doc_id in overlay.get("adds") or []:
            if doc_id not in catalog["doc_ids"]:
                errors.append("I2 overlay %s adds %s, absent from documents.json"
                              % (overlay["id"], doc_id))


def check_interview(catalog, errors):
    seen = set()
    for question in catalog["interview"]:
        if question["id"] in seen:
            errors.append("I9 interview.json declares %s twice" % question["id"])
        seen.add(question["id"])
        if question.get("no_signal_may_set") and question.get("default_from"):
            errors.append("I5 %s is marked no_signal_may_set and carries %d default_from rules"
                          % (question["id"], len(question["default_from"])))
        fallback = question["fallback"]
        for value in fallback if isinstance(fallback, list) else [fallback]:
            if value not in question["answers"]:
                errors.append("I8 %s falls back to %s, outside its answers"
                              % (question["id"], value))
        for entry in question.get("default_from") or []:
            where = "interview.json %s.default_from" % question["id"]
            check_predicate(catalog, entry["when"], where, errors)
            check_cites(catalog, entry.get("cite"), where, errors)
            value = entry["value"]
            for item in value if isinstance(value, list) else [value]:
                if item not in question["answers"]:
                    errors.append("I8 %s defaults to %s, outside its answers"
                                  % (question["id"], item))
            # A default_from that a hint can swing is allowed, and it is how a GC or an EU
            # signal reaches the user at all. What it may not do is resolve the answer, so it
            # has to say so in the catalog and resolve_answers honours the flag by opening the
            # question instead. prompts on an entry no hint can swing is the mirror mistake:
            # the entry would be scanned, skipped, and never resolve anything.
            swings = hint_dependent_signals(catalog, entry["when"])
            if swings and not entry.get("prompts"):
                errors.append("I4 %s turns on hint signal %s and resolves %s to %s without "
                              "prompts. %s" % (where, swings[0], question["id"],
                                               json.dumps(entry["value"]), HINT_RULE))
            if entry.get("prompts") and not swings:
                errors.append("I4 %s sets prompts and no hint-capped signal can change it, so "
                              "the entry opens nothing and resolves nothing" % where)
    if "q4_decides_about_people" in catalog["question_by_id"]:
        question = catalog["question_by_id"]["q4_decides_about_people"]
        if question.get("default_from"):
            errors.append("I5 q4_decides_about_people carries a default_from rule; no signal may "
                          "set it")


def check_invariants(catalog):
    errors = []
    check_documents(catalog, errors)
    check_rules(catalog, errors)
    check_archetypes(catalog, errors)
    check_interview(catalog, errors)
    for signal in catalog["signals"]:
        if not signal.get("gate"):
            continue
        where = "signals.json %s.gate" % signal["id"]
        check_predicate(catalog, signal["gate"], where, errors)
        if signal.get("max_state") != HINT_MAX_STATE:
            # A gate decides whether a signal fires at all. A hint gating a hint is the
            # corroboration pattern the jurisdiction family is built on. A hint gating a
            # signal that is allowed to reach a verdict is the same escape by one more hop.
            check_hint_free(catalog, signal["gate"], where,
                            "the gate decides whether %s fires and %s is not hint capped"
                            % (signal["id"], signal["id"]), errors)
    return sorted(set(errors))


def predicate(ctx, node):
    if not isinstance(node, dict) or not node:
        raise ValueError("predicate is not an object: %s" % json.dumps(node))
    if "all" in node:
        return all(predicate(ctx, child) for child in node["all"])
    if "any" in node:
        return any(predicate(ctx, child) for child in node["any"])
    if "not" in node:
        return not predicate(ctx, node["not"])
    if "always" in node:
        return bool(node["always"])
    if "never" in node:
        return not bool(node["never"])
    if "signal" in node:
        record = ctx["signals"].get(node["signal"])
        if record is None:
            raise ValueError("predicate names signal %s, absent from signals.json" % node["signal"])
        if "gte" in node:
            return record["state"] == "present" and (record.get("hits") or 0) >= node["gte"]
        if "is" in node:
            return record["state"] == node["is"]
        return record["state"] == "present"
    if "answer" in node:
        value = ctx["answers"].get(node["answer"])
        if value is None:
            return False
        chosen = value if isinstance(value, list) else [value]
        wanted = node.get("in") or ([node["is"]] if "is" in node else [])
        return any(item in wanted for item in chosen)
    if "archetype" in node:
        return ctx["archetype"] == node["archetype"]
    if "overlay" in node:
        return node["overlay"] in ctx["overlays"]
    if "document" in node:
        state = ctx["docstate"].get(node["document"], "absent")
        wanted = node.get("state", "present")
        if wanted == "present":
            return state.startswith("present")
        return state == wanted
    raise ValueError("unknown predicate operator: %s" % ", ".join(sorted(node)))


def firing_distance(ctx, node):
    if not isinstance(node, dict) or not node:
        return FAR
    if "all" in node:
        return min(FAR, sum(firing_distance(ctx, child) for child in node["all"]))
    if "any" in node:
        return min([firing_distance(ctx, child) for child in node["any"]] or [FAR])
    if predicate(ctx, node):
        return 0
    if "not" in node:
        return 1
    return 1


def true_terms(ctx, node, out):
    if not isinstance(node, dict):
        return
    if "all" in node:
        for child in node["all"]:
            true_terms(ctx, child, out)
        return
    if "any" in node:
        for child in node["any"]:
            if predicate(ctx, child):
                true_terms(ctx, child, out)
        return
    if "not" in node:
        true_terms(ctx, node["not"], out)
        return
    for token in leaf_ids(node):
        if token not in out:
            out.append(token)


def missing_terms(ctx, node, out):
    if not isinstance(node, dict):
        return
    if "all" in node or "any" in node:
        for child in node.get("all", node.get("any")) or []:
            missing_terms(ctx, child, out)
        return
    if "not" in node or predicate(ctx, node):
        return
    for token in leaf_ids(node):
        if token not in out:
            out.append(token)


def cite_label(ctx, token):
    record = ctx["signals"].get(token)
    if record is not None:
        if record["state"] == "present":
            return token
        return "%s=%s" % (token, record["state"])
    if token in ctx["answers"]:
        value = ctx["answers"][token]
        return "%s=%s" % (token, ",".join(value) if isinstance(value, list) else value)
    state = (ctx.get("docstate") or {}).get(token)
    if state is not None:
        # leaf_ids harvests {"document": ...} terms the same way it harvests signals, so a
        # cite token can be a catalog document id. Emitted bare it reads like a signal id
        # and names nothing with a file path, which breaks the promise that every exclusion
        # names its evidence. Say which presence fact the token stands for.
        if state.startswith("present"):
            return "%s present in the repo" % token
        return "%s absent" % token
    return token


def cite_labels(ctx, tokens):
    return [cite_label(ctx, token) for token in tokens or []]


def cite_evidence(ctx, tokens, limit=3):
    paths = []
    for token in tokens or []:
        record = ctx["signals"].get(token)
        if record is None or record["state"] not in ("present", "hint"):
            continue
        for item in record.get("evidence") or []:
            path = item.get("path")
            if path and path not in paths:
                paths.append(path)
            if len(paths) >= limit:
                return paths
    return paths


def signal_map(catalog, scan):
    signals = {}
    for signal in catalog["signals"]:
        signals[signal["id"]] = {"id": signal["id"], "state": "unknown", "hits": 0,
                                 "evidence": [], "label": signal["label"]}
    for record in scan.get("signals") or []:
        if record["id"] in signals:
            signals[record["id"]] = record
    return signals


def score_archetypes(ctx, catalog):
    scored = []
    for primary in catalog["archetypes"]["primaries"]:
        total = sum(weight["points"] for weight in primary["weights"] if weight["points"] > 0)
        matched = 0
        fired = []
        for weight in primary["weights"]:
            if predicate(ctx, weight["when"]):
                matched += weight["points"]
                if weight["points"] > 0:
                    true_terms(ctx, weight["when"], fired)
        blocked = [signal_id for signal_id in primary.get("requires_absent") or []
                   if ctx["signals"][signal_id]["state"] == "present"]
        score = 0.0 if total <= 0 else max(0.0, min(1.0, float(matched) / float(total)))
        if blocked:
            score = 0.0
        scored.append({"id": primary["id"], "score": round(score, 3), "baseline": primary["baseline"],
                       "blocked_by": blocked, "cite": cite_labels(ctx, fired[:4])})
    scored.sort(key=lambda item: (-item["score"], item["id"]))
    return scored


def resolve_archetype(ctx, catalog):
    scored = score_archetypes(ctx, catalog)
    floor = catalog["archetypes"]["floor"]
    margin = catalog["archetypes"]["counterfactual_margin"]
    top = scored[0]
    runner = scored[1] if len(scored) > 1 else None
    gap = round(100.0 * (top["score"] - runner["score"]), 3) if runner else 100.0
    primary = top["id"] if top["score"] >= floor else "unknown"
    if primary == "unknown":
        confidence = "low"
    elif gap >= margin and top["score"] >= 0.70:
        confidence = "high"
    elif gap >= margin or top["score"] >= 0.70:
        confidence = "medium"
    else:
        confidence = "low"
    return {"primary": primary, "score": top["score"], "baseline": top["baseline"],
            "confidence": confidence, "floor": floor, "margin": margin, "gap": round(gap, 1),
            "cite": top["cite"], "scored": scored,
            "runner_up": None if runner is None else {"id": runner["id"], "score": runner["score"]},
            "within_margin": bool(runner is not None and primary != "unknown" and gap < margin)}


def signal_labels(ctx, tokens):
    labels = []
    for token in tokens or []:
        record = ctx["signals"].get(token) or {}
        label = record.get("label")
        if label and label not in labels:
            labels.append(label)
    return labels


def entry_terms(ctx, entry):
    fired = []
    true_terms(ctx, entry["when"], fired)
    return fired or list(entry.get("cite") or [])


# Three sources, and the middle one is the whole point. "user" is a real answer, from
# --answer or from a prior manifest. "assumed" is docdna taking a question at its fallback
# or at a default a non-hint signal earned. "hint-prompted" is a question a jurisdiction
# hint opened and did not answer: the value stays at whatever the fallback or a non-hint
# default gives it, and the value the hint would have written is reported as an open
# question with its blast radius instead. That is the difference between "I found
# Government-of-Canada signals but will not act on them without you" and quietly writing
# government-authorizer into the manifest, which is what the code used to do.
def resolve_answers(ctx, catalog, overrides, prior):
    answers = {}
    for question in catalog["interview"]:
        key = question["id"]
        if key in overrides:
            answers[key] = {"value": overrides[key], "source": "user", "from": "--answer"}
            continue
        if key in prior:
            answers[key] = {"value": prior[key], "source": "user", "from": "manifest"}
            continue
        chosen = None
        opened = None
        for entry in question.get("default_from") or []:
            if not predicate(ctx, entry["when"]):
                continue
            if entry.get("prompts"):
                # First match wins here too, so one hint opens one question, not three.
                # Scanning continues, because a later entry a real signal earned may still
                # resolve the answer that the hint was not allowed to.
                if opened is None:
                    terms = entry_terms(ctx, entry)
                    opened = {"value": entry["value"], "cite": cite_labels(ctx, terms),
                              "found": signal_labels(ctx, terms),
                              "evidence": cite_evidence(ctx, terms)}
                continue
            chosen = entry
            break
        if chosen is None:
            row = {"value": question["fallback"], "source": "assumed", "from": "fallback"}
        else:
            row = {"value": chosen["value"], "source": "assumed",
                   "from": ", ".join(cite_labels(ctx, entry_terms(ctx, chosen)))}
        if opened is not None:
            row["source"] = "hint-prompted"
            row["prompted_by"] = opened
        answers[key] = row
    return answers


def answer_values(answers):
    return dict((key, row["value"]) for key, row in answers.items())


def resolve_overlays(ctx, catalog):
    active = []
    for overlay in catalog["archetypes"]["overlays"]:
        if predicate(ctx, overlay["when"]):
            active.append(overlay["id"])
    return sorted(active)


def locate(scan_docs, root, candidate):
    full = repository_path(root, candidate.rstrip("/") or ".")
    if full is None:
        return None
    target = os.path.realpath(full)
    if candidate.endswith("/"):
        for path in sorted(scan_docs):
            if path.startswith(candidate) and repository_path(root, path) is not None:
                return path
        if safe_is_dir(root, target) and safe_listdir(root, target):
            return candidate
        return None
    if candidate in scan_docs:
        return candidate
    if safe_exists(root, target):
        return candidate
    return None


def document_states(catalog, scan, root):
    scan_docs = {}
    for doc in scan["inventory"]["docs"]:
        scan_docs[doc["path"]] = doc
    for row in scan["inventory"].get("opaque") or []:
        scan_docs.setdefault(row["path"], {"path": row["path"], "bytes": row.get("bytes")})
    drifted = set(row["doc"] for row in scan.get("drift") or [])
    states = {}
    found = {}
    for entry in catalog["documents"]:
        candidates = []
        for candidate in list(entry["detect_paths"]) + [entry["path"]]:
            if candidate not in candidates:
                candidates.append(candidate)
        state = "absent"
        where = None
        for candidate in candidates:
            hit = locate(scan_docs, root, candidate)
            if hit is None:
                continue
            where = hit
            size = None
            if hit in scan_docs:
                size = scan_docs[hit].get("bytes")
            else:
                full = repository_path(root, hit)
                target = os.path.realpath(full) if full is not None else None
                if target is not None and safe_is_file(root, target):
                    size = safe_file_size(root, target)
            if hit in drifted:
                state = "present-drifted"
            elif size is not None and size < STUB_BYTES:
                state = "present-stub"
            else:
                state = "present-fresh"
            break
        states[entry["id"]] = state
        found[entry["id"]] = where
    return states, found


def baseline_record(ctx, doc, selected):
    terms = []
    if selected:
        true_terms(ctx, doc["selects_on"], terms)
        labels = cite_labels(ctx, terms)
        because = ("Selected by %s." % ", ".join(labels) if labels
                   else "The catalog selects this document for every repository.")
    else:
        missing_terms(ctx, doc["selects_on"], terms)
        because = "No signal in this repository selects this document."
    return {"rule": "catalog-baseline", "layer": "baseline",
            "verdict": doc["baseline_verdict"] if selected else "not-applicable",
            "because": because, "cite": cite_labels(ctx, terms), "tokens": list(terms),
            "revisit_when": None if selected else doc["selects_on"]}


def run_engine(ctx, catalog):
    state = {}
    for doc in catalog["documents"]:
        selected = predicate(ctx, doc["selects_on"])
        record = baseline_record(ctx, doc, selected)
        state[doc["id"]] = {"verdict": record["verdict"], "records": [record], "rules": [],
                            "forced": [], "blocked": [], "notes": []}
    notes = []
    questions = []
    for rule in catalog["ordered_rules"]:
        if not predicate(ctx, rule["when"]):
            continue
        row = {"rule": rule["id"], "layer": rule["layer"], "because": rule["because"],
               "cite": cite_labels(ctx, rule.get("cite")), "documents": rule["documents"]}
        if rule["effect"] in SOFT_EFFECTS:
            (questions if rule["effect"] == "ask" else notes).append(row)
            for doc_id in rule["documents"]:
                state[doc_id]["notes"].append(row)
            continue
        target = EFFECT_VERDICT[rule["effect"]]
        for doc_id in rule["documents"]:
            entry = state[doc_id]
            lowers = VERDICT_RANK[target] < VERDICT_RANK[entry["verdict"]]
            if lowers and not rule.get("force"):
                entry["blocked"].append(rule["id"])
                continue
            if lowers:
                entry["forced"].append(rule["id"])
            entry["verdict"] = target
            entry["rules"].append(rule["id"])
            entry["records"].append({"rule": rule["id"], "layer": rule["layer"], "verdict": target,
                                     "because": rule["because"],
                                     "cite": cite_labels(ctx, rule.get("cite")),
                                     "tokens": list(rule.get("cite") or []),
                                     "revisit_when": rule.get("revisit_when")})
    return {"documents": state, "notes": notes, "questions": questions}


def engine_for(ctx, catalog, answers, archetype=None):
    scratch = dict(ctx)
    scratch["answers"] = answers
    if archetype is not None:
        scratch["archetype"] = archetype
    scratch["overlays"] = resolve_overlays(scratch, catalog)
    return scratch, run_engine(scratch, catalog)


def verdict_sets(result):
    required = set()
    selected = set()
    for doc_id, entry in result["documents"].items():
        if entry["verdict"] == "required":
            required.add(doc_id)
        if VERDICT_RANK[entry["verdict"]] > 0:
            selected.add(doc_id)
    return required, selected


def counterfactual_rows(ctx, catalog, answers, base):
    base_required, base_selected = verdict_sets(base)
    rows = []
    for question in catalog["interview"]:
        key = question["id"]
        current = answers[key]["value"]
        best = None
        for value in question["answers"]:
            flipped = [value] if question["multi_select"] else value
            if flipped == current:
                continue
            trial = dict(answer_values(answers))
            trial[key] = flipped
            _, result = engine_for(ctx, catalog, trial)
            required, selected = verdict_sets(result)
            added = sorted(required - base_required)
            removed = sorted(base_required - required)
            row = {"answer": key, "from": current, "to": flipped,
                   "becomes_required": len(added), "no_longer_required": len(removed),
                   "added": added, "removed": removed,
                   "documents_selected": len(selected) - len(base_selected),
                   "counterfactual": question["counterfactual"]}
            if best is None or row["becomes_required"] > best["becomes_required"]:
                best = row
        if best is not None:
            rows.append(best)
    rows.sort(key=lambda item: (-item["becomes_required"], item["answer"]))
    return rows


def open_question_rows(ctx, catalog, answers, base):
    base_required, _ = verdict_sets(base)
    rows = []
    for key in sorted(answers):
        row = answers[key]
        if row["source"] != "hint-prompted":
            continue
        opened = row["prompted_by"]
        trial = dict(answer_values(answers))
        trial[key] = opened["value"]
        _, result = engine_for(ctx, catalog, trial)
        required, _ = verdict_sets(result)
        added = sorted(required - base_required)
        rows.append({"answer": key, "would_be": opened["value"], "assumed": row["value"],
                     "cite": opened["cite"], "found": opened["found"],
                     "evidence": opened["evidence"], "becomes_required": len(added),
                     "added": added, "prompt": catalog["question_by_id"][key]["prompt"]})
    rows.sort(key=lambda item: (-item["becomes_required"], item["answer"]))
    return rows


def archetype_counterfactual(ctx, catalog, answers, base, archetype):
    if not archetype["within_margin"] or archetype["runner_up"] is None:
        return None
    _, result = engine_for(ctx, catalog, answer_values(answers), archetype["runner_up"]["id"])
    _, base_selected = verdict_sets(base)
    _, other_selected = verdict_sets(result)
    return {archetype["runner_up"]["id"]: {"added": sorted(other_selected - base_selected),
                                           "removed": sorted(base_selected - other_selected)}}


def resolve_system_of_record(doc, answers):
    if doc["system_of_record"] != "ask":
        return doc["system_of_record"]
    location = answers["q8_doc_location"]["value"]
    if location == "mostly-elsewhere":
        return "external"
    if location == "repo":
        return "repo"
    return "ask"


def owner_candidate(scan):
    ownership = scan.get("ownership") or {}
    if ownership.get("codeowners") and ownership.get("codeowners_path"):
        return "see %s (unconfirmed)" % ownership["codeowners_path"]
    authors = ownership.get("top_authors") or []
    if authors:
        return "%s (top committer, unconfirmed)" % authors[0]["name"]
    return None


def because_for(entry):
    live = [record for record in entry["records"] if record["verdict"] == entry["verdict"]]
    ordered = [record for record in reversed(live) if record["rule"] != "catalog-baseline"]
    ordered += [record for record in live if record["rule"] == "catalog-baseline"]
    reasons = []
    cites = []
    for record in ordered:
        if record["because"] not in reasons:
            reasons.append(record["because"])
        for token in record["cite"]:
            if token not in cites:
                cites.append(token)
    return reasons, cites


def tokens_for(entry):
    tokens = []
    for record in entry["records"]:
        if record["verdict"] != entry["verdict"]:
            continue
        for token in record.get("tokens") or []:
            if token not in tokens:
                tokens.append(token)
    return tokens


def revisit_for(entry):
    revisit = None
    for record in entry["records"]:
        if record["verdict"] == "not-applicable" and record.get("revisit_when"):
            revisit = record["revisit_when"]
    return revisit


def build_rows(ctx, catalog, base, answers, states, found, scan, prior_status, blocked_stages):
    documents = []
    excluded = []
    for doc in catalog["documents"]:
        entry = base["documents"][doc["id"]]
        verdict = entry["verdict"]
        state = states[doc["id"]]
        record = resolve_system_of_record(doc, answers)
        if state == "absent" and record == "external":
            state = "present-elsewhere"
        action = ACTIONS[(verdict, state)]
        reasons, cites = because_for(entry)
        if verdict == "not-applicable" and action == "skip":
            excluded.append({"id": doc["id"], "title": doc["title"], "stage": doc["stage"],
                             "rule": entry["rules"][-1] if entry["rules"] else "catalog-baseline",
                             "because": reasons[0] if reasons else "",
                             "cite": cites, "revisit_when": revisit_for(entry)})
            continue
        row = {"id": doc["id"], "title": doc["title"], "stage": doc["stage"], "verdict": verdict,
               "state": state, "action": action, "durability": doc["durability"],
               "scope": doc["scope"], "system_of_record": record, "producible": doc["producible"],
               "backfillability": doc["backfillability"], "cadence": doc["cadence"],
               "sensitivity": doc["sensitivity"], "path": doc["path"], "found_at": found[doc["id"]],
               "because": reasons, "cite": cites,
               "evidence": cite_evidence(ctx, tokens_for(entry)),
               "satisfies": doc["satisfies"], "audiences": doc["audiences"],
               "owner": "unassigned", "owner_candidate": owner_candidate(scan),
               "defers_to": doc["defers_to"], "rules": entry["rules"],
               "write_status": prior_status.get(doc["id"], "pending")}
        if entry["forced"]:
            row["forced_by"] = entry["forced"]
        if entry["blocked"]:
            row["downgrade_refused"] = entry["blocked"]
        if entry["notes"]:
            row["notes"] = [note["because"] for note in entry["notes"]]
        if doc["stage"] in blocked_stages and action in ("write", "offer", "refresh", "complete"):
            row["write_block"] = ("archetype confidence is low, so docdna will not write an %s "
                                  "stage document until the archetype is confirmed" % doc["stage"])
        documents.append(row)
    documents.sort(key=lambda item: (-VERDICT_RANK[item["verdict"]], item["id"]))
    excluded.sort(key=lambda item: item["id"])
    return documents, excluded


def build_assumptions(answers, dial):
    by_answer = dict((row["answer"], row) for row in dial)
    rows = []
    for key in sorted(answers):
        if answers[key]["source"] != "assumed":
            continue
        row = by_answer.get(key) or {}
        count = row.get("becomes_required", 0)
        phrase = row.get("counterfactual", key)
        sentence = "If %s, up to %s become required." % (phrase, plural(count, "document"))
        if count == 0:
            sentence = "If %s, no document changes verdict." % phrase
        rows.append({"answer": key, "assumed": answers[key]["value"], "from": answers[key]["from"],
                     "counterfactual": sentence, "becomes_required": count,
                     "worst_case": row.get("to"), "added": row.get("added") or []})
    rows.sort(key=lambda item: (-item["becomes_required"], item["answer"]))
    return rows


def plural(count, word, suffix="s"):
    return "%d %s%s" % (count, word, "" if count == 1 else suffix)


def near_firing(ctx, excluded):
    rows = []
    for row in excluded:
        if not row.get("revisit_when"):
            continue
        if firing_distance(ctx, row["revisit_when"]) != NEAR_MISS:
            continue
        terms = []
        missing_terms(ctx, row["revisit_when"], terms)
        rows.append({"id": row["id"], "needs": terms[:MAX_TRIPWIRE_TERMS]})
    rows.sort(key=lambda item: item["id"])
    return rows


def coverage_of(documents):
    need = [row for row in documents if row["verdict"] in ("required", "recommended")]
    have = [row for row in need if row["state"] == "present-fresh"]
    return {"have": len(have), "need": len(need),
            "definition": "present-fresh over required plus recommended"}


def boundary_text(catalog):
    question = catalog["question_by_id"].get("q8_doc_location") or {}
    return question.get("always_state_text") or BOUNDARY


def build_spine():
    return [{"spine": name, "from": start, "to": end, "method": "annotation",
             "coverage": None, "reason": SPINE_REASON} for name, start, end in SPINE_HOPS]


def interview_row(row):
    out = {"value": row["value"], "source": row["source"], "from": row["from"]}
    if row.get("prompted_by"):
        out["prompted_by"] = row["prompted_by"]
    return out


def build_manifest(ctx, catalog, scan, answers, archetype, base, dial, opens, documents, excluded,
                   prior, unattended):
    drift = []
    by_path = {}
    for doc in catalog["documents"]:
        for candidate in doc["detect_paths"]:
            by_path.setdefault(candidate, doc["id"])
    for row in scan.get("drift") or []:
        item = dict(row)
        if row.get("doc") in by_path:
            item["doc_id"] = by_path[row["doc"]]
        drift.append(item)
    manifest = {
        "schema": SCHEMA,
        "generated_by": "docdna v%s" % VERSION,
        "generated_at": today(),
        "tool": TOOL,
        "root": scan["root"],
        "repo_head": (scan.get("commit") or "")[:7] or None,
        "dirty": scan.get("dirty"),
        "scan_generated": scan.get("generated"),
        "unattended": bool(unattended),
        "archetype": {"primary": archetype["primary"], "score": archetype["score"],
                      "runner_up": archetype["runner_up"], "confidence": archetype["confidence"],
                      "floor": archetype["floor"], "margin_points": archetype["gap"],
                      "counterfactual_margin": archetype["margin"],
                      "baseline": archetype["baseline"], "cite": archetype["cite"],
                      "overlays": ctx["overlays"],
                      "scores": [{"id": row["id"], "score": row["score"],
                                  "blocked_by": row["blocked_by"]}
                                 for row in archetype["scored"]],
                      "counterfactual": archetype.get("document_delta")},
        "interview": dict((key, interview_row(row)) for key, row in answers.items()),
        "open_questions": opens,
        "coverage": coverage_of(documents),
        "documents": documents,
        "excluded": excluded,
        "assumptions": build_assumptions(answers, dial),
        "counterfactual": dial,
        "questions": base["questions"],
        "notes": base["notes"],
        "drift": drift,
        "spine": build_spine(),
        "boundary": boundary_text(catalog),
    }
    if archetype["within_margin"]:
        manifest["archetype_counterfactual"] = True
    if prior.get("generated_at"):
        manifest["previous"] = {"generated_at": prior["generated_at"],
                                "coverage": prior.get("coverage")}
    return manifest


def fact_line(signals, archetype, overlays):
    parts = [archetype["primary"]]
    if overlays:
        parts.append("overlays: %s" % ", ".join(overlays))
    loc = signals.get("scale.loc") or {}
    langs = ((signals.get("scale.languages") or {}).get("detail") or {}).get("distinct") or []
    names = [LANG_NAMES.get(item, item) for item in langs[:2]]
    if len(langs) > 2:
        names.append("+%d" % (len(langs) - 2))
    if loc.get("state") == "present":
        parts.append("%s %s" % (plural(loc.get("hits") or 0, "line"), "/".join(names) or "source"))
    authors = signals.get("proc.authors_12mo") or {}
    if authors.get("state") == "present":
        parts.append(plural(authors.get("hits") or 0, "author"))
    license_row = signals.get("supply.license") or {}
    if license_row.get("state") == "present":
        parts.append((license_row.get("detail") or {}).get("spdx") or "licensed")
    else:
        parts.append("no license")
    tags = signals.get("proc.tags") or {}
    if tags.get("state") == "present" and tags.get("hits"):
        parts.append(plural(tags["hits"], "tag"))
    if (signals.get("deploy.cd") or {}).get("state") == "present":
        parts.append("continuous deployment")
    elif (signals.get("deploy.ci") or {}).get("state") == "present":
        parts.append("CI only")
    else:
        parts.append("nothing deployed")
    return "docdna  " + "  ·  ".join(parts)


def labelled(label, body, lines):
    wrapped = []
    for chunk in body:
        wrapped.extend(textwrap.wrap(chunk, LINE_WIDTH - LABEL_WIDTH) or [""])
    for index, text in enumerate(wrapped):
        prefix = label.ljust(LABEL_WIDTH) if index == 0 else " " * LABEL_WIDTH
        lines.append((prefix + text).rstrip())


def row_line(name, text, lines):
    wrapped = textwrap.wrap(text, LINE_WIDTH - ROW_WIDTH - 2) or [""]
    if len(wrapped) > MAX_ROW_LINES:
        wrapped = wrapped[:MAX_ROW_LINES]
        wrapped[-1] = wrapped[-1] + " ..."
    for index, chunk in enumerate(wrapped):
        prefix = "  " + name + " " * max(1, ROW_WIDTH - len(name)) if index == 0 \
            else " " * (ROW_WIDTH + 2)
        lines.append((prefix + chunk).rstrip())


def section(title, total, shown, lines):
    if total > shown:
        lines.append("%s  (%d, showing %d)" % (title, total, shown))
    else:
        lines.append(title)


def stale_section(total, shown, lines):
    if total > shown:
        lines.append("%s  (%d, showing %d)" % (STALE_TITLE, total, shown))
    else:
        lines.append("%s  (%d)" % (STALE_TITLE, total))


def discarded_paths(scan):
    dropped = ((scan.get("scan") or {}).get("drift") or {}).get("discarded")
    if isinstance(dropped, dict):
        return sum(value for value in dropped.values() if isinstance(value, int))
    return dropped if isinstance(dropped, int) else 0


def stale_note(rows, scan):
    kinds = set(row.get("kind") for row in rows)
    parts = []
    if PATH_KIND in kinds:
        parts.append(STALE_PATH_NOTE)
        dropped = discarded_paths(scan)
        if dropped:
            parts.append(DISCARD_NOTE % plural(dropped, "candidate"))
    if COMMAND_KIND in kinds:
        parts.append(STALE_COMMAND_NOTE)
    parts.append(STALE_READ_NOTE)
    parts.append(STALE_LEDGER_NOTE % MANIFEST_REL)
    return " ".join(parts)


def drift_sentence(row):
    claim = row.get("claim")
    detail = row.get("detail") or row.get("kind")
    if claim:
        return "says `%s`; %s" % (claim, detail)
    return detail


def joined(value):
    return ", ".join(value) if isinstance(value, list) else str(value)


def open_sentences(row):
    body = ["I found %s but will not act on that without you."
            % joined(row["found"] or row["cite"])]
    if row["evidence"]:
        body.append("Evidence: %s." % ", ".join(row["evidence"][:MAX_OPEN_EVIDENCE]))
    body.append("%s (%s) is unanswered." % (row["answer"], row["prompt"]))
    if row["becomes_required"]:
        body.append("Answering %s makes %s required."
                    % (joined(row["would_be"]), plural(row["becomes_required"], "document")))
    else:
        body.append("Answering %s changes no verdict." % joined(row["would_be"]))
    body.append("I have assumed %s." % joined(row["assumed"]))
    return [" ".join(body)]


def lead_text(manifest, scan):
    rows = manifest["drift"]
    if rows:
        return plural(len(rows), "possible stale reference")
    return "none across your %s" % plural(scan["inventory"]["counts"]["total"], "document")


# The only number in the headline that the tool decides is the coverage of the document set. The
# lead count sits beside it as a count of things to read, because a reader who sees nothing at all
# cannot tell a repository with no stale references from a pass that never ran.
def headline(manifest, scan):
    coverage = manifest["coverage"]
    head = "Documentation  %d of %d" % (coverage["have"], coverage["need"])
    previous = (manifest.get("previous") or {}).get("coverage") or {}
    if previous and (previous.get("have"), previous.get("need")) != (coverage["have"],
                                                                     coverage["need"]):
        head += " (was %d of %d on %s)" % (previous["have"], previous["need"],
                                           manifest["previous"]["generated_at"])
    tail = "%s  %s" % (LEAD_LABEL, lead_text(manifest, scan))
    line = "%s        %s" % (head, tail)
    return line if len(line) <= LINE_WIDTH else "%s   %s" % (head, tail)


# What the repository owes and what it does not. This is the tool's own output, the one thing in
# the report that no human has to adjudicate, so it runs first and everything else qualifies it.
def render_owed(ctx, manifest, lines):
    missing = [row for row in manifest["documents"] if row["action"] in ("write", "offer")]
    if missing:
        lines.append("")
        section("MISSING AND LOAD-BEARING", len(missing), min(len(missing), MAX_MISSING_ROWS),
                lines)
        for row in missing[:MAX_MISSING_ROWS]:
            evidence = ", ".join(row["evidence"][:2])
            reason = row["because"][0] if row["because"] else row["title"]
            if evidence:
                reason = "%s [%s]" % (reason, evidence)
            row_line(row["id"], reason, lines)
    orphans = [row for row in manifest["documents"] if row["action"] == "orphan"]
    if orphans:
        lines.append("")
        section("ORPHANED", len(orphans), min(len(orphans), MAX_ORPHAN_ROWS), lines)
        for row in orphans[:MAX_ORPHAN_ROWS]:
            row_line(row["id"], "%s is present, and nothing in this profile requires it"
                     % (row["found_at"] or row["path"]), lines)
    lines.append("")
    excluded = manifest["excluded"]
    counts = {}
    for row in excluded:
        if row["rule"] != "catalog-baseline":
            counts[row["because"]] = counts.get(row["because"], 0) + 1
    reason = "No signal in this repository selects them."
    if counts:
        reason = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    labelled("NOT APPLICABLE", ["%s. %s Full ledger: %s"
                                % (plural(len(excluded), "document"), reason, MANIFEST_REL)], lines)
    for row in near_firing(ctx, excluded)[:MAX_TRIPWIRE_ROWS]:
        labelled("", ["%s is one signal away: %s" % (row["id"], " or ".join(row["needs"]))], lines)
    lines.append("")
    labelled("NOTE", [manifest["boundary"]], lines)


# Every place the selection rests on something docdna decided for the reader, each with the number
# of documents that would change if the reader decided otherwise.
def render_assumed(manifest, lines):
    archetype = manifest["archetype"]
    if archetype["counterfactual"]:
        blocked = [row for row in manifest["documents"] if "write_block" in row]
        tail = "the document delta is in the manifest"
        if blocked:
            tail = ("and %d assure stage documents will not be written until you confirm"
                    % len(blocked))
        lines.append("")
        labelled("UNCERTAIN", ["%s scores %s points above %s, %s."
                               % (archetype["primary"], archetype["margin_points"],
                                  archetype["runner_up"]["id"], tail)], lines)
    for row in manifest["open_questions"][:MAX_OPEN_ROWS]:
        lines.append("")
        labelled("OPEN", open_sentences(row), lines)
    assumptions = manifest["assumptions"]
    if assumptions:
        lines.append("")
        shown = ["%s=%s" % (row["answer"], row["assumed"])
                 for row in assumptions[:MAX_ASSUMED_SHOWN]]
        body = ["assumed %s." % ", ".join(shown)]
        for row in assumptions[:DIAL_LIMIT]:
            if row["becomes_required"]:
                body.append(row["counterfactual"])
        labelled("ASSUMED", body, lines)


def render_stale(manifest, scan, lines):
    rows = manifest["drift"]
    if not rows:
        return
    lines.append("")
    stale_section(len(rows), min(len(rows), MAX_STALE_ROWS), lines)
    for row in rows[:MAX_STALE_ROWS]:
        row_line(row["doc"], drift_sentence(row), lines)
    labelled("", [stale_note(rows, scan)], lines)


def render_report(ctx, manifest, scan):
    lines = []
    lines.append(fact_line(ctx["signals"], manifest["archetype"],
                           manifest["archetype"]["overlays"]))
    lines.append("")
    lines.append(headline(manifest, scan))
    render_owed(ctx, manifest, lines)
    render_assumed(manifest, lines)
    render_stale(manifest, scan, lines)
    lines.append("")
    labelled("NEXT", ["  ·  ".join(next_actions(manifest, ctx))], lines)
    return "\n".join(lines) + "\n"


def next_actions(manifest, ctx):
    actions = []
    writable = [row for row in manifest["documents"]
                if row["action"] == "write" and row["producible"] == "Y"
                and "write_block" not in row]
    refresh = [row for row in manifest["documents"] if row["action"] == "refresh"]
    if writable:
        actions.append("write %s" % plural(len(writable), "derivable document"))
    if refresh:
        actions.append("refresh %s" % plural(len(refresh), "drifted document"))
    opens = manifest["open_questions"]
    top = manifest["assumptions"][0] if manifest["assumptions"] else None
    if opens and not ctx["unattended"]:
        actions.append("--answer %s" % opens[0]["answer"])
    elif top is not None and top["becomes_required"] and not ctx["unattended"]:
        actions.append("--answer %s" % top["answer"])
    actions.append(MANIFEST_REL)
    return actions[:3]


def read_prior(root):
    try:
        output_path(root, MANIFEST_REL)
    except ValueError:
        return {}
    if not safe_exists(root, MANIFEST_REL):
        return {}
    try:
        text = safe_read_text(root, MANIFEST_REL, max_bytes=MAX_CONTROL_BYTES)
    except FileTooLarge:
        raise
    except ValueError:
        return {}
    prior = safe_parse_json(text, MANIFEST_REL)
    return safe_require_manifest(prior, MANIFEST_REL, SCHEMA)


def prior_answers(prior, catalog, unattended):
    answers = {}
    if unattended:
        return answers
    for key, row in (prior.get("interview") or {}).items():
        if key in catalog["question_by_id"] and row.get("source") == "user":
            answers[key] = row["value"]
    return answers


def prior_write_status(prior):
    status = {}
    for row in prior.get("documents") or []:
        if row.get("write_status") in WRITE_STATUS:
            status[row["id"]] = row["write_status"]
    return status


def parse_answers(catalog, pairs):
    answers = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise ValueError("--answer takes key=value, got %s" % pair)
        key, value = pair.split("=", 1)
        key = key.strip()
        question = catalog["question_by_id"].get(key)
        if question is None:
            raise ValueError("--answer names %s, which is not one of %s"
                             % (key, ", ".join(sorted(catalog["question_by_id"]))))
        chosen = [item.strip() for item in value.split(",") if item.strip()]
        for item in chosen:
            if item not in question["answers"]:
                raise ValueError("--answer %s=%s is outside its answers: %s"
                                 % (key, item, ", ".join(question["answers"])))
        if not chosen:
            raise ValueError("--answer %s has no value" % key)
        answers[key] = chosen if question["multi_select"] else chosen[0]
    return answers


def run_scan(repo, exclude_dirs=None):
    if not safe_root_is_current(repo):
        raise ValueError("repository root changed before docdna_scan.py ran")
    descriptor = safe_open_root(repo)

    def enter_bound_root():
        os.fchdir(descriptor)

    command = [sys.executable, SCAN_SCRIPT, "--json", "."]
    for directory in exclude_dirs or []:
        command.extend(["--exclude-dir", directory])
    try:
        with tempfile.TemporaryFile() as output:
            process = subprocess.run(command, stdout=output, stderr=subprocess.PIPE,
                                     preexec_fn=enter_bound_root, pass_fds=(descriptor,))
            output.seek(0)
            raw = output.read(MAX_CONTROL_BYTES + 1)
    finally:
        os.close(descriptor)
    if not safe_root_is_current(repo):
        raise ValueError("repository root changed while docdna_scan.py ran")
    if process.returncode != 0:
        raise ValueError("docdna_scan.py failed: %s"
                         % process.stderr.decode("utf-8", "replace").strip())
    if len(raw) > MAX_CONTROL_BYTES:
        raise ValueError("docdna_scan.py output exceeds the %d byte limit" % MAX_CONTROL_BYTES)
    return safe_parse_json(raw.decode("utf-8", "replace"), "docdna_scan.py output")


def write_outputs(root, manifest, report):
    for rel in (REPORT_REL, MANIFEST_REL):
        output_path(root, rel)
        details = safe_path_stat(root, rel)
        if details is not None and not stat.S_ISREG(details.st_mode):
            raise ValueError("refused unsafe repository output %s" % rel)
    # The manifest is the authoritative generation marker. Write the human report first so a
    # failure cannot publish a new machine-readable decision ledger beside an old report.
    clean_report, _stats = clean_generated_text(report)
    write_repository_text(root, REPORT_REL, clean_report)
    manifest_path = output_path(root, MANIFEST_REL)
    write_repository_text(root, MANIFEST_REL,
                          json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest_path


def config_excludes(repo):
    root = repo
    if not safe_control_file_exists(root, CONFIG_REL):
        return []
    text = safe_read_text(root, CONFIG_REL, max_bytes=MAX_CONTROL_BYTES)
    raw = safe_parse_json(text, CONFIG_REL)
    safe_require_config(raw, CONFIG_REL)
    return [item for item in (raw.get("exclude_dirs") or []) if isinstance(item, str)]


def select(repo, scan_path, answer_pairs, unattended, exclude_dirs=None):
    root = safe_bind_root(os.path.abspath(repo))
    try:
        return select_bound(root, scan_path, answer_pairs, unattended, exclude_dirs)
    finally:
        root.close()


def select_bound(root, scan_path, answer_pairs, unattended, exclude_dirs=None):
    catalog = load_catalog()
    errors = check_invariants(catalog)
    if errors:
        raise ValueError("catalog invariants failed\n  " + "\n  ".join(errors))
    excludes = list(exclude_dirs or []) + config_excludes(root)
    scan = (safe_parse_json(safe_read_bounded_path(scan_path, MAX_CONTROL_BYTES), scan_path)
            if scan_path else run_scan(root, excludes))
    safe_require_scan(scan, "scan", SCHEMA)
    scan_root = os.path.abspath(scan["root"])
    if os.path.realpath(scan_root) != os.path.realpath(root):
        raise ValueError("scan root %s does not match repository %s" % (scan_root, root))
    safe_require_root_identity(root, scan.get("root_identity"), "scan")
    if scan_path:
        current = run_scan(root, excludes)
        safe_require_scan(current, "current scan", SCHEMA)
        if scan.get("content_fingerprint") != current.get("content_fingerprint"):
            raise ValueError("imported scan does not match the current repository contents")
        current["generated"] = scan["generated"]
        scan = current
    overrides = parse_answers(catalog, answer_pairs)
    prior = read_prior(root)
    states, found = document_states(catalog, scan, root)
    ctx = {"signals": signal_map(catalog, scan), "answers": {}, "archetype": "unknown",
           "overlays": [], "docstate": states, "unattended": bool(unattended)}
    archetype = resolve_archetype(ctx, catalog)
    ctx["archetype"] = archetype["primary"]
    answers = resolve_answers(ctx, catalog, overrides,
                              prior_answers(prior, catalog, unattended))
    ctx, base = engine_for(ctx, catalog, answer_values(answers))
    ctx["unattended"] = bool(unattended)
    dial = counterfactual_rows(ctx, catalog, answers, base)
    opens = open_question_rows(ctx, catalog, answers, base)
    archetype["document_delta"] = archetype_counterfactual(ctx, catalog, answers, base, archetype)
    blocked = ("assure",) if archetype["confidence"] == "low" else ()
    documents, excluded = build_rows(ctx, catalog, base, answers, states, found, scan,
                                     prior_write_status(prior), blocked)
    manifest = build_manifest(ctx, catalog, scan, answers, archetype, base, dial, opens,
                              documents, excluded, prior, unattended)
    report = render_report(ctx, manifest, scan)
    write_outputs(root, manifest, report)
    return manifest, report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Select the document set this repository owes and "
                                                 "write .docdna/manifest.json plus DOCDNA.md.")
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--json", action="store_true", help="emit the manifest instead of the report")
    parser.add_argument("--answer", action="append", metavar="KEY=VALUE",
                        help="record an interview answer, repeatable")
    parser.add_argument("--unattended", action="store_true",
                        help="never surface a question; take every unanswered question at its default")
    parser.add_argument("--scan", metavar="PATH",
                        help="validate scanner JSON, reproduce a fresh scan, and reject changed contents")
    parser.add_argument("--exclude-dir", action="append", metavar="DIR",
                        help="keep a directory out of the document inventory and drift pass, "
                             "for vendored or fixture repositories that carry their own "
                             "documentation, repeatable")
    args = parser.parse_args(argv)

    try:
        manifest, report = select(args.repo, args.scan, args.answer, args.unattended,
                                  args.exclude_dir)
    except KeyError as error:
        sys.stderr.write("docdna_select: scan or catalog is missing key %s\n" % error)
        return 2
    except (OSError, ValueError) as error:
        sys.stderr.write("docdna_select: %s\n" % error)
        return 2
    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
