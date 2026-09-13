"""Temporary endpoint routing contracts; real client/Qt, mocked HTTP only."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QComboBox
from phase_studio import sharped_server_client as api

CURRENT = {"models": ["koala 2.0", "koala 4.0", "viper 3.0"], "default": "koala 4.0"}
LEGACY = {"models": ["koala 2.0", "viper 3.0"], "default": "koala 2.0"}


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        api._catalogs.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "synthetic.xplor"
        self.source.write_bytes(b"synthetic map data\n")
        self.requests = []
        self.legacy = LEGACY
        self.fail_compatibility = False
        self.fail_auth = False
        self.logs = []
        self.client = api.SharpEDServerClient()
        self.token = "private-test-token-not-for-logs"
        def transport(method, url, data=None, headers=None):
            self.requests.append((method, url, data, headers))
            if url.endswith("/sharp-ed/models"):
                if url.startswith("https://jana."):
                    if self.fail_compatibility:
                        raise api.SharpEDServerError("compatibility offline")
                    result = self.legacy
                else:
                    result = CURRENT
            elif method == "POST":
                if self.fail_auth:
                    raise api.SharpEDServerError("SharpED HTTP error 401: Invalid API token")
                result = {"success": True, "job_id": 1, "token": "job-secret",
                          "status_url": "https://sharped.fzu.cz/api/user/sharp-ed/status/job-secret"}
            elif "/status/" in url:
                result = {"status": "completed", "download_url":
                          "https://sharped.fzu.cz/api/user/sharp-ed/download/job-secret"}
            else:
                return self.source.read_bytes()
            return json.dumps(result).encode()
        self.mock = patch.object(self.client, "_request_bytes", side_effect=transport)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def upload(self, model):
        return self.client.upload(self.source, self.token, "C", model, .2, self.logs.append)

    def test_current_discovery_and_separate_compatibility(self):
        catalog = self.client.get_models()
        self.assertEqual([r[1] for r in self.requests], [
            "https://sharped.fzu.cz/sharp-ed/models", "https://jana.fzu.cz/sharp-ed/models"])
        self.assertEqual(catalog.models, tuple(CURRENT["models"]))
        self.assertEqual(catalog.default_model, "koala 4.0")
        self.assertEqual(catalog.inference_models, tuple(LEGACY["models"]))
        self.client.get_inference_models()
        self.assertIs(api.current_model_catalog(api.DEFAULT_SERVER_URL), catalog)

    def test_complete_job_lifecycle_uses_legacy_and_exact_model_and_map(self):
        output = Path(self.temp.name) / "result.xplor"
        self.client.execute(self.source, self.token, output, "C", "viper 3.0", log=self.logs.append)
        jobs = [r for r in self.requests if "/api/" in r[1]]
        self.assertEqual([r[0] for r in jobs], ["POST", "GET", "GET"])
        self.assertTrue(all(r[1].startswith("https://jana.fzu.cz/api/") for r in jobs))
        self.assertIn(b'name="model"\r\n\r\nviper 3.0\r\n', jobs[0][2])
        self.assertIn(self.source.read_bytes(), jobs[0][2])
        self.assertEqual(output.read_bytes(), self.source.read_bytes())
        self.assertNotIn(self.token, "\n".join(self.logs))
        self.assertNotIn("job-secret", "\n".join(self.logs))

    def test_unsupported_explicit_model_never_uploads_or_substitutes(self):
        with self.assertRaisesRegex(api.SharpEDServerError, "koala 4.0.*temporarily unavailable"):
            self.upload("koala 4.0")
        self.assertFalse(any(r[0] == "POST" for r in self.requests))

    def test_current_default_unavailable_never_runs_legacy_default(self):
        with self.assertRaisesRegex(api.SharpEDServerError, "Select a compatible concrete model"):
            self.upload("default")
        self.assertFalse(any(r[0] == "POST" for r in self.requests))
        self.assertEqual(api.current_model_catalog(api.DEFAULT_SERVER_URL).default_model, "koala 4.0")

    def test_supported_current_default_is_exact_even_with_different_legacy_default(self):
        self.legacy = {"models": CURRENT["models"], "default": "koala 2.0"}
        self.upload("default")
        self.assertIn(b'name="model"\r\n\r\nkoala 4.0\r\n', self.requests[-1][2])
        self.assertNotIn(b"koala 2.0", self.requests[-1][2])

    def test_failed_compatibility_preserves_current_catalog_and_blocks_upload(self):
        self.fail_compatibility = True
        catalog = self.client.get_models()
        self.assertEqual(catalog.models, tuple(CURRENT["models"]))
        self.assertIsNone(catalog.inference_models)
        with self.assertRaisesRegex(api.SharpEDServerError, "Cannot verify"):
            self.upload("viper 3.0")
        self.assertFalse(any(r[0] == "POST" for r in self.requests))

    def test_compatibility_rechecked_at_submission(self):
        self.client.get_models()
        self.legacy = {"models": ["koala 2.0"], "default": "koala 2.0"}
        with self.assertRaisesRegex(api.SharpEDServerError, "viper 3.0.*temporarily unavailable"):
            self.upload("viper 3.0")

    def test_ui_retains_current_catalog_and_disables_unsupported_default_and_model(self):
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItem("default")
        status = api.apply_model_catalog(combo, self.client.get_models())
        self.assertEqual([combo.itemText(i) for i in range(combo.count())], ["default", *CURRENT["models"]])
        self.assertFalse(combo.model().item(0).isEnabled())
        self.assertFalse(combo.model().item(2).isEnabled())
        self.assertTrue(combo.model().item(3).isEnabled())
        self.assertIn("Server default temporarily unavailable", status)
        self.assertNotIn("from server", status)
        self.assertEqual(combo.currentIndex(), -1)
        self.assertEqual(combo.lineEdit().placeholderText(), "Select a compatible model")
        self.assertIn("Temporarily unavailable", combo.model().item(2).toolTip())

    def test_upload_401_never_switches_hosts(self):
        self.fail_auth = True
        with self.assertRaisesRegex(api.SharpEDServerError, "HTTP error 401"):
            self.upload("viper 3.0")
        self.assertEqual([r[1] for r in self.requests if r[0] == "POST"],
                         ["https://jana.fzu.cz/api/user/sharp-ed/upload"])

    def test_future_unified_endpoint_needs_no_compatibility_or_architecture_change(self):
        self.client.endpoints = api.SharpEDEndpoints(api.DEFAULT_SERVER_URL, api.DEFAULT_SERVER_URL)
        self.upload("default")
        self.assertEqual(len(self.requests), 2)
        self.assertTrue(all(r[1].startswith(api.DEFAULT_SERVER_URL) for r in self.requests))
        self.assertIn(b"koala 4.0", self.requests[-1][2])

    def test_unknown_job_hosts_rejected_and_relative_routes_resolved(self):
        self.assertEqual(self.client._absolute_url('/api/user/sharp-ed/status/job'),
                         'https://jana.fzu.cz/api/user/sharp-ed/status/job')
        for url in ('https://unknown.invalid/job', '//unknown.invalid/job', 'file:///local/map', 'https:job'):
            with self.assertRaises(api.SharpEDServerError):
                self.client.get_status(url, 'job-secret', self.token)
        self.assertEqual(self.requests, [])

    def test_redirect_cannot_forward_credentials_to_other_host(self):
        handler = api._SameOriginRedirectHandler()
        request = Request('https://jana.fzu.cz/api/user/sharp-ed/status/job',
                          headers={'Authorization': 'Bearer '+self.token})
        with self.assertRaisesRegex(api.SharpEDServerError, 'no credentials were forwarded'):
            handler.redirect_request(request, None, 302, '', {}, 'https://sharped.fzu.cz/api/job')

    def test_server_echo_of_token_is_removed_from_error(self):
        self.mock.stop()
        error = HTTPError('https://jana.fzu.cz/api/user/sharp-ed/upload', 401, 'Unauthorized', {},
                          io.BytesIO(('Invalid value '+self.token).encode()))
        with patch.object(self.client._opener, 'open', side_effect=error):
            with self.assertRaises(api.SharpEDServerError) as caught:
                self.client._request_bytes('POST', error.url, headers={'Authorization': 'Bearer '+self.token})
        self.assertNotIn(self.token, str(caught.exception))
        self.assertIn('HTTP error 401', str(caught.exception))


if __name__ == '__main__':
    unittest.main(verbosity=2)
