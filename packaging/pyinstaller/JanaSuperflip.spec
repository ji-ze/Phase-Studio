# -*- mode: python ; coding: utf-8 -*-
# PyInstaller ONEDIR build for the Jana2020 integration payload.
#
# Output (relative to this spec file's own --distpath, see
# packaging/build_windows.ps1 / build_store_msix.ps1):
#
#     JanaIntegration/
#         superflip.exe
#         _internal/...
#
# This is the exact deployment unit phase_studio.jana_integration copies into
# an existing Jana2020\SUPERFLIP directory. It is a frozen build of
# phase_studio/jana_superflip.py -- the Jana2020 Wizard/console wrapper --
# never the main PhaseStudio.exe renamed. Console build (Jana2020 launches it
# from its own working directory and may expect console I/O).
#
# This is a copy of the repository's own top-level superflip.spec, adjusted
# only for its nested location (project_dir now resolves two levels up).
# Keep the two in sync if the wrapper's own PyInstaller requirements change;
# the top-level spec remains for ad hoc developer builds (see
# packaging/README_STORE.md).

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_dir = Path(SPECPATH).resolve().parent.parent.parent

hiddenimports = [
    "phase_studio",
    "phase_studio.app",
    "phase_studio.jana_superflip",
    # phase_studio.app's own "Install to Jana2020" dialog imports this
    # lazily (function-scoped, not module-level); every window this wrapper
    # constructs has launched_from_jana_wizard=True, so that code path is
    # never actually reached from here, but PyInstaller's static analysis
    # still needs it declared to bundle it safely regardless.
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
    [str(project_dir / "phase_studio" / "jana_superflip.py")],
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
    name="superflip",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
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
    name="JanaIntegration",
)
