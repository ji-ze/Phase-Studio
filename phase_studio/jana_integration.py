"""Phase Studio -> Jana2020 SUPERFLIP integration.

Detects, installs, updates, repairs and removes the Phase Studio Superflip
launcher (superflip.exe, a frozen build of jana_superflip.py) inside an
existing Jana2020\\SUPERFLIP installation, while preserving the user's real
Superflip executable as superflip_original.exe.

This module is pure file-system management. It never runs Superflip, EDMA,
or any crystallographic calculation, and it never touches EDMA.exe. It is
deliberately Qt-free so the transactional logic can be unit tested without a
GUI; phase_studio/app.py provides the dialog that drives it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

try:
    from phase_studio.version import VERSION as PHASE_STUDIO_VERSION
except ImportError:  # pragma: no cover - direct-script execution fallback
    from version import VERSION as PHASE_STUDIO_VERSION

MARKER_FILENAME = "phase_studio_integration.json"
WRAPPER_EXE_NAME = "superflip.exe"
ORIGINAL_EXE_NAME = "superflip_original.exe"
EDMA_EXE_NAME = "EDMA.exe"
RUNTIME_DIR_NAME = "_internal"
STAGING_DIR_NAME = ".phase_studio_install_tmp"
BACKUP_EXE_SUFFIX = ".phase_studio_prev"
BACKUP_RUNTIME_SUFFIX = ".phase_studio_prev"


class IntegrationState:
    """String constants rather than an enum: written verbatim into log text
    and comparisons throughout the GUI, so plain strings keep call sites
    simple. Matches spec PART B section 17."""

    NOT_INSTALLED = "not_installed"
    INSTALLED_CURRENT = "installed_current"
    UPDATE_AVAILABLE = "update_available"
    REPAIR_REQUIRED = "repair_required"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class IntegrationMarker:
    """phase_studio_integration.json contents. No secrets; payload_hash is a
    plain SHA-256 of the installed wrapper executable, used only for repair
    detection (section 16)."""

    product: str
    version: str
    wrapper: str
    original_superflip: str
    payload_hash: str = ""

    def to_json(self) -> dict:
        return {
            "product": self.product,
            "version": self.version,
            "wrapper": self.wrapper,
            "original_superflip": self.original_superflip,
            "payload_hash": self.payload_hash,
        }

    @staticmethod
    def from_json(data: dict) -> "IntegrationMarker":
        return IntegrationMarker(
            product=str(data.get("product", "")),
            version=str(data.get("version", "")),
            wrapper=str(data.get("wrapper", WRAPPER_EXE_NAME)),
            original_superflip=str(data.get("original_superflip", ORIGINAL_EXE_NAME)),
            payload_hash=str(data.get("payload_hash", "")),
        )


@dataclass(frozen=True)
class JanaDirectoryReport:
    """Read-only inspection of a candidate Jana2020\\SUPERFLIP directory.
    Never modifies anything; classify_install_state() and the install/remove
    functions decide what, if anything, is safe to do based on this."""

    directory: Path
    exists: bool
    is_writable: bool
    has_superflip_exe: bool
    has_original_exe: bool
    has_edma_exe: bool
    has_runtime_dir: bool
    has_marker: bool
    marker: Optional[IntegrationMarker]
    marker_error: str = ""


@dataclass
class OperationResult:
    """Outcome of install_or_update_integration() / remove_integration()."""

    success: bool
    state: str
    message: str
    log: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Detection (section 7-9, 17)
# ---------------------------------------------------------------------------

def default_jana_root_candidates() -> List[Path]:
    """Well-known install location only -- never a recursive disk search
    (section 7)."""
    return [Path(r"C:\Jana2020")]


def superflip_dir_for_root(jana_root: Path) -> Path:
    return Path(jana_root) / "SUPERFLIP"


def detect_jana_root(configured_paths: Sequence[Optional[Path]] = ()) -> Optional[Path]:
    """Best-effort, non-recursive detection: the well-known C:\\Jana2020
    default first, then any currently configured Superflip/EDMA executable
    path that already lives inside a ...\\SUPERFLIP directory."""
    for candidate in default_jana_root_candidates():
        if superflip_dir_for_root(candidate).is_dir():
            return candidate
    for configured in configured_paths:
        if configured is None:
            continue
        try:
            path = Path(configured).expanduser()
        except Exception:
            continue
        if path.parent.name.upper() == "SUPERFLIP" and path.parent.is_dir():
            return path.parent.parent
    return None


def check_writable(directory: Path) -> bool:
    """Lightweight writability probe (create + delete a throwaway file).
    Never infer permission from ownership/ACL metadata alone (section 32)."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".phase_studio_write_check_{os.getpid()}.tmp"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def read_marker(directory: Path) -> tuple:
    marker_path = directory / MARKER_FILENAME
    if not marker_path.is_file():
        return None, ""
    try:
        data = json.loads(marker_path.read_text(encoding="utf-8"))
        return IntegrationMarker.from_json(data), ""
    except Exception as exc:
        return None, f"Integration marker could not be read: {exc}"


