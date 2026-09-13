"""Windows native-dependency auditor for the Phase Studio portable build.

Walks the PE import tables of the given roots (recursively) with ``pefile`` and
reports, for every imported DLL, where it would actually be resolved from.

The point of the audit is to answer one question: *would this run on a clean
Windows 10/11 x64 box?*  A DLL is only acceptable if it is either

* shipped inside the distribution (``_internal``/next to the exe), or
* a DLL that a supported Windows 10/11 install always provides.

Anything else -- most importantly the MSVC runtime (``vcruntime140*.dll``,
``msvcp140*.dll``), which Windows does **not** ship -- must be bundled.

Usage::

    python packaging/tools/audit_dependencies.py dist/PhaseStudio/PhaseStudio.exe
    python packaging/tools/audit_dependencies.py --env      # audit the build env
    python packaging/tools/audit_dependencies.py --dist dist/PhaseStudio
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import sysconfig
from pathlib import Path

try:
    import pefile
except ImportError:  # pragma: no cover
    sys.exit("pefile is required: python -m pip install pefile")


# --------------------------------------------------------------------------
# Windows DLLs that a supported Windows 10/11 x64 installation always has.
# Matched case-insensitively against the bare file name.  Deliberately
# conservative: anything not listed here is reported so it can be reviewed.
# --------------------------------------------------------------------------
WINDOWS_SYSTEM_DLLS = {
    # Core Win32
    "kernel32.dll", "kernelbase.dll", "ntdll.dll", "user32.dll", "gdi32.dll",
    "gdi32full.dll", "advapi32.dll", "shell32.dll", "shlwapi.dll", "ole32.dll",
    "oleaut32.dll", "combase.dll", "rpcrt4.dll", "sechost.dll", "bcrypt.dll",
    "bcryptprimitives.dll", "crypt32.dll", "cryptbase.dll", "ncrypt.dll",
    "secur32.dll", "sspicli.dll", "userenv.dll", "version.dll", "winmm.dll",
    "ws2_32.dll", "mswsock.dll", "wsock32.dll", "iphlpapi.dll", "dnsapi.dll",
    "netapi32.dll", "winhttp.dll", "wininet.dll", "urlmon.dll", "imm32.dll",
    "comdlg32.dll", "comctl32.dll", "setupapi.dll", "cfgmgr32.dll",
    "powrprof.dll", "psapi.dll", "dbghelp.dll", "wintrust.dll", "authz.dll",
    "msi.dll", "oleacc.dll", "uxtheme.dll", "dwmapi.dll", "propsys.dll",
    "winspool.drv", "mpr.dll", "pdh.dll", "wtsapi32.dll", "credui.dll",
    "windowscodecs.dll", "wldap32.dll", "normaliz.dll", "profapi.dll",
    "d3dcompiler_47.dll",
    # Graphics / media
    "opengl32.dll", "glu32.dll", "d3d9.dll", "d3d11.dll", "d3d12.dll",
    "dxgi.dll", "dwrite.dll", "d2d1.dll", "dcomp.dll", "dxva2.dll",
    "avicap32.dll", "avrt.dll", "mf.dll", "mfplat.dll", "mfreadwrite.dll",
    "mfcore.dll", "mmdevapi.dll", "ksuser.dll", "dsound.dll",
    # Universal CRT -- part of Windows 10/11 itself
    "ucrtbase.dll", "api-ms-win-crt-runtime-l1-1-0.dll",
    # WinRT / misc
    "windows.storage.dll", "twinapi.appcore.dll", "wintypes.dll",
    "cryptnet.dll", "msvcrt.dll", "rometadata.dll", "hid.dll",
    "coremessaging.dll", "coreuicomponents.dll", "inputhost.dll",
    "textinputframework.dll", "usp10.dll", "clbcatq.dll", "bthprops.cpl",
    "deviceaccess.dll", "wbemuuid.dll", "wevtapi.dll", "srvcli.dll",
    "winsta.dll", "wer.dll", "nsi.dll", "cabinet.dll", "bcp47mrm.dll",
    "imagehlp.dll", "uiautomationcore.dll", "userenv.dll", "mpr.dll",
}

# DLLs that Windows provides, but only from a specific Windows 10 build.
# These cannot be bundled -- they are OS components and are not
# redistributable -- so they are reported separately as a documented minimum
# platform requirement rather than as a packaging defect.
WINDOWS_VERSION_GATED_DLLS = {
    # Microsoft's built-in ICU. Present only from Windows 10 version 1903
    # (build 18362) onwards. Qt 6 links it for text-codec support, so
    # Qt6Core.dll -- and therefore PySide6.QtCore -- cannot load without it.
    # https://learn.microsoft.com/en-us/windows/win32/intl/international-components-for-unicode--icu-
    "icuuc.dll": "Windows 10 1903+ (built-in ICU; required by Qt6Core.dll)",
    "icu.dll": "Windows 10 1903+ (built-in ICU)",
    "icuin.dll": "Windows 10 1903+ (built-in ICU)",
}

# API-set contract stubs: always satisfied by the OS on Windows 10/11.
APISET_RE = re.compile(r"^(api-ms-win-|ext-ms-win-)", re.IGNORECASE)

# The redistributable MSVC runtime.  Windows does NOT ship these; a clean PC
# only has them if some other product installed vc_redist.  They must be
# bundled app-local for the distribution to be portable.
MSVC_RUNTIME_RE = re.compile(
    r"^(vcruntime\d+(_\d+|_threads)?|msvcp\d+(_\d+|_atomic_wait|_codecvt_ids)?"
    r"|concrt\d+|vcomp\d+|vcamp\d+)\.dll$",
    re.IGNORECASE,
)


def is_apiset(name: str) -> bool:
    return bool(APISET_RE.match(name))


def is_windows_dll(name: str) -> bool:
    return name.lower() in WINDOWS_SYSTEM_DLLS or is_apiset(name)


def is_msvc_runtime(name: str) -> bool:
    return bool(MSVC_RUNTIME_RE.match(name))


def imported_dlls(path: Path) -> list[str]:
    """Return the DLL names in *path*'s import + delay-import tables."""
    names: list[str] = []
    try:
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(
            directories=[
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
            ]
        )
    except Exception as exc:  # noqa: BLE001 - non-PE or unreadable
        print(f"  ! cannot parse {path.name}: {exc}", file=sys.stderr)
        return names

    for attr in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
        for entry in getattr(pe, attr, None) or []:
            if entry.dll:
                names.append(entry.dll.decode("ascii", "replace"))
    pe.close()
    return sorted(set(names))


