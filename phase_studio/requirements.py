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

import hashlib
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Callable, List, Optional, Sequence, Tuple

# The canonical Jana2020 location both tools are normally installed into.
DEFAULT_JANA_SUPERFLIP_DIR = Path(r"C:\Jana2020\SUPERFLIP")

WRAPPER_EXE_NAME = "superflip.exe"
ORIGINAL_EXE_NAME = "superflip_original.exe"
EDMA_EXE_NAME = "EDMA.exe"

# Official third-party sources. Phase Studio never bundles or mirrors these.
SUPERFLIP_DOWNLOAD_URL = "https://superflip.fzu.cz/download/superflip_win.zip"
EDMA_DOWNLOAD_URL = "https://superflip.fzu.cz/download/EDMA_win.zip"
SUPERFLIP_LICENSE_URL = "https://superflip.fzu.cz/download/license_superflip.txt"
EDMA_LICENSE_URL = "https://superflip.fzu.cz/download/license_EDMA.txt"
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
    WRONG_EXECUTABLE = "wrong_executable"
    INCOMPATIBLE = "incompatible"
    MISSING_RUNTIME = "missing_runtime"
    CANNOT_LAUNCH = "cannot_launch"
    IS_PHASE_STUDIO_WRAPPER = "is_phase_studio_wrapper"
    TOKEN_MISSING = "token_missing"
    TOKEN_REJECTED = "token_rejected"
    ACCESS_DENIED = "access_denied"
    SERVER_UNAVAILABLE = "server_unavailable"
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
    # A successful SharpED reachability check already fetched the server's
    # model response. Keep its default for the immediately following run so
    # DEFAULT does not trigger the same public request a second time.
    sharped_default_model: str = ""
    # The model names of that same response (exact strings), so a workflow
    # that requires specific models can check them without a second request.
    sharped_models: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.state is RequirementState.OK

    @property
    def title(self) -> str:
        return {
            RequirementKind.SUPERFLIP: "Set up Superflip",
            RequirementKind.EDMA: "Set up EDMA",
            RequirementKind.SHARPED: "Connect to SharpED",
        }[self.kind]

    @property
    def message(self) -> str:
        """User-facing explanation. Never contains a token or any secret."""
        if self.ok:
            return ""
        if self.kind is RequirementKind.SHARPED:
            return {
                RequirementState.TOKEN_MISSING:
                    "Enter your SharpED access key to continue.",
                RequirementState.TOKEN_REJECTED:
                    "This access key was not accepted. Check the key associated with your Jana2020 account.",
                RequirementState.ACCESS_DENIED:
                    "Your Jana2020 account does not currently have permission to use SharpED processing. Check your SharpED account access.",
                RequirementState.SERVER_UNAVAILABLE:
                    "SharpED is temporarily unavailable. Please try again later.",
                RequirementState.SERVER_UNREACHABLE:
                    "Phase Studio could not reach the SharpED server. Check the "
                    "internet connection and try again.",
                RequirementState.MALFORMED_RESPONSE:
                    "The SharpED server returned an unexpected response.",
            }.get(self.state, "SharpED access could not be verified.")
        label = "Superflip" if self.kind is RequirementKind.SUPERFLIP else "EDMA"
        if self.state is RequirementState.INCOMPATIBLE:
            return f"This installation of {label} is not compatible with this computer. Choose another installation."
        if self.state is RequirementState.MISSING_RUNTIME:
            return f"{label} was found, but a required supporting file is missing. Repair the installation or choose another file."
        if self.state is RequirementState.CANNOT_LAUNCH:
            return f"{label} was found but could not be started safely. Choose another installation or use the official download page."
        if self.state is RequirementState.IS_PHASE_STUDIO_WRAPPER:
            return (
                f"The configured {label} executable is the Phase Studio Jana2020 "
                f"launcher, not {label} itself. Select the real {label} executable "
                f"({ORIGINAL_EXE_NAME} in a Phase Studio-integrated Jana2020 "
                f"installation)."
            )
        if self.state is RequirementState.WRONG_EXECUTABLE:
            return (
                f"The selected file could not be verified as a compatible {label} installation. "
                f"Choose another file or use the official download page."
            )
        if self.state is RequirementState.NOT_A_FILE:
            return f"The selected {label} location is a folder, not a program. Choose the program inside the installation."
        if self.state in (RequirementState.NOT_FOUND, RequirementState.NOT_CONFIGURED):
            purpose = "identify atomic positions" if self.kind is RequirementKind.EDMA else "solve structures using charge flipping"
            return f"{label} was not found on this computer. Phase Studio needs it to {purpose}."
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
            expected = str(getattr(marker, "payload_hash", "") or "").casefold()
            if expected:
                digest = hashlib.sha256(exe.read_bytes()).hexdigest().casefold()
                return digest == expected
        # A marked installation renames the real program; if that sibling
        # exists alongside an unmarked superflip.exe the wrapper is still the
        # most likely identity, but without a marker we do not claim it.
        return False
    except Exception:
        return False


