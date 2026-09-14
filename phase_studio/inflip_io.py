"""Lightweight, formatting-preserving helpers for Superflip ``.inflip`` files."""
from __future__ import annotations

import shlex
from pathlib import Path
from typing import Callable, Iterable, List, Sequence, Tuple


COMMENT_MARKERS = ("#", "!", ";")
_M80_REPLACED_KEYWORDS = {
    "modelfile", "modelformat", "repeatmode", "randomseed", "polish",
    "maxcycles", "searchsymmetry", "derivesymmetry", "voxel",
}


def split_inline_comment(line: str) -> Tuple[str, str]:
    """Split a comment marker only when it occurs outside double quotes."""
    quote = False
    for index, character in enumerate(line):
        if character == '"':
            quote = not quote
        elif not quote and character in COMMENT_MARKERS:
            return line[:index].rstrip(), line[index:]
    return line.rstrip(), ""


def split_inflip_line(line: str) -> List[str]:
    """Tokenize a Jana wrapper line while preserving quoted comment markers."""
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
    return parts[0].lower() if parts else ""


def split_inflip_line_legacy(line: str) -> List[str]:
    """Tokenize with the full GUI's established first-marker comment policy."""
    text = str(line or "")
    for marker in COMMENT_MARKERS:
        if marker in text:
            text = text.split(marker, 1)[0]
    text = text.strip()
    if not text:
        return []
    try:
        return shlex.split(text)
    except Exception:
        return text.split()


def first_token_legacy(line: str) -> str:
    parts = split_inflip_line_legacy(line)
    return parts[0].lower() if parts else ""


def _insert_before_fbegin(
    lines: Sequence[str], new_line: str, token_reader: Callable[[str], str],
) -> List[str]:
    output: List[str] = []
    inserted = False
    for line in lines:
        if not inserted and token_reader(line) == "fbegin":
            output.append(new_line)
            inserted = True
        output.append(line)
    if not inserted:
        output.append(new_line)
    return output


def insert_before_fbegin(lines: Sequence[str], new_line: str) -> List[str]:
    return _insert_before_fbegin(lines, new_line, first_token)


def insert_before_fbegin_legacy(lines: Sequence[str], new_line: str) -> List[str]:
    return _insert_before_fbegin(lines, new_line, first_token_legacy)


def _without_keywords(
    lines: Sequence[str], keywords: Iterable[str], token_reader: Callable[[str], str],
) -> List[str]:
    blocked = {str(keyword).lower() for keyword in keywords}
    return [line for line in lines if token_reader(line) not in blocked]


def without_keywords(lines: Sequence[str], keywords: Iterable[str]) -> List[str]:
    return _without_keywords(lines, keywords, first_token)


def without_keywords_legacy(lines: Sequence[str], keywords: Iterable[str]) -> List[str]:
    return _without_keywords(lines, keywords, first_token_legacy)


def line_has_xplor_output(line: str) -> bool:
    body, _comment = split_inline_comment(line)
    parts = body.split()
    return any(Path(part.strip('"')).suffix.lower() == ".xplor" for part in parts[1:])


def ensure_xplor_output(lines: Sequence[str], base_name: str) -> List[str]:
    output: List[str] = []
    changed = False
    found = False
    xplor_name = f"{base_name}.xplor"
    for line in lines:
        if first_token(line) == "outputfile":
            found = True
            if line_has_xplor_output(line):
                output.append(line)
            else:
                body, comment = split_inline_comment(line)
                spacer = "" if not body or body.endswith((" ", "\t")) else " "
                tail = (" " + comment) if comment else ""
                output.append(f'{body}{spacer}"{xplor_name}"{tail}')
                changed = True
        else:
            output.append(line)
    if not found:
        output = insert_before_fbegin(output, f'outputfile "{xplor_name}"')
        changed = True
    return output if changed else list(lines)


