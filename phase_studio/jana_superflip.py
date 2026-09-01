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
        # Must match one of the "Map format" combo items in app.py exactly (XPLOR is
        # always produced regardless; "jana" additionally saves Jana m80/m81 for hand-off).
        "map_export_format": "jana",
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
        raise FileNotFoundError(f"Inflip file not found: {inflip_path}")
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
                raise RuntimeError(f"SharpED did not create expected deblurred map: {deblurred_map}")
            log(f"Deblurred map: {deblurred_map}")
            selected_map = deblurred_map
        else:
            selected_map = xplor_map

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
            QGroupBox,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMessageBox,
            QPushButton,
            QRadioButton,
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
        "QGroupBox": QGroupBox,
        "QHBoxLayout": QHBoxLayout,
        "QHeaderView": QHeaderView,
        "QLabel": QLabel,
        "QLineEdit": QLineEdit,
        "QMessageBox": QMessageBox,
        "QPushButton": QPushButton,
        "QRadioButton": QRadioButton,
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
    WORKFLOW_SUPERFLIP_ONLY: "Run Superflip once and hand the result back to Jana2020.",
    WORKFLOW_SUPERFLIP_SHARPED: "Run Superflip once, then sharpen the resulting map with SharpED.",
    WORKFLOW_PHASE_RECYCLING: (
        "Repeat Superflip and SharpED over several cycles, feeding each cycle's map "
        "back in as the next model."
    ),
}