def is_expected_executable(kind: RequirementKind, exe: Path) -> bool:
    """Verify format, identity, runtime and a bounded non-calculating launch."""
    from phase_studio.scientific_tools import validate_program
    if kind is RequirementKind.SUPERFLIP and is_phase_studio_wrapper(exe):
        return False
    return validate_program(kind, exe).ok


def _check_executable(
    kind: RequirementKind,
    configured: object,
    candidates: Sequence[Path],
) -> RequirementStatus:
    """Shared Superflip/EDMA logic: validate, else look in known locations."""
    configured_failure: Optional[RequirementStatus] = None
    search_candidates = list(candidates)
    raw_value = str(configured or "").strip().strip('"')
    raw_path = Path(raw_value).expanduser()
    # Bare legacy defaults ("superflip.exe" / "EDMA.exe") are PATH searches,
    # not an explicit installed path that can outrank the active Jana program.
    resolved = raw_path.resolve() if raw_value and raw_path.is_file() else None
    if resolved is None and raw_value:
        found = shutil.which(raw_value)
        if found:
            search_candidates.append(Path(found))
    if str(configured or "").strip() and raw_path.is_dir():
        configured_failure = RequirementStatus(kind, RequirementState.NOT_A_FILE, path=raw_path)

    if resolved is not None and resolved.is_file():
        if kind is RequirementKind.SUPERFLIP and is_phase_studio_wrapper(resolved):
            sibling = resolved.parent / ORIGINAL_EXE_NAME
            search_candidates.insert(0, sibling)
            configured_failure = RequirementStatus(kind, RequirementState.IS_PHASE_STUDIO_WRAPPER, path=resolved)
        elif not is_expected_executable(kind, resolved):
            from phase_studio.scientific_tools import validate_program
            validation = validate_program(kind, resolved)
            configured_failure = RequirementStatus(
                kind=kind,
                state=RequirementState(validation.state),
                path=resolved,
                detail=str(resolved),
            )
        else:
            return RequirementStatus(kind=kind, state=RequirementState.OK,
                                     path=resolved, detail=str(resolved))

    for candidate in search_candidates:
        candidate = Path(candidate)
        if not candidate.is_file():
            continue
        if kind is RequirementKind.SUPERFLIP and is_phase_studio_wrapper(candidate):
            continue
        if not is_expected_executable(kind, candidate):
            if configured_failure is None:
                from phase_studio.scientific_tools import validate_program
                validation = validate_program(kind, candidate)
                configured_failure = RequirementStatus(kind, RequirementState(validation.state), path=candidate)
            continue
        return RequirementStatus(
            kind=kind,
            state=(configured_failure.state if configured_failure is not None
                   else RequirementState.NOT_FOUND),
            path=resolved,
            suggested_path=candidate.resolve(),
            detail=f"Found a candidate at {candidate}",
        )

    if configured_failure is not None:
        return configured_failure

    state = (RequirementState.NOT_CONFIGURED
             if not str(configured or "").strip()
             else RequirementState.NOT_FOUND)
    return RequirementStatus(kind=kind, state=state, path=None,
                             detail=str(configured or ""))


def check_superflip(configured: object,
                    jana_dir: Optional[Path] = None) -> RequirementStatus:
    """Validate the configured Superflip, else look in the Jana2020 directory.

    Candidate priority follows Jana's supported scientific location,
    ``SUPERFLIP\\superflip.exe``.  The legacy original-name sibling remains
    detectable only as a remediation candidate for an old verified wrapper
    installation; it is never the normal default.

    The active Jana directory precedes managed tools, supported locations and
    PATH. Standalone callers omit jana_dir so managed tools take precedence.
    """
    candidates = [Path(jana_dir) / WRAPPER_EXE_NAME] if jana_dir is not None else []
    if candidates and is_phase_studio_wrapper(candidates[0]):
        candidates.append(Path(jana_dir) / ORIGINAL_EXE_NAME)
    candidates.extend(_standalone_candidates(RequirementKind.SUPERFLIP))
    return _check_executable(
        RequirementKind.SUPERFLIP,
        configured,
        candidates,
    )


