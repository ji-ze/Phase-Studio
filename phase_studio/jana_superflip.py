#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jana2020-compatible Superflip launcher.

This module is intended to be frozen as superflip.exe and placed where Jana
normally finds the Superflip-for-Jana wrapper. The original Superflip binary is
expected next to it as superflip_original.exe.
"""

from __future__ import annotations

import locale
import math
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
    from phase_studio.sharped_server_client import SharpEDServerClient
except Exception:
    from sharped_server_client import SharpEDServerClient

try:
    from phase_studio.ui_style import apply_phase_studio_style
except Exception:
    from ui_style import apply_phase_studio_style


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
    app_input_label = {
        INPUT_MODE_INFLIP: "Jana .inflip",
        INPUT_MODE_INFLIP_OVERRIDES: "Jana .inflip with external HKL/reference overrides",
        INPUT_MODE_EXTERNAL: "External HKL + CIF reference",
    }[input_mode]
    allow_external_sources = input_mode in {INPUT_MODE_INFLIP_OVERRIDES, INPUT_MODE_EXTERNAL}
    explicit_hkl = _resolved_handoff_path(options.hkl_override, base_dir) if allow_external_sources else ""
    explicit_reference = _resolved_handoff_path(options.reference_override, base_dir) if allow_external_sources else ""
    explicit_superflip_reference = _resolved_handoff_path(options.superflip_referencefile, base_dir)
    explicit_first_model = _resolved_handoff_path(options.first_cycle_modelfile, base_dir)

    handoff_values = {
        "input_source_mode": app_input_label,
        "jana_inflip": str(inflip_path),
        "work_dir": str(base_dir / f"phase_studio_full_run_{inflip_path.stem}"),
        "superflip_exe": str(DEFAULT_JANA_SUPERFLIP),
        "edma_exe": str(DEFAULT_JANA_EDMA),
        "cycles": str(options.cycles),
        "run_sharped": "true" if options.next_cycle_modelfile == "deblurred_xplor" else "false",
        "sharped_base_url": options.server_url,
        "sharped_api_token": options.api_token,
        "sharped_model": options.model,
        "sharped_elements": options.elements,
        "sharped_outres": str(options.outres),
        "modelfile_source": options.next_cycle_modelfile,
        "export_superflip_xplor": "true",
        "export_superflip_jana": "true",
        "hkl": explicit_hkl,
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
    applied = set(applied_keys)
    imported_inflip_keys = [key for key in handoff.inflip_keys if key in applied]
    lines = [
        "Jana2020 hand-off detected.",
        f"Primary input: {Path(inflip_path).name}",
        f"Working directory: {handoff.values.get('work_dir', '')}",
        f"Input data mode: {handoff.input_mode}",
        f"Reflection source: {handoff.reflection_source}",
        f"Reference source shown in GUI: {handoff.reference_source}",
        f"Imported {len(imported_inflip_keys)} mapped .inflip parameter(s).",
    ]
    if "reflection_data_mode" in imported_inflip_keys:
        lines.append(f"Imported HKL format: {handoff.values['reflection_data_mode']}")
    lines.extend(f"Import note: {limitation}" for limitation in handoff.limitations)
    return lines


@dataclass
class JanaCycleMetrics:
    saved_run: Optional[int] = None
    rvalue: Optional[float] = None
    peaks: Optional[float] = None
    symm: Optional[float] = None
    derived_sg: str = ""
    fom: Optional[float] = None
    success_rate: Optional[float] = None
    mean_cycles: Optional[float] = None


@dataclass
class JanaCycleResult:
    cycle: int
    superflip_map: Path
    deblurred_map: Optional[Path]
    sflog_path: Optional[Path] = None
    saved_run: Optional[int] = None
    rvalue: Optional[float] = None
    peaks: Optional[float] = None
    symm: Optional[float] = None
    derived_sg: str = ""
    fom: Optional[float] = None
    success_rate: Optional[float] = None
    mean_cycles: Optional[float] = None




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
        text = str(message)
        print(text, flush=True)
        self._fh.write(text + "\n")
        self._fh.flush()


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def text_encoding() -> str:
    if os.name == "nt":
        return "mbcs"
    return locale.getpreferredencoding(False) or "utf-8"


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


def _safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def _safe_int(value: str) -> int:
    return int(round(_safe_float(value, 0.0)))


def _float7_text(value: float) -> str:
    try:
        x = float(value)
        if not math.isfinite(x):
            x = 0.0
    except Exception:
        x = 0.0
    return f"{x:.7f}"


def calculate_jana_dataitemwidths(records: Sequence[Tuple[int, int, int, float, float, float]]) -> Tuple[int, int, int]:
    """Calculate dataitemwidths from the exact reflection records to be written."""
    if not records:
        return 4, 14, 14
    max_index_len = 1
    max_float_len = 1
    for h, k, l, value, phase, sigma in records:
        max_index_len = max(max_index_len, len(str(int(h))), len(str(int(k))), len(str(int(l))))
        max_float_len = max(max_float_len, len(_float7_text(value)), len(_float7_text(phase)), len(_float7_text(sigma)))
    # Keep at least one leading character before the longest signed index.
    hkl_width = max(4, max_index_len + 1)
    item_width = max(14, max_float_len + 1)
    return hkl_width, item_width, item_width


def format_jana_reflection_record(
    h: int,
    k: int,
    l: int,
    value: float,
    phase: float = 0.0,
    sigma: float = 0.0,
    widths: Tuple[int, int, int] = (4, 14, 14),
) -> str:
    """Return a Jana/Superflip fixed-width fbegin record matching dataitemwidths."""
    hkl_width, value_width, sigma_width = widths
    phase_width = sigma_width
    return (
        f"{int(h):{hkl_width}d}"
        f"{int(k):{hkl_width}d}"
        f"{int(l):{hkl_width}d}"
        f"{float(value):{value_width}.7f}"
        f"{float(phase):{phase_width}.7f}"
        f"{float(sigma):{sigma_width}.7f}"
    )


def normalize_hkl_override_for_jana_fbegin(hkl_path: Path) -> Tuple[List[str], str]:
    """Parse an external HKL-like file and return Jana-compatible fbegin lines and dataitemwidths."""
    records: List[Tuple[int, int, int, float, float, float]] = []
    for raw in read_text_lines(hkl_path):
        stripped = raw.strip()
        if not stripped or stripped.startswith(COMMENT_MARKERS):
            continue
        parts = stripped.split()
        if len(parts) < 4:
            continue
        try:
            h, k, l = _safe_int(parts[0]), _safe_int(parts[1]), _safe_int(parts[2])
            value = _safe_float(parts[3], 0.0)
            if len(parts) >= 6:
                phase = _safe_float(parts[4], 0.0)
                sigma = _safe_float(parts[5], 0.0)
            elif len(parts) >= 5:
                phase = 0.0
                sigma = _safe_float(parts[4], 0.0)
            else:
                phase = 0.0
                sigma = 0.0
            records.append((h, k, l, value, phase, sigma))
        except Exception:
            continue
    if not records:
        raise ValueError(f"The selected HKL override contains no readable reflection records: {hkl_path}")
    widths = calculate_jana_dataitemwidths(records)
    lines = [format_jana_reflection_record(h, k, l, value, phase, sigma, widths) for h, k, l, value, phase, sigma in records]
    return lines, f"{widths[0]} {widths[1]} {widths[2]}"


def ensure_jana_dataitemwidths(lines: Sequence[str], dataitemwidths: str) -> List[str]:
    """Use the fixed-width Jana fbegin layout expected by normalized overrides."""
    cleaned = without_keywords(lines, {"dataformat", "dataitemwidths"})
    return insert_before_fbegin(cleaned, f"dataitemwidths {dataitemwidths}")


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


def add_xplor_modelfile(lines: Sequence[str], model_name: str) -> List[str]:
    return add_modelseed_modelfile(lines, model_name, ".xplor")


def replace_fbegin_with_hkl(lines: Sequence[str], hkl_path: Path) -> List[str]:
    """Replace the embedded reflection block with a normalized external HKL file.

    The selected file can be whitespace-delimited, but the inserted Superflip
    block is always written as Jana-compatible fixed-width ``h k l F phase
    sigma`` records with automatically generated ``dataitemwidths``.
    """
    reflections, dataitemwidths = normalize_hkl_override_for_jana_fbegin(hkl_path)
    source_lines = ensure_jana_dataitemwidths(lines, dataitemwidths)

    out: List[str] = []
    in_block = False
    found = False
    for line in source_lines:
        key = first_token(line)
        if not in_block and key == "fbegin":
            found = True
            in_block = True
            out.append(line)
            out.extend(reflections)
            continue
        if in_block:
            if key == "endf":
                out.append(line)
                in_block = False
            continue
        out.append(line)
    if not found:
        out.extend(["fbegin", *reflections, "endf"])
    elif in_block:
        out.append("endf")
    return out


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


def inflip_reference_path(inflip_path: Path) -> Optional[Path]:
    """Resolve a referencefile declared by the incoming Jana .inflip file."""
    for line in read_text_lines(inflip_path):
        parts = split_inflip_line(line)
        if parts and parts[0].lower() == "referencefile" and len(parts) > 1:
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


def allow_external_process_foreground(process_id: int) -> bool:
    """Grant the native Superflip process one-shot foreground permission on Windows."""
    if sys.platform != "win32" or int(process_id) <= 0:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        return bool(user32.AllowSetForegroundWindow(int(process_id)))
    except Exception:
        return False


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



def parse_superflip_log_metrics(log_path: Path) -> JanaCycleMetrics:
    """Parse saved-density Superflip metrics from a Jana .sflog.

    The final map is represented by the last "Properties of the saved density"
    table.  The first column in that table is the saved repeatmode run that was
    actually used, followed by Rvalue, Peaks, Symm. and Der.SG.
    """
    metrics = JanaCycleMetrics()
    if not log_path.is_file():
        return metrics
    lines = read_text_lines(log_path)

    def as_float(value: str) -> Optional[float]:
        try:
            return float(str(value).replace(",", "."))
        except Exception:
            return None

    def is_float_token(value: str) -> bool:
        return as_float(value) is not None

    in_table = False
    for line in lines:
        if "Run" in line and "Rvalue" in line and "Peaks" in line and "Symm" in line:
            in_table = True
            continue
        if not in_table:
            continue
        parts = line.split()
        if not parts:
            in_table = False
            continue
        if len(parts) < 4:
            continue
        try:
            saved_run = int(float(parts[0]))
        except Exception:
            continue
        rvalue = as_float(parts[1])
        peaks = as_float(parts[2])
        symm = as_float(parts[3])
        if rvalue is None or peaks is None or symm is None:
            continue
        metrics.saved_run = saved_run
        metrics.rvalue = rvalue
        metrics.peaks = peaks
        metrics.symm = symm
        if len(parts) >= 5 and not is_float_token(parts[4]):
            metrics.derived_sg = parts[4]

    sr_re = re.compile(r"Success rate(?:\s*\(SR\))?\s*\[%\]\s*:\s*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE)
    mean_re = re.compile(r"Mean cycles per convergence\(beta\)\s*:\s*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE)
    score_re = re.compile(r"\bScore:\s*([-+]?\d+(?:\.\d+)?)")
    fom_re = re.compile(r"\bFOM\b[^-+0-9]*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE)
    for line in lines:
        m = sr_re.search(line)
        if m:
            try:
                metrics.success_rate = float(m.group(1))
            except Exception:
                pass
        m = mean_re.search(line)
        if m:
            try:
                metrics.mean_cycles = float(m.group(1))
            except Exception:
                pass
        m = score_re.search(line)
        if m:
            try:
                metrics.fom = float(m.group(1))
            except Exception:
                pass
        m = fom_re.search(line)
        if m:
            try:
                metrics.fom = float(m.group(1))
            except Exception:
                pass
    return metrics

def find_cycle_sflog(cwd: Path, base_name: str, cycle: int) -> Optional[Path]:
    candidates = [
        cwd / f"{base_name}_phase_studio_cycle_{cycle:03d}.sflog",
        cwd / f"{base_name}.sflog",
        cwd / f"{base_name}.log",
    ]
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    matches = sorted(cwd.glob(f"{base_name}*cycle_{cycle:03d}*.sflog"))
    for candidate in matches:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def best_jana_cycle_index(results: Sequence[JanaCycleResult]) -> int:
    finite = [
        (idx, float(result.symm))
        for idx, result in enumerate(results)
        if result.symm is not None
    ]
    if finite:
        return min(finite, key=lambda item: item[1])[0]
    return len(results) - 1 if results else -1


def final_jana_handoff(
    inflip_path: Path,
    selected_map: Path,
    base_name: str,
    original_superflip: Path,
    log: Callable[[str], None],
) -> int:
    if not selected_map.is_file() or selected_map.stat().st_size == 0:
        raise RuntimeError(f"Selected hand-off map does not exist: {selected_map}")
    cwd = inflip_path.parent
    if selected_map.parent != cwd:
        target_map = cwd / selected_map.name
        if selected_map.resolve() != target_map.resolve():
            shutil.copy2(selected_map, target_map)
    else:
        target_map = selected_map
    header = inflip_header_for_m80(read_text_lines(inflip_path))
    calc_m80 = original_superflip.parent / "deblurrer" / "calc_m80.inflip"
    write_text_lines(calc_m80, define_m80_inflip(header, base_name, target_map.name))
    log(f"Final Jana2020 hand-off map: {target_map}")
    log(f"Final Jana2020 inflip: {calc_m80}")
    return run_process([str(original_superflip), str(calc_m80)], cwd=cwd, log=log)


def show_simplified_handoff_dialog(
    inflip_path: Path,
    base_name: str,
    results: Sequence[JanaCycleResult],
    original_superflip: Path,
    log: Callable[[str], None],
) -> int:
    if not results:
        raise RuntimeError("No completed cycle is available for Jana2020 hand-off.")
    qt = _qt_imports()
    QApplication = qt["QApplication"]
    QDialog = qt["QDialog"]
    QVBoxLayout = qt["QVBoxLayout"]
    QLabel = qt["QLabel"]
    QFormLayout = qt["QFormLayout"]
    QComboBox = qt["QComboBox"]
    QDialogButtonBox = qt["QDialogButtonBox"]
    QMessageBox = qt["QMessageBox"]
    QTableWidget = qt["QTableWidget"]
    QTableWidgetItem = qt["QTableWidgetItem"]
    QHeaderView = qt["QHeaderView"]
    QAbstractItemView = qt["QAbstractItemView"]

    app = QApplication.instance() or QApplication([sys.argv[0]])
    apply_phase_studio_style(app)

    dialog = QDialog()
    dialog.setWindowTitle("Pass Phase Studio result to Jana2020")
    dialog.resize(760, 460)
    layout = QVBoxLayout(dialog)
    info = QLabel(
        "The simplified Jana2020 calculation has finished. Select the cycle and map "
        "that should be passed back to Jana2020 for the final Superflip hand-off."
    )
    info.setWordWrap(True)
    layout.addWidget(info)

    table = QTableWidget(len(results), 6)
    table.setHorizontalHeaderLabels(["Cycle", "Rvalue", "Peaks", "Symm.", "Superflip map", "Deblurred map"])
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)

    def fmt(value: Optional[float]) -> str:
        if value is None:
            return "n/a"
        try:
            return f"{float(value):.4g}"
        except Exception:
            return "n/a"

    for row, result in enumerate(results):
        values = [
            f"{int(result.cycle):03d}",
            fmt(result.rvalue),
            fmt(result.peaks),
            fmt(result.symm),
            "yes" if result.superflip_map.is_file() else "missing",
            "yes" if result.deblurred_map.is_file() else "missing",
        ]
        for col, value in enumerate(values):
            table.setItem(row, col, QTableWidgetItem(value))
    recommended = best_jana_cycle_index(results)
    if recommended >= 0:
        table.selectRow(recommended)
    layout.addWidget(table, 1)

    form = QFormLayout()
    cycle_combo = QComboBox()
    for result in results:
        symm = "n/a" if result.symm is None else f"{float(result.symm):.3f}"
        rvalue = "n/a" if result.rvalue is None else f"{float(result.rvalue):.3f}"
        cycle_combo.addItem(f"Cycle {int(result.cycle):03d} — Symm. {symm}, Rvalue {rvalue}", int(result.cycle))
    if recommended >= 0:
        cycle_combo.setCurrentIndex(recommended)

    map_combo = QComboBox()
    map_combo.addItem("Deblurred map (SharpED output)", "deblurred")
    map_combo.addItem("Superflip map", "superflip")
    if recommended >= 0 and not results[recommended].deblurred_map.is_file() and results[recommended].superflip_map.is_file():
        map_combo.setCurrentIndex(1)

    def sync_table_to_combo() -> None:
        row = table.currentRow()
        if 0 <= row < len(results):
            cycle_combo.setCurrentIndex(row)

    def sync_combo_to_table(index: int) -> None:
        if 0 <= index < len(results):
            table.selectRow(index)

    table.itemSelectionChanged.connect(sync_table_to_combo)
    cycle_combo.currentIndexChanged.connect(sync_combo_to_table)

    form.addRow("Cycle", cycle_combo)
    form.addRow("Map source", map_combo)
    layout.addLayout(form)

    note = QLabel(
        "The suggested row is selected by the best available Superflip symmetry agreement "
        "(lowest Symm. residual). You can override the selection manually."
    )
    note.setWordWrap(True)
    layout.addWidget(note)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Ok).setText("Pass to Jana2020")
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() != QDialog.Accepted:
        log("Jana2020 hand-off was cancelled by the user.")
        return 1

    selected_cycle = int(cycle_combo.currentData())
    source = str(map_combo.currentData() or "deblurred")
    selected = next((r for r in results if int(r.cycle) == selected_cycle), None)
    if selected is None:
        QMessageBox.warning(dialog, "Jana2020 hand-off", "Selected cycle is no longer available.")
        return 1
    selected_map = selected.superflip_map if source.startswith("super") else selected.deblurred_map
    try:
        return final_jana_handoff(inflip_path, selected_map, base_name, original_superflip, log)
    except Exception as exc:
        QMessageBox.critical(dialog, "Jana2020 hand-off failed", str(exc))
        raise


def parse_simple_superflip_metrics(log_path: Path) -> JanaCycleMetrics:
    """Compatibility wrapper for the saved-density Superflip metric parser."""
    return parse_superflip_log_metrics(log_path)

def locate_superflip_sflog(cwd: Path, base_name: str, temp_inflip: Path) -> Optional[Path]:
    candidates = [
        cwd / f"{base_name}.sflog",
        cwd / f"{temp_inflip.stem}.sflog",
        temp_inflip.with_suffix(".sflog"),
    ]
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def recommended_jana_cycle_index(results: Sequence[JanaCycleResult]) -> int:
    finite = [
        (idx, float(r.symm))
        for idx, r in enumerate(results)
        if r.symm is not None
    ]
    if finite:
        return min(finite, key=lambda item: item[1])[0]
    return len(results) - 1 if results else -1


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
        raise RuntimeError(f"Selected hand-off map does not exist or is empty: {selected_map}")
    header = inflip_header_for_m80(original_lines)
    calc_m80 = exe_dir / "deblurrer" / "calc_m80.inflip"
    write_text_lines(calc_m80, define_m80_inflip(header, base_name, selected_map.name))
    log(f"Final Jana inflip: {calc_m80}")
    log(f"Final Jana hand-off model: {selected_map}")
    return run_process([str(original), str(calc_m80)], cwd=cwd, log=log)


def show_jana_handoff_dialog(
    results: Sequence[JanaCycleResult],
    parent_title: str = "Pass Phase Studio result to Jana2020",
) -> Optional[tuple[int, str]]:
    if not results:
        return None
    qt = _qt_imports()
    QApplication = qt["QApplication"]
    QComboBox = qt["QComboBox"]
    QDialog = qt["QDialog"]
    QDialogButtonBox = qt["QDialogButtonBox"]
    QFormLayout = qt["QFormLayout"]
    QHeaderView = qt["QHeaderView"]
    QLabel = qt["QLabel"]
    QTableWidget = qt["QTableWidget"]
    QTableWidgetItem = qt["QTableWidgetItem"]
    QAbstractItemView = qt["QAbstractItemView"]
    QVBoxLayout = qt["QVBoxLayout"]
    Qt = qt["Qt"]

    app = QApplication.instance() or QApplication([sys.argv[0]])
    apply_phase_studio_style(app)

    dialog = QDialog()
    dialog.setWindowTitle(parent_title)
    dialog.resize(1120, 540)
    layout = QVBoxLayout(dialog)
    info = QLabel(
        "The calculation has finished. Select the cycle and density map that should be "
        "passed back to Jana2020 for the final Superflip hand-off. The table shows all "
        "Superflip metrics parsed from each cycle; Rvalue, Peaks, Symm. and Der.SG are "
        "taken from the saved repeatmode run actually used by Superflip."
    )
    info.setWordWrap(True)
    layout.addWidget(info)

    headers = [
        "Cycle",
        "Saved run",
        "Rvalue",
        "Peaks",
        "Symm.",
        "Der.SG",
        "FoM / Score",
        "Success rate %",
        "Mean cycles",
        "Superflip map",
        "Deblurred map",
    ]
    table = QTableWidget(len(results), len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(False)

    def fmt(value: object) -> str:
        if value is None:
            return "n/a"
        try:
            return f"{float(value):.3f}"
        except Exception:
            return str(value) if str(value) else "n/a"

    for row, result in enumerate(results):
        values = [
            f"{result.cycle:03d}",
            "n/a" if result.saved_run is None else str(int(result.saved_run)),
            fmt(result.rvalue),
            fmt(result.peaks),
            fmt(result.symm),
            result.derived_sg or "n/a",
            fmt(result.fom),
            fmt(result.success_rate),
            fmt(result.mean_cycles),
            "available" if result.superflip_map.is_file() else "missing",
            "available" if result.deblurred_map is not None and result.deblurred_map.is_file() else "missing",
        ]
        for col, text in enumerate(values):
            item = QTableWidgetItem(text)
            if col == 0:
                item.setData(Qt.UserRole, int(result.cycle))
            table.setItem(row, col, item)
    layout.addWidget(table, 1)

    form = QFormLayout()
    cycle_combo = QComboBox()
    for result in results:
        symm = "n/a" if result.symm is None else f"{float(result.symm):.3f}"
        rvalue = "n/a" if result.rvalue is None else f"{float(result.rvalue):.3f}"
        run_label = "n/a" if result.saved_run is None else str(int(result.saved_run))
        cycle_combo.addItem(f"Cycle {result.cycle:03d} — saved run {run_label}, Symm. {symm}, Rvalue {rvalue}", result.cycle)
    recommended = recommended_jana_cycle_index(results)
    if recommended >= 0:
        cycle_combo.setCurrentIndex(recommended)
        table.selectRow(recommended)

    map_combo = QComboBox()
    map_combo.addItem("Deblurred map (SharpED output)", "deblurred")
    map_combo.addItem("Superflip map", "superflip")
    try:
        rec = results[recommended]
        if rec.deblurred_map is None or not rec.deblurred_map.is_file():
            map_combo.setCurrentIndex(1)
    except Exception:
        pass

    def sync_table_from_combo(index: int) -> None:
        if 0 <= index < table.rowCount():
            table.selectRow(index)

    def sync_combo_from_table() -> None:
        row = table.currentRow()
        if 0 <= row < cycle_combo.count() and row != cycle_combo.currentIndex():
            cycle_combo.setCurrentIndex(row)

    cycle_combo.currentIndexChanged.connect(sync_table_from_combo)
    table.itemSelectionChanged.connect(sync_combo_from_table)

    form.addRow("Cycle", cycle_combo)
    form.addRow("Map source", map_combo)
    layout.addLayout(form)

    note = QLabel(
        "The suggested cycle is selected by the best Superflip symmetry agreement "
        "(lowest Symm. residual). After a successful hand-off this launcher closes automatically."
    )
    note.setWordWrap(True)
    layout.addWidget(note)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Ok).setText("Pass to Jana2020")
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() != QDialog.Accepted:
        return None
    return int(cycle_combo.currentData()), str(map_combo.currentData() or "deblurred")

def run_jana_superflip(args: Sequence[str], options: JanaRunOptions, log: Callable[[str], None]) -> int:
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

    arg_index, inflip_path = inflip_arg
    if not inflip_path.is_file():
        raise FileNotFoundError(f"Inflip file not found: {inflip_path}")
    base_name = inflip_path.stem
    original_lines = read_text_lines(inflip_path)
    # Must exist before any optional reference/model staging.
    temp_files: List[Path] = []
    input_mode = normalize_dialog_input_mode(options.input_mode)
    log(f"Input data mode: {input_mode}")

    use_hkl_override = input_mode in {INPUT_MODE_INFLIP_OVERRIDES, INPUT_MODE_EXTERNAL} and options.hkl_override.strip()
    use_reference_override = input_mode in {INPUT_MODE_INFLIP_OVERRIDES, INPUT_MODE_EXTERNAL} and options.reference_override.strip()
    use_superflip_referencefile = bool(options.superflip_referencefile.strip())
    if input_mode == INPUT_MODE_EXTERNAL:
        if not options.hkl_override.strip():
            raise FileNotFoundError("External HKL + reference CIF mode requires an external HKL file.")
        if not options.reference_override.strip():
            raise FileNotFoundError("External HKL + reference CIF mode requires a reference CIF or XPLOR file.")

    if use_hkl_override:
        hkl_override = Path(options.hkl_override).expanduser().resolve()
        if not hkl_override.is_file():
            raise FileNotFoundError(f"HKL override not found: {hkl_override}")
        original_lines = replace_fbegin_with_hkl(original_lines, hkl_override)
        log(f"HKL source: external file {hkl_override}")
    else:
        log("Reflection source: embedded Jana2020 fbegin/endf block")

    if use_reference_override:
        reference_override = Path(options.reference_override).expanduser().resolve()
        if not reference_override.is_file():
            raise FileNotFoundError(f"Reference override not found: {reference_override}")
        staged_reference_override = stage_external_file_for_superflip(
            reference_override, cwd, base_name, "reference_override"
        )
        original_lines = apply_reference_override(original_lines, staged_reference_override)
        temp_files.append(staged_reference_override)
        log(f"Reference source: external file {reference_override}")
        log(f"  staged for Superflip as local file: {staged_reference_override.name}")
        log(f"  staged file path: {staged_reference_override}")
    else:
        log("Reference source: incoming Jana2020 .inflip declaration/metadata")

    if use_superflip_referencefile:
        referencefile_path = Path(options.superflip_referencefile).expanduser().resolve()
        if not referencefile_path.is_file():
            raise FileNotFoundError(f"Superflip referencefile not found: {referencefile_path}")
        if referencefile_path.suffix.lower() not in {".cif", ".xplor"}:
            raise RuntimeError("Superflip referencefile must be a CIF structure or an XPLOR density map.")
        staged_referencefile = stage_external_file_for_superflip(
            referencefile_path, cwd, base_name, "referencefile"
        )
        original_lines = apply_reference_override(original_lines, staged_referencefile)
        temp_files.append(staged_referencefile)
        log(f"Superflip referencefile: {referencefile_path}")
        log(f"  staged for Superflip as local file: {staged_referencefile.name}")
        log(f"  staged file path: {staged_referencefile}")

    first_cycle_model: Optional[Path] = None
    if options.first_cycle_modelfile.strip():
        source_model = Path(options.first_cycle_modelfile).expanduser().resolve()
        if not source_model.is_file():
            raise FileNotFoundError(f"First-cycle modelfile not found: {source_model}")
        if source_model.suffix.lower() not in {".xplor", ".ccp4", ".cif"}:
            raise RuntimeError(
                "First-cycle modelfile must be an XPLOR map, CCP4 map or CIF structure: "
                f"{source_model}"
            )
        first_cycle_model = stage_external_file_for_superflip(
            source_model, cwd, base_name, "first_cycle_modelfile"
        )
        temp_files.append(first_cycle_model)
        log(f"First-cycle modelfile: {source_model}")
        log(f"  staged for Superflip as local file: {first_cycle_model.name}")
        log(f"  staged file path: {first_cycle_model}")

    log(f"Wrapper inflip: {inflip_path}")
    log(f"Output base: {base_name}")
    next_cycle_mode = str(getattr(options, "next_cycle_modelfile", "") or "").strip().lower()
    if not next_cycle_mode:
        next_cycle_mode = "deblurred_xplor" if options.use_deblurred_map else "none"
    if next_cycle_mode not in {"superflip_xplor", "deblurred_xplor", "none"}:
        next_cycle_mode = "deblurred_xplor" if options.use_deblurred_map else "none"
    use_superflip_xplor_modelfile = next_cycle_mode == "superflip_xplor"
    use_deblurred_xplor_modelfile = next_cycle_mode == "deblurred_xplor"
    effective_cycles = max(1, int(options.cycles)) if next_cycle_mode != "none" else 1
    log(f"Cycles: {effective_cycles}")
    if next_cycle_mode == "none":
        log("Next-cycle modelfile: none; running one Superflip cycle without SharpED feedback.")
    elif use_superflip_xplor_modelfile:
        log("Next-cycle modelfile: superflip_xplor; cycling without SharpED deblurring.")
    else:
        log("Next-cycle modelfile: deblurred_xplor.")

    xplor_map = cwd / f"{base_name}.xplor"
    deblurred_map = cwd / f"{base_name}-deb.xplor"
    current_model: Optional[Path] = None
    results: List[JanaCycleResult] = []
    try:
        for cycle in range(1, effective_cycles + 1):
            log(f"=== Jana wrapper cycle {cycle} ===")
            cycle_lines = ensure_xplor_output(original_lines, base_name)
            if cycle == 1 and first_cycle_model is not None:
                cycle_lines = add_modelseed_modelfile(
                    cycle_lines,
                    first_cycle_model.name,
                    first_cycle_model.suffix,
                )
                log(
                    "First cycle uses an external modelfile; model-seeded policy: "
                    "repeatmode 1; randomseed keyword omitted."
                )
            elif current_model is not None:
                cycle_lines = add_xplor_modelfile(cycle_lines, current_model.name)
                log(
                    "Model-seeded cycle policy: repeatmode 1; "
                    "randomseed keyword omitted."
                )
            temp_inflip = cwd / f"{base_name}_phase_studio_cycle_{cycle:03d}.inflip"
            write_text_lines(temp_inflip, cycle_lines)
            temp_files.append(temp_inflip)

            run_args = list(args)
            run_args[arg_index] = temp_inflip.name
            run_started_at = time.time()
            for stale in (xplor_map, cwd / f"{base_name}.sflog"):
                try:
                    if stale.is_file():
                        stale.unlink()
                        log(f"Removed stale Superflip output before run: {stale.name}")
                except Exception as exc:
                    log(f"Could not remove stale Superflip output {stale}: {exc}")
            run_process([str(original), *run_args], cwd=cwd, log=log)
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

            cycle_superflip_map = cwd / f"{base_name}_phase_studio_cycle_{cycle:03d}_superflip.xplor"
            shutil.copy2(xplor_map, cycle_superflip_map)

            sflog = locate_superflip_sflog(cwd, base_name, temp_inflip)
            cycle_sflog: Optional[Path] = None
            cycle_metrics = JanaCycleMetrics()
            if sflog is not None:
                cycle_sflog = cwd / f"{base_name}_phase_studio_cycle_{cycle:03d}.sflog"
                try:
                    shutil.copy2(sflog, cycle_sflog)
                except Exception:
                    cycle_sflog = sflog
                cycle_metrics = parse_simple_superflip_metrics(cycle_sflog)
                log(
                    "Superflip metrics: "
                    f"saved_run={cycle_metrics.saved_run if cycle_metrics.saved_run is not None else 'n/a'}, "
                    f"Rvalue={cycle_metrics.rvalue if cycle_metrics.rvalue is not None else 'n/a'}, "
                    f"Peaks={cycle_metrics.peaks if cycle_metrics.peaks is not None else 'n/a'}, "
                    f"Symm.={cycle_metrics.symm if cycle_metrics.symm is not None else 'n/a'}, "
                    f"Der.SG={cycle_metrics.derived_sg or 'n/a'}, "
                    f"SR={cycle_metrics.success_rate if cycle_metrics.success_rate is not None else 'n/a'}%"
                )

            cycle_deblurred_map: Optional[Path] = None
            if use_deblurred_xplor_modelfile:
                deblur_with_sharped(xplor_map, deblurred_map, options, log=log)
                if not deblurred_map.is_file() or deblurred_map.stat().st_size == 0:
                    raise RuntimeError(f"SharpED did not create expected deblurred map: {deblurred_map}")
                log(f"Deblurred map: {deblurred_map}")
                cycle_deblurred_map = cwd / f"{base_name}_phase_studio_cycle_{cycle:03d}_deblurred.xplor"
                shutil.copy2(deblurred_map, cycle_deblurred_map)

                # Stage the next-cycle modelfile under a short local name.  The
                # legacy Jana/Superflip parser can fail on unquoted or long file
                # names with spaces/commas (for example ``Ag O9,12 ... -deb.xplor``)
                # and reports only "Error reading keyword modelfile".  Keeping the
                # real per-cycle output above while feeding Superflip a stable short
                # name makes later cycles robust.
                current_model = stage_external_file_for_superflip(
                    deblurred_map,
                    cwd,
                    base_name,
                    "next_cycle_modelfile",
                )
                if current_model not in temp_files:
                    temp_files.append(current_model)
                log(f"Next-cycle Superflip modelfile staged as local file: {current_model.name}")
                log(f"  staged file path: {current_model}")
            elif use_superflip_xplor_modelfile:
                current_model = stage_external_file_for_superflip(
                    xplor_map,
                    cwd,
                    base_name,
                    "next_cycle_modelfile",
                )
                if current_model not in temp_files:
                    temp_files.append(current_model)
                log(f"Next-cycle raw Superflip XPLOR modelfile staged as local file: {current_model.name}")
                log(f"  staged file path: {current_model}")
            else:
                current_model = None

            results.append(
                JanaCycleResult(
                    cycle=cycle,
                    superflip_map=cycle_superflip_map,
                    deblurred_map=cycle_deblurred_map,
                    sflog_path=cycle_sflog,
                    saved_run=cycle_metrics.saved_run,
                    rvalue=cycle_metrics.rvalue,
                    peaks=cycle_metrics.peaks,
                    symm=cycle_metrics.symm,
                    derived_sg=cycle_metrics.derived_sg,
                    fom=cycle_metrics.fom,
                    success_rate=cycle_metrics.success_rate,
                    mean_cycles=cycle_metrics.mean_cycles,
                )
            )

        selection = show_jana_handoff_dialog(results)
        if selection is None:
            log("Jana2020 hand-off was cancelled by the user.")
            return 1
        selected_cycle, selected_source = selection
        selected_result = next((r for r in results if int(r.cycle) == int(selected_cycle)), None)
        if selected_result is None:
            raise RuntimeError(f"Selected cycle is not available: {selected_cycle}")
        if selected_source == "superflip":
            selected_map = selected_result.superflip_map
        else:
            selected_map = selected_result.deblurred_map or selected_result.superflip_map
        log(f"Selected Jana2020 hand-off: cycle {selected_cycle:03d}, {selected_source} map")
        code = run_final_jana_handoff(original, exe_dir, cwd, original_lines, base_name, selected_map, log)
        log("Jana2020 hand-off completed. The Phase Studio launcher will close automatically.")
        try:
            qt = _qt_imports()
            app = qt["QApplication"].instance()
            if app is not None:
                app.quit()
        except Exception:
            pass
        return code
    finally:
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
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QDoubleSpinBox,
            QFileDialog,
            QFormLayout,
            QGroupBox,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMessageBox,
            QPushButton,
            QSizePolicy,
            QSpinBox,
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
        "QCheckBox": QCheckBox,
        "QComboBox": QComboBox,
        "QDialog": QDialog,
        "QDialogButtonBox": QDialogButtonBox,
        "QDoubleSpinBox": QDoubleSpinBox,
        "QFileDialog": QFileDialog,
        "QFormLayout": QFormLayout,
        "QGroupBox": QGroupBox,
        "QHBoxLayout": QHBoxLayout,
        "QHeaderView": QHeaderView,
        "QLabel": QLabel,
        "QLineEdit": QLineEdit,
        "QMessageBox": QMessageBox,
        "QPushButton": QPushButton,
        "QSettings": QSettings,
        "QSizePolicy": QSizePolicy,
        "QSpinBox": QSpinBox,
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
    QMessageBox = qt["QMessageBox"]
    message = QMessageBox(parent)
    message.setIcon(QMessageBox.Warning)
    message.setWindowTitle("SharpED credentials required")
    message.setText("An API token is required to run SharpED deblurring.")
    message.setInformativeText(
        "Open SharpED connection settings and enter your API token, or define "
        "the SHARPED_API_TOKEN environment variable before starting the job."
    )
    message.setStandardButtons(QMessageBox.Ok)
    message.exec()


def show_jana_dialog(args: Sequence[str], inflip_path: Optional[Path]) -> JanaRunOptions:
    qt = _qt_imports()
    QApplication = qt["QApplication"]
    QCheckBox = qt["QCheckBox"]
    QComboBox = qt["QComboBox"]
    QDialog = qt["QDialog"]
    QDoubleSpinBox = qt["QDoubleSpinBox"]
    QFileDialog = qt["QFileDialog"]
    QFormLayout = qt["QFormLayout"]
    QGroupBox = qt["QGroupBox"]
    QHBoxLayout = qt["QHBoxLayout"]
    QLabel = qt["QLabel"]
    QLineEdit = qt["QLineEdit"]
    QMessageBox = qt["QMessageBox"]
    QPushButton = qt["QPushButton"]
    QSettings = qt["QSettings"]
    QSizePolicy = qt["QSizePolicy"]
    QSpinBox = qt["QSpinBox"]
    QStyle = qt["QStyle"]
    QTimer = qt["QTimer"]
    QToolButton = qt["QToolButton"]
    Qt = qt["Qt"]
    QVBoxLayout = qt["QVBoxLayout"]
    QWidget = qt["QWidget"]

    app = QApplication.instance() or QApplication([sys.argv[0], *args])
    apply_phase_studio_style(app)

    settings = QSettings("PhaseStudio", "JanaSuperflipWrapper")
    dialog = QDialog()
    dialog.setWindowTitle("Phase Studio 1.0.1 for Jana2020")
    dialog.setMinimumWidth(760)
    dialog.resize(820, 680)

    root = QVBoxLayout(dialog)
    root.setContentsMargins(14, 14, 14, 14)
    root.setSpacing(10)

    title = QLabel("Phase Studio 1.0.1 for Jana2020")
    title_font = title.font()
    title_font.setPointSize(title_font.pointSize() + 5)
    title_font.setBold(True)
    title.setFont(title_font)
    root.addWidget(title)

    subtitle = QLabel(
        "Choose whether the Superflip job supplied by Jana2020 should be executed "
        "directly or opened in the complete Phase Studio workspace. The incoming "
        ".inflip file remains the primary crystallographic input unless an explicit "
        "override is selected below."
    )
    subtitle.setWordWrap(True)
    root.addWidget(subtitle)

    input_group = QGroupBox("Crystallographic input source")
    input_outer = QVBoxLayout(input_group)
    input_form = QFormLayout()
    input_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

    input_mode = QComboBox()
    input_mode.addItems(INPUT_MODE_LABELS)
    input_mode.setCurrentText(str(settings.value("input_mode", INPUT_MODE_INFLIP)) or INPUT_MODE_INFLIP)
    input_mode.setToolTip(
        "Select the source of the crystallographic data for this Jana2020 job. "
        "Use the incoming Jana .inflip as-is, use it as a template with selected "
        "external HKL/CIF replacements, or run from an external HKL plus reference CIF."
    )
    input_form.addRow("Input data mode", input_mode)

    input_path = QLineEdit(str(inflip_path) if inflip_path else "No .inflip argument was detected.")
    input_path.setReadOnly(True)
    input_path.setCursorPosition(0)
    input_path.setToolTip(
        "Jana2020-generated Superflip input file. In Jana input modes, Phase Studio "
        "uses its fbegin/endf reflection block, unit-cell parameters, space-group "
        "symmetry, composition and calculation keywords unless a selected override "
        "replaces the corresponding data source."
    )
    jana_inflip_label = QLabel("Incoming .inflip")
    input_form.addRow(jana_inflip_label, input_path)

    def add_file_override(label_text: str, file_filter: str, tooltip: str, placeholder: str):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setToolTip(tooltip)
        browse = QPushButton("Browse…")
        browse.setToolTip(f"Select {label_text.lower()}.")

        def browse_file() -> None:
            selected = QFileDialog.getOpenFileName(
                dialog,
                f"Select {label_text}",
                edit.text(),
                file_filter,
            )[0]
            if selected:
                edit.setText(selected)

        browse.clicked.connect(browse_file)
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(browse)
        label = QLabel(label_text)
        input_form.addRow(label, row_widget)
        return label, row_widget, edit

    hkl_label, hkl_row, hkl_override = add_file_override(
        "External HKL",
        "Reflection files (*.hkl *.fcf *.int);;All files (*)",
        "External reflection file. In override mode, these h k l records replace "
        "the Jana .inflip fbegin/endf block. In external-input mode this field is required.",
        "Use reflections embedded in the Jana .inflip",
    )
    reference_label, reference_row, reference_override = add_file_override(
        "Reference CIF / XPLOR",
        "Reference files (*.cif *.xplor);;CIF structures (*.cif);;XPLOR maps (*.xplor);;All files (*)",
        "External reference source. A CIF supplies structural and crystallographic "
        "reference information; an XPLOR map supplies a reference density map. "
        "In external-input mode a reference CIF/XPLOR is required.",
        "Use reference metadata from the Jana .inflip",
    )
    first_model_label, first_model_row, first_cycle_modelfile = add_file_override(
        "Cycle 1 modelfile",
        "Model/map files (*.xplor *.ccp4 *.cif);;XPLOR maps (*.xplor);;CCP4 maps (*.ccp4);;CIF structures (*.cif);;All files (*)",
        "Optional model or density map for the first Superflip cycle. If supplied, "
        "cycle 1 is treated as model-seeded: repeatmode is forced to 1 and randomseed is omitted.",
        "No first-cycle modelfile",
    )
    first_cycle_modelfile.setText(str(settings.value("first_cycle_modelfile", "")))
    referencefile_label, referencefile_row, superflip_referencefile = add_file_override(
        "Superflip referencefile",
        "Reference files (*.cif *.xplor);;CIF structures (*.cif);;XPLOR density maps (*.xplor);;All files (*)",
        "Optional Superflip referencefile for the generated input. This can be used together with the default Jana .inflip mode without replacing the embedded HKL block or the .inflip metadata.",
        "No additional Superflip referencefile",
    )
    superflip_referencefile.setText(str(settings.value("superflip_referencefile", "")))

    input_note = QLabel(
        "Default mode uses the incoming Jana .inflip without replacing its reflection "
        "or reference data. External files are used only in the two modes that explicitly "
        "enable them."
    )
    input_note.setWordWrap(True)
    input_outer.addLayout(input_form)
    input_outer.addWidget(input_note)
    root.addWidget(input_group)

    def sync_input_mode() -> None:
        mode = normalize_dialog_input_mode(input_mode.currentText())
        use_inflip = mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES}
        allow_overrides = mode in {INPUT_MODE_INFLIP_OVERRIDES, INPUT_MODE_EXTERNAL}
        external_required = mode == INPUT_MODE_EXTERNAL

        jana_inflip_label.setVisible(use_inflip)
        input_path.setVisible(use_inflip)
        for widget in (hkl_label, hkl_row, reference_label, reference_row):
            widget.setVisible(allow_overrides)
        if mode == INPUT_MODE_INFLIP:
            hkl_override.clear()
            reference_override.clear()
            input_note.setText(
                "The Jana .inflip is used as the primary crystallographic input. "
                "Its embedded fbegin/endf reflection block and reference metadata are preserved. "
                "An optional first-cycle modelfile and an optional Superflip referencefile may still be supplied."
            )
        elif mode == INPUT_MODE_INFLIP_OVERRIDES:
            input_note.setText(
                "The Jana .inflip remains the calculation template, but the reflection block "
                "and/or reference declaration may be replaced by the selected external files."
            )
        else:
            input_note.setText(
                "The calculation uses external HKL plus reference CIF/XPLOR data. The Jana .inflip "
                "is used only as the Jana2020 hand-off template and for compatible Superflip keywords."
            )
        if external_required:
            hkl_override.setPlaceholderText("Required external HKL")
            reference_override.setPlaceholderText("Required reference CIF / XPLOR")
        else:
            hkl_override.setPlaceholderText("Optional HKL override")
            reference_override.setPlaceholderText("Optional reference override")

    input_mode.currentTextChanged.connect(sync_input_mode)
    sync_input_mode()

    workflow_group = QGroupBox("Processing workflow")
    workflow_layout = QVBoxLayout(workflow_group)
    workflow_form = QFormLayout()
    workflow_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

    cycles = QSpinBox()
    cycles.setRange(1, 999)
    cycles.setValue(int(settings.value("cycles", 1)))
    cycles.setToolTip(
        "Total number of wrapper cycles. If Next-cycle modelfile is none, the run is forced to one cycle."
    )
    workflow_form.addRow("Processing cycles", cycles)

    next_cycle_modelfile = QComboBox()
    next_cycle_modelfile.addItems(["superflip_xplor", "deblurred_xplor", "none"])
    saved_next_model = str(settings.value("next_cycle_modelfile", "")).strip()
    if not saved_next_model:
        saved_next_model = "superflip_xplor"
    idx = next_cycle_modelfile.findText(saved_next_model)
    if idx >= 0:
        next_cycle_modelfile.setCurrentIndex(idx)
    next_cycle_modelfile.setToolTip(
        "Authoritative setting for cycle 2 and later. superflip_xplor cycles without SharpED deblurring; deblurred_xplor submits the Superflip map to SharpED and uses the returned XPLOR; none forces one cycle."
    )
    workflow_form.addRow("Next-cycle modelfile", next_cycle_modelfile)
    workflow_layout.addLayout(workflow_form)

    policy_note = QLabel(
        "Model-seeded cycle policy: when a modelfile is used, repeatmode is set "
        "to 1 and randomseed is removed. If Next-cycle modelfile is none, there is no later model and cycles are forced to 1."
    )
    policy_note.setWordWrap(True)
    workflow_layout.addWidget(policy_note)
    root.addWidget(workflow_group)

    sharped_group = QGroupBox("SharpED connection and model settings")
    sharped_group.setToolTip(
        "Use the disclosure arrow to configure the SharpED server, API credentials, "
        "inference model, element list and output sampling."
    )
    sharped_outer = QVBoxLayout(sharped_group)
    sharped_toggle = QToolButton()
    sharped_toggle.setText("SharpED API and model settings")
    sharped_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    sharped_toggle.setArrowType(Qt.RightArrow)
    sharped_toggle.setCheckable(True)
    sharped_toggle.setChecked(False)
    sharped_toggle.setToolTip("Expand or collapse the SharpED connection settings.")
    sharped_outer.addWidget(sharped_toggle)
    sharped_body = QWidget()
    sharped_layout = QVBoxLayout(sharped_body)
    sharped_layout.setContentsMargins(18, 4, 0, 0)
    sharped_form = QFormLayout()
    sharped_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

    server_url = QLineEdit(str(settings.value("server_url", DEFAULT_SERVER_URL)))
    server_url.setPlaceholderText(DEFAULT_SERVER_URL)
    server_url.setToolTip("Base URL of the SharpED service used for model discovery and map processing.")
    sharped_form.addRow("Server URL", server_url)

    api_token = QLineEdit(
        str(settings.value("api_token", os.environ.get("SHARPED_API_TOKEN", "")))
    )
    api_token.setEchoMode(QLineEdit.Password)
    api_token.setPlaceholderText("Enter API token")
    api_token.setToolTip(
        "Bearer token used to authorize SharpED processing. The token is masked in "
        "the interface and may alternatively be supplied through SHARPED_API_TOKEN."
    )
    sharped_form.addRow("API token", api_token)

    model = QComboBox()
    model.setEditable(True)
    saved_model = str(settings.value("model", "default")).strip() or "default"
    model.addItem(saved_model)
    if saved_model != "default":
        model.insertItem(0, "default")
    model.setCurrentText(saved_model)
    model.setToolTip(
        "SharpED inference model. Select a model returned by the server or enter an "
        "explicit model identifier. The value 'default' requests the server default."
    )
    sharped_form.addRow("Model", model)

    refresh_row = QWidget()
    refresh_layout = QHBoxLayout(refresh_row)
    refresh_layout.setContentsMargins(0, 0, 0, 0)
    refresh_models_button = QPushButton("Refresh available models")
    refresh_models_button.setToolTip(
        "Query the SharpED /sharp-ed/models endpoint and repopulate the model selector "
        "with the currently available server models."
    )
    model_status = QLabel("Model list has not been queried in this session.")
    model_status.setWordWrap(True)
    model_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    refresh_layout.addWidget(refresh_models_button)
    refresh_layout.addWidget(model_status, 1)
    sharped_form.addRow("Available models", refresh_row)

    elements = QLineEdit(str(settings.value("elements", "C N O")))
    elements.setPlaceholderText("C N O")
    elements.setToolTip(
        "Space-separated chemical element symbols expected in the density map, for "
        "example 'C N O' or 'C N O Zn'."
    )
    sharped_form.addRow("Elements", elements)

    outres = QDoubleSpinBox()
    outres.setRange(0.001, 10.0)
    outres.setDecimals(4)
    outres.setSingleStep(0.05)
    outres.setSuffix(" Å")
    outres.setValue(float(settings.value("outres", 0.2)))
    outres.setToolTip("Requested SharpED output-map sampling in ångströms.")
    sharped_form.addRow("Output resolution", outres)

    sharped_layout.addLayout(sharped_form)
    sharped_outer.addWidget(sharped_body)
    sharped_body.setVisible(False)

    def sync_sharped_disclosure(opened: bool) -> None:
        sharped_body.setVisible(bool(opened))
        sharped_toggle.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)

    sharped_toggle.toggled.connect(sync_sharped_disclosure)
    sync_sharped_disclosure(False)
    root.addWidget(sharped_group)

    refresh_results: "queue.Queue[tuple[str, object]]" = queue.Queue()
    refresh_timer = QTimer(dialog)
    refresh_timer.setInterval(100)

    def refresh_available_models() -> None:
        base_url = server_url.text().strip() or DEFAULT_SERVER_URL
        refresh_models_button.setEnabled(False)
        model_status.setText("Contacting the SharpED server…")

        def worker() -> None:
            try:
                client = SharpEDServerClient(base_url=base_url, timeout=30.0)
                models_result = client.get_models()
                refresh_results.put(("ok", models_result))
            except Exception as exc:
                refresh_results.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        if not refresh_timer.isActive():
            refresh_timer.start()

    def poll_model_refresh() -> None:
        try:
            state, payload = refresh_results.get_nowait()
        except queue.Empty:
            return

        refresh_timer.stop()
        refresh_models_button.setEnabled(True)
        if state == "error":
            error_text = str(payload)
            model_status.setText("Unable to retrieve the model list.")
            QMessageBox.warning(
                dialog,
                "SharpED model discovery failed",
                "The list of available SharpED models could not be retrieved.\n\n"
                f"Server: {server_url.text().strip() or DEFAULT_SERVER_URL}\n"
                f"Reason: {error_text}\n\n"
                "Verify the server URL and network connection. A model identifier may "
                "still be entered manually.",
            )
            return

        models_result = payload
        current = model.currentText().strip() or "default"
        values: List[str] = ["default"]
        default_model = str(getattr(models_result, "default_model", "") or "").strip()
        if default_model and default_model not in values:
            values.append(default_model)
        for available in list(getattr(models_result, "models", []) or []):
            value = str(available).strip()
            if value and value not in values:
                values.append(value)

        model.blockSignals(True)
        model.clear()
        model.addItems(values)
        model.setCurrentText(current if current in values else "default")
        model.blockSignals(False)
        if default_model:
            model_status.setText(
                f"{len(values) - 1} server model(s) available; default: {default_model}."
            )
        else:
            model_status.setText(f"{len(values) - 1} server model(s) available.")

    refresh_models_button.clicked.connect(refresh_available_models)
    refresh_timer.timeout.connect(poll_model_refresh)

    validation_group = QGroupBox("Scientific validation notice")
    validation_layout = QHBoxLayout(validation_group)
    warning_icon = QLabel()
    warning_icon.setPixmap(dialog.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(28, 28))
    warning_icon.setAlignment(Qt.AlignTop)
    validation_layout.addWidget(warning_icon, 0, Qt.AlignTop)
    warning_text = QLabel(
        "SharpED output is generated by a neural-network model and may contain "
        "artifacts or chemically implausible features. Use it as an interpretation "
        "aid and validate every resulting structure against the measured diffraction "
        "data and an independent crystallographic refinement."
    )
    warning_text.setWordWrap(True)
    validation_layout.addWidget(warning_text, 1)
    root.addWidget(validation_group)

    def sync_enabled() -> None:
        mode = next_cycle_modelfile.currentText().strip().lower()
        enabled = mode != "none"
        needs_sharped = mode == "deblurred_xplor"
        sharped_group.setEnabled(needs_sharped)
        validation_group.setVisible(needs_sharped)
        if not enabled:
            if cycles.value() != 1:
                cycles.setValue(1)
            cycles.setEnabled(False)
            if sharped_toggle.isChecked():
                sharped_toggle.setChecked(False)
        else:
            cycles.setEnabled(True)

    next_cycle_modelfile.currentTextChanged.connect(sync_enabled)
    sync_enabled()

    root.addStretch(1)
    button_row = QHBoxLayout()
    cancel_button = QPushButton("Cancel")
    edit_button = QPushButton("Open full Phase Studio configuration")
    run_button = QPushButton("Run Jana2020 calculation")
    run_button.setDefault(True)
    run_button.setToolTip(
        "Execute the Jana2020 Superflip job through the Phase Studio cycle wrapper. "
        "The incoming .inflip remains authoritative unless an override is selected. "
        "For every model-seeded cycle, repeatmode 1 is enforced and randomseed is omitted."
    )
    edit_button.setToolTip(
        "Open the complete Phase Studio workspace with parameters imported from the "
        "Jana2020 .inflip file. Embedded reflections are exported to a working HKL file "
        "unless an external HKL override is selected."
    )
    cancel_button.setToolTip("Close the launcher without starting or modifying the Jana2020 job.")
    button_row.addStretch(1)
    button_row.addWidget(cancel_button)
    button_row.addWidget(edit_button)
    button_row.addWidget(run_button)
    root.addLayout(button_row)

    result = {"action": "cancel"}

    def save_values(action: str) -> None:
        settings.setValue("cycles", cycles.value())
        settings.setValue("next_cycle_modelfile", next_cycle_modelfile.currentText())
        settings.setValue("use_deblurred_map", next_cycle_modelfile.currentText().strip().lower() == "deblurred_xplor")
        settings.setValue("input_mode", input_mode.currentText())
        settings.setValue("server_url", server_url.text())
        settings.setValue("api_token", api_token.text())
        settings.setValue("model", model.currentText())
        settings.setValue("elements", elements.text())
        settings.setValue("outres", outres.value())
        settings.setValue("superflip_referencefile", superflip_referencefile.text())
        settings.setValue("first_cycle_modelfile", first_cycle_modelfile.text())
        settings.sync()
        result["action"] = action
        dialog.accept()

    def validate_input_selection() -> bool:
        mode = normalize_dialog_input_mode(input_mode.currentText())
        if mode == INPUT_MODE_EXTERNAL:
            missing = []
            if not hkl_override.text().strip():
                missing.append("external HKL")
            if not reference_override.text().strip():
                missing.append("reference CIF / XPLOR")
            if missing:
                QMessageBox.warning(
                    dialog,
                    "Crystallographic input required",
                    "The selected input mode requires: " + ", ".join(missing) + ".",
                )
                return False
        return True

    def run_clicked() -> None:
        if not validate_input_selection():
            return
        token = api_token.text().strip() or os.environ.get("SHARPED_API_TOKEN", "").strip()
        if next_cycle_modelfile.currentText().strip().lower() == "deblurred_xplor" and not token:
            sharped_toggle.setChecked(True)
            api_token.setFocus()
            _show_missing_token_warning(dialog, qt)
            return
        save_values("run")

    def edit_clicked() -> None:
        if validate_input_selection():
            save_values("edit")

    run_button.clicked.connect(run_clicked)
    edit_button.clicked.connect(edit_clicked)
    cancel_button.clicked.connect(dialog.reject)

    accepted = dialog.exec()
    refresh_timer.stop()
    if not accepted:
        return JanaRunOptions(action="cancel")
    return JanaRunOptions(
        action=result["action"],
        cycles=1 if next_cycle_modelfile.currentText().strip().lower() == "none" else int(cycles.value()),
        use_deblurred_map=next_cycle_modelfile.currentText().strip().lower() == "deblurred_xplor",
        next_cycle_modelfile=next_cycle_modelfile.currentText().strip().lower(),
        api_token=api_token.text().strip(),
        server_url=server_url.text().strip() or DEFAULT_SERVER_URL,
        model=model.currentText().strip() or "default",
        elements=elements.text().strip() or "C N O",
        outres=float(outres.value()),
        input_mode=normalize_dialog_input_mode(input_mode.currentText()),
        hkl_override=hkl_override.text().strip(),
        reference_override=reference_override.text().strip(),
        superflip_referencefile=superflip_referencefile.text().strip(),
        first_cycle_modelfile=first_cycle_modelfile.text().strip(),
    )


def launch_phase_studio_from_jana(inflip_path: Optional[Path], options: JanaRunOptions) -> int:
    # Load PySide6 before importing app.py, which initializes Matplotlib QtAgg.
    qt = _qt_imports()
    QApplication = qt["QApplication"]

    from phase_studio.app import (
        IterativeSuperflipPipelineQtGUI,
        create_startup_splash,
        parse_inflip_settings,
    )

    app = QApplication.instance() or QApplication(sys.argv)
    apply_phase_studio_style(app)
    splash = create_startup_splash()
    splash.show()
    app.processEvents()
    win = IterativeSuperflipPipelineQtGUI()
    if inflip_path is not None and inflip_path.is_file():
        parsed = parse_inflip_settings(inflip_path)
        handoff_import = build_jana_handoff_import(inflip_path, options, parsed)
        applied_keys: list[str] = []
        for key, value in handoff_import.values.items():
            widget = win.inputs.get(key)
            if widget is not None:
                win._set_widget_value_from_string(widget, value)
                applied_keys.append(key)
        win._sync_input_source_mode_widgets()
        win._sync_workflow_widgets()
        for line in jana_handoff_log_lines(handoff_import, inflip_path, applied_keys):
            win._append_execution_log(line, subsystem="Jana2020")
        win._append_execution_log(
            "After the full pipeline finishes, use the 'Pass data to Jana2020' button to choose the cycle and map source for the final Jana2020 hand-off.",
            level="DETAIL",
            subsystem="Jana2020",
        )
    win.setWindowTitle("Phase Studio 1.0.1 for Jana2020")
    win.show()
    splash.finish(win)
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
        code = run_jana_superflip(args, options, logger)
        logger("Wrapper finished")
        return int(code)
    except Exception as exc:
        logger("ERROR: " + str(exc))
        logger(traceback.format_exc())
        try:
            qt = _qt_imports()
            QApplication = qt["QApplication"]
            QMessageBox = qt["QMessageBox"]
            QApplication.instance() or QApplication([sys.argv[0]])
            QMessageBox.critical(None, "Phase Studio 1.0.1 for Jana2020 — calculation error", str(exc))
        except Exception:
            pass
        return 1
    finally:
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main())