def show_jana_dialog(args: Sequence[str], inflip_path: Optional[Path]) -> JanaRunOptions:
    qt = _qt_imports()
    QApplication = qt["QApplication"]
    QButtonGroup = qt["QButtonGroup"]
    QComboBox = qt["QComboBox"]
    QDialog = qt["QDialog"]
    QDoubleSpinBox = qt["QDoubleSpinBox"]
    QFileDialog = qt["QFileDialog"]
    QFormLayout = qt["QFormLayout"]
    QGroupBox = qt["QGroupBox"]
    QHBoxLayout = qt["QHBoxLayout"]
    QLabel = qt["QLabel"]
    QLineEdit = qt["QLineEdit"]
    QPushButton = qt["QPushButton"]
    QRadioButton = qt["QRadioButton"]
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

    settings = QSettings("PhaseStudio", "JanaSuperflipWrapper")
    saved_workflow = str(settings.value("workflow", WORKFLOW_SUPERFLIP_ONLY))
    if saved_workflow not in WORKFLOW_LABELS:
        saved_workflow = WORKFLOW_SUPERFLIP_ONLY

    dialog = QDialog()
    dialog.setWindowTitle(f"Phase Studio {__version__} for Jana2020")
    dialog.setMinimumWidth(640)
    dialog.resize(680, 560)

    root = QVBoxLayout(dialog)
    root.setContentsMargins(14, 14, 14, 14)
    root.setSpacing(10)

    title = QLabel(f"Phase Studio {__version__} for Jana2020")
    title_font = title.font()
    title_font.setPointSize(title_font.pointSize() + 5)
    title_font.setBold(True)
    title.setFont(title_font)
    root.addWidget(title)

    inflip_info = QLabel(
        f"Incoming Jana2020 file: {inflip_path.name}" if inflip_path else "No .inflip argument was detected."
    )
    inflip_info.setToolTip(str(inflip_path) if inflip_path else "")
    root.addWidget(inflip_info)

    stack = QStackedWidget()
    root.addWidget(stack, 1)

    # ----- Page 1: reference/model files, then the 3 primary workflow actions -----
    page1 = QWidget()
    page1_layout = QVBoxLayout(page1)
    page1_layout.setContentsMargins(0, 0, 0, 0)
    page1_layout.setSpacing(10)

    files_group = QGroupBox("Reference and model files")
    files_form = QFormLayout(files_group)
    files_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

    def add_file_row(label_text: str, file_filter: str, tooltip: str, placeholder: str, initial: str):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit(initial)
        edit.setPlaceholderText(placeholder)
        edit.setToolTip(tooltip)
        browse = QPushButton("Browse…")
        browse.setToolTip(f"Select {label_text.lower()}.")

        def browse_file() -> None:
            selected = QFileDialog.getOpenFileName(dialog, f"Select {label_text}", edit.text(), file_filter)[0]
            if selected:
                edit.setText(selected)

        browse.clicked.connect(browse_file)
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(browse)
        files_form.addRow(label_text, row_widget)
        return edit

    def _inflip_keyword_default(keyword: str) -> str:
        # Deliberately not persisted across runs: these fields reflect what the
        # incoming Jana2020 .inflip already declares, not a remembered value from
        # an unrelated previous job.
        if inflip_path is None:
            return ""
        try:
            found = inflip_keyword_path(inflip_path, keyword)
        except Exception:
            return ""
        return str(found) if found is not None else ""

    reference_file = add_file_row(
        "Reference file",
        "Reference files (*.cif *.xplor);;CIF structures (*.cif);;XPLOR maps (*.xplor);;All files (*)",
        "Optional reference CIF structure or XPLOR density map, used together with the "
        "incoming Jana .inflip without replacing its embedded reflections or metadata. "
        "When supplied, Superflip also reports how well each cycle matches this reference, "
        "which is used to recommend the best map for the Jana2020 hand-off. Pre-filled from "
        "the incoming .inflip's own referencefile keyword, if it declares one.",
        "Use metadata embedded in the Jana .inflip",
        _inflip_keyword_default("referencefile"),
    )
    model_file = add_file_row(
        "Model file",
        "Model/map files (*.xplor *.ccp4 *.cif);;XPLOR maps (*.xplor);;CCP4 maps (*.ccp4);;CIF structures (*.cif);;All files (*)",
        "Optional model or density map to seed the first Superflip cycle. If supplied, "
        "cycle 1 is model-seeded: repeatmode is forced to 1 and randomseed is omitted. "
        "Pre-filled from the incoming .inflip's own modelfile keyword, if it declares one.",
        "No first-cycle modelfile",
        _inflip_keyword_default("modelfile"),
    )
    page1_layout.addWidget(files_group)

    workflow_group = QGroupBox("Workflow")
    workflow_group_layout = QVBoxLayout(workflow_group)
    workflow_group_layout.setSpacing(8)
    workflow_buttons: dict[str, QPushButton] = {}
    for key in (WORKFLOW_SUPERFLIP_ONLY, WORKFLOW_SUPERFLIP_SHARPED, WORKFLOW_PHASE_RECYCLING):
        workflow_button = QPushButton(WORKFLOW_LABELS[key])
        workflow_button.setObjectName("primaryButton")
        workflow_button.setToolTip(WORKFLOW_DESCRIPTIONS[key])
        workflow_button.setMinimumHeight(38)
        workflow_group_layout.addWidget(workflow_button)
        workflow_buttons[key] = workflow_button
    page1_layout.addWidget(workflow_group)
    page1_layout.addStretch(1)
    stack.addWidget(page1)

    # ----- Page 2: SharpED / phase-recycling settings (workflows 2 and 3 only) -----
    page2 = QWidget()
    page2_layout = QVBoxLayout(page2)
    page2_layout.setContentsMargins(0, 0, 0, 0)
    page2_layout.setSpacing(10)

    page2_title = QLabel("")
    page2_title_font = page2_title.font()
    page2_title_font.setBold(True)
    page2_title.setFont(page2_title_font)
    page2_layout.addWidget(page2_title)

    map_group = QGroupBox("Map used for phase recycling and hand-off")
    map_group_layout = QVBoxLayout(map_group)
    map_buttons = QButtonGroup(dialog)
    sharped_map_radio = QRadioButton("SharpED map (deblurred)")
    superflip_map_radio = QRadioButton("Superflip map (raw)")
    sharped_map_radio.setToolTip(
        "Feed each next cycle with the SharpED-sharpened map and prefer it for the Jana2020 hand-off."
    )
    superflip_map_radio.setToolTip(
        "Feed each next cycle with the raw Superflip map, without SharpED sharpening."
    )
    map_buttons.addButton(sharped_map_radio)
    map_buttons.addButton(superflip_map_radio)
    map_group_layout.addWidget(sharped_map_radio)
    map_group_layout.addWidget(superflip_map_radio)
    saved_next_cycle = str(settings.value("next_cycle_modelfile", "deblurred_xplor")).strip().lower()
    if saved_next_cycle == "superflip_xplor":
        superflip_map_radio.setChecked(True)
    else:
        sharped_map_radio.setChecked(True)
    page2_layout.addWidget(map_group)

    processing_form = QFormLayout()
    processing_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

    cycles = QSpinBox()
    cycles.setRange(1, 999)
    cycles.setValue(int(settings.value("cycles", 1)) or 1)
    cycles.setToolTip("Total number of Superflip/SharpED cycles.")
    processing_form.addRow("Processing cycles", cycles)

    cycles_user_edited = {"value": False}

    def mark_cycles_user_edited(_value: int = 0) -> None:
        cycles_user_edited["value"] = True

    cycles.valueChanged.connect(mark_cycles_user_edited)

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
    processing_form.addRow("Model", model)
    page2_layout.addLayout(processing_form)

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
    page2_layout.addWidget(refresh_row)

    sharped_group = QGroupBox()
    sharped_outer = QVBoxLayout(sharped_group)
    sharped_toggle = QToolButton()
    sharped_toggle.setText("Setup API")
    sharped_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    sharped_toggle.setArrowType(Qt.RightArrow)
    sharped_toggle.setCheckable(True)
    sharped_toggle.setChecked(False)
    sharped_toggle.setToolTip("Expand or collapse the SharpED server connection settings.")
    sharped_outer.addWidget(sharped_toggle)
    sharped_body = QWidget()
    sharped_form = QFormLayout(sharped_body)
    sharped_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    sharped_form.setContentsMargins(18, 4, 0, 0)

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

    sharped_outer.addWidget(sharped_body)
    sharped_body.setVisible(False)

    def sync_sharped_disclosure(opened: bool) -> None:
        sharped_body.setVisible(bool(opened))
        sharped_toggle.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)

    sharped_toggle.toggled.connect(sync_sharped_disclosure)
    page2_layout.addWidget(sharped_group)

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
            model_status.setText("Unable to retrieve the model list.")
            model_status.setToolTip(
                "Model discovery failed. Verify the server URL and network connection; "
                "a model identifier may still be entered manually.\n\n"
                + sanitize_error_details(payload)
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
    page2_layout.addWidget(validation_group)
    page2_layout.addStretch(1)
    stack.addWidget(page2)

    def sync_map_choice() -> None:
        validation_group.setVisible(sharped_map_radio.isChecked())

    sharped_map_radio.toggled.connect(lambda _checked=False: sync_map_choice())
    sync_map_choice()

    # ----- Shared bottom row: a prominent "Run" action (page 2 only) plus the
    # less prominent Back / Cancel / Open full Phase Studio actions. -----
    button_row = QHBoxLayout()
    back_button = QPushButton("‹ Back")
    back_button.setToolTip("Return to the workflow selection.")
    cancel_button = QPushButton("Cancel")
    cancel_button.setToolTip("Close the launcher without starting or modifying the Jana2020 job.")
    edit_button = QPushButton("Open full Phase Studio configuration")
    edit_button.setToolTip(
        "Open the complete Phase Studio workspace with parameters imported from the "
        "Jana2020 .inflip file. Embedded reflections are exported to a working HKL file "
        "unless an external HKL override is selected there."
    )
    primary_button = QPushButton("Run Jana2020 calculation")
    primary_button.setObjectName("primaryButton")
    primary_button.setDefault(True)
    button_row.addWidget(back_button)
    button_row.addStretch(1)
    button_row.addWidget(cancel_button)
    button_row.addWidget(edit_button)
    button_row.addWidget(primary_button)
    root.addLayout(button_row)

    workflow_state = {"key": saved_workflow}

    def current_workflow() -> str:
        return workflow_state["key"]

    def apply_workflow_cycle_default(key: str) -> None:
        # "Superflip + SharpED" is always a single Superflip call followed by one
        # SharpED pass; only "Phase recycling" repeats that pair over several cycles.
        cycles.setEnabled(key == WORKFLOW_PHASE_RECYCLING)
        if cycles_user_edited["value"] and key == WORKFLOW_PHASE_RECYCLING:
            return
        cycles.blockSignals(True)
        try:
            if key == WORKFLOW_PHASE_RECYCLING:
                cycles.setValue(max(int(settings.value("cycles", 5)) or 5, 2))
            else:
                cycles.setValue(1)
        finally:
            cycles.blockSignals(False)

    def workflow_changed() -> None:
        key = current_workflow()
        page2_title.setText(WORKFLOW_LABELS[key])
        if key != WORKFLOW_SUPERFLIP_ONLY:
            apply_workflow_cycle_default(key)

    workflow_changed()

    def go_to_page1() -> None:
        stack.setCurrentWidget(page1)
        back_button.setVisible(False)
        primary_button.setVisible(False)

    def go_to_page2() -> None:
        stack.setCurrentWidget(page2)
        back_button.setVisible(True)
        primary_button.setVisible(True)
        primary_button.setText("Run Jana2020 calculation")
        primary_button.setToolTip(
            "Execute the Jana2020 Superflip job through the Phase Studio cycle wrapper. "
            "For every model-seeded cycle, repeatmode 1 is enforced and randomseed is omitted."
        )

    back_button.clicked.connect(go_to_page1)
    go_to_page1()

    result = {"action": "cancel"}

    def effective_next_cycle_mode() -> str:
        if current_workflow() == WORKFLOW_SUPERFLIP_ONLY:
            return "none"
        return "superflip_xplor" if superflip_map_radio.isChecked() else "deblurred_xplor"

    def effective_cycles() -> int:
        return 1 if current_workflow() == WORKFLOW_SUPERFLIP_ONLY else cycles.value()

    def save_values() -> None:
        next_cycle_mode = effective_next_cycle_mode()
        settings.setValue("workflow", current_workflow())
        settings.setValue("cycles", effective_cycles())
        settings.setValue("next_cycle_modelfile", next_cycle_mode)
        settings.setValue("use_deblurred_map", next_cycle_mode == "deblurred_xplor")
        settings.setValue("server_url", server_url.text())
        settings.setValue("api_token", api_token.text())
        settings.setValue("model", model.currentText())
        settings.setValue("elements", elements.text())
        settings.setValue("outres", outres.value())
        # Reference file / model file are deliberately not persisted: they should
        # reflect the incoming .inflip (or be blank), never a leftover value from
        # an unrelated previous Jana2020 job.
        settings.sync()

    def build_options(action: str) -> JanaRunOptions:
        next_cycle_mode = effective_next_cycle_mode()
        return JanaRunOptions(
            action=action,
            cycles=effective_cycles(),
            use_deblurred_map=next_cycle_mode == "deblurred_xplor",
            next_cycle_modelfile=next_cycle_mode,
            api_token=api_token.text().strip(),
            server_url=server_url.text().strip() or DEFAULT_SERVER_URL,
            model=model.currentText().strip() or "default",
            elements=elements.text().strip() or "C N O",
            outres=float(outres.value()),
            input_mode=INPUT_MODE_INFLIP,
            hkl_override="",
            reference_override="",
            superflip_referencefile=reference_file.text().strip(),
            first_cycle_modelfile=model_file.text().strip(),
        )

    def attempt_run() -> None:
        token = api_token.text().strip() or os.environ.get("SHARPED_API_TOKEN", "").strip()
        if effective_next_cycle_mode() == "deblurred_xplor" and not token:
            if stack.currentWidget() is not page2:
                go_to_page2()
            sharped_toggle.setChecked(True)
            api_token.setFocus()
            _show_missing_token_warning(dialog, qt)
            return
        save_values()
        result["action"] = "recycle" if current_workflow() == WORKFLOW_PHASE_RECYCLING else "run"
        dialog.accept()

    def edit_clicked() -> None:
        save_values()
        result["action"] = "edit"
        dialog.accept()

    def workflow_button_clicked(key: str) -> None:
        workflow_state["key"] = key
        workflow_changed()
        if key == WORKFLOW_SUPERFLIP_ONLY:
            attempt_run()
        else:
            go_to_page2()

    for _key, _button in workflow_buttons.items():
        _button.clicked.connect(lambda _checked=False, _k=_key: workflow_button_clicked(_k))

    primary_button.clicked.connect(attempt_run)
    edit_button.clicked.connect(edit_clicked)
    cancel_button.clicked.connect(dialog.reject)

    accepted = dialog.exec()
    refresh_timer.stop()
    if not accepted:
        return JanaRunOptions(action="cancel")
    return build_options(result["action"])


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
        if auto_start:
            # Fill every EDMA/Superflip setting the dialog and the .inflip don't
            # cover with Phase Studio's own "recommended" preset first, so the
            # values applied below (this Jana2020 run's explicit choices) win.
            win._apply_workflow_preset("recommended")
        if inflip_path is not None and handoff_import is not None:
            splash.set_status("Loading Jana2020 hand-off…")
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
                    "Phase recycling was requested from the Jana2020 launcher; the pipeline "
                    "will start automatically. Use 'Send to Jana2020' once it finishes.",
                    level="DETAIL",
                    subsystem="Jana2020",
                )
            else:
                win._append_execution_log(
                    "After the full pipeline finishes, use the 'Send to Jana2020' button to choose the cycle and map source for the final Jana2020 hand-off.",
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