def inspect_jana_superflip_dir(directory: Path) -> JanaDirectoryReport:
    directory = Path(directory)
    if not directory.is_dir():
        return JanaDirectoryReport(
            directory=directory, exists=False, is_writable=False,
            has_superflip_exe=False, has_original_exe=False, has_edma_exe=False,
            has_runtime_dir=False, has_marker=False, marker=None,
        )
    marker, marker_error = read_marker(directory)
    return JanaDirectoryReport(
        directory=directory,
        exists=True,
        is_writable=check_writable(directory),
        has_superflip_exe=(directory / WRAPPER_EXE_NAME).is_file(),
        has_original_exe=(directory / ORIGINAL_EXE_NAME).is_file(),
        has_edma_exe=(directory / EDMA_EXE_NAME).is_file(),
        has_runtime_dir=(directory / RUNTIME_DIR_NAME).is_dir(),
        has_marker=marker is not None,
        marker=marker,
        marker_error=marker_error,
    )


def classify_install_state(report: JanaDirectoryReport, bundled_version: str = PHASE_STUDIO_VERSION) -> str:
    """Sections 19-23, 75: never guess. A verified Phase Studio marker is
    the ONLY basis for treating an installation as Phase-Studio-owned; an
    unmarked superflip_original.exe is always a conflict, never assumed to
    be a stale/manual Phase Studio artifact. Likewise, an unmarked
    RUNTIME_DIR_NAME (e.g. _internal) is always a conflict too -- ownership
    of that directory cannot be verified either, and silently merging the
    install into it would be exactly the collision this guards against
    (some other, unrelated frozen application happening to place its own
    _internal next to Jana2020's Superflip)."""
    if not report.exists:
        return IntegrationState.NOT_INSTALLED
    if report.has_marker and report.marker is not None:
        if not report.has_superflip_exe or not report.has_original_exe or not report.has_runtime_dir:
            return IntegrationState.REPAIR_REQUIRED
        if report.marker.version != bundled_version:
            return IntegrationState.UPDATE_AVAILABLE
        return IntegrationState.INSTALLED_CURRENT
    if report.has_runtime_dir:
        return IntegrationState.CONFLICT
    if not report.has_original_exe:
        # Clean Jana2020 SUPERFLIP directory (with or without its own
        # superflip.exe, and confirmed above to have no runtime directory
        # either) -- nothing has ever been renamed or installed here.
        return IntegrationState.NOT_INSTALLED
    # superflip_original.exe exists but no marker: ownership cannot be
    # verified. This also covers a directory Phase Studio itself renamed but
    # then lost its marker in (e.g. manual deletion) -- still a conflict,
    # not assumed safe.
    return IntegrationState.CONFLICT


# ---------------------------------------------------------------------------
# Bundled payload resolution (section 12-14, 59)
# ---------------------------------------------------------------------------

def bundled_integration_version() -> str:
    return PHASE_STUDIO_VERSION


