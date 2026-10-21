"""Pinned public-native OAuth code/S256 flow. No cookies, secrets or OIDC claims."""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from urllib.error import HTTPError

ISSUER = "https://jana.fzu.cz"
DISCOVERY = ISSUER + "/.well-known/openid-configuration"
AUTHORIZE = ISSUER + "/oauth/authorize"
TOKEN = ISSUER + "/oauth/token"
RESOURCE = "https://sharped.fzu.cz"
CLIENT_ID = "phase-studio"
SCOPE = "sharped"


class OAuthError(Exception):
    """Fixed, non-sensitive errors suitable for the ordinary connection UI."""
    def __init__(self, kind: str):
        self.kind = kind
        super().__init__({
            "configuration": "Jana2020 sign-in configuration could not be verified.",
            "network": "Jana2020 sign-in is unavailable. Check your connection and retry.",
            "cancelled": "Sign-in cancelled.",
            "timeout": "Sign-in timed out. Please start a new sign-in.",
            "exchange": "Sign-in could not be completed. Please start a new sign-in.",
            "response": "Jana2020 returned an unexpected sign-in response. Please retry.",
            "browser": "The browser could not be opened. Please retry.",
            "port": "The local sign-in callback could not be started. Please retry.",
        }.get(kind, "Sign-in could not be completed. Please retry."))


@dataclass(frozen=True)
class OAuthCredential:
    access_token: str = field(repr=False)
    expires_at: float
    scope: str = SCOPE
    expires_at_utc: float | None = None

    def usable(self, now=None, margin=60):
        return (time.monotonic() if now is None else now) + margin < self.expires_at


def pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class OAuthTransport:
    """Use the same verified platform TLS authority as the inference client."""
    def __init__(self):
        from phase_studio.sharped_server_client import SharpEDServerClient
        context, _ = SharpEDServerClient._create_ssl_context()
        self.opener = build_opener(_NoRedirect(), HTTPSHandler(context=context))

    def json(self, url, form=None):
        data = urlencode(form).encode("ascii") if form is not None else None
        request = Request(url, data=data, headers={"Accept": "application/json"},
                          method="POST" if form is not None else "GET")
        if form is not None:
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with self.opener.open(request, timeout=15) as response:
                body = response.read(65537)
                if len(body) > 65536:
                    raise OAuthError("response")
                result = json.loads(body)
        except HTTPError:
            # Never retry a consumed code and never echo server bodies/URLs.
            raise OAuthError("exchange" if form is not None else "configuration") from None
        except OAuthError:
            raise
        except (OSError, ValueError):
            raise OAuthError("network") from None
        if not isinstance(result, dict):
            raise OAuthError("response")
        return result


def validate_discovery(metadata):
    required = {"issuer": ISSUER, "authorization_endpoint": AUTHORIZE, "token_endpoint": TOKEN}
    if any(metadata.get(k) != v for k, v in required.items()):
        raise OAuthError("configuration")
    for name, value in (("response_types_supported", "code"),
                        ("token_endpoint_auth_methods_supported", "none"),
                        ("scopes_supported", SCOPE)):
        if not isinstance(metadata.get(name), list) or value not in metadata[name]:
            raise OAuthError("configuration")
    if "code_challenge_methods_supported" in metadata and (
            not isinstance(metadata["code_challenge_methods_supported"], list) or
            "S256" not in metadata["code_challenge_methods_supported"]):
        raise OAuthError("configuration")
    if "grant_types_supported" in metadata and "authorization_code" not in metadata["grant_types_supported"]:
        raise OAuthError("configuration")


