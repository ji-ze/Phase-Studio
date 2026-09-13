"""Symbol-level import verification for a PyInstaller onedir distribution.

For every PE file in the distribution, resolve each imported DLL the way the
Windows loader would on a clean machine (distribution directories first, then
the system directory) and check that every imported *symbol* is actually
exported by the DLL that will provide it.

An unsatisfied symbol is precisely what produces::

    ImportError: DLL load failed while importing <mod>:
    The specified procedure could not be found.

(``ERROR_PROC_NOT_FOUND``, 127 -- as opposed to 126, a missing DLL.)

Also reports *duplicate* DLL base names inside the distribution: Windows keeps
one module per base name per process, so two different builds of, say,
``MSVCP140.dll`` cannot coexist -- whichever loads first serves everybody.

Usage::

    python packaging/tools/verify_imports.py dist/PhaseStudio
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

try:
    import pefile
except ImportError:  # pragma: no cover
    sys.exit("pefile is required: python -m pip install pefile")

SYSTEM_DIR = Path(r"C:\Windows\System32")
WINSXS_DIR = Path(r"C:\Windows\WinSxS")

# Libraries delivered through a side-by-side assembly rather than System32.
# PyInstaller embeds a manifest requesting Microsoft.Windows.Common-Controls
# 6.0.0.0, so comctl32 imports resolve to the WinSxS v6 assembly (which
# exports e.g. LoadIconMetric / TaskDialogIndirect); the System32 copy is the
# legacy 5.82 build and lacks them.
SXS_ASSEMBLIES = {
    "comctl32.dll": "amd64_microsoft.windows.common-controls_6595b64144ccf1df_6.0.",
}


def _sxs_candidates(dll: str) -> list[Path]:
    prefix = SXS_ASSEMBLIES.get(dll.lower())
    if not prefix or not WINSXS_DIR.is_dir():
        return []
    matches = sorted(
        (d for d in WINSXS_DIR.iterdir()
         if d.is_dir() and d.name.startswith(prefix)),
        reverse=True,  # highest version first
    )
    return [d / dll for d in matches]

# pefile caps the export table at MAX_SYMBOL_EXPORT_COUNT (0x2000 = 8192) and
# silently truncates beyond it.  Qt6Core/Qt6Gui export well over 30000 symbols,
# so the default cap makes perfectly good exports look missing.  Raise it.
_EXPORT_CAP = 0x100000


def _open(path: Path) -> "pefile.PE":
    return pefile.PE(str(path), fast_load=True, max_symbol_exports=_EXPORT_CAP)


def pe_exports(path: Path) -> set[str] | None:
    """Exported names plus ``#<ordinal>`` entries, or None if unparseable."""
    try:
        pe = _open(path)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    except Exception:
        return None
    names: set[str] = set()
    export_dir = getattr(pe, "DIRECTORY_ENTRY_EXPORT", None)
    if export_dir is not None:
        for symbol in export_dir.symbols:
            if symbol.name:
                names.add(symbol.name.decode("ascii", "replace"))
            if symbol.ordinal is not None:
                names.add(f"#{symbol.ordinal}")
    pe.close()
    return names