def walk(roots: list[Path], search_dirs: list[Path]) -> tuple[dict, dict]:
    """Recursively resolve the import graph of *roots* within *search_dirs*.

    Returns ``(resolved, unresolved)`` where ``resolved`` maps a lower-cased
    DLL name to the path it was found at, and ``unresolved`` maps a
    lower-cased DLL name to the set of importers that asked for it.
    """
    resolved: dict[str, Path] = {}
    unresolved: dict[str, set[str]] = {}
    pending = [p for p in roots if p.is_file()]
    seen: set[str] = set()

    def find(name: str) -> Path | None:
        for directory in search_dirs:
            candidate = directory / name
            if candidate.is_file():
                return candidate
            # Case-insensitive fallback for oddly-cased import entries.
            if directory.is_dir():
                for child in directory.iterdir():
                    if child.name.lower() == name.lower() and child.is_file():
                        return child
        return None

    while pending:
        current = pending.pop()
        key = current.name.lower()
        if key in seen:
            continue
        seen.add(key)
        for dep in imported_dlls(current):
            dep_key = dep.lower()
            if dep_key in resolved or dep_key in seen:
                continue
            if is_windows_dll(dep):
                continue
            found = find(dep)
            if found is None:
                unresolved.setdefault(dep_key, set()).add(current.name)
            else:
                resolved[dep_key] = found
                pending.append(found)
    return resolved, unresolved