def resolve_bundled_jana_payload_dir() -> Optional[Path]:
    """Locate the pre-built JanaIntegration payload (superflip.exe + its
    runtime directory) bundled alongside the running Phase Studio
    application. Covers every supported layout -- normal Python development,
    PyInstaller ONEDIR, and an MSIX-packaged ONEDIR -- without ever
    hard-coding a development-machine or WindowsApps path (sections 14, 59).
    Returns None if no payload is available (e.g. running from source with
    no local JanaIntegration build)."""
    candidates: List[Path] = []
    if getattr(sys, "frozen", False):
        # PyInstaller ONEDIR: sys.executable is .../PhaseStudio/PhaseStudio.exe.
        # The payload is a sibling application resource (see packaging's MSIX
        # layout), never inside PhaseStudio's own _internal.
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "JanaIntegration")
        candidates.append(exe_dir.parent / "JanaIntegration")
    # Development: a locally built payload from packaging/build_windows.ps1,
    # which builds the Jana wrapper via the known-working
    # "python -m PyInstaller --clean --noconfirm superflip.spec" against the
    # repository's root-level superflip.spec -- its real output directory is
    # dist/superflip (COLLECT(..., name="superflip") in that spec), not
    # dist/JanaIntegration. "JanaIntegration" is only the staging name used
    # once the payload is copied into an MSIX layout (build_store_msix.ps1).
    module_dir = Path(__file__).resolve().parent.parent
    candidates.append(module_dir / "dist" / "superflip")
    candidates.append(module_dir / "build" / "store" / "layout" / "JanaIntegration")
    for candidate in candidates:
        if (candidate / WRAPPER_EXE_NAME).is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Install / update / repair (sections 19-28, 33)
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_or_update_integration(
    jana_superflip_dir: Path,
    payload_dir: Path,
    *,
    bundled_version: str = PHASE_STUDIO_VERSION,
    log: Optional[Callable[[str], None]] = None,
) -> OperationResult:
    """Transactional install/update/repair of the Phase Studio Superflip
    wrapper into jana_superflip_dir, from a pre-built payload_dir (a
    PyInstaller ONEDIR JanaIntegration build: <payload_dir>/superflip.exe +
    <payload_dir>/_internal/...).

    Stages the payload into a temporary directory first and verifies it,
    then performs the minimal live-directory swap, keeping whatever was
    previously live as a recoverable backup until the swap fully succeeds.
    On any failure the directory is left either in its untouched original
    state (first install) or its previous working Phase Studio state
    (update/repair) -- never half-installed. EDMA.exe is never touched."""
    lines: List[str] = []

    def emit(message: str) -> None:
        lines.append(message)
        if log is not None:
            log(message)

    directory = Path(jana_superflip_dir)
    payload_dir = Path(payload_dir)
    payload_exe = payload_dir / WRAPPER_EXE_NAME
    payload_runtime = payload_dir / RUNTIME_DIR_NAME

    if not payload_exe.is_file():
        return OperationResult(False, "error", f"Integration payload is missing {WRAPPER_EXE_NAME}: {payload_exe}", lines)
    if not directory.is_dir():
        return OperationResult(False, "error", f"Jana2020 SUPERFLIP directory does not exist: {directory}", lines)
    if not check_writable(directory):
        return OperationResult(
            False, "permission_denied",
            f"Phase Studio cannot modify this Jana2020 installation with the current Windows permissions: {directory}",
            lines,
        )

    report = inspect_jana_superflip_dir(directory)
    state = classify_install_state(report, bundled_version)
    if state == IntegrationState.CONFLICT:
        if report.has_original_exe:
            conflict_detail = "Existing Superflip backup detected"
        else:
            conflict_detail = f"An existing {RUNTIME_DIR_NAME} folder was found"
        return OperationResult(
            False, state,
            f"{conflict_detail}. Phase Studio did not modify this installation because its "
            "ownership could not be verified.",
            lines,
        )

    is_first_install = state == IntegrationState.NOT_INSTALLED
    original_exe = directory / ORIGINAL_EXE_NAME
    live_exe = directory / WRAPPER_EXE_NAME
    live_runtime = directory / RUNTIME_DIR_NAME
    marker_path = directory / MARKER_FILENAME

    if not is_first_install and not original_exe.is_file():
        return OperationResult(
            False, "error",
            f"{ORIGINAL_EXE_NAME} is missing; cannot safely update an existing Phase Studio integration without it.",
            lines,
        )

    # ----- Stage (section 24) -----
    staging_dir = directory / STAGING_DIR_NAME
    shutil.rmtree(staging_dir, ignore_errors=True)
    try:
        staging_dir.mkdir(parents=True)
        shutil.copy2(payload_exe, staging_dir / WRAPPER_EXE_NAME)
        if payload_runtime.is_dir():
            shutil.copytree(payload_runtime, staging_dir / RUNTIME_DIR_NAME)
        if not (staging_dir / WRAPPER_EXE_NAME).is_file():
            raise RuntimeError("Staged wrapper executable is missing after copy.")
        if payload_runtime.is_dir() and not (staging_dir / RUNTIME_DIR_NAME).is_dir():
            raise RuntimeError("Staged runtime directory is missing after copy.")
    except Exception as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        return OperationResult(False, "error", f"Failed to stage the integration payload: {exc}", lines)
    emit(f"Staged integration payload in {staging_dir}")

    # ----- Recoverable backup of whatever is currently live -----
    backup_exe = directory / f"{WRAPPER_EXE_NAME}{BACKUP_EXE_SUFFIX}"
    backup_runtime = directory / f"{RUNTIME_DIR_NAME}{BACKUP_RUNTIME_SUFFIX}"
    shutil.rmtree(backup_runtime, ignore_errors=True)
    if backup_exe.exists():
        backup_exe.unlink()

    def rollback(reason: str) -> OperationResult:
        emit(f"Installation failed: {reason}")
        try:
            if is_first_install:
                # Nothing was moved aside except the original itself.
                if original_exe.is_file() and not live_exe.exists():
                    shutil.move(str(original_exe), str(live_exe))
                    emit(f"Rolled back: restored the original Superflip to {live_exe}")
            else:
                if live_exe.exists():
                    live_exe.unlink()
                if backup_exe.is_file():
                    shutil.move(str(backup_exe), str(live_exe))
                if live_runtime.exists():
                    shutil.rmtree(live_runtime, ignore_errors=True)
                if backup_runtime.is_dir():
                    shutil.move(str(backup_runtime), str(live_runtime))
                emit("Rolled back to the previous Phase Studio integration.")
        except Exception as rollback_exc:
            shutil.rmtree(staging_dir, ignore_errors=True)
            return OperationResult(
                False, "rollback_failed",
                f"Installation failed and automatic rollback also failed: {rollback_exc}. "
                "Jana2020 may be left without a working Superflip -- manual recovery required.",
                lines,
            )
        shutil.rmtree(staging_dir, ignore_errors=True)
        shutil.rmtree(backup_runtime, ignore_errors=True)
        if backup_exe.exists():
            try:
                backup_exe.unlink()
            except Exception:
                pass
        return OperationResult(False, "error", f"Installation failed and was rolled back: {reason}", lines)

    try:
        if is_first_install:
            # ----- Original Superflip is sacred (section 21) -----
            if not live_exe.is_file():
                return rollback(f"Expected an existing Superflip executable to preserve: {live_exe}")
            if original_exe.exists():
                return rollback(f"{ORIGINAL_EXE_NAME} unexpectedly already exists; aborting to avoid overwriting it.")
            shutil.move(str(live_exe), str(original_exe))
            if not original_exe.is_file():
                return rollback("Original Superflip executable was not found at its preserved location after rename.")
            emit(f"Preserved the original Superflip executable as {original_exe}")
        else:
            # Move the current Phase-Studio-owned files aside as a
            # recoverable backup instead of deleting them outright.
            if live_exe.exists():
                shutil.move(str(live_exe), str(backup_exe))
            if live_runtime.exists():
                shutil.move(str(live_runtime), str(backup_runtime))

        shutil.move(str(staging_dir / WRAPPER_EXE_NAME), str(live_exe))
        if (staging_dir / RUNTIME_DIR_NAME).is_dir():
            shutil.move(str(staging_dir / RUNTIME_DIR_NAME), str(live_runtime))
        if not live_exe.is_file():
            return rollback("Phase Studio wrapper executable is missing after install.")

        marker = IntegrationMarker(
            product="Phase Studio",
            version=bundled_version,
            wrapper=WRAPPER_EXE_NAME,
            original_superflip=ORIGINAL_EXE_NAME,
            payload_hash=_sha256_file(live_exe),
        )
        marker_path.write_text(json.dumps(marker.to_json(), indent=2), encoding="utf-8")
        emit(f"Installed Phase Studio launcher as {live_exe}")
        emit(f"Wrote integration marker {marker_path}")
    except Exception as exc:
        return rollback(str(exc))

    # ----- Success: drop the now-unneeded backups/staging -----
    shutil.rmtree(staging_dir, ignore_errors=True)
    shutil.rmtree(backup_runtime, ignore_errors=True)
    if backup_exe.exists():
        try:
            backup_exe.unlink()
        except Exception:
            pass
    return OperationResult(True, IntegrationState.INSTALLED_CURRENT, "Jana2020 integration installed successfully.", lines)


