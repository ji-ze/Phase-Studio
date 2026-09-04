#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jana2020-compatible Superflip launcher.

This module is intended to be frozen as superflip.exe and placed where Jana
normally finds the Superflip-for-Jana wrapper. The original Superflip binary is
expected next to it as superflip_original.exe.
"""

from __future__ import annotations

import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

try:
    from phase_studio.version import VERSION as __version__
except Exception:
    from version import VERSION as __version__

try:
    from phase_studio.error_reporting import build_error_report, sanitize_error_details, show_phase_studio_error
except Exception:
    from error_reporting import build_error_report, sanitize_error_details, show_phase_studio_error

try:
    from phase_studio.sharped_server_client import SharpEDServerClient
except Exception:
    from sharped_server_client import SharpEDServerClient

try:
    from phase_studio.ui_style import apply_phase_studio_style
except Exception:
    from ui_style import apply_phase_studio_style

try:
    from phase_studio.process_utils import allow_external_process_foreground, text_encoding
except Exception:
    from process_utils import allow_external_process_foreground, text_encoding


COMMENT_MARKERS = ("#", "!", ";")
INFLIP_SUFFIXES = {".inflip", ".inp"}
DEFAULT_SERVER_URL = "https://jana.fzu.cz"
DEFAULT_JANA_SUPERFLIP = Path(r"C:\Jana2020\SUPERFLIP\superflip_original.exe")
DEFAULT_JANA_EDMA = Path(r"C:\Jana2020\SUPERFLIP\EDMA.exe")

INPUT_MODE_INFLIP = "Jana .inflip"
INPUT_MODE_INFLIP_OVERRIDES = "Jana .inflip with external HKL/CIF overrides"
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
    api_token: str = ""
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

    handoff_values = {
        "input_source_mode": app_input_label,
        "jana_inflip": str(inflip_path),
        "work_dir": str(base_dir / f"phase_studio_full_run_{inflip_path.stem}"),
        "superflip_exe": str(DEFAULT_JANA_SUPERFLIP),
        "edma_exe": str(DEFAULT_JANA_EDMA),
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
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.log_path.open("w", encoding="utf-8", errors="replace")

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass

    def __call__(self, message: str) -> None:
        text = sanitize_error_details(message)
        # log.txt (below) is the authoritative, always-available copy of this
        # message; the console mirror is a bonus for a development console
        # window, not something later code depends on. This wrapper builds
        # windowed (console=False, see superflip.spec) precisely so no black
        # console window appears behind the Jana2020 Wizard -- stdout may
        # therefore be absent entirely, which must never take down logging.
        try:
            print(text, flush=True)
        except Exception:
            pass
        self._fh.write(text + "\n")
        self._fh.flush()


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


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


def split_inline_comment(line: str) -> Tuple[str, str]:
    quote = False
    for i, ch in enumerate(line):
        if ch == '"':
            quote = not quote
        elif not quote and ch in COMMENT_MARKERS:
            return line[:i].rstrip(), line[i:]
    return line.rstrip(), ""


def split_inflip_line(line: str) -> List[str]:
    """Split one Superflip/Jana keyword line while preserving quoted paths.

    Inline comments beginning with #, ! or ; are removed only when they occur
    outside double quotes. This keeps Windows paths and filenames containing
    spaces intact.
    """
    body, _comment = split_inline_comment(str(line or ""))
    text = body.strip()
    if not text:
        return []
    try:
        return shlex.split(text, posix=True)
    except (ValueError, TypeError):
        return text.split()


def first_token(line: str) -> str:
    parts = split_inflip_line(line)
    if not parts:
        return ""
    return parts[0].lower()


def line_has_xplor_output(line: str) -> bool:
    body, _comment = split_inline_comment(line)
    parts = body.split()
    return any(Path(part.strip('"')).suffix.lower() == ".xplor" for part in parts[1:])


def insert_before_fbegin(lines: Sequence[str], new_line: str) -> List[str]:
    out: List[str] = []
    inserted = False
    for line in lines:
        if not inserted and first_token(line) == "fbegin":
            out.append(new_line)
            inserted = True
        out.append(line)
    if not inserted:
        out.append(new_line)
    return out


def ensure_xplor_output(lines: Sequence[str], base_name: str) -> List[str]:
    out: List[str] = []
    changed = False
    found = False
    xplor_name = f'{base_name}.xplor'
    for line in lines:
        if first_token(line) == "outputfile":
            found = True
            if line_has_xplor_output(line):
                out.append(line)
            else:
                body, comment = split_inline_comment(line)
                spacer = "" if not body or body.endswith((" ", "\t")) else " "
                tail = (" " + comment) if comment else ""
                out.append(f'{body}{spacer}"{xplor_name}"{tail}')
                changed = True
        else:
            out.append(line)
    if not found:
        out = insert_before_fbegin(out, f'outputfile "{xplor_name}"')
        changed = True
    return out if changed else list(lines)


def without_keywords(lines: Sequence[str], keywords: Iterable[str]) -> List[str]:
    blocked = {k.lower() for k in keywords}
    return [line for line in lines if first_token(line) not in blocked]


def add_modelseed_modelfile(lines: Sequence[str], model_name: str, suffix: str = ".xplor") -> List[str]:
    """Add a Superflip modelfile using the Phase Studio model-seeded policy.

    A model-seeded Superflip run is deterministic. Therefore repeated attempts
    are disabled and the randomseed keyword is omitted, matching the logic used
    by the full Phase Studio pipeline. Phase Studio writes only modelfile and
    lets Superflip infer the format from the file extension.
    """
    cleaned = without_keywords(
        lines,
        {"modelfile", "modelformat", "repeatmode", "randomseed"},
    )
    cleaned = insert_before_fbegin(cleaned, "repeatmode 1")
    cleaned = insert_before_fbegin(cleaned, f"modelfile {model_name}")
    return cleaned


def apply_reference_override(lines: Sequence[str], reference_path: Path) -> List[str]:
    """Replace the Superflip referencefile declaration with a CIF or XPLOR file.

    Phase Studio writes only the referencefile keyword and lets Superflip infer
    the reference format from the file extension.
    """
    suffix = reference_path.suffix.lower()
    if suffix not in {".cif", ".xplor"}:
        raise ValueError(
            "Reference override must be a CIF structure or an XPLOR density map: "
            f"{reference_path}"
        )
    cleaned = without_keywords(lines, {"referencefile", "referenceformat"})
    cleaned = insert_before_fbegin(cleaned, f"referencefile {Path(reference_path).name}")
    return cleaned


def extract_embedded_hkl(inflip_path: Path) -> Optional[Path]:
    """Export the Jana fbegin/endf reflection block for the full Phase Studio GUI."""
    lines = read_text_lines(inflip_path)
    reflections: List[str] = []
    in_block = False
    for line in lines:
        key = first_token(line)
        if key == "fbegin":
            in_block = True
            continue
        if in_block and key == "endf":
            break
        if in_block and line.strip() and not line.lstrip().startswith(COMMENT_MARKERS):
            reflections.append(line.rstrip())
    if not reflections:
        return None
    output = inflip_path.parent / f"{inflip_path.stem}_embedded_reflections.hkl"
    output.write_text(
        "# Reflections exported from the Jana2020 .inflip fbegin/endf block.\n"
        + "\n".join(reflections)
        + "\n",
        encoding="utf-8",
    )
    return output


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


def inflip_header_for_m80(lines: Sequence[str]) -> List[str]:
    header: List[str] = []
    marker = "# Keywords for charge flipping"
    for line in lines:
        if marker in line:
            break
        if first_token(line) == "fbegin":
            break
        header.append(line)
    return header


def define_m80_inflip(header_lines: Sequence[str], base_name: str, model_name: str) -> List[str]:
    out: List[str] = []
    saw_perform = False
    saw_outputfile = False
    # These keywords are explicitly controlled for the final model-seeded run.
    # In particular, randomseed must not be present and repeatmode must be 1.
    drop = {
        "modelfile",
        "modelformat",
        "repeatmode",
        "randomseed",
        "polish",
        "maxcycles",
        "searchsymmetry",
        "derivesymmetry",
        "voxel",
    }
    for line in header_lines:
        key = first_token(line)
        if key in drop:
            continue
        if key == "perform" and not saw_perform:
            out.append("perform symmetry")
            saw_perform = True
            continue
        if key == "outputfile" and not saw_outputfile:
            body, comment = split_inline_comment(line)
            ready = f'{base_name}-ready.xplor'
            if ready.lower() not in body.lower():
                spacer = "" if body.endswith((" ", "\t")) else " "
                body = f'{body}{spacer}"{ready}"'
            out.append(body if not comment else f"{body} {comment}")
            saw_outputfile = True
            continue
        out.append(line)
    if not saw_perform:
        out = insert_before_fbegin(out, "perform symmetry")
    if not saw_outputfile:
        out = insert_before_fbegin(out, f'outputfile "{base_name}-ready.xplor"')
    out.extend(
        [
            "repeatmode 1",
            f'modelfile "{model_name}"',
            "polish no",
            "maxcycles 0",
            "searchsymmetry average",
            "derivesymmetry yes",
        ]
    )
    return out


def find_inflip_arg(args: Sequence[str], cwd: Path) -> Optional[Tuple[int, Path]]:
    for i, arg in enumerate(args):
        p = Path(str(arg).strip('"'))
        if p.suffix.lower() in INFLIP_SUFFIXES:
            return i, (p if p.is_absolute() else cwd / p)
    return None


def resolve_original_superflip(exe_dir: Path) -> Path:
    candidates = [
        DEFAULT_JANA_SUPERFLIP,
        exe_dir / "superflip_original.exe",
        exe_dir / "SuperFlip-orig.exe",
        exe_dir / "superflip-original.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    found = shutil.which("superflip_original.exe") or shutil.which("SuperFlip-orig.exe")
    if found:
        return Path(found)
    return candidates[0]


def run_process(cmd: Sequence[str], cwd: Path, log: Callable[[str], None]) -> int:
    log("Running: " + " ".join(str(part) for part in cmd))
    proc = subprocess.Popen(
        [str(part) for part in cmd],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding=text_encoding(),
        errors="replace",
    )
    allow_external_process_foreground(proc.pid)
    assert proc.stdout is not None
    for line in proc.stdout:
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
    client.execute(
        file_path=input_map,
        bearer_token=token,
        out_path=output_map,
        elements=options.elements.strip() or "C N O",
        model=selected_model,
        outres=float(options.outres),
        poll_seconds=2,
        max_polls=-1,
        log=log,
    )
    if not output_map.is_file() or output_map.stat().st_size == 0:
        raise RuntimeError(f"SharpED did not create output map: {output_map}")



def run_final_jana_handoff(
    original: Path,
    exe_dir: Path,
    cwd: Path,
    original_lines: Sequence[str],
    base_name: str,
    selected_map: Path,
    log: Callable[[str], None],
) -> int:
    if not selected_map.is_file() or selected_map.stat().st_size == 0:
        raise RuntimeError(f"Selected handoff map does not exist or is empty: {selected_map}")
    header = inflip_header_for_m80(original_lines)
    calc_m80 = exe_dir / "deblurrer" / "calc_m80.inflip"
    write_text_lines(calc_m80, define_m80_inflip(header, base_name, selected_map.name))
    log(f"Final Jana inflip: {calc_m80}")
    log(f"Final Jana handoff model: {selected_map}")
    return run_process([str(original), str(calc_m80)], cwd=cwd, log=log)


def run_jana_superflip(args: Sequence[str], options: JanaRunOptions, log: Callable[[str], None]) -> int:
    """Run the "Superflip only" and "Superflip + SharpED" (single-pass) workflows.

    Both workflows call superflip_original with Jana2020's own .inflip essentially
    unmodified (only reference/model overrides and, for the SharpED workflow, the
    XPLOR output keyword are injected in place, under the exact same file name Jana
    supplied) so Superflip's own output-file naming is never disturbed. Phase
    recycling (multiple cycles) is handled separately by the full Phase Studio
    pipeline; this function always performs exactly one Superflip call.
    """
    cwd = Path.cwd()
    exe_dir = application_dir()
    original = resolve_original_superflip(exe_dir)
    if not original.is_file():
        raise FileNotFoundError(
            f"Original Superflip was not found: {original}. "
            "Place it next to superflip.exe as superflip_original.exe."
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


def _show_missing_token_warning(parent: object, qt: dict[str, object]) -> None:
    report = build_error_report(
        RuntimeError("Missing SharpED API token."),
        subsystem="SharpED",
        operation="Validate Jana2020 launcher settings",
        severity="warning",
    )
    show_phase_studio_error(parent, report)


WORKFLOW_SUPERFLIP_ONLY = "superflip_only"
WORKFLOW_SUPERFLIP_SHARPED = "superflip_sharped"
WORKFLOW_PHASE_RECYCLING = "phase_recycling"
WORKFLOW_LABELS = {
    WORKFLOW_SUPERFLIP_ONLY: "Superflip only",
    WORKFLOW_SUPERFLIP_SHARPED: "Superflip + SharpED",
    WORKFLOW_PHASE_RECYCLING: "Phase recycling with Superflip + SharpED",
}
WORKFLOW_DESCRIPTIONS = {
    WORKFLOW_SUPERFLIP_ONLY: "Run one Superflip reconstruction and return the result to Jana2020.",
    WORKFLOW_SUPERFLIP_SHARPED: (
        "Run Superflip once, process the resulting map with SharpED, and return it to Jana2020."
    ),
    WORKFLOW_PHASE_RECYCLING: (
        "Iterate Superflip and SharpED over multiple cycles, using each selected map to "
        "initialize the next cycle."
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
        shared_value = str(self.shared_settings.value(f"inputs/{shared_key}", "") or "").strip()
        if shared_value:
            return shared_value
        legacy_value = str(self.settings.value(legacy_key, "") or "").strip()
        return legacy_value or fallback

    def _adjust_dialog_size(self) -> None:
        from phase_studio.app import apply_safe_dialog_geometry
        # dialog.adjustSize() alone under-sizes the window here: QScrollArea's
        # own sizeHint() does not reliably grow to match its contained page's
        # actual sizeHint (Qt quirk), so relying on it can leave the dialog
        # shorter than the current page truly needs -- forcing an unwanted
        # vertical scrollbar even though the page would otherwise fit
        # entirely. Compute the target size explicitly instead, from the
        # fixed chrome (brand header + context banner + footer) plus the
        # scrollable content's own required height, then let
        # apply_safe_dialog_geometry cap BOTH size and position to
        # availableGeometry() (excludes the taskbar) and re-center within it,
        # so the title bar can never end up unreachable as content grows.
        # Only the scrollable central content area (never this top-level
        # window) may still exceed the screen's usable height, for a page
        # taller than the whole screen can show at once.
        # Deliberately NOT max()'d against dialog.width()/height(): the
        # dialog must be able to shrink back down again too (e.g. going from
        # the taller page2 back to page1, or collapsing an expanded SharpED
        # disclosure) -- always resize from a fresh measurement of what the
        # CURRENT page actually needs, not whatever the dialog happened to be
        # sized to from an earlier call.
        self.dialog.adjustSize()
        footer_widget = self.chrome_holder["footer"]
        chrome_height = (
            self.brand_header.sizeHint().height()
            + self.context_banner.sizeHint().height()
            + (footer_widget.sizeHint().height() if footer_widget is not None else 0)
        )
        target_width = self.content.sizeHint().width() + 8
        # content.sizeHint() alone is unreliable here: it is computed at some
        # narrower candidate width, so word-wrapped labels (workflow card
        # descriptions, the Cell row, etc.) end up wrapping to more lines
        # than they actually will at target_width, overstating the needed
        # height by 100+ px. heightForWidth(target_width) asks for the real
        # answer at the width the dialog will actually use.
        content_height = (
            self.content.heightForWidth(target_width) if self.content.hasHeightForWidth()
            else self.content.sizeHint().height()
        )
        target_height = chrome_height + content_height + 8
        apply_safe_dialog_geometry(self.dialog, target_width, target_height)

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
        # group) -- reuses the same backing window (and therefore the same
        # HKL/.inflip parsing app.py itself uses) built for page1's summary.
        if self.detected_data_mode_holder["mode"] is None:
            try:
                backing_win = self._get_backing_window()
                self.detected_data_mode_holder["mode"] = backing_win._resolve_configured_data_mode_for_ui()
            except Exception:
                self.detected_data_mode_holder["mode"] = ""
        return self.detected_data_mode_holder["mode"]

    def _sync_page3_for_data_type(self) -> None:
        from phase_studio.app import (
            format_reflection_data_mode,
            reflection_mode_has_fwhm,
            resolve_powder_wavelength,
        )
        mode = self._detect_reflection_data_mode()
        is_powder = reflection_mode_has_fwhm(mode)
        self.reflection_type_value.setText("Powder / polycrystalline" if is_powder else "Single crystal")
        self.reflection_format_value.setText(format_reflection_data_mode(mode) if mode else "Not yet determined")
        self.page3_description.setText(
            "FWHM data detected. Powder overlap repartitioning is available."
            if is_powder
            else "Available feedback methods for single-crystal reflection data."
        )
        self.missing_group.setVisible(not is_powder)
        self.intensity_group.setVisible(not is_powder)
        self.powder_group.setVisible(is_powder)
        if is_powder and self.powder_wavelength_spin.value() <= 0:
            # Display default only (mirrors the main GUI's own
            # resolve_powder_wavelength() called again at actual run time) --
            # still fully editable, and 0 keeps its existing "auto" meaning
            # for the underlying algorithm if left untouched.
            try:
                ref_text = self.reference_file.text().strip()
                ref_path = Path(ref_text).expanduser() if ref_text else None
                detected_wavelength, _source = resolve_powder_wavelength(0.0, self.inflip_path, ref_path)
            except Exception:
                detected_wavelength = 0.0
            if detected_wavelength > 0:
                self.powder_wavelength_spin.setValue(detected_wavelength)
        self._adjust_dialog_size()

    def _check_page3_validity(self) -> Optional[str]:
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
            if checkbox.isVisible() and checkbox.isChecked() and spin.value() >= total_cycles:
                return "A subsequent cycle is required for map feedback."
        return None

    def _refresh_page3_validation_message(self) -> None:
        message = self._check_page3_validity()
        self.page3_validation_label.setText(message or "")
        self.page3_validation_label.setVisible(bool(message))

    def _current_workflow(self) -> str:
        return self.workflow_state["key"]

    def _apply_workflow_cycle_default(self, key: str) -> None:
        # "Superflip + SharpED" is always a single Superflip call followed by one
        # SharpED pass; only "Phase recycling" repeats that pair over several cycles.
        self.cycles.setEnabled(key == WORKFLOW_PHASE_RECYCLING)
        recompute_default = not (self.cycles_user_edited["value"] and key == WORKFLOW_PHASE_RECYCLING)
        self.cycles.blockSignals(True)
        try:
            # A single cycle never feeds a map back into a next cycle, so it
            # isn't actually "recycling" -- the spinbox's own minimum (not
            # just its default value) is raised to 2 for this workflow so the
            # control itself can't be turned down to a non-recycling value.
            self.cycles.setMinimum(2 if key == WORKFLOW_PHASE_RECYCLING else 1)
            if recompute_default:
                if key == WORKFLOW_PHASE_RECYCLING:
                    self.cycles.setValue(max(int(self.settings.value("cycles", 5)) or 5, 2))
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
        else:
            self.primary_button.setText("Next ›")
            self.primary_button.setToolTip("Continue to the SharpED and cycle settings.")

    def _workflow_changed(self) -> None:
        key = self._current_workflow()
        for card_key, card in self.workflow_cards.items():
            card.set_selected(card_key == key)
        cycles_visible = key == WORKFLOW_PHASE_RECYCLING
        self.cycles.setVisible(cycles_visible)
        if self.cycles_label is not None:
            self.cycles_label.setVisible(cycles_visible)
        if key != WORKFLOW_SUPERFLIP_ONLY:
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
            self.map_group.setVisible(key == WORKFLOW_PHASE_RECYCLING)
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

        self.dialog = QDialog()
        self.dialog.setWindowTitle(f"Phase Studio {__version__} for Jana2020")
        self.dialog.setMinimumWidth(640)

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

        self.inflip_info = QLabel(
            f"Jana2020 input: {inflip_path.name}" if inflip_path else "No .inflip argument was detected."
        )
        self.inflip_info.setToolTip(str(inflip_path) if inflip_path else "")
        self.root.addWidget(self.inflip_info)

        self.stack = QStackedWidget()
        self.root.addWidget(self.stack, 1)

        self._build_page1()
        self._build_page2()
        self._build_page3()

    # ----- Page 1: input summary, reference/model files, then the 3 primary workflow actions -----
    def _build_page1(self) -> None:
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
        self.page1_layout.setSpacing(8)

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
            section_layout.setSpacing(4)
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
            body_layout.setContentsMargins(0, 6, 0, 0)
            body_layout.setSpacing(4)
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

        self.input_summary_fields = QWidget()
        self.input_summary_layout = QFormLayout(self.input_summary_fields)
        self.input_summary_layout.setContentsMargins(0, 0, 0, 0)
        self.input_summary_layout.setVerticalSpacing(3)
        self.input_summary_layout.setHorizontalSpacing(10)
        self.input_summary_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.reflections_value = QLabel("Not available")
        self.format_value = QLabel("Not available")
        self.cell_value = QLabel("Not available")
        self.spacegroup_value = QLabel("Not available")
        self.composition_value = QLabel("Not available")
        for summary_label in (self.reflections_value, self.format_value, self.cell_value, self.spacegroup_value, self.composition_value):
            summary_label.setWordWrap(True)
        self.input_summary_layout.addRow("Reflections", self.reflections_value)
        self.input_summary_layout.addRow("Format", self.format_value)
        self.input_summary_layout.addRow("Cell", self.cell_value)
        self.input_summary_layout.addRow("Space group", self.spacegroup_value)
        self.input_summary_layout.addRow("Composition", self.composition_value)
        self.input_summary_outer.addWidget(self.input_summary_fields, 1)

        self.hkl_buttons_column = QVBoxLayout()
        self.hkl_buttons_column.setSpacing(4)
        self.validate_hkl_button = QPushButton("Validate HKL")
        self.analyze_completeness_button = QPushButton("Analyze completeness")
        self.hkl_buttons_column.addWidget(self.validate_hkl_button)
        self.hkl_buttons_column.addWidget(self.analyze_completeness_button)
        self.hkl_buttons_column.addStretch(1)
        self.input_summary_outer.addLayout(self.hkl_buttons_column)
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
                win = self._get_backing_window()
                from phase_studio.app import compact_spacegroup_symbol, format_reflection_data_mode
                request = win._collect_hkl_analysis_request()
                result = win._build_hkl_load_result(request)
            except Exception:
                # Per spec: never show a raw exception in this summary. The
                # existing structured error dialog still covers Validate HKL /
                # Analyze completeness themselves if the reflection block truly
                # cannot be analyzed.
                return
            self.reflections_value.setText(f"{len(result.reflections):,} parsed · {len(result.unique_reflections):,} unique")
            self.format_value.setText(format_reflection_data_mode(result.data_mode))
            rcell = result.cell
            self.cell_value.setText(
                f"{rcell.a:.5g} × {rcell.b:.5g} × {rcell.c:.5g} Å\n"
                f"{rcell.alpha:.4g}° × {rcell.beta:.4g}° × {rcell.gamma:.4g}°"
            )
            self.spacegroup_value.setText(f"{compact_spacegroup_symbol(result.spacegroup)} (#{result.spacegroup.number})")
            metadata = request.metadata
            self.composition_value.setText(metadata.composition if metadata is not None and metadata.composition else "—")
            self.validate_hkl_button.setEnabled(True)
            self.analyze_completeness_button.setEnabled(True)
            self.validate_hkl_button.setToolTip(
                "Parse the incoming Jana2020 .inflip reflection block and show which h, k, l, "
                "value, sigma and phase fields were read. Uses the same parser as Basic → Input."
            )
            self.analyze_completeness_button.setToolTip(
                "Open completeness and data-statistics plots for the incoming Jana2020 .inflip "
                "reflection data. Uses the same analysis as Basic → Input."
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
        QTimer.singleShot(0, refresh_input_summary)

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
            edit.setToolTip(
                (tooltip + "\n\nCurrently set from the incoming .inflip.") if from_inflip else tooltip
            )
            browse = QPushButton("Browse…")
            browse.setToolTip(f"Select {label_text.lower()}.")

            source_note = QLabel("From .inflip")
            source_note.setStyleSheet("color: #7183a6; font-style: italic;")
            source_note.setVisible(from_inflip)

            def browse_file() -> None:
                selected = QFileDialog.getOpenFileName(self.dialog, f"Select {label_text}", edit.text(), file_filter)[0]
                if selected:
                    edit.setText(selected)
                    # A manual replacement is no longer "from the .inflip".
                    source_note.setVisible(False)
                    edit.setToolTip(tooltip)

            browse.clicked.connect(browse_file)
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
            "Reference files (*.cif *.xplor);;CIF structures (*.cif);;XPLOR maps (*.xplor);;All files (*)",
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
            "Model/map files (*.xplor *.ccp4 *.cif);;XPLOR maps (*.xplor);;CCP4 maps (*.ccp4);;CIF structures (*.cif);;All files (*)",
            "Model or density map to seed the first Superflip cycle. If supplied, "
            "cycle 1 is model-seeded: repeatmode is forced to 1 and randomseed is omitted. "
            "Pre-filled from the incoming .inflip's own modelfile keyword, if it declares one.",
            "No first-cycle model",
            _inflip_keyword_default("modelfile"),
        )
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

        def workflow_card_clicked(key: str) -> None:
            self.workflow_state["key"] = key
            self._workflow_changed()

        # Workflow is the single most important choice on this page (it decides
        # the whole execution path) and must not blend in as one more same-weight
        # section -- it gets the same lightweight sectionLabel heading as Input
        # summary / Reference and initial model above, plus the explicit
        # "Choose one of three workflows." helper text called for in the spec.
        self.workflow_section, self.workflow_body = build_page1_section("Workflow", "Choose one of three workflows.")
        self.workflow_body.setSpacing(5)
        self.workflow_cards: dict[str, "_WorkflowCard"] = {}
        for key in (WORKFLOW_SUPERFLIP_ONLY, WORKFLOW_SUPERFLIP_SHARPED, WORKFLOW_PHASE_RECYCLING):
            card = _WorkflowCard(key, WORKFLOW_LABELS[key], WORKFLOW_DESCRIPTIONS[key], workflow_card_clicked)
            card.setToolTip("Select this workflow, then use Run phasing / Next below to proceed.")
            self.workflow_body.addWidget(card)
            self.workflow_cards[key] = card

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
        self.page2_layout.setSpacing(10)

        self.map_group = QGroupBox("Map used for Jana2020 handoff")
        self.map_group_layout = QVBoxLayout(self.map_group)
        self.map_buttons = QButtonGroup(self.dialog)
        self.sharped_map_radio = QRadioButton("SharpED map")
        self.superflip_map_radio = QRadioButton("Superflip map")
        self.sharped_map_radio.setToolTip(
            "Use the SharpED map for the next phase-recycling cycle and for the Jana2020 handoff."
        )
        self.superflip_map_radio.setToolTip(
            "Use the Superflip map for the next phase-recycling cycle and for the Jana2020 handoff."
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

        self.cycles = QSpinBox()
        self.cycles.setRange(1, 999)
        self.cycles.setValue(int(self.settings.value("cycles", 1)) or 1)
        self.cycles.setToolTip("Number of Superflip/SharpED phase-recycling cycles.")
        self.processing_form.addRow("Recycling cycles", self.cycles)
        self.cycles_label = self.processing_form.labelForField(self.cycles)

        self.cycles_user_edited = {"value": False}

        def mark_cycles_user_edited(_value: int = 0) -> None:
            self.cycles_user_edited["value"] = True

        self.cycles.valueChanged.connect(mark_cycles_user_edited)

        self.model = QComboBox()
        self.model.setEditable(True)
        saved_model = str(self.settings.value("model", "default")).strip() or "default"
        self.model.addItem(saved_model)
        if saved_model != "default":
            self.model.insertItem(0, "default")
        self.model.setCurrentText(saved_model)
        self.model.setToolTip(
            "SharpED inference model. Select a model returned by the server or enter an "
            "explicit model identifier. The value 'default' requests the server default."
        )
        self.processing_form.addRow("Model", self.model)
        self.page2_layout.addLayout(self.processing_form)

        self.refresh_row = QWidget()
        self.refresh_layout = QHBoxLayout(self.refresh_row)
        self.refresh_layout.setContentsMargins(0, 0, 0, 0)
        self.refresh_models_button = QPushButton("Refresh models")
        self.refresh_models_button.setToolTip("Query the SharpED server for its currently available models.")
        self.model_status = QLabel("Model list not loaded.")
        self.model_status.setWordWrap(True)
        self.model_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.refresh_layout.addWidget(self.refresh_models_button)
        self.refresh_layout.addWidget(self.model_status, 1)
        self.page2_layout.addWidget(self.refresh_row)

        self.sharped_group = QGroupBox()
        self.sharped_outer = QVBoxLayout(self.sharped_group)
        self.sharped_toggle = QToolButton()
        self.sharped_toggle.setObjectName("disclosureToggle")
        self.sharped_toggle.setText("SharpED settings")
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

        self.server_url = QLineEdit(self._shared_or_legacy_value("sharped_base_url", "server_url", DEFAULT_SERVER_URL))
        self.server_url.setPlaceholderText(DEFAULT_SERVER_URL)
        self.server_url.setToolTip(
            "Base URL of the SharpED service used for model discovery and map processing. "
            "Shared with the full Phase Studio application's own Advanced → Setup value."
        )
        self.sharped_form.addRow("Server URL", self.server_url)

        self.api_token = QLineEdit(
            self._shared_or_legacy_value("sharped_api_token", "api_token", os.environ.get("SHARPED_API_TOKEN", ""))
        )
        self.api_token.setEchoMode(QLineEdit.Password)
        self.api_token.setPlaceholderText("Enter API token")
        self.api_token.setToolTip(
            "Bearer token used to authorize SharpED processing. The token is masked in "
            "the interface, may alternatively be supplied through SHARPED_API_TOKEN, and "
            "is shared with the full Phase Studio application's own API token -- saving it "
            "here also updates that copy, and vice versa."
        )
        self.sharped_form.addRow("API token", self.api_token)

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
            self._adjust_dialog_size()

        self.sharped_toggle.toggled.connect(sync_sharped_disclosure)
        self.page2_layout.addWidget(self.sharped_group)

        self.refresh_results: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.refresh_timer = QTimer(self.dialog)
        self.refresh_timer.setInterval(100)

        def refresh_available_models() -> None:
            base_url = self.server_url.text().strip() or DEFAULT_SERVER_URL
            self.refresh_models_button.setEnabled(False)
            self.model_status.setText("Contacting the SharpED server…")

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
            if state == "error":
                self.model_status.setText("Unable to retrieve the model list.")
                self.model_status.setToolTip(
                    "Model discovery failed. Verify the server URL and network connection; "
                    "a model identifier may still be entered manually.\n\n"
                    + sanitize_error_details(payload)
                )
                return

            models_result = payload
            current = self.model.currentText().strip() or "default"
            values: List[str] = ["default"]
            default_model = str(getattr(models_result, "default_model", "") or "").strip()
            if default_model and default_model not in values:
                values.append(default_model)
            for available in list(getattr(models_result, "models", []) or []):
                value = str(available).strip()
                if value and value not in values:
                    values.append(value)

            self.model.blockSignals(True)
            self.model.clear()
            self.model.addItems(values)
            self.model.setCurrentText(current if current in values else "default")
            self.model.blockSignals(False)
            if default_model:
                self.model_status.setText(f"{len(values) - 1} models available · Default: {default_model}")
            else:
                self.model_status.setText(f"{len(values) - 1} models available")

        self.refresh_models_button.clicked.connect(refresh_available_models)
        self.refresh_timer.timeout.connect(poll_model_refresh)

        self.validation_group = QGroupBox("Scientific validation")
        self.validation_layout = QHBoxLayout(self.validation_group)
        self.warning_icon = QLabel()
        self.warning_icon.setPixmap(self.dialog.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(28, 28))
        self.warning_icon.setAlignment(Qt.AlignTop)
        self.validation_layout.addWidget(self.warning_icon, 0, Qt.AlignTop)
        self.warning_text = QLabel(
            "SharpED uses a neural-network density-processing model. Its output may "
            "contain artifacts and should be validated against the measured "
            "diffraction data and an independent crystallographic refinement."
        )
        self.warning_text.setWordWrap(True)
        self.validation_layout.addWidget(self.warning_text, 1)
        self.page2_layout.addWidget(self.validation_group)

        # Phase recycling only: maps directly onto the existing full-pipeline
        # compute_omit_maps / compute_omit_rfree settings (see build_jana_handoff_import).
        # Not shown for either single-pass workflow, which never reaches that pipeline.
        self.cross_validation_group = QGroupBox("Cross-validation")
        self.cross_validation_layout = QVBoxLayout(self.cross_validation_group)
        self.omit_checkbox = QCheckBox("Compute OMIT validation maps")
        self.omit_checkbox.setToolTip(
            "Each cycle, additionally run Superflip (and SharpED, if enabled) on a fixed "
            "random 5% holdout of reflections excluded from the input, for cross-validation. "
            "Feeds the phase-recycling result selector's Selection score, helping identify the "
            "most suitable map among the recycling cycles. Roughly doubles Superflip/SharpED "
            "time per cycle."
        )
        self.rfree_checkbox = QCheckBox("Calculate R_free")
        self.rfree_checkbox.setToolTip(
            "Compute R_free (the crystallographic R-factor between the excluded holdout "
            "reflections' observed |F| and |F| calculated by FFT from the omit map) for each "
            "cycle. Feeds the phase-recycling result selector's Selection score alongside OMIT "
            "correlation, helping rank cycles and choose the most suitable map. Requires "
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
            self.rfree_checkbox.setEnabled(omit_enabled)
            if not omit_enabled and self.rfree_checkbox.isChecked():
                self.rfree_checkbox.setChecked(False)

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
        self.page3_layout.setSpacing(10)

        self.reflection_data_group = QGroupBox("Reflection data")
        self.reflection_data_form = QFormLayout(self.reflection_data_group)
        self.reflection_data_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.reflection_type_value = QLabel("")
        self.reflection_format_value = QLabel("")
        self.reflection_data_form.addRow("Type", self.reflection_type_value)
        self.reflection_data_form.addRow("Format", self.reflection_format_value)
        self.page3_layout.addWidget(self.reflection_data_group)

        self.page3_description = QLabel("")
        self.page3_description.setWordWrap(True)
        self.page3_description.setStyleSheet("color: #52658b;")
        self.page3_layout.addWidget(self.page3_description)

        # Same "Warning" message and icon+text presentation as the "Scientific
        # validation" box above (and Basic -> Map feedback's settings_callout in
        # the main GUI) -- always visible on this page, regardless of whether
        # any option below is enabled.
        self.map_feedback_warning_group = QGroupBox()
        self.map_feedback_warning_layout = QHBoxLayout(self.map_feedback_warning_group)
        self.map_feedback_warning_icon = QLabel()
        self.map_feedback_warning_icon.setPixmap(self.dialog.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(28, 28))
        self.map_feedback_warning_icon.setAlignment(Qt.AlignTop)
        self.map_feedback_warning_layout.addWidget(self.map_feedback_warning_icon, 0, Qt.AlignTop)
        self.map_feedback_warning_text = QLabel(
            "<b>Warning</b><br>"
            "The operations on this page modify the reflection data supplied to subsequent cycles. "
            "Results from these cycles should therefore be validated against the original measured data."
        )
        self.map_feedback_warning_text.setTextFormat(Qt.RichText)
        self.map_feedback_warning_text.setWordWrap(True)
        self.map_feedback_warning_layout.addWidget(self.map_feedback_warning_text, 1)
        self.page3_layout.addWidget(self.map_feedback_warning_group)

        # --- Single-crystal branch: Missing-reflection completion + Intensity
        # correction, exactly Basic -> Map feedback's own controls/defaults/
        # ranges/tooltips. ---
        self.missing_group = QGroupBox("Missing-reflection completion")
        self.missing_outer = QVBoxLayout(self.missing_group)
        self.missing_enabled_checkbox = QCheckBox("Enable missing-reflection completion")
        self.missing_outer.addWidget(self.missing_enabled_checkbox)
        self.missing_form = QFormLayout()
        self.missing_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
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
        self.missing_outer.addLayout(self.missing_form)
        self.page3_layout.addWidget(self.missing_group)

        self.intensity_group = QGroupBox("Intensity correction")
        self.intensity_outer = QVBoxLayout(self.intensity_group)
        self.intensity_enabled_checkbox = QCheckBox("Enable intensity correction")
        self.intensity_outer.addWidget(self.intensity_enabled_checkbox)
        self.intensity_form = QFormLayout()
        self.intensity_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
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
        self.intensity_sigma_spin.setToolTip(
            "Apply map-based intensity correction only to non-zero reflections with value/sigma "
            "below this limit. Use 0 to correct all non-zero reflections -- including reflection "
            "formats with no sigma column, since the value/sigma gate is then simply not applied."
        )
        self.intensity_form.addRow("Apply when value/σ <", self.intensity_sigma_spin)
        self.intensity_outer.addLayout(self.intensity_form)
        self.intensity_note = QLabel("Value/σ = 0 applies correction to all non-zero reflections.")
        self.intensity_note.setWordWrap(True)
        self.intensity_note.setStyleSheet("color: #52658b;")
        self.intensity_outer.addWidget(self.intensity_note)
        self.page3_layout.addWidget(self.intensity_group)

        # --- Powder/FWHM branch: Powder overlap repartitioning, exactly Basic ->
        # Map feedback's own controls/defaults/ranges/tooltips. ---
        self.powder_group = QGroupBox("Powder overlap repartitioning")
        self.powder_outer = QVBoxLayout(self.powder_group)
        self.powder_enabled_checkbox = QCheckBox("Enable powder overlap repartitioning (FWHM data)")
        self.powder_outer.addWidget(self.powder_enabled_checkbox)
        self.powder_form = QFormLayout()
        self.powder_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
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
        self.powder_wavelength_spin.setDecimals(5)
        self.powder_wavelength_spin.setValue(0.0)
        self.powder_wavelength_spin.setToolTip(
            "Required to compute 2θ. Auto-detected -- when left at 0 -- from the Jana2020 .inflip "
            "file, then the reference file; enter it manually if neither source has it."
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
        self.powder_outer.addLayout(self.powder_form)
        self.powder_note = QLabel(
            "Only applies to reflections with an FWHM value (hkl I/F fwhm data)."
        )
        self.powder_note.setWordWrap(True)
        self.powder_note.setStyleSheet("color: #52658b;")
        self.powder_outer.addWidget(self.powder_note)
        self.page3_layout.addWidget(self.powder_group)

        self.page3_validation_label = QLabel("")
        self.page3_validation_label.setWordWrap(True)
        self.page3_validation_label.setObjectName("wizardValidationMessage")
        self.page3_validation_label.setStyleSheet("color: #b42318;")
        self.page3_validation_label.setVisible(False)
        self.page3_layout.addWidget(self.page3_validation_label)

        self.page3_layout.addStretch(1)
        self.stack.addWidget(self.page3)

        # Every fresh Wizard invocation starts every Map feedback checkbox OFF --
        # deliberately NOT restored from QSettings (same reasoning as the Cross-
        # validation checkboxes on page2: this is job-specific state, not
        # something that should silently carry over from an unrelated previous
        # Jana2020 job). The default-off state above already satisfies this; no
        # settings.value(...) read is ever wired to these controls.

        def sync_missing_dependency(_checked: bool = False) -> None:
            enabled = self.missing_enabled_checkbox.isChecked()
            self.missing_start_cycle_spin.setEnabled(enabled)
            self.missing_percent_spin.setEnabled(enabled)

        self.missing_enabled_checkbox.toggled.connect(sync_missing_dependency)
        sync_missing_dependency()

        def sync_intensity_dependency(_checked: bool = False) -> None:
            enabled = self.intensity_enabled_checkbox.isChecked()
            self.intensity_start_cycle_spin.setEnabled(enabled)
            self.intensity_damping_spin.setEnabled(enabled)
            self.intensity_sigma_spin.setEnabled(enabled)

        self.intensity_enabled_checkbox.toggled.connect(sync_intensity_dependency)
        sync_intensity_dependency()

        def sync_powder_dependency(_checked: bool = False) -> None:
            enabled = self.powder_enabled_checkbox.isChecked()
            self.powder_start_cycle_spin.setEnabled(enabled)
            self.powder_wavelength_spin.setEnabled(enabled)
            self.powder_separation_spin.setEnabled(enabled)
            self.powder_mix_spin.setEnabled(enabled)

        self.powder_enabled_checkbox.toggled.connect(sync_powder_dependency)
        sync_powder_dependency()

        self.detected_data_mode_holder: dict = {"mode": None}





        for _spin in (self.missing_start_cycle_spin, self.intensity_start_cycle_spin, self.powder_start_cycle_spin):
            _spin.valueChanged.connect(lambda _value=0: self._refresh_page3_validation_message())
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
        # `root`/content_layout), so Back/Cancel/Open config/Run phasing always
        # stay visible above the taskbar regardless of how tall the scrollable
        # page content above them gets (spec: "WIZARD WINDOW SIZING" sections
        # 5/8). A prominent "Run" action on page 2 plus the less prominent
        # Back / Cancel / Open full Phase Studio actions. -----
        self.footer = QWidget()
        self.footer.setObjectName("wizardFooter")
        self.button_row = QHBoxLayout(self.footer)
        self.button_row.setContentsMargins(14, 8, 14, 12)
        self.back_button = QPushButton("‹ Back")
        self.back_button.setToolTip("Return to the workflow selection.")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setToolTip("Close the launcher without starting or modifying the Jana2020 job.")
        self.edit_button = QPushButton("Open full configuration")
        self.edit_button.setToolTip(
            "Open the complete Phase Studio workspace with parameters imported from the "
            "Jana2020 .inflip file. Embedded reflections are exported to a working HKL file "
            "unless an external HKL override is selected there."
        )
        self.primary_button = QPushButton("Run phasing")
        self.primary_button.setObjectName("primaryButton")
        self.primary_button.setDefault(True)
        self.button_row.addWidget(self.back_button)
        self.button_row.addStretch(1)
        self.button_row.addWidget(self.cancel_button)
        self.button_row.addWidget(self.edit_button)
        self.button_row.addWidget(self.primary_button)
        self.outer_root.addWidget(self.footer)
        self.chrome_holder["footer"] = self.footer





        self._workflow_changed()

        self.PAGE2_BANNER_TEXT = {
            WORKFLOW_SUPERFLIP_SHARPED: ("SUPERFLIP + SHARPED", "Configure the map returned to Jana2020"),
            WORKFLOW_PHASE_RECYCLING: ("PHASE RECYCLING", "Configure iterative reconstruction and validation"),
        }

        def go_to_page1() -> None:
            self.stack.setCurrentWidget(self.page1)
            self.back_button.setVisible(False)
            self._sync_primary_button_for_page1()
            self.context_title_label.setText("JANA2020 WORKFLOW")
            self.context_subtitle_label.setText("Review the incoming crystallographic data and choose a workflow")
            self._adjust_dialog_size()

        def go_to_page2() -> None:
            self.stack.setCurrentWidget(self.page2)
            self.back_button.setVisible(True)
            if self._current_workflow() == WORKFLOW_PHASE_RECYCLING:
                # Phase recycling alone continues to a third page (Map feedback)
                # before anything runs; Superflip + SharpED has no such page and
                # keeps running directly from here.
                self.primary_button.setText("Next ›")
                self.primary_button.setToolTip("Continue to the Map feedback settings.")
            else:
                self.primary_button.setText("Run phasing")
                self.primary_button.setToolTip(
                    "Execute the Jana2020 Superflip job through the Phase Studio cycle wrapper. "
                    "For every model-seeded cycle, repeatmode 1 is enforced and randomseed is omitted."
                )
            banner_title, banner_subtitle = self.PAGE2_BANNER_TEXT.get(
                self._current_workflow(), ("JANA2020 WORKFLOW", "")
            )
            self.context_title_label.setText(banner_title)
            self.context_subtitle_label.setText(banner_subtitle)
            self._adjust_dialog_size()

        def go_to_page3() -> None:
            self._sync_page3_for_data_type()
            self._refresh_page3_validation_message()
            self.stack.setCurrentWidget(self.page3)
            self.back_button.setVisible(True)
            self.primary_button.setText("Run phasing")
            self.primary_button.setToolTip(
                "Execute the Jana2020 Superflip job through the Phase Studio cycle wrapper. "
                "For every model-seeded cycle, repeatmode 1 is enforced and randomseed is omitted."
            )
            self.context_title_label.setText("PHASE RECYCLING · MAP FEEDBACK")
            self.context_subtitle_label.setText("Optionally update reflection data between recycling cycles")
            self._adjust_dialog_size()

        def go_back() -> None:
            if self.stack.currentWidget() is self.page3:
                go_to_page2()
            else:
                go_to_page1()

        self.back_button.clicked.connect(go_back)
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
            # PAGE 3 is Phase-recycling-only; its controls must never leak
            # through for either single-pass workflow even if somehow toggled.
            return self._current_workflow() == WORKFLOW_PHASE_RECYCLING

        def save_values() -> None:
            next_cycle_mode = effective_next_cycle_mode()
            self.settings.setValue("workflow", self._current_workflow())
            self.settings.setValue("cycles", effective_cycles())
            self.settings.setValue("next_cycle_modelfile", next_cycle_mode)
            self.settings.setValue("use_deblurred_map", next_cycle_mode == "deblurred_xplor")
            # SharpED server URL / API token are the shared credentials also used by
            # the full Phase Studio application; write them there, not to a second,
            # independent copy under this wrapper's own settings (see shared_settings
            # above for why: two copies drift and silently overwrite one another).
            self.shared_settings.setValue("inputs/sharped_base_url", self.server_url.text())
            self.shared_settings.setValue("inputs/sharped_api_token", self.api_token.text())
            self.shared_settings.sync()
            self.settings.setValue("model", self.model.currentText())
            # Elements and Output resolution have no control of their own here
            # any more -- they come from the shared full-application settings (see
            # effective_elements()/effective_outres()) and are not re-persisted.
            # Reference file / model file are deliberately not persisted: they should
            # reflect the incoming .inflip (or be blank), never a leftover value from
            # an unrelated previous Jana2020 job.
            self.settings.sync()

        def build_options(action: str) -> JanaRunOptions:
            next_cycle_mode = effective_next_cycle_mode()
            return JanaRunOptions(
                action=action,
                cycles=effective_cycles(),
                use_deblurred_map=next_cycle_mode == "deblurred_xplor",
                next_cycle_modelfile=next_cycle_mode,
                api_token=self.api_token.text().strip(),
                server_url=self.server_url.text().strip() or DEFAULT_SERVER_URL,
                model=self.model.currentText().strip() or "default",
                elements=effective_elements(),
                outres=effective_outres(),
                input_mode=INPUT_MODE_INFLIP,
                hkl_override="",
                reference_override="",
                superflip_referencefile=self.reference_file.text().strip(),
                first_cycle_modelfile=self.model_file.text().strip(),
                compute_omit_maps=effective_compute_omit_maps(),
                compute_omit_rfree=effective_compute_omit_rfree(),
                enable_missing_completion=effective_map_feedback_enabled() and self.missing_enabled_checkbox.isChecked(),
                missing_start_cycle=self.missing_start_cycle_spin.value(),
                missing_max_added_percent=self.missing_percent_spin.value(),
                enable_intensity_correction=effective_map_feedback_enabled() and self.intensity_enabled_checkbox.isChecked(),
                intensity_start_cycle=self.intensity_start_cycle_spin.value(),
                intensity_damping=self.intensity_damping_spin.value(),
                intensity_sigma_threshold=self.intensity_sigma_spin.value(),
                enable_powder_repartition=effective_map_feedback_enabled() and self.powder_enabled_checkbox.isChecked(),
                powder_start_cycle=self.powder_start_cycle_spin.value(),
                powder_wavelength=self.powder_wavelength_spin.value(),
                powder_separation_factor=self.powder_separation_spin.value(),
                powder_map_ratio_mix=self.powder_mix_spin.value(),
            )

        def attempt_run() -> None:
            if self.stack.currentWidget() is self.page1 and self._current_workflow() != WORKFLOW_SUPERFLIP_ONLY:
                go_to_page2()
                return
            if self.stack.currentWidget() is self.page3:
                validation_message = self._check_page3_validity()
                if validation_message:
                    self._refresh_page3_validation_message()
                    return
                save_values()
                self.result["action"] = "recycle"
                self.dialog.accept()
                return
            token = self.api_token.text().strip() or os.environ.get("SHARPED_API_TOKEN", "").strip()
            if effective_next_cycle_mode() == "deblurred_xplor" and not token:
                if self.stack.currentWidget() is not self.page2:
                    go_to_page2()
                self.sharped_toggle.setChecked(True)
                self.api_token.setFocus()
                _show_missing_token_warning(self.dialog, qt)
                return
            if self.stack.currentWidget() is self.page2 and self._current_workflow() == WORKFLOW_PHASE_RECYCLING:
                go_to_page3()
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

        self.primary_button.clicked.connect(attempt_run)
        self.edit_button.clicked.connect(edit_clicked)
        self.cancel_button.clicked.connect(self.dialog.reject)

        # Word-wrapped labels' heightForWidth() is not fully trustworthy until
        # the widget tree has actually been laid out and polished at least once,
        # so the synchronous adjust_dialog_size() calls made during construction
        # above can overstate the needed height. A second pass once the dialog's
        # event loop has actually started (same deferred-refit pattern used for
        # the HKL Completeness dialog in app.py) settles it accurately.
        QTimer.singleShot(0, self._adjust_dialog_size)

        accepted = self.dialog.exec()
        self.refresh_timer.stop()
        if not accepted:
            return JanaRunOptions(action="cancel")
        return build_options(self.result["action"])


def show_jana_dialog(args: Sequence[str], inflip_path: Optional[Path]) -> JanaRunOptions:
    return _JanaWorkflowWizard(args, inflip_path).run()


def launch_phase_studio_from_jana(
    inflip_path: Optional[Path], options: JanaRunOptions, auto_start: bool = False
) -> int:
    # Load PySide6 before importing app.py, which initializes Matplotlib QtAgg.
    qt = _qt_imports()
    QApplication = qt["QApplication"]

    from phase_studio.app import (
        IterativeSuperflipPipelineQtGUI,
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
                "superflip" if options.next_cycle_modelfile == "superflip_xplor" else "deblurred"
            )
            # Fill every EDMA/Superflip setting the dialog and the .inflip don't
            # cover with Phase Studio's own "recommended" preset first, so the
            # values applied below (this Jana2020 run's explicit choices) win.
            win._apply_workflow_preset("recommended")
        else:
            # "Open full configuration": the user drives the whole workflow
            # manually and explicitly clicks Send to Jana2020 once a run
            # completes -- no auto-selected map source, no auto-start.
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
            if auto_start:
                win._append_execution_log(
                    "[Jana2020] Phase recycling requested · calculation will start automatically",
                    level="DETAIL",
                    subsystem="Jana2020",
                )
            else:
                win._append_execution_log(
                    "After the full pipeline finishes, use the 'Send to Jana2020' button to choose the cycle and map source for the final Jana2020 handoff.",
                    level="DETAIL",
                    subsystem="Jana2020",
                )
        win.setWindowTitle(f"Phase Studio {__version__} for Jana2020")
        return win

    win = initialize_main_window(app, splash, build_window)
    if win is None:
        return 1
    if auto_start:
        win.start_run()
    return int(app.exec())


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    args = argv[1:]
    exe_dir = application_dir()
    logger = JanaLogger(exe_dir / "log.txt")
    try:
        logger("Phase Studio Jana Superflip wrapper started")
        logger(f"Executable dir: {exe_dir}")
        logger(f"Current working dir: {Path.cwd()}")
        logger(f"Received arguments count: {len(args)}")
        for i, arg in enumerate(args, 1):
            logger(f"arg[{i}] = {arg}")
        if not args:
            logger("No arguments; opening Phase Studio GUI.")
            return launch_phase_studio_from_jana(None, JanaRunOptions(action="edit"))

        inflip_info = find_inflip_arg(args, Path.cwd())
        inflip_path = inflip_info[1] if inflip_info else None
        options = show_jana_dialog(args, inflip_path)
        if options.action == "cancel":
            logger("Cancelled by user.")
            return 1
        if options.action == "edit":
            logger("Opening full Phase Studio GUI.")
            return launch_phase_studio_from_jana(inflip_path, options)
        if options.action == "recycle":
            logger("Phase recycling requested; running it through the full Phase Studio pipeline.")
            return launch_phase_studio_from_jana(inflip_path, options, auto_start=True)
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
            show_phase_studio_error(None, report)
        except Exception:
            pass
        return 1
    finally:
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main())
