from __future__ import annotations

import json
import mimetypes
import os
import re
import socket
import ssl
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

try:
    from phase_studio.error_reporting import sanitize_error_details
except Exception:
    from error_reporting import sanitize_error_details

try:
    from phase_studio.performance import profile_stage
except Exception:
    from performance import profile_stage


ProgressLog = Optional[Callable[[str], None]]
DEFAULT_SERVER_URL = "https://jana.fzu.cz/"


def polling_delay_seconds(completed_polls: int, configured_seconds: int) -> float:
    """Return the bounded wait before the next SharpED status request.

    The first two waits are capped at one second. Long-running jobs then use
    the configured interval unchanged, adding at most one early status/probe
    pair for the default two-second setting while reducing short-job detection
    latency without sustained extra server load.
    """
    configured = float(max(1, int(configured_seconds)))
    return min(configured, 1.0) if int(completed_polls) <= 2 else configured


def redact_server_diagnostic(value: object) -> str:
    return sanitize_error_details(value)


@dataclass
class UploadResult:
    job_id: int
    token: str
    status_url: str
    raw_json: str


@dataclass
class StatusResult:
    status: str
    output_file_name: str
    download_url: str
    error_message: str
    raw_json: str
    download_bytes: Optional[bytes] = None

    @property
    def completed(self) -> bool:
        status = str(self.status or "").strip().lower()
        if status in {"completed", "complete", "done", "ready", "finished", "success", "succeeded"}:
            return True
        return bool(self.download_url or self.output_file_name)

    @property
    def failed(self) -> bool:
        return str(self.status or "").strip().lower() in {"failed", "failure", "error", "errored", "cancelled", "canceled"}


@dataclass
class ModelsResult:
    default_model: str
    models: list[str]
    raw_json: str
    provenance: str = "live"


def reconcile_model_selection(
    previous: str, models: list[str], server_default: str,
) -> tuple[list[str], str]:
    """Resolve one stable selector view without network or widget behavior."""
    default_model = str(server_default or "").strip()
    values = ["default"]
    for candidate in [default_model, *list(models or [])]:
        value = str(candidate or "").strip()
        if value and value not in values:
            values.append(value)
    requested = str(previous or "").strip() or "default"
    displayed = requested if requested in values else "default"
    return values, displayed


class SharpEDServerError(RuntimeError):
    """A classified, sanitized SharpED transport or protocol failure."""

    def __init__(self, message: str, *, category: str = "server") -> None:
        super().__init__(sanitize_error_details(message))
        self.category = category


