import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_PATH = ROOT / "skill" / "scripts" / "docdna_scan.py"
SIGNALS_PATH = ROOT / "skill" / "catalog" / "signals.json"
FIXTURES = ROOT / "tests" / "fixtures"

DOCKERFILE = "FROM nginx:alpine\nCOPY dist /usr/share/nginx/html\n"

AXIOS_CLIENT = """import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export function fetchCart() {
  return api.get('/cart')
}

export function submitOrder(payload) {
  return api.post('/orders', payload)
}
"""

CRYPTO_PACKAGE = """{
  "name": "client-spa",
  "private": true,
  "scripts": { "dev": "vite", "build": "vite build" },
  "dependencies": { "vue": "^3.4.0", "vue-router": "^4.3.0", "bcryptjs": "^2.4.3" }
}
"""

EN_LOCALE = """{
  "consent": "Consent",
  "withdraw": "Withdraw consent"
}
"""

MAIN_TF = """terraform {
  required_version = ">= 1.5.0"
}
"""

REGIONS_JSON = """{
  "regions": ["us-east-1", "us-west-2", "eu-west-1", "ca-central-1", "ap-southeast-2"]
}
"""

EXPRESS_PACKAGE = """{
  "name": "orders-service",
  "dependencies": { "express": "^4.19.0" }
}
"""

EXPRESS_SERVER = """const express = require('express')

const app = express()

app.get('/health', (req, res) => res.json({ ok: true }))

app.listen(3000)
"""

BCRYPT_PACKAGE = """{
  "name": "orders-service",
  "dependencies": { "bcryptjs": "^2.4.3" }
}
"""

MD5_MODULE = """const crypto = require('crypto')

function fingerprint(value) {
  return crypto.createHash('md5').update(value).digest('hex')
}

module.exports = { fingerprint }
"""

PERSON_TABLE = """CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email TEXT NOT NULL,
  first_name TEXT,
  last_name TEXT
);
"""


