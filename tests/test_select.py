import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELECT_PATH = ROOT / "skill" / "scripts" / "docdna_select.py"
SCAN_PATH = ROOT / "skill" / "scripts" / "docdna_scan.py"
FIXTURE_DIR = ROOT / "tests" / "fixtures"

DOC = "build.readme"

SCAN_CACHE = {}


def load_select():
    spec = importlib.util.spec_from_file_location("docdna_select", SELECT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SELECT = load_select()


def signal(signal_id, state="present", hits=1, evidence=None):
    return {"id": signal_id, "state": state, "hits": hits, "label": signal_id,
            "evidence": evidence or []}


def signals(*rows):
    return dict((row["id"], row) for row in rows)


def context(signal_rows=None, answers=None, archetype="unknown", overlays=None, docstate=None):
    return {"signals": signal_rows or {}, "answers": answers or {}, "archetype": archetype,
            "overlays": overlays or [], "docstate": docstate or {}, "unattended": False}


def rule(rule_id, effect, when=None, layer="signal", force=False, documents=None):
    return {"id": rule_id, "layer": layer, "effect": effect, "force": force,
            "when": when or {"always": True}, "because": "Rule %s fired." % rule_id,
            "cite": [], "documents": documents or [DOC]}


def one_doc_catalog(rules, baseline="recommended"):
    return {"documents": [{"id": DOC, "selects_on": {"always": True},
                           "baseline_verdict": baseline}],
            "ordered_rules": rules}


def copy_fixture(name, tmp):
    target = Path(tmp) / name
    shutil.copytree(str(FIXTURE_DIR / name), str(target))
    return target


def scan_file(name, root, tmp):
    if name not in SCAN_CACHE:
        proc = subprocess.run([sys.executable, str(SCAN_PATH), "--json", str(root)],
                              check=True, capture_output=True)
        SCAN_CACHE[name] = json.loads(proc.stdout.decode("utf-8"))
    payload = dict(SCAN_CACHE[name])
    payload["root"] = str(root)
    path = Path(tmp) / "scan.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def clear_outputs(root):
    shutil.rmtree(str(root / ".docdna"), ignore_errors=True)
    report = root / "DOCDNA.md"
    if report.exists():
        report.unlink()


class PredicateTests(unittest.TestCase):
    def setUp(self):
        self.ctx = context(
            signal_rows=signals(signal("sec.authn"), signal("data.pii", "present", 4),
                                signal("arch.service", "absent", 0),
                                signal("supply.sbom", "unknown", 0),
                                signal("jur.eu", "hint", 9)),
            answers={"q1_users": "customers", "q5_markets": ["eu-eea", "us"]},
            archetype="commercial-saas", overlays=["ai-system"],
            docstate={"decide.adr": "present-fresh", "govern.manifest": "present-drifted",
                      "frame.glossary": "absent"})

    def test_signal_is_matches_the_exact_state(self):
        for state in ("present", "absent", "unknown", "hint"):
            node = {"signal": "sec.authn", "is": state}
            self.assertEqual(SELECT.predicate(self.ctx, node), state == "present")

    def test_bare_signal_means_present(self):
        self.assertTrue(SELECT.predicate(self.ctx, {"signal": "sec.authn"}))
        self.assertFalse(SELECT.predicate(self.ctx, {"signal": "arch.service"}))
        self.assertFalse(SELECT.predicate(self.ctx, {"signal": "jur.eu"}))

    def test_gte_counts_hits_on_a_present_signal(self):
        self.assertTrue(SELECT.predicate(self.ctx, {"signal": "data.pii", "gte": 1}))
        self.assertTrue(SELECT.predicate(self.ctx, {"signal": "data.pii", "gte": 4}))
        self.assertFalse(SELECT.predicate(self.ctx, {"signal": "data.pii", "gte": 5}))

    def test_a_hint_does_not_satisfy_is_present(self):
        self.assertEqual(self.ctx["signals"]["jur.eu"]["state"], "hint")
        self.assertFalse(SELECT.predicate(self.ctx, {"signal": "jur.eu", "is": "present"}))
        self.assertTrue(SELECT.predicate(self.ctx, {"signal": "jur.eu", "is": "hint"}))

    def test_a_hint_does_not_satisfy_gte_however_many_hits_it_carries(self):
        self.assertEqual(self.ctx["signals"]["jur.eu"]["hits"], 9)
        for threshold in (1, 2, 9):
            self.assertFalse(SELECT.predicate(self.ctx, {"signal": "jur.eu", "gte": threshold}),
                             "gte %d was satisfied by a hint" % threshold)

    def test_unknown_is_never_read_as_absence_of_the_thing(self):
        self.assertFalse(SELECT.predicate(self.ctx, {"signal": "supply.sbom", "is": "present"}))
        self.assertFalse(SELECT.predicate(self.ctx, {"signal": "supply.sbom", "is": "absent"}))
        self.assertTrue(SELECT.predicate(self.ctx, {"signal": "supply.sbom", "is": "unknown"}))

    def test_all_and_any_and_not(self):
        yes = {"signal": "sec.authn", "is": "present"}
        no = {"signal": "arch.service", "is": "present"}
        self.assertTrue(SELECT.predicate(self.ctx, {"all": [yes, yes]}))
        self.assertFalse(SELECT.predicate(self.ctx, {"all": [yes, no]}))
        self.assertTrue(SELECT.predicate(self.ctx, {"any": [no, yes]}))
        self.assertFalse(SELECT.predicate(self.ctx, {"any": [no, no]}))
        self.assertTrue(SELECT.predicate(self.ctx, {"not": no}))
        self.assertFalse(SELECT.predicate(self.ctx, {"not": yes}))

    def test_empty_all_is_true_and_empty_any_is_false(self):
        self.assertTrue(SELECT.predicate(self.ctx, {"all": []}))
        self.assertFalse(SELECT.predicate(self.ctx, {"any": []}))

    def test_answer_in_and_answer_is(self):
        self.assertTrue(SELECT.predicate(self.ctx, {"answer": "q1_users",
                                                    "in": ["customers", "public"]}))
        self.assertFalse(SELECT.predicate(self.ctx, {"answer": "q1_users", "in": ["nobody"]}))
        self.assertTrue(SELECT.predicate(self.ctx, {"answer": "q1_users", "is": "customers"}))

    def test_a_multi_select_answer_matches_on_any_chosen_value(self):
        self.assertTrue(SELECT.predicate(self.ctx, {"answer": "q5_markets", "in": ["eu-eea"]}))
        self.assertTrue(SELECT.predicate(self.ctx, {"answer": "q5_markets", "in": ["us"]}))
        self.assertFalse(SELECT.predicate(self.ctx, {"answer": "q5_markets", "in": ["canada"]}))

    def test_an_unrecorded_answer_is_false_rather_than_an_error(self):
        self.assertFalse(SELECT.predicate(self.ctx, {"answer": "q4_decides_about_people",
                                                     "in": ["no"]}))

    def test_archetype_and_overlay(self):
        self.assertTrue(SELECT.predicate(self.ctx, {"archetype": "commercial-saas"}))
        self.assertFalse(SELECT.predicate(self.ctx, {"archetype": "oss-library"}))
        self.assertTrue(SELECT.predicate(self.ctx, {"overlay": "ai-system"}))
        self.assertFalse(SELECT.predicate(self.ctx, {"overlay": "shipped-artifact"}))

    def test_document_state(self):
        self.assertTrue(SELECT.predicate(self.ctx, {"document": "decide.adr", "state": "present"}))
        self.assertTrue(SELECT.predicate(self.ctx, {"document": "govern.manifest",
                                                    "state": "present"}))
        self.assertTrue(SELECT.predicate(self.ctx, {"document": "govern.manifest",
                                                    "state": "present-drifted"}))
        self.assertFalse(SELECT.predicate(self.ctx, {"document": "frame.glossary",
                                                     "state": "present"}))
        self.assertTrue(SELECT.predicate(self.ctx, {"document": "verify.dod", "state": "absent"}))

    def test_always_and_never(self):
        self.assertTrue(SELECT.predicate(self.ctx, {"always": True}))
        self.assertFalse(SELECT.predicate(self.ctx, {"always": False}))
        self.assertFalse(SELECT.predicate(self.ctx, {"never": True}))
        self.assertTrue(SELECT.predicate(self.ctx, {"never": False}))

    def test_a_missing_signal_id_is_a_hard_error(self):
        with self.assertRaises(ValueError):
            SELECT.predicate(self.ctx, {"signal": "sec.no_such_signal", "is": "present"})

    def test_an_unknown_operator_is_a_hard_error(self):
        with self.assertRaises(ValueError):
            SELECT.predicate(self.ctx, {"maybe": "sec.authn"})
        with self.assertRaises(ValueError):
            SELECT.predicate(self.ctx, {})

    def test_evaluation_is_total(self):
        for node in ({"signal": "supply.sbom", "is": "present"}, {"all": []}, {"any": []},
                     {"not": {"signal": "supply.sbom", "is": "present"}}):
            self.assertIn(SELECT.predicate(self.ctx, node), (True, False))


class EscalationTests(unittest.TestCase):
    def setUp(self):
        self.ctx = context(signal_rows=signals(signal("sec.authn")))

    def run_rules(self, rules, baseline="recommended"):
        result = SELECT.run_engine(self.ctx, one_doc_catalog(rules, baseline))
        return result, result["documents"][DOC]

    def test_baseline_verdict_is_the_starting_point(self):
        _, entry = self.run_rules([])
        self.assertEqual(entry["verdict"], "recommended")
        self.assertEqual(entry["records"][0]["rule"], "catalog-baseline")

    def test_a_rule_may_raise_a_verdict_without_force(self):
        _, entry = self.run_rules([rule("R-UP", "require")], "optional")
        self.assertEqual(entry["verdict"], "required")
        self.assertEqual(entry["rules"], ["R-UP"])
        self.assertEqual(entry["forced"], [])
        self.assertEqual(entry["blocked"], [])

    def test_a_rule_may_not_lower_a_verdict_without_force(self):
        _, entry = self.run_rules([rule("R-DOWN", "optionalize")], "required")
        self.assertEqual(entry["verdict"], "required")
        self.assertEqual(entry["blocked"], ["R-DOWN"])
        self.assertEqual(entry["rules"], [])

    def test_an_exclusion_cannot_delete_a_required_document_by_accident(self):
        _, entry = self.run_rules([rule("R-EXCLUDE", "exclude")], "required")
        self.assertEqual(entry["verdict"], "required")
        self.assertEqual(entry["blocked"], ["R-EXCLUDE"])

    def test_force_true_is_the_only_way_down_and_it_is_recorded(self):
        _, entry = self.run_rules([rule("R-DOWN", "optionalize", force=True)], "required")
        self.assertEqual(entry["verdict"], "optional")
        self.assertEqual(entry["forced"], ["R-DOWN"])
        self.assertEqual(entry["rules"], ["R-DOWN"])

    def test_every_downgrade_pair_is_refused_and_every_upgrade_pair_lands(self):
        order = ["not-applicable", "optional", "recommended", "required"]
        effects = {"not-applicable": "exclude", "optional": "optionalize",
                   "recommended": "recommend", "required": "require"}
        for baseline in order:
            for target in order:
                _, entry = self.run_rules([rule("R-MOVE", effects[target])], baseline)
                lowers = order.index(target) < order.index(baseline)
                self.assertEqual(entry["verdict"], baseline if lowers else target,
                                 "%s to %s" % (baseline, target))
                self.assertEqual(entry["blocked"], ["R-MOVE"] if lowers else [])

    def test_a_rule_whose_predicate_is_false_never_runs(self):
        never = rule("R-QUIET", "require", when={"never": True})
        _, entry = self.run_rules([never], "optional")
        self.assertEqual(entry["verdict"], "optional")
        self.assertEqual(entry["rules"], [])

    def test_ask_and_note_carry_no_verdict(self):
        result, entry = self.run_rules([rule("R-ASK", "ask"), rule("R-NOTE", "note")], "optional")
        self.assertEqual(entry["verdict"], "optional")
        self.assertEqual([row["rule"] for row in result["questions"]], ["R-ASK"])
        self.assertEqual([row["rule"] for row in result["notes"]], ["R-NOTE"])
        self.assertEqual([row["rule"] for row in entry["notes"]], ["R-ASK", "R-NOTE"])

    def test_a_forced_override_runs_after_the_signal_layer_that_raised_the_verdict(self):
        rules = [rule("R-RAISE", "require", layer="signal"),
                 rule("R-DROP", "optionalize", layer="override", force=True)]
        _, entry = self.run_rules(rules, "optional")

        self.assertEqual(entry["rules"], ["R-RAISE", "R-DROP"])
        self.assertEqual(entry["forced"], ["R-DROP"])
        self.assertEqual(entry["verdict"], "optional")

    def test_the_real_catalog_orders_rules_by_layer_then_id(self):
        catalog = SELECT.load_catalog()
        ordered = catalog["ordered_rules"]
        keys = [(SELECT.LAYER_RANK[item["layer"]], item["id"]) for item in ordered]

        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(ordered), len(catalog["rules"]))