# ---------------------------------------------------------------------------
# Remove (sections 29-31)
# ---------------------------------------------------------------------------

def remove_integration(jana_superflip_dir: Path, *, log: Optional[Callable[[str], None]] = None) -> OperationResult:
    lines: List[str] = []

    def emit(message: str) -> None:
        lines.append(message)
        if log is not None:
            log(message)

    directory = Path(jana_superflip_dir)
    if not directory.is_dir():
        return OperationResult(False, "error", f"Jana2020 SUPERFLIP directory does not exist: {directory}", lines)
    if not check_writable(directory):
        return OperationResult(
            False, "permission_denied",
            f"Phase Studio cannot modify this Jana2020 installation with the current Windows permissions: {directory}",
            lines,
        )
    report = inspect_jana_superflip_dir(directory)
    if not report.has_marker or report.marker is None:
        return OperationResult(False, "error", "No verified Phase Studio integration was found here; nothing to remove.", lines)

    original_exe = directory / ORIGINAL_EXE_NAME
    live_exe = directory / WRAPPER_EXE_NAME
    live_runtime = directory / RUNTIME_DIR_NAME
    marker_path = directory / MARKER_FILENAME

    # ----- Verify the backup before touching the active wrapper (section 31) -----
    if not original_exe.is_file():
        return OperationResult(
            False, "error",
            f"{ORIGINAL_EXE_NAME} is missing; refusing to remove the Phase Studio wrapper, which would leave "
            "Jana2020 without a working Superflip. The current installation was left unchanged.",
            lines,
        )
    if original_exe.stat().st_size <= 0:
        return OperationResult(
            False, "error",
            f"{ORIGINAL_EXE_NAME} appears empty or invalid; refusing to remove the active wrapper. "
            "The current installation was left unchanged.",
            lines,
        )

    try:
        if live_runtime.exists():
            shutil.rmtree(live_runtime)
        if live_exe.exists():
            live_exe.unlink()
        shutil.move(str(original_exe), str(live_exe))
        if not live_exe.is_file():
            raise RuntimeError("Superflip executable is missing after restore.")
        if marker_path.exists():
            marker_path.unlink()
        emit(f"Restored the original Superflip executable to {live_exe}")
    except Exception as exc:
        return OperationResult(False, "error", f"Failed to remove the Phase Studio integration: {exc}", lines)

    return OperationResult(True, IntegrationState.NOT_INSTALLED, "Jana2020 integration removed; the original Superflip executable was restored.", lines)


