import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "skill" / "catalog"
TEMPLATE_DIR = ROOT / "skill" / "templates"
SELECT_PATH = ROOT / "skill" / "scripts" / "docdna_select.py"

SCHEMA = 1

DOCUMENT_TOTAL = 60
PRODUCIBLE_TOTALS = {"Y": 41, "M": 19, "R": 0}
STAGE_TOTALS = {"frame": 4, "decide": 4, "design": 5, "build": 14, "verify": 4, "assure": 9,
                "operate": 11, "serve": 2, "govern": 6, "retire": 1}
STAGE_PRODUCIBLE = {("assure", "M"): 4, ("assure", "Y"): 5,
                    ("build", "M"): 2, ("build", "Y"): 12,
                    ("decide", "M"): 1, ("decide", "Y"): 3,
                    ("design", "Y"): 5,
                    ("frame", "Y"): 4,
                    ("govern", "M"): 1, ("govern", "Y"): 5,
                    ("operate", "M"): 9, ("operate", "Y"): 2,
                    ("retire", "Y"): 1,
                    ("serve", "M"): 1, ("serve", "Y"): 1,
                    ("verify", "M"): 1, ("verify", "Y"): 3}

SIGNAL_TOTAL = 132
FAMILIES = ("a11y", "ai", "arch", "data", "deploy", "docs", "iface", "jur", "ops", "proc",
            "qual", "scale", "sec", "supply", "users")
FAMILY_TOTALS = {"a11y": 5, "ai": 8, "arch": 10, "data": 11, "deploy": 9, "docs": 13, "iface": 6,
                 "jur": 11, "ops": 10, "proc": 8, "qual": 6, "scale": 6, "sec": 12, "supply": 8,
                 "users": 9}

RULE_TOTAL = 88
PRIMARY_TOTAL = 8
OVERLAY_TOTAL = 5
QUESTION_TOTAL = 8

STAGES = ("frame", "decide", "design", "build", "verify", "assure", "operate", "serve", "govern",
          "retire")
DURABILITIES = ("durable", "evidence", "transient")
SCOPES = ("repo", "product", "org")
PRODUCIBLES = ("Y", "M", "R")
BACKFILLABILITIES = ("H", "P", "N")
SENSITIVITIES = ("public", "internal", "restricted")
CADENCE_WORDS = ("none", "on-release", "on-change")
CADENCE_ISO = re.compile(r"^P(?=\w)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+S)?)?$")
SIGNAL_STATES = ("present", "absent", "unknown", "hint")
VERDICTS = ("not-applicable", "optional", "recommended", "required")
LAYERS = ("baseline", "signal", "overlay", "answer", "override")
EFFECTS = ("require", "recommend", "optionalize", "exclude", "ask", "note")
SOFT_EFFECTS = ("ask", "note")
DOC_STATES = ("present", "absent", "present-fresh", "present-drifted", "present-stub",
              "present-elsewhere")

EM_DASH = "\u2014"
EN_DASH = "\u2013"

OPERATORS = ("all", "any", "not", "signal", "answer", "archetype", "overlay", "document",
             "always", "never")
MODIFIERS = {"all": (), "any": (), "not": (), "always": (), "never": (), "archetype": (),
             "overlay": (), "signal": ("is", "gte"), "answer": ("is", "in"),
             "document": ("state",)}


def load(name):
    with open(str(CATALOG_DIR / ("%s.json" % name)), encoding="utf-8") as handle:
        return json.load(handle)


