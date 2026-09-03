# -*- mode: python ; coding: utf-8 -*-
# PyInstaller ONEDIR build of the main Phase Studio application, used for the
# Microsoft Store / MSIX staging build (packaging/build_store_msix.ps1).
#
# Output:
#
#     PhaseStudio/
#         PhaseStudio.exe
#         _internal/...
#
# ONEDIR (not ONEFILE) is used here deliberately: MSIX already provides
# application packaging/versioning, files can be staged into the MSIX layout
# deterministically, and startup never pays the ONEFILE self-extraction cost
# (see packaging/README_STORE.md, "Why ONEDIR"). This does not change the
# Python application itself -- it is the same phase_studio/app.py entry point
# the repository's own top-level PhaseStudio.spec (ONEFILE, for quick
# developer/testing distribution) builds; keep both in sync if PyInstaller
# requirements change.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


# SPECPATH (supplied by PyInstaller) is the directory CONTAINING this spec
# file: <RepoRoot>\packaging\pyinstaller. Two .parent steps reach the repo
# root (pyinstaller -> packaging -> RepoRoot) -- a THIRD .parent was the
# actual bug behind "script ...\phase_studio\app.py not found" during the
# first real Windows build (it resolved one directory above the repo root).
# Verified with an assertion below rather than trusting the arithmetic alone.
project_dir = Path(SPECPATH).resolve().parent.parent

entry_point = project_dir / "phase_studio" / "app.py"
if not entry_point.is_file():
    raise FileNotFoundError(
        f"Phase Studio entry point not found: {entry_point}\n"
        f"Resolved project root: {project_dir}\n"
        f"SPECPATH was: {Path(SPECPATH).resolve()}"
    )

hiddenimports = [
    "phase_studio",
    "phase_studio.app",
    "phase_studio.jana_superflip",
    "phase_studio.jana_integration",
    "phase_studio.sharped_server_client",
    "phase_studio.ui_style",
    "matplotlib.backends.backend_qtagg",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
]

try:
    hiddenimports += collect_submodules("qtvscodestyle")
except Exception:
    pass

datas = []
datas += [(str(project_dir / "phase_studio" / "assets"), "phase_studio/assets")]
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
    runtime_hooks=[],
    excludes=[
        "PyQt5",
        "PyQt6",
        "PySide2",
        "tkinter",
        "matplotlib.backends.backend_tkagg",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PhaseStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(project_dir / "phase_studio" / "assets" / "phase_studio.ico")],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PhaseStudio",
)