class ArchetypeTests(unittest.TestCase):
    def setUp(self):
        self.catalog = SELECT.load_catalog()

    def scored_for(self, name):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture(name, tmp)
            path = scan_file(name, root, tmp)
            scan = json.loads(path.read_text(encoding="utf-8"))
        ctx = context(signal_rows=SELECT.signal_map(self.catalog, scan))
        return ctx, SELECT.score_archetypes(ctx, self.catalog)

    def test_solo_cli_resolves_to_solo_utility(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture("solo_cli", tmp)
            manifest, _ = SELECT.select(str(root), str(scan_file("solo_cli", root, tmp)),
                                        None, False)
        archetype = manifest["archetype"]
        self.assertEqual(archetype["primary"], "solo-utility")
        self.assertGreaterEqual(archetype["score"], archetype["floor"])
        self.assertNotEqual(archetype["runner_up"]["id"], "solo-utility")

    def test_client_spa_scores_client_application_over_every_deployed_archetype(self):
        ctx, scored = self.scored_for("client_spa")
        self.assertEqual(ctx["signals"]["arch.webapp"]["state"], "present")
        self.assertNotEqual(ctx["signals"]["iface.http"]["state"], "present")
        ranked = [row["id"] for row in scored if row["id"] != "solo-utility"]
        self.assertEqual(ranked[0], "client-application")
        by_id = dict((row["id"], row["score"]) for row in scored)
        for loser in ("oss-library", "internal-service", "commercial-saas", "data-platform"):
            self.assertLess(by_id[loser], by_id["client-application"], loser)

    def test_client_spa_resolves_to_client_application_once_it_is_not_a_solo_repo(self):
        ctx, _ = self.scored_for("client_spa")
        ctx["signals"]["proc.authors_12mo"] = signal("proc.authors_12mo", "present", 4)
        ctx["signals"]["proc.commits_12mo"] = signal("proc.commits_12mo", "present", 400)
        ctx["signals"]["deploy.cd"] = signal("deploy.cd", "present", 1)
        archetype = SELECT.resolve_archetype(ctx, self.catalog)
        self.assertEqual(archetype["primary"], "client-application")
        self.assertEqual(archetype["runner_up"]["id"], "solo-utility")
        self.assertIn("arch.webapp", archetype["cite"])

    def test_requires_absent_zeroes_an_archetype_rather_than_shading_it(self):
        ctx, _ = self.scored_for("client_spa")
        ctx["signals"]["users.published_package"] = signal("users.published_package")
        ctx["signals"]["supply.license_permissive"] = signal("supply.license_permissive")
        ctx["signals"]["iface.http"] = signal("iface.http")
        scored = dict((row["id"], row) for row in SELECT.score_archetypes(ctx, self.catalog))
        self.assertEqual(scored["oss-library"]["score"], 0.0)
        self.assertEqual(scored["oss-library"]["blocked_by"], ["iface.http"])

    def test_a_top_score_below_the_floor_resolves_to_unknown(self):
        ctx = context(signal_rows=SELECT.signal_map(self.catalog, {"signals": []}))
        for signal_id in ("proc.authors_12mo", "proc.commits_12mo", "deploy.cd", "sec.authn",
                          "scale.loc", "users.published_package", "proc.codeowners",
                          "users.public_signup"):
            ctx["signals"][signal_id] = signal(signal_id, "present", 1000)
        archetype = SELECT.resolve_archetype(ctx, self.catalog)

        self.assertLess(archetype["score"], archetype["floor"])
        self.assertEqual(archetype["primary"], "unknown")
        self.assertEqual(archetype["confidence"], "low")


class ManifestTests(unittest.TestCase):
    def build(self, tmp, name="solo_cli", answers=None, unattended=False):
        root = copy_fixture(name, tmp)
        path = scan_file(name, root, tmp)
        manifest, report = SELECT.select(str(root), str(path), answers, unattended)
        return root, path, manifest, report

    def test_the_manifest_is_a_pure_function_of_the_scan_and_the_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, path, first, first_report = self.build(tmp)
            first_bytes = (root / ".docdna" / "manifest.json").read_bytes()
            clear_outputs(root)
            second, second_report = SELECT.select(str(root), str(path), None, False)
            second_bytes = (root / ".docdna" / "manifest.json").read_bytes()

            self.assertEqual(first, second)
            self.assertEqual(first_bytes, second_bytes)
            self.assertEqual(first_report, second_report)

    def test_the_same_answers_produce_the_same_bytes_and_different_answers_do_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            answers = ["q2_operator=separate-ops-team"]
            root, path, first, _ = self.build(tmp, answers=list(answers))
            first_bytes = (root / ".docdna" / "manifest.json").read_bytes()
            clear_outputs(root)
            SELECT.select(str(root), str(path), list(answers), False)
            second_bytes = (root / ".docdna" / "manifest.json").read_bytes()
            clear_outputs(root)
            other, _ = SELECT.select(str(root), str(path), ["q2_operator=not-deployed"], False)

            self.assertEqual(first_bytes, second_bytes)
            self.assertNotEqual(first["interview"]["q2_operator"]["value"],
                                other["interview"]["q2_operator"]["value"])

    def test_an_answer_override_is_labelled_user_and_a_default_is_labelled_assumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, manifest, _ = self.build(tmp, answers=["q2_operator=separate-ops-team"])
            interview = manifest["interview"]

            self.assertEqual(interview["q2_operator"],
                             {"value": "separate-ops-team", "source": "user", "from": "--answer"})
            for key, row in interview.items():
                if key == "q2_operator":
                    continue
                self.assertEqual(row["source"], "assumed", key)
            assumed = [row["answer"] for row in manifest["assumptions"]]
            self.assertNotIn("q2_operator", assumed)
            self.assertIn("q1_users", assumed)

    def test_a_multi_select_override_takes_a_comma_separated_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, manifest, _ = self.build(tmp, answers=["q5_markets=eu-eea,canada"])

            self.assertEqual(manifest["interview"]["q5_markets"]["value"], ["eu-eea", "canada"])
            self.assertEqual(manifest["interview"]["q5_markets"]["source"], "user")

    def test_an_override_outside_the_answer_set_is_refused(self):
        catalog = SELECT.load_catalog()
        with self.assertRaises(ValueError):
            SELECT.parse_answers(catalog, ["q2_operator=whoever-is-awake"])
        with self.assertRaises(ValueError):
            SELECT.parse_answers(catalog, ["q99_nonexistent=yes"])
        with self.assertRaises(ValueError):
            SELECT.parse_answers(catalog, ["q2_operator"])

    def test_an_override_changes_the_document_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, path, base, _ = self.build(tmp)
            clear_outputs(root)
            raised, _ = SELECT.select(str(root), str(path), ["q2_operator=separate-ops-team"],
                                      False)

            def required(manifest):
                return set(row["id"] for row in manifest["documents"]
                           if row["verdict"] == "required")

            self.assertTrue(required(raised) - required(base))

    def test_every_exclusion_carries_because_and_cite_and_revisit_when(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, manifest, _ = self.build(tmp)
            excluded = manifest["excluded"]

            self.assertTrue(excluded)
            for row in excluded:
                self.assertTrue(row.get("because"), row["id"])
                self.assertTrue(row["because"].endswith("."), row["id"])
                self.assertTrue(row.get("cite"), row["id"])
                self.assertIsInstance(row["cite"], list)
                self.assertTrue(row.get("revisit_when"), row["id"])
                self.assertIsInstance(row["revisit_when"], dict)
                self.assertTrue(row.get("rule"), row["id"])

    def test_no_exclusion_ships_with_a_tripwire_that_already_fires(self):
        catalog = SELECT.load_catalog()
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture("solo_cli", tmp)
            path = scan_file("solo_cli", root, tmp)
            scan = json.loads(path.read_text(encoding="utf-8"))
            states, _ = SELECT.document_states(catalog, scan, str(root))
            manifest, _ = SELECT.select(str(root), str(path), None, False)
            ctx = context(signal_rows=SELECT.signal_map(catalog, scan),
                          answers=dict((key, row["value"])
                                       for key, row in manifest["interview"].items()),
                          archetype=manifest["archetype"]["primary"],
                          overlays=manifest["archetype"]["overlays"], docstate=states)

            self.assertTrue(manifest["excluded"])
            for row in manifest["excluded"]:
                self.assertFalse(SELECT.predicate(ctx, row["revisit_when"]),
                                 "%s is excluded and its tripwire already fires" % row["id"])

    def test_the_report_never_prints_the_full_exclusion_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _, manifest, report = self.build(tmp)
            written = (root / "DOCDNA.md").read_text(encoding="utf-8")
            excluded = manifest["excluded"]
            named = [row["id"] for row in excluded if row["id"] in report]

            self.assertEqual(report, written)
            self.assertGreater(len(excluded), SELECT.MAX_TRIPWIRE_ROWS + 1)
            self.assertLessEqual(len(named), SELECT.MAX_TRIPWIRE_ROWS)
            self.assertIn("NOT APPLICABLE", report)
            self.assertIn("%d documents" % len(excluded), report)
            self.assertIn(SELECT.MANIFEST_REL, report)
            for row in excluded:
                self.assertNotIn(row["title"], report, row["id"])

    def test_the_report_states_the_boundary_every_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, manifest, report = self.build(tmp)

            self.assertIn(manifest["boundary"], report.replace("\n" + " " * 16, " "))
            self.assertIn("present-elsewhere", report)

    def test_unattended_never_offers_a_question_as_a_next_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, manifest, report = self.build(tmp, unattended=True)

            self.assertTrue(manifest["unattended"])
            self.assertNotIn("--answer", report)

    def test_a_prior_user_answer_survives_a_rerun_and_unattended_drops_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, path, _, _ = self.build(tmp, answers=["q2_operator=separate-ops-team"])
            again, _ = SELECT.select(str(root), str(path), None, False)
            unattended, _ = SELECT.select(str(root), str(path), None, True)

            self.assertEqual(again["interview"]["q2_operator"],
                             {"value": "separate-ops-team", "source": "user", "from": "manifest"})
            self.assertEqual(unattended["interview"]["q2_operator"]["source"], "assumed")

    def test_every_document_row_names_what_selected_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, manifest, _ = self.build(tmp)
            for row in manifest["documents"]:
                self.assertTrue(row["because"], row["id"])
                self.assertIn(row["verdict"], SELECT.VERDICT_RANK, row["id"])
                self.assertIn((row["verdict"], row["state"]), SELECT.ACTIONS, row["id"])
                self.assertEqual(row["action"], SELECT.ACTIONS[(row["verdict"], row["state"])])

    def test_the_cli_emits_the_manifest_under_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture("solo_cli", tmp)
            path = scan_file("solo_cli", root, tmp)
            proc = subprocess.run([sys.executable, str(SELECT_PATH), "--json",
                                   "--scan", str(path), str(root)],
                                  check=True, capture_output=True)
            payload = json.loads(proc.stdout.decode("utf-8"))

            self.assertEqual(payload["schema"], SELECT.SCHEMA)
            self.assertEqual(payload["tool"], SELECT.TOOL)
            self.assertTrue(payload["documents"])


# The report says what docdna decided, then what it assumed, then what a human still has to read.
# Drift sits last because 51 hand-adjudicated repositories put both passes in the single digits of
# precision. These tests hold that order and hold the vocabulary that goes with it.
class ReportShapeTests(unittest.TestCase):
    ORDER = ["MISSING AND LOAD-BEARING", "NOT APPLICABLE", "NOTE", "ASSUMED",
             SELECT.STALE_TITLE, "NEXT"]

    def report_for(self, tmp, name):
        root = copy_fixture(name, tmp)
        path = scan_file(name, root, tmp)
        manifest, report = SELECT.select(str(root), str(path), None, False)
        return manifest, report

    # internal_service carries a command row and a count row, solo_cli a command row alone, and
    # documented_repo none. Every one of those used to be able to print WRONG NOW.
    def test_no_report_prints_a_wrong_now_section_or_calls_a_document_wrong(self):
        for name in ("internal_service", "solo_cli", "documented_repo"):
            with tempfile.TemporaryDirectory() as tmp:
                _, report = self.report_for(tmp, name)

                self.assertNotIn("WRONG NOW", report, name)
                self.assertNotIn("contradict", report, name)

    def test_both_former_wrong_now_kinds_render_as_leads(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, report = self.report_for(tmp, "internal_service")
            kinds = set(row["kind"] for row in manifest["drift"])

            self.assertEqual(kinds, {"command-not-found", "count-mismatch"})
            self.assertIn("%s  (%d)" % (SELECT.STALE_TITLE, len(manifest["drift"])), report)
            self.assertIn(SELECT.STALE_READ_NOTE, report.replace("\n" + " " * 16, " "))
            for row in manifest["drift"]:
                self.assertIn(row["doc"], report, row["kind"])

    def test_the_report_leads_with_the_document_set_and_ends_with_the_leads(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, report = self.report_for(tmp, "internal_service")
            found = [report.find(title) for title in self.ORDER]

            for title, index in zip(self.ORDER, found):
                self.assertNotEqual(index, -1, title)
            self.assertEqual(found, sorted(found))

    def test_the_headline_counts_leads_and_never_counts_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, report = self.report_for(tmp, "internal_service")
            headline = report.splitlines()[2]

            self.assertIn("Documentation  ", headline)
            self.assertIn("%s  2 possible stale references" % SELECT.LEAD_LABEL, headline)
            self.assertEqual(len(manifest["drift"]), 2)

    def test_a_repository_with_no_drift_says_so_and_prints_no_stale_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, report = self.report_for(tmp, "documented_repo")

            self.assertEqual(manifest["drift"], [])
            self.assertNotIn(SELECT.STALE_TITLE, report)
            self.assertIn("%s  none across your" % SELECT.LEAD_LABEL, report.splitlines()[2])

    # A count and three examples. A reader who wants the fourth is told where the ledger is, in the
    # same breath as being told the rows are leads rather than findings.
    def test_the_stale_section_shows_a_count_three_examples_and_the_ledger(self):
        rows = [{"doc": "docs/%d.md" % index, "kind": "path-not-found",
                 "claim": "docs/gone-%d.md" % index, "detail": "no such file"}
                for index in range(5)]
        lines = []
        SELECT.render_stale({"drift": rows}, {"scan": {"drift": {"discarded": 7}}}, lines)
        text = "\n".join(lines)

        self.assertIn("%s  (5, showing 3)" % SELECT.STALE_TITLE, text)
        self.assertEqual(sum(1 for row in rows if row["doc"] in text), 3)
        self.assertIn(SELECT.STALE_PATH_NOTE, text.replace("\n" + " " * 16, " "))
        self.assertIn(SELECT.STALE_READ_NOTE, text.replace("\n" + " " * 16, " "))
        self.assertIn(SELECT.MANIFEST_REL, text)

    def test_the_stale_note_names_only_the_kinds_actually_present(self):
        scan = {"scan": {"drift": {"discarded": 0}}}
        path_only = SELECT.stale_note([{"kind": "path-not-found"}], scan)
        command_only = SELECT.stale_note([{"kind": "command-not-found"}], scan)

        self.assertIn(SELECT.STALE_PATH_NOTE, path_only)
        self.assertNotIn(SELECT.STALE_COMMAND_NOTE, path_only)
        self.assertIn(SELECT.STALE_COMMAND_NOTE, command_only)
        self.assertNotIn(SELECT.STALE_PATH_NOTE, command_only)
        self.assertIn(SELECT.STALE_READ_NOTE, path_only)
        self.assertIn(SELECT.STALE_READ_NOTE, command_only)


if __name__ == "__main__":
    unittest.main()