def audit_dist(dist_dir: Path) -> int:
    exe = next(iter(sorted(dist_dir.glob("*.exe"))), None)
    if exe is None:
        sys.exit(f"no .exe found in {dist_dir}")
    internal = dist_dir / "_internal"
    search_dirs = [dist_dir, internal]
    search_dirs += [p for p in sorted(internal.rglob("*")) if p.is_dir()] if internal.is_dir() else []

    roots = [exe]
    for pattern in ("*.pyd", "*.dll"):
        roots += sorted(internal.rglob(pattern)) if internal.is_dir() else []

    print(f"Auditing distribution: {dist_dir}")
    print(f"  entry point : {exe.name}")
    print(f"  PE files    : {len(roots)}")

    resolved, unresolved = walk(roots, search_dirs)

    inside = {n: p for n, p in resolved.items() if dist_dir in p.parents or p.parent == dist_dir}
    outside = {n: p for n, p in resolved.items() if n not in inside}

    print("\nMSVC runtime DLLs bundled in the distribution:")
    msvc = sorted(n for n in inside if is_msvc_runtime(n))
    for name in msvc:
        print(f"  {name:<32} {inside[name].relative_to(dist_dir)}")
    if not msvc:
        print("  (none)")

    if outside:
        print("\nRESOLVED OUTSIDE THE DISTRIBUTION (not portable):")
        for name in sorted(outside):
            print(f"  {name:<32} {outside[name]}")

    gated = {n: v for n, v in unresolved.items() if n in WINDOWS_VERSION_GATED_DLLS}
    genuine = {n: v for n, v in unresolved.items() if n not in gated}

    if gated:
        print("\nProvided by Windows, but only from a given build "
              "(minimum platform requirement, cannot be bundled):")
        for name in sorted(gated):
            importers = ", ".join(sorted(gated[name])[:4])
            print(f"  {name:<32} {WINDOWS_VERSION_GATED_DLLS[name]}")
            print(f"  {'':<32} needed by {importers}")

    if genuine:
        print("\nUNRESOLVED (would fail on a clean PC):")
        for name in sorted(genuine):
            importers = ", ".join(sorted(genuine[name])[:4])
            print(f"  {name:<32} needed by {importers}")

    problems = len(outside) + len(genuine)
    print(f"\nResult: {len(inside)} bundled, {len(outside)} external, "
          f"{len(genuine)} unresolved, {len(gated)} OS-version-gated.")
    if problems == 0:
        print("PORTABLE: every non-Windows dependency ships inside the distribution.")
    return 1 if problems else 0


def audit_env(targets: list[str] | None = None) -> int:
    """Audit the *build environment* rather than a built distribution."""
    site = Path(sysconfig.get_paths()["purelib"])
    env_root = Path(sys.prefix)
    search_dirs = [
        env_root, env_root / "DLLs", env_root / "Library" / "bin",
        site, site / "PySide6", site / "shiboken6",
        Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs",
    ]
    search_dirs += [Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    search_dirs = [d for d in search_dirs if d.is_dir()]

    default_targets = [
        site / "PySide6" / "QtCore.pyd",
        site / "PySide6" / f"QtCore.cp{sys.version_info.major}{sys.version_info.minor}-win_amd64.pyd",
        site / "PySide6" / "QtGui.pyd",
        site / "PySide6" / "QtWidgets.pyd",
        site / "PySide6" / "Qt6Core.dll",
        site / "PySide6" / "Qt6Gui.dll",
        site / "PySide6" / "Qt6Widgets.dll",
        site / "shiboken6" / "Shiboken.pyd",
    ]
    default_targets += sorted(site.glob("gemmi*.pyd")) or sorted(site.glob("gemmi/*.pyd"))
    default_targets += sorted((site / "numpy" / "_core").glob("_multiarray_umath*.pyd"))
    default_targets += sorted((site / "numpy").rglob("*.dll"))[:8]

    chosen = [Path(t) for t in targets] if targets else default_targets

    print(f"Build environment: {sys.prefix}")
    print(f"Python           : {sys.version}")
    print()
    rc = 0
    for target in chosen:
        if not target.is_file():
            continue
        print(f"{target.relative_to(site) if site in target.parents else target}")
        for dep in imported_dlls(target):
            if is_apiset(dep):
                continue
            location = "SYSTEM (Windows)" if is_windows_dll(dep) else "?"
            if location == "?":
                for directory in search_dirs:
                    if (directory / dep).is_file():
                        location = str(directory / dep)
                        break
            if location == "?":
                location = "*** NOT FOUND ***"
                rc = 1
            tag = "  [MSVC RT]" if is_msvc_runtime(dep) else ""
            print(f"    {dep:<34} {location}{tag}")
        print()
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*", help="PE files to audit (env mode)")
    parser.add_argument("--env", action="store_true",
                        help="audit the current build environment")
    parser.add_argument("--dist", metavar="DIR",
                        help="audit a built onedir distribution")
    args = parser.parse_args()

    if args.dist:
        return audit_dist(Path(args.dist).resolve())
    return audit_env(args.targets or None)


if __name__ == "__main__":
    raise SystemExit(main())
