"""Manual keys and expiring OAuth grants use separate WinCred targets.

No credentials are written to QSettings. Headless/offscreen processes use
session-only access unless a storage backend is explicitly supplied.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import threading
import time
from ctypes import wintypes
from urllib.parse import urlsplit

from phase_studio.sharped_server_client import DEFAULT_SERVER_URL


def credential_origin(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("A valid SharpED server address is required.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{parsed.scheme}://{parsed.hostname.lower()}:{port}"


class WindowsCredentialBackend:
    """Standard WinCred generic credentials, scoped to the current user/device."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Windows Credential Manager is unavailable.")

        class Credential(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        self.Credential = Credential
        self.api = ctypes.WinDLL("advapi32", use_last_error=True)
        pointer = ctypes.POINTER(Credential)
        self.api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(pointer)]
        self.api.CredReadW.restype = wintypes.BOOL
        self.api.CredWriteW.argtypes = [pointer, wintypes.DWORD]
        self.api.CredWriteW.restype = wintypes.BOOL
        self.api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self.api.CredDeleteW.restype = wintypes.BOOL
        self.api.CredFree.argtypes = [ctypes.c_void_p]
        self.api.CredFree.restype = None

    @staticmethod
    def target(origin: str) -> str:
        return "FZU/PhaseStudio/SharpED/" + hashlib.sha256(origin.encode("utf8")).hexdigest()

    def read(self, origin: str) -> str:
        pointer = ctypes.POINTER(self.Credential)()
        if not self.api.CredReadW(self.target(origin), 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:  # ERROR_NOT_FOUND
                return ""
            raise OSError("Saved SharpED access could not be read.")
        try:
            value = pointer.contents
            return ctypes.string_at(value.CredentialBlob, value.CredentialBlobSize).decode("utf8")
        finally:
            self.api.CredFree(pointer)

    def write(self, origin: str, token: str) -> None:
        data = token.encode("utf8")
        if len(data) > 2560:
            raise ValueError("This access key is too long for secure storage.")
        blob = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        credential = self.Credential()
        credential.Type = 1  # CRED_TYPE_GENERIC
        credential.TargetName = self.target(origin)
        credential.UserName = "Jana2020 account"
        credential.CredentialBlobSize = len(data)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE: current user, no roaming
        if not self.api.CredWriteW(ctypes.byref(credential), 0):
            raise OSError("SharpED access could not be saved securely.")

    def delete(self, origin: str) -> None:
        if not self.api.CredDeleteW(self.target(origin), 1, 0) and ctypes.get_last_error() != 1168:
            raise OSError("Saved SharpED access could not be removed.")


class CredentialStore:
    def __init__(self, backend=None) -> None:
        self.backend = backend
        self._session: dict[str, str] = {}
        self._remember: dict[str, bool] = {}
        self._oauth = None
        self._oauth_selected = False
        self._oauth_fingerprints: set[str] = set()
        self._oauth_renew_lock = threading.Lock()
        self._oauth_state_lock = threading.RLock()
        self.reauthorize = None
        self._bindings = []
        self._oauth_loaded = False
        self._oauth_remember = backend is not None
        self.oauth_storage_error = False

    @staticmethod
    def oauth_target():
        from phase_studio.oauth import ISSUER, RESOURCE, CLIENT_ID
        return "oauth:v1|" + ISSUER + "|" + RESOURCE + "|" + CLIENT_ID

    def _restore_oauth(self):
        from phase_studio.oauth import OAuthCredential, ISSUER, RESOURCE, CLIENT_ID, SCOPE
        with self._oauth_state_lock:
            if self._oauth_loaded:
                return
            self._oauth_loaded = True
            if self.backend is None:
                return
            try:
                record = json.loads(self.backend.read(self.oauth_target()) or "null")
                if not isinstance(record, dict) or type(record.get('schema')) is not int or record['schema'] != 1:
                    return
                if (record.get('issuer'), record.get('resource'), record.get('client_id')) != (ISSUER, RESOURCE, CLIENT_ID):
                    return
                token, scope = record['access_token'], record['scope']
                deadline, saved = record['expires_at_utc'], record['saved_at_utc']
                if not all(type(v) in (int, float) and math.isfinite(v) for v in (deadline, saved)):
                    return
                now = time.time()
                # Reject clock rollback and impossible lifetimes, never extend a grant.
                if not saved <= now < deadline or not 60 < deadline - saved <= 3600:
                    return
                if (not isinstance(token, str) or not token or len(token) > 16384 or
                        any(ord(c) < 33 or ord(c) >= 127 for c in token) or
                        not isinstance(scope, str) or SCOPE not in scope.split()):
                    return
                from phase_studio.sharped_server_client import SharpEDServerClient
                SharpEDServerClient._validate_request_headers({'Authorization': 'Bearer ' + token})
                credential = OAuthCredential(token, time.monotonic() + deadline - now, scope, deadline)
                if not credential.usable():
                    return
                self._redact(token)
                self._oauth_fingerprints.add(hashlib.sha256(token.encode('utf8')).hexdigest())
                self._oauth = credential
                self._oauth_selected = True
                self._oauth_remember = True
            except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
                return  # Leave unreadable saved data intact; a new sign-in can replace it.

    @staticmethod
    def _oauth_origin(base_url):
        try:
            return credential_origin(base_url) in {
                "https://jana.fzu.cz:443", "https://sharped.fzu.cz:443",
            }
        except ValueError:
            return False

    def is_oauth(self, token):
        self._restore_oauth()
        return bool(token) and hashlib.sha256(token.encode("utf8")).hexdigest() in self._oauth_fingerprints

    def activate_oauth(self, credential, *, remember=None):
        self._redact(credential.access_token)
        with self._oauth_state_lock:
            self._oauth_loaded = True
            if remember is not None:
                self._oauth_remember = bool(remember)
            self._oauth_fingerprints.add(hashlib.sha256(credential.access_token.encode("utf8")).hexdigest())
            self._oauth = credential
            self._oauth_selected = True
            self.oauth_storage_error = False
            if self.backend is not None:
                try:
                    if self._oauth_remember:
                        from phase_studio.oauth import ISSUER, RESOURCE, CLIENT_ID
                        now = time.time()
                        remaining = credential.expires_at - time.monotonic()
                        deadline = credential.expires_at_utc
                        if deadline is None:
                            deadline = now + remaining
                        deadline = min(deadline, now + remaining)
                        if not math.isfinite(deadline) or not 60 < deadline - now <= 3600:
                            raise ValueError('Invalid OAuth lifetime')
                        self.backend.write(self.oauth_target(), json.dumps(dict(schema=1,
                            issuer=ISSUER, resource=RESOURCE, client_id=CLIENT_ID,
                            scope=credential.scope, access_token=credential.access_token,
                            saved_at_utc=now, expires_at_utc=deadline)))
                    else:
                        self.backend.delete(self.oauth_target())
                except (OSError, ValueError, UnicodeError):
                    self.oauth_storage_error = True
        self._notify()

    def sign_out_oauth(self):
        with self._oauth_state_lock:
            if self.backend is not None:
                self.backend.delete(self.oauth_target())
            self._oauth_loaded = True
            self._oauth_selected = False
            self._oauth = None
        self._notify()

    def reject_oauth(self, token):
        """Only a server 401 rejects a grant; never replay its upload."""
        from dataclasses import replace
        with self._oauth_state_lock:
            if self._oauth is not None and self._oauth.access_token == token:
                if self.backend is not None:
                    self.backend.delete(self.oauth_target())
                self._oauth = replace(self._oauth, expires_at=0)

    def bind_input(self, widget, base_url=lambda: DEFAULT_SERVER_URL):
        """Keep live Qt credential fields synchronized without persisting text edits."""
        import weakref
        from PySide6.QtCore import QObject, Signal, Slot
        from phase_studio.oauth_ui import install_reauthorization
        install_reauthorization(self)
        store = self

        class Binding(QObject):
            refresh = Signal()

            @Slot()
            def update(self):
                widget.setText(store.get(base_url()))

        binding = Binding(widget)
        binding.refresh.connect(binding.update)
        self._bindings.append(weakref.ref(binding))
        # Retain the Python wrapper until the owning field is destroyed.
        widget._credential_binding = binding

    def _notify(self):
        live = []
        for reference in self._bindings:
            binding = reference()
            if binding is not None:
                try:
                    binding.refresh.emit()
                    live.append(reference)
                except RuntimeError:
                    pass  # Qt owner has already been destroyed.
        self._bindings = live

    def authentication_method(self, base_url=DEFAULT_SERVER_URL):
        self._restore_oauth()
        with self._oauth_state_lock:
            return "oauth" if self._oauth_selected and self._oauth_origin(base_url) else "manual"

    def oauth_for_request(self, token, *, force=False, cancel_event=None):
        """Serialized browser renewal; retired tokens identify the same session.

        OAuth grants use a separate issuer/resource/client credential target.
        Reauthorization is a Qt-mediated callback installed by the account UI.
        """
        from phase_studio.oauth import OAuthError
        with self._oauth_renew_lock:
            if cancel_event is not None and cancel_event.is_set():
                raise OAuthError("cancelled")
            with self._oauth_state_lock:
                credential = self._oauth
                if not self._oauth_selected or credential is None:
                    raise OAuthError("cancelled")
                if credential.usable() and (not force or token != credential.access_token):
                    return credential.access_token
            if self.reauthorize is None:
                raise OAuthError("exchange")
            credential = self.reauthorize() if cancel_event is None else self.reauthorize(cancel_event)
            with self._oauth_state_lock:
                if (credential is None or not self._oauth_selected or
                        cancel_event is not None and cancel_event.is_set()):
                    raise OAuthError("cancelled")
                self.activate_oauth(credential)
                return credential.access_token

    @property
    def persistent_available(self) -> bool:
        return self.backend is not None

    def get(self, base_url: str = DEFAULT_SERVER_URL) -> str:
        self._restore_oauth()
        with self._oauth_state_lock:
            if self._oauth_selected and self._oauth_origin(base_url):
                return self._oauth.access_token
        try:
            origin = credential_origin(base_url)
        except ValueError:
            return ""  # Invalid saved server settings must remain repairable.
        if not self._session.get(origin):
            value = ""
            if self.backend is not None:
                try:
                    value = self.backend.read(origin)
                except (OSError, ValueError, UnicodeError):
                    pass  # A new key can always be supplied for this session.
            self._session[origin] = value
            self._remember[origin] = bool(value)
            self._redact(value)
        return self._session[origin]

    def remembered(self, base_url: str = DEFAULT_SERVER_URL) -> bool:
        if self.authentication_method(base_url) == "oauth":
            return False
        self.get(base_url)
        try:
            return self._remember.get(credential_origin(base_url), False)
        except ValueError:
            return False

    @staticmethod
    def _redact(token: str) -> None:
        if token:
            from phase_studio.error_reporting import register_private_value
            register_private_value(token)

    def set(self, token: str, *, remember: bool | None = None, base_url: str = DEFAULT_SERVER_URL) -> None:
        token = str(token or "")
        if not token:
            return  # Empty configuration is not an explicit removal request.
        from phase_studio.sharped_server_client import SharpEDServerClient
        SharpEDServerClient._validate_request_headers({"Authorization": "Bearer " + token})
        if self.is_oauth(token):
            raise ValueError("OAuth access uses separate secure sign-in storage.")
        origin = credential_origin(base_url)
        self._redact(token)
        if remember is None:
            remember = self.persistent_available
        if remember and token:
            if self.backend is None:
                raise OSError("Secure storage is unavailable. Use access for this session only.")
            self.backend.write(origin, token)
        self._session[origin] = token
        self._remember[origin] = bool(remember and token)
        if self._oauth_origin(base_url):
            self.sign_out_oauth()
        self._notify()

    def save_input(self, token: str, base_url: str = DEFAULT_SERVER_URL) -> None:
        if not token:
            return
        if self.is_oauth(str(token or "").strip()):
            return  # A scientific config may retain the previous session token.
        if str(token or "").strip() == self.get(base_url):
            return
        self.set(token, base_url=base_url)

    def remove(self, base_url: str = DEFAULT_SERVER_URL) -> None:
        origin = credential_origin(base_url)
        if self.backend is not None:
            self.backend.delete(origin)
        self._session[origin] = ""
        self._remember[origin] = False
        self._notify()

    def load_settings(self, shared, legacy=None, base_url: str = DEFAULT_SERVER_URL) -> str:
        """Migrate legacy keys securely before removing their old copies.

        If secure storage fails, retain the legacy copy for a future retry.
        Never create a new plaintext copy or destroy the only surviving key.
        """
        value = self.get(base_url)
        previous = str(shared.value("inputs/sharped_api_token", "") or "").strip()
        if legacy is not None:
            previous = previous or str(legacy.value("api_token", "") or "").strip()
        if previous and not value:
            try:
                self.set(previous, remember=True, base_url=base_url)
            except (OSError, ValueError, RuntimeError):
                self._redact(previous)  # Return only to the current UI session.
            value = previous
        # Do not discard a different legacy key silently, even if a secure
        # credential already exists for this origin.
        if self.remembered(base_url) and (not previous or previous == value == self.get(base_url)):
            shared.remove("inputs/sharped_api_token")
            shared.sync()
            if legacy is not None and str(legacy.value("api_token", "") or "").strip() in ("", value):
                legacy.remove("api_token")
                legacy.sync()
        return value


def _default_backend():
    if os.name != "nt" or os.environ.get("QT_QPA_PLATFORM", "").lower().split(":", 1)[0] == "offscreen":
        return None
    try:
        return WindowsCredentialBackend()
    except (OSError, AttributeError):
        return None


credential_store = CredentialStore(_default_backend())