def pe_imports(path: Path) -> dict[str, set[str]] | None:
    """{dll_name_lower: {symbol or '#ordinal', ...}} for normal + delay imports."""
    try:
        pe = _open(path)
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
        ])
    except Exception:
        return None
    result: dict[str, set[str]] = defaultdict(set)
    # Delay imports are resolved lazily and are frequently optional, so they are
    # tracked separately (prefixed) and only reported as warnings.
    for attr, prefix in (("DIRECTORY_ENTRY_IMPORT", ""),
                         ("DIRECTORY_ENTRY_DELAY_IMPORT", "delay:")):
        for entry in getattr(pe, attr, None) or []:
            if not entry.dll:
                continue
            key = prefix + entry.dll.decode("ascii", "replace").lower()
            for imp in entry.imports:
                if imp.name:
                    result[key].add(imp.name.decode("ascii", "replace"))
                elif imp.ordinal is not None:
                    result[key].add(f"#{imp.ordinal}")
    pe.close()
    return dict(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", help="onedir distribution directory")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    dist = Path(args.dist).resolve()
    if not dist.is_dir():
        sys.exit(f"not a directory: {dist}")

    pe_files = sorted(
        p for p in dist.rglob("*")
        if p.is_file() and p.suffix.lower() in {".dll", ".pyd", ".exe", ".drv"}
    )

    # Index of DLL base name -> paths inside the distribution.
    index: dict[str, list[Path]] = defaultdict(list)
    for path in pe_files:
        index[path.name.lower()].append(path)

    print(f"Distribution : {dist}")
    print(f"PE files     : {len(pe_files)}")
    print()

    # ---- duplicate base names -------------------------------------------
    duplicates = {
        name: paths for name, paths in index.items()
        if len(paths) > 1 and len({p.stat().st_size for p in paths}) > 1
    }
    if duplicates:
        print("DUPLICATE DLL BASE NAMES WITH DIFFERING CONTENT")
        print("  (Windows loads one module per base name per process.)")
        for name in sorted(duplicates):
            print(f"  {name}")
            for path in duplicates[name]:
                version = ""
                try:
                    pe = _open(path)
                    pe.parse_data_directories(directories=[
                        pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
                    if hasattr(pe, "VS_FIXEDFILEINFO") and pe.VS_FIXEDFILEINFO:
                        info = pe.VS_FIXEDFILEINFO[0]
                        version = "%d.%d.%d.%d" % (
                            info.FileVersionMS >> 16, info.FileVersionMS & 0xFFFF,
                            info.FileVersionLS >> 16, info.FileVersionLS & 0xFFFF)
                    pe.close()
                except Exception:
                    pass
                print(f"      {path.relative_to(dist)}  "
                      f"size={path.stat().st_size} version={version or '-'}")
        print()

    # ---- symbol resolution ----------------------------------------------
    export_cache: dict[Path, set[str] | None] = {}

    def resolve(dll: str, importer: Path) -> Path | None:
        """Loader-like lookup restricted to the distribution + system dir."""
        candidates = [importer.parent / dll, dist / dll, dist / "_internal" / dll]
        candidates += index.get(dll.lower(), [])
        # Side-by-side assemblies win over System32 when a manifest asks for
        # them, which PyInstaller-built executables do for common controls.
        candidates += _sxs_candidates(dll)
        candidates.append(SYSTEM_DIR / dll)
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    hard_failures: list[str] = []
    delay_failures: list[str] = []
    missing_dlls: list[str] = []

    for path in pe_files:
        imports = pe_imports(path)
        if not imports:
            continue
        for key, symbols in imports.items():
            delayed = key.startswith("delay:")
            dll = key[6:] if delayed else key
            # API-set contracts are resolved by the loader from the OS schema,
            # never from a file on disk.  Windows 10/11 always satisfies them.
            if dll.startswith(("api-ms-win-", "ext-ms-win-")):
                continue
            target = resolve(dll, path)
            if target is None:
                message = f"{path.relative_to(dist)} -> {dll} (DLL not found)"
                (delay_failures if delayed else missing_dlls).append(message)
                continue
            if target not in export_cache:
                export_cache[target] = pe_exports(target)
            available = export_cache[target]
            if available is None:
                continue
            unsatisfied = sorted(s for s in symbols if s not in available)
            if not unsatisfied:
                continue
            where = target if SYSTEM_DIR in target.parents else target.relative_to(dist)
            message = (f"{path.relative_to(dist)} -> {dll} [{where}]: "
                       f"{len(unsatisfied)} missing: {', '.join(unsatisfied[:6])}")
            (delay_failures if delayed else hard_failures).append(message)

    if missing_dlls:
        print("MISSING DLLs (error 126 -- 'specified module could not be found')")
        for message in missing_dlls:
            print(f"  {message}")
        print()

    if hard_failures:
        print("UNSATISFIED IMPORTED SYMBOLS "
              "(error 127 -- 'specified procedure could not be found')")
        for message in hard_failures:
            print(f"  {message}")
        print()

    if delay_failures and not args.quiet:
        print(f"delay-load imports not resolvable ({len(delay_failures)}) -- "
              f"usually optional, listed for information:")
        for message in delay_failures:
            print(f"  {message}")
        print()

    problems = len(hard_failures) + len(missing_dlls)
    print(f"Result: {problems} blocking problem(s), "
          f"{len(duplicates)} conflicting duplicate DLL name(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