def add_modelseed_modelfile(
    lines: Sequence[str], model_name: str, suffix: str = ".xplor",
) -> List[str]:
    """Apply the deterministic model-seeded policy used by the Jana wrapper."""
    del suffix  # Retained for the established caller contract.
    cleaned = without_keywords(
        lines, {"modelfile", "modelformat", "repeatmode", "randomseed"},
    )
    cleaned = insert_before_fbegin(cleaned, "repeatmode 1")
    return insert_before_fbegin(cleaned, f"modelfile {model_name}")


def apply_reference_override(lines: Sequence[str], reference_path: Path) -> List[str]:
    """Replace a Jana wrapper reference with a supported local file."""
    if reference_path.suffix.lower() not in {".cif", ".xplor"}:
        raise ValueError(
            "Reference override must be a CIF structure or an XPLOR density map: "
            f"{reference_path}"
        )
    cleaned = without_keywords(lines, {"referencefile", "referenceformat"})
    return insert_before_fbegin(cleaned, f"referencefile {Path(reference_path).name}")


def _header_for_m80(
    lines: Sequence[str], token_reader: Callable[[str], str],
) -> List[str]:
    header: List[str] = []
    for line in lines:
        if "# Keywords for charge flipping" in line or token_reader(line) == "fbegin":
            break
        header.append(line)
    return header


def inflip_header_for_m80(lines: Sequence[str]) -> List[str]:
    return _header_for_m80(lines, first_token)


def inflip_header_for_m80_legacy(lines: Sequence[str]) -> List[str]:
    return _header_for_m80(lines, first_token_legacy)


def _wrapper_outputfile(line: str, ready_name: str) -> str:
    body, comment = split_inline_comment(line)
    if ready_name.lower() not in body.lower():
        spacer = "" if body.endswith((" ", "\t")) else " "
        body = f'{body}{spacer}"{ready_name}"'
    return body if not comment else f"{body} {comment}"


def _legacy_outputfile(line: str, ready_name: str) -> str:
    body = str(line).split("#", 1)[0].rstrip()
    if ready_name.lower() not in body.lower():
        spacer = "" if body.endswith((" ", "\t")) else " "
        body = f'{body}{spacer}"{ready_name}"'
    return body


def _define_m80_inflip(
    header_lines: Sequence[str],
    base_name: str,
    model_name: str,
    token_reader: Callable[[str], str],
    insert_line: Callable[[Sequence[str], str], List[str]],
    rewrite_outputfile: Callable[[str, str], str],
) -> List[str]:
    output: List[str] = []
    saw_perform = False
    saw_outputfile = False
    ready_name = f"{base_name}-ready.xplor"
    for line in header_lines:
        key = token_reader(line)
        if key in _M80_REPLACED_KEYWORDS:
            continue
        if key == "perform" and not saw_perform:
            output.append("perform symmetry")
            saw_perform = True
            continue
        if key == "outputfile" and not saw_outputfile:
            output.append(rewrite_outputfile(line, ready_name))
            saw_outputfile = True
            continue
        output.append(line)
    if not saw_perform:
        output = insert_line(output, "perform symmetry")
    if not saw_outputfile:
        output = insert_line(output, f'outputfile "{ready_name}"')
    output.extend([
        "repeatmode 1",
        f'modelfile "{model_name}"',
        "polish no",
        "maxcycles 0",
        "searchsymmetry average",
        "derivesymmetry yes",
    ])
    return output


def define_m80_inflip(
    header_lines: Sequence[str], base_name: str, model_name: str,
) -> List[str]:
    return _define_m80_inflip(
        header_lines, base_name, model_name,
        first_token, insert_before_fbegin, _wrapper_outputfile,
    )


def define_m80_inflip_legacy(
    header_lines: Sequence[str], base_name: str, model_name: str,
) -> List[str]:
    return _define_m80_inflip(
        header_lines, base_name, model_name,
        first_token_legacy, insert_before_fbegin_legacy, _legacy_outputfile,
    )
