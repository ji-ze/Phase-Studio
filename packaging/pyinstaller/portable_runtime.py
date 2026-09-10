"""Shared portable-runtime staging for the Phase Studio Windows builds.

Imported from both ``packaging/pyinstaller/PhaseStudio.spec`` and the root
``superflip.spec``.  Everything here exists to make the PyInstaller **onedir**
output start on a clean, freshly-installed Windows 10/11 x64 machine with no
Python, no Conda, no PySide6/Qt and **no Visual C++ Redistributable**.

Four jobs, in the order the spec calls them:

``validate_pyside6_installation()``
    Refuse to build against a mixed or non-wheel PySide6.  The build must use
    one self-contained PySide6 distribution whose Qt DLLs, shiboken6 and Qt
    plugins all live inside the installed ``PySide6``/``shiboken6`` packages.
    Conda-forge/Anaconda PySide6 keeps Qt in ``<env>/Library/bin`` instead and
    is rejected, as are version-mismatched PySide6/shiboken6 pairs.

``strip_app_local_ucrt()``
    Drop any app-local Universal CRT (``ucrtbase.dll`` plus the
    ``api-ms-win-*.dll`` forwarder stubs).  The UCRT is a *component of
    Windows* on 10/11; shipping a private, older copy next to the executable
    is a portability hazard rather than a fix, and PyInstaller excludes it for
    exactly that reason.  Some redistributable Python builds put one in their
    install root, from where dependency analysis happily collects it.

``stage_msvc_runtime()``
    The VC++ runtime (``vcruntime140*.dll``, ``msvcp140*.dll``, ...) is *not*
    part of Windows -- a clean machine has it only if some other product
    installed ``vc_redist.x64.exe``.  It is redistributable, so it is bundled
    app-local.  The required set is discovered from the PE import tables of the
    binaries this build actually collected, and each DLL is taken from an
    explicit, in-environment source directory (never from ``System32`` and
    never from ``PATH``).  Exactly one copy of each is staged at the
    ``_internal`` root, because Windows keeps one module per base name per
    process: duplicate copies at different versions in different
    subdirectories are a real source of
    ``ImportError: DLL load failed ...: The specified procedure could not be
    found.``

``write_portable_manifest()``
    Record what was staged so ``packaging/build_windows.ps1`` can verify the
    finished distribution against the audited requirement instead of a
    hard-coded list.
"""

from __future__ import annotations

import json
import re
import sys
import sysconfig
from pathlib import Path

import pefile

__all__ = [
    "MSVC_RUNTIME_RE",
    "PortableRuntimeError",
    "stage_msvc_runtime",
    "strip_app_local_ucrt",
    "validate_pyside6_installation",
    "write_portable_manifest",
]


class PortableRuntimeError(RuntimeError):
    """Raised for build-environment problems that would produce a broken build."""


# Redistributable Visual C++ runtime DLLs.  Windows ships none of these.
MSVC_RUNTIME_RE = re.compile(
    r"^(?:vcruntime\d+(?:_\d+|_threads)?"
    r"|msvcp\d+(?:_\d+|_atomic_wait|_codecvt_ids)?"
    r"|concrt\d+|vcomp\d+|vcamp\d+|vccorlib\d+)\.dll$",
    re.IGNORECASE,
)

# App-local Universal CRT: a Windows component, never bundled.
UCRT_RE = re.compile(r"^(?:ucrtbase(?:d)?\.dll|api-ms-win-.*\.dll|ext-ms-win-.*\.dll)$",
                     re.IGNORECASE)

# pefile truncates export tables at 0x2000 symbols by default; Qt6Core alone
# exports well over 8000.  Only import tables are read here, but keep the cap
# high so the same helper can be reused for exports.
_PE_SYMBOL_CAP = 0x100000


# ---------------------------------------------------------------------------
# PE helpers
# ---------------------------------------------------------------------------

def _imported_dll_names(path: Path) -> set[str]:
    """Base names in *path*'s import + delay-import tables (lower-cased)."""
    try:
        pe = pefile.PE(str(path), fast_load=True, max_symbol_exports=_PE_SYMBOL_CAP)
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
        ])
    except Exception:
        return set()
    names: set[str] = set()
    for attr in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
        for entry in getattr(pe, attr, None) or []:
            if entry.dll:
                names.add(entry.dll.decode("ascii", "replace").lower())
    pe.close()
    return names


def _file_version(path: Path) -> tuple[int, int, int, int]:
    """``FileVersion`` from the version resource, or zeros when absent."""
    try:
        pe = pefile.PE(str(path), fast_load=True, max_symbol_exports=_PE_SYMBOL_CAP)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
        info = pe.VS_FIXEDFILEINFO[0] if getattr(pe, "VS_FIXEDFILEINFO", None) else None
        pe.close()
    except Exception:
        return (0, 0, 0, 0)
    if info is None:
        return (0, 0, 0, 0)
    return (info.FileVersionMS >> 16, info.FileVersionMS & 0xFFFF,
            info.FileVersionLS >> 16, info.FileVersionLS & 0xFFFF)