def load_select():
    spec = importlib.util.spec_from_file_location("docdna_select", SELECT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def counted(items, key):
    counts = {}
    for item in items:
        counts[key(item)] = counts.get(key(item), 0) + 1
    return counts


def template_path(doc):
    return TEMPLATE_DIR / ("%s-%s.md" % (doc["stage"], doc["id"].split(".", 1)[-1]))


def hint_in(node):
    if not isinstance(node, dict):
        return False
    for key in ("all", "any"):
        if key in node:
            return any(hint_in(child) for child in node[key] or [])
    if "not" in node:
        return hint_in(node["not"])
    return "signal" in node and node.get("is") == "hint"


def answer_in(node):
    if not isinstance(node, dict):
        return False
    for key in ("all", "any"):
        if key in node:
            return any(answer_in(child) for child in node[key] or [])
    if "not" in node:
        return answer_in(node["not"])
    return "answer" in node


class Catalog(object):
    def __init__(self):
        self.signals = load("signals")["signals"]
        self.documents = load("documents")["documents"]
        self.rules = load("rules")["rules"]
        self.archetypes = load("archetypes")
        self.questions = load("interview")["questions"]
        self.signal_ids = set(item["id"] for item in self.signals)
        self.doc_ids = set(item["id"] for item in self.documents)
        self.question_ids = set(item["id"] for item in self.questions)
        self.primary_ids = set(item["id"] for item in self.archetypes["primaries"])
        self.overlay_ids = set(item["id"] for item in self.archetypes["overlays"])
        self.question_by_id = dict((item["id"], item) for item in self.questions)
        self.doc_by_id = dict((item["id"], item) for item in self.documents)

    def predicates(self):
        found = []
        for signal in self.signals:
            if signal.get("gate"):
                self.walk(signal["gate"], "signals.json %s.gate" % signal["id"], found)
        for doc in self.documents:
            self.walk(doc["selects_on"], "documents.json %s.selects_on" % doc["id"], found)
        for rule in self.rules:
            self.walk(rule["when"], "rules.json %s.when" % rule["id"], found)
            if rule.get("revisit_when"):
                self.walk(rule["revisit_when"], "rules.json %s.revisit_when" % rule["id"], found)
        for primary in self.archetypes["primaries"]:
            for weight in primary["weights"]:
                self.walk(weight["when"], "archetypes.json %s.weights" % primary["id"], found)
        for overlay in self.archetypes["overlays"]:
            self.walk(overlay["when"], "archetypes.json %s.when" % overlay["id"], found)
        for question in self.questions:
            for entry in question.get("default_from") or []:
                self.walk(entry["when"], "interview.json %s.default_from" % question["id"], found)
        return found

    def walk(self, node, where, found):
        found.append((where, node))
        if not isinstance(node, dict):
            return
        for key in ("all", "any"):
            if key in node and isinstance(node[key], list):
                for child in node[key]:
                    self.walk(child, where, found)
        if "not" in node:
            self.walk(node["not"], where, found)

    def cites(self):
        found = []
        for rule in self.rules:
            for token in rule.get("cite") or []:
                found.append(("rules.json %s.cite" % rule["id"], token))
        for question in self.questions:
            for entry in question.get("default_from") or []:
                for token in entry.get("cite") or []:
                    found.append(("interview.json %s.default_from.cite" % question["id"], token))
        return found

    def document_references(self):
        found = []
        for rule in self.rules:
            for doc_id in rule.get("documents") or []:
                found.append(("rules.json %s.documents" % rule["id"], doc_id))
        for overlay in self.archetypes["overlays"]:
            for doc_id in overlay.get("adds") or []:
                found.append(("archetypes.json %s.adds" % overlay["id"], doc_id))
        for where, node in self.predicates():
            if isinstance(node, dict) and "document" in node:
                found.append((where, node["document"]))
        return found


CAT = Catalog()


class ShapeTests(unittest.TestCase):
    def test_every_file_declares_schema_one(self):
        for name in ("signals", "documents", "rules", "archetypes", "interview"):
            self.assertEqual(load(name).get("schema"), SCHEMA, "%s.json" % name)

    def test_every_collection_is_sorted_by_id(self):
        collections = [("signals.json", CAT.signals), ("documents.json", CAT.documents),
                       ("rules.json", CAT.rules), ("interview.json", CAT.questions),
                       ("archetypes.json primaries", CAT.archetypes["primaries"]),
                       ("archetypes.json overlays", CAT.archetypes["overlays"])]
        for name, items in collections:
            ids = [item["id"] for item in items]
            self.assertEqual(ids, sorted(ids), "%s is not sorted by id" % name)

    def test_collection_sizes_are_the_decision_not_a_drawer(self):
        self.assertEqual(len(CAT.signals), SIGNAL_TOTAL)
        self.assertEqual(len(CAT.documents), DOCUMENT_TOTAL)
        self.assertEqual(len(CAT.rules), RULE_TOTAL)
        self.assertEqual(len(CAT.archetypes["primaries"]), PRIMARY_TOTAL)
        self.assertEqual(len(CAT.archetypes["overlays"]), OVERLAY_TOTAL)
        self.assertEqual(len(CAT.questions), QUESTION_TOTAL)


class DocumentCountTests(unittest.TestCase):
    def test_exactly_sixty_entries(self):
        self.assertEqual(len(CAT.documents), DOCUMENT_TOTAL)
        self.assertEqual(len(CAT.doc_ids), DOCUMENT_TOTAL)

    def test_producible_split_is_forty_one_y_nineteen_m_zero_r(self):
        counts = counted(CAT.documents, lambda doc: doc["producible"])
        self.assertEqual(counts.get("Y", 0), PRODUCIBLE_TOTALS["Y"])
        self.assertEqual(counts.get("M", 0), PRODUCIBLE_TOTALS["M"])
        self.assertEqual(counts.get("R", 0), PRODUCIBLE_TOTALS["R"])
        self.assertEqual(sum(counts.values()), DOCUMENT_TOTAL)

    def test_per_stage_counts(self):
        counts = counted(CAT.documents, lambda doc: doc["stage"])
        self.assertEqual(counts, STAGE_TOTALS)
        self.assertEqual(sum(STAGE_TOTALS.values()), DOCUMENT_TOTAL)

    def test_per_stage_producible_counts(self):
        counts = counted(CAT.documents, lambda doc: (doc["stage"], doc["producible"]))
        self.assertEqual(counts, STAGE_PRODUCIBLE)
        self.assertEqual(sum(STAGE_PRODUCIBLE.values()), DOCUMENT_TOTAL)


class SignalFamilyTests(unittest.TestCase):
    def test_one_hundred_thirty_two_signals(self):
        self.assertEqual(len(CAT.signals), SIGNAL_TOTAL)
        self.assertEqual(len(CAT.signal_ids), SIGNAL_TOTAL)

    def test_exactly_the_fifteen_families(self):
        families = set(signal["family"] for signal in CAT.signals)
        self.assertEqual(families, set(FAMILIES))
        self.assertEqual(counted(CAT.signals, lambda signal: signal["family"]), FAMILY_TOTALS)
        self.assertEqual(sum(FAMILY_TOTALS.values()), SIGNAL_TOTAL)

    def test_family_is_the_id_prefix(self):
        for signal in CAT.signals:
            prefix = signal["id"].split(".", 1)[0]
            self.assertEqual(prefix, signal["family"],
                             "%s sits in family %s" % (signal["id"], signal["family"]))

    def test_pass_and_detector_vocabulary(self):
        kinds = ("path", "manifest", "grep", "git", "derived")
        for signal in CAT.signals:
            self.assertIn(signal["pass"], (1, 2, 3), signal["id"])
            if signal.get("refuses_to_guess"):
                self.assertIsNone(signal["detect"], signal["id"])
                self.assertIn(signal["question"], CAT.question_ids, signal["id"])
            else:
                self.assertIsNotNone(signal["detect"], signal["id"])
                self.assertIn(signal["detect"]["kind"], kinds, signal["id"])
            self.assertIn(signal["max_state"], SIGNAL_STATES, signal["id"])


class HintDisciplineTests(unittest.TestCase):
    def test_every_jurisdiction_signal_is_capped_at_hint(self):
        jur = [signal for signal in CAT.signals if signal["family"] == "jur"]
        self.assertEqual(len(jur), FAMILY_TOTALS["jur"])
        for signal in jur:
            self.assertEqual(signal.get("max_state"), "hint", signal["id"])

    def test_ai_decides_about_people_does_not_exist(self):
        self.assertNotIn("ai.decides_about_people", CAT.signal_ids)
        for signal in CAT.signals:
            self.assertNotIn("decides_about_people", signal["id"])

    def test_q4_takes_no_default_from_a_signal(self):
        question = CAT.question_by_id["q4_decides_about_people"]
        self.assertEqual(question.get("default_from"), [])
        self.assertEqual(question["fallback"], "no")
        self.assertIn("no", question["answers"])
        self.assertTrue(question.get("no_signal_may_set"))

    def test_no_rule_tests_hint_unless_it_only_asks_or_notes(self):
        consumers = [rule for rule in CAT.rules if hint_in(rule["when"])]
        self.assertTrue(consumers)
        for rule in consumers:
            self.assertIn(rule["effect"], SOFT_EFFECTS,
                          "%s consumes a hint and sets effect=%s" % (rule["id"], rule["effect"]))


class PredicateGrammarTests(unittest.TestCase):
    def test_every_node_carries_exactly_one_operator_key(self):
        for where, node in CAT.predicates():
            self.assertIsInstance(node, dict, where)
            operators = [key for key in node if key in OPERATORS]
            self.assertEqual(len(operators), 1,
                             "%s holds a node with keys %s" % (where, sorted(node)))

    def test_no_node_carries_a_key_outside_its_operator_vocabulary(self):
        for where, node in CAT.predicates():
            operator = [key for key in node if key in OPERATORS][0]
            allowed = set(MODIFIERS[operator]) | set([operator])
            extra = sorted(key for key in node if key not in allowed)
            self.assertEqual(extra, [], "%s node %s carries %s" % (where, operator, extra))

    def test_every_signal_is_value_is_one_of_the_four_states(self):
        for where, node in CAT.predicates():
            if "signal" not in node or "is" not in node:
                continue
            self.assertIn(node["is"], SIGNAL_STATES, "%s tests %s" % (where, node["is"]))

    def test_gte_is_an_integer_and_document_state_is_known(self):
        for where, node in CAT.predicates():
            if "gte" in node:
                self.assertIsInstance(node["gte"], int, where)
                self.assertIn("signal", node, where)
            if "document" in node and "state" in node:
                self.assertIn(node["state"], DOC_STATES, where)

    def test_combinators_take_lists(self):
        for where, node in CAT.predicates():
            for key in ("all", "any"):
                if key in node:
                    self.assertIsInstance(node[key], list, where)
            if "not" in node:
                self.assertIsInstance(node["not"], dict, where)


class ReferenceTests(unittest.TestCase):
    def test_every_signal_id_in_a_predicate_resolves(self):
        for where, node in CAT.predicates():
            if "signal" in node:
                self.assertIn(node["signal"], CAT.signal_ids, where)

    def test_every_signal_id_in_a_cite_resolves(self):
        for where, token in CAT.cites():
            self.assertTrue(token in CAT.signal_ids or token in CAT.question_ids,
                            "%s cites %s, neither a signal nor a question" % (where, token))

    def test_every_document_id_referenced_resolves(self):
        for where, doc_id in CAT.document_references():
            self.assertIn(doc_id, CAT.doc_ids, where)

    def test_every_answer_and_archetype_and_overlay_reference_resolves(self):
        for where, node in CAT.predicates():
            if "answer" in node:
                self.assertIn(node["answer"], CAT.question_ids, where)
                question = CAT.question_by_id[node["answer"]]
                wanted = node.get("in") or ([node["is"]] if "is" in node else [])
                for value in wanted:
                    self.assertIn(value, question["answers"], where)
            if "archetype" in node:
                self.assertTrue(node["archetype"] in CAT.primary_ids
                                or node["archetype"] == "unknown", where)
            if "overlay" in node:
                self.assertIn(node["overlay"], CAT.overlay_ids, where)

    def test_archetype_requires_absent_names_real_signals(self):
        for primary in CAT.archetypes["primaries"]:
            for signal_id in primary.get("requires_absent") or []:
                self.assertIn(signal_id, CAT.signal_ids, primary["id"])

    def test_signal_gate_and_derived_dependencies_resolve(self):
        for signal in CAT.signals:
            detect = signal.get("detect") or {}
            for dependency in detect.get("depends_on") or []:
                self.assertIn(dependency, CAT.signal_ids, signal["id"])


class InvariantTests(unittest.TestCase):
    def test_i1_no_template_ships_for_a_manifest_only_or_refused_entry(self):
        for doc in CAT.documents:
            if doc["producible"] in ("M", "R"):
                self.assertFalse(template_path(doc).exists(),
                                 "I1 %s is producible %s and ships %s"
                                 % (doc["id"], doc["producible"], template_path(doc)))

    def test_i2_no_reference_names_a_document_outside_the_catalog(self):
        for where, doc_id in CAT.document_references():
            self.assertIn(doc_id, CAT.doc_ids, "I2 %s names %s" % (where, doc_id))

    def test_i3_no_predicate_or_cite_names_a_signal_outside_the_registry(self):
        for where, node in CAT.predicates():
            if "signal" in node:
                self.assertIn(node["signal"], CAT.signal_ids, "I3 %s" % where)
        for where, token in CAT.cites():
            self.assertTrue(token in CAT.signal_ids or token in CAT.question_ids, "I3 %s" % where)

    def test_i4_a_hint_never_sets_a_verdict(self):
        for rule in CAT.rules:
            if hint_in(rule["when"]):
                self.assertIn(rule["effect"], SOFT_EFFECTS, "I4 %s" % rule["id"])

    def test_i5_q4_carries_no_default_from(self):
        self.assertEqual(CAT.question_by_id["q4_decides_about_people"].get("default_from"), [])
        for question in CAT.questions:
            if question.get("no_signal_may_set"):
                self.assertEqual(question.get("default_from"), [], question["id"])

    def test_i6_no_signal_alone_makes_a_refused_document_required(self):
        for rule in CAT.rules:
            if rule["effect"] not in ("require", "recommend"):
                continue
            if answer_in(rule["when"]):
                continue
            for doc_id in rule.get("documents") or []:
                doc = CAT.doc_by_id[doc_id]
                self.assertNotEqual(doc["producible"], "R",
                                    "I6 %s sets %s on refused %s with no answer term"
                                    % (rule["id"], rule["effect"], doc_id))

    def test_i7_every_exclusion_carries_because_cite_and_revisit_when(self):
        excluders = [rule for rule in CAT.rules if rule["effect"] == "exclude"]
        self.assertTrue(excluders)
        for rule in excluders:
            self.assertTrue(rule.get("because"), "I7 %s has no because" % rule["id"])
            self.assertTrue(rule.get("cite"), "I7 %s has no cite" % rule["id"])
            self.assertTrue(rule.get("revisit_when"), "I7 %s has no revisit_when" % rule["id"])

    def test_i8_every_enum_field_sits_inside_its_enum(self):
        enums = [("stage", STAGES), ("durability", DURABILITIES), ("scope", SCOPES),
                 ("producible", PRODUCIBLES), ("backfillability", BACKFILLABILITIES),
                 ("sensitivity", SENSITIVITIES), ("baseline_verdict", VERDICTS)]
        for doc in CAT.documents:
            for field, allowed in enums:
                self.assertIn(doc.get(field), allowed, "I8 %s.%s" % (doc["id"], field))
            cadence = doc.get("cadence")
            self.assertTrue(cadence in CADENCE_WORDS or CADENCE_ISO.match(str(cadence)),
                            "I8 %s sets cadence=%s" % (doc["id"], cadence))
        for rule in CAT.rules:
            self.assertIn(rule.get("layer"), LAYERS, "I8 %s.layer" % rule["id"])
            self.assertIn(rule.get("effect"), EFFECTS, "I8 %s.effect" % rule["id"])
        for question in CAT.questions:
            fallback = question["fallback"]
            values = fallback if isinstance(fallback, list) else [fallback]
            for value in values:
                self.assertIn(value, question["answers"], "I8 %s.fallback" % question["id"])

    def test_i9_no_two_entries_share_an_id(self):
        for name, items in (("documents.json", CAT.documents), ("rules.json", CAT.rules),
                            ("signals.json", CAT.signals), ("interview.json", CAT.questions),
                            ("primaries", CAT.archetypes["primaries"]),
                            ("overlays", CAT.archetypes["overlays"])):
            ids = [item["id"] for item in items]
            self.assertEqual(len(ids), len(set(ids)), "I9 %s repeats an id" % name)

    def test_i10_product_and_org_scope_always_ask_for_the_system_of_record(self):
        wider = [doc for doc in CAT.documents if doc["scope"] in ("product", "org")]
        self.assertTrue(wider)
        for doc in wider:
            self.assertEqual(doc.get("system_of_record"), "ask",
                             "I10 %s is %s scoped" % (doc["id"], doc["scope"]))

    def test_the_selector_agrees_that_every_invariant_holds(self):
        select = load_select()
        self.assertEqual(select.check_invariants(select.load_catalog()), [])


class ProseTests(unittest.TestCase):
    def test_every_rule_because_is_a_finished_sentence(self):
        for rule in CAT.rules:
            because = rule["because"]
            self.assertTrue(because.endswith("."), "%s: %s" % (rule["id"], because))
            self.assertNotIn("{", because, rule["id"])
            self.assertNotIn("%s", because, rule["id"])

    def test_no_em_dash_or_en_dash_anywhere_in_the_catalog(self):
        for name in ("signals", "documents", "rules", "archetypes", "interview"):
            text = (CATALOG_DIR / ("%s.json" % name)).read_text(encoding="utf-8")
            self.assertNotIn(EM_DASH, text, "%s.json holds an em dash" % name)
            self.assertNotIn(EN_DASH, text, "%s.json holds an en dash" % name)


if __name__ == "__main__":
    unittest.main()