# ---------------------------------------------------------------------------
# Post-install verification (sections 35-37) -- filesystem/marker checks
# only, never a real Superflip/EDMA invocation.
# ---------------------------------------------------------------------------

def authenticode_signature_status(exe_path: Path, *, timeout: float = 5.0) -> str:
    """Best-effort Authenticode status for a Windows executable: "signed",
    "unsigned", or "unknown" (non-Windows, powershell unavailable, or the
    file does not exist). Never raises. Section 57: shown in the
    integration dialog for diagnosis only -- installation is never blocked
    on this by Phase Studio itself."""
    exe_path = Path(exe_path)
    if sys.platform != "win32" or not exe_path.is_file():
        return "unknown"
    try:
        import subprocess

        ps = (
            "$sig = Get-AuthenticodeSignature -LiteralPath $args[0]; "
            "if ($sig.Status -eq 'Valid') { 'Signed' } else { 'Unsigned' }"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps, str(exe_path)],
            capture_output=True, text=True, timeout=timeout,
        )
        output = (proc.stdout or "").strip()
        if "Signed" in output and "Unsigned" not in output:
            return "signed"
        if "Unsigned" in output:
            return "unsigned"
    except Exception:
        pass
    return "unknown"


def verify_installed(directory: Path, *, edma_hash_before: Optional[str] = None) -> List[str]:
    """Returns a list of human-readable problems found (empty list = fully
    verified). Filesystem/marker checks only -- never starts Superflip or
    EDMA (section 36)."""
    problems: List[str] = []
    report = inspect_jana_superflip_dir(directory)
    if not report.has_superflip_exe:
        problems.append(f"{WRAPPER_EXE_NAME} is missing.")
    if not report.has_original_exe:
        problems.append(f"{ORIGINAL_EXE_NAME} is missing.")
    if not report.has_runtime_dir:
        problems.append(f"{RUNTIME_DIR_NAME} runtime directory is missing.")
    if not report.has_marker:
        problems.append(f"{MARKER_FILENAME} is missing.")
    if edma_hash_before is not None and report.has_edma_exe:
        edma_path = Path(directory) / EDMA_EXE_NAME
        try:
            if _sha256_file(edma_path) != edma_hash_before:
                problems.append(f"{EDMA_EXE_NAME} changed unexpectedly during installation.")
        except Exception:
            pass
    return problems
