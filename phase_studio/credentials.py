"""Session credentials and optional Windows Credential Manager persistence.

No credentials are written to QSettings. Headless/offscreen processes use
session-only access unless a storage backend is explicitly supplied.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
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

    @property
    def persistent_available(self) -> bool:
        return self.backend is not None

    def get(self, base_url: str = DEFAULT_SERVER_URL) -> str:
        try:
            origin = credential_origin(base_url)
        except ValueError:
            return ""  # Invalid saved server settings must remain repairable.
        if origin not in self._session:
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

    def set(self, token: str, *, remember: bool = False, base_url: str = DEFAULT_SERVER_URL) -> None:
        token = str(token or "").strip()
        origin = credential_origin(base_url)
        self._redact(token)
        if remember and token:
            if self.backend is None:
                raise OSError("Secure storage is unavailable. Use access for this session only.")
            self.backend.write(origin, token)
        elif self.backend is not None and self.remembered(base_url):
            self.backend.delete(origin)
        self._session[origin] = token
        self._remember[origin] = bool(remember and token)

    def save_input(self, token: str, base_url: str = DEFAULT_SERVER_URL) -> None:
        if str(token or "").strip() == self.get(base_url):
            return
        self.set(token, remember=self.remembered(base_url), base_url=base_url)

    def remove(self, base_url: str = DEFAULT_SERVER_URL) -> None:
        origin = credential_origin(base_url)
        if self.backend is not None:
            self.backend.delete(origin)
        self._session[origin] = ""
        self._remember[origin] = False

    def load_settings(self, shared, legacy=None, base_url: str = DEFAULT_SERVER_URL) -> str:
        """Retain old plaintext access for this session, then remove old copies.

        Persistence now requires the user's explicit Remember choice. Migration
        never silently writes a private key into a new persistent backend.
        """
        value = self.get(base_url)
        previous = str(shared.value("inputs/sharped_api_token", "") or "").strip()
        if legacy is not None:
            previous = previous or str(legacy.value("api_token", "") or "").strip()
        if previous and not value:
            try:
                self.set(previous, base_url=base_url)
            except ValueError:
                self._redact(previous)  # Return only to the current UI session.
            value = previous
        shared.remove("inputs/sharped_api_token")
        shared.sync()
        if legacy is not None:
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