def check_edma(configured: object,
               jana_dir: Optional[Path] = None) -> RequirementStatus:
    """Validate the configured EDMA, else look in the Jana2020 directory.

    Detection never modifies Jana2020's own EDMA; it only records where it is.
    """
    candidates = [Path(jana_dir) / EDMA_EXE_NAME] if jana_dir is not None else []
    return _check_executable(RequirementKind.EDMA, configured,
                             [*candidates, *_standalone_candidates(RequirementKind.EDMA)])


def _standalone_candidates(kind):
    from phase_studio.scientific_tools import managed_tools_directory
    name = WRAPPER_EXE_NAME if kind is RequirementKind.SUPERFLIP else EDMA_EXE_NAME
    managed = managed_tools_directory() / kind.value
    candidates = sorted(managed.rglob(name)) if managed.is_dir() else []
    # Known supported location follows the active Jana installation / managed tools.
    candidates.append(DEFAULT_JANA_SUPERFLIP_DIR / name)
    found = shutil.which(name)
    if found:
        candidates.append(Path(found))
    return candidates


def download_requirement_executable(
    kind: RequirementKind,
    destination_dir: Path,
    *,
    opener: Optional[Callable[..., BinaryIO]] = None,
) -> Path:
    """Install only a release-reviewed distribution with independent integrity.

    The caller owns the license-acknowledgement UI.  Archive paths are never
    extracted directly, which avoids path traversal and leaves Jana2020 files
    untouched.  The destination is a Phase Studio-owned user-data directory.
    """
    if kind is RequirementKind.SHARPED:
        raise ValueError("SharpED is an account requirement, not a local tool.")
    from phase_studio.scientific_tools import install_distribution
    return install_distribution(kind, destination_dir, opener=opener)


# ---------------------------------------------------------------------------
# SharpED
# ---------------------------------------------------------------------------

def check_sharped_api(base_url: str, token: str, *, timeout: float = 15.0,
                      client_factory: Optional[Callable[..., object]] = None) -> RequirementStatus:
    """Verify SharpED access as far as the existing API client allows.

    This uses the SAME client and configured server as the application and
    performs a real public model request. Nothing creates or consumes a job.

    What this proves, honestly:

      * a token is configured at all (answered without any request);
      * the configured server was reachable and spoke the expected protocol;
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

    from phase_studio.sharped_server_client import SharpEDServerClient

    if client_factory is None:
        client_factory = SharpEDServerClient

    try:
        client = client_factory(base_url=base_url, timeout=timeout)
        models = client.get_models()
    except Exception as exc:  # noqa: BLE001 - classified below
        return _classify_sharped_error(exc)

    if models is None or not hasattr(models, "models"):
        return RequirementStatus(kind=RequirementKind.SHARPED,
                                 state=RequirementState.MALFORMED_RESPONSE)
    return RequirementStatus(
        kind=RequirementKind.SHARPED,
        state=RequirementState.OK,
        sharped_default_model=str(getattr(models, "default_model", "") or "").strip(),
        sharped_models=tuple(str(item) for item in (getattr(models, "models", None) or []) if isinstance(item, str)),
    )


def _classify_sharped_error(exc: BaseException) -> RequirementStatus:
    """Map a client exception onto the reason the user actually needs.

    Deliberately never echoes the exception text into `detail`: a failing
    request can carry the URL, and the URL can carry a token.
    """
    status_code = getattr(exc, "code", None) or getattr(exc, "status", None)
    text = f"{type(exc).__name__}: {exc}".lower()

    if status_code == 403 or "http error 403" in text or "forbidden" in text:
        state = RequirementState.ACCESS_DENIED
    elif status_code == 401 or "http error 401" in text or "unauthor" in text:
        state = RequirementState.TOKEN_REJECTED
    elif (isinstance(status_code, int) and 500 <= status_code < 600) or any(
        f"http error {code}" in text for code in range(500, 600)
    ):
        state = RequirementState.SERVER_UNAVAILABLE
    elif isinstance(exc, (TimeoutError, ConnectionError)) or any(
        marker in text
        for marker in ("urlerror", "timed out", "timeout", "connection",
                       "getaddrinfo", "name or service", "unreachable", "ssl")
    ):
        state = RequirementState.SERVER_UNREACHABLE
    elif "json" in text or "decode" in text or "expecting value" in text:
        state = RequirementState.MALFORMED_RESPONSE
    else:
        # Only explicit HTTP authentication evidence may reject a token.
        # Public catalog/protocol failures do not establish token validity.
        state = RequirementState.MALFORMED_RESPONSE
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
    jana_dir: Optional[Path] = None,
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