class OAuthAttempt:
    """One transaction, one code exchange; run on a worker, never the Qt thread."""
    def __init__(self, transport=None, *, timeout=120, resource=None, clock=time.monotonic):
        if resource not in (None, RESOURCE):
            raise OAuthError("configuration")
        self.transport = transport or OAuthTransport()
        self.clock, self.timeout, self.resource = clock, min(timeout, 120), resource
        self.verifier = secrets.token_urlsafe(48)
        self.state = secrets.token_urlsafe(32)
        from phase_studio.error_reporting import register_private_value
        register_private_value(self.verifier)
        register_private_value(self.state)
        self.cancelled = threading.Event()
        self.server = None
        self.credential = None
        self.error = None
        self.consumed = False
        self.exchange_started = False
        self.redirect_uri = ""

    def cancel(self):
        self.cancelled.set()

    def authorization_url(self):
        fields = dict(response_type="code", client_id=CLIENT_ID, redirect_uri=self.redirect_uri,
                      scope=SCOPE, state=self.state, code_challenge=pkce_challenge(self.verifier),
                      code_challenge_method="S256")
        if self.resource:
            fields["resource"] = self.resource
        return AUTHORIZE + "?" + urlencode(fields)

    def exchange(self, code):
        if self.exchange_started:
            raise OAuthError("exchange")
        self.exchange_started = True
        from phase_studio.error_reporting import register_private_value
        register_private_value(code)
        started = self.clock()
        started_utc = time.time()
        form = dict(grant_type="authorization_code", code=code,
                    redirect_uri=self.redirect_uri, client_id=CLIENT_ID, code_verifier=self.verifier)
        if self.resource:
            form["resource"] = self.resource
        response = self.transport.json(TOKEN, form)
        token = response.get("access_token")
        # Register even a malformed response's token before any further handling.
        if isinstance(token, str):
            register_private_value(token)
        expiry = response.get("expires_in")
        if (not isinstance(token, str) or not token or token.strip() != token or
                any(ord(c) < 33 or ord(c) >= 127 for c in token) or len(token) > 16384 or
                str(response.get("token_type", "")).lower() != "bearer" or
                not isinstance(response.get("scope"), str) or SCOPE not in response["scope"].split() or
                isinstance(expiry, bool) or not isinstance(expiry, (int, float)) or not 60 < expiry <= 3600 or
                "id_token" in response or "refresh_token" in response):
            raise OAuthError("response")
        return OAuthCredential(token, started + expiry, response["scope"], started_utc + expiry)

    def run(self, ready, progress=lambda state: None):
        try:
            validate_discovery(self.transport.json(DISCOVERY))
            if self.cancelled.is_set():
                raise OAuthError("cancelled")
            owner = self

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass  # HTTP request lines contain the authorization code.

                def reply(self, status, text):
                    body = ("<!doctype html><title>Phase Studio</title><h1>" + text +
                            "</h1><p>You can return to Phase Studio.</p>").encode("utf8")
                    self.send_response(status)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    try:
                        self.wfile.write(body)
                    except OSError:
                        pass

                def do_POST(self):
                    self.reply(405, "Invalid sign-in response")

                def do_GET(self):
                    try:
                        parts = urlsplit(self.path)
                        query = parse_qs(parts.query, keep_blank_values=True, strict_parsing=True, max_num_fields=12)
                    except ValueError:
                        self.reply(400, "Invalid sign-in response")
                        return
                    if (parts.path != "/callback" or parts.scheme or parts.netloc or parts.fragment or
                            len(self.path) > 8192 or len(self.headers.get_all("Host", [])) != 1 or
                            self.headers.get("Host") != urlsplit(owner.redirect_uri).netloc or
                            any(len(v) != 1 for v in query.values()) or
                            set(query) - {"state", "code", "error", "error_description", "error_uri", "iss"} or
                            not query.get("state", [""])[0].isascii() or
                            not secrets.compare_digest(query.get("state", [""])[0], owner.state) or
                            ("iss" in query and query["iss"] != [ISSUER]) or
                            ("code" in query) == ("error" in query) or
                            not query.get("code", query.get("error", [""]))[0]):
                        self.reply(400, "Invalid sign-in response")
                        return
                    if owner.consumed or owner.cancelled.is_set() or owner.clock() >= owner.deadline:
                        self.reply(409, "Sign-in is no longer pending")
                        return
                    owner.consumed = True
                    if "error" in query:
                        owner.error = OAuthError("cancelled" if query["error"] == ["access_denied"] else "exchange")
                    else:
                        progress("exchange")
                        try:
                            credential = owner.exchange(query["code"][0])
                            if owner.cancelled.is_set():
                                raise OAuthError("cancelled")
                            if owner.clock() >= owner.deadline:
                                raise OAuthError("timeout")
                            owner.credential = credential
                        except OAuthError as exc:
                            owner.error = exc
                    self.reply(200 if owner.credential else 400,
                               "Sign-in completed" if owner.credential else "Sign-in could not be completed")

            try:
                self.server = HTTPServer(("127.0.0.1", 0), Handler)
            except OSError:
                raise OAuthError("port") from None
            self.server.timeout = .2
            # Bound the individual accepted socket as well as accept().
            original_get_request = self.server.get_request
            def get_request():
                sock, address = original_get_request()
                sock.settimeout(2)
                return sock, address
            self.server.get_request = get_request
            self.redirect_uri = f"http://127.0.0.1:{self.server.server_port}/callback"
            self.deadline = self.clock() + self.timeout
            ready(self.authorization_url())
            while not self.consumed and not self.cancelled.is_set() and self.clock() < self.deadline:
                self.server.handle_request()
            if self.cancelled.is_set():
                raise OAuthError("cancelled")
            if self.error:
                raise self.error
            if not self.credential:
                raise OAuthError("timeout")
            return self.credential
        finally:
            if self.server:
                self.server.server_close()
            self.verifier = self.state = ""
