#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jana2020-compatible Superflip launcher.

This module is intended to be frozen as the Superflip-for-Jana launcher.  The
scientific executable is resolved from the active Jana installation as
``SUPERFLIP\\superflip.exe``.  ``superflip_original.exe`` is retained only for
the verified legacy layout that replaced that file with a wrapper.
"""

from __future__ import annotations

import os
import json
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime
from dataclasses import dataclass, field
from phase_studio.credentials import credential_store
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple
from phase_studio.jana_density import origin_preserving_conversion_lines

try:
    from phase_studio.edma_defaults import NORMAL_EDMA_THRESHOLD_SIGMA
except Exception:
    from edma_defaults import NORMAL_EDMA_THRESHOLD_SIGMA

try:
    from phase_studio.version import VERSION as __version__
except Exception:
    from version import VERSION as __version__

try:
    from phase_studio.error_reporting import build_error_report, sanitize_error_details, show_phase_studio_error
except Exception:
    from error_reporting import build_error_report, sanitize_error_details, show_phase_studio_error

try:
    from phase_studio.sharped_server_client import SharpEDServerClient, DEFAULT_SERVER_URL, reconcile_model_selection
except Exception:
    from sharped_server_client import SharpEDServerClient, DEFAULT_SERVER_URL, reconcile_model_selection

try:
    from phase_studio.sharped_tiling import decide_sharped_submission, run_tiled_sharped_inference
except Exception:
    from sharped_tiling import decide_sharped_submission, run_tiled_sharped_inference  # type: ignore[no-redef]

# This lightweight wrapper has no user-facing "max upload size" setting
# (unlike the full GUI's sharped_max_upload_mb); 100 MB matches that
# setting's own default and the current public SharpED server's known
# limit, so an oversized map is still tiled rather than failing outright.
DEFAULT_SHARPED_MAX_UPLOAD_MB = 100.0
SHARPED_ONE_CYCLE_MODEL = "PEAK A (model prediction)"
SHARPED_ITERATIVE_MODEL = "SEED (cyclic CF)"


def sharped_model_for_cycles(cycles: int) -> str:
    """Return Phase Studio's exact, server-independent workflow policy."""
    return SHARPED_ONE_CYCLE_MODEL if int(cycles) == 1 else SHARPED_ITERATIVE_MODEL

try:
    from phase_studio.ui_style import apply_phase_studio_style
except Exception:
    from ui_style import apply_phase_studio_style

try:
    from phase_studio.process_utils import (
        allow_external_process_foreground,
        ensure_visible_console,
        no_console_popen_kwargs,
        text_encoding,
    )
except Exception:
    from process_utils import (
        allow_external_process_foreground,
        ensure_visible_console,
        no_console_popen_kwargs,
        text_encoding,
    )

try:
    from phase_studio.inflip_io import (
        COMMENT_MARKERS,
        add_modelseed_modelfile,
        apply_reference_override,
        define_m80_inflip,
        ensure_xplor_output,
        first_token,
        inflip_header_for_m80,
        split_inflip_line,
    )
except Exception:
    from inflip_io import (  # type: ignore[no-redef]
        COMMENT_MARKERS,
        add_modelseed_modelfile,
        apply_reference_override,
        define_m80_inflip,
        ensure_xplor_output,
        first_token,
        inflip_header_for_m80,
        split_inflip_line,
    )

INFLIP_SUFFIXES = {".inflip", ".inp"}
DEFAULT_JANA_SUPERFLIP = Path(r"C:\Jana2020\SUPERFLIP\superflip.exe")
DEFAULT_JANA_EDMA = Path(r"C:\Jana2020\SUPERFLIP\EDMA.exe")

INPUT_MODE_INFLIP = "Jana2020 .inflip"
INPUT_MODE_INFLIP_OVERRIDES = "Jana2020 .inflip with external HKL/CIF overrides"
INPUT_MODE_EXTERNAL = "External HKL + reference CIF"
INPUT_MODE_LABELS = [
    INPUT_MODE_INFLIP,
    INPUT_MODE_INFLIP_OVERRIDES,
    INPUT_MODE_EXTERNAL,
]


def normalize_dialog_input_mode(value: str) -> str:
    text = str(value or "").strip().lower()
    if "override" in text or "nahra" in text or "replace" in text:
        return INPUT_MODE_INFLIP_OVERRIDES
    if "external" in text and "hkl" in text and "cif" in text:
        return INPUT_MODE_EXTERNAL
    return INPUT_MODE_INFLIP


@dataclass
class JanaRunOptions:
    action: str
    cycles: int = 1
    use_deblurred_map: bool = True
    next_cycle_modelfile: str = "deblurred_xplor"
    api_token: str = field(default="", repr=False)
    server_url: str = DEFAULT_SERVER_URL
    model: str = "default"
    elements: str = "C N O"
    outres: float = 0.2
    input_mode: str = INPUT_MODE_INFLIP
    hkl_override: str = ""
    reference_override: str = ""
    superflip_referencefile: str = ""
    first_cycle_modelfile: str = ""
    # Phase-recycling-only cross-validation controls (Wizard section "Cross-
    # validation"); both default off and are never shown/settable for either
    # single-pass workflow. Map 1:1 onto the existing full-pipeline
    # compute_omit_maps / compute_omit_rfree settings -- no new calculation.
    compute_omit_maps: bool = False
    compute_omit_rfree: bool = False
    # Phase-recycling-only Map feedback page (Wizard PAGE 3); never shown or
    # settable for either single-pass workflow, so these all stay at their
    # off/default values for those. Map 1:1 onto the existing full-pipeline
    # map_feedback_missing_*/map_feedback_intensity_*/redistribute_overlaps
    # (powder_*) RunConfig fields -- no new map-feedback calculation, just
    # another way to populate the same existing settings.
    enable_missing_completion: bool = False
    missing_start_cycle: int = 1
    missing_max_added_percent: float = 0.0
    enable_intensity_correction: bool = False
    intensity_start_cycle: int = 1
    intensity_damping: float = 0.0
    intensity_sigma_threshold: float = 0.0
    enable_powder_repartition: bool = False
    powder_start_cycle: int = 1
    powder_wavelength: float = 0.0
    powder_separation_factor: float = 0.2
    powder_map_ratio_mix: float = 1.0
    # 2.0.0 Autosolve: "A" (solve the phase problem) or "B" (predict the
    # structure model); empty for every other action.
    autosolve_option: str = ""


@dataclass
class JanaHandoffImport:
    values: dict[str, str]
    inflip_keys: list[str]
    handoff_keys: list[str]
    limitations: list[str]
    input_mode: str
    reflection_source: str
    reference_source: str


def _resolved_handoff_path(value: str, base_dir: Path) -> str:
    text = str(value or "").strip().strip('"')
    if not text:
        return ""
    path = Path(text).expanduser()
    return str((path if path.is_absolute() else base_dir / path).resolve())


def build_jana_handoff_import(
    inflip_path: Path,
    options: JanaRunOptions,
    parsed_settings: dict[str, str],
) -> JanaHandoffImport:
    """Compose one-shot GUI values with explicit hand-off precedence.

    Values explicitly returned by the Jana launcher override mapped .inflip
    keywords. Saved Phase Studio values already exist in the constructed window
    and therefore remain the fallback for keys absent from both sources.
    """
    inflip_path = Path(inflip_path).expanduser().resolve()
    base_dir = inflip_path.parent
    path_keys = {"reference_cif", "superflip_referencefile", "first_cycle_modelfile"}
    inflip_values: dict[str, str] = {}
    for key, value in parsed_settings.items():
        mapped_value = _resolved_handoff_path(value, base_dir) if key in path_keys else str(value)
        inflip_values[key] = mapped_value

    input_mode = normalize_dialog_input_mode(options.input_mode)
    # These values are applied onto the main window's own "input_source_mode"
    # combo by display text (see _set_widget_value_from_string), so they must
    # stay identical to app.py's INPUT_MODE_LABELS -- not a second, independently
    # worded copy of the same three labels.
    app_input_label = {
        INPUT_MODE_INFLIP: "Jana2020 .inflip",
        INPUT_MODE_INFLIP_OVERRIDES: "Jana2020 .inflip with external HKL/reference overrides",
        INPUT_MODE_EXTERNAL: "External HKL + CIF reference",
    }[input_mode]
    allow_external_sources = input_mode in {INPUT_MODE_INFLIP_OVERRIDES, INPUT_MODE_EXTERNAL}
    explicit_hkl = _resolved_handoff_path(options.hkl_override, base_dir) if allow_external_sources else ""
    explicit_reference = _resolved_handoff_path(options.reference_override, base_dir) if allow_external_sources else ""
    explicit_superflip_reference = _resolved_handoff_path(options.superflip_referencefile, base_dir)
    explicit_first_model = _resolved_handoff_path(options.first_cycle_modelfile, base_dir)

    # The Wizard's Phase-recycling "map used for Jana2020 hand-off" radio
    # (superflip_xplor / deblurred_xplor) only ever decides which map the
    # user is offered to review/select at the end -- see wizard_map_source
    # in launch_phase_studio_from_jana(), which reads options.next_cycle_modelfile
    # directly and is unaffected by this. It must never silently stop
    # SharpED from running each cycle: only "none" (the "Superflip only"
    # single-pass workflow) is genuinely SharpED-free. Both map preferences
    # keep SharpED running every cycle and keep feeding its deblurred map
    # forward, exactly like the "SharpED map" preference already did.
    handoff_run_sharped = options.next_cycle_modelfile != "none"
    handoff_modelfile_source = "none" if options.next_cycle_modelfile == "none" else "deblurred_xplor"

    integration_dir = application_dir()
    integration_superflip = resolve_active_jana_superflip(integration_dir)
    jana_root = resolve_jana_installation_root(integration_dir)
    integration_edma = jana_root / "SUPERFLIP" / "EDMA.exe"
    handoff_values = {
        "input_source_mode": app_input_label,
        "jana_inflip": str(inflip_path),
        "work_dir": str(base_dir / f"phase_studio_full_run_{inflip_path.stem}"),
        "superflip_exe": str(integration_superflip.resolve()),
        "edma_exe": str(integration_edma.resolve()),
        # Normal Jana workflows start from Phase Studio's own structure-
        # extraction policy. Incoming .inflip plimit and persisted GUI values
        # must not resurrect the former 0.30/0.50 defaults. Users can still
        # edit either control after the handoff is loaded.
        "plimit_superflip": str(NORMAL_EDMA_THRESHOLD_SIGMA),
        "plimit_deblur": str(NORMAL_EDMA_THRESHOLD_SIGMA),
        "cycles": str(options.cycles),
        "run_sharped": "true" if handoff_run_sharped else "false",
        "sharped_base_url": options.server_url,
        "sharped_api_token": options.api_token,
        "sharped_model": options.model,
        "sharped_elements": options.elements,
        "sharped_outres": str(options.outres),
        "modelfile_source": handoff_modelfile_source,
        # Must match one of the "Map format" combo items in app.py exactly (XPLOR is
        # always produced regardless; "jana" additionally saves Jana m80/m81 for hand-off).
        "map_export_format": "jana",
        "hkl": explicit_hkl,
        "compute_omit_maps": "true" if options.compute_omit_maps else "false",
        "compute_omit_rfree": "true" if (options.compute_omit_maps and options.compute_omit_rfree) else "false",
        # Wizard PAGE 3 (Map feedback, Phase-recycling only) -- these map 1:1
        # onto the existing Basic -> Map feedback RunConfig fields; see
        # JanaRunOptions for why they stay at their off/default values for
        # either single-pass workflow.
        "map_feedback_missing_enabled": "true" if options.enable_missing_completion else "false",
        "map_feedback_missing_from_cycle": str(options.missing_start_cycle),
        "map_feedback_missing_percent_limit": str(options.missing_max_added_percent),
        "map_feedback_intensity_enabled": "true" if options.enable_intensity_correction else "false",
        "map_feedback_intensity_from_cycle": str(options.intensity_start_cycle),
        "map_feedback_intensity_damping": str(options.intensity_damping),
        "map_feedback_intensity_max_i_over_sigma": str(options.intensity_sigma_threshold),
        "redistribute_overlaps": "true" if options.enable_powder_repartition else "false",
        "powder_redistribution_from_cycle": str(options.powder_start_cycle),
        "powder_wavelength": str(options.powder_wavelength),
        "powder_separation_factor": str(options.powder_separation_factor),
        "powder_redistribution_mix": str(options.powder_map_ratio_mix),
    }
    if explicit_first_model:
        handoff_values["first_cycle_modelfile"] = explicit_first_model

    limitations: list[str] = []
    if explicit_reference:
        handoff_values["reference_cif"] = explicit_reference
        handoff_values["referencefile_mode"] = "reference_density" if Path(explicit_reference).suffix.lower() in {".xplor", ".ccp4", ".map", ".m80", ".m81", ".jana"} else "reference_cif"
        reference_source = explicit_reference
        if explicit_superflip_reference and Path(explicit_superflip_reference) != Path(explicit_reference):
            limitations.append(
                "A separate Superflip referencefile was also supplied; the GUI has one External reference field, so the explicit crystallographic reference override is shown there."
            )
    elif explicit_superflip_reference:
        handoff_values["reference_cif"] = explicit_superflip_reference
        handoff_values["referencefile_mode"] = "reference_density" if Path(explicit_superflip_reference).suffix.lower() in {".xplor", ".ccp4", ".map", ".m80", ".m81", ".jana"} else "reference_cif"
        reference_source = explicit_superflip_reference
    elif inflip_values.get("reference_cif"):
        reference_source = inflip_values["reference_cif"]
    else:
        handoff_values["reference_cif"] = ""
        reference_source = "cell, space group and composition embedded in the .inflip"

    values = dict(inflip_values)
    values.update(handoff_values)
    # superflip_referencefile is an internal compatibility key, not a visible
    # main-window control. The visible reference_cif field above carries only a
    # verified semantically compatible source.
    values.pop("superflip_referencefile", None)
    reflection_source = explicit_hkl or "embedded fbegin/endf block from the .inflip"
    return JanaHandoffImport(
        values=values,
        inflip_keys=sorted(key for key in inflip_values if key not in {"superflip_referencefile"}),
        handoff_keys=sorted(handoff_values),
        limitations=limitations,
        input_mode=app_input_label,
        reflection_source=reflection_source,
        reference_source=reference_source,
    )


def jana_handoff_log_lines(handoff: JanaHandoffImport, inflip_path: Path, applied_keys: Sequence[str]) -> list[str]:
    """Return concise provenance only; sensitive hand-off values are excluded."""
    from phase_studio.app import format_reflection_data_mode

    applied = set(applied_keys)
    imported_inflip_keys = [key for key in handoff.inflip_keys if key in applied]
    lines = [
        "[Jana2020] Job received",
        f"  Input: {Path(inflip_path).name}",
        f"  Working directory: {handoff.values.get('work_dir', '')}",
        f"  Mode: {handoff.input_mode}",
        f"  Reflections: {handoff.reflection_source}",
        f"  Reference: {handoff.reference_source}",
        f"[Input] {len(imported_inflip_keys)} compatible .inflip settings imported",
    ]
    if "reflection_data_mode" in imported_inflip_keys:
        lines.append(f"  Format: {format_reflection_data_mode(handoff.values['reflection_data_mode'])}")
    lines.extend(f"  Note: {limitation}" for limitation in handoff.limitations)
    return lines