def load_scan():
    spec = importlib.util.spec_from_file_location("docdna_scan", SCAN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_signals():
    return json.loads(SIGNALS_PATH.read_text(encoding="utf-8"))["signals"]


def write_files(root, files):
    for rel, body in files.items():
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return str(root)


def trap(rel):
    return (FIXTURES / rel).read_text(encoding="utf-8")


def copy_fixture(name, tmp, extra=None):
    target = Path(tmp) / name
    shutil.copytree(str(FIXTURES / name), str(target))
    return write_files(target, extra or {})


class FalsePositiveTests(unittest.TestCase):
    def setUp(self):
        self.scan = load_scan()

    def states(self, root):
        report = self.scan.scan(str(root), set(), False, 5)
        return dict((item["id"], item) for item in report["signals"])

    def assert_not_present(self, results, signal_id, why):
        self.assertNotEqual(results[signal_id]["state"], "present",
                            "%s fired on %s: %s" % (signal_id, why, results[signal_id]["evidence"]))

    def assert_no_jurisdiction_verdict(self, results, why):
        for signal_id, item in sorted(results.items()):
            if not signal_id.startswith("jur."):
                continue
            self.assertNotEqual(item["state"], "present",
                                "%s reached present on %s: %s" % (signal_id, why, item["evidence"]))

    def test_fixtures_still_carry_their_traps(self):
        locale = trap("client_spa/src/locales/fr.json")
        router = trap("client_spa/src/router/index.js")
        schema = trap("weather_api/schema/station.sql")
        readme = trap("gdpr_lib/README.md")
        regions = trap("region_const/config/regions.py")

        self.assertEqual(locale.count("des"), 4)
        self.assertIn("router.get", router)
        self.assertIn("vue-router", router)
        self.assertNotIn("express", router)
        self.assertIn("latitude", schema)
        self.assertIn("longitude", schema)
        self.assertIn("ip_address", schema)
        self.assertNotIn("CREATE TABLE user", schema)
        self.assertIn("GDPR", readme)
        self.assertIn("Article", readme)
        self.assertIn("eu-west-1", regions)
        self.assertIn("ca-central-1", regions)

    def test_client_router_is_not_a_server_route(self):
        results = self.states(FIXTURES / "client_spa")

        self.assert_not_present(results, "iface.http", "a vue-router client router")

    def test_client_router_is_not_a_server_route_once_the_gate_fires(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture("client_spa", tmp, {"Dockerfile": DOCKERFILE,
                                                    "src/api/client.js": AXIOS_CLIENT})
            results = self.states(root)

            self.assertEqual(results["deploy.container"]["state"], "present")
            self.assertEqual(results["iface.http"]["state"], "absent")

    def test_http_still_fires_on_a_real_server_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_files(tmp, {"package.json": EXPRESS_PACKAGE, "server.js": EXPRESS_SERVER})
            results = self.states(root)

            self.assertEqual(results["arch.service"]["state"], "present")
            self.assertEqual(results["iface.http"]["state"], "present")
            self.assertEqual(results["iface.http"]["evidence"][0]["path"], "server.js")

    def test_french_locale_is_not_weak_crypto(self):
        results = self.states(FIXTURES / "client_spa")

        self.assert_not_present(results, "sec.weak_crypto", "a French locale bundle")

    def test_french_locale_is_not_weak_crypto_once_the_gate_fires(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture("client_spa", tmp, {"package.json": CRYPTO_PACKAGE})
            results = self.states(root)

            self.assertEqual(results["sec.crypto"]["state"], "present")
            self.assertEqual(results["sec.weak_crypto"]["state"], "absent")

    def test_weak_crypto_lexicon_refuses_locales_and_lockfiles(self):
        detect = dict((sig["id"], sig) for sig in load_signals())["sec.weak_crypto"]["detect"]

        self.assertNotIn(".json", detect["include_ext"])
        self.assertIn("**/locales/**", detect["exclude_glob"])
        self.assertIn("**/i18n/**", detect["exclude_glob"])
        self.assertIn("package-lock.json", detect["exclude_glob"])
        for pattern in detect["patterns"]:
            self.assertTrue(len(pattern) > 6, pattern)

    def test_weak_crypto_still_fires_on_a_real_md5_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_files(tmp, {"package.json": BCRYPT_PACKAGE, "src/hash.js": MD5_MODULE})
            results = self.states(root)

            self.assertEqual(results["sec.weak_crypto"]["state"], "present")
            self.assertEqual(results["sec.weak_crypto"]["evidence"][0]["path"], "src/hash.js")

    def test_coordinates_are_not_personal_data(self):
        results = self.states(FIXTURES / "weather_api")

        self.assertEqual(results["data.ddl"]["state"], "present")
        self.assertEqual(results["data.person_entity"]["state"], "absent")
        self.assert_not_present(results, "data.pii", "latitude, longitude and ip_address on a "
                                                     "station table")

    def test_pii_still_fires_on_a_real_person_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = write_files(tmp, {"schema/users.sql": PERSON_TABLE})
            results = self.states(root)

            self.assertEqual(results["data.person_entity"]["state"], "present")
            self.assertEqual(results["data.pii_lexicon"]["state"], "present")
            self.assertEqual(results["data.pii"]["state"], "present")

    def test_gdpr_prose_sets_no_jurisdiction_signal(self):
        results = self.states(FIXTURES / "gdpr_lib")

        self.assert_no_jurisdiction_verdict(results, "GDPR prose in a README")

    def test_gdpr_prose_stays_quiet_once_the_gate_fires(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture("gdpr_lib", tmp, {"locales/en.json": EN_LOCALE})
            results = self.states(root)

            self.assertEqual(results["users.i18n"]["state"], "present")
            self.assertEqual(results["jur.gdpr_lexicon"]["state"], "absent")
            self.assertEqual(results["jur.eu"]["state"], "absent")
            self.assert_no_jurisdiction_verdict(results, "GDPR prose in a README")

    def test_region_enum_sets_no_jurisdiction_signal(self):
        results = self.states(FIXTURES / "region_const")

        self.assert_no_jurisdiction_verdict(results, "a supported-region enum")

    def test_region_enum_stays_quiet_once_the_gate_fires(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_fixture("region_const", tmp, {"main.tf": MAIN_TF,
                                                      "config/regions.json": REGIONS_JSON})
            results = self.states(root)

            self.assertEqual(results["deploy.iac"]["state"], "present")
            self.assertEqual(results["jur.eu_region"]["state"], "absent")
            self.assertEqual(results["jur.ca_region"]["state"], "absent")
            self.assert_no_jurisdiction_verdict(results, "a supported-region enum")

    def test_no_jurisdiction_grep_ever_reads_prose(self):
        prose = (".md", ".markdown", ".rst", ".adoc", ".txt")
        greps = [sig for sig in load_signals()
                 if sig["family"] == "jur" and (sig.get("detect") or {}).get("kind") == "grep"]

        self.assertTrue(greps)
        for sig in greps:
            detect = sig["detect"]
            for ext in prose:
                self.assertNotIn(ext, detect["include_ext"], sig["id"])
            for pattern in detect.get("include_glob") or []:
                self.assertFalse(pattern.endswith(prose), "%s: %s" % (sig["id"], pattern))
            for blocked in ("README*", "**/README*", "**/*.md", "**/*.rst", "**/*.txt",
                            "**/docs/**"):
                self.assertIn(blocked, detect["exclude_glob"], sig["id"])

    def test_no_signal_decides_about_people(self):
        ids = [sig["id"] for sig in load_signals()]

        self.assertNotIn("ai.decides_about_people", ids)
        self.assertEqual([name for name in ids if "decides_about_people" in name], [])

    def test_every_jurisdiction_signal_is_capped_at_hint(self):
        jurisdiction = [sig for sig in load_signals() if sig["family"] == "jur"]

        self.assertTrue(jurisdiction)
        for sig in jurisdiction:
            self.assertTrue(sig["id"].startswith("jur."), sig["id"])
            self.assertEqual(sig["max_state"], "hint", sig["id"])
        for sig in load_signals():
            if sig["id"].startswith("jur."):
                self.assertEqual(sig["family"], "jur", sig["id"])

    def test_no_scan_returns_a_jurisdiction_signal_as_present(self):
        roots = [path for path in sorted(FIXTURES.iterdir()) if path.is_dir()] + [ROOT]
        for root in roots:
            self.assert_no_jurisdiction_verdict(self.states(root), str(root))

    def test_clamp_state_caps_a_jurisdiction_hit_at_hint(self):
        sig = {"id": "jur.eu_region", "family": "jur", "label": "region", "max_state": "hint"}
        evidence = [{"path": "main.tf", "line": 3}]
        record = self.scan.finish(sig, "present", 7, evidence, 5)

        self.assertEqual(self.scan.clamp_state("present", "hint"), "hint")
        self.assertEqual(record["state"], "hint")
        self.assertEqual(record["hits"], 7)
        self.assertEqual(record["note"], self.scan.HINT_NOTE)


if __name__ == "__main__":
    unittest.main()
