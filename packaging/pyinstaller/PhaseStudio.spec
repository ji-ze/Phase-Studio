# Shared Windows spec. Direct downloads are ONEFILE; the Store profile remains
# ONEDIR because MSIX owns the outer installation layout.
import sys
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


# SPECPATH (supplied by PyInstaller) is the directory CONTAINING this spec
# file: <RepoRoot>\packaging\pyinstaller. Two .parent steps reach the repo
# root (pyinstaller -> packaging -> RepoRoot) -- a THIRD .parent was the
# actual bug behind "script ...\phase_studio\app.py not found" during the
# first real Windows build (it resolved one directory above the repo root).
# Verified with an assertion below rather than trusting the arithmetic alone.
project_dir = Path(SPECPATH).resolve().parent.parent

installer_build = globals().get("installer_build", False)
store_build = globals().get("store_build", False)
if installer_build and store_build:
    raise ValueError("Installer and Store build profiles are mutually exclusive.")
if installer_build:
    target_name = "PhaseStudio-Jana2020-Installer-1.0.9-x64"
elif store_build:
    target_name = "PhaseStudio"
else:
    target_name = "PhaseStudio-1.0.9-x64"
entry_point = project_dir / "phase_studio" / ("jana_installer.py" if installer_build else "standalone.py")
if not entry_point.is_file():
    raise FileNotFoundError(
        f"Phase Studio entry point not found: {entry_point}\n"
        f"Resolved project root: {project_dir}\n"
        f"SPECPATH was: {Path(SPECPATH).resolve()}"
    )

# Shared portable-runtime staging (see packaging/pyinstaller/portable_runtime.py).
# It lives beside this spec and is not importable as an installed package.
spec_dir = Path(SPECPATH).resolve()
sys.path.insert(0, str(spec_dir))
import portable_runtime  # noqa: E402
from windows_version import version_resource

# Fail before doing any work if the build environment cannot produce a
# consistent Qt runtime (Conda PySide6 with Qt outside the Python package,
# mismatched PySide6/shiboken6, missing Qt platform plugin).
qt_report = portable_runtime.validate_pyside6_installation()

hiddenimports = [
    "phase_studio",
    "phase_studio.app",
    "phase_studio.jana_superflip",
    "phase_studio.sharped_server_client",
    "phase_studio.ui_style",
    "matplotlib.backends.backend_qtagg",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
]

if installer_build:
    hiddenimports = ["phase_studio.jana_installer", "phase_studio.jana_integration",
                     "phase_studio.ui_branding", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]

try:
    hiddenimports += collect_submodules("qtvscodestyle")
except Exception:
    pass

datas = []
datas += [(str(project_dir / "phase_studio" / "assets"), "phase_studio/assets")]
if installer_build:
    wrapper_payload = Path(os.environ.get("PHASE_STUDIO_WRAPPER_PAYLOAD", project_dir / "dist" / "superflip"))
    if not (wrapper_payload / "superflip.exe").is_file() or not (wrapper_payload / "_internal").is_dir():
        raise FileNotFoundError(
            "The Jana installer requires the complete authoritative dist/superflip payload. "
            "Build superflip.spec first."
        )
    payload_bundle = project_dir / "build" / "jana-payload"
    payload_archive = payload_bundle / "jana-wrapper.zip"
    payload_manifest = payload_bundle / "jana-wrapper-manifest.json"
    if not payload_archive.is_file() or not payload_manifest.is_file():
        raise FileNotFoundError("Run package_jana_payload.py before building the installer.")
    datas += [
        (str(payload_archive), "JanaIntegrationPayload"),
        (str(payload_manifest), "JanaIntegrationPayload"),
    ]
try:
    datas += collect_data_files("qtvscodestyle")
except Exception:
    pass


a = Analysis(
    [str(entry_point)],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={
        "matplotlib": {
            "backends": "QtAgg",
        },
    },
    # Resolve native DLLs from this distribution only -- not from PATH and not
    # from the executable's own directory. Prevents a foreign Qt6*.dll, ICU or
    # VC runtime belonging to another installed program from being loaded.
    runtime_hooks=[
        str(spec_dir / "runtime_hooks" / "pyi_rth_dll_isolation.py"),
    ],
    excludes=(["phase_studio.app", "phase_studio.jana_superflip", "numpy", "matplotlib", "gemmi"]
              if installer_build else ["phase_studio.jana_installer"]) + [
        "PyQt5",
        "PyQt6",
        "PySide2",
        "tkinter",
        "matplotlib.backends.backend_tkagg",
    ],
    noarchive=False,
    optimize=0,
)

# ---------------------------------------------------------------------------
# Portable native runtime -- makes this distribution start on a clean Windows
# 10/11 x64 machine with no Visual C++ Redistributable installed.
# ---------------------------------------------------------------------------
# 1. Drop any app-local Universal CRT collected from the Python distribution:
#    the UCRT is a component of Windows 10/11, and a private older copy is a
#    portability hazard rather than a fix.
a.binaries, removed_ucrt = portable_runtime.strip_app_local_ucrt(a.binaries)

# 2. Bundle exactly one copy of each required VC++ runtime DLL at the
#    _internal root, discovered from the collected binaries' import tables and
#    taken from explicit in-environment sources (never System32, never PATH).
a.binaries, staged_runtime = portable_runtime.stage_msvc_runtime(a.binaries)

portable_runtime.report(target_name, staged_runtime, qt_report, removed_ucrt)
portable_runtime.write_portable_manifest(
    project_dir / "build" / f"portable-runtime-{target_name}.json",
    app=target_name,
    staged_runtime=staged_runtime,
    qt_report=qt_report,
    removed_ucrt=removed_ucrt,
)

pyz = PYZ(a.pure)

if store_build:
    exe = EXE(
        pyz, a.scripts, [], exclude_binaries=True, name=target_name,
        version=version_resource(target_name, project_dir), debug=False,
        bootloader_ignore_signals=False, strip=False, upx=False, console=False,
        disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
        codesign_identity=None, entitlements_file=None,
        icon=[str(project_dir / "phase_studio" / "assets" / "phase_studio.ico")],
    )
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
                   upx_exclude=[], name=target_name)
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [], exclude_binaries=False,
        name=target_name, version=version_resource(target_name, project_dir),
        debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
        console=False, disable_windowed_traceback=False, argv_emulation=False,
        target_arch=None, codesign_identity=None, entitlements_file=None,
        icon=[str(project_dir / "phase_studio" / "assets" / "phase_studio.ico")],
    )