class SharpEDServerClient:
    def __init__(
        self,
        base_url: str = DEFAULT_SERVER_URL,
        user_agent: str = "PhaseStudio-SharpED/1.0",
        timeout: float = 600.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout = timeout
        self.ssl_context, self.tls_fallback_message = self._create_ssl_context()
        self._tls_fallback_logged = False
        self.performance_profiler = None

    @staticmethod
    def _create_ssl_context() -> tuple[ssl.SSLContext, str]:
        """Create a verified TLS context using the platform trust authority.

        CPython's OpenSSL build does not use the Windows certificate store by
        default.  The frozen Windows application therefore uses truststore's
        SSLContext, which delegates chain building to Windows while keeping
        CERT_REQUIRED and hostname verification enabled.  Other platforms
        retain Python's normal verified context.
        """
        if os.name == "nt":
            try:
                import truststore
            except ImportError as exc:
                raise SharpEDServerError(
                    "Windows system TLS trust is unavailable because the truststore package is missing.",
                    category="tls_configuration",
                ) from exc
            context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.verify_mode = ssl.CERT_REQUIRED
            context.check_hostname = True
            return context, "Windows system certificate store (truststore)"
        context = ssl.create_default_context()
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        return context, "Platform default verified certificate store"

    def _log_tls_fallback(self, log: ProgressLog) -> None:
        if log and self.tls_fallback_message and not self._tls_fallback_logged:
            log(f"[SharpED] TLS trust: {self.tls_fallback_message}")
            self._tls_fallback_logged = True

    def get_models(self, log: ProgressLog = None) -> ModelsResult:
        self._log_tls_fallback(log)
        if log:
            log("SharpED server: fetching available models")
        with profile_stage(self.performance_profiler, "SharpED model discovery", "external"):
            body = self._request_text("GET", self._url("/sharp-ed/models"))
        data = self._loads_json(body, "Models")
        if (not isinstance(data, dict) or not isinstance(data.get("models"), list)
                or any(not isinstance(item, str) or not item.strip() for item in data["models"])):
            raise SharpEDServerError("SharpED catalogue has an invalid models list.", category="malformed_catalog")
        return ModelsResult(
            default_model=str(data.get("default") or ""),
            models=[str(item) for item in data.get("models", []) if isinstance(item, str)],
            raw_json=body,
        )

    def execute(
        self,
        file_path: Path,
        bearer_token: str,
        out_path: Path,
        elements: str,
        model: str = "SharpED latest",
        outres: float = 0.2,
        poll_seconds: int = 2,
        max_polls: int = -1,
        log: ProgressLog = None,
        stop_event: object = None,
    ) -> Path:
        self._use_oauth_origin(bearer_token)
        self._oauth_stop_event = stop_event
        self._raise_if_stopped(stop_event)
        upload = self.upload(file_path, bearer_token, elements, model, outres, log=log)
        with profile_stage(self.performance_profiler, "SharpED server processing and polling", "external"):
            status = self.wait_for_completion(
                upload.status_url,
                upload.token,
                bearer_token,
                poll_seconds=poll_seconds,
                max_polls=max_polls,
                log=log,
                stop_event=stop_event,
            )
        if not status.download_url:
            status.download_url = self._url(f"/api/user/sharp-ed/download/{upload.token}")
        self._raise_if_stopped(stop_event)
        if status.download_bytes is not None:
            if log:
                log(f"  Result path: {out_path}")
            self._write_download_body(status.download_bytes, out_path)
        else:
            self.download(status.download_url, out_path, primary_token=upload.token, fallback_token=bearer_token, log=log)
        # A blocking transfer is an atomic network/file operation. Observe a
        # cancellation raised during it before any caller starts postprocessing.
        self._raise_if_stopped(stop_event)
        return out_path

    def upload(
        self,
        file_path: Path,
        bearer_token: str,
        elements: str,
        model: str,
        outres: float,
        log: ProgressLog = None,
    ) -> UploadResult:
        self._use_oauth_origin(bearer_token)
        from phase_studio.error_reporting import register_private_value
        register_private_value(bearer_token)
        self._log_tls_fallback(log)
        if not bearer_token:
            raise SharpEDServerError("Missing SharpED API token.")
        if not file_path.is_file():
            raise SharpEDServerError(f"Input map not found: {file_path}")

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        fields = {
            "elements": elements,
            "outres": f"{float(outres):.10g}",
            "model": model,
        }
        body, boundary = self._multipart_body(file_path, content_type, fields)
        if log:
            log(f"[SharpED] Model ID: {model} · displayed name: {model}")
            log(f"[SharpED] Uploading {file_path.name} · {len(body) / (1024 * 1024):.1f} MiB")

        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        }
        with profile_stage(self.performance_profiler, "SharpED upload transfer", "external"):
            text = self._request_text("POST", self._url("/api/user/sharp-ed/upload"), data=body, headers=headers)
        data = self._loads_json(text, "Upload")
        if not data.get("success", False):
            raise SharpEDServerError(f"SharpED upload failed: {redact_server_diagnostic(text)}")
        token = str(data.get("token") or "")
        status_url = str(data.get("status_url") or "")
        if status_url:
            status_url = self._absolute_url(status_url)
        if not status_url and token:
            status_url = self._url(f"/api/user/sharp-ed/status/{token}")
        if log:
            log(f"[SharpED] Job submitted · ID {data.get('job_id', -1)}")
        return UploadResult(
            job_id=int(data.get("job_id", -1)),
            token=token,
            status_url=status_url,
            raw_json=text,
        )

    def wait_for_completion(
        self,
        status_url: str,
        job_token: str,
        bearer_token: str,
        poll_seconds: int = 2,
        max_polls: int = -1,
        log: ProgressLog = None,
        stop_event: object = None,
    ) -> StatusResult:
        polls = 0
        last_logged_status = ""
        while max_polls < 0 or polls < max_polls:
            self._raise_if_stopped(stop_event)
            with profile_stage(self.performance_profiler, "SharpED status request", "external"):
                status = self.get_status(status_url, job_token, bearer_token)
            normalized_status = str(status.status or "<empty>").strip().lower()
            if log and normalized_status != last_logged_status:
                if normalized_status in {"processing", "running", "queued", "pending"}:
                    log("[SharpED] Processing…")
                elif normalized_status in {"completed", "complete", "done", "ready", "finished", "success", "succeeded"}:
                    log("[SharpED] Completed")
                else:
                    log(f"[SharpED] Status: {status.status or '<empty>'}")
                last_logged_status = normalized_status
            if status.completed:
                return status
            if status.failed:
                raise SharpEDServerError(f"SharpED processing failed: {status.error_message}")
            with profile_stage(self.performance_profiler, "SharpED compatibility download probe", "external"):
                probe = self._probe_download(job_token, bearer_token)
            if probe is not None:
                if log:
                    log("[SharpED] Result available · downloading…")
                    log(
                        "SharpED protocol detail: result became downloadable while status still reported "
                        f"{status.status or 'processing'}."
                    )
                return StatusResult(
                    status=status.status or "downloadable",
                    output_file_name=status.output_file_name,
                    download_url=self._url(f"/api/user/sharp-ed/download/{job_token}"),
                    error_message="",
                    raw_json=status.raw_json,
                    download_bytes=probe,
                )
            polls += 1
            deadline = time.monotonic() + polling_delay_seconds(polls, poll_seconds)
            with profile_stage(self.performance_profiler, "SharpED polling interval wait", "external"):
                while time.monotonic() < deadline:
                    self._raise_if_stopped(stop_event)
                    time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
        raise SharpEDServerError("SharpED processing did not finish within the polling limit.")

    def get_status(self, status_url: str, job_token: str, bearer_token: str) -> StatusResult:
        text = self._request_text_with_auth_candidates(status_url, [bearer_token, job_token])
        data = self._loads_json(text, "Status")
        status = self._find_string(data, {"status", "state", "phase"})
        download_url = self._find_string(data, {"downloadurl", "downloadlink", "resulturl"})
        output_file_name = self._find_string(data, {"outputfilename", "outputfile", "filename", "resultfile"})
        if download_url:
            download_url = self._absolute_url(download_url)
        if not download_url and job_token and (str(status).strip().lower() in {"completed", "complete", "done", "ready", "finished", "success", "succeeded"} or output_file_name):
            download_url = self._url(f"/api/user/sharp-ed/download/{job_token}")
        return StatusResult(
            status=status,
            output_file_name=output_file_name,
            download_url=download_url,
            error_message=str(data.get("error_message") or ""),
            raw_json=text,
        )

    def download(
        self,
        download_url: str,
        out_path: Path,
        primary_token: str,
        fallback_token: str,
        log: ProgressLog = None,
    ) -> None:
        if log:
            log(f"[SharpED] Downloading result to {out_path}")
        with profile_stage(self.performance_profiler, "SharpED download transfer", "external"):
            body = self._request_bytes_with_auth_candidates(download_url, [primary_token, fallback_token])
        self._write_download_body(body, out_path)

    def _write_download_body(self, body: bytes, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(body)
        if not out_path.is_file() or out_path.stat().st_size == 0:
            raise SharpEDServerError(f"SharpED download produced an empty output map: {out_path}")
        if not self._looks_like_map_payload(body):
            snippet = body[:200].decode("utf-8", errors="replace").replace("\n", " ")
            raise SharpEDServerError(f"SharpED download did not look like an XPLOR/CCP4 map. Response starts with: {snippet}")

    def _url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _absolute_url(self, url: str) -> str:
        if url.startswith(("http://", "https://")):
            return url
        return self._url(url)

    def _raise_if_stopped(self, stop_event: object = None) -> None:
        if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
            raise SharpEDServerError("Immediate stop requested during SharpED server processing.")

    def _probe_download(self, job_token: str, bearer_token: str) -> Optional[bytes]:
        if not job_token:
            return None
        try:
            body = self._request_bytes_with_auth_candidates(
                self._url(f"/api/user/sharp-ed/download/{job_token}"),
                [job_token, bearer_token],
            )
        except SharpEDServerError as exc:
            from phase_studio.credentials import credential_store
            if credential_store.is_oauth(bearer_token) and exc.category in {"authentication", "authorization"}:
                raise  # Do not hide repeated login/permission failure in polling.
            return None
        return body if self._looks_like_map_payload(body) else None

    def _looks_like_map_payload(self, body: bytes) -> bool:
        if not body:
            return False
        head = body[:512].lstrip()
        if not head:
            return False
        if head[:1] in {b"{", b"["} or head[:1] == b"<":
            return False
        lower = head.decode("utf-8", errors="ignore").lower()
        if "not ready" in lower or lower.startswith(("error", "failed")):
            return False
        return True

    def _find_string(self, value: object, keys: set[str]) -> str:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key).replace("_", "").replace("-", "").lower()
                if normalized in keys and item not in (None, ""):
                    return str(item)
            for item in value.values():
                found = self._find_string(item, keys)
                if found:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = self._find_string(item, keys)
                if found:
                    return found
        return ""

    def _request_text(self, method: str, url: str, data: Optional[bytes] = None, headers: Optional[dict[str, str]] = None) -> str:
        return self._request_bytes(method, url, data=data, headers=headers).decode("utf-8", errors="replace")

    def _use_oauth_origin(self, bearer_token):
        from phase_studio.credentials import credential_store
        if credential_store.is_oauth(bearer_token):
            from phase_studio.oauth import RESOURCE
            self.base_url = RESOURCE

    def _request_bytes(self, method: str, url: str, data: Optional[bytes] = None, headers: Optional[dict[str, str]] = None,
                       *, _oauth_retry: bool = False) -> bytes:
        req_headers = {"User-Agent": self.user_agent}
        req_headers.update(headers or {})
        from phase_studio.credentials import credential_store
        bearer = req_headers.get("Authorization", "").removeprefix("Bearer ")
        oauth = credential_store.is_oauth(bearer)
        request_opener = urlopen
        if oauth:
            from phase_studio.oauth import RESOURCE, OAuthError, _NoRedirect
            from urllib.parse import urlsplit
            from urllib.request import build_opener, HTTPSHandler
            parsed = urlsplit(url)
            if (parsed.scheme != "https" or parsed.hostname != "sharped.fzu.cz" or
                    parsed.port not in (None, 443) or parsed.username or parsed.password):
                raise SharpEDServerError("OAuth credentials cannot be sent to this server.", category="authentication")
            try:
                bearer = credential_store.oauth_for_request(bearer, cancel_event=getattr(self, "_oauth_stop_event", None))
            except OAuthError as exc:
                raise SharpEDServerError(str(exc), category="authentication") from None
            req_headers["Authorization"] = "Bearer " + bearer
            opener = build_opener(_NoRedirect(), HTTPSHandler(context=self.ssl_context))
            request_opener = lambda request, **kwargs: opener.open(request, timeout=kwargs["timeout"])
        self._validate_request_headers(req_headers)
        req = Request(url, data=data, headers=req_headers, method=method)
        try:
            with request_opener(req, timeout=self.timeout, context=self.ssl_context) as resp:
                return resp.read()
        except HTTPError as exc:
            if oauth and exc.code == 401 and method == "GET" and not _oauth_retry:
                # GET status/download can resume. Never replay an upload POST.
                exc.close()
                try:
                    renewed = credential_store.oauth_for_request(bearer, force=True,
                        cancel_event=getattr(self, "_oauth_stop_event", None))
                except OAuthError as error:
                    raise SharpEDServerError(str(error), category="authentication") from None
                return self._request_bytes(method, url, data=data,
                    headers={**(headers or {}), "Authorization": "Bearer " + renewed}, _oauth_retry=True)
            body = exc.read().decode("utf-8", errors="replace")
            category = ("authentication" if exc.code == 401 else "authorization" if exc.code == 403
                        else "server" if exc.code >= 500 else "http")
            raise SharpEDServerError(
                f"SharpED HTTP error {exc.code} for {redact_server_diagnostic(url)}. "
                f"Body: {redact_server_diagnostic(body)}",
                category=category,
            ) from exc
        except URLError as exc:
            reason = exc.reason
            if isinstance(reason, ssl.SSLCertVerificationError) or "certificate_verify_failed" in str(reason).lower():
                raise SharpEDServerError(
                    "SharpED secure connection failed. Phase Studio reached sharped.fzu.cz, but could not verify "
                    "the server's TLS certificate chain. Check Windows updates and system date/time. If the "
                    f"problem persists, Phase Studio may not be using the Windows trusted certificate store. Technical detail: {reason}",
                    category="tls_certificate",
                ) from exc
            if isinstance(reason, socket.gaierror):
                category = "dns"
            elif isinstance(reason, (TimeoutError, socket.timeout)):
                category = "timeout"
            else:
                category = "unreachable"
            raise SharpEDServerError(
                f"SharpED request failed for {redact_server_diagnostic(url)}: {reason}", category=category,
            ) from exc
        except ssl.SSLCertVerificationError as exc:
            raise SharpEDServerError(
                "SharpED secure connection failed. Phase Studio reached sharped.fzu.cz, but could not verify "
                "the server's TLS certificate chain. Check Windows updates and system date/time. If the problem "
                f"persists, Phase Studio may not be using the Windows trusted certificate store. Technical detail: {exc}",
                category="tls_certificate",
            ) from exc
        except ssl.SSLError as exc:
            raise SharpEDServerError(
                f"SharpED secure connection failed for {redact_server_diagnostic(url)}: {exc}", category="tls",
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise SharpEDServerError(
                f"SharpED connection timed out for {redact_server_diagnostic(url)}: {exc}", category="timeout",
            ) from exc

    @staticmethod
    def _validate_request_headers(headers: dict[str, str]) -> None:
        """Reject invalid configuration before http.client can expose its value.

        Multipart metadata is UTF-8; HTTP field values are not UTF-8 strings.
        Bearer credentials use the ASCII b64token grammar (RFC 6750).
        Never include a supplied field name/value or encoding exception in errors.
        """
        for name, value in headers.items():
            if not isinstance(name, str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
                raise SharpEDServerError("Invalid SharpED HTTP header name. Check client configuration.", category="configuration")
            authorization = name.lower() == "authorization"
            valid = isinstance(value, str)
            if valid:
                valid = all(ch == "\t" or 32 <= ord(ch) <= 255 and ord(ch) != 127 for ch in value)
            if authorization:
                valid = valid and bool(re.fullmatch(r"Bearer [A-Za-z0-9._~+/-]+=*", value))
            if not valid:
                if authorization:
                    raise SharpEDServerError(
                        "Invalid SharpED authentication credential in Authorization header. "
                        "Sign in with Jana2020 again, or paste only the access key without labels or instructions.",
                        category="authentication",
                    ) from None
                label = "User-Agent" if name.lower() == "user-agent" else "configured"
                raise SharpEDServerError(
                    f"Invalid SharpED {label} HTTP header value. Check client configuration; "
                    "Unicode metadata belongs in the UTF-8 request body.", category="configuration",
                ) from None

    def _request_text_with_auth_candidates(self, url: str, tokens: list[str]) -> str:
        return self._request_bytes_with_auth_candidates(url, tokens).decode("utf-8", errors="replace")

    def _request_bytes_with_auth_candidates(self, url: str, tokens: list[str]) -> bytes:
        from phase_studio.credentials import credential_store
        oauth_tokens = [token for token in tokens if credential_store.is_oauth(token)]
        if oauth_tokens:
            # Job path identity is never substituted for account authorization.
            return self._request_bytes("GET", url, headers={"Authorization": "Bearer " + oauth_tokens[0]})
        candidates = [token for token in tokens if token]
        if not candidates:
            candidates = [""]
        last_error: Optional[SharpEDServerError] = None
        for token in candidates:
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            try:
                return self._request_bytes("GET", url, headers=headers)
            except SharpEDServerError as exc:
                last_error = exc
                message = str(exc)
                if "HTTP error 401" in message or "HTTP error 403" in message:
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise SharpEDServerError(f"SharpED request failed for {url}")

    def _loads_json(self, body: str, label: str) -> dict:
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise SharpEDServerError(f"{label} JSON parse failed: {exc}", category="malformed_catalog") from exc
        if not isinstance(data, dict):
            raise SharpEDServerError(
                f"{label} response is not a JSON object: {redact_server_diagnostic(body)}",
                category="malformed_catalog",
            )
        return data

    def _multipart_body(self, file_path: Path, content_type: str, fields: dict[str, str]) -> tuple[bytes, str]:
        boundary = "----PhaseStudioSharpED" + uuid.uuid4().hex
        chunks: list[bytes] = []
        chunks.append(
            (
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"file\"; filename=\"{file_path.name}\"\r\n"
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(file_path.read_bytes())
        chunks.append(b"\r\n")
        for key, value in fields.items():
            chunks.append(
                (
                    f"--{boundary}\r\n"
                    f"Content-Disposition: form-data; name=\"{key}\"\r\n\r\n"
                    f"{value}\r\n"
                ).encode("utf-8")
            )
        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
        return b"".join(chunks), boundary