def _version_text(version: tuple[int, int, int, int]) -> str:
    return ".".join(str(part) for part in version)


# ---------------------------------------------------------------------------
# Environment discovery
# ---------------------------------------------------------------------------

def _site_packages() -> Path:
    return Path(sysconfig.get_paths()["purelib"])


def runtime_source_dirs() -> list[Path]:
    """Explicit, in-environment directories that may hold VC runtime DLLs.

    Ordered most-authoritative first.  ``System32`` and ``PATH`` are
    deliberately absent: the bundled runtime must come from the same toolchain
    as the wheels being packaged, and must not depend on what happens to be
    installed on the build machine.
    """
    site = _site_packages()
    candidates = [
        site / "PySide6",       # ships the VC runtime matching this Qt build
        site / "shiboken6",
        Path(sys.base_prefix),  # the interpreter's own vcruntime140*.dll
        Path(sys.prefix),
        Path(sys.base_prefix) / "DLLs",
    ]
    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_dir() and resolved not in seen:
            seen.add(resolved)
            ordered.append(resolved)
    return ordered


# ---------------------------------------------------------------------------
# 1. PySide6 / Qt consistency
# ---------------------------------------------------------------------------

def validate_pyside6_installation() -> dict[str, str]:
    """Verify one internally consistent PySide6/Qt runtime, or raise.

    Returns a small report describing what was accepted.
    """
    site = _site_packages()
    pyside_dir = site / "PySide6"
    shiboken_dir = site / "shiboken6"

    if not pyside_dir.is_dir():
        raise PortableRuntimeError(
            f"PySide6 is not installed in {site}. Install the PySide6 wheel into "
            f"the build environment (python -m pip install PySide6)."
        )

    # The wheel layout keeps Qt inside the package.  Conda-forge/Anaconda
    # PySide6 keeps Qt6*.dll in <env>/Library/bin and plugins in
    # <env>/Library/lib/qt6/plugins, which cannot be staged consistently.
    required_qt = ["Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll"]
    missing_qt = [name for name in required_qt if not (pyside_dir / name).is_file()]
    if missing_qt:
        library_bin = Path(sys.prefix) / "Library" / "bin"
        hint = ""
        if any((library_bin / name).is_file() for name in required_qt):
            hint = (
                f"\n  Qt was found in {library_bin} instead. That is a Conda/Anaconda "
                f"PySide6 build, whose Qt lives outside the Python package and must "
                f"not be mixed into a portable distribution.\n"
                f"  Build in a plain (non-Conda) virtual environment using the PySide6 "
                f"wheel from PyPI."
            )
        raise PortableRuntimeError(
            f"PySide6 at {pyside_dir} does not contain its own Qt runtime "
            f"(missing: {', '.join(missing_qt)}).{hint}"
        )

    if not (shiboken_dir).is_dir():
        raise PortableRuntimeError(f"shiboken6 is not installed in {site}.")

    # PySide6 and shiboken6 must be the same version: pyside6.abi3.dll is
    # linked against a specific shiboken6.abi3.dll ABI.
    try:
        from PySide6 import __version__ as pyside_version
    except Exception as exc:  # pragma: no cover
        raise PortableRuntimeError(f"cannot import PySide6: {exc}") from exc
    try:
        from shiboken6 import __version__ as shiboken_version
    except Exception as exc:  # pragma: no cover
        raise PortableRuntimeError(f"cannot import shiboken6: {exc}") from exc

    if pyside_version != shiboken_version:
        raise PortableRuntimeError(
            f"PySide6 ({pyside_version}) and shiboken6 ({shiboken_version}) versions "
            f"differ. A mismatched pair is the classic cause of "
            f"'DLL load failed while importing QtCore'."
        )

    plugins_dir = pyside_dir / "plugins"
    if not (plugins_dir / "platforms" / "qwindows.dll").is_file():
        raise PortableRuntimeError(
            f"the Qt Windows platform plugin is missing from {plugins_dir}. "
            f"Without plugins/platforms/qwindows.dll the packaged GUI cannot start."
        )

    return {
        "pyside6_version": pyside_version,
        "shiboken6_version": shiboken_version,
        "pyside6_path": str(pyside_dir),
        "qt_plugins_path": str(plugins_dir),
    }


# ---------------------------------------------------------------------------
# 2. App-local UCRT removal
# ---------------------------------------------------------------------------

def strip_app_local_ucrt(binaries: list[tuple]) -> tuple[list[tuple], list[str]]:
    """Remove app-local Universal CRT entries from a PyInstaller binaries TOC.

    Returns ``(filtered_toc, removed_names)``.
    """
    kept: list[tuple] = []
    removed: list[str] = []
    for entry in binaries:
        dest = str(entry[0])
        if UCRT_RE.match(Path(dest).name):
            removed.append(Path(dest).name)
            continue
        kept.append(entry)
    return kept, sorted(set(removed))


# ---------------------------------------------------------------------------
# 3. MSVC runtime staging
# ---------------------------------------------------------------------------

