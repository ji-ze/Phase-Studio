"""Regression coverage for the restored one-server SharpED API contract."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase_studio import sharped_server_client as api


class SharpEDAPIContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "synthetic.xplor"
        self.source.write_bytes(b"synthetic map payload\n")
        self.output = Path(self.temp.name) / "result.xplor"
        self.requests = []
        self.logs = []
        self.user_token = "private-user-token"
        self.job_token = "private-job-token"

    def transport(self, method, url, data=None, headers=None):
        self.requests.append((method, url, data, headers or {}))
        if url.endswith("/sharp-ed/models"):
            return json.dumps({"default": "koala 2.0", "models": ["koala 2.0", "viper 3.0"]}).encode()
        if method == "POST":
            return json.dumps({"success": True, "job_id": 7, "token": self.job_token,
                               "status_url": "/api/user/sharp-ed/status/" + self.job_token}).encode()
        if "/status/" in url:
            return json.dumps({"status": "completed",
                               "download_url": "/api/user/sharp-ed/download/" + self.job_token}).encode()
        if "/download/" in url:
            return self.source.read_bytes()
        raise AssertionError(url)

    def test_historical_default_and_no_url_migration(self):
        self.assertEqual(api.DEFAULT_SERVER_URL, "https://jana.fzu.cz")
        self.assertEqual(api.SharpEDServerClient().base_url, "https://jana.fzu.cz")
        self.assertEqual(api.SharpEDServerClient("http://jana.fzu.cz/").base_url, "http://jana.fzu.cz")
        self.assertEqual(api.SharpEDServerClient("https://custom.invalid/api/").base_url,
                         "https://custom.invalid/api")

    def test_model_discovery_uses_same_historical_base_without_auth_headers(self):
        client = api.SharpEDServerClient()
        with patch.object(api.SharpEDServerClient, "_request_bytes", self.transport):
            models = client.get_models()
        self.assertEqual((models.default_model, models.models),
                         ("koala 2.0", ["koala 2.0", "viper 3.0"]))
        self.assertEqual(self.requests, [("GET", "https://jana.fzu.cz/sharp-ed/models", None, {})])

    def test_model_selection_reconciliation_is_shared_and_preserves_default(self):
        values, displayed = api.reconcile_model_selection(
            "default", ["koala 2.0", "viper 3.0", "koala 2.0"], "koala 2.0",
        )
        self.assertEqual(values, ["default", "koala 2.0", "viper 3.0"])
        self.assertEqual(displayed, "default")
        _values, displayed = api.reconcile_model_selection(
            "viper 3.0", ["koala 2.0", "viper 3.0"], "koala 2.0",
        )
        self.assertEqual(displayed, "viper 3.0")
        _values, displayed = api.reconcile_model_selection(
            "removed model", ["koala 2.0"], "koala 2.0",
        )
        self.assertEqual(displayed, "default")

    def test_complete_lifecycle_uses_one_base_and_historical_tokens(self):
        client = api.SharpEDServerClient()
        with patch.object(api.SharpEDServerClient, "_request_bytes", self.transport):
            client.execute(self.source, self.user_token, self.output, "C", "viper 3.0",
                           max_polls=1, log=self.logs.append)
        self.assertEqual([request[0] for request in self.requests], ["POST", "GET", "GET"])
        self.assertTrue(all(request[1].startswith("https://jana.fzu.cz/") for request in self.requests))
        upload = self.requests[0]
        self.assertEqual(upload[3]["Authorization"], "Bearer " + self.user_token)
        self.assertNotIn("Accept", upload[3])
        self.assertIn(b'name="model"\r\n\r\nviper 3.0\r\n', upload[2])
        self.assertIn(self.source.read_bytes(), upload[2])
        self.assertEqual(self.requests[1][3]["Authorization"], "Bearer " + self.user_token)
        self.assertEqual(self.requests[2][3]["Authorization"], "Bearer " + self.job_token)
        self.assertEqual(self.output.read_bytes(), self.source.read_bytes())
        visible = "\n".join(self.logs)
        self.assertNotIn(self.user_token, visible)
        self.assertNotIn(self.job_token, visible)

    def test_custom_base_drives_every_route_without_a_hidden_host(self):
        client = api.SharpEDServerClient("https://custom.invalid/service")
        with patch.object(api.SharpEDServerClient, "_request_bytes", self.transport):
            client.get_models()
            client.execute(self.source, self.user_token, self.output, "C", "viper 3.0", max_polls=1)
        self.assertTrue(all(request[1].startswith("https://custom.invalid/service/")
                            for request in self.requests))
        self.assertFalse(any("sharped.fzu.cz" in request[1] or "jana.fzu.cz" in request[1]
                             for request in self.requests))

    def test_main_and_jana_callers_resolve_default_from_same_client(self):
        from phase_studio import app, jana_superflip
        calls = []
        class Client:
            def __init__(self, base_url, timeout):
                calls.append(("init", base_url, timeout))
            def get_models(self, log=None):
                calls.append(("models",))
                return api.ModelsResult("koala 2.0", ["koala 2.0", "viper 3.0"], "{}")
            def execute(self, **kwargs):
                calls.append(("execute", kwargs["model"], kwargs["bearer_token"]))
                kwargs["out_path"].write_bytes(kwargs["file_path"].read_bytes())
        with patch.object(app, "SharpEDServerClient", Client):
            app.run_sharped_deblur(self.source, self.output, api.DEFAULT_SERVER_URL,
                                   self.user_token, "default", "C", .2, 1, 600, 1, 1,
                                   self.logs.append)
        jana_output = Path(self.temp.name) / "jana.xplor"
        with patch.object(jana_superflip, "SharpEDServerClient", Client):
            jana_superflip.deblur_with_sharped(
                self.source, jana_output,
                jana_superflip.JanaRunOptions(action="run", api_token=self.user_token,
                                               server_url=api.DEFAULT_SERVER_URL, model="default"),
                self.logs.append)
        self.assertEqual([call[1] for call in calls if call[0] == "execute"],
                         ["koala 2.0", "koala 2.0"])
        self.assertEqual(sum(call[0] == "models" for call in calls), 2)

    def test_explicit_model_is_passed_unchanged_without_discovery(self):
        from phase_studio import jana_superflip
        calls = []
        class Client:
            def __init__(self, **kwargs):
                pass
            def get_models(self, **kwargs):
                raise AssertionError("explicit model must not trigger discovery")
            def execute(self, **kwargs):
                calls.append(kwargs["model"])
                kwargs["out_path"].write_bytes(kwargs["file_path"].read_bytes())
        with patch.object(jana_superflip, "SharpEDServerClient", Client):
            jana_superflip.deblur_with_sharped(
                self.source, self.output,
                jana_superflip.JanaRunOptions(action="run", api_token=self.user_token,
                                               model="viper 3.0"), self.logs.append)
        self.assertEqual(calls, ["viper 3.0"])

    def test_no_split_endpoint_api_remains(self):
        source = Path(api.__file__).read_text(encoding="utf-8")
        for obsolete in ("PRODUCTION_ENDPOINTS", "metadata_base_url", "inference_base_url",
                         "legacy inference", "temporarily unavailable for inference"):
            self.assertNotIn(obsolete, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
