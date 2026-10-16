"""Local HTTP mock provider; no production login, tokens, cookies or inference."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import sys
import threading
import time
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase_studio import oauth
from phase_studio.credentials import CredentialStore

METADATA = dict(issuer=oauth.ISSUER, authorization_endpoint=oauth.AUTHORIZE,
    token_endpoint=oauth.TOKEN, response_types_supported=["code"],
    code_challenge_methods_supported=["S256"], scopes_supported=["sharped"],
    token_endpoint_auth_methods_supported=["none", "client_secret_basic", "client_secret_post"])


class Provider:
    def __init__(self):
        self.codes = {}
        self.exchanges = []
        self.response = dict(access_token="mock-oauth-access", token_type="Bearer", scope="sharped", expires_in=3600)
        self.metadata = dict(METADATA)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def send(self, status, obj):
                body = json.dumps(obj).encode()
                self.send_response(status);self.end_headers();self.wfile.write(body)
            def do_GET(self):
                p = urlsplit(self.path)
                if p.path.endswith("openid-configuration"):
                    self.send(200, owner.metadata)
                elif p.path == "/oauth/authorize":
                    q = {k: v[0] for k, v in parse_qs(p.query).items()}
                    if q.get("client_id") != "phase-studio" or q.get("scope") != "sharped" or q.get("code_challenge_method") != "S256":
                        self.send(400, {"error": "invalid_request"});return
                    code = "mock-code-" + str(len(owner.codes))
                    owner.codes[code] = q
                    self.send(200, dict(code=code, state=q["state"]))
                else:
                    self.send(404, {})
            def do_POST(self):
                q = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode()).items()}
                owner.exchanges.append(q)
                original = owner.codes.pop(q.get("code"), None)
                if (not original or "client_secret" in q or self.headers.get("Authorization") or
                        q.get("client_id") != "phase-studio" or q.get("grant_type") != "authorization_code" or
                        q.get("redirect_uri") != original["redirect_uri"] or
                        oauth.pkce_challenge(q.get("code_verifier", "")) != original["code_challenge"]):
                    self.send(400, {"error": "invalid_grant"});return
                self.send(200, owner.response)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def json(self, url, form=None):
        # Production endpoints remain pinned; ONLY the test transport maps them.
        assert url in (oauth.DISCOVERY, oauth.TOKEN)
        request = Request(self.base + urlsplit(url).path,
                          data=urlencode(form).encode() if form is not None else None)
        try:
            with urlopen(request, timeout=2) as r:
                return json.load(r)
        except HTTPError:
            raise oauth.OAuthError("exchange") from None

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)


class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.provider = Provider()
        self.attempts = []
    def tearDown(self):
        for attempt, thread in self.attempts:
            attempt.cancel();thread.join(3)
            self.assertFalse(thread.is_alive())
        self.provider.close()
    def start(self, **kwargs):
        attempt = oauth.OAuthAttempt(self.provider, **kwargs)
        ready = queue.Queue();done = queue.Queue()
        def run():
            try: done.put(attempt.run(ready.put))
            except oauth.OAuthError as e: done.put(e)
        thread = threading.Thread(target=run);thread.start();self.attempts.append((attempt, thread))
        return attempt, ready.get(timeout=2), done
    def authorize(self, url):
        with urlopen(self.provider.base + "/oauth/authorize?" + urlsplit(url).query) as response:
            return json.load(response)
    def callback(self, attempt, q, path="/callback", host=None):
        request = Request(attempt.redirect_uri.replace("/callback", path) + "?" + urlencode(q, doseq=True))
        if host:request.add_header("Host", host)
        try:
            with urlopen(request, timeout=2) as r:return r.status, r.read().decode()
        except HTTPError as e:return e.code, e.read().decode()
    def test_discovery_pins_and_public_auth(self):
        oauth.validate_discovery(METADATA)
        for key, bad in [("issuer", "https://evil.invalid"), ("authorization_endpoint", "https://evil.invalid/a"),
                         ("token_endpoint", "https://evil.invalid/t"), ("response_types_supported", ["token"]),
                         ("code_challenge_methods_supported", ["plain"]), ("token_endpoint_auth_methods_supported", ["client_secret_post"])]:
            with self.subTest(key=key), self.assertRaises(oauth.OAuthError):
                oauth.validate_discovery({**METADATA, key: bad})
    def test_s256_rfc_vector_and_random_transactions(self):
        self.assertEqual(oauth.pkce_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"),
                         "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
        a = oauth.OAuthAttempt(self.provider);b = oauth.OAuthAttempt(self.provider)
        self.assertNotEqual(a.verifier,b.verifier);self.assertNotEqual(a.state,b.state)
        self.assertTrue(43 <= len(a.verifier) <= 128)
    def test_complete_local_code_exchange_and_listener_cleanup(self):
        a, url, done = self.start()
        q = parse_qs(urlsplit(url).query)
        self.assertEqual(q["client_id"],["phase-studio"]);self.assertEqual(q["scope"],["sharped"])
        self.assertEqual(q["code_challenge_method"],["S256"])
        self.assertNotIn("resource",q);self.assertNotIn("client_secret",q);self.assertNotIn("openid",q["scope"])
        self.assertEqual(urlsplit(a.redirect_uri).hostname,"127.0.0.1")
        code = self.authorize(url)
        status, page = self.callback(a,code)
        result = done.get(timeout=2)
        self.assertEqual(status,200);self.assertIn("Sign-in completed",page)
        self.assertNotIn(code["code"],page);self.assertNotIn(result.access_token,page)
        self.assertIsInstance(result,oauth.OAuthCredential)
        self.assertTrue(result.usable());self.assertNotIn(result.access_token,repr(result))
        self.assertEqual(self.provider.exchanges[0]["redirect_uri"],a.redirect_uri)
        self.assertNotIn("client_secret",self.provider.exchanges[0])
        self.attempts[-1][1].join(2)
        with self.assertRaises(OSError):urlopen(a.redirect_uri,timeout=.5)
        self.assertEqual(a.verifier,"");self.assertEqual(a.state,"")
    def test_invalid_callbacks_leave_legitimate_attempt_pending(self):
        a,url,done=self.start();code=self.authorize(url)
        cases=[({**code,"state":"wrong"},"/callback",None),({"state":code["state"]},"/callback",None),
               ({**code,"error":"access_denied"},"/callback",None),(code,"/other",None),
               (code,"/callback","localhost:"+str(a.server.server_port)),
               ({**code,"state":[code["state"],code["state"]]},"/callback",None),
               ({**code,"iss":"https://evil.invalid"},"/callback",None),
               ({**code,"access_token":"not-allowed"},"/callback",None)]
        for q,path,host in cases:
            with self.subTest(q=q,path=path):self.assertEqual(self.callback(a,q,path,host)[0],400)
        self.assertFalse(a.consumed);self.assertEqual(self.provider.exchanges,[])
        self.assertEqual(self.callback(a,code)[0],200);self.assertIsInstance(done.get(timeout=2),oauth.OAuthCredential)
    def test_incorrect_verifier_consumes_code_no_retry(self):
        a,url,done=self.start();code=self.authorize(url);a.verifier="incorrect-verifier"
        self.assertEqual(self.callback(a,code)[0],400)
        self.assertEqual(done.get(timeout=2).kind,"exchange");self.assertEqual(len(self.provider.exchanges),1)
        with self.assertRaises(oauth.OAuthError):a.exchange(code["code"])
        self.assertNotIn(code["code"],self.provider.codes)
        self.assertEqual(len(self.provider.exchanges),1)
    def test_stale_callback_and_code_replay_are_rejected(self):
        old,old_url,old_done=self.start();old_code=self.authorize(old_url);old.cancel()
        self.assertEqual(old_done.get(timeout=2).kind,"cancelled")
        fresh,url,done=self.start();fresh_code=self.authorize(url)
        self.assertEqual(self.callback(fresh,old_code)[0],400)
        self.assertEqual(self.callback(fresh,fresh_code)[0],200)
        self.assertIsInstance(done.get(timeout=2),oauth.OAuthCredential)
        with self.assertRaises(oauth.OAuthError):fresh.exchange(fresh_code["code"])
        self.assertEqual(len(self.provider.exchanges),1)
    def test_malformed_token_responses_and_no_oidc_refresh(self):
        changes=[{"token_type":"Basic"},{"access_token":""},{"scope":"openid"},{"expires_in":0},
                 {"expires_in":float("nan")},{"expires_in":True},{"expires_in":7200},
                 {"id_token":"not-allowed"},{"refresh_token":"not-allowed"},{"access_token":"bad\nheader"}]
        for change in changes:
            with self.subTest(change=change):
                self.provider.response.update(change)
                a,url,done=self.start();code=self.authorize(url)
                self.assertEqual(self.callback(a,code)[0],400);self.assertEqual(done.get(timeout=2).kind,"response")
                self.provider.response=dict(access_token="mock-oauth-access",token_type="Bearer",scope="sharped",expires_in=3600)
    def test_resource_is_optional_exact_and_validated(self):
        for value in [oauth.RESOURCE+"/","https://jana.fzu.cz",oauth.RESOURCE+"/api"]:
            with self.assertRaises(oauth.OAuthError):oauth.OAuthAttempt(self.provider,resource=value)
        a,url,done=self.start(resource=oauth.RESOURCE)
        self.assertEqual(parse_qs(urlsplit(url).query)["resource"],[oauth.RESOURCE]);a.cancel()
        self.assertEqual(done.get(timeout=2).kind,"cancelled")
    def test_cancel_timeout_and_authorization_denial(self):
        for cancel in [False,True]:
            a,url,done=self.start(timeout=.2)
            if cancel:a.cancel()
            self.assertEqual(done.get(timeout=2).kind,"cancelled" if cancel else "timeout")
        a,url,done=self.start()
        self.callback(a,dict(state=a.state,error="access_denied",error_description="private-error"))
        result=done.get(timeout=2);self.assertEqual(result.kind,"cancelled");self.assertNotIn("private-error",str(result))
    def test_expired_callback_no_exchange(self):
        now=[10];a,url,done=self.start(clock=lambda:now[0]);code=self.authorize(url);now[0]=131
        self.assertEqual(self.callback(a,code)[0],409);self.assertEqual(done.get(timeout=2).kind,"timeout")
        self.assertEqual(self.provider.exchanges,[])
    def test_port_and_network_failure(self):
        a=oauth.OAuthAttempt(self.provider)
        with patch.object(oauth,"HTTPServer",side_effect=OSError()),self.assertRaises(oauth.OAuthError) as err:a.run(lambda _:None)
        self.assertEqual(err.exception.kind,"port")
        with patch.object(self.provider,"json",side_effect=oauth.OAuthError("network")),self.assertRaises(oauth.OAuthError):a.run(lambda _:None)
    def test_memory_only_expiration_and_manual_key_preserved(self):
        class Backend:
            def __init__(self):self.value="saved-legacy"
            def read(self,origin):return self.value
            def write(self,*args):raise AssertionError("OAuth must not persist")
            def delete(self,*args):raise AssertionError("OAuth must not delete legacy")
        backend=Backend();store=CredentialStore(backend)
        credential=oauth.OAuthCredential("memory-oauth",time.monotonic()+3600)
        store.activate_oauth(credential);self.assertEqual(store.get(),credential.access_token)
        self.assertEqual(store.authentication_method(),"oauth");self.assertFalse(store.remembered())
        store.save_input(credential.access_token);self.assertEqual(backend.value,"saved-legacy")
        with self.assertRaises(ValueError):store.set(credential.access_token,remember=True)
        store.sign_out_oauth();self.assertEqual(store.get(),"saved-legacy")
        with self.assertRaises(oauth.OAuthError):store.oauth_for_request(credential.access_token)
        self.assertFalse(credential.usable(now=credential.expires_at-30))
    def test_serialized_renewal_once_for_retired_tokens(self):
        store=CredentialStore();store.activate_oauth(oauth.OAuthCredential("expired",0));calls=[]
        def renew():calls.append(1);return oauth.OAuthCredential("renewed",time.monotonic()+3600)
        store.reauthorize=renew;values=[]
        threads=[threading.Thread(target=lambda:values.append(store.oauth_for_request("expired"))) for _ in range(4)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(calls,[1]);self.assertEqual(values,["renewed"]*4)


if __name__ == "__main__":
    unittest.main()
