from __future__ import annotations

import json
import mimetypes
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ProgressLog = Optional[Callable[[str], None]]


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


class SharpEDServerError(RuntimeError):
    pass


class SharpEDServerClient:
    def __init__(
        self,
        base_url: str = "https://jana.fzu.cz",
        user_agent: str = "PhaseStudio-SharpED/1.0",
        timeout: float = 600.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout = timeout

    def get_models(self, log: ProgressLog = None) -> ModelsResult:
        if log:
            log("SharpED server: fetching available models")
        body = self._request_text("GET", self._url("/sharp-ed/models"))
        data = self._loads_json(body, "Models")
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
        self._raise_if_stopped(stop_event)
        upload = self.upload(file_path, bearer_token, elements, model, outres, log=log)
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
                log(f"SharpED server: downloading result to {out_path}")
            self._write_download_body(status.download_bytes, out_path)
        else:
            self.download(status.download_url, out_path, primary_token=upload.token, fallback_token=bearer_token, log=log)
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
            log(f"SharpED server: uploading {file_path.name} ({len(body)} bytes)")

        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        }
        text = self._request_text("POST", self._url("/api/user/sharp-ed/upload"), data=body, headers=headers)
        data = self._loads_json(text, "Upload")
        if not data.get("success", False):
            raise SharpEDServerError(f"SharpED upload failed: {text}")
        token = str(data.get("token") or "")
        status_url = str(data.get("status_url") or "")
        if status_url:
            status_url = self._absolute_url(status_url)
        if not status_url and token:
            status_url = self._url(f"/api/user/sharp-ed/status/{token}")
        if log:
            log(f"SharpED server: uploaded job_id={data.get('job_id', -1)}, token={token or '<missing>'}")
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
        while max_polls < 0 or polls < max_polls:
            self._raise_if_stopped(stop_event)
            status = self.get_status(status_url, job_token, bearer_token)
            if log:
                log(f"SharpED server status: {status.status or '<empty>'}")
            if status.completed:
                return status
            if status.failed:
                raise SharpEDServerError(f"SharpED processing failed: {status.error_message}")
            probe = self._probe_download(job_token, bearer_token)
            if probe is not None:
                if log:
                    log("SharpED server: result is downloadable although status still reports processing; continuing.")
                return StatusResult(
                    status=status.status or "downloadable",
                    output_file_name=status.output_file_name,
                    download_url=self._url(f"/api/user/sharp-ed/download/{job_token}"),
                    error_message="",
                    raw_json=status.raw_json,
                    download_bytes=probe,
                )
            polls += 1
            deadline = time.monotonic() + max(1, int(poll_seconds))
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
            log(f"SharpED server: downloading result to {out_path}")
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
        except SharpEDServerError:
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

    def _request_bytes(self, method: str, url: str, data: Optional[bytes] = None, headers: Optional[dict[str, str]] = None) -> bytes:
        req_headers = {"User-Agent": self.user_agent}
        req_headers.update(headers or {})
        req = Request(url, data=data, headers=req_headers, method=method)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise SharpEDServerError(f"SharpED HTTP error {exc.code} for {url}. Body: {body}") from exc
        except URLError as exc:
            raise SharpEDServerError(f"SharpED request failed for {url}: {exc}") from exc

    def _request_text_with_auth_candidates(self, url: str, tokens: list[str]) -> str:
        return self._request_bytes_with_auth_candidates(url, tokens).decode("utf-8", errors="replace")

    def _request_bytes_with_auth_candidates(self, url: str, tokens: list[str]) -> bytes:
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
            raise SharpEDServerError(f"{label} JSON parse failed: {exc}") from exc
        if not isinstance(data, dict):
            raise SharpEDServerError(f"{label} response is not a JSON object: {body}")
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