def _required_msvc_runtime_names(binaries: list[tuple], extra: list[Path]) -> set[str]:
    """VC runtime DLLs actually imported by the collected binaries."""
    required: set[str] = set()
    sources = [Path(entry[1]) for entry in binaries if len(entry) > 1]
    for path in sources + extra:
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".dll", ".pyd", ".exe"}:
            continue
        for name in _imported_dll_names(path):
            if MSVC_RUNTIME_RE.match(name):
                required.add(name.lower())
    return required


def _resolve_runtime_dll(name: str, search_dirs: list[Path]) -> Path | None:
    """Highest-versioned copy of *name* across *search_dirs*."""
    best: Path | None = None
    best_version = (-1, -1, -1, -1)
    for directory in search_dirs:
        for child in directory.iterdir():
            if child.name.lower() != name or not child.is_file():
                continue
            version = _file_version(child)
            if version > best_version:
                best, best_version = child, version
    return best


def stage_msvc_runtime(binaries: list[tuple]) -> tuple[list[tuple], list[dict]]:
    """Bundle exactly one copy of each required VC runtime DLL app-local.

    Every pre-existing VC-runtime entry is dropped from the TOC first, so the
    finished ``_internal`` tree holds a single, version-consistent copy of each
    DLL at its root rather than several copies in package subdirectories.

    Returns ``(new_toc, staged)`` where each ``staged`` item records the DLL
    name, the source it was taken from and its file version.
    """
    search_dirs = runtime_source_dirs()

    # Discover the requirement from the binaries this build collected, plus the
    # interpreter itself (its own vcruntime import must be satisfied too).
    extra = [p for p in (Path(sys.base_prefix) / f"python{sys.version_info.major}"
                         f"{sys.version_info.minor}.dll",) if p.is_file()]
    required = _required_msvc_runtime_names(binaries, extra)

    # A VC runtime DLL already collected by dependency analysis is required
    # even if nothing scanned above imports it directly.
    for entry in binaries:
        name = Path(str(entry[0])).name.lower()
        if MSVC_RUNTIME_RE.match(name):
            required.add(name)

    # Satellite libraries import from msvcp140.dll, so it is always needed
    # whenever any of them is.
    if any(n.startswith("msvcp140_") for n in required):
        required.add("msvcp140.dll")

    filtered = [
        entry for entry in binaries
        if not MSVC_RUNTIME_RE.match(Path(str(entry[0])).name)
    ]

    staged: list[dict] = []
    unresolved: list[str] = []
    for name in sorted(required):
        source = _resolve_runtime_dll(name, search_dirs)
        if source is None:
            unresolved.append(name)
            continue
        # Bare destination name -> the _internal root of the onedir bundle.
        filtered.append((source.name, str(source), "BINARY"))
        staged.append({
            "name": source.name,
            "source": str(source),
            "version": _version_text(_file_version(source)),
        })

    if unresolved:
        raise PortableRuntimeError(
            "these Visual C++ runtime DLLs are required by the collected binaries "
            "but were not found in the build environment: "
            + ", ".join(unresolved)
            + "\n  searched: " + ", ".join(str(d) for d in search_dirs)
            + "\n  Install the PySide6 wheel (it ships a matching VC runtime) or use "
              "a Python distribution that provides vcruntime140*.dll in its root."
        )

    versions = {item["version"] for item in staged}
    if len(versions) > 1:
        # Not fatal -- the VC runtime is backward compatible -- but a mixed set
        # is worth surfacing, since satellite/base skew can break loading.
        print(f"[portable-runtime] WARNING: staged VC runtime spans several "
              f"versions: {', '.join(sorted(versions))}")

    return filtered, staged


# ---------------------------------------------------------------------------
# 4. Build manifest
# ---------------------------------------------------------------------------

def write_portable_manifest(
    path: Path,
    *,
    app: str,
    staged_runtime: list[dict],
    qt_report: dict[str, str],
    removed_ucrt: list[str],
    extra_required: list[str] | None = None,
) -> None:
    """Write the JSON manifest consumed by ``packaging/build_windows.ps1``."""
    payload = {
        "app": app,
        "python": sys.version,
        "python_prefix": sys.base_prefix,
        "qt": qt_report,
        "msvc_runtime": staged_runtime,
        "removed_app_local_ucrt": removed_ucrt,
        # Qt libraries whose presence the build script also verifies.
        "required_binaries": extra_required or [
            "Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll",
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[portable-runtime] manifest written: {path}")


def report(app: str, staged_runtime: list[dict], qt_report: dict[str, str],
           removed_ucrt: list[str]) -> None:
    """Print a concise build-time summary."""
    print(f"[portable-runtime] {app}: PySide6 {qt_report['pyside6_version']} / "
          f"shiboken6 {qt_report['shiboken6_version']}")
    print(f"[portable-runtime] {app}: Qt from {qt_report['pyside6_path']}")
    for item in staged_runtime:
        print(f"[portable-runtime]   + {item['name']:<28} "
              f"{item['version']:<16} {item['source']}")
    if removed_ucrt:
        print(f"[portable-runtime] {app}: dropped app-local UCRT "
              f"({len(removed_ucrt)} file(s)); Windows 10/11 provides the UCRT")
