"""Protected requests renew account access without resubmitting an inference."""
import io
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase_studio.credentials import CredentialStore
from phase_studio.oauth import OAuthCredential, RESOURCE, OAuthError
from phase_studio.sharped_server_client import SharpEDServerClient, SharpEDServerError


class Response(io.BytesIO):
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class OAuthAPITests(unittest.TestCase):
    def setUp(self):
        self.store=CredentialStore();self.store.activate_oauth(OAuthCredential("mock-initial",time.monotonic()+3600))
        self.calls=[];self.renewals=[];self.failures=[]
        def renew():
            self.renewals.append(1)
            return OAuthCredential("mock-renewed",time.monotonic()+3600)
        self.store.reauthorize=renew
        self.store_patch=patch("phase_studio.credentials.credential_store",self.store);self.store_patch.start()
        self.opener_patch=patch("urllib.request.build_opener",return_value=self);self.opener_patch.start()
        self.client=SharpEDServerClient()
    def tearDown(self):self.opener_patch.stop();self.store_patch.stop()
    def open(self,request,timeout):
        self.calls.append((request.method,request.full_url,request.get_header("Authorization"),request.data))
        if self.failures:
            code=self.failures.pop(0)
            if code:raise HTTPError(request.full_url,code,"mock",{},io.BytesIO(b"redacted failure"))
        if request.method=="POST":
            return Response(b'{"success":true,"token":"job-identifier","status_url":"/api/user/sharp-ed/status/job-identifier"}')
        return Response(b"scientific-result")
    def test_oauth_upload_origin_payload_and_account_header(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"map.xplor";p.write_bytes(b"scientific-map")
            result=self.client.upload(p,"mock-initial","C9 N1","SEED",.2)
        method,url,header,body=self.calls[0]
        self.assertEqual(method,"POST");self.assertEqual(url,RESOURCE+"/api/user/sharp-ed/upload")
        self.assertEqual(header,"Bearer mock-initial");self.assertIn(b"scientific-map",body)
        self.assertIn(b'SEED',body);self.assertEqual(result.token,"job-identifier")
        self.assertNotIn("mock-initial",result.status_url)
    def test_expiration_before_upload_renews_then_submits_once(self):
        self.store.activate_oauth(OAuthCredential("mock-initial",0))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"map.xplor";p.write_bytes(b"map")
            self.client.upload(p,"mock-initial","C1","SEED",.2)
        self.assertEqual(len(self.calls),1);self.assertEqual(self.renewals,[1])
        self.assertEqual(self.calls[0][2],"Bearer mock-renewed")
    def test_get_401_renews_once_preserves_job_and_resumes_download(self):
        self.failures=[401,0]
        url=RESOURCE+"/api/user/sharp-ed/download/job-original"
        body=self.client._request_bytes_with_auth_candidates(url,["job-original","mock-initial"])
        self.assertEqual(body,b"scientific-result");self.assertEqual(self.renewals,[1])
        self.assertEqual([c[1] for c in self.calls],[url,url])
        self.assertEqual([c[2] for c in self.calls],["Bearer mock-initial","Bearer mock-renewed"])
        self.assertTrue(all(c[0]=="GET" for c in self.calls))
    def test_expired_status_request_keeps_job_identifier(self):
        self.store.activate_oauth(OAuthCredential("mock-initial",0))
        url=RESOURCE+"/api/user/sharp-ed/status/existing-job"
        self.client._request_text_with_auth_candidates(url,["mock-initial","existing-job"])
        self.assertEqual(self.calls[0][1],url);self.assertEqual(self.calls[0][2],"Bearer mock-renewed")
    def test_reauthorization_bounded_and_403_not_retried(self):
        for codes in ([401,401],[403]):
            with self.subTest(codes=codes):
                self.calls.clear();self.renewals.clear();self.failures=list(codes)
                self.store.activate_oauth(OAuthCredential("mock-initial",time.monotonic()+3600))
                with self.assertRaises(SharpEDServerError):
                    self.client._request_bytes_with_auth_candidates(RESOURCE+"/api/user/sharp-ed/status/job",["mock-initial","job"])
                self.assertEqual(len(self.calls),len(codes))
                self.assertEqual(len(self.renewals),1 if codes[0]==401 else 0)
    def test_post_failures_never_replay(self):
        for code in [401,403,500]:
            with self.subTest(code=code):
                self.calls.clear();self.failures=[code]
                with self.assertRaises(SharpEDServerError):
                    self.client._request_bytes("POST",RESOURCE+"/api/user/sharp-ed/upload",data=b"density",headers={"Authorization":"Bearer mock-initial"})
                self.assertEqual(len(self.calls),1);self.assertEqual(self.renewals,[])
    def test_oauth_never_sent_to_other_hosts_or_legacy_fallback_header(self):
        for url in ["https://jana.fzu.cz/api/user/sharp-ed/upload","http://sharped.fzu.cz/api/user/sharp-ed/status/job","https://evil.invalid/job"]:
            with self.subTest(url=url),self.assertRaises(SharpEDServerError):
                self.client._request_bytes("GET",url,headers={"Authorization":"Bearer mock-initial"})
        self.assertEqual(self.calls,[])
    def test_sign_out_or_cancelled_renewal_stops_requests(self):
        self.store.sign_out_oauth()
        with self.assertRaises(SharpEDServerError):
            self.client._request_bytes_with_auth_candidates(RESOURCE+"/api/user/sharp-ed/status/job",["job","mock-initial"])
        self.assertEqual(self.calls,[])
        self.store.activate_oauth(OAuthCredential("mock-initial",0));self.store.reauthorize=lambda:None
        with self.assertRaises(SharpEDServerError):
            self.client._request_bytes_with_auth_candidates(RESOURCE+"/api/user/sharp-ed/status/job",["mock-initial"])
        self.assertEqual(self.calls,[])
    def test_download_probe_does_not_hide_oauth_permission_failure(self):
        self.client.base_url=RESOURCE;self.failures=[403]
        with self.assertRaises(SharpEDServerError):self.client._probe_download("job","mock-initial")
        self.assertEqual(len(self.calls),1);self.assertEqual(self.renewals,[])
    def test_stop_at_renewal_completion_never_starts_upload(self):
        self.store.activate_oauth(OAuthCredential("mock-initial",0))
        stop=threading.Event();self.client._oauth_stop_event=stop
        def renew(event):
            event.set()
            return OAuthCredential("mock-renewed",time.monotonic()+3600)
        self.store.reauthorize=renew
        with self.assertRaises(SharpEDServerError):
            self.client._request_bytes("POST",RESOURCE+"/api/user/sharp-ed/upload",data=b"map",headers={"Authorization":"Bearer mock-initial"})
        self.assertEqual(self.calls,[])


if __name__=="__main__":unittest.main()
