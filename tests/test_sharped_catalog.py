"""Live-catalog contract and production regression; no network or user settings.

Run with python tests/test_sharped_catalog.py (standard-library unittest).
Only the HTTP transport is mocked; parsing, Qt widgets and multipart upload run.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QComboBox, QDialog
from phase_studio import sharped_server_client as api

OLD = {"default": "koala 2.0", "models": [
    "koala 1.0", "koala 2.0", "viper 2.0", "viper 3.0", "viper 4.0",
    "koalaB 1.0", "agama 1.0", "agama 2.0", "buzzard 1.0"]}
NEW = {"default": "koala 4.0", "models": [
    "koala 1.0", "koala 2.0", "koala 4.0", "viper 2.0", "viper 3.0",
    "viper 4.0", "koalaB 1.0", "agama 1.0", "agama 2.0", "buzzard 1.0", "buzzard 2.0"]}


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        api._catalogs.clear()
        self.response = OLD
        self.requests = []
        self.failure = False
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.map = Path(self.temp.name) / "input.xplor"
        self.map.write_bytes(b"synthetic map payload\n")

        def transport(client, method, url, data=None, headers=None):
            self.requests.append((method, url, data, headers))
            if method == "GET":
                if self.failure:
                    raise api.SharpEDServerError("synthetic network failure")
                return json.dumps(self.response)
            return json.dumps({"success": True, "job_id": 1, "token": "job-token"})

        self.addCleanup(patch.stopall)
        # Catalog-only contracts also exercise the future unified deployment.
        # Temporary split routing/compatibility has dedicated regression tests.
        patch.object(api, "PRODUCTION_ENDPOINTS", api.SharpEDEndpoints(api.DEFAULT_SERVER_URL, api.DEFAULT_SERVER_URL)).start()
        patch.object(api.SharpEDServerClient, "_request_text", transport).start()
        self.client = api.SharpEDServerClient()

    def fetch(self, response):
        self.response = response
        return self.client.get_models()

    def combo(self):
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItem("default")
        return combo

    def items(self, combo):
        return [combo.itemText(i) for i in range(combo.count())]

    def test_endpoint_migration_and_public_request(self):
        for value in ("", "https://jana.fzu.cz/", "http://jana.fzu.cz", api.DEFAULT_SERVER_URL):
            self.assertEqual(api.SharpEDServerClient(value).base_url, api.DEFAULT_SERVER_URL)
        self.assertEqual(api.normalize_server_url("https://custom.invalid/api/"), "https://custom.invalid/api")
        self.client.get_models()
        method, url, data, headers = self.requests[-1]
        self.assertEqual((method, url, data), ("GET", "https://sharped.fzu.cz/sharp-ed/models", None))
        self.assertEqual(headers, {"Accept": "application/json", "Cache-Control": "no-cache"})

    def test_response_replaces_catalog_and_default_atomically(self):
        first = self.fetch({"models": ["A", "B"], "default": "A"})
        second = self.fetch({"models": ["B", "C"], "default": "C"})
        self.assertEqual(first.models, ("A", "B"))
        self.assertEqual((second.models, second.default_model), (("B", "C"), "C"))
        self.assertIs(api.current_model_catalog("https://jana.fzu.cz"), second)
        self.assertGreater(second.fetched_at, 0)
        self.assertEqual(second.source, "https://sharped.fzu.cz/sharp-ed/models")

    def test_adjacent_consumers_reuse_but_refresh_and_submission_fetch(self):
        first = self.fetch(OLD)
        self.response = NEW
        logs = []
        self.assertIs(self.client.get_models(log=logs.append, max_age=15), first)
        self.assertEqual(len(self.requests), 1)
        self.assertFalse(any("refreshed" in line for line in logs))
        refreshed = self.client.get_models()
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(refreshed.default_model, "koala 4.0")
        self.response = {"models": ["future"], "default": "future"}
        self.client.upload(self.map, "test-token", "C", "default", .2)
        self.assertEqual(len(self.requests), 4)
        self.assertIn(b'name="model"\r\n\r\nfuture\r\n', self.requests[-1][2])

    def test_expired_or_failed_catalog_is_not_reused(self):
        self.fetch(OLD)
        self.response = NEW
        with patch.object(api.time, "time", return_value=time.time() + 16):
            self.assertEqual(self.client.get_models(max_age=15).default_model, "koala 4.0")
        self.failure = True
        with self.assertRaises(api.SharpEDServerError):
            self.client.get_models()
        self.failure = False
        self.response = OLD
        self.assertEqual(self.client.get_models(max_age=15).default_model, "koala 2.0")

    def test_custom_server_does_not_display_another_servers_metadata(self):
        combo = self.combo()
        self.fetch(NEW)
        api.sync_model_catalog(combo, api.DEFAULT_SERVER_URL)
        combo.setCurrentText("viper 3.0")
        status = api.sync_model_catalog(combo, "https://custom.invalid")
        self.assertEqual(self.items(combo), ["default"])
        self.assertEqual(combo.currentText(), "viper 3.0")
        self.assertIn("not loaded", status)
        self.assertIsNone(combo._sharped_catalog)

    def test_production_refresh_replaces_combo_and_preserves_default_intent(self):
        combo = self.combo()
        api.apply_model_catalog(combo, self.fetch(OLD))
        status = api.apply_model_catalog(combo, self.fetch(NEW))
        self.assertEqual(self.items(combo), ["default", *NEW["models"]])
        self.assertEqual(combo.currentText(), "default")
        self.assertIn("11 models available", status)
        self.assertIn("server default: koala 4.0", status)

    def test_new_model_without_restart(self):
        combo = self.combo()
        api.apply_model_catalog(combo, self.fetch({"models": ["koala 1.0", "koala 2.0"], "default": "koala 2.0"}))
        api.apply_model_catalog(combo, self.fetch({"models": ["koala 1.0", "koala 2.0", "koala 4.0"], "default": "koala 4.0"}))
        self.assertIn("koala 4.0", self.items(combo))

    def test_retained_and_removed_selections(self):
        combo = self.combo()
        api.apply_model_catalog(combo, self.fetch({"models": ["A", "B"], "default": "A"}))
        combo.setCurrentText("B")
        api.apply_model_catalog(combo, self.fetch({"models": ["B", "C"], "default": "C"}))
        self.assertEqual(combo.currentText(), "B")
        api.apply_model_catalog(combo, self.fetch({"models": ["C"], "default": "C"}))
        self.assertEqual(combo.currentText(), "default")
        self.assertEqual(self.items(combo), ["default", "C"])

    def test_invalid_responses_never_replace_valid_metadata(self):
        self.fetch(NEW)
        for invalid in ({}, {"models": [], "default": "A"}, {"models": ["A"], "default": "B"},
                        {"models": ["A", 42], "default": "A"}, {"models": ["default"], "default": "default"},
                        {"models": "A", "default": "A"}):
            with self.subTest(response=invalid):
                self.response = invalid
                with self.assertRaises(api.SharpEDServerError):
                    self.client.get_models()
                cached = api.current_model_catalog(api.DEFAULT_SERVER_URL)
                self.assertEqual(cached.models, tuple(NEW["models"]))
                self.assertEqual(cached.default_model, NEW["default"])
                self.assertEqual(cached.status, "cached")

    def test_failed_refresh_is_honest_and_default_upload_does_not_guess(self):
        self.fetch(OLD)
        self.failure = True
        logs = []
        with self.assertRaises(api.SharpEDServerError):
            self.client.upload(self.map, "test-token", "C", "default", .2, log=logs.append)
        self.assertFalse(any(method == "POST" for method, *_ in self.requests))
        self.assertTrue(any("refresh failed" in line for line in logs))
        self.assertFalse(any("refreshed from server" in line for line in logs))
        self.assertIn("cached", api.apply_model_catalog(self.combo(), api.current_model_catalog(api.DEFAULT_SERVER_URL)))

    def test_actual_multipart_submission_resolves_current_default(self):
        self.fetch(OLD)
        self.response = NEW
        self.client.upload(self.map, "test-token", "C N O", "default", .2)
        method, url, body, headers = self.requests[-1]
        self.assertEqual((method, url), ("POST", "https://sharped.fzu.cz/api/user/sharp-ed/upload"))
        self.assertIn(b'name="model"\r\n\r\nkoala 4.0\r\n', body)
        self.assertNotIn(b"koala 2.0", body)
        self.assertIn(self.map.read_bytes(), body)
        self.assertEqual(headers["Authorization"], "Bearer test-token")
        self.assertEqual(api.current_model_catalog(api.DEFAULT_SERVER_URL).default_model, "koala 4.0")

    def test_explicit_model_is_sent_unchanged_without_discovery(self):
        self.failure = True
        self.client.upload(self.map, "test-token", "C", "viper 3.0", .2)
        self.assertEqual(len(self.requests), 1)
        self.assertIn(b'name="model"\r\n\r\nviper 3.0\r\n', self.requests[0][2])

    def test_main_and_jana_workflows_reach_real_upload_with_default_intent(self):
        from phase_studio import app as main, jana_superflip as js
        self.fetch(OLD)
        self.response = NEW
        completed = api.StatusResult("completed", "result.xplor", "", "", "{}",
                                     download_bytes=self.map.read_bytes())
        with patch.object(api.SharpEDServerClient, "wait_for_completion", return_value=completed):
            output = Path(self.temp.name) / "main.xplor"
            main.run_sharped_deblur(self.map, output, "https://jana.fzu.cz", "test-token",
                                   "default", "C N O", .2, 0, 600, 1, 1, lambda message: None)
            self.assertEqual(output.read_bytes(), self.map.read_bytes())
            self.assertIn(b'name="model"\r\n\r\nkoala 4.0\r\n', self.requests[-1][2])
            options = js.JanaRunOptions(action="run", api_token="test-token", model="default")
            js.deblur_with_sharped(self.map, Path(self.temp.name) / "wizard.xplor", options, lambda message: None)
            self.assertEqual(options.model, "default")
            self.assertIn(b'name="model"\r\n\r\nkoala 4.0\r\n', self.requests[-1][2])

    def make_window(self):
        from phase_studio import app as main
        cls = main.IterativeSuperflipPipelineQtGUI
        with patch.object(cls, "load_settings"), patch.object(cls, "save_settings"):
            window = cls()
        window.settings = QSettings(str(Path(self.temp.name) / "settings.ini"), QSettings.IniFormat)
        window.timer.stop()
        self.addCleanup(window.deleteLater)
        return window

    def test_main_gui_settings_race_rebuild_and_restart(self):
        window = self.make_window()
        self.fetch(NEW)
        window._poll_queue()
        combo = window.inputs["sharped_model"]
        window.settings.setValue("inputs/sharped_base_url", "https://jana.fzu.cz")
        window.settings.setValue("inputs/sharped_model", "removed model")
        window.settings.setValue("inputs/sharped_models", OLD["models"])
        window.settings.setValue("inputs/sharped_default_model", "koala 2.0")
        window.load_settings()  # restoration after the successful async response
        self.assertEqual(self.items(combo), ["default", *NEW["models"]])
        self.assertEqual(combo.currentText(), "default")
        self.assertEqual(window.inputs["sharped_base_url"].text(), api.DEFAULT_SERVER_URL)
        self.assertIn("koala 4.0", window.sharped_model_status.text())
        # The next RunConfig cannot retain a model removed by a refresh.
        for key, value in {"metadata_source": "manual", "manual_cell_a": "8",
                           "manual_cell_b": "8", "manual_cell_c": "8",
                           "manual_cell_alpha": "90", "manual_cell_beta": "90",
                           "manual_cell_gamma": "90", "manual_spacegroup_number": "1",
                           "manual_spacegroup_symbol": "P1", "manual_composition": "C4"}.items():
            window._set_widget_value_from_string(window.inputs[key], value)
        self.assertEqual(window.get_config().sharped_model, "default")
        rebuilt = self.make_window()  # constructor must consume existing live metadata
        self.assertEqual(self.items(rebuilt.inputs["sharped_model"]), ["default", *NEW["models"]])
        window.settings.setValue("inputs/sharped_model", "default")
        window.settings.sync()
        api._catalogs.clear()  # new process has no authoritative persisted metadata
        restarted = self.make_window()
        restarted.load_settings()
        restarted.refresh_sharped_models()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and api.current_model_catalog(api.DEFAULT_SERVER_URL) is None:
            time.sleep(.01)
        restarted._poll_queue()
        self.assertEqual(self.items(restarted.inputs["sharped_model"]), ["default", *NEW["models"]])
        self.assertEqual(restarted.inputs["sharped_model"].currentText(), "default")
        self.assertIn("koala 4.0", restarted.sharped_model_status.text())

    def test_preflight_and_both_wizard_workflows_share_catalog(self):
        from phase_studio import jana_superflip as js
        from phase_studio.requirements import check_sharped_api
        window = self.make_window()
        self.response = NEW
        check_sharped_api("https://jana.fzu.cz", "test-token")
        window._poll_queue()
        self.assertEqual(self.items(window.inputs["sharped_model"]), ["default", *NEW["models"]])
        settings = QSettings(str(Path(self.temp.name) / "wizard.ini"), QSettings.IniFormat)
        with patch.object(QDialog, "exec", return_value=QDialog.Rejected):
            # Wizard QSettings are supplied by its lazy Qt import dictionary.
            original = js._qt_imports
            def qt_imports():
                qt = original()
                qt["QSettings"] = lambda *args: settings
                return qt
            with patch.object(js, "_qt_imports", qt_imports):
                for workflow in (js.WORKFLOW_SUPERFLIP_SHARPED, js.WORKFLOW_PHASE_RECYCLING):
                    wizard = js._JanaWorkflowWizard([], None)
                    wizard.run()
                    self.addCleanup(wizard.dialog.deleteLater)
                    wizard.workflow_state["key"] = workflow
                    wizard._workflow_changed()
                    wizard._ensure_models_loaded()
                    deadline = time.monotonic() + 5
                    while wizard.model_cache["inflight"] and time.monotonic() < deadline:
                        wizard.refresh_timer.timeout.emit()
                        time.sleep(.01)
                    self.assertFalse(wizard.model_cache["inflight"])
                    self.assertEqual(self.items(wizard.model), self.items(window.inputs["sharped_model"]))
                    self.assertEqual(wizard.model.currentText(), "default")
                    self.assertIn("koala 4.0", wizard.model_status.text())
                    self.assertIs(wizard.model._sharped_catalog, api.current_model_catalog(api.DEFAULT_SERVER_URL))


if __name__ == "__main__":
    unittest.main(verbosity=2)
