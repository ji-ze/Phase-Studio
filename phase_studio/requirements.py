"""One authoritative pre-run requirements check for Phase Studio workflows.

Both surfaces that can start a workflow -- the full Phase Studio GUI and the
Jana2020 Wizard -- ask this module, so the rules live in exactly one place and
cannot drift apart.

The check runs immediately BEFORE a requested workflow starts: after the final
configuration is known, but before any scientific output exists and before any
external program is launched. It never runs merely because the application
started; the user must always be able to inspect data, edit settings and browse
Help without being interrupted.

Only what the configured workflow actually needs is checked. A workflow that
never runs EDMA is never asked for EDMA.

Deliberately dependency-free apart from the standard library and this package's
own light helpers: no PySide6 import here, so the whole thing is testable
headlessly and the Jana2020 wrapper can use it without pulling in the GUI.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional, Sequence

# The canonical Jana2020 location both tools are normally installed into.
DEFAULT_JANA_SUPERFLIP_DIR = Path(r"C:\Jana2020\SUPERFLIP")

WRAPPER_EXE_NAME = "superflip.exe"
ORIGINAL_EXE_NAME = "superflip_original.exe"
EDMA_EXE_NAME = "EDMA.exe"

# Official third-party sources. Phase Studio never bundles or mirrors these.
SUPERFLIP_DOWNLOAD_URL = "https://superflip.fzu.cz/download/superflip_win.zip"
EDMA_DOWNLOAD_URL = "https://superflip.fzu.cz/download/EDMA_win.zip"
SUPERFLIP_LICENSE_URL = "https://superflip.fzu.cz/"
SHARPED_ACCOUNT_URL = "https://sharped.fzu.cz/sharp-ed"


class RequirementKind(str, Enum):
    SUPERFLIP = "superflip"
    EDMA = "edma"
    SHARPED = "sharped"


class RequirementState(str, Enum):
    """Why a requirement is (not) satisfied.

    The distinction matters because the remediation differs: telling someone to
    replace their API token when the real problem is a missing network
    connection sends them off to do the wrong thing.
    """

    OK = "ok"
    NOT_CONFIGURED = "not_configured"
    NOT_FOUND = "not_found"
    NOT_A_FILE = "not_a_file"
    IS_PHASE_STUDIO_WRAPPER = "is_phase_studio_wrapper"
    TOKEN_MISSING = "token_missing"
    TOKEN_REJECTED = "token_rejected"
    SERVER_UNREACHABLE = "server_unreachable"
    MALFORMED_RESPONSE = "malformed_response"


@dataclass(frozen=True)
class RequirementStatus:
    """The outcome of checking one requirement."""

    kind: RequirementKind
    state: RequirementState
    path: Optional[Path] = None
    detail: str = ""
    # Set when the check found a usable candidate the configuration does not
    # point at yet, so the caller can repair the setting without asking.
    suggested_path: Optional[Path] = None

    @property
    def ok(self) -> bool:
        return self.state is RequirementState.OK

    @property
    def title(self) -> str:
        return {
            RequirementKind.SUPERFLIP: "Superflip setup required",
            RequirementKind.EDMA: "EDMA setup required",
            RequirementKind.SHARPED: "SharpED access required",
        }[self.kind]

    @property
    def message(self) -> str:
        """User-facing explanation. Never contains a token or any secret."""
        if self.ok:
            return ""
        if self.kind is RequirementKind.SHARPED:
            return {
                RequirementState.TOKEN_MISSING:
                    "No SharpED API token is configured.",
                RequirementState.TOKEN_REJECTED:
                    "The SharpED API token was not accepted. Sign in to SharpED "
                    'and create a new token using "Create token".',
                RequirementState.SERVER_UNREACHABLE:
                    "Phase Studio could not reach the SharpED server. Check the "
                    "internet connection and try again.",
                RequirementState.MALFORMED_RESPONSE:
                    "The SharpED server returned an unexpected response.",
            }.get(self.state, "SharpED access could not be verified.")
        label = "Superflip" if self.kind is RequirementKind.SUPERFLIP else "EDMA"
        if self.state is RequirementState.IS_PHASE_STUDIO_WRAPPER:
            return (
                f"The configured {label} executable is the Phase Studio Jana2020 "
                f"launcher, not {label} itself. Select the real {label} executable "
                f"({ORIGINAL_EXE_NAME} in a Phase Studio-integrated Jana2020 "
                f"installation)."
            )
        return (
            f"Phase Studio could not find a working {label} executable. Select an "
            f"existing installation or install {label} before starting this workflow."
        )


@dataclass
class RequirementSet:
    """Which requirements a particular workflow actually needs."""

    superflip: bool = False
    edma: bool = False
    sharped: bool = False

    def kinds(self) -> List[RequirementKind]:
        # Remediation order: the cheapest and most fundamental first, so a user
        # fixing several things is not bounced between unrelated dialogs.
        ordered = []
        if self.superflip:
            ordered.append(RequirementKind.SUPERFLIP)
        if self.edma:
            ordered.append(RequirementKind.EDMA)
        if self.sharped:
            ordered.append(RequirementKind.SHARPED)
        return ordered


# ---------------------------------------------------------------------------
# Executable identification
# ---------------------------------------------------------------------------

def resolve_executable(value: object) -> Optional[Path]:
    """Resolve a configured executable string to a real file, or None."""
    raw = str(value or "").strip().strip('"')
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if candidate.is_file():
        return candidate.resolve()
    found = shutil.which(raw)
    return Path(found).resolve() if found else None


def is_phase_studio_wrapper(exe: Path) -> bool:
    """Is this executable the Phase Studio Jana2020 launcher rather than Superflip?

    This matters because after integration ``superflip.exe`` in the Jana2020
    directory IS the Phase Studio launcher, and the real program has been
    renamed to ``superflip_original.exe``. Running the launcher as if it were
    Superflip would recurse.

    Decided from the integration marker that the installer itself writes --
    the same authoritative source jana_integration uses -- never from the file
    name alone.
    """
    exe = Path(exe)
    if exe.name.lower() != WRAPPER_EXE_NAME:
        return False
    try:
        from phase_studio import jana_integration as ji

        marker, _error = ji.read_marker(exe.parent)
        if marker is not None and str(marker.wrapper).lower() == exe.name.lower():
            return True
        # A marked installation renames the real program; if that sibling
        # exists alongside an unmarked superflip.exe the wrapper is still the
        # most likely identity, but without a marker we do not claim it.
        return False
    except Exception:
        return False


def _check_executable(
    kind: RequirementKind,
    configured: object,
    candidates: Sequence[Path],
) -> RequirementStatus:
    """Shared Superflip/EDMA logic: validate, else look in known locations."""
    resolved = resolve_executable(configured)

    if resolved is not None and resolved.is_file():
        if kind is RequirementKind.SUPERFLIP and is_phase_studio_wrapper(resolved):
            # Configured path points at our own launcher: look for the real one
            # next to it before giving up.
            sibling = resolved.parent / ORIGINAL_EXE_NAME
            return RequirementStatus(
                kind=kind,
                state=RequirementState.IS_PHASE_STUDIO_WRAPPER,
                path=resolved,
                suggested_path=sibling if sibling.is_file() else None,
                detail=str(resolved),
            )
        return RequirementStatus(kind=kind, state=RequirementState.OK,
                                 path=resolved, detail=str(resolved))

    for candidate in candidates:
        candidate = Path(candidate)
        if not candidate.is_file():
            continue
        if kind is RequirementKind.SUPERFLIP and is_phase_studio_wrapper(candidate):
            continue
        return RequirementStatus(
            kind=kind,
            state=RequirementState.NOT_FOUND,
            path=resolved,
            suggested_path=candidate.resolve(),
            detail=f"Found a candidate at {candidate}",
        )

    state = (RequirementState.NOT_CONFIGURED
             if not str(configured or "").strip()
             else RequirementState.NOT_FOUND)
    return RequirementStatus(kind=kind, state=state, path=None,
                             detail=str(configured or ""))


def check_superflip(configured: object,
                    jana_dir: Path = DEFAULT_JANA_SUPERFLIP_DIR) -> RequirementStatus:
    """Validate the configured Superflip, else look in the Jana2020 directory.

    Candidate priority deliberately prefers ``superflip_original.exe``: in a
    Phase Studio-integrated Jana2020 installation that is the real program,
    while ``superflip.exe`` is our own launcher. A bare ``superflip.exe`` is
    only accepted when it is established not to be the wrapper.

    Never searches beyond the configured path and this one known directory.
    """
    jana_dir = Path(jana_dir)
    return _check_executable(
        RequirementKind.SUPERFLIP,
        configured,
        [jana_dir / ORIGINAL_EXE_NAME, jana_dir / WRAPPER_EXE_NAME],
    )


def check_edma(configured: object,
               jana_dir: Path = DEFAULT_JANA_SUPERFLIP_DIR) -> RequirementStatus:
    """Validate the configured EDMA, else look in the Jana2020 directory.

    Detection never modifies Jana2020's own EDMA; it only records where it is.
    """
    jana_dir = Path(jana_dir)
    return _check_executable(RequirementKind.EDMA, configured, [jana_dir / EDMA_EXE_NAME])


# ---------------------------------------------------------------------------
# SharpED
# ---------------------------------------------------------------------------

def check_sharped_api(base_url: str, token: str, *, timeout: float = 15.0,
                      client_factory: Optional[Callable[..., object]] = None) -> RequirementStatus:
    """Verify SharpED access as far as the existing API client allows.

    This uses the SAME client and shared model catalog as the application.
    A successful response from the last 15 seconds may be reused; otherwise
    it performs a real model request. Nothing creates or consumes a job.

    What this proves, honestly:

      * a token is configured at all (answered without any request);
      * the configured server was recently reachable and spoke the expected protocol;
      * the response is well formed.

    What it CANNOT prove with the current client: that the token will be
    accepted. ``get_models()`` is an unauthenticated endpoint, and the only
    authenticated operations available are uploading a job, polling it and
    downloading its result -- none of which is harmless enough to run as a
    preflight probe, and adding a new endpoint would mean a second API
    implementation. A rejected token therefore surfaces when the SharpED stage
    actually runs, and TOKEN_REJECTED is still produced here if the server ever
    does answer this request with 401/403.

    The token never appears in the returned status: every message is derived
    from the failure kind, never from the request or the exception text, so it
    cannot leak into a log or an error report.
    """
    if not str(token or "").strip():
        return RequirementStatus(kind=RequirementKind.SHARPED,
                                 state=RequirementState.TOKEN_MISSING)

    from phase_studio.sharped_server_client import SharpEDServerClient, MODEL_METADATA_REUSE_SECONDS

    if client_factory is None:
        client_factory = SharpEDServerClient

    try:
        client = client_factory(base_url=base_url, timeout=timeout)
        models = client.get_models(max_age=MODEL_METADATA_REUSE_SECONDS)
    except Exception as exc:  # noqa: BLE001 - classified below
        return _classify_sharped_error(exc)

    if models is None or not hasattr(models, "models"):
        return RequirementStatus(kind=RequirementKind.SHARPED,
                                 state=RequirementState.MALFORMED_RESPONSE)
    return RequirementStatus(kind=RequirementKind.SHARPED, state=RequirementState.OK)


def _classify_sharped_error(exc: BaseException) -> RequirementStatus:
    """Map a client exception onto the reason the user actually needs.

    Deliberately never echoes the exception text into `detail`: a failing
    request can carry the URL, and the URL can carry a token.
    """
    status_code = getattr(exc, "code", None) or getattr(exc, "status", None)
    text = f"{type(exc).__name__}: {exc}".lower()

    if status_code in (401, 403) or "unauthor" in text or "forbidden" in text:
        state = RequirementState.TOKEN_REJECTED
    elif isinstance(exc, (TimeoutError, ConnectionError)) or any(
        marker in text
        for marker in ("urlerror", "timed out", "timeout", "connection",
                       "getaddrinfo", "name or service", "unreachable", "ssl")
    ):
        state = RequirementState.SERVER_UNREACHABLE
    elif "json" in text or "decode" in text or "expecting value" in text:
        state = RequirementState.MALFORMED_RESPONSE
    elif isinstance(status_code, int) and 500 <= status_code < 600:
        state = RequirementState.SERVER_UNREACHABLE
    else:
        state = RequirementState.TOKEN_REJECTED
    return RequirementStatus(kind=RequirementKind.SHARPED, state=state)


# ---------------------------------------------------------------------------
# The workflow-level preflight
# ---------------------------------------------------------------------------

def requirements_for_workflow(*, needs_superflip: bool, needs_edma: bool,
                              needs_sharped: bool) -> RequirementSet:
    """Exactly what the configured workflow needs -- nothing more."""
    return RequirementSet(superflip=bool(needs_superflip),
                          edma=bool(needs_edma),
                          sharped=bool(needs_sharped))


@dataclass
class PreflightResult:
    statuses: List[RequirementStatus] = field(default_factory=list)
    repaired: List[RequirementStatus] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(status.ok for status in self.statuses)

    @property
    def failures(self) -> List[RequirementStatus]:
        return [status for status in self.statuses if not status.ok]

    @property
    def first_failure(self) -> Optional[RequirementStatus]:
        failures = self.failures
        return failures[0] if failures else None


def run_preflight(
    required: RequirementSet,
    *,
    superflip_path: object = "",
    edma_path: object = "",
    sharped_base_url: str = "",
    sharped_token: str = "",
    jana_dir: Path = DEFAULT_JANA_SUPERFLIP_DIR,
    client_factory: Optional[Callable[..., object]] = None,
    accept_suggestion: Optional[Callable[[RequirementStatus], bool]] = None,
) -> PreflightResult:
    """Check every requirement this workflow needs, in remediation order.

    When a check finds a usable executable the configuration does not point at
    yet, and *accept_suggestion* accepts it, the requirement is re-checked
    against that path and reported as repaired -- so a correct Jana2020
    installation simply works without asking the user anything.
    """
    result = PreflightResult()

    for kind in required.kinds():
        if kind is RequirementKind.SUPERFLIP:
            status = check_superflip(superflip_path, jana_dir=jana_dir)
        elif kind is RequirementKind.EDMA:
            status = check_edma(edma_path, jana_dir=jana_dir)
        else:
            status = check_sharped_api(sharped_base_url, sharped_token,
                                       client_factory=client_factory)

        if (not status.ok and status.suggested_path is not None
                and (accept_suggestion is None or accept_suggestion(status))):
            repaired = (check_superflip(status.suggested_path, jana_dir=jana_dir)
                        if kind is RequirementKind.SUPERFLIP
                        else check_edma(status.suggested_path, jana_dir=jana_dir))
            if repaired.ok:
                result.repaired.append(repaired)
                status = repaired
        result.statuses.append(status)

    return result