class JanaLogger:
    """Append-only, timestamped log anchored to one resolved project path."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = Path(log_path).expanduser().resolve()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.log_path.open("a", encoding="utf-8", errors="replace")
        self._lock = threading.Lock()
        started = datetime.now().astimezone()
        self._fh.write("\n" + "=" * 60 + "\n")
        self._fh.write(f"Phase Studio {__version__} session\n")
        self._fh.write(f"Started: {started.isoformat(timespec='seconds')}\n")
        self._fh.write("=" * 60 + "\n")
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass

    def __call__(self, message: str) -> None:
        text = sanitize_error_details(message)
        # The Jana project log is the authoritative, always-available copy of
        # this message; the console mirror is a bonus for a development
        # console window, not something later code depends on. This wrapper
        # builds windowed (console=False, see superflip.spec) precisely so no
        # black console window appears behind the Jana2020 Wizard -- stdout
        # may therefore be absent entirely, which must never take down logging.
        try:
            print(text, flush=True)
        except Exception:
            pass
        timestamp = datetime.now().astimezone().strftime("%H:%M:%S.%f")[:-3]
        with self._lock:
            self._fh.write(f"{timestamp} {text}\n")
            self._fh.flush()


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def safe_wrapper_log_dir() -> Path:
    """Writable fallback that is never derived from the wrapper executable."""
    return (Path(tempfile.gettempdir()) / "PhaseStudio").resolve()


def jana_project_log_path(
    project_dir: Optional[Path] = None, *, inflip_path: Optional[Path] = None,
) -> Path:
    """Return a path fixed from the incoming Jana project, or safe temp.

    CWD and the executable directory are deliberately not fallback authorities:
    Jana commonly launches the wrapper with its installation directory as CWD.
    """
    if inflip_path is not None:
        root = Path(inflip_path).expanduser().resolve().parent
    elif project_dir is not None:
        root = Path(project_dir).expanduser().resolve()
    else:
        root = safe_wrapper_log_dir()
    return root / "log.txt"


def create_jana_logger(inflip_path: Optional[Path]) -> JanaLogger:
    """Open the authoritative project log, with a safe early-failure fallback."""
    preferred = jana_project_log_path(inflip_path=inflip_path)
    try:
        return JanaLogger(preferred)
    except OSError:
        fallback = safe_wrapper_log_dir() / "log.txt"
        logger = JanaLogger(fallback)
        logger(
            f"WARNING: project log {preferred} could not be opened; "
            f"using writable fallback {fallback}."
        )
        return logger


def read_text_lines(path: Path) -> List[str]:
    data = path.read_bytes()
    for enc in (text_encoding(), "utf-8", "cp1250", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except Exception:
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def write_text_lines(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\r\n".join(lines).rstrip("\r\n") + "\r\n"
    path.write_bytes(text.encode(text_encoding(), errors="replace"))



def stage_external_file_for_superflip(source: Path, target_dir: Path, base_name: str, role: str) -> Path:
    """Copy an external file next to the generated .inflip under a very short safe name.

    Older Jana/Superflip builds are fragile with long/quoted file names in
    referencefile/modelfile keywords.  The full Phase Studio pipeline already
    uses short local file names in the cycle directory; the Jana launcher must
    do the same.  Therefore the staged name deliberately does not include the
    structure/base name.
    """
    src = Path(source).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"{role} file not found: {src}")
    suffix = src.suffix.lower() or ".dat"
    role_text = str(role or "file").lower()
    if "reference" in role_text:
        stem = "superflip_referencefile"
    elif "model" in role_text:
        stem = "superflip_modelfile"
    elif "hkl" in role_text or "reflection" in role_text:
        stem = "superflip_reflections"
    else:
        safe_role = re.sub(r"[^A-Za-z0-9_.-]+", "_", role_text).strip("._") or "file"
        stem = f"superflip_{safe_role}"
    dst = target_dir / f"{stem}{suffix}"
    try:
        same = src.resolve() == dst.resolve()
    except Exception:
        same = False
    if not same:
        shutil.copy2(src, dst)
    # Verify immediately; otherwise Superflip later reports only a vague
    # "Error opening cif file" and the real staging problem is hidden.
    if not dst.is_file() or dst.stat().st_size <= 0:
        raise RuntimeError(f"Staged {role} file is missing or empty: {dst}")
    return dst


def inflip_keyword_path(inflip_path: Path, keyword: str) -> Optional[Path]:
    """Resolve a file path declared by a single-value keyword in the incoming Jana .inflip."""
    key = keyword.strip().lower()
    for line in read_text_lines(inflip_path):
        parts = split_inflip_line(line)
        if parts and parts[0].lower() == key and len(parts) > 1:
            candidate = Path(parts[1].strip().strip('"'))
            if not candidate.is_absolute():
                candidate = inflip_path.parent / candidate
            return candidate.resolve()
    return None


def find_inflip_arg(args: Sequence[str], cwd: Path) -> Optional[Tuple[int, Path]]:
    for i, arg in enumerate(args):
        p = Path(str(arg).strip('"'))
        if p.suffix.lower() in INFLIP_SUFFIXES:
            return i, (p if p.is_absolute() else cwd / p)
    return None


def resolve_original_superflip(exe_dir: Path) -> Path:
    """Compatibility binary for the old in-place wrapper installation only."""
    candidates = [
        exe_dir / "superflip_original.exe",
        exe_dir / "SuperFlip-orig.exe",
        exe_dir / "superflip-original.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # Never use PATH here: with two Jana2020 installations it can silently
    # select a wrapper/helper belonging to a different integration root.
    return exe_dir / "superflip_original.exe"


def resolve_jana_installation_root(exe_dir: Path) -> Path:
    """Return the Jana root for either supported integration location.

    Current installations launch Phase Studio from ``<jana>\\SharpED`` while
    older in-place wrappers run from ``<jana>\\SUPERFLIP``. In both cases the
    scientific programs belong to the sibling ``SUPERFLIP`` directory.
    """
    integration_dir = Path(exe_dir).expanduser().resolve()
    if integration_dir.name.casefold() in {"sharped", "superflip"}:
        return integration_dir.parent
    for parent in integration_dir.parents:
        if parent.name.casefold() == "sharped":
            return parent.parent
    return integration_dir


def resolve_active_jana_superflip(exe_dir: Path) -> Path:
    """Resolve the scientific binary from the active Jana launcher root.

    Jana normally launches Phase Studio from its installation root, while the
    authoritative scientific executable remains in ``SUPERFLIP\\superflip.exe``.
    An older Phase Studio integration replaced that exact file with its wrapper;
    only a verified marker permits the narrowly-scoped original-name escape in
    that legacy layout, preventing recursion without making it a default.
    """
    integration_dir = Path(exe_dir).expanduser().resolve()
    jana_root = resolve_jana_installation_root(integration_dir)
    authoritative = jana_root / "SUPERFLIP" / "superflip.exe"
    if authoritative.is_file():
        try:
            from phase_studio.jana_integration import read_marker
            marker, marker_error = read_marker(authoritative.parent)
        except Exception:
            marker, marker_error = None, ""
        running_wrapper = (
            authoritative.parent == integration_dir
            and Path(sys.executable).resolve() == authoritative.resolve()
            if getattr(sys, "frozen", False) else False
        )
        if not running_wrapper:
            return authoritative
        if marker is not None and not marker_error:
            compatibility = resolve_original_superflip(integration_dir)
            if compatibility.is_file():
                return compatibility
    raise FileNotFoundError(
        "The active Jana2020 Superflip executable was not found or resolves to "
        f"the Phase Studio launcher itself: {authoritative}. Repair the Jana2020 integration."
    )


def log_wrapper_runtime_identity(log: Callable[[str], None]) -> None:
    """Record and validate the wrapper actually invoked by Jana2020."""
    exe_dir = application_dir()
    wrapper_path = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else Path(__file__).resolve()
    log(f"Phase Studio version: {__version__}")
    log(f"Jana wrapper path: {wrapper_path}")
    jana_root = resolve_jana_installation_root(exe_dir)
    log(f"Jana installation root: {jana_root}")
    log(f"Phase Studio integration root: {exe_dir}")
    try:
        log(f"Superflip executable: {resolve_active_jana_superflip(exe_dir).resolve()}")
    except Exception as exc:
        log(f"Superflip executable: unavailable ({exc})")
    try:
        from phase_studio.jana_integration import read_marker
        marker, marker_error = read_marker(exe_dir)
    except Exception as exc:
        marker, marker_error = None, str(exc)
    if marker_error:
        log(f"Jana integration marker could not be read: {marker_error}")
        return
    if marker is None:
        log("Jana integration marker: not present (development/manual installation)")
        return
    log(f"Jana integration payload version: {marker.version}")
    if marker.version != __version__:
        raise RuntimeError(
            "The installed Phase Studio Jana2020 integration does not match this "
            "Phase Studio version. Repair the Jana2020 integration before continuing."
        )


def run_process(cmd: Sequence[str], cwd: Path, log: Callable[[str], None]) -> int:
    """Run one external command for a wrapper-only Jana2020 workflow.

    These workflows (Superflip only, Superflip + SharpED) never open the Phase
    Studio main window, so this console IS the user's live execution feedback.

    Exactly one visible console is involved and it belongs to the wrapper: the
    child is started hidden and its output is teed straight back out to the
    wrapper's console as it arrives, as well as into log.txt through the
    existing logger. Previously the only window on screen was the child's own,
    created by Windows because the windowed wrapper has no console to share --
    and it was empty, because the child's stdout/stderr were redirected into a
    pipe for logging and so never reached it.

    GFORTRAN_UNBUFFERED_ALL is set for the child because Superflip is a
    gfortran program, whose runtime block-buffers stdout when it is a pipe
    rather than a terminal; without it a whole run would appear at once at the
    end. It affects I/O buffering only, never any computed value.
    """
    log("Running: " + " ".join(str(part) for part in cmd))
    ensure_visible_console("Phase Studio - Superflip")
    child_env = dict(os.environ)
    child_env.setdefault("GFORTRAN_UNBUFFERED_ALL", "y")
    proc = subprocess.Popen(
        [str(part) for part in cmd],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding=text_encoding(),
        errors="replace",
        env=child_env,
        **no_console_popen_kwargs(),
    )
    allow_external_process_foreground(proc.pid)
    assert proc.stdout is not None
    # readline() rather than iterating the file object: it hands back each line
    # as soon as the child emits it, so the console fills in progressively
    # instead of only at the end. stderr is folded into this same stream, so a
    # single reader can never deadlock on a second, undrained pipe.
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        log(line.rstrip("\r\n"))
    code = proc.wait()
    log(f"Process finished with code {code}")
    if code != 0:
        raise RuntimeError(f"Command failed with code {code}: {' '.join(str(part) for part in cmd)}")
    return code


def deblur_with_sharped(
    input_map: Path,
    output_map: Path,
    options: JanaRunOptions,
    log: Callable[[str], None],
) -> None:
    token = options.api_token.strip() or os.environ.get("SHARPED_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("SharpED API token is empty. Fill it in the Jana dialog or set SHARPED_API_TOKEN.")
    server_url = options.server_url.strip() or DEFAULT_SERVER_URL
    model = options.model.strip() or "default"
    client = SharpEDServerClient(base_url=server_url, timeout=600.0)
    selected_model = model
    if model.lower() in {"default", "server default", "sharped default"}:
        models = client.get_models(log=log)
        selected_model = models.default_model or "SharpED latest"
        log(f"SharpED default model: {selected_model}")

    tiled_submission = decide_sharped_submission(input_map, DEFAULT_SHARPED_MAX_UPLOAD_MB) == "tiled"

    def _infer_one(request_map: Path, response_map: Path) -> None:
        def request_log(line: str) -> None:
            if tiled_submission and str(line).strip().casefold() == "[sharped] completed":
                return
            log(line)

        client.execute(
            file_path=request_map,
            bearer_token=token,
            out_path=response_map,
            elements=options.elements.strip() or "C N O",
            model=selected_model,
            outres=float(options.outres),
            poll_seconds=2,
            max_polls=-1,
            log=request_log,
        )

    # 2.0.0: the same shared, size-aware submission boundary the full GUI
    # uses -- an oversized map is tiled instead of failing or being silently
    # sent past the server's real limit.
    if tiled_submission:
        run_tiled_sharped_inference(input_map, output_map, DEFAULT_SHARPED_MAX_UPLOAD_MB, _infer_one, log)
    else:
        _infer_one(input_map, output_map)
    if not output_map.is_file() or output_map.stat().st_size == 0:
        raise RuntimeError(f"SharpED did not create output map: {output_map}")



def run_final_jana_handoff(
    original: Path,
    _exe_dir: Path,
    cwd: Path,
    original_lines: Sequence[str],
    base_name: str,
    selected_map: Path,
    log: Callable[[str], None],
) -> int:
    if not selected_map.is_file() or selected_map.stat().st_size == 0:
        raise RuntimeError(f"Selected handoff map does not exist or is empty: {selected_map}")
    header = inflip_header_for_m80(original_lines)
    # The integration directory is an application/binary location and may be
    # read-only.  Generated protocol input belongs to the active Jana project.
    calc_m80 = cwd / f".phase-studio-{os.getpid()}-calc_m80.inflip"
    conversion_lines = origin_preserving_conversion_lines(
        define_m80_inflip(header, base_name, selected_map.name), selected_map,
    )
    write_text_lines(calc_m80, conversion_lines)
    log(f"Final Jana inflip: {calc_m80}")
    log(f"Final Jana handoff model: {selected_map}")
    try:
        return run_process([str(original), str(calc_m80)], cwd=cwd, log=log)
    finally:
        try:
            calc_m80.unlink()
        except FileNotFoundError:
            pass


def run_jana_superflip(args: Sequence[str], options: JanaRunOptions, log: Callable[[str], None]) -> int:
    """Run the "Superflip only" and "Superflip + SharpED" (single-pass) workflows.

    Both workflows call the active Jana scientific Superflip with Jana2020's own .inflip essentially
    unmodified (only reference/model overrides and, for the SharpED workflow, the
    XPLOR output keyword are injected in place, under the exact same file name Jana
    supplied) so Superflip's own output-file naming is never disturbed. Phase
    recycling (multiple cycles) is handled separately by the full Phase Studio
    pipeline; this function always performs exactly one Superflip call.
    """
    cwd = Path.cwd()
    exe_dir = application_dir()
    original = resolve_active_jana_superflip(exe_dir)
    if not original.is_file():
        raise FileNotFoundError(
            f"Active Jana2020 Superflip was not found: {original}. Repair the Jana2020 integration."
        )

    inflip_arg = find_inflip_arg(args, cwd)
    if inflip_arg is None:
        log("No .inflip argument detected; forwarding directly to original Superflip.")
        return run_process([str(original), *args], cwd=cwd, log=log)

    _arg_index, inflip_path = inflip_arg
    if not inflip_path.is_file():
        raise FileNotFoundError(f"Jana2020 .inflip file not found: {inflip_path}")
    base_name = inflip_path.stem
    original_lines = read_text_lines(inflip_path)
    original_bytes = inflip_path.read_bytes()

    next_cycle_mode = str(getattr(options, "next_cycle_modelfile", "") or "").strip().lower()
    if next_cycle_mode not in {"superflip_xplor", "deblurred_xplor", "none"}:
        next_cycle_mode = "deblurred_xplor" if options.use_deblurred_map else "none"
    use_sharped = next_cycle_mode == "deblurred_xplor"
    log(
        "Workflow: "
        + ("Superflip only" if next_cycle_mode == "none" else ("Superflip + SharpED" if use_sharped else "Superflip"))
    )

    temp_files: List[Path] = []
    modified_lines = original_lines

    if options.superflip_referencefile.strip():
        referencefile_path = Path(options.superflip_referencefile).expanduser().resolve()
        if not referencefile_path.is_file():
            raise FileNotFoundError(f"Reference file not found: {referencefile_path}")
        if referencefile_path.suffix.lower() not in {".cif", ".xplor"}:
            raise RuntimeError("Reference file must be a CIF structure or an XPLOR density map.")
        staged_referencefile = stage_external_file_for_superflip(referencefile_path, cwd, base_name, "referencefile")
        temp_files.append(staged_referencefile)
        modified_lines = apply_reference_override(modified_lines, staged_referencefile)
        log(f"Reference file: {referencefile_path}")
        log(f"  staged for Superflip as local file: {staged_referencefile.name}")

    if options.first_cycle_modelfile.strip():
        source_model = Path(options.first_cycle_modelfile).expanduser().resolve()
        if not source_model.is_file():
            raise FileNotFoundError(f"Model file not found: {source_model}")
        if source_model.suffix.lower() not in {".xplor", ".ccp4", ".cif"}:
            raise RuntimeError(f"Model file must be an XPLOR map, CCP4 map or CIF structure: {source_model}")
        staged_model = stage_external_file_for_superflip(source_model, cwd, base_name, "modelfile")
        temp_files.append(staged_model)
        modified_lines = add_modelseed_modelfile(modified_lines, staged_model.name, staged_model.suffix)
        log(f"Model file: {source_model}")
        log(f"  staged for Superflip as local file: {staged_model.name}")

    if use_sharped:
        modified_lines = ensure_xplor_output(modified_lines, base_name)
        log("Output format: XPLOR map forced so the result can be submitted to the SharpED server.")

    modified = modified_lines != original_lines
    xplor_map = cwd / f"{base_name}.xplor"
    deblurred_map = cwd / f"{base_name}-deb.xplor"

    try:
        if modified:
            # Write back to the exact same file name Jana2020 supplied (args is
            # passed through unchanged below) so Superflip's own implicit
            # output-file naming, which some builds derive from the input file
            # name, is not disturbed.
            write_text_lines(inflip_path, modified_lines)
            log("Applied reference/model file overrides to the Jana2020 .inflip before calling Superflip.")
        else:
            log("Using the Jana2020 .inflip unmodified.")

        if next_cycle_mode != "none":
            for stale in (xplor_map, deblurred_map, cwd / f"{base_name}.sflog"):
                try:
                    if stale.is_file():
                        stale.unlink()
                        log(f"Removed stale Superflip output before run: {stale.name}")
                except Exception as exc:
                    log(f"Could not remove stale Superflip output {stale}: {exc}")

        run_started_at = time.time()
        run_process([str(original), *args], cwd=cwd, log=log)

        if next_cycle_mode == "none":
            log("Superflip run complete.")
            return 0

        if not xplor_map.is_file() or xplor_map.stat().st_size == 0:
            raise RuntimeError(f"Superflip did not create expected XPLOR map: {xplor_map}")
        try:
            if xplor_map.stat().st_mtime < run_started_at - 1.0:
                raise RuntimeError(
                    f"Superflip output map is older than the current run and was probably stale: {xplor_map}"
                )
        except RuntimeError:
            raise
        except Exception:
            pass
        log(f"Superflip XPLOR map: {xplor_map}")

        if use_sharped:
            deblur_with_sharped(xplor_map, deblurred_map, options, log=log)
            if not deblurred_map.is_file() or deblurred_map.stat().st_size == 0:
                raise RuntimeError(f"SharpED did not create the expected SharpED map: {deblurred_map}")
            log(f"SharpED map: {deblurred_map}")
            selected_map = deblurred_map
        else:
            selected_map = xplor_map

        code = run_final_jana_handoff(original, exe_dir, cwd, original_lines, base_name, selected_map, log)
        log("Jana2020 handoff completed. The Phase Studio launcher will close automatically.")
        try:
            qt = _qt_imports()
            app = qt["QApplication"].instance()
            if app is not None:
                app.quit()
        except Exception:
            pass
        return code
    finally:
        if modified:
            try:
                inflip_path.write_bytes(original_bytes)
            except Exception as exc:
                log(f"Could not restore the original Jana2020 .inflip content: {exc}")
        for path in temp_files:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except Exception as exc:
                log(f"Could not remove temporary file {path}: {exc}")


def _qt_imports():
    try:
        from PySide6.QtCore import QSettings, QTimer, Qt
        from PySide6.QtWidgets import (
            QApplication,
            QAbstractItemView,
            QButtonGroup,
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QDoubleSpinBox,
            QFileDialog,
            QFormLayout,
            QFrame,
            QGroupBox,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMessageBox,
            QPushButton,
            QRadioButton,
            QScrollArea,
            QSizePolicy,
            QSpinBox,
            QStackedWidget,
            QStyle,
            QTableWidget,
            QToolButton,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
    except Exception as exc:
        raise RuntimeError(
            "PySide6 could not be loaded by the Jana Superflip wrapper. "
            f"Original error: {exc}"
        ) from exc

    return {
        "QApplication": QApplication,
        "QAbstractItemView": QAbstractItemView,
        "QButtonGroup": QButtonGroup,
        "QCheckBox": QCheckBox,
        "QComboBox": QComboBox,
        "QDialog": QDialog,
        "QDialogButtonBox": QDialogButtonBox,
        "QDoubleSpinBox": QDoubleSpinBox,
        "QFileDialog": QFileDialog,
        "QFormLayout": QFormLayout,
        "QFrame": QFrame,
        "QGroupBox": QGroupBox,
        "QHBoxLayout": QHBoxLayout,
        "QHeaderView": QHeaderView,
        "QLabel": QLabel,
        "QLineEdit": QLineEdit,
        "QMessageBox": QMessageBox,
        "QPushButton": QPushButton,
        "QRadioButton": QRadioButton,
        "QScrollArea": QScrollArea,
        "QSettings": QSettings,
        "QSizePolicy": QSizePolicy,
        "QSpinBox": QSpinBox,
        "QStackedWidget": QStackedWidget,
        "QStyle": QStyle,
        "QTableWidget": QTableWidget,
        "QTableWidgetItem": QTableWidgetItem,
        "QToolButton": QToolButton,
        "QTimer": QTimer,
        "Qt": Qt,
        "QVBoxLayout": QVBoxLayout,
        "QWidget": QWidget,
    }


# Shared Jana Wizard action-tile geometry (2.0.0). Every _ActionTile uses
# exactly these, so paired tiles have identical internal geometry, and page
# elements that must line up with a tile's text column (the Autosolve
# warning) can do so by constant rather than by measured pixels.
TILE_PADDING_H = 16
TILE_PADDING_V = 5
TILE_TEXT_SPACING = 2
TILE_CHEVRON_GAP = 12
TILE_CHEVRON_WIDTH = 24  # minimum; widened to the glyph's real advance
TILE_ICON_SIZE = 24
TILE_ICON_GAP = 14
# QFrame#actionTile's QSS border (1px) + margin (1px), see ui_style.py.
TILE_FRAME_INSET = 2
TILE_TEXT_INSET = TILE_FRAME_INSET + TILE_PADDING_H + TILE_ICON_SIZE + TILE_ICON_GAP
# Gap between a tile and a note that belongs to it (vs 8px between tiles).
TILE_ATTACHED_GAP = 4

WORKFLOW_SUPERFLIP_ONLY = "superflip_only"
WORKFLOW_SUPERFLIP_SHARPED = "superflip_sharped"
WORKFLOW_PHASE_RECYCLING = "phase_recycling"
WORKFLOW_AUTOSOLVE = "autosolve"
WORKFLOW_LABELS = {
    WORKFLOW_SUPERFLIP_ONLY: "Superflip only",
    WORKFLOW_SUPERFLIP_SHARPED: "Superflip + SharpED",
    WORKFLOW_PHASE_RECYCLING: "Phase recycling with Superflip + SharpED",
    WORKFLOW_AUTOSOLVE: "SharpED Autosolve",
}
WORKFLOW_DESCRIPTIONS = {
    WORKFLOW_SUPERFLIP_ONLY: "Conventional charge-flipping structure solution",
    WORKFLOW_SUPERFLIP_SHARPED: (
        "Charge flipping with neural-network map processing"
    ),
    WORKFLOW_PHASE_RECYCLING: (
        "Iterate Superflip and SharpED over multiple cycles while keeping user control over "
        "the initial model, Map Feedback and the map passed to Jana2020."
    ),
    WORKFLOW_AUTOSOLVE: (
        "Automated iterative structure solution assisted by SharpED"
    ),
}


class _JanaWorkflowWizard:
    """Explicit-state controller for the Jana2020 Wizard dialog shown by
    show_jana_dialog() -- extracted from what was a single ~1,300-line free
    function full of nested closures sharing one mutable scope. This first
    pass keeps the exact original body as one method (with every top-level
    local promoted to a self.* attribute so it can be split into per-page
    methods next); no behavior changes.
    """

    def _shared_or_legacy_value(self, shared_key: str, legacy_key: str, fallback: str) -> str:
        if shared_key == "sharped_api_token":
            return credential_store.load_settings(self.shared_settings, self.settings) or fallback
        shared_value = str(self.shared_settings.value(f"inputs/{shared_key}", "") or "").strip()
        if shared_value:
            return shared_value
        legacy_value = str(self.settings.value(legacy_key, "") or "").strip()
        return legacy_value or fallback

    def _ensure_workflow_requirements(self, *, needs_sharped: bool) -> bool:
        """Run the shared preflight before a lightweight Wizard workflow exits."""
        from phase_studio import requirements as reqs
        from phase_studio.requirements_ui import run_remediation_loop

        saved_superflip = str(self.shared_settings.value("inputs/superflip_exe", "") or "").strip()
        try:
            active_superflip = resolve_active_jana_superflip(application_dir())
        except FileNotFoundError:
            active_superflip = Path()
        superflip_path = saved_superflip or (str(active_superflip) if active_superflip.is_file() else "")
        token = self.api_token.text().strip() or os.environ.get("SHARPED_API_TOKEN", "").strip()
        required = reqs.requirements_for_workflow(
            needs_superflip=True, needs_edma=False, needs_sharped=needs_sharped,
        )

        def persist(kind: object, value: str, _detected: bool) -> None:
            nonlocal superflip_path, token
            if kind is reqs.RequirementKind.SUPERFLIP:
                superflip_path = value
                self.shared_settings.setValue("inputs/superflip_exe", value)
            elif kind is reqs.RequirementKind.SHARPED:
                token = value
                self.api_token.setText(value)
                self.shared_settings.remove("inputs/sharped_api_token")
            self.shared_settings.sync()

        def check() -> object:
            return reqs.run_preflight(
                required,
                superflip_path=superflip_path,
                sharped_base_url=DEFAULT_SERVER_URL,
                sharped_token=token,
                jana_dir=getattr(self, "_preflight_jana_dir", resolve_jana_installation_root(application_dir()) / "SUPERFLIP"),
                client_factory=getattr(self, "_preflight_client_factory", None),
                accept_suggestion=lambda _status: True,
            )

        def on_success(result: object) -> None:
            # A wrapper-local original may have entered as the configured
            # value rather than as a suggestion; synchronize it too.
            for checked in result.statuses:
                if (checked.kind is reqs.RequirementKind.SUPERFLIP
                        and checked.ok and checked.path is not None
                        and str(checked.path) != saved_superflip):
                    persist(checked.kind, str(checked.path), True)
                if (
                    checked.kind is reqs.RequirementKind.SHARPED
                    and checked.ok
                    and checked.sharped_default_model
                ):
                    self._preflight_sharped_default_model = checked.sharped_default_model

        return run_remediation_loop(
            self.dialog,
            check,
            lambda kind: superflip_path if kind is reqs.RequirementKind.SUPERFLIP else token,
            persist,
            on_success,
            download_dir=getattr(self, "_preflight_download_dir", None),
            download_opener=getattr(self, "_preflight_download_opener", None),
            sharped_base_url=DEFAULT_SERVER_URL,
            sharped_probe=lambda key: reqs.check_sharped_api(
                DEFAULT_SERVER_URL, key,
                client_factory=getattr(self, "_preflight_client_factory", None),
            ),
        )

    def _manage_sharped_access(self) -> None:
        from phase_studio import requirements as reqs
        from phase_studio.requirements_ui import show_requirement_remediation_dialog
        previous = credential_store.get()
        self.connection_status.setText('Connecting')
        value = show_requirement_remediation_dialog(
            self.dialog, reqs.RequirementStatus(reqs.RequirementKind.SHARPED, reqs.RequirementState.OK),
            self.api_token.text(), sharped_base_url=DEFAULT_SERVER_URL,
            sharped_probe=lambda key: reqs.check_sharped_api(
                DEFAULT_SERVER_URL, key, client_factory=getattr(self, "_preflight_client_factory", None)),
        )
        if value is not None or (previous and not credential_store.get()):
            self.api_token.setText(value or "")
        self._update_account_presentation()

    # --- Wizard window width policy ---------------------------------------
    # The Wizard used to take whatever width self.content.sizeHint() happened
    # to report, which on a normal desktop settled around the 640 px minimum:
    # workflow descriptions, the Scientific-validation text and the
    # cross-validation explanation all wrapped far more than necessary, which
    # in turn made the pages tall enough to scroll while leaving wide empty
    # bands below the content. A deliberate preferred width fixes the cause
    # (too little horizontal space) rather than the symptom (height).
    #
    # Nothing here is a fixed pixel geometry: the preferred width is clamped
    # to the screen that is actually available, so 1366x768 and smaller stay
    # usable.
    WIZARD_MIN_WIDTH = 720
    WIZARD_PREFERRED_WIDTH = 1000
    WIZARD_MAX_WIDTH = 1040
    WIZARD_PREFERRED_HEIGHT = 760
    WIZARD_MAX_SCREEN_FRACTION = 0.92

    def _available_screen_width(self) -> int:
        """Usable width of the screen this dialog is on (taskbar excluded)."""
        try:
            from PySide6.QtGui import QGuiApplication

            screen = self.dialog.screen() or QGuiApplication.primaryScreen()
            if screen is not None:
                return int(screen.availableGeometry().width())
        except Exception:
            pass
        return 0

    def _available_screen_height(self) -> int:
        """Usable height of the screen this dialog is on (taskbar excluded)."""
        try:
            from PySide6.QtGui import QGuiApplication

            screen = self.dialog.screen() or QGuiApplication.primaryScreen()
            if screen is not None:
                return int(screen.availableGeometry().height())
        except Exception:
            pass
        return 0

    def _preferred_dialog_width(self) -> int:
        """Target content width: roomy on a desktop, never wider than the screen."""
        target = self.WIZARD_PREFERRED_WIDTH
        target = min(target, self.WIZARD_MAX_WIDTH)
        target = max(target, self.WIZARD_MIN_WIDTH)
        available = self._available_screen_width()
        if available > 0:
            # A narrow display wins over the preferred width every time; the
            # body scrolls and the fixed footer stays visible (see the footer
            # note in run(): it lives on outer_root, outside the scroll area).
            target = min(target, max(1, int(available * self.WIZARD_MAX_SCREEN_FRACTION)))
        return int(target)

    def _preferred_dialog_height(self) -> int:
        """One content-independent initial height for every Wizard step."""
        target = self.WIZARD_PREFERRED_HEIGHT
        available = self._available_screen_height()
        if available > 0:
            target = min(target, max(1, int(available * self.WIZARD_MAX_SCREEN_FRACTION)))
        return int(target)

    # Short numeric editors should not span the whole Wizard: at the wider
    # window a spin box holding "1" or "0.000" stretched across ~500 px, which
    # reads as an input error rather than a number. Capped to a comfortable
    # editor width, with the spare width becoming flexible space so the labels
    # stay aligned. Still well within the usable area at 1366x768.
    MAP_FEEDBACK_EDITOR_WIDTH = 180

    def _constrain_numeric_editors(self, *editors) -> None:
        """Give short numeric editors a sensible preferred width."""
        for editor in editors:
            if editor is None:
                continue
            try:
                editor.setMaximumWidth(self.MAP_FEEDBACK_EDITOR_WIDTH)
                editor.setMinimumWidth(min(140, self.MAP_FEEDBACK_EDITOR_WIDTH))
            except Exception:
                pass

    def _apply_wizard_section_style(self) -> None:
        """Give every Wizard section the same spacing rhythm.

        Tags each QGroupBox so the shared QGroupBox#wizardSection rule applies,
        and normalises the page-level gaps to the shared spacing levels. The
        main Phase Studio GUI is deliberately untouched: it has a scrollable
        settings panel per page, while the Wizard stacks several sections in
        one screen-safe window.
        """
        try:
            from phase_studio.ui_style import PHASE_STUDIO_SPACING as spacing
        except Exception:
            return
        QGroupBox = self.qt["QGroupBox"]
        for group in self.dialog.findChildren(QGroupBox):
            if not group.objectName():
                group.setObjectName("wizardSection")
        for page in (getattr(self, "page1", None), getattr(self, "page2", None),
                     getattr(self, "page3", None), getattr(self, "page_advanced", None)):
            if page is None or page.layout() is None:
                continue
            page.layout().setSpacing(spacing["section_gap"])
        if getattr(self,'page1',None) is not None:
            self.page1.layout().setSpacing(max(0,spacing['section_gap']-4))
        try:
            self.content_layout.setSpacing(max(0,spacing["section_gap"]-2))
            margin = spacing["page_margin"]
            self.content_layout.setContentsMargins(margin, 10, margin, 10)
        except Exception:
            pass

    def _fit_model_popup_width(self) -> None:
        """Widen the model drop-down's popup to fit the longest model name.

        Server model identifiers are considerably longer than the closed combo
        box, which elides them into ambiguity ("sharped-2026-03-v2-..."). The
        popup is widened to the real text width, clamped to the usable screen
        so the expanded list can never extend past the display edge. Purely
        presentational: items, ordering and the current selection are
        untouched.
        """
        try:
            view = self.model.view()
            metrics = view.fontMetrics()
            widest = max(
                (metrics.horizontalAdvance(self.model.itemText(i)) for i in range(self.model.count())),
                default=0,
            )
            if widest <= 0:
                return
            # Frame, scrollbar and a little breathing room.
            needed = widest + 48
            available = self._available_screen_width()
            if available > 0:
                needed = min(needed, int(available * self.WIZARD_MAX_SCREEN_FRACTION))
            view.setMinimumWidth(max(self.model.width(), int(needed)))
        except Exception:
            # Never let a cosmetic sizing detail break model refresh.
            pass

    def _content_inner_width(self, width: int) -> int:
        """Width available to the page inside the scrollable content column."""
        margins = self.content_layout.contentsMargins()
        return max(1, int(width) - margins.left() - margins.right())

    def _page_height_for_width(self, page, width: int) -> int:
        """Height the given page needs at *width*."""
        if page is None:
            return 0
        if page.hasHeightForWidth():
            return int(page.heightForWidth(width))
        return int(page.sizeHint().height())

    def _size_stack_to_current_page(self, width: int) -> int:
        """Pin the page stack to exactly the height the CURRENT page needs.

        QStackedLayout reports the tallest page it holds whichever page is
        showing, and the surrounding QVBoxLayout/QWidgetItem cache that answer,
        so neither overriding the stack's size hints nor invalidating the
        layout was enough on its own -- the scrolled widget stayed as tall as
        the Map feedback page and every short page kept a scrollbar it did not
        need. Setting the height explicitly is cache-proof.

        Nothing is clipped: the height IS the current page's own requirement.
        On a display too short for it the viewport shrinks below this and the
        scroll area scrolls normally, which is when a scrollbar is genuinely
        wanted.
        """
        page = self.stack.currentWidget()
        self._watch_page_growth(page)
        needed = self._page_height_for_width(page, self._content_inner_width(width))
        # Never pin below the page's own minimum: a height-for-width answer
        # computed before late content (e.g. the deferred .inflip input
        # summary) arrived is smaller than what the page now needs, and a
        # fixed height below the minimum forces Qt to squeeze compressible
        # children (the action tiles), cropping their text.
        if page is not None:
            needed = max(needed, int(page.minimumSizeHint().height()))
        if needed > 0:
            self.stack.setFixedHeight(needed)
        return needed

    def _watch_page_growth(self, page) -> None:
        """Re-fit whenever a pinned page's own content grows later.

        The stack is pinned to the current page's height, but pages keep
        changing after they are shown -- the deferred .inflip input summary,
        "From .inflip" notes, validation text, disclosures. Any of those makes
        the page's minimum taller than the pinned height, and Qt then squeezes
        the compressible action tiles and crops their text. Instead of
        patching each source, every page is watched for Qt's own
        LayoutRequest (posted whenever a descendant's size hint changes) and
        the dialog re-fits, debounced to one event-loop turn, as soon as the
        page needs more than it was given."""
        if page is None or page.property("phaseStudioGrowthWatched"):
            return
        from PySide6.QtCore import QEvent, QObject, QTimer

        wizard = self

        class _PageGrowthWatcher(QObject):
            def __init__(self, parent) -> None:
                super().__init__(parent)
                self._pending = False

            def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt override
                if event.type() == QEvent.LayoutRequest and watched is wizard.stack.currentWidget():
                    # Synchronously, before anything is painted: settle the
                    # page's own layout and re-pin the stack if the page now
                    # needs more -- so not even one frame shows squeezed
                    # tiles. The full dialog re-fit follows one turn later.
                    layout = watched.layout()
                    if layout is not None:
                        layout.activate()
                    needed = int(watched.minimumSizeHint().height())
                    if needed > wizard.stack.height():
                        wizard.stack.setFixedHeight(needed)
                    if not self._pending:
                        self._pending = True
                        QTimer.singleShot(0, self._refit)
                return False

            def _refit(self) -> None:
                self._pending = False
                from shiboken6 import isValid
                if not isValid(wizard.stack):
                    return
                current = wizard.stack.currentWidget()
                if current is None:
                    return
                # Every page may both grow and shrink (catalogue status,
                # warnings and disclosures). Re-pin only the scroll body at
                # the user's current width, never the top-level window.
                wizard._size_stack_to_current_page(wizard.dialog.width())

        watcher = _PageGrowthWatcher(page)
        page.installEventFilter(watcher)
        page.setProperty("phaseStudioGrowthWatched", True)
        self._page_growth_watchers = getattr(self, "_page_growth_watchers", []) + [watcher]

    def _content_height_for_width(self, width: int) -> int:
        """Height the scrollable content column needs at *width*.

        Summed from the content layout's own items rather than asking the
        widget, whose heightForWidth is cached per width and went stale as soon
        as the visible page changed.
        """
        margins = self.content_layout.contentsMargins()
        inner = self._content_inner_width(width)
        total = margins.top() + margins.bottom()
        visible_items = 0
        for index in range(self.content_layout.count()):
            item = self.content_layout.itemAt(index)
            widget = item.widget()
            if widget is None:
                total += int(item.sizeHint().height())
                visible_items += 1
                continue
            if widget is self.stack:
                total += self._page_height_for_width(self.stack.currentWidget(), inner)
            elif widget.hasHeightForWidth():
                total += int(widget.heightForWidth(inner))
            else:
                total += int(widget.sizeHint().height())
            visible_items += 1
        if visible_items > 1:
            total += self.content_layout.spacing() * (visible_items - 1)
        return max(0, total)

    def _adjust_dialog_size(self) -> None:
        from phase_studio.app import apply_safe_dialog_geometry
        # All later changes reflow only the scroll body. Initial geometry is
        # applied exactly once, after the shared footer exists.
        if not getattr(self,'_geometry_initialized',False) and self.jana_parent_rect is not None:
            from PySide6.QtGui import QGuiApplication
            screen=QGuiApplication.screenAt(self.jana_parent_rect.center())
            if screen is not None:
                self.dialog.winId()
                self.dialog.windowHandle().setScreen(screen)
        target_width = self.dialog.width() if getattr(self, "_geometry_initialized", False) else self._preferred_dialog_width()
        self._size_stack_to_current_page(target_width)
        if not getattr(self, "_geometry_initialized", False) and self.chrome_holder.get("footer") is not None:
            self._geometry_initialized = True
            apply_safe_dialog_geometry(self.dialog, target_width, self._preferred_dialog_height())
            saved = self.settings.value("wizard/windowGeometry")
            restored=bool(saved and self.dialog.restoreGeometry(saved))
            from PySide6.QtCore import QRect
            saved_rect = self.settings.value("wizard/windowRect")
            if isinstance(saved_rect,QRect) and saved_rect.isValid():
                self.dialog.setGeometry(saved_rect);restored=True
            if not restored and self.jana_parent_rect is not None:
                self.dialog.move(self.dialog.pos()+self.jana_parent_rect.center()-self.dialog.frameGeometry().center())
            from phase_studio.ui_branding import clamp_window_to_available_screen
            clamp_window_to_available_screen(self.dialog)
            self._size_stack_to_current_page(self.dialog.width())
        # Once this geometry is laid out, re-check the current page at the
        # width it really got (a vertical scrollbar on a short screen makes it
        # narrower than measured above); only ever grows.
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self.stack._grow_to_current_page)

    def _get_backing_window(self):
        win = self.backing_window_holder.get("win")
        if win is not None:
            return win
        from phase_studio.app import IterativeSuperflipPipelineQtGUI, parse_inflip_settings

        win = IterativeSuperflipPipelineQtGUI()
        if self.inflip_path is not None:
            try:
                parsed = parse_inflip_settings(self.inflip_path)
                handoff_import = build_jana_handoff_import(self.inflip_path, JanaRunOptions(action="edit"), parsed)
                for key, value in handoff_import.values.items():
                    widget = win.inputs.get(key)
                    if widget is not None:
                        win._set_widget_value_from_string(widget, value)
                win._input_mode_user_changed()
                win._sync_input_source_mode_widgets()
            except Exception:
                pass
        self.backing_window_holder["win"] = win
        return win

    def _sync_map_choice(self) -> None:
        self.validation_group.setVisible(self.sharped_map_radio.isChecked())
        self._adjust_dialog_size()

    def _detect_reflection_data_mode(self) -> str:
        # The ACTUAL parsed reflection format (not filename/composition/space
        # group) -- calls the same shared resolver app.py's own
        # _resolve_configured_data_mode_for_ui() uses for its "Jana2020
        # .inflip" input mode (configured mode AUTO, no separate HKL
        # override -- the Wizard never has one), without needing a hidden
        # backing window just to reach it.
        if self.detected_data_mode_holder["mode"] is None:
            from phase_studio.app import (
                REFLECTION_DATA_MODE_AUTO,
                normalize_reflection_data_mode,
                resolve_reflection_data_mode_from_sources,
            )
            try:
                self.detected_data_mode_holder["mode"] = resolve_reflection_data_mode_from_sources(
                    Path(""), REFLECTION_DATA_MODE_AUTO, self.inflip_path
                )
            except Exception:
                self.detected_data_mode_holder["mode"] = normalize_reflection_data_mode(REFLECTION_DATA_MODE_AUTO)
        return self.detected_data_mode_holder["mode"]

    def _sync_page3_for_data_type(self) -> None:
        from phase_studio.app import (
            format_reflection_data_mode,
            reflection_mode_has_fwhm,
            reflection_mode_is_amplitude,
        )
        import math
        mode = self._detect_reflection_data_mode()
        is_powder = reflection_mode_has_fwhm(mode)
        self.feedback_is_powder = is_powder
        self.reflection_type_value.setText("Powder / polycrystalline" if is_powder else "Single crystal")
        self.reflection_format_value.setText(format_reflection_data_mode(mode) if mode else "Not yet determined")
        self.feedback_has_uncertainty = not is_powder and any(
            r.sigma is not None and math.isfinite(float(r.sigma)) and r.sigma > 0
            and math.isfinite(float(r.value))
            for r in getattr(self, "input_reflections", ())
        )
        self.page3_description.setText(
            "FWHM: peak width in degrees 2θ · σ(I) unavailable. FWHM is not measurement uncertainty."
            if is_powder else
            ("Measured uncertainties available." if self.feedback_has_uncertainty else
             "Valid measured uncertainties unavailable." if hasattr(self, "input_reflections") else
             "Uncertainty availability has not been verified; validate the incoming HKL data.")
        )
        self.missing_group.setVisible(not is_powder)
        self.intensity_group.setVisible(True)
        self.powder_group.setVisible(is_powder)
        ratio = "F/σ(F)" if reflection_mode_is_amplitude(mode) else "I/σ(I)"
        self.intensity_form.labelForField(self.intensity_sigma_spin).setText(f"{ratio} limit")
        self.intensity_note.setText(
            f"Positive limits use measured {ratio}; 0 applies to all map-supported reflections."
            if self.feedback_has_uncertainty else
            ("Experimental intensity uncertainties are not supplied. " if is_powder else
             "Valid measured uncertainties are unavailable. " if hasattr(self, "input_reflections") else
             "Measured uncertainties have not been verified. ") + "Significance filtering is unavailable. "
            "Correction uses the existing threshold-0 mode: all reflections with a positive map prediction, without σ."
        )
        self.intensity_enabled_checkbox.setText(
            'Enable map-supported intensity correction (no σ filter)' if not self.feedback_has_uncertainty else
            'Enable weak-reflection intensity correction')
        self.intensity_group.setTitle('Weak-reflection intensity correction' if self.feedback_has_uncertainty else
                                      'Map-supported intensity correction (experimental)')
        self._sync_feedback_applicability()
        self._adjust_dialog_size()

    def _map_feedback_wavelength(self) -> tuple[float, str]:
        from phase_studio.app import resolve_powder_wavelength, resolve_jana_m90_path
        reference = self.reference_file.text().strip()
        return resolve_powder_wavelength(
            self.powder_wavelength_spin.value(), self.inflip_path,
            Path(reference).expanduser() if reference else None,
            jana_m90_path=resolve_jana_m90_path(self.inflip_path),
        )

    def _check_page3_validity(self) -> Optional[str]:
        if getattr(self, "model_policy_error", ""):
            return str(self.model_policy_error)
        if (
            self._current_workflow() != WORKFLOW_SUPERFLIP_ONLY
            and not getattr(self, "model_cache", {}).get("loaded", False)
        ):
            return "Wait for the live SharpED model catalogue, or use Refresh models to retry."
        if self._current_workflow() != WORKFLOW_SUPERFLIP_ONLY and not self.model.currentText().strip():
            return "Select an available SharpED model before running."
        # Map feedback only affects SUBSEQUENT cycles -- an enabled method
        # whose "Start after cycle" leaves no later cycle to apply to would
        # silently do nothing; block Run rather than accept a setting that
        # can never take effect. Never auto-raises Cycles to fix this.
        total_cycles = max(1, self.cycles.value())
        for checkbox, spin in (
            (self.missing_enabled_checkbox, self.missing_start_cycle_spin),
            (self.intensity_enabled_checkbox, self.intensity_start_cycle_spin),
            (self.powder_enabled_checkbox, self.powder_start_cycle_spin),
        ):
            if total_cycles > 1 and checkbox.isVisible() and checkbox.isChecked() and spin.value() >= total_cycles:
                return "A subsequent cycle is required for map feedback."
        if total_cycles > 1 and self.powder_group.isVisible() and self.powder_enabled_checkbox.isChecked():
            wavelength, _source = self._map_feedback_wavelength()
            import math
            if wavelength <= 0 or not math.isfinite(wavelength):
                return "Enter a positive wavelength (Å) for powder repartitioning; automatic detection found none."
        return None

    def _refresh_page3_validation_message(self) -> None:
        message = self._check_page3_validity()
        self.page3_validation_label.setText(message or "")
        self.page3_validation_label.setVisible(bool(message))

    def _current_workflow(self) -> str:
        return self.workflow_state["key"]

    def _apply_workflow_cycle_default(self, key: str) -> None:
        # The recommended workflow is the established ordinary multi-cycle
        # Superflip -> EDMA -> SharpED -> EDMA loop. Five cycles are the
        # recommended balance between solution quality and calculation time.
        configurable = key in (WORKFLOW_SUPERFLIP_SHARPED, WORKFLOW_PHASE_RECYCLING)
        self.cycles.setEnabled(configurable)
        recompute_default = not (self.cycles_user_edited["value"] and configurable)
        self.cycles.blockSignals(True)
        try:
            # A single cycle never feeds a map back into a next cycle, so it
            # isn't actually "recycling" -- the spinbox's own minimum (not
            # just its default value) is raised to 2 for this workflow so the
            # control itself can't be turned down to a non-recycling value.
            self.cycles.setMinimum(1)
            if recompute_default:
                if configurable:
                    self.cycles.setValue(max(int(self.settings.value("cycles", 5)) or 5, 1))
                else:
                    self.cycles.setValue(1)
        finally:
            self.cycles.blockSignals(False)

    def _sync_primary_button_for_page1(self) -> None:
        # Selecting a workflow card never runs or navigates by itself; the
        # bottom-right button is the one clear place that either advances to the
        # workflow's extra settings or, for Superflip only, runs it directly.
        if self._current_workflow() == WORKFLOW_SUPERFLIP_ONLY:
            self.primary_button.setText("Run phasing")
            self.primary_button.setToolTip(
                "Execute the Jana2020 Superflip job through the Phase Studio cycle wrapper."
            )
        elif self._current_workflow() == WORKFLOW_AUTOSOLVE:
            self.primary_button.setText("Start Autosolve")
            self.primary_button.setToolTip("Start the guided SharpED Autosolve workflow.")
        else:
            self.primary_button.setText("Next ›")
            self.primary_button.setToolTip("Continue to the SharpED and cycle settings.")

    def _workflow_changed(self) -> None:
        key = self._current_workflow()
        self.processing_progress.setVisible(key == WORKFLOW_SUPERFLIP_SHARPED)
        for card_key, card in self.workflow_cards.items():
            card.set_selected(card_key == key)
        cycles_visible = key in (WORKFLOW_SUPERFLIP_SHARPED, WORKFLOW_PHASE_RECYCLING)
        self.cycles.setVisible(cycles_visible)
        if self.cycles_label is not None:
            self.cycles_label.setVisible(cycles_visible)
        # Autosolve and Superflip only do not visit the configurable ordinary
        # workflow pages.
        if key in (WORKFLOW_SUPERFLIP_SHARPED, WORKFLOW_PHASE_RECYCLING):
            self._apply_workflow_cycle_default(key)
            self.map_group.setTitle(
                "Map used for phase recycling and Jana2020 handoff"
                if key == WORKFLOW_PHASE_RECYCLING
                else "Map used for Jana2020 handoff"
            )
            # The raw-vs-SharpED map choice is only meaningful for Phase
            # recycling; "Superflip + SharpED" always uses the SharpED map
            # (see effective_next_cycle_mode()), so offering it as a live
            # choice there would be misleading. Force the radio to match
            # before hiding it, so it reflects the truth if ever shown again.
            self.map_group.setVisible(False)
            if key == WORKFLOW_SUPERFLIP_SHARPED:
                self.sharped_map_radio.setChecked(True)
                self._sync_map_choice()
            self._adjust_dialog_size()
        self.cross_validation_group.setVisible(key == WORKFLOW_PHASE_RECYCLING)
        if self.stack.currentWidget() is self.page1:
            self._sync_primary_button_for_page1()

    def __init__(self, args: Sequence[str], inflip_path: Optional[Path]) -> None:
        self.inflip_path = inflip_path
        qt = _qt_imports()
        self.qt = qt
        QApplication = qt["QApplication"]
        QButtonGroup = qt["QButtonGroup"]
        QComboBox = qt["QComboBox"]
        QDialog = qt["QDialog"]
        QDoubleSpinBox = qt["QDoubleSpinBox"]
        QFileDialog = qt["QFileDialog"]
        QFormLayout = qt["QFormLayout"]
        QFrame = qt["QFrame"]
        QGroupBox = qt["QGroupBox"]
        QHBoxLayout = qt["QHBoxLayout"]
        QLabel = qt["QLabel"]
        QLineEdit = qt["QLineEdit"]
        QPushButton = qt["QPushButton"]
        QCheckBox = qt["QCheckBox"]
        QRadioButton = qt["QRadioButton"]
        QScrollArea = qt["QScrollArea"]
        QSettings = qt["QSettings"]
        QSizePolicy = qt["QSizePolicy"]
        QSpinBox = qt["QSpinBox"]
        QStackedWidget = qt["QStackedWidget"]
        QStyle = qt["QStyle"]
        QTimer = qt["QTimer"]
        QToolButton = qt["QToolButton"]
        Qt = qt["Qt"]
        QVBoxLayout = qt["QVBoxLayout"]
        QWidget = qt["QWidget"]

        app = QApplication.instance() or QApplication([sys.argv[0], *args])
        # Same application icon as the main window, via the same helper: the
        # Wizard is Phase Studio, not a separate tool, and without this its
        # title bar, taskbar entry and Alt+Tab card all show the generic Qt
        # icon. Set on the application, so every Wizard page and dialog
        # inherits it.
        try:
            from phase_studio.app import apply_phase_studio_app_icon

            apply_phase_studio_app_icon(app)
        except Exception:
            pass
        apply_phase_studio_style(app)
        # Load after PySide6/style setup, same ordering as the other phase_studio.app
        # imports in this module: shares the exact header/banner widgets the main
        # window uses, so the Wizard reads as the same application, not a generic
        # Qt dialog.
        from phase_studio.app import (
            apply_safe_dialog_geometry,
            create_phase_studio_brand_header,
            create_phase_studio_context_banner,
            format_reflection_data_mode,
            reflection_mode_has_fwhm,
            resolve_powder_wavelength,
        )

        self.settings = QSettings("PhaseStudio", "JanaSuperflipWrapper")
        # SharpED connection credentials (server URL, API token) are shared with the
        # full Phase Studio application's own QSettings store, not kept as a second,
        # independent copy here -- otherwise whichever one launched last silently
        # overwrites the other's token the next time either app saves its settings.
        self.shared_settings = QSettings("PhaseStudio", "PhaseStudio")


        saved_workflow = str(self.settings.value("workflow", WORKFLOW_SUPERFLIP_ONLY))
        if saved_workflow not in WORKFLOW_LABELS:
            saved_workflow = WORKFLOW_SUPERFLIP_ONLY
        self.workflow_state = {"key": saved_workflow}

        from phase_studio.ui_branding import jana_launch_parent_rect
        self.jana_parent_rect=jana_launch_parent_rect()
        self.dialog = QDialog()
        self.dialog.setWindowTitle(f"Phase Studio {__version__} for Jana2020")
        self.dialog.setMinimumWidth(min(640, max(1, int(self._available_screen_width() * self.WIZARD_MAX_SCREEN_FRACTION))))

        # footer is only constructed later (after page1/page2), but
        # adjust_dialog_size() is also invoked by callbacks wired up during page2
        # construction, before it exists -- this mutable holder (same pattern as
        # backing_window_holder below) lets adjust_dialog_size() reference
        # whatever footer currently exists (or none yet) without a NameError; the
        # final go_to_page1() call after construction recomputes the size once
        # footer is available, so an early, footer-less estimate here is harmless.
        self.chrome_holder: dict = {"footer": None}


        self.outer_root = QVBoxLayout(self.dialog)
        self.outer_root.setContentsMargins(0, 0, 0, 0)
        self.outer_root.setSpacing(0)

        self.brand_header = create_phase_studio_brand_header()
        self.brand_header.layout().setContentsMargins(12, 5, 12, 5)
        for label in self.brand_header.findChildren(QLabel):
            if label.objectName() == "versionBadge":
                label.setStyleSheet("color: #7183a6; background: transparent; font-size: 8pt; padding: 2px 4px;")
        self.outer_root.addWidget(self.brand_header)

        self.context_banner = create_phase_studio_context_banner(
            "JANA2020 WORKFLOW", "Review the incoming crystallographic data and choose a workflow"
        )
        self.context_title_label = self.context_banner.findChild(QLabel, "dashboardTitle")
        self.context_subtitle_label = self.context_banner.findChild(QLabel, "dashboardSubtitle")
        self.outer_root.addWidget(self.context_banner)

        # Only this central area scrolls (spec: "WIZARD WINDOW SIZING" section 5) --
        # the branded header/banner above and the action footer added at the very
        # end of this function (via outer_root, not `root`) always stay fixed and
        # visible, however tall an expanded page's content gets.
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("wizardScrollArea")
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(14, 10, 14, 10)
        self.content_layout.setSpacing(10)
        self.scroll_area.setWidget(self.content)
        self.outer_root.addWidget(self.scroll_area, 1)
        self.root = self.content_layout

        class _InputIdentification(QLabel):
            def __init__(self, text: str) -> None:
                super().__init__(text)
                self.full_text = text
                self.setAccessibleName(text)
                self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

            def resizeEvent(self, event) -> None:
                self.setText(self.fontMetrics().elidedText(self.full_text, Qt.ElideMiddle, self.width()))
                super().resizeEvent(event)

        self.inflip_info = _InputIdentification(
            f"Jana2020 input: {inflip_path.name}" if inflip_path else "No .inflip argument was detected."
        )
        self.inflip_info.setToolTip(str(inflip_path) if inflip_path else "")
        self.root.addWidget(self.inflip_info)

        # QStackedLayout reports the tallest page it holds for BOTH sizeHint()
        # and heightForWidth(), whichever page is showing. Inside a
        # widgetResizable QScrollArea that made the scrolled widget permanently
        # as tall as the Map feedback page, so every page -- including the short
        # workflow page -- displayed a vertical scrollbar it did not need, and
        # short pages sat in a tall window with a large blank band.
        #
        # Reporting the CURRENT page's requirement instead is what actually
        # makes the content fit: nothing is clipped and nothing is hidden, the
        # scroll area simply stops being told the page overflows. Scrolling
        # still engages normally when a page genuinely is taller than the
        # viewport (the policy stays ScrollBarAsNeeded).
        class _CurrentPageStack(QStackedWidget):
            def sizeHint(self):  # noqa: N802 - Qt override
                page = self.currentWidget()
                return page.sizeHint() if page is not None else super().sizeHint()

            def minimumSizeHint(self):  # noqa: N802 - Qt override
                page = self.currentWidget()
                return page.minimumSizeHint() if page is not None else super().minimumSizeHint()

            def hasHeightForWidth(self):  # noqa: N802 - Qt override
                page = self.currentWidget()
                return page.hasHeightForWidth() if page is not None else super().hasHeightForWidth()

            def heightForWidth(self, width):  # noqa: N802 - Qt override
                page = self.currentWidget()
                if page is not None and page.hasHeightForWidth():
                    return page.heightForWidth(width)
                return super().heightForWidth(width)

            def resizeEvent(self, event):  # noqa: N802 - Qt override
                super().resizeEvent(event)
                # The pinned height is measured at the dialog's content width.
                # When the window is capped to a short screen, the body
                # scrolls and the vertical scrollbar narrows this stack, so
                # word-wrapped text (e.g. the Autosolve warning at 150%) needs
                # another line. Re-check at the real width; only ever grow.
                if event.size().width() != event.oldSize().width():
                    QTimer.singleShot(0, self._grow_to_current_page)

            def _grow_to_current_page(self):
                try:
                    page = self.currentWidget()
                except RuntimeError:
                    return  # the Wizard closed before this deferred check ran
                if page is None or not page.hasHeightForWidth() or self.width() <= 1:
                    return
                needed = int(page.heightForWidth(self.width()))
                if needed > self.height():
                    self.setFixedHeight(needed)

        self.stack = _CurrentPageStack()
        # Re-ask the layout for a size whenever the visible page changes.
        self.stack.currentChanged.connect(lambda _index=0: self.stack.updateGeometry())
        self.root.addWidget(self.stack, 1)
        # The pinned stack cannot absorb surplus height. Keep the incoming
        # filename and scientific forms at their natural height, with unused
        # window space below the content instead of between these blocks.
        self.root.addStretch(1)

        self._build_page1()
        self._build_page2()
        self._build_page3()

    # ----- Page 1: input summary, reference/model files, then the 3 primary workflow actions -----
    def _build_page1(self) -> None:
        # One authoritative source for every model/reference file filter, shared
        # with the main window (see phase_studio.app) so no selector carries its
        # own extension list.
        from phase_studio.app import (
            supported_model_filters,
            supported_wrapper_reference_filters,
        )
        # Icons come ONLY from Phase Studio's established icon inventory
        # (ui_branding.ESTABLISHED_ICON_INVENTORY); actions with no
        # established icon stay text-only rather than adding a new family.
        from phase_studio.ui_branding import apply_established_icon

        qt = self.qt
        QFileDialog = qt["QFileDialog"]
        QFormLayout = qt["QFormLayout"]
        QFrame = qt["QFrame"]
        QGroupBox = qt["QGroupBox"]
        QHBoxLayout = qt["QHBoxLayout"]
        QLabel = qt["QLabel"]
        QLineEdit = qt["QLineEdit"]
        QPushButton = qt["QPushButton"]
        Qt = qt["Qt"]
        QTimer = qt["QTimer"]
        QVBoxLayout = qt["QVBoxLayout"]
        QWidget = qt["QWidget"]
        from phase_studio.app import format_reflection_data_mode

        self.page1 = QWidget()
        self.page1_layout = QVBoxLayout(self.page1)
        self.page1_layout.setContentsMargins(0, 0, 0, 0)
        self.page1_layout.setSpacing(4)

        # A hidden, never-shown full Phase Studio window used purely as a dialog
        # factory: it reuses the exact same HKL parsing/validation/completeness
        # implementation (and diagnostic dialog styling) as the main application,
        # seeded from THIS incoming .inflip via the same hand-off mechanism used
        # for "Open full Phase Studio" / "Phase recycling" -- not from whatever a
        # previous, unrelated Phase Studio session had saved. Built lazily so the
        # wizard's first page still appears immediately.
        self.backing_window_holder: dict = {"win": None}


        def build_page1_section(title: str, helper_text: str = "") -> tuple:
            # A plain QGroupBox's title/border/padding chrome (shared app-wide via
            # ui_style.py, so not something this single-page pass may change)
            # costs roughly 35-40px of pure vertical overhead per section on top
            # of its actual content -- with three stacked sections on this page,
            # that alone can be the difference between fitting on screen at
            # 150% Windows scaling and needing a scrollbar. Using the same
            # lightweight sectionLabel-plus-rule heading for all three of this
            # page's sections (Input summary / Reference and initial model /
            # Workflow) instead keeps them visually distinct and on-brand while
            # recovering that space; this only affects page1 of the Wizard, not
            # QGroupBox elsewhere in the app.
            section = QWidget()
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(0, 0, 0, 0)
            section_layout.setSpacing(2)
            heading_row = QHBoxLayout()
            heading_row.setSpacing(8)
            heading_label = QLabel(title.upper())
            heading_label.setObjectName("sectionLabel")
            heading_row.addWidget(heading_label)
            heading_row.addStretch(1)
            if helper_text:
                helper_label = QLabel(helper_text)
                helper_label.setStyleSheet("color: #7183a6; font-style: italic;")
                heading_row.addWidget(helper_label)
            section_layout.addLayout(heading_row)
            separator = QFrame()
            separator.setFixedHeight(2)
            separator.setFrameShape(QFrame.NoFrame)
            separator.setStyleSheet("background-color: #2264b8;")
            section_layout.addWidget(separator)
            body = QWidget()
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(0, 2, 0, 0)
            body_layout.setSpacing(3)
            section_layout.addWidget(body)
            return section, body_layout

        # Compact single-row-per-field summary with the diagnostic actions
        # (Validate HKL / Analyze completeness) as a small button column on the
        # right rather than a third row underneath the metadata -- keeps the
        # whole section short enough that it, the Reference/model section and
        # all three Workflow cards fit on the first page without scrolling.
        self.input_summary_section, self.input_summary_body = build_page1_section("Input summary")
        self.input_summary_outer = QHBoxLayout()
        self.input_summary_outer.setSpacing(14)
        self.input_summary_body.addLayout(self.input_summary_outer)

        wizard = self

        class _SummaryFields(QWidget):
            def resizeEvent(self, event):
                super().resizeEvent(event)
                from PySide6.QtGui import QTextDocument
                def form_width(form):
                    width=0
                    for row in range(form.rowCount()):
                        label=form.itemAt(row,QFormLayout.LabelRole).widget()
                        value=form.itemAt(row,QFormLayout.FieldRole).widget()
                        document=QTextDocument()
                        document.setDocumentMargin(0)
                        document.setDefaultFont(value.font())
                        if '</' in value.text():document.setHtml(value.text())
                        else:document.setPlainText(value.text())
                        document.setTextWidth(-1)
                        width=max(width,label.sizeHint().width()+form.horizontalSpacing()+int(document.idealWidth()+1))
                    return width
                fields_width=sum(form_width(form) for form in (wizard.input_summary_layout,wizard.input_summary_right_layout))+wizard.input_summary_columns.spacing()
                required=fields_width
                available=wizard.input_summary_section.contentsRect().width()
                wizard.summary_wide_minimum_width=required
                narrow = event.size().width() < fields_width
                wizard.input_summary_columns.setDirection(
                    QHBoxLayout.TopToBottom if narrow else QHBoxLayout.LeftToRight
                )

        self.input_summary_fields = _SummaryFields()
        self.input_summary_columns = QHBoxLayout(self.input_summary_fields)
        self.input_summary_columns.setContentsMargins(0, 0, 0, 0)
        self.input_summary_columns.setSpacing(12)
        left_summary = QWidget()
        right_summary = QWidget()
        self.input_summary_layout = QFormLayout(left_summary)
        self.input_summary_right_layout = QFormLayout(right_summary)
        for summary_layout in (self.input_summary_layout, self.input_summary_right_layout):
            summary_layout.setContentsMargins(0, 0, 0, 0)
            summary_layout.setVerticalSpacing(2)
            summary_layout.setHorizontalSpacing(10)
            summary_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            summary_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.reflections_value = QLabel("Not available")
        self.format_value = QLabel("Not available")
        self.data_type_value = QLabel("Not available / unverified")
        self.cell_value = QLabel("Not available")
        self.spacegroup_value = QLabel("Not available")
        self.composition_value = QLabel("Not available")
        for summary_label in (self.reflections_value, self.format_value, self.cell_value, self.spacegroup_value, self.composition_value):
            summary_label.setWordWrap(True)
        self.reflections_value.setWordWrap(True)
        self.input_summary_layout.addRow("Reflections", self.reflections_value)
        self.input_summary_layout.addRow("Data type", self.data_type_value)
        self.input_summary_layout.addRow("Format", self.format_value)
        self.input_summary_right_layout.addRow("Cell", self.cell_value)
        self.input_summary_right_layout.addRow("Space group", self.spacegroup_value)
        for title, summary, stretch in (("Reflection data", left_summary, 1), ("Crystal data", right_summary, 1)):
            group = QWidget()
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(0, 0, 0, 0)
            group_layout.setSpacing(3)
            heading = QLabel(title)
            heading.setStyleSheet("color: #33456e; font-weight: 600;")
            group_layout.addWidget(heading)
            group_layout.addWidget(summary)
            group_layout.addStretch(1)
            self.input_summary_columns.addWidget(group, stretch)
        self.input_summary_outer.addWidget(self.input_summary_fields, 1)

        self.hkl_buttons_column = QHBoxLayout()
        self.hkl_buttons_column.setSpacing(8)
        analysis_label = QLabel("Input analysis")
        analysis_label.setStyleSheet("color:#33456e; font-weight:600;")
        self.hkl_buttons_column.addWidget(analysis_label)
        self.validate_hkl_button = QPushButton("Validate HKL")
        self.analyze_completeness_button = QPushButton("Analyze completeness")
        self.hkl_buttons_column.addWidget(self.validate_hkl_button)
        self.hkl_buttons_column.addWidget(self.analyze_completeness_button)
        self.hkl_buttons_column.addStretch(1)
        analysis_button_width = max(self.validate_hkl_button.sizeHint().width(), self.analyze_completeness_button.sizeHint().width()) + 12
        for button in (self.validate_hkl_button, self.analyze_completeness_button):
            button.setFixedWidth(analysis_button_width)
            button.setAccessibleName(button.text())
            button.setMinimumHeight(36)
            button.setStyleSheet(
                "QPushButton { background:#ffffff; color:#001170; border:1px solid #8fa9cc; padding:5px 12px; }"
                "QPushButton:hover { background:#edf3fa; border-color:#527dab; }"
                "QPushButton:focus { background:#f5f9ff; border:2px solid #2264b8; padding:4px 11px; }"
                "QPushButton:pressed { background:#dceaf8; border-color:#2264b8; }"
            )
            button.ensurePolished()
        diagnostic_width = max(button.sizeHint().width() for button in (
            self.validate_hkl_button, self.analyze_completeness_button
        ))
        for button in (self.validate_hkl_button, self.analyze_completeness_button):
            button.setMinimumWidth(diagnostic_width)
        self.input_summary_body.addLayout(self.hkl_buttons_column)
        composition_row = QHBoxLayout()
        composition_row.setSpacing(10)
        composition_row.addWidget(QLabel("Superflip input composition"))
        composition_row.addWidget(self.composition_value, 1)
        self.input_summary_body.addLayout(composition_row)
        self.page1_layout.addWidget(self.input_summary_section)

        def refresh_input_summary() -> None:
            no_inflip_tip = "No incoming Jana2020 .inflip was supplied."
            if self.inflip_path is None:
                self.validate_hkl_button.setEnabled(False)
                self.analyze_completeness_button.setEnabled(False)
                self.validate_hkl_button.setToolTip(no_inflip_tip)
                self.analyze_completeness_button.setToolTip(no_inflip_tip)
                return
            try:
                from phase_studio.app import (
                    build_hkl_analysis_request_from_inflip,
                    build_hkl_load_result,
                    format_reflection_data_mode,
                    parse_inflip_settings,
                )
                # Computed directly from this Wizard's own state (no hidden
                # backing IterativeSuperflipPipelineQtGUI needed for this --
                # unlike validate_hkl_clicked()/analyze_completeness_clicked()
                # below, this only needs the shared HKL-analysis computation,
                # not the main GUI's dialog presentation). work_dir is
                # resolved via the same build_jana_handoff_import() call the
                # backing window itself would apply to its own widgets, so
                # the embedded-HKL cache file lands in the same place a real
                # run would put it.
                ref_text = self.reference_file.text().strip()
                reference_file = Path(ref_text).expanduser() if ref_text else None
                parsed = parse_inflip_settings(self.inflip_path)
                handoff_import = build_jana_handoff_import(self.inflip_path, JanaRunOptions(action="edit"), parsed)
                work_dir_text = handoff_import.values.get("work_dir", "")
                work_dir = Path(work_dir_text) if work_dir_text else None
                request = build_hkl_analysis_request_from_inflip(
                    self.inflip_path, reference_file=reference_file, work_dir=work_dir
                )
                # Large input summaries use the same cached diagnostic worker
                # as the dialogs, without doing a long parse on the Qt thread.
                # Small inputs retain their immediate summary presentation.
                state = getattr(self, "_hkl_summary_state", None)
                if self.inflip_path.stat().st_size > 1_000_000 and state is None:
                    import threading
                    from phase_studio.hkl_diagnostics import diagnostic_cancellation
                    from shiboken6 import isValid
                    state = self._hkl_summary_state = {"done": False}
                    cancelled = threading.Event()
                    self.dialog.finished.connect(lambda _result: cancelled.set())

                    def load_summary() -> None:
                        try:
                            with diagnostic_cancellation(cancelled):
                                state["result"] = build_hkl_load_result(request)
                        except Exception:
                            state["error"] = True
                        finally:
                            state["done"] = True

                    def poll_summary() -> None:
                        if not isValid(self.dialog) or cancelled.is_set():
                            return
                        if not state["done"]:
                            QTimer.singleShot(25, poll_summary)
                        else:
                            refresh_input_summary_and_refit()

                    threading.Thread(target=load_summary, daemon=True).start()
                    self.reflections_value.setText("Loading HKL diagnostics…")
                    QTimer.singleShot(25, poll_summary)
                    return
                if state is not None:
                    if not state["done"] or state.get("error"):
                        return
                    result = state["result"]
                else:
                    result = build_hkl_load_result(request)
            except Exception:
                # Per spec: never show a raw exception in this summary. The
                # existing structured error dialog still covers Validate HKL /
                # Analyze completeness themselves if the reflection block truly
                # cannot be analyzed.
                return
            self.reflections_value.setText(f"{len(result.reflections):,} HKL records · {len(result.unique_reflections):,} unique indices")
            self.reflections_value.setToolTip(
                "Unique indices count distinct literal (h, k, l) tuples, not symmetry-independent orbits. "
                "For powder input, indexed reflections need not be independently measured or resolved."
            )
            self.input_reflections = result.reflections
            if hasattr(self, "intensity_group"):
                self._sync_page3_for_data_type()
            self.format_value.setText(format_reflection_data_mode(result.data_mode))
            # Use the diagnostic authority's verified column semantics, never
            # a filename or AUTO fallback, to classify the measurement input.
            report = result.diagnostics
            verified = report is not None and report.available('column_semantics')
            self.data_type_value.setText(('Powder / polycrystalline' if report.data_type.startswith('Powder') else 'Single crystal') if verified else 'Not available / unverified')
            self.format_value.setToolTip('FWHM is a peak width in degrees 2θ, not a measurement uncertainty.' if verified and report.data_type.startswith('Powder') and report.fwhm_units=='degrees_2theta' else 'Declared reflection-column layout; data type is shown only when verified.')
            rcell = result.cell
            from phase_studio.scientific_typography import scientific_text
            self.cell_value.setText(
                '<table cellspacing="0" cellpadding="0"><tr>'+''.join(
                    ('</tr><tr>' if index==3 else '')+'<td style="padding-right:10px">'+
                    scientific_text(text).replace(' ','&nbsp;')+'</td>' for index,text in enumerate((
                    f'a = {rcell.a:.5g} Å', f'b = {rcell.b:.5g} Å', f'c = {rcell.c:.5g} Å',
                    f'alpha = {rcell.alpha:.4g}°', f'beta = {rcell.beta:.4g}°', f'gamma = {rcell.gamma:.4g}°')))+
                '</tr></table>'
            )
            from phase_studio.hkl_diagnostics_ui import _spacegroup_display
            symbol, setting = _spacegroup_display(result.spacegroup.xhm())
            self.spacegroup_value.setText(symbol)
            self.spacegroup_value.setToolTip(setting)
            metadata = request.metadata
            composition = metadata.composition if metadata is not None and metadata.composition else "—"
            self.composition_value.setText(composition.translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")))
            self.validate_hkl_button.setEnabled(True)
            self.analyze_completeness_button.setEnabled(True)
            # These short hints need no application-wide rich-text wrapping.
            self.validate_hkl_button.setProperty("toolTip",
                "Check reflection data and input format."
            )
            self.analyze_completeness_button.setProperty("toolTip",
                "Show reflection completeness and intensity statistics."
            )

        def validate_hkl_clicked() -> None:
            try:
                self._get_backing_window().test_hkl_load_dialog()
            except Exception as exc:
                report = build_error_report(exc, subsystem="HKL", operation="HKL validation")
                show_phase_studio_error(self.dialog, report)

        def analyze_completeness_clicked() -> None:
            try:
                self._get_backing_window().open_hkl_completeness_dialog()
            except Exception as exc:
                report = build_error_report(exc, subsystem="HKL", operation="HKL completeness")
                show_phase_studio_error(self.dialog, report)

        self.validate_hkl_button.setEnabled(False)
        self.analyze_completeness_button.setEnabled(False)
        self.validate_hkl_button.clicked.connect(validate_hkl_clicked)
        self.analyze_completeness_button.clicked.connect(analyze_completeness_clicked)
        # Deferred so the wizard's first page paints immediately; the summary
        # (and the one-time backing-window construction it triggers) fills in
        # right after, once the dialog's event loop actually starts.
        summary_labels = (self.reflections_value, self.format_value, self.cell_value, self.spacegroup_value, self.composition_value)

        def pin_wrapped_summary_heights() -> None:
            # QFormLayout mis-distributes height between word-wrapped rows
            # (a two-line Cell value was given one line and cropped, while a
            # one-line row got the spare). Each wrapped value's minimum height
            # is its own heightForWidth at the width it actually has.
            for label in summary_labels:
                width = label.width() if label.width() > 1 else self.input_summary_fields.width()
                if width > 1:
                    label.setMinimumHeight(max(label.fontMetrics().height(), label.heightForWidth(width)))

        from PySide6.QtCore import QEvent as _QEvent, QObject as _QObject

        class _SummaryResizeWatcher(_QObject):
            def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt override
                if event.type() == _QEvent.Resize:
                    pin_wrapped_summary_heights()
                return False

        self._summary_resize_watcher = _SummaryResizeWatcher(self.input_summary_fields)
        self.input_summary_fields.installEventFilter(self._summary_resize_watcher)

        def refresh_input_summary_and_refit() -> None:
            from shiboken6 import isValid
            if not isValid(self.stack):
                return
            refresh_input_summary()
            pin_wrapped_summary_heights()
            # Before control returns to the event loop (so before anything is
            # painted): deliver the layout requests the new texts just posted,
            # so page 1's minimum is current, and re-pin the stack to it.
            if self.stack.currentWidget() is self.page1:
                from PySide6.QtCore import QCoreApplication, QEvent

                QCoreApplication.sendPostedEvents(None, QEvent.LayoutRequest)
                self._size_stack_to_current_page(self._preferred_dialog_width())
            # The populated summary is taller than the placeholder page the
            # dialog was first fitted to (two-line cell, reflection counts,
            # composition, "From .inflip" notes) -- re-fit, or the stack
            # stays pinned to the stale, shorter height.
            def refit() -> None:
                from shiboken6 import isValid
                if not isValid(self.stack):
                    return
                if self.stack.currentWidget() is self.page1:
                    self.page1_layout.activate()
                    self._adjust_dialog_size()

            # Next event-loop turn: the new label texts' size hints are only
            # propagated once Qt has processed the posted LayoutRequest.
            QTimer.singleShot(0, refit)

        QTimer.singleShot(0, refresh_input_summary_and_refit)

        self.files_section, self.files_body = build_page1_section("Reference and initial model")
        self.files_form_widget = QWidget()
        self.files_form = QFormLayout(self.files_form_widget)
        self.files_form.setContentsMargins(0, 0, 0, 0)
        self.files_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.files_form.setVerticalSpacing(4)
        self.files_body.addWidget(self.files_form_widget)

        def add_file_row(label_text: str, file_filter: str, tooltip: str, placeholder: str, initial: str):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(initial)
            from_inflip = bool(initial)
            edit.setPlaceholderText(placeholder)
            edit.setStyleSheet("QLineEdit { placeholder-text-color:#566b8c; }")
            edit.setToolTip(
                (tooltip + "\n\nCurrently set from the incoming .inflip.") if from_inflip else tooltip
            )
            browse = QPushButton("Browse…")
            browse.setObjectName("optionalFileBrowse")
            browse.setToolTip(f"Select {label_text.lower()}.")

            source_note = QLabel("From .inflip")
            source_note.setStyleSheet("color: #566b8c; font-style: italic;")
            source_note.setVisible(from_inflip)

            def browse_file() -> None:
                selected = QFileDialog.getOpenFileName(self.dialog, f"Select {label_text}", edit.text(), file_filter)[0]
                if selected:
                    edit.setText(selected)
                    # A manual replacement is no longer "from the .inflip".
                    source_note.setVisible(False)

            browse.clicked.connect(browse_file)
            edit.textChanged.connect(lambda value: edit.setToolTip(tooltip + ("\n\n" + value if value else "")))
            if initial:
                edit.setToolTip(tooltip + "\n\n" + initial)
            row_layout.addWidget(edit, 1)
            row_layout.addWidget(source_note)
            row_layout.addWidget(browse)
            self.files_form.addRow(label_text, row_widget)
            return edit

        def _inflip_keyword_default(keyword: str) -> str:
            # Deliberately not persisted across runs: these fields reflect what the
            # incoming Jana2020 .inflip already declares, not a remembered value from
            # an unrelated previous job.
            if self.inflip_path is None:
                return ""
            try:
                found = inflip_keyword_path(self.inflip_path, keyword)
            except Exception:
                return ""
            return str(found) if found is not None else ""

        self.reference_file = add_file_row(
            "Reference (optional)",
            # Same authoritative helper the main window uses, so no selector
            # carries its own extension list. Deliberately the narrower wrapper
            # set: the single-pass workflows validate the selection against
            # .cif/.xplor and reject anything else.
            supported_wrapper_reference_filters(),
            "Reference CIF structure or XPLOR density map, used together with the "
            "incoming Jana2020 .inflip without replacing its embedded reflections or metadata. "
            "When supplied, Superflip also reports how well each cycle matches this reference, "
            "which is used to recommend the best map for the Jana2020 handoff. Pre-filled from "
            "the incoming .inflip's own referencefile keyword, if it declares one.",
            "No external reference",
            _inflip_keyword_default("referencefile"),
        )
        self.model_file = add_file_row(
            "Initial model (optional)",
            supported_model_filters(),
            "Model or density map to seed the first Superflip cycle. If supplied, "
            "cycle 1 is model-seeded: repeatmode is forced to 1 and randomseed is omitted. "
            "Pre-filled from the incoming .inflip's own modelfile keyword, if it declares one.",
            "No first-cycle model",
            _inflip_keyword_default("modelfile"),
        )
        # These overrides are useful but optional for nearly every Jana run.
        # Keep their availability obvious while leaving enough vertical room
        # for all four workflows on the opening page at Full HD / 125%.
        # Expanding changes only the scroll area's contents; the Wizard's
        # stable outer geometry remains fixed.
        QStyle = self.qt["QStyle"]
        self.files_toggle = QPushButton("Advanced input options (optional)")
        self.files_toggle.setObjectName("compactDisclosureButton")
        self.files_toggle.setCheckable(True)
        self.files_toggle.setChecked(False)
        self.files_toggle.setIcon(self.dialog.style().standardIcon(QStyle.SP_ArrowRight))
        self.files_toggle.setCursor(Qt.PointingHandCursor)
        self.files_toggle.setToolTip("Optional reference structure and initial model.")
        self.files_toggle.setStyleSheet(
            "QPushButton#compactDisclosureButton { text-align:left; background:transparent; "
            "border:1px solid transparent; border-radius:4px; padding:3px 7px; color:#29456f; }"
            "QPushButton#compactDisclosureButton:hover { background:#f1f5fb; border-color:#d7e1ef; }"
            "QPushButton#compactDisclosureButton:checked { background:#edf3fb; border-color:#c7d6e9; }"
            "QPushButton#compactDisclosureButton:focus { border-color:#2264b8; }"
        )
        self.files_body.insertWidget(0, self.files_toggle)
        self.files_form_widget.setVisible(False)
        # In collapsed form the disclosure itself is the section heading.
        # Avoid spending another heading line and rule on the same words.
        for label in self.files_section.findChildren(QLabel):
            if label.text() == "REFERENCE AND INITIAL MODEL":
                label.setVisible(False)
        for separator in self.files_section.findChildren(QFrame):
            if separator.parentWidget() is self.files_section:
                separator.setVisible(False)
        files_body_widget = self.files_toggle.parentWidget()
        if files_body_widget is not None and files_body_widget.layout() is not None:
            files_body_widget.layout().setContentsMargins(0, 0, 0, 0)

        def toggle_optional_files(expanded: bool) -> None:
            self.files_form_widget.setVisible(expanded)
            self.files_toggle.setIcon(self.dialog.style().standardIcon(
                QStyle.SP_ArrowDown if expanded else QStyle.SP_ArrowRight
            ))
            self.page1_layout.invalidate()
            self.page1.updateGeometry()
            QTimer.singleShot(0, lambda: self._size_stack_to_current_page(self.dialog.width()))

        self.files_toggle.toggled.connect(toggle_optional_files)
        self.page1_layout.addWidget(self.files_section)

        class _WorkflowCard(QFrame):
            """A selectable workflow row: bold title, one description line, no
            execution on click -- selecting a workflow only updates which card is
            highlighted; the dialog's own "Run phasing" / "Next" action decides
            whether and when anything actually runs."""

            def __init__(self, key: str, title: str, description: str, on_click) -> None:
                super().__init__()
                self._key = key
                self._on_click = on_click
                self.setObjectName("workflowCard")
                self.setFrameShape(QFrame.NoFrame)
                self.setCursor(Qt.PointingHandCursor)
                # Selected/hover states are driven entirely by the "selected" dynamic
                # property + the shared QSS rules for QFrame#workflowCard (ui_style.py),
                # mirroring the statusBadge[runState=...] pattern used elsewhere in
                # Phase Studio, instead of swapping the whole stylesheet in Python.
                # WA_Hover is required for a plain QFrame to actually repaint on
                # mouse-enter/leave -- QAbstractButton gets this for free, QFrame does not.
                self.setAttribute(Qt.WA_Hover, True)
                layout = QVBoxLayout(self)
                layout.setContentsMargins(12, 8, 12, 8)
                layout.setSpacing(2)
                title_label = QLabel(title)
                title_font = title_label.font()
                title_font.setBold(True)
                title_label.setFont(title_font)
                desc_label = QLabel(description)
                desc_label.setWordWrap(True)
                desc_label.setObjectName("workflowCardDescription")
                layout.addWidget(title_label)
                layout.addWidget(desc_label)
                self.set_selected(False)

            def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
                super().mousePressEvent(event)
                self._on_click(self._key)

            def set_selected(self, selected: bool) -> None:
                self.setProperty("selected", bool(selected))
                self.style().unpolish(self)
                self.style().polish(self)

        class _ActionTile(QFrame):
            """A large, fully-clickable primary action tile (2.0.0): unlike
            _WorkflowCard, there is no separate select-then-confirm step --
            the entire tile IS the button. Clicking it (mouse press+release
            inside the tile), or giving it keyboard focus and pressing
            Enter/Return/Space, immediately performs the action. Hover and
            focus rely on Qt's own native :hover/:focus QSS pseudo-states
            (WA_Hover is enabled below, exactly like the existing
            _WorkflowCard); "pressed" has no native QFrame pseudo-state, so
            it is tracked as an explicit property the same way _WorkflowCard
            already tracks "selected"."""

            def __init__(
                self, title: str, subtitle: str, on_click, *, secondary: str = "",
                chevron: bool = True, icon_source: str = "", tier: str = "primary", runtime: str = "",
            ) -> None:
                super().__init__()
                self._on_click = on_click
                self.setObjectName("actionTile")
                self.setFrameShape(QFrame.NoFrame)
                self.setCursor(Qt.PointingHandCursor)
                self.setAttribute(Qt.WA_Hover, True)
                self.setFocusPolicy(Qt.StrongFocus)
                self.setProperty("pressed", False)
                self._last_activation = 0.0
                self.setAccessibleName(title)
                self.setAccessibleDescription(subtitle)
                self.setProperty("workflowTier", tier)
                self.setProperty("recommended", secondary == "Recommended")
                if icon_source.startswith("workflow_"):
                    self.setMinimumHeight(76 if tier == "primary" else 94)
                    # Recommendation is a label, not a permanent selection.
                    self.setStyleSheet(
                        'QFrame#actionTile[recommended="true"] { background:#f3f8ff; border-color:#8fa9cc; }'
                        'QFrame#actionTile[recommended="true"]:hover { background:#edf3fa; border-color:#2264b8; }'
                        'QFrame#actionTile[recommended="true"]:focus { background:#f5f9ff; border:2px solid #2264b8; }'
                        'QFrame#actionTile[pressed="true"]:enabled { background:#dceaf8; border:2px solid #14509a; }'
                        'QFrame#actionTile:disabled { background:#f1f3f6; border:1px solid #d7dce5; }'
                        'QFrame#actionTile QLabel:disabled { color:#8893a6; }'
                    )
                # Compact established icon, strong title, one explanatory
                # line, optional result line, right chevron. Every tile uses
                # the same TILE_* geometry, so tiles on one page line up
                # exactly. Heights come only from the labels' own font
                # metrics/size hints -- no fixed text heights anywhere.
                outer = QHBoxLayout(self)
                outer.setContentsMargins(TILE_PADDING_H, TILE_PADDING_V, TILE_PADDING_H, TILE_PADDING_V)
                outer.setSpacing(TILE_CHEVRON_GAP)
                self.icon_label = None
                if icon_source:
                    self.icon_label = QLabel()
                    self.icon_label.setObjectName("actionTileIcon")
                    workflow_icon = icon_source.startswith("workflow_")
                    apply_established_icon(self.icon_label, icon_source, size=32 if workflow_icon else TILE_ICON_SIZE)
                    self.icon_label.setFixedSize(40 if workflow_icon else TILE_ICON_SIZE,
                                                40 if workflow_icon else TILE_ICON_SIZE)
                    self.icon_label.setAlignment(Qt.AlignCenter)
                    outer.addWidget(self.icon_label, 0, Qt.AlignVCenter)
                    outer.addSpacing(TILE_ICON_GAP - TILE_CHEVRON_GAP)
                text_layout = QVBoxLayout()
                text_layout.setContentsMargins(0, 0, 0, 0)
                text_layout.setSpacing(TILE_TEXT_SPACING)
                self.title_label = QLabel(title)
                self.title_label.setObjectName("actionTileTitle")
                self.title_label.setWordWrap(True)
                # Titles can wrap on narrow displays. Paired secondary cards
                # reserve a common title band below to preserve baselines.
                self.subtitle_label = QLabel(subtitle)
                self.subtitle_label.setObjectName("actionTileSubtitle")
                self.subtitle_label.setWordWrap(True)
                self.subtitle_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                self.secondary_label = QLabel(secondary)
                self.secondary_label.setObjectName("actionTileSecondary")
                self.secondary_label.setWordWrap(False)
                self.secondary_label.setProperty("placeholder", not bool(secondary))
                self.title_row_widget = QWidget()
                self.title_row_widget.setStyleSheet("background: transparent;")
                title_row = QHBoxLayout(self.title_row_widget)
                self.title_row_layout = title_row
                title_row.setContentsMargins(0, 0, 0, 0)
                title_row.setSpacing(8)
                title_row.addWidget(self.title_label, 0, Qt.AlignTop)
                if secondary:
                    title_row.addWidget(self.secondary_label, 0, Qt.AlignTop)
                else:
                    self.secondary_label.hide()
                title_row.addStretch(1)
                text_layout.addWidget(self.title_row_widget)
                text_layout.addWidget(self.subtitle_label)
                self.runtime_label = QLabel(runtime)
                self.runtime_label.setObjectName("actionTileSecondary")
                self.runtime_label.setWordWrap(True)
                # Local contrast adjustment: other dialogs retain their styles.
                for label in (self.secondary_label, self.runtime_label):
                    if label.text():
                        label.setStyleSheet("color:#566b8c;")
                if runtime or tier == "secondary":
                    self.runtime_label.setMinimumHeight(self.runtime_label.fontMetrics().lineSpacing())
                    text_layout.addWidget(self.runtime_label)
                else:
                    self.runtime_label.hide()
                text_widget = QWidget()
                text_widget.setLayout(text_layout)
                text_widget.setStyleSheet("background: transparent;")
                self.text_widget = text_widget
                outer.addWidget(text_widget, 1, Qt.AlignVCenter)
                self.chevron_label = None
                if chevron:
                    self.chevron_label = QLabel("›")
                    self.chevron_label.setObjectName("actionTileChevron")
                    self.chevron_label.setStyleSheet("color:#566b8c;")
                    self.chevron_label.setAlignment(Qt.AlignCenter)
                    self.chevron_label.ensurePolished()
                    self.chevron_label.setFixedWidth(
                        max(TILE_CHEVRON_WIDTH, self.chevron_label.fontMetrics().horizontalAdvance("›") + 2)
                    )
                    outer.addWidget(self.chevron_label, 0, Qt.AlignVCenter)

            def _trigger(self, *, pointer: bool = False) -> None:
                # A double click / repeated key event must not dispatch twice.
                now = time.monotonic()
                if self.isEnabled() and (not pointer or now - self._last_activation >= 0.35):
                    if pointer:
                        self._last_activation = now
                    self._on_click()

            def resizeEvent(self, event) -> None:
                super().resizeEvent(event)
                if self.property("workflowTier") == "secondary":
                    # Both columns reserve the same title band when their
                    # adjacent status forces wrapping on a narrow display.
                    column_width = self.width()
                    compact = column_width < 300
                    self.title_row_layout.setDirection(QHBoxLayout.TopToBottom if compact else QHBoxLayout.LeftToRight)
                    lines = 3 if compact else (2 if column_width < 360 else 1)
                    self.title_row_widget.setMinimumHeight(lines * self.title_label.fontMetrics().lineSpacing() + (8 if compact else 0))

            def click(self) -> None:
                """QPushButton-compatible programmatic activation."""
                self._trigger()

            def _set_pressed(self, pressed: bool) -> None:
                self.setProperty("pressed", bool(pressed))
                self.style().unpolish(self)
                self.style().polish(self)

            def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
                super().mousePressEvent(event)
                self._set_pressed(True)

            def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
                super().mouseReleaseEvent(event)
                was_pressed = bool(self.property("pressed"))
                self._set_pressed(False)
                if was_pressed and self.rect().contains(event.pos()):
                    self._trigger(pointer=True)

            def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
                super().leaveEvent(event)
                self._set_pressed(False)

            def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
                if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                    if not event.isAutoRepeat():
                        self._trigger()
                    return
                super().keyPressEvent(event)

        # 2.0.0: exposed so the Autosolve decision page (built by a separate
        # method, after this one) can reuse the exact same tile class instead
        # of a second definition.
        self._ActionTile = _ActionTile

        def workflow_card_clicked(key: str) -> None:
            self.workflow_state["key"] = key
            self._workflow_changed()

        # 2.0.0: exposed so the Advanced page (built by a separate method,
        # after this one) can reuse the exact same card class/visual language
        # instead of a second definition. Page1's own two dominant actions no
        # longer use _WorkflowCard at all -- see _ActionTile above.
        self._WorkflowCard = _WorkflowCard
        self._workflow_card_clicked = workflow_card_clicked

        def original_superflip_tile_clicked() -> None:
            self.workflow_state["key"] = WORKFLOW_SUPERFLIP_ONLY
            self._workflow_changed()
            self._attempt_run()

        def autosolve_tile_clicked() -> None:
            self.workflow_state["key"] = WORKFLOW_AUTOSOLVE
            self._workflow_changed()
            self._attempt_run()

        def recommended_tile_clicked() -> None:
            self.workflow_state["key"] = WORKFLOW_SUPERFLIP_SHARPED
            self._workflow_changed()
            self._attempt_run()

        # Workflow is the single most important choice on this page (it decides
        # the whole execution path) and must not blend in as one more same-weight
        # section -- it gets the same lightweight sectionLabel heading as Input
        # summary / Reference and initial model above. Two dominant, fully
        # clickable primary workflow tiles. Professional mode remains a
        # visually subordinate expert action below them.
        self.workflow_section, self.workflow_body = build_page1_section("Workflow")
        self.workflow_body.setSpacing(6)
        self.primary_workflows_label = QLabel("PRIMARY WORKFLOWS")
        self.primary_workflows_label.setObjectName("workflowGroupLabel")
        self.primary_workflows_label.setStyleSheet("color:#566b8c;")
        self.workflow_body.addWidget(self.primary_workflows_label)
        self.original_superflip_tile = _ActionTile(
            WORKFLOW_LABELS[WORKFLOW_SUPERFLIP_ONLY],
            WORKFLOW_DESCRIPTIONS[WORKFLOW_SUPERFLIP_ONLY],
            original_superflip_tile_clicked,
            icon_source="workflow_superflip",
        )
        self.superflip_sharped_tile = _ActionTile(
            WORKFLOW_LABELS[WORKFLOW_SUPERFLIP_SHARPED],
            WORKFLOW_DESCRIPTIONS[WORKFLOW_SUPERFLIP_SHARPED],
            recommended_tile_clicked,
            secondary="Recommended",
            icon_source="workflow_sharped",
        )
        primary_subtitles = (self.original_superflip_tile.subtitle_label, self.superflip_sharped_tile.subtitle_label)
        for label in primary_subtitles:
            label.ensurePolished()
        primary_height = max(label.fontMetrics().lineSpacing() for label in primary_subtitles)
        for label in primary_subtitles:
            label.setMinimumHeight(primary_height)
        self.autosolve_tile = _ActionTile(
            WORKFLOW_LABELS[WORKFLOW_AUTOSOLVE],
            WORKFLOW_DESCRIPTIONS[WORKFLOW_AUTOSOLVE],
            autosolve_tile_clicked,
            secondary="Experimental",
            icon_source="workflow_autosolve",
            tier="secondary",
            runtime="Runtime depends on data and server load",
        )
        self.workflow_body.addWidget(self.original_superflip_tile)
        self.workflow_body.addWidget(self.superflip_sharped_tile)
        # Primary tiles act immediately or navigate to their dedicated setup.
        self.workflow_cards: dict[str, "_WorkflowCard"] = {}

        self.secondary_workflows_label = QLabel("SECONDARY WORKFLOWS")
        self.secondary_workflows_label.setObjectName("workflowGroupLabel")
        self.secondary_workflows_label.setStyleSheet("color:#566b8c;")
        self.workflow_body.addWidget(self.secondary_workflows_label)
        class _SecondaryActions(QWidget):
            def resizeEvent(self, event):
                super().resizeEvent(event)
                wizard.secondary_actions_row.setDirection(
                    QHBoxLayout.TopToBottom if event.size().width() < self.minimum_pair_width() else QHBoxLayout.LeftToRight
                )
                if event.size().width() != event.oldSize().width():
                    QTimer.singleShot(0, self.align_text)

            def minimum_pair_width(self):
                # Reserve a readable title/status band plus the established
                # icon, chevron, padding and gap, using the current UI font.
                tiles = (wizard.autosolve_tile, wizard.professional_mode_tile)
                card_width = max(
                    tile.title_label.fontMetrics().horizontalAdvance(tile.title_label.text())
                    + (tile.secondary_label.sizeHint().width() + tile.title_row_layout.spacing()
                       if tile.secondary_label.text() else 0)
                    + 2 * TILE_PADDING_H + tile.icon_label.width() + tile.chevron_label.width()
                    + 3 * TILE_CHEVRON_GAP + TILE_ICON_GAP - TILE_CHEVRON_GAP
                    + 4  # two-pixel focus border on both sides
                    for tile in tiles
                )
                return 2 * card_width + wizard.secondary_actions_row.spacing() + 1

            def align_text(self):
                from shiboken6 import isValid
                if not isValid(self):
                    return
                tiles = (wizard.autosolve_tile, wizard.professional_mode_tile)
                for tile in tiles:
                    tile.subtitle_label.setMinimumHeight(0)
                subtitle_height = max(
                    max(tile.subtitle_label.fontMetrics().lineSpacing(),
                        tile.subtitle_label.heightForWidth(max(1, tile.subtitle_label.width())))
                    for tile in tiles
                )
                for tile in tiles:
                    tile.subtitle_label.setMinimumHeight(subtitle_height)

        self.secondary_actions = _SecondaryActions()
        secondary_actions_row = QHBoxLayout(self.secondary_actions)
        self.secondary_actions_row = secondary_actions_row
        # One trailing logical pixel makes the two equal-stretch columns
        # divide exactly even when the available page width is odd.
        secondary_actions_row.setContentsMargins(0, 0, 1, 0)
        secondary_actions_row.setSpacing(8)
        self.professional_mode_button = _ActionTile(
            "Professional mode",
            "Advanced control of Superflip, SharpED and EDMA",
            lambda: self._attempt_edit(),
            icon_source="workflow_settings",
            tier="secondary",
        )
        self.professional_mode_tile = self.professional_mode_button
        # The horizontal layout already gives the pair equal height. Let each
        # wrapped subtitle report its natural size rather than reserving four
        # lines even when three are enough at the target width.
        self.professional_mode_tile.setToolTip(
            "Open the complete Phase Studio application with parameters imported from the "
            "Jana2020 .inflip file. Configure settings and press Run manually."
        )
        secondary_actions_row.addWidget(self.autosolve_tile, 1)
        secondary_actions_row.addWidget(self.professional_mode_tile, 1)
        self.workflow_body.addWidget(self.secondary_actions)

        self.page1_layout.addWidget(self.workflow_section)
        self.page1_layout.addStretch(1)
        self.stack.addWidget(self.page1)

    # ----- Page 2: SharpED / phase-recycling settings (workflows 2 and 3 only) -----
    def _build_page2(self) -> None:
        qt = self.qt
        QButtonGroup = qt["QButtonGroup"]
        QComboBox = qt["QComboBox"]
        QFormLayout = qt["QFormLayout"]
        QGroupBox = qt["QGroupBox"]
        QHBoxLayout = qt["QHBoxLayout"]
        QLabel = qt["QLabel"]
        QLineEdit = qt["QLineEdit"]
        QPushButton = qt["QPushButton"]
        QCheckBox = qt["QCheckBox"]
        QRadioButton = qt["QRadioButton"]
        QSettings = qt["QSettings"]
        QSizePolicy = qt["QSizePolicy"]
        QSpinBox = qt["QSpinBox"]
        QStyle = qt["QStyle"]
        QTimer = qt["QTimer"]
        QToolButton = qt["QToolButton"]
        Qt = qt["Qt"]
        QVBoxLayout = qt["QVBoxLayout"]
        QWidget = qt["QWidget"]

        self.page2 = QWidget()
        self.page2_layout = QVBoxLayout(self.page2)
        self.page2_layout.setContentsMargins(0, 0, 0, 0)
        self.page2_layout.setSpacing(5)
        self.processing_progress = QLabel('Choose workflow → <b>Configure processing</b> → Map feedback')
        self.processing_progress.setStyleSheet('color:#52658b;')
        self.page2_layout.addWidget(self.processing_progress)
        self.processing_heading = QLabel('PROCESSING CONFIGURATION')
        self.processing_heading.setStyleSheet('color:#2264b8; font-weight:600;')
        self.page2_layout.addWidget(self.processing_heading)

        self.map_group = QGroupBox("Map used for Jana2020 handoff")
        self.map_group_layout = QVBoxLayout(self.map_group)
        self.map_buttons = QButtonGroup(self.dialog)
        self.sharped_map_radio = QRadioButton("SharpED map")
        self.superflip_map_radio = QRadioButton("Superflip map")
        self.sharped_map_radio.setToolTip(
            "Open Result Selection on the SharpED results for the Jana2020 handoff. "
            "Each next cycle is initialized from the SharpED map."
        )
        self.superflip_map_radio.setToolTip(
            "Open Result Selection on the Superflip results for the Jana2020 handoff. "
            "Each next cycle is still initialized from the SharpED map."
        )
        self.map_buttons.addButton(self.sharped_map_radio)
        self.map_buttons.addButton(self.superflip_map_radio)
        self.map_group_layout.addWidget(self.sharped_map_radio)
        self.map_group_layout.addWidget(self.superflip_map_radio)
        saved_next_cycle = str(self.settings.value("next_cycle_modelfile", "deblurred_xplor")).strip().lower()
        if saved_next_cycle == "superflip_xplor":
            self.superflip_map_radio.setChecked(True)
        else:
            self.sharped_map_radio.setChecked(True)
        self.page2_layout.addWidget(self.map_group)

        self.processing_form = QFormLayout()
        self.processing_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.processing_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.processing_form.setVerticalSpacing(4)

        self.cycles = QSpinBox()
        self.cycles.setRange(1, 999)
        self.cycles.setFixedWidth(110)
        self.cycles.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.cycles.setValue(int(self.settings.value("cycles", 5)) or 5)
        self.cycles.setToolTip("Number of ordinary Superflip + SharpED workflow cycles.")
        self.cycles_row = QWidget()
        cycles_layout = QHBoxLayout(self.cycles_row)
        cycles_layout.setContentsMargins(0, 0, 0, 0)
        cycles_layout.setSpacing(12)
        self.cycles_recommendation = QLabel()
        self.cycles_recommendation.setObjectName("recommendationReason")
        self.cycles_recommendation.setStyleSheet("color: #52658b;")
        self.cycles_recommendation.setWordWrap(True)
        cycles_layout.addWidget(self.cycles)
        cycles_layout.addWidget(self.cycles_recommendation, 1)
        self.processing_form.addRow("Number of cycles", self.cycles_row)
        self.cycles_label = self.processing_form.labelForField(self.cycles_row)

        def update_cycle_guidance(value: int) -> None:
            self.cycles_recommendation.setText(
                "Each cycle processes a charge-flipping map with SharpED. Additional cycles "
                "increase processing time and may improve the iterative solution."
            )

        self.cycles.valueChanged.connect(update_cycle_guidance)
        update_cycle_guidance(self.cycles.value())

        self.cycles_user_edited = {"value": False}

        def mark_cycles_user_edited(_value: int = 0) -> None:
            self.cycles_user_edited["value"] = True

        self.cycles.valueChanged.connect(mark_cycles_user_edited)

        self.model = QComboBox()
        self.model.setEditable(False)
        self.model.setMaxVisibleItems(8)
        self.model.setMinimumWidth(340)
        self.model.setMaximumWidth(420)
        self.model.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        saved_model = str(self.settings.value("model", "default")).strip() or "default"
        saved_mode = str(self.settings.value("model_selection_mode", "")).strip().casefold()
        # Restore only an explicitly saved manual preference. The live
        # catalogue below verifies it; legacy model strings are not overrides.
        automatic_initially = saved_mode != "manual" or not saved_model
        initial_model = sharped_model_for_cycles(self.cycles.value()) if automatic_initially else saved_model
        self.model.addItem(initial_model)
        self.model.setMinimumContentsLength(24)
        self.model.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.model.setCurrentText(initial_model)
        self.model.setToolTip(
            "SharpED inference model. Select an exact model returned by the live server catalog. "
            "Automatic selection follows the Phase Studio cycle policy."
        )
        self.model_user_picked = {"value": not automatic_initially}
        self.model_row = QWidget()
        self.model_row_layout = QHBoxLayout(self.model_row)
        self.model_row_layout.setContentsMargins(0, 0, 0, 0)
        self.model_row_layout.setSpacing(8)
        self.model_row_layout.addWidget(self.model)
        self.processing_form.addRow("SharpED model", self.model_row)
        self.manual_model_row = QWidget()
        manual_model_layout = QHBoxLayout(self.manual_model_row)
        manual_model_layout.setContentsMargins(0, 0, 0, 0)
        self.manual_model_indicator = QLabel("Manually selected")
        self.manual_model_indicator.setObjectName("modelRecommendation")
        self.manual_model_indicator.setStyleSheet("color: #52658b;")
        self.restore_automatic_model_button = QPushButton("Restore automatic")
        self.restore_automatic_model_button.setFlat(True)
        self.restore_automatic_model_button.setObjectName("restoreAutomaticLink")
        self.restore_automatic_model_button.setFocusPolicy(Qt.StrongFocus)
        self.restore_automatic_model_button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.restore_automatic_model_button.setToolTip(
            "Use PEAK A (model prediction) for one cycle and SEED (cyclic CF) for two or more cycles."
        )
        manual_model_layout.addWidget(self.manual_model_indicator,1)
        manual_model_layout.addWidget(self.restore_automatic_model_button)
        self.model_recommendation = QLabel("")
        self.model_recommendation.setObjectName("modelRecommendation")
        self.model_recommendation.setStyleSheet("color: #52658b;")
        self.model_recommendation.setWordWrap(True)
        self.page2_layout.addLayout(self.processing_form)

        self.refresh_row = QWidget()
        self.refresh_layout = QHBoxLayout(self.refresh_row)
        self.refresh_layout.setContentsMargins(0, 0, 0, 0)
        self.refresh_layout.setSpacing(3)
        self.refresh_models_button = QPushButton("Refresh")
        self.refresh_models_button.setAccessibleName("Refresh models")
        self.refresh_models_button.setToolTip("Query the SharpED server for its currently available models.")
        self.model_status = QLabel("Loading models…")
        self.model_status.setObjectName("recommendationReason")
        self.model_status.setStyleSheet("color: #52658b;")
        self.model_status.setWordWrap(True)
        self.model_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.model_row_layout.addWidget(self.refresh_models_button)
        self.model_row_layout.addStretch(1)
        self.refresh_layout.addWidget(self.model_status, 1, Qt.AlignVCenter)
        self.model_state_row = QWidget()
        self.model_state_row.setMaximumWidth(560)
        state_layout = QHBoxLayout(self.model_state_row)
        state_layout.setContentsMargins(0,0,0,0)
        state_layout.setSpacing(8)
        self.manual_model_indicator.setWordWrap(True)
        state_layout.addWidget(self.manual_model_row,1)
        state_layout.addWidget(self.model_recommendation,1)
        self.refresh_row.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Preferred)
        state_layout.addWidget(self.refresh_row)
        self.processing_form.addRow("", self.model_state_row)

        self.connection_heading = QLabel('SHARPED CONNECTION')
        self.connection_heading.setStyleSheet('color:#2264b8; font-weight:600;')
        self.connection_heading.setWordWrap(True)
        self.page2_layout.addWidget(self.connection_heading)
        self.connection_row = QWidget()
        connection_layout = QHBoxLayout(self.connection_row)
        connection_layout.setContentsMargins(0,0,0,0)
        connection_layout.addWidget(QLabel("SharpED account"))
        self.connection_status = QLabel('SharpED account access')
        self.connection_status.setWordWrap(True)
        self.connection_status.setStyleSheet('color:#52658b;')
        self.connection_status.setToolTip('Model discovery is public and does not verify account access. Authentication is checked by the existing sign-in and workflow preflight.')
        connection_layout.addWidget(self.connection_status,1)
        self.page2_layout.addWidget(self.connection_row)

        self.sharped_group = QWidget()
        self.sharped_outer = QVBoxLayout(self.sharped_group)
        self.sharped_outer.setContentsMargins(0, 0, 0, 0)
        self.sharped_outer.setSpacing(4)
        self.sharped_toggle = QToolButton()
        self.sharped_toggle.setObjectName("disclosureToggle")
        self.sharped_toggle.setText("Advanced SharpED settings")
        self.sharped_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.sharped_toggle.setArrowType(Qt.RightArrow)
        self.sharped_toggle.setCheckable(True)
        self.sharped_toggle.setChecked(False)
        self.sharped_toggle.setToolTip("Expand or collapse the SharpED server connection settings.")
        self.sharped_outer.addWidget(self.sharped_toggle)
        self.sharped_body = QWidget()
        self.sharped_form = QFormLayout(self.sharped_body)
        self.sharped_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.sharped_form.setContentsMargins(18, 4, 0, 0)

        # Normal Wizard workflows use the one authoritative SharpED service.
        # The hidden object preserves compatibility with code that reads the
        # value, without exposing an endpoint editor to normal users.
        self.server_url = QLineEdit(DEFAULT_SERVER_URL)
        self.server_url.setPlaceholderText(DEFAULT_SERVER_URL)
        self.server_url.setReadOnly(True)
        self.server_url.setVisible(False)

        self.api_token = QLineEdit(
            self._shared_or_legacy_value("sharped_api_token", "api_token", os.environ.get("SHARPED_API_TOKEN", ""))
        )
        self.api_token.setEchoMode(QLineEdit.Password)
        credential_store.bind_input(self.api_token)
        self.api_token.setPlaceholderText("Paste your access key here")
        self.api_token.setMaximumWidth(340)
        self.api_token.setToolTip(
            "Private access key for your Jana2020 account. It is masked and shared with "
            "Phase Studio for this session. Remember access saves it in Windows Credential Manager."
        )
        self.sharped_form.addRow("SharpED access key", self.api_token)
        self.sharped_account_button = QPushButton("Manage account…")
        self.sharped_account_button.setAccessibleName("Manage SharpED account")
        self.sharped_account_button.setMaximumWidth(180)
        self.sharped_account_button.clicked.connect(self._manage_sharped_access)
        connection_layout.addWidget(self.sharped_account_button)
        def update_account_presentation(_text=None):
            # A stored key alone does not establish an authenticated session.
            from phase_studio.sharped_access import connection_status
            self.connection_status.setText('Credentials available — not yet verified'
                if self.api_token.text() and self.api_token.text()!=credential_store.get(DEFAULT_SERVER_URL)
                else connection_status(credential_store,DEFAULT_SERVER_URL))
        self._update_account_presentation = update_account_presentation
        self.api_token.textChanged.connect(update_account_presentation)
        update_account_presentation()

        # Elements and Output resolution are deliberately not exposed here: they
        # are shared with the full Phase Studio application's own Advanced ->
        # SharpED values (auto-detected from composition there), the same way
        # Server URL / API token are shared above -- see effective_elements()/
        # effective_outres() below.
        self.sharped_outer.addWidget(self.sharped_body)
        self.sharped_body.setVisible(False)

        def sync_sharped_disclosure(opened: bool) -> None:
            self.sharped_body.setVisible(bool(opened))
            self.sharped_toggle.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)
            self._size_stack_to_current_page(self.dialog.width())

        self.sharped_toggle.toggled.connect(sync_sharped_disclosure)
        self.advanced_heading = QLabel("ADVANCED SETTINGS AND SCIENTIFIC VALIDATION")
        self.advanced_heading.setStyleSheet('color:#2264b8; font-weight:600;')
        self.advanced_heading.setWordWrap(True)
        self.page2_layout.addWidget(self.advanced_heading)
        self.page2_layout.addWidget(self.sharped_group)

        self.refresh_results: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.refresh_timer = QTimer(self.dialog)
        self.refresh_timer.setInterval(100)
        # One successful list is reused for the Wizard session.
        self.model_cache = {"loaded": False, "inflight": False, "key": None}

        self.model_catalog = {"values": tuple()}
        self.missing_manual_model = ''
        self.model_policy_error = ""

        def update_model_recommendation(_value: int = 0) -> None:
            self.manual_model_row.setVisible(self.model_user_picked["value"])
            one_cycle = self.cycles.value() == 1
            recommended = sharped_model_for_cycles(self.cycles.value())
            manual = self.model_user_picked["value"]
            self.model_recommendation.setVisible(not manual)
            self.manual_model_indicator.setText(
                "Manually selected · Matches recommended model"
                if manual and self.model.currentText() == recommended else "Manually selected · Different from recommendation"
            )
            self.model_recommendation.setText(
                f"Automatically selected for {self.cycles.value()} "
                f"{'cycle' if one_cycle else 'cycles'}"
            )
            self.model_policy_error = ""
            if manual and self.model.currentIndex()<0 and self.model_cache['loaded']:
                self.model_policy_error = 'The selected model is no longer available. Select another model or Restore automatic.'
                self.model_status.setText(self.model_policy_error)
                self.model_status.setToolTip(self.missing_manual_model)
            if not self.model_user_picked["value"]:
                index = self.model.findText(recommended)
                if index >= 0:
                    self.model.setCurrentIndex(index)
                elif self.model_cache["loaded"]:
                    self.model.setCurrentIndex(-1)
                    self.model_policy_error = f"Required automatic model is unavailable: {recommended}."
                    self.model_status.setText(self.model_policy_error)
            if self.model_cache.get('last_error'):
                self.model_policy_error = 'The live SharpED model catalogue is unavailable. Use Refresh models to retry.'
            elif self.model_cache['loaded'] and not self.model_policy_error:
                count = len(self.model_catalog['values'])
                self.model_status.setText(f"{count} {'model' if count==1 else 'models'} available")
                self.model_status.setToolTip('Public model catalogue; account authentication is checked separately.')

        def restore_automatic_model() -> None:
            self.model_user_picked["value"] = False
            update_model_recommendation()

        def mark_model_user_picked(_index: int = 0) -> None:
            self.model_user_picked["value"] = True
            update_model_recommendation()

        self.cycles.valueChanged.connect(update_model_recommendation)
        self.model.activated.connect(mark_model_user_picked)
        self.restore_automatic_model_button.clicked.connect(restore_automatic_model)
        update_model_recommendation()

        def model_request_key() -> tuple:
            return (DEFAULT_SERVER_URL, self.api_token.text().strip())

        def refresh_available_models(manual: bool = True) -> None:
            base_url = DEFAULT_SERVER_URL
            if self.model_cache["inflight"]:
                return
            self.model_cache["inflight"] = True
            self.model_cache["key"] = model_request_key()
            self.refresh_models_button.setEnabled(False)
            self.model_status.setText("Refreshing models…")

            def worker() -> None:
                try:
                    client = SharpEDServerClient(base_url=base_url, timeout=30.0)
                    models_result = client.get_models()
                    self.refresh_results.put(("ok", models_result))
                except Exception as exc:
                    self.refresh_results.put(("error", str(exc)))

            threading.Thread(target=worker, daemon=True).start()
            if not self.refresh_timer.isActive():
                self.refresh_timer.start()

        def poll_model_refresh() -> None:
            try:
                state, payload = self.refresh_results.get_nowait()
            except queue.Empty:
                return

            self.refresh_timer.stop()
            self.refresh_models_button.setEnabled(True)
            self.model_cache["inflight"] = False
            if state == "error":
                self.model_cache['last_error'] = True
                report = build_error_report(
                    payload, subsystem="SharpED", operation="Load model catalog",
                )
                self.model_policy_error = "The live SharpED model catalogue is unavailable. Use Refresh models to retry."
                self.model_status.setText(f"Cached: {len(self.model_catalog['values'])} models · Live catalogue unavailable"
                                          if self.model_cache['loaded'] else "Model list unavailable — Refresh to retry")
                self.model_status.setToolTip(
                    ('Previously loaded entries have not been reverified.\n\n' if self.model_cache['loaded'] else '') +
                    f"{report.summary}\n\n{report.guidance}\n\n{report.technical_details}"
                )
                return

            models_result = payload
            self.model_cache['last_error'] = False
            current = self.model.currentText().strip() or self.missing_manual_model
            default_model = str(getattr(models_result, "default_model", "") or "").strip()
            values = []
            for candidate in list(getattr(models_result, "models", []) or []):
                exact = str(candidate or "").strip()
                if exact and exact not in values:
                    values.append(exact)
            manual_was_removed = self.model_user_picked["value"] and current not in values
            self.missing_manual_model = current if manual_was_removed else ''
            self.model.blockSignals(True)
            self.model.clear()
            self.model.addItems(values)
            if manual_was_removed:
                self.model.setCurrentIndex(-1)
            if current in values and not manual_was_removed:
                self.model.setCurrentText(current)
            self.model.blockSignals(False)
            self.model_catalog["values"] = tuple(values)
            self._sharped_server_default = default_model
            self.model_cache["loaded"] = True
            update_model_recommendation()
            self._fit_model_popup_width()
            model_count = len(values)
            noun = "model" if model_count == 1 else "models"
            if self.model_policy_error:
                self.model_status.setText(self.model_policy_error)
            else:
                self.model_status.setText(f"{model_count} {noun} available")
                self.model_status.setToolTip('Public model catalogue; account authentication is checked separately.')

        self.refresh_models_button.clicked.connect(lambda _checked=False: refresh_available_models(manual=True))
        self.refresh_timer.timeout.connect(poll_model_refresh)

        def ensure_models_loaded() -> None:
            """Fetch the SharpED model list once, before the user picks a model.

            Only for workflows that actually run SharpED -- "Superflip only"
            never contacts the server. Asynchronous (the existing worker thread
            and poll timer), so the Wizard never freezes, and cached for the
            session: a repeat call after a successful load, or while a request
            is already in flight, does nothing.
            """
            if self._current_workflow() == WORKFLOW_SUPERFLIP_ONLY:
                return
            if self.model_cache["inflight"]:
                return
            if self.model_cache["loaded"] and self.model_cache["key"] == model_request_key():
                return
            refresh_available_models(manual=False)

        self._ensure_models_loaded = ensure_models_loaded

        self.validation_group = qt["QFrame"]()
        self.validation_group.setObjectName("configurationValidation")
        self.validation_layout = QHBoxLayout(self.validation_group)
        self.validation_layout.setContentsMargins(8, 4, 8, 4)
        self.validation_layout.setSpacing(8)
        self.warning_icon = QLabel()
        self.warning_icon.setPixmap(self.dialog.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(20, 20))
        self.warning_icon.setAlignment(Qt.AlignTop)
        self.validation_layout.addWidget(self.warning_icon, 0, Qt.AlignTop)
        validation_body = QVBoxLayout()
        validation_body.setSpacing(2)
        self.validation_heading = QLabel("Scientific validation")
        self.validation_heading.setObjectName("configurationValidationHeading")
        validation_body.addWidget(self.validation_heading)
        self.warning_text = QLabel(
            "SharpED predictions may contain artifacts. Validate the selected result against "
            "original measured diffraction data and independent crystallographic refinement."
        )
        self.warning_text.setWordWrap(True)
        validation_body.addWidget(self.warning_text)
        self.validation_layout.addLayout(validation_body, 1)
        self.page2_layout.addWidget(self.validation_group)

        # Phase recycling only: maps directly onto the existing full-pipeline
        # compute_omit_maps / compute_omit_rfree settings (see build_jana_handoff_import).
        # Not shown for either single-pass workflow, which never reaches that pipeline.
        self.cross_validation_group = QGroupBox("Cross-validation")
        self.cross_validation_layout = QVBoxLayout(self.cross_validation_group)
        self.omit_checkbox = QCheckBox("Compute OMIT validation maps")
        self.omit_checkbox.setToolTip(
            "Freeze a symmetry/Friedel-orbit-safe 5% reflection holdout before the workflow "
            "and exclude it from every work-data and feedback step. Enables cross-validation "
            "metrics and profile-aware result recommendation. Roughly doubles Superflip/SharpED "
            "time per cycle."
        )
        self.rfree_checkbox = QCheckBox("Calculate R_free")
        self.rfree_checkbox.setToolTip(
            "Calculated automatically with the holdout: the crystallographic R-factor between the excluded "
            "reflections' observed |F| and |F| calculated by FFT from the omit map) for each "
            "cycle. The result selector uses the active profile's explicit lexicographic "
            "criteria, without a combined numeric score. Requires "
            "'Compute OMIT validation maps'."
        )
        self.cross_validation_layout.addWidget(self.omit_checkbox)
        self.cross_validation_layout.addWidget(self.rfree_checkbox)
        self.cross_validation_help = QLabel(
            "Optional. Excludes a random 5% of reflections each cycle to compute OMIT / R_free "
            "validation metrics, which help rank the recycling cycles and select the most "
            "suitable map."
        )
        self.cross_validation_help.setWordWrap(True)
        self.cross_validation_help.setStyleSheet("color: #52658b;")
        self.cross_validation_layout.addWidget(self.cross_validation_help)
        self.page2_layout.addWidget(self.cross_validation_group)

        # Deliberately not persisted/restored from QSettings: cross-validation is
        # an expensive, per-job opt-in and must not be silently inherited from an
        # unrelated previous Jana2020 job. Every fresh invocation starts unchecked.

        def sync_rfree_dependency(_checked: bool = False) -> None:
            omit_enabled = self.omit_checkbox.isChecked()
            self.rfree_checkbox.setChecked(omit_enabled)
            self.rfree_checkbox.setEnabled(False)

        self.omit_checkbox.toggled.connect(sync_rfree_dependency)
        sync_rfree_dependency()

        self.page2_layout.addStretch(1)
        self.stack.addWidget(self.page2)


        self.sharped_map_radio.toggled.connect(lambda _checked=False: self._sync_map_choice())
        self._sync_map_choice()

    # ----- Page 3: Map feedback (Phase recycling only) -- exposes and
    # populates the existing Basic -> Map feedback controls/RunConfig
    # fields (see build_jana_handoff_import); no new map-feedback algorithm
    # is implemented here. Not added to Superflip only or Superflip +
    # SharpED, which never reach this page. -----
    def _build_page3(self) -> None:
        qt = self.qt
        QDoubleSpinBox = qt["QDoubleSpinBox"]
        QFormLayout = qt["QFormLayout"]
        QGroupBox = qt["QGroupBox"]
        QHBoxLayout = qt["QHBoxLayout"]
        QLabel = qt["QLabel"]
        QCheckBox = qt["QCheckBox"]
        QSpinBox = qt["QSpinBox"]
        QStyle = qt["QStyle"]
        Qt = qt["Qt"]
        QVBoxLayout = qt["QVBoxLayout"]
        QWidget = qt["QWidget"]

        self.page3 = QWidget()
        self.page3_layout = QVBoxLayout(self.page3)
        self.page3_layout.setContentsMargins(0, 0, 0, 0)
        self.page3_layout.setSpacing(5)

        self.reflection_data_group = QWidget()
        self.reflection_data_form = QFormLayout(self.reflection_data_group)
        self.reflection_data_form.setContentsMargins(0, 0, 0, 0)
        self.reflection_data_form.setVerticalSpacing(2)
        self.reflection_data_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.reflection_type_value = QLabel("")
        self.reflection_format_value = QLabel("")
        self.reflection_data_form.addRow("Reflection type", self.reflection_type_value)
        self.reflection_data_form.addRow("Input format", self.reflection_format_value)
        self.page3_layout.addWidget(self.reflection_data_group)

        self.page3_description = QLabel("")
        self.page3_description.setWordWrap(True)
        self.page3_description.setStyleSheet("color: #52658b;")
        self.page3_layout.addWidget(self.page3_description)
        self.feedback_applicability_note = QLabel(
            "Map Feedback requires at least 2 cycles."
        )
        self.feedback_applicability_note.setObjectName("recommendationReason")
        self.feedback_applicability_note.setWordWrap(True)
        self.feedback_applicability_note.setVisible(False)
        self.page3_layout.addWidget(self.feedback_applicability_note)

        # One compact state-dependent callout; source measurements stay immutable.
        self.map_feedback_warning_group = qt["QFrame"]()
        self.map_feedback_warning_group.setObjectName("mapFeedbackWarning")
        self.map_feedback_warning_group.setStyleSheet("QFrame#mapFeedbackWarning { margin: 0; padding: 0; border: 1px solid #dce5f2; }")
        self.map_feedback_warning_layout = QHBoxLayout(self.map_feedback_warning_group)
        self.map_feedback_warning_layout.setContentsMargins(10, 7, 10, 7)
        self.map_feedback_warning_layout.setSpacing(8)
        self.map_feedback_warning_icon = QLabel()
        self.map_feedback_warning_icon.setPixmap(self.dialog.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(20, 20))
        self.map_feedback_warning_icon.setAlignment(Qt.AlignTop)
        self.map_feedback_warning_layout.addWidget(self.map_feedback_warning_icon, 0, Qt.AlignTop)
        self.map_feedback_warning_text = QLabel(
            "<b>Scientific warning</b><br>"
            "Map Feedback modifies reflection data supplied to subsequent cycles. "
            "Validate results against the original measured data."
        )
        self.map_feedback_warning_text.setTextFormat(Qt.RichText)
        self.map_feedback_warning_text.setWordWrap(True)
        self.map_feedback_warning_layout.addWidget(self.map_feedback_warning_text, 1)
        self.page3_layout.addWidget(self.map_feedback_warning_group)
        self.feedback_cycle_summary = QLabel("")
        self.feedback_cycle_summary.setWordWrap(True)
        self.page3_layout.addWidget(self.feedback_cycle_summary)

        # --- Single-crystal branch: Missing-reflection completion + Intensity
        # correction, exactly Basic -> Map feedback's own controls/defaults/
        # ranges/tooltips. ---
        self.missing_group = QGroupBox("Missing-reflection completion")
        self.missing_outer = QVBoxLayout(self.missing_group)
        self.missing_outer.setSpacing(4)
        self.missing_enabled_checkbox = QCheckBox("Enable missing-reflection completion")
        self.missing_outer.addWidget(self.missing_enabled_checkbox)
        self.missing_form = QFormLayout()
        self.missing_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        self.missing_form.setVerticalSpacing(3)
        self.missing_start_cycle_spin = QSpinBox()
        self.missing_start_cycle_spin.setRange(1, 999)
        self.missing_start_cycle_spin.setValue(1)
        self.missing_start_cycle_spin.setToolTip(
            "First completed cycle whose map is used to add missing reflections for the next cycle."
        )
        self.missing_form.addRow("Start after cycle", self.missing_start_cycle_spin)
        self.missing_percent_spin = QDoubleSpinBox()
        self.missing_percent_spin.setRange(0.0, 100.0)
        self.missing_percent_spin.setSingleStep(1.0)
        self.missing_percent_spin.setDecimals(3)
        self.missing_percent_spin.setValue(0.0)
        self.missing_percent_spin.setToolTip(
            "Caps generated missing reflections as a percent of the current reflection count, "
            "preventing feedback from overwhelming measured data."
        )
        self.missing_form.addRow("Maximum added reflections (%)", self.missing_percent_spin)
        self.missing_parameters = QWidget()
        self.missing_parameters.setLayout(self.missing_form)
        self.missing_outer.addWidget(self.missing_parameters)
        self.missing_outer.addStretch(1)

        self.intensity_group = QGroupBox("Weak-reflection intensity correction")
        self.intensity_outer = QVBoxLayout(self.intensity_group)
        self.intensity_outer.setSpacing(4)
        self.intensity_enabled_checkbox = QCheckBox("Enable weak-reflection intensity correction")
        self.intensity_outer.addWidget(self.intensity_enabled_checkbox)
        self.intensity_form = QFormLayout()
        self.intensity_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        self.intensity_form.setVerticalSpacing(3)
        self.intensity_start_cycle_spin = QSpinBox()
        self.intensity_start_cycle_spin.setRange(1, 999)
        self.intensity_start_cycle_spin.setValue(1)
        self.intensity_start_cycle_spin.setToolTip(
            "First completed cycle whose map is used to damp observed intensities for the next cycle."
        )
        self.intensity_form.addRow("Start after cycle", self.intensity_start_cycle_spin)
        self.intensity_damping_spin = QDoubleSpinBox()
        self.intensity_damping_spin.setRange(0.0, 1.0)
        self.intensity_damping_spin.setSingleStep(0.05)
        self.intensity_damping_spin.setDecimals(3)
        self.intensity_damping_spin.setValue(0.0)
        self.intensity_damping_spin.setToolTip(
            "Damping factor for map-based intensity correction. 0 keeps observed data; "
            "1 replaces them by scaled map-derived intensities."
        )
        self.intensity_form.addRow("Correction damping", self.intensity_damping_spin)
        self.intensity_sigma_spin = QDoubleSpinBox()
        self.intensity_sigma_spin.setRange(0.0, 1000.0)
        self.intensity_sigma_spin.setSingleStep(0.5)
        self.intensity_sigma_spin.setDecimals(3)
        self.intensity_sigma_spin.setValue(0.0)
        self.intensity_sigma_spin.setSpecialValueText("All map-supported")
        self.intensity_sigma_spin.setToolTip(
            "Positive limits filter using the supplied value uncertainty. Threshold 0 bypasses "
            "that filter and corrects every reflection with a positive map prediction; σ is not required."
        )
        self.intensity_form.addRow("Significance limit", self.intensity_sigma_spin)
        self.intensity_parameters = QWidget()
        self.intensity_parameters.setLayout(self.intensity_form)
        self.intensity_outer.addWidget(self.intensity_parameters)
        self.intensity_note = QLabel("Threshold 0 applies to all map-supported reflections without uncertainty filtering.")
        self.intensity_note.setWordWrap(True)
        self.intensity_note.setStyleSheet("color: #52658b;")
        self.intensity_outer.addWidget(self.intensity_note)
        self.intensity_effective_note = QLabel("")
        self.intensity_effective_note.setWordWrap(True)
        self.intensity_effective_note.setStyleSheet("color: #52658b;")
        self.intensity_outer.addWidget(self.intensity_effective_note)

        # --- Powder/FWHM branch: Powder overlap repartitioning, exactly Basic ->
        # Map feedback's own controls/defaults/ranges/tooltips. ---
        self.powder_group = QGroupBox("Powder overlap repartitioning")
        self.powder_outer = QVBoxLayout(self.powder_group)
        self.powder_outer.setSpacing(4)
        self.powder_enabled_checkbox = QCheckBox("Enable powder overlap repartitioning (FWHM data)")
        self.powder_outer.addWidget(self.powder_enabled_checkbox)
        self.powder_form = QFormLayout()
        self.powder_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        self.powder_form.setVerticalSpacing(3)
        self.powder_start_cycle_spin = QSpinBox()
        self.powder_start_cycle_spin.setRange(1, 999)
        self.powder_start_cycle_spin.setValue(1)
        self.powder_start_cycle_spin.setToolTip(
            "First completed cycle whose map is used to redistribute overlapping reflections for the next cycle."
        )
        self.powder_form.addRow("Start after cycle", self.powder_start_cycle_spin)
        self.powder_wavelength_spin = QDoubleSpinBox()
        self.powder_wavelength_spin.setRange(0.0, 10.0)
        self.powder_wavelength_spin.setSingleStep(0.01)
        self.powder_wavelength_spin.setDecimals(8)
        self.powder_wavelength_spin.setValue(0.0)
        self.powder_wavelength_spin.setSpecialValueText("Automatic")
        self.powder_wavelength_spin.setToolTip(
            "Required to compute 2θ. Zero requests automatic detection from this project's matching "
            "Jana2020 .m90, then .inflip, then reference CIF. Enter a positive value if none is available."
        )
        self.powder_form.addRow("Wavelength (Å)", self.powder_wavelength_spin)
        self.powder_separation_spin = QDoubleSpinBox()
        self.powder_separation_spin.setRange(0.001, 100.0)
        self.powder_separation_spin.setSingleStep(0.05)
        self.powder_separation_spin.setDecimals(3)
        self.powder_separation_spin.setValue(0.2)
        self.powder_separation_spin.setToolTip(
            "Overlap threshold as a fraction of the mean FWHM of two neighboring reflections "
            "(Superflip's own fwhmseparation convention)."
        )
        self.powder_form.addRow("Separation factor", self.powder_separation_spin)
        self.powder_mix_spin = QDoubleSpinBox()
        self.powder_mix_spin.setRange(0.0, 1.0)
        self.powder_mix_spin.setSingleStep(0.05)
        self.powder_mix_spin.setDecimals(3)
        self.powder_mix_spin.setValue(1.0)
        self.powder_mix_spin.setToolTip(
            "0 keeps the observed intensity split within each overlap group; 1 uses the "
            "map-derived split fully. The group total is always conserved."
        )
        self.powder_form.addRow("Map ratio mix", self.powder_mix_spin)
        self.powder_parameters = QWidget()
        self.powder_parameters.setLayout(self.powder_form)
        self.powder_outer.addWidget(self.powder_parameters)
        self.powder_wavelength_status = QLabel("")
        self.powder_wavelength_status.setWordWrap(True)
        self.powder_wavelength_status.setStyleSheet("color: #52658b;")
        self.powder_outer.addWidget(self.powder_wavelength_status)
        self.powder_note = QLabel(
            "FWHM: peak width in degrees 2θ, not σ(I). Automatic wavelength uses verified project metadata; "
            "enter a measured wavelength if none is available."
        )
        self.powder_note.setWordWrap(True)
        self.powder_note.setStyleSheet("color: #52658b;")
        self.powder_outer.addWidget(self.powder_note)
        class _FeedbackPanels(QWidget):
            def resizeEvent(self, event):
                super().resizeEvent(event)
                self.layout().setDirection(QHBoxLayout.TopToBottom if event.size().width() < 820 else QHBoxLayout.LeftToRight)

        self.feedback_panels = _FeedbackPanels()
        self.feedback_panels_layout = QHBoxLayout(self.feedback_panels)
        self.feedback_panels_layout.setContentsMargins(0, 0, 0, 0)
        self.feedback_panels_layout.setSpacing(8)
        self.feedback_panels_layout.addWidget(self.missing_group, 1)
        self.feedback_panels_layout.addWidget(self.powder_group, 1)
        self.feedback_panels_layout.addWidget(self.intensity_group, 1)
        self.intensity_outer.addStretch(1)
        self.powder_outer.addStretch(1)
        self.page3_layout.addWidget(self.feedback_panels)

        for editor in (
            self.missing_start_cycle_spin, self.missing_percent_spin,
            self.intensity_start_cycle_spin, self.intensity_damping_spin,
            self.intensity_sigma_spin, self.powder_start_cycle_spin,
            self.powder_wavelength_spin, self.powder_separation_spin,
            self.powder_mix_spin,
        ):
            editor.setMaximumWidth(180)

        self.page3_validation_label = QLabel("")
        self.page3_validation_label.setWordWrap(True)
        self.page3_validation_label.setObjectName("wizardValidationMessage")
        self.page3_validation_label.setStyleSheet("color: #b42318;")
        self.page3_validation_label.setVisible(False)
        self.page3_layout.addWidget(self.page3_validation_label)

        # Keep the final scientific field visibly separated from the fixed
        # Wizard footer; the page's existing scroll area handles short screens.
        self.page3_layout.addSpacing(4)
        self.page3_layout.addStretch(1)
        self.stack.addWidget(self.page3)

        # Every fresh Wizard invocation starts every Map feedback checkbox OFF --
        # deliberately NOT restored from QSettings (same reasoning as the Cross-
        # validation checkboxes on page2: this is job-specific state, not
        # something that should silently carry over from an unrelated previous
        # Jana2020 job). The default-off state above already satisfies this; no
        # settings.value(...) read is ever wired to these controls.

        def sync_missing_dependency(_checked: bool = False) -> None:
            enabled = self.cycles.value() > 1 and self.missing_enabled_checkbox.isChecked()
            self.missing_parameters.setVisible(enabled)
            self.missing_start_cycle_spin.setEnabled(enabled)
            self.missing_percent_spin.setEnabled(enabled)
            label = self.missing_form.labelForField(self.missing_percent_spin)
            label.setText('Maximum added reflections (%)' + (' · No additions at 0%' if enabled and self.missing_percent_spin.value()==0 else ''))

        self.missing_enabled_checkbox.toggled.connect(sync_missing_dependency)
        self.missing_percent_spin.valueChanged.connect(sync_missing_dependency)
        sync_missing_dependency()

        def sync_intensity_dependency(_checked: bool = False) -> None:
            enabled = self.cycles.value() > 1 and self.intensity_enabled_checkbox.isChecked()
            self.intensity_parameters.setVisible(enabled)
            self.intensity_start_cycle_spin.setEnabled(enabled)
            self.intensity_damping_spin.setEnabled(enabled)
            has_sigma = getattr(self, "feedback_has_uncertainty", False)
            self.intensity_sigma_spin.setEnabled(enabled and has_sigma)
            self.intensity_sigma_spin.setVisible(has_sigma)
            self.intensity_form.labelForField(self.intensity_sigma_spin).setVisible(has_sigma)
            inactive = enabled and self.intensity_damping_spin.value() == 0
            self.intensity_effective_note.setText("No intensity correction: damping is 0; observed values are retained." if inactive else
                "Intensity correction will use the configured positive damping." if enabled else "")
            self.intensity_effective_note.setVisible(enabled)

        self.intensity_enabled_checkbox.toggled.connect(sync_intensity_dependency)
        self.intensity_damping_spin.valueChanged.connect(sync_intensity_dependency)
        sync_intensity_dependency()

        def sync_powder_dependency(_checked: bool = False) -> None:
            enabled = self.cycles.value() > 1 and self.powder_enabled_checkbox.isChecked()
            self.powder_parameters.setVisible(enabled)
            self.powder_start_cycle_spin.setEnabled(enabled)
            self.powder_wavelength_spin.setEnabled(enabled)
            self.powder_separation_spin.setEnabled(enabled)
            self.powder_mix_spin.setEnabled(enabled)
            self.powder_form.labelForField(self.powder_mix_spin).setText('Map ratio mix' +
                (' · No repartitioning at 0' if enabled and self.powder_mix_spin.value()==0 else ''))
            if enabled and self.powder_wavelength_spin.value() == 0:
                wavelength, source = self._map_feedback_wavelength()
                self.powder_wavelength_status.setText(
                    f"Automatic wavelength: {wavelength:.10g} Å · {source}"
                    if wavelength > 0 else "No automatic wavelength was found. Enter a positive measured wavelength."
                )
                self.powder_wavelength_status.setVisible(True)
            else:
                self.powder_wavelength_status.setVisible(False)

        self.powder_enabled_checkbox.toggled.connect(sync_powder_dependency)
        self.powder_mix_spin.valueChanged.connect(sync_powder_dependency)
        self.powder_wavelength_spin.valueChanged.connect(sync_powder_dependency)
        sync_powder_dependency()

        def sync_feedback_description(_value=None) -> None:
            total = self.cycles.value()
            powder = getattr(self, 'feedback_is_powder', False)
            active = []
            selected = []
            for title, checkbox, start, magnitude, compatible in (
                ('Missing-reflection completion', self.missing_enabled_checkbox, self.missing_start_cycle_spin,
                 self.missing_percent_spin.value(), not powder),
                ('Intensity correction', self.intensity_enabled_checkbox, self.intensity_start_cycle_spin,
                 self.intensity_damping_spin.value(), True),
                ('Powder repartitioning', self.powder_enabled_checkbox, self.powder_start_cycle_spin,
                 self.powder_mix_spin.value(), powder),
            ):
                if not compatible or not checkbox.isChecked():
                    continue
                selected.append(title)
                if total > 1 and start.value() < total and magnitude > 0:
                    if title != 'Powder repartitioning' or self._map_feedback_wavelength()[0] > 0:
                        active.append((title, start.value() + 1))
            if active:
                text = ('<b>Map Feedback enabled</b> · '+ ' → '.join(name for name, _ in active)+
                        '<br>Scientific warning: Map Feedback can modify the reflection data supplied to subsequent cycles. '
                        'Validate the resulting structure against the original measured diffraction data.')
                icon = QStyle.SP_MessageBoxWarning
            elif selected and total > 1:
                text = ('<b>Map Feedback has no effective operation</b><br>This setting currently has no effect. '
                        'Check the enabled methods, start cycles, damping, addition limit, map ratio mix and required wavelength.')
                icon = QStyle.SP_MessageBoxInformation
            else:
                text = ('<b>Map Feedback disabled</b> · No reflection-data updates will be applied between cycles.')
                icon = QStyle.SP_MessageBoxInformation
            text += '<br>Original experimental input files are never modified.'
            noops = [name for name in selected if name not in {name for name, _ in active}]
            if active and noops:
                text += '<br>This setting currently has no effect: ' + ', '.join(noops) + '.'
            self.map_feedback_warning_text.setText(text)
            self.map_feedback_warning_icon.setPixmap(self.dialog.style().standardIcon(icon).pixmap(20, 20))
            cycle_text = f'{total} cycles configured'
            if active:
                # These are the existing engine's eligible subsequent cycles, not a promise of changed values.
                for name, first in active:
                    span = str(first) if first == total else f'{first}–{total}'
                    cycle_text += f' · {name} may affect cycles {span}'
                cycle_text += '\n' + ' → '.join(name.lower() for name, _ in active) + ' → next cycle (when eligible)'
            self.feedback_cycle_summary.setText(cycle_text)
            self.intensity_note.setVisible(self.intensity_enabled_checkbox.isChecked() and total > 1)
            self.powder_note.setVisible(self.powder_enabled_checkbox.isChecked() and total > 1)

        self._sync_feedback_description = sync_feedback_description
        for control in (self.missing_enabled_checkbox, self.intensity_enabled_checkbox, self.powder_enabled_checkbox):
            control.toggled.connect(sync_feedback_description)
        for control in (self.missing_start_cycle_spin, self.missing_percent_spin, self.intensity_start_cycle_spin,
                        self.intensity_damping_spin, self.powder_start_cycle_spin, self.powder_mix_spin,
                        self.powder_wavelength_spin):
            control.valueChanged.connect(sync_feedback_description)

        def sync_feedback_applicability(_value: int = 0) -> None:
            applicable = self.cycles.value() > 1
            self.feedback_applicability_note.setVisible(not applicable)
            for checkbox in (
                self.missing_enabled_checkbox,
                self.intensity_enabled_checkbox,
                self.powder_enabled_checkbox,
            ):
                checkbox.setEnabled(applicable)
            if applicable:
                maximum = self.cycles.value() - 1
                for spin in (
                    self.missing_start_cycle_spin,
                    self.intensity_start_cycle_spin,
                    self.powder_start_cycle_spin,
                ):
                    # Keep a user's later start intact if the cycle count is reduced.
                    # Existing Run validation explains that it leaves no subsequent cycle.
                    spin.setMaximum(max(maximum, spin.value()))
            else:
                # Retain the configured value while the one-cycle workflow
                # makes feedback inapplicable; it is restored if cycles rise.
                for spin in (
                    self.missing_start_cycle_spin,
                    self.intensity_start_cycle_spin,
                    self.powder_start_cycle_spin,
                ):
                    spin.setMaximum(999)
            sync_missing_dependency()
            sync_intensity_dependency()
            sync_powder_dependency()
            sync_feedback_description()

        self._sync_feedback_applicability = sync_feedback_applicability
        self.cycles.valueChanged.connect(sync_feedback_applicability)
        sync_feedback_applicability()

        # One consistent rhythm for every Wizard section (shared constants in
        # ui_style.PHASE_STUDIO_SPACING), instead of each page carrying its own
        # pixel values. Layout only -- no control, value or behaviour changes.
        self._apply_wizard_section_style()

        # Map feedback numeric editors: layout only, no changed semantics.
        self._constrain_numeric_editors(
            self.missing_start_cycle_spin,
            self.missing_percent_spin,
            self.intensity_start_cycle_spin,
            self.intensity_damping_spin,
            self.intensity_sigma_spin,
            self.powder_start_cycle_spin,
            self.powder_wavelength_spin,
            self.powder_separation_spin,
            self.powder_mix_spin,
        )

        self.detected_data_mode_holder: dict = {"mode": None}





        for _spin in (self.missing_start_cycle_spin, self.intensity_start_cycle_spin, self.powder_start_cycle_spin):
            _spin.valueChanged.connect(lambda _value=0: self._refresh_page3_validation_message())
        self.powder_wavelength_spin.valueChanged.connect(lambda _value=0: self._refresh_page3_validation_message())
        for _checkbox in (self.missing_enabled_checkbox, self.intensity_enabled_checkbox, self.powder_enabled_checkbox):
            _checkbox.toggled.connect(lambda _checked=False: self._refresh_page3_validation_message())
        self.cycles.valueChanged.connect(lambda _value=0: self._refresh_page3_validation_message())

    def run(self) -> JanaRunOptions:
        qt = self.qt
        QHBoxLayout = qt["QHBoxLayout"]
        QPushButton = qt["QPushButton"]
        QTimer = qt["QTimer"]
        QWidget = qt["QWidget"]

        # ----- Fixed action footer: added to outer_root (NOT the scrollable
        # `root`/content_layout), so Back/Cancel/Run phasing always stay
        # visible above the taskbar regardless of how tall the scrollable
        # page content above them gets (spec: "WIZARD WINDOW SIZING" sections
        # 5/8). 2.0.0: "Open full configuration" is removed -- it duplicated
        # "Professional mode" on page1, which is now the one authoritative
        # entry to the full Phase Studio GUI. The primary button is hidden
        # entirely on page1 and the Autosolve decision page, since their
        # actions are tile-click-driven (no Next/Run confirmation step);
        # Advanced's own page2/page3 flow keeps it. -----
        self.footer = QWidget()
        self.footer.setObjectName("wizardFooter")
        self.button_row = QHBoxLayout(self.footer)
        self.button_row.setContentsMargins(14, 8, 14, 12)
        self.back_button = QPushButton("‹ Back")
        self.back_button.setToolTip("Return to the workflow selection.")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setToolTip("Close the launcher without starting or modifying the Jana2020 job.")
        self.primary_button = QPushButton("Run phasing")
        self.primary_button.setObjectName("primaryButton")
        self.primary_button.setDefault(True)
        self.button_row.addWidget(self.back_button)
        from phase_studio.update_ui import install_application_header_menu
        self.header_controls = install_application_header_menu(self.brand_header, self.dialog,
            about=lambda: qt['QMessageBox'].about(self.dialog, 'About Phase Studio',
                'Phase Studio ' + __version__ + '<br>Crystallographic phasing with Superflip and SharpED.'))
        self.update_menu = self.header_controls.menu_button
        self.button_row.addStretch(1)
        self.button_row.addWidget(self.cancel_button)
        self.button_row.addWidget(self.primary_button)
        self.outer_root.addWidget(self.footer)
        self.chrome_holder["footer"] = self.footer
        self.brand_header.setFixedHeight(self.brand_header.sizeHint().height())
        self.context_banner.setFixedHeight(self.context_banner.sizeHint().height())
        self.footer.setFixedHeight(max(button.sizeHint().height() for button in
            (self.back_button, self.cancel_button, self.primary_button)) + 20)

        # Qt's default scroll-area focus handling may expose only a child or
        # cursor rectangle. Keep the whole focused control and its focus ring
        # inside the viewport, without moving the fixed footer.
        from PySide6.QtCore import QEvent, QObject, QPoint

        wizard = self

        class _FocusVisibility(QObject):
            def eventFilter(self, watched, event):
                if event.type() == QEvent.FocusIn:
                    QTimer.singleShot(0, lambda: self.reveal(watched))
                return False

            def reveal(self, control):
                from shiboken6 import isValid
                if not isValid(control) or not control.hasFocus() or not control.isVisible():
                    return
                viewport = wizard.scroll_area.viewport()
                rect = control.rect().translated(control.mapTo(viewport, QPoint()))
                margin = 6
                bar = wizard.scroll_area.verticalScrollBar()
                if rect.bottom() + margin >= viewport.height():
                    bar.setValue(bar.value() + rect.bottom() + margin - viewport.height() + 1)
                elif rect.top() < margin:
                    bar.setValue(bar.value() + rect.top() - margin)

        self._focus_visibility = _FocusVisibility(self.dialog)
        browses = self.files_form_widget.findChildren(QPushButton, "optionalFileBrowse")
        controls = [self.validate_hkl_button, self.analyze_completeness_button, self.files_toggle,
                    self.reference_file, browses[0], self.model_file, browses[1],
                    self.original_superflip_tile, self.superflip_sharped_tile,
                    self.autosolve_tile, self.professional_mode_tile, self.cancel_button]
        for before, after in zip(controls, controls[1:]):
            QWidget.setTabOrder(before, after)
        for control in controls[:-1]:
            control.installEventFilter(self._focus_visibility)





        self._workflow_changed()

        self.PAGE2_BANNER_TEXT = {
            WORKFLOW_SUPERFLIP_SHARPED: (
                "SUPERFLIP + SHARPED",
                "Configure charge flipping and SharpED processing",
            ),
            WORKFLOW_PHASE_RECYCLING: ("PHASE RECYCLING", "Configure phase recycling and validation"),
        }

        def scroll_to_page_top() -> None:
            # Each step begins at its own top. Carrying the previous page's
            # offset through Next/Back can hide the heading and look like a
            # geometry jump even though the outer window is stable.
            from PySide6.QtWidgets import QToolTip
            QToolTip.hideText()
            self.scroll_area.verticalScrollBar().setValue(0)

        def go_to_page1() -> None:
            self.content_layout.setContentsMargins(14, 10, 14, 14)
            if self._current_workflow() not in (
                WORKFLOW_SUPERFLIP_ONLY, WORKFLOW_SUPERFLIP_SHARPED, WORKFLOW_AUTOSOLVE,
            ):
                self.workflow_state["key"] = WORKFLOW_SUPERFLIP_ONLY
                self._workflow_changed()
            self.stack.setCurrentWidget(self.page1)
            self.back_button.setVisible(False)
            # Both dominant actions are tile-click-driven -- no Next/Run
            # confirmation step, so the primary button has nothing to do here.
            self.primary_button.setVisible(False)
            self.context_title_label.setText("JANA2020 WORKFLOW")
            self.context_subtitle_label.setText("Review the incoming crystallographic data and choose a workflow")
            scroll_to_page_top()
            self._adjust_dialog_size()

        def go_to_page2() -> None:
            self.content_layout.setContentsMargins(14, 16, 14, 10)
            self.stack.setCurrentWidget(self.page2)
            self.back_button.setVisible(True)
            self.primary_button.setVisible(True)
            # Page 2 is where a SharpED model is chosen, so the list is fetched
            # on arrival instead of leaving the user on "Model list not loaded."
            # until they find the Refresh button. No-op for Superflip only, and
            # cached for the rest of the session.
            self._ensure_models_loaded()
            self.primary_button.setText("Next: Map feedback →" if self._current_workflow()==WORKFLOW_SUPERFLIP_SHARPED else "Next ›")
            self.primary_button.setToolTip("Continue to Map Feedback.")
            banner_title, banner_subtitle = self.PAGE2_BANNER_TEXT.get(
                self._current_workflow(), ("JANA2020 WORKFLOW", "")
            )
            self.context_title_label.setText(banner_title)
            self.context_subtitle_label.setText(banner_subtitle)
            scroll_to_page_top()
            self._adjust_dialog_size()

        def go_to_page3() -> None:
            self.content_layout.setContentsMargins(14, 10, 14, 10)
            self._sync_page3_for_data_type()
            self._refresh_page3_validation_message()
            self.stack.setCurrentWidget(self.page3)
            self.back_button.setVisible(True)
            self.primary_button.setVisible(True)
            self.primary_button.setText("Run phasing")
            self.primary_button.setToolTip(
                "Start the configured phasing workflow."
            )
            self.context_title_label.setText("SUPERFLIP + SHARPED · MAP FEEDBACK")
            self.context_subtitle_label.setText("Optionally update reflection data between cycles")
            scroll_to_page_top()
            self._adjust_dialog_size()

        def go_back() -> None:
            current = self.stack.currentWidget()
            if current is self.page3:
                go_to_page2()
            elif current is self.page2:
                go_to_page1()
            else:
                go_to_page1()

        self.back_button.clicked.connect(go_back)
        self._go_to_map_feedback = go_to_page3
        go_to_page1()

        self.result = {"action": "cancel"}

        def effective_next_cycle_mode() -> str:
            if self._current_workflow() == WORKFLOW_SUPERFLIP_ONLY:
                return "none"
            if self._current_workflow() == WORKFLOW_SUPERFLIP_SHARPED:
                # This workflow always runs SharpED and hands its (deblurred)
                # map off to Jana2020 -- the raw-vs-SharpED map choice only has
                # real meaning for Phase recycling, where each cycle genuinely
                # can feed forward either map. Never let a leftover radio
                # selection from an earlier Phase-recycling session silently
                # skip SharpED here even if somehow still checked.
                return "deblurred_xplor"
            return "superflip_xplor" if self.superflip_map_radio.isChecked() else "deblurred_xplor"

        def effective_cycles() -> int:
            return 1 if self._current_workflow() == WORKFLOW_SUPERFLIP_ONLY else self.cycles.value()

        def effective_elements() -> str:
            return self._shared_or_legacy_value("sharped_elements", "elements", "C N O")

        def effective_outres() -> float:
            try:
                return float(self._shared_or_legacy_value("sharped_outres", "outres", "0.2"))
            except ValueError:
                return 0.2

        def effective_compute_omit_maps() -> bool:
            # Cross-validation is Phase-recycling-only; the checkboxes are hidden
            # (never even shown) for either single-pass workflow, and their value
            # must not leak through in that case regardless of prior state.
            return self._current_workflow() == WORKFLOW_PHASE_RECYCLING and self.omit_checkbox.isChecked()

        def effective_compute_omit_rfree() -> bool:
            return effective_compute_omit_maps() and self.rfree_checkbox.isChecked()

        def effective_map_feedback_enabled() -> bool:
            return effective_cycles() > 1 and self._current_workflow() in (WORKFLOW_SUPERFLIP_SHARPED, WORKFLOW_PHASE_RECYCLING)

        def save_values() -> None:
            next_cycle_mode = effective_next_cycle_mode()
            self.settings.setValue("workflow", self._current_workflow())
            self.settings.setValue("cycles", effective_cycles())
            self.settings.setValue("next_cycle_modelfile", next_cycle_mode)
            self.settings.setValue("use_deblurred_map", next_cycle_mode == "deblurred_xplor")
            # The URL is fixed for normal Wizard workflows; the API token is
            # shared with the full application.
            self.shared_settings.setValue("inputs/sharped_base_url", DEFAULT_SERVER_URL)
            try:
                credential_store.save_input(self.api_token.text())
            except (OSError, ValueError):
                # Retain the configured key in memory; never write plaintext
                # when device storage is unavailable.
                pass
            self.shared_settings.sync()
            self.settings.setValue("model", self.model.currentText())
            self.settings.setValue(
                "model_selection_mode", "manual" if self.model_user_picked["value"] else "automatic"
            )
            # Elements and Output resolution have no control of their own here
            # any more -- they come from the shared full-application settings (see
            # effective_elements()/effective_outres()) and are not re-persisted.
            # Reference file / model file are deliberately not persisted: they should
            # reflect the incoming .inflip (or be blank), never a leftover value from
            # an unrelated previous Jana2020 job.
            self.settings.sync()

        def build_options(action: str) -> JanaRunOptions:
            next_cycle_mode = effective_next_cycle_mode()
            run_model = self.model.currentText().strip()
            return JanaRunOptions(
                action=action,
                cycles=effective_cycles(),
                # The recommended workflow always retains both completed
                # result families. Its initial Result Selection source is the
                # measured-data Charge-flipping solution result; the SharpED result is
                # available beside it without a hidden pre-run objective.
                use_deblurred_map=(
                    False if self._current_workflow() == WORKFLOW_SUPERFLIP_SHARPED
                    else next_cycle_mode == "deblurred_xplor"
                ),
                next_cycle_modelfile=next_cycle_mode,
                api_token=self.api_token.text().strip(),
                server_url=DEFAULT_SERVER_URL,
                model=run_model,
                elements=effective_elements(),
                outres=effective_outres(),
                input_mode=INPUT_MODE_INFLIP,
                hkl_override="",
                reference_override="",
                superflip_referencefile=self.reference_file.text().strip(),
                first_cycle_modelfile=self.model_file.text().strip(),
                compute_omit_maps=effective_compute_omit_maps(),
                compute_omit_rfree=effective_compute_omit_rfree(),
                enable_missing_completion=effective_map_feedback_enabled() and not getattr(self, "feedback_is_powder", False) and self.missing_enabled_checkbox.isChecked(),
                missing_start_cycle=self.missing_start_cycle_spin.value(),
                missing_max_added_percent=self.missing_percent_spin.value(),
                enable_intensity_correction=effective_map_feedback_enabled() and self.intensity_enabled_checkbox.isChecked(),
                intensity_start_cycle=self.intensity_start_cycle_spin.value(),
                intensity_damping=self.intensity_damping_spin.value(),
                intensity_sigma_threshold=self.intensity_sigma_spin.value() if getattr(self, "feedback_has_uncertainty", False) else 0.0,
                enable_powder_repartition=effective_map_feedback_enabled() and getattr(self, "feedback_is_powder", False) and self.powder_enabled_checkbox.isChecked(),
                powder_start_cycle=self.powder_start_cycle_spin.value(),
                powder_wavelength=self._map_feedback_wavelength()[0] if effective_map_feedback_enabled() and self.powder_enabled_checkbox.isChecked() else self.powder_wavelength_spin.value(),
                powder_separation_factor=self.powder_separation_spin.value(),
                powder_map_ratio_mix=self.powder_mix_spin.value(),
                # Kept only for the adaptive Autosolve backend's compatibility
                # contract. The ordinary Superflip + SharpED route has no
                # objective state; users choose the exact family/cycle later.
                autosolve_option="A" if action == "autosolve" else "",
            )

        def attempt_run() -> None:
            self._preflight_sharped_default_model = ""
            if self.stack.currentWidget() is self.page1 and self._current_workflow() == WORKFLOW_SUPERFLIP_SHARPED:
                go_to_page2()
                return
            if self.stack.currentWidget() is self.page1 and self._current_workflow() == WORKFLOW_AUTOSOLVE:
                if not self._ensure_workflow_requirements(needs_sharped=True):
                    return
                save_values()
                self.result["action"] = "autosolve"
                self.dialog.accept()
                return
            if self.stack.currentWidget() is self.page3:
                validation_message = self._check_page3_validity()
                if validation_message:
                    self._refresh_page3_validation_message()
                    return
                if not self._ensure_workflow_requirements(needs_sharped=True):
                    return
                save_values()
                self.result["action"] = "recycle"
                self.dialog.accept()
                return
            if self.stack.currentWidget() is self.page2 and self._current_workflow() == WORKFLOW_SUPERFLIP_SHARPED:
                go_to_page3()
                return
            if not self._ensure_workflow_requirements(
                needs_sharped=effective_next_cycle_mode() == "deblurred_xplor"
            ):
                return
            save_values()
            # Only Phase recycling opens the full Phase Studio main window (via
            # PAGE 3 above, "Next ›" then "Run phasing"). Both single-pass
            # workflows (Superflip only, Superflip + SharpED) keep the original
            # lightweight console/wrapper path below -- run_jana_superflip()
            # called directly from main(), no main window at all.
            self.result["action"] = "run"
            self.dialog.accept()

        def edit_clicked() -> None:
            save_values()
            self.result["action"] = "edit"
            self.dialog.accept()

        # Exposed so page1's own tile-click
        # handlers (built by earlier methods) can trigger exactly the same
        # dispatch a visible "Run phasing"/"Next"/"Start Autosolve" button
        # used to -- not a second, parallel dispatch implementation.
        self._attempt_run = attempt_run
        self._attempt_edit = edit_clicked

        self.primary_button.clicked.connect(attempt_run)
        # "Professional mode" is the one authoritative entry to the full
        # Phase Studio GUI (2.0.0: the old "Open full configuration" footer
        # button duplicated it and has been removed).
        self.cancel_button.clicked.connect(self.dialog.reject)

        # Word-wrapped labels' heightForWidth() is not fully trustworthy until
        # the widget tree has actually been laid out and polished at least once,
        # so the synchronous adjust_dialog_size() calls made during construction
        # above can overstate the needed height. A second pass once the dialog's
        # event loop has actually started (same deferred-refit pattern used for
        # the HKL Completeness dialog in app.py) settles it accurately.
        QTimer.singleShot(0, self._adjust_dialog_size)

        def remember_window_geometry(_result):
            self.settings.setValue("wizard/windowGeometry", self.dialog.saveGeometry())
            self.settings.setValue("wizard/windowRect", self.dialog.geometry())
        self.dialog.finished.connect(remember_window_geometry)
        accepted = self.dialog.exec()
        self.refresh_timer.stop()
        if not accepted:
            return JanaRunOptions(action="cancel")
        return build_options(self.result["action"])


def show_jana_dialog(args: Sequence[str], inflip_path: Optional[Path]) -> JanaRunOptions:
    return _JanaWorkflowWizard(args, inflip_path).run()


def launch_phase_studio_from_jana(
    inflip_path: Optional[Path], options: JanaRunOptions, auto_start: bool = False,
    diagnostic_log: Optional[Callable[[str], None]] = None,
) -> int:
    # Load PySide6 before importing app.py, which initializes Matplotlib QtAgg.
    qt = _qt_imports()
    QApplication = qt["QApplication"]

    from phase_studio.app import (
        IterativeSuperflipPipelineQtGUI,
        apply_phase_studio_app_icon,
        create_startup_splash,
        initialize_main_window,
        parse_inflip_settings,
    )

    handoff_import: Optional[JanaHandoffImport] = None
    if inflip_path is not None:
        if not inflip_path.is_file():
            raise FileNotFoundError(f"Jana2020 .inflip file not found: {inflip_path}")
        parsed = parse_inflip_settings(inflip_path)
        handoff_import = build_jana_handoff_import(inflip_path, options, parsed)

    app = QApplication.instance() or QApplication(sys.argv)
    apply_phase_studio_style(app)
    apply_phase_studio_app_icon(app)
    splash = create_startup_splash()
    splash.show()
    app.processEvents()

    def build_window() -> IterativeSuperflipPipelineQtGUI:
        win = IterativeSuperflipPipelineQtGUI()
        # Both launches that reach this function (Wizard "Open full
        # configuration" and Wizard "Phase recycling") are genuinely
        # Wizard-initiated -- set this before any handed-off settings are
        # applied below and before a run can start, so the main window
        # always knows a future completed run is Jana2020-hand-off-eligible,
        # even for a plain "Open full configuration" session that the user
        # drives and completes manually.
        win.jana_wizard_context.launched_from_jana_wizard = True
        if auto_start:
            # Phase recycling still runs the ordinary full pipeline (start_run()
            # below); this mode only annotates that run as Wizard-initiated so
            # its completion opens the source-specific result selector instead
            # of the ordinary "Send to Jana2020" dialog. The map source was
            # already chosen on the Wizard's second page (superflip_xplor /
            # deblurred_xplor are the only two values that reach this launch
            # path -- see effective_next_cycle_mode() in show_jana_dialog()).
            win.jana_wizard_context.launch_mode = "phase_recycling"
            win.jana_wizard_context.wizard_map_source = (
                "deblurred" if options.use_deblurred_map else "superflip"
            )
            win.jana_wizard_context.autosolve_option = options.autosolve_option or (
                "B" if options.use_deblurred_map else "A"
            )
            # Fill every EDMA/Superflip setting the dialog and the .inflip don't
            # cover with Phase Studio's own "recommended" preset first, so the
            # values applied below (this Jana2020 run's explicit choices) win.
            win._apply_workflow_preset("recommended")
        else:
            # "Open full configuration": the user drives the whole workflow
            # manually; no map source is pre-locked and the workflow does not
            # auto-start. Completed runs use the shared result selector.
            win.jana_wizard_context.launch_mode = "full_configuration"
        # The third primary button and window title default to standalone's
        # "Install to Jana2020" / "Phase Studio <version>" at construction;
        # both Wizard launch paths above just changed jana_wizard_context, so
        # re-sync both immediately rather than waiting for the next unrelated
        # state change.
        win._sync_jana_action_button()
        win._sync_window_title()
        if inflip_path is not None and handoff_import is not None:
            splash.set_status("Loading Jana2020 workflow…")
            app.processEvents()
            applied_keys: list[str] = []
            for key, value in handoff_import.values.items():
                widget = win.inputs.get(key)
                if widget is not None:
                    win._set_widget_value_from_string(widget, value)
                    applied_keys.append(key)
            # Programmatic hand-off does not fire the interactive signals that
            # normally keep "Crystal metadata source" synced to input_source_mode
            # (PathRow.set_value / QComboBox.setCurrentIndex don't emit on_change /
            # activated), so re-derive it explicitly here.
            win._input_mode_user_changed()
            win._sync_input_source_mode_widgets()
            win._sync_workflow_widgets()
            for line in jana_handoff_log_lines(handoff_import, inflip_path, applied_keys):
                win._append_execution_log(line, subsystem="Jana2020")
            win._append_execution_log(
                f"[Jana2020] Integration · Phase Studio {__version__} · "
                f"launcher {(Path(sys.executable).resolve() if getattr(sys, 'frozen', False) else Path(__file__).resolve())} · "
                f"Superflip {resolve_active_jana_superflip(application_dir()).resolve()}",
                level="DETAIL",
                subsystem="Jana2020",
            )
            if auto_start:
                win._append_execution_log(
                    "[Jana2020] Phase recycling requested · calculation will start automatically",
                    level="DETAIL",
                    subsystem="Jana2020",
                )
            else:
                win._append_execution_log(
                    "After the full workflow finishes, the result selector opens with the recommended cycle and map source preselected; use 'Pass to Jana2020' to complete the handoff.",
                    level="DETAIL",
                    subsystem="Jana2020",
                )
        win.setWindowTitle(f"Phase Studio {__version__} for Jana2020")
        win._phase_studio_distribution = 'jana'
        return win

    if auto_start:
        # The full window supplies the established scientific backend, but a
        # Wizard-selected automatic workflow must never display or activate
        # Professional mode. Construct it directly and show only Execution.
        try:
            splash.set_status("Loading Jana2020 workflow…")
            app.processEvents()
            win = build_window()
            from phase_studio.autosolve_window import AutosolveWindow

            execution = AutosolveWindow(
                win,
                options.autosolve_option or ("B" if options.use_deblurred_map else "A"),
                inflip_path=inflip_path,
                workflow_name="Superflip + SharpED",
            )
            from phase_studio.ui_branding import fit_dialog_to_available_screen
            from PySide6.QtCore import QSize
            fit_dialog_to_available_screen(
                execution, QSize(1420, 860), width_fraction=0.92, height_fraction=0.90,
            )
            from phase_studio.ui_branding import transfer_user_foreground
            transfer_user_foreground(
                splash, execution, windows_foreground=True, diagnostic_log=diagnostic_log,
            )
            win.autosolve_dialog_parent = execution
            splash.set_status("Ready")
            win.start_run()
        except Exception as exc:
            splash.close()
            app.processEvents()
            report = build_error_report(
                exc, subsystem="Startup", operation="Initialize Jana2020 workflow",
                extra_details=traceback.format_exc(),
            )
            show_phase_studio_error(None, report)
            return 1
    else:
        win = initialize_main_window(app, splash, build_window)
        if win is None:
            return 1
        from phase_studio.ui_branding import activate_user_launched_window
        activate_user_launched_window(
            win, windows_foreground=True, diagnostic_log=diagnostic_log,
        )
    return int(app.exec())


def launch_autosolve_from_jana(
    inflip_path: Optional[Path], options: JanaRunOptions,
    diagnostic_log: Optional[Callable[[str], None]] = None,
) -> int:
    """Autosolve entry point (2.0.0). Drives the exact same ordinary-cycle
    mechanism the Wizard's "Phase recycling" card already uses
    (reconstruction_mode stays "superflip", Superflip runs every cycle seeded
    by the previous cycle's SharpED-deblurred map, undamped), but the cycle
    budget, any Map Feedback stage transition, and the final Jana2020 handoff
    are all fully automatic -- see IterativeSuperflipPipelineQtGUI's
    _autosolve_on_run_done()/_autosolve_begin_prediction()/
    _autosolve_handoff() in app.py, hooked into the existing "done" queue
    event alongside the manual Wizard/standalone completion paths.

    The full IterativeSuperflipPipelineQtGUI window is constructed here as
    the scientific *backend* only -- it is never shown. The user-visible
    window is the dedicated, simplified AutosolveWindow (autosolve_window.py),
    which borrows its structure-rendering/camera-sync methods and reparents
    its Execution Log and progress-bar widgets from the backend, exactly the
    way create_result_preview_host() already borrows the same methods for
    the Jana2020 result selector -- not a second implementation, and not the
    full multi-tab configuration GUI."""
    if inflip_path is None:
        raise ValueError("Autosolve requires a Jana2020 .inflip file.")
    qt = _qt_imports()
    QApplication = qt["QApplication"]

    from phase_studio.app import (
        AdaptiveCyclePolicy,
        IterativeSuperflipPipelineQtGUI,
        apply_phase_studio_app_icon,
        create_startup_splash,
        parse_inflip_settings,
    )
    from phase_studio.autosolve_window import AutosolveWindow

    inflip_path = Path(inflip_path)
    if not inflip_path.is_file():
        raise FileNotFoundError(f"Jana2020 .inflip file not found: {inflip_path}")
    parsed = parse_inflip_settings(inflip_path)
    handoff_import = build_jana_handoff_import(inflip_path, options, parsed)

    autosolve_option = options.autosolve_option or "A"
    # Autosolve's configuration is not user-editable, so these override both
    # the .inflip and whatever the Wizard's own leftover settings happen to
    # hold -- see the plan's mechanism section for why each value is exactly
    # this (undamped feed-forward of the latest SharpED map, EDMA every
    # cycle for both sources, an initial five-cycle fixed budget).
    # Both historical goals share one phase search -- Superflip + SharpED
    # UNIVERSAL, feeding the SharpED map's EDMA STRUCTURE forward
    # as the next Superflip model (the existing deblurred_edma_cif mode),
    # EDMA at 1.0 sigma on BOTH sides (Superflip / Charge-flipping solution and the
    # SharpED structure fed forward). See phase_studio/autosolve_review.py.
    from phase_studio.autosolve_review import (
        OBSERVED_THRESHOLD_SIGMA, PHASE_SEARCH_MODEL, PREDICTED_THRESHOLD_SIGMA,
    )

    autosolve_overrides = {
        "cycles": "5",
        "run_sharped": "true",
        "sharped_model": PHASE_SEARCH_MODEL,
        "modelfile_source": "deblurred_edma_cif",
        "damping_factor": "1.0",
        "run_edma_superflip": "true",
        "run_edma_deblurred": "true",
        "plimit_superflip": f"{OBSERVED_THRESHOLD_SIGMA:.2f}",
        "plimit_deblur": f"{PREDICTED_THRESHOLD_SIGMA:.2f}",
        "map_export_format": "jana",
    }
    values = dict(handoff_import.values)
    values.update(autosolve_overrides)

    app = QApplication.instance() or QApplication(sys.argv)
    apply_phase_studio_style(app)
    apply_phase_studio_app_icon(app)
    splash = create_startup_splash()
    splash.show()
    app.processEvents()

    def build_backend() -> IterativeSuperflipPipelineQtGUI:
        # The full GUI class, used purely as the scientific engine (RunConfig/
        # PipelineState/_run_pipeline_cycles/EDMA/SharpED/ranking/handoff) --
        # never shown. Constructing it fully (rather than a stripped-down
        # subset) is what makes reusing its existing widgets/methods for
        # AutosolveWindow safe: nothing in this class assumes it is visible
        # (confirmed: no isVisible()/screen()/showEvent() usage anywhere),
        # and its own internal 50ms QTimer already drives _poll_queue
        # regardless of .show() ever being called -- the same pattern
        # _get_backing_window() already uses for "Advanced" pages.
        win = IterativeSuperflipPipelineQtGUI()
        win.jana_wizard_context.launched_from_jana_wizard = True
        win.jana_wizard_context.launch_mode = "autosolve"
        win.jana_wizard_context.autosolve_option = autosolve_option
        win.jana_wizard_context.wizard_map_source = "superflip" if autosolve_option == "A" else "deblurred"
        win._apply_workflow_preset("recommended")
        # 2.0.0: EDMA threshold mode for BOTH sources from one central
        # constant (phase_studio/edma_threshold.py). "manual" uses the
        # plimit_* overrides below; "auto" calibrates per map and uses them
        # only as the fallback. See AUTOSOLVE_EDMA_THRESHOLD_MODE for why
        # 2.0.0 ships manual.
        from phase_studio.edma_threshold import AUTOSOLVE_EDMA_THRESHOLD_MODE, EDMA_THRESHOLD_MODE_AUTO

        win.edma_threshold_mode = AUTOSOLVE_EDMA_THRESHOLD_MODE
        applied_keys: list[str] = []
        for key, value in values.items():
            widget = win.inputs.get(key)
            if widget is not None:
                win._set_widget_value_from_string(widget, value)
                applied_keys.append(key)
        win._input_mode_user_changed()
        win._sync_input_source_mode_widgets()
        win._sync_workflow_widgets()
        for line in jana_handoff_log_lines(handoff_import, inflip_path, applied_keys):
            win._append_execution_log(line, subsystem="Jana2020")
        win._append_execution_log(
            f"[Jana2020] SharpED Autosolve requested -- the shared phase search "
            f"(Superflip + SharpED '{PHASE_SEARCH_MODEL}') starts "
            "automatically. When it converges, a Structure prediction is generated from the best "
            "Charge-flipping solution map and Review opens: tune the EDMA thresholds, recalculate, or pass "
            "the result you choose to Jana2020.",
            level="DETAIL",
            subsystem="Jana2020",
        )
        if win.edma_threshold_mode == EDMA_THRESHOLD_MODE_AUTO:
            threshold_text = (
                "Auto, calibrated per map "
                f"(fallback {float(autosolve_overrides['plimit_superflip']):g} σ after Superflip, "
                f"{float(autosolve_overrides['plimit_deblur']):g} σ after SharpED)"
            )
        else:
            threshold_text = (
                f"{float(autosolve_overrides['plimit_superflip']):g} σ after Superflip, "
                f"{float(autosolve_overrides['plimit_deblur']):g} σ after SharpED"
            )
        win._append_execution_log(
            f"[Autosolve] EDMA threshold: {threshold_text}",
            level="DETAIL",
            subsystem="Autosolve",
        )
        return win

    try:
        splash.set_status("Loading Jana2020 workflow…")
        app.processEvents()
        backend = build_backend()
        splash.close()
        backend._autosolve_stage = "search"
        backend._autosolve_policy = AdaptiveCyclePolicy(
            backend._active_validation_profile(), initial=5, block_size=3,
        )
        backend.start_run()
        if str(getattr(backend, "_run_status", "")).upper() != "RUNNING":
            backend.close()
            return 1
        splash.set_status("Finalizing workspace…")
        app.processEvents()
        autosolve_win = AutosolveWindow(backend, autosolve_option, inflip_path=inflip_path)
        from phase_studio.ui_branding import fit_dialog_to_available_screen
        from PySide6.QtCore import QSize
        fit_dialog_to_available_screen(
            autosolve_win, QSize(1420, 860), width_fraction=0.92, height_fraction=0.90,
        )
        from phase_studio.ui_branding import activate_user_launched_window
        activate_user_launched_window(
            autosolve_win, windows_foreground=True, diagnostic_log=diagnostic_log,
        )
        app.processEvents()
        splash.set_status("Ready")
        splash.finish(autosolve_win)
    except Exception as exc:
        splash.close()
        app.processEvents()
        report = build_error_report(
            exc,
            subsystem="Startup",
            operation="Initialize Autosolve",
            extra_details=traceback.format_exc(),
        )
        show_phase_studio_error(None, report)
        return 1

    return int(app.exec())


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    args = argv[1:]
    if "--release-ui-check" in args:
        index = args.index("--release-ui-check")
        from phase_studio.release_diagnostics import run_release_ui_check
        return run_release_ui_check(args[index + 1])
    if "--credential-self-check" in args:
        index = args.index("--credential-self-check")
        from phase_studio.oauth_diagnostics import run_credential_check
        return run_credential_check(args[index + 1], args[index + 2])
    if "--version" in args:
        print(__version__)
        return 0
    for flag in ("--oauth-self-check", "--oauth-sign-in-check"):
        if flag in args:
            index = args.index(flag)
            if index + 1 >= len(args):
                raise ValueError(flag + " requires an output JSON path")
            from phase_studio.oauth_diagnostics import run_oauth_check
            return run_oauth_check(args[index + 1], interactive=flag == "--oauth-sign-in-check")
    if "--brand-font-check" in args:
        index = args.index("--brand-font-check")
        if index + 1 >= len(args):
            raise ValueError("--brand-font-check requires an output JSON path")
        from PySide6.QtWidgets import QApplication
        from phase_studio.ui_branding import phase_studio_brand_runtime_report
        app = QApplication.instance() or QApplication([sys.argv[0]])
        apply_phase_studio_style(app)
        output = Path(args[index + 1]).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(phase_studio_brand_runtime_report("jana-wrapper"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return 0
    exe_dir = application_dir()
    initial_cwd = Path.cwd().resolve()
    inflip_info = find_inflip_arg(args, initial_cwd)
    inflip_path = inflip_info[1].expanduser().resolve() if inflip_info else None
    logger = create_jana_logger(inflip_path)
    try:
        logger("Phase Studio Jana Superflip wrapper started")
        logger(f"Jana project: {inflip_path.parent if inflip_path is not None else 'unavailable; using safe temporary log'}")
        logger(f"Input: {inflip_path if inflip_path is not None else 'not supplied'}")
        logger(f"Project log: {logger.log_path}")
        log_wrapper_runtime_identity(logger)
        logger(f"Executable dir: {exe_dir}")
        logger(f"Initial working dir (diagnostic only): {initial_cwd}")
        logger(f"Received arguments count: {len(args)}")
        for i, arg in enumerate(args, 1):
            logger(f"arg[{i}] = {arg}")
        if not args:
            logger("No arguments; opening Phase Studio GUI.")
            return launch_phase_studio_from_jana(
                None, JanaRunOptions(action="edit"), diagnostic_log=logger,
            )

        options = show_jana_dialog(args, inflip_path)
        if options.action == "cancel":
            logger("Cancelled by user.")
            return 1
        if options.action == "edit":
            logger("Opening full Phase Studio GUI.")
            return launch_phase_studio_from_jana(
                inflip_path, options, diagnostic_log=logger,
            )
        if options.action == "recycle":
            logger("Phase recycling requested; running it through the full Phase Studio workflow.")
            return launch_phase_studio_from_jana(
                inflip_path, options, auto_start=True, diagnostic_log=logger,
            )
        if options.action == "autosolve":
            logger(f"Autosolve requested (option {options.autosolve_option!r}); starting the adaptive search.")
            # The dedicated Autosolve window presents the shared backend's
            # adaptive cycle budget, Map Feedback transition, and Jana2020
            # handoff without exposing the full configuration window.
            return launch_autosolve_from_jana(
                inflip_path, options, diagnostic_log=logger,
            )
        # Both single-pass workflows ("run": Superflip only and Superflip +
        # SharpED) use the original lightweight console/wrapper path -- no main
        # window. Only Phase recycling (above) opens the full Phase Studio GUI.
        code = run_jana_superflip(args, options, logger)
        logger("Wrapper finished")
        return int(code)
    except Exception as exc:
        report = build_error_report(
            exc,
            subsystem="Jana2020",
            operation="Run Jana2020 calculation",
            extra_details=traceback.format_exc(),
        )
        logger(f"[ERROR][{report.subsystem}] {report.title}.")
        logger(report.diagnostic_block())
        try:
            qt = _qt_imports()
            QApplication = qt["QApplication"]
            app = QApplication.instance() or QApplication([sys.argv[0]])
            apply_phase_studio_style(app)
            if report.category == "sharped_authentication":
                from phase_studio import requirements as reqs
                from phase_studio.requirements_ui import show_requirement_remediation_dialog

                shared = qt["QSettings"]("PhaseStudio", "PhaseStudio")
                current = credential_store.load_settings(shared)
                status = reqs.RequirementStatus(
                    kind=reqs.RequirementKind.SHARPED,
                    state=reqs.RequirementState.TOKEN_REJECTED,
                )
                classified = reqs._classify_sharped_error(RuntimeError(report.technical_details))
                if classified.state in {reqs.RequirementState.TOKEN_REJECTED, reqs.RequirementState.ACCESS_DENIED}:
                    status = classified
                token = show_requirement_remediation_dialog(None, status, current)
                if token is not None:
                    shared.remove("inputs/sharped_api_token")
                    shared.sync()
            else:
                show_phase_studio_error(None, report)
        except Exception:
            pass
        return 1
    finally:
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main())
