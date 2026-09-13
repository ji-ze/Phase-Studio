# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_dir = Path(SPECPATH).resolve()

# Shared portable-runtime staging, identical to the one the main application
# uses (see packaging/pyinstaller/portable_runtime.py). It matters especially
# here: this wrapper is deployed INSIDE the Jana2020 tree, beside Jana's own
# executables, so it must not pick up foreign Qt/ICU/VC runtime binaries from
# its deployment directory or from PATH.
packaging_dir = project_dir / "packaging" / "pyinstaller"
sys.path.insert(0, str(packaging_dir))
import portable_runtime  # noqa: E402

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
    ["phase_studio/jana_superflip.py"],
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
    runtime_hooks=[
        str(packaging_dir / "runtime_hooks" / "pyi_rth_dll_isolation.py"),
    ],
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

# Same portable native runtime treatment as the main application: no app-local
# Universal CRT, and exactly one copy of each required VC++ runtime DLL at the
# _internal root.
a.binaries, removed_ucrt = portable_runtime.strip_app_local_ucrt(a.binaries)
a.binaries, staged_runtime = portable_runtime.stage_msvc_runtime(a.binaries)

portable_runtime.report("superflip", staged_runtime, qt_report, removed_ucrt)
portable_runtime.write_portable_manifest(
    project_dir / "build" / "portable-runtime-superflip.json",
    app="superflip",
    staged_runtime=staged_runtime,
    qt_report=qt_report,
    removed_ucrt=removed_ucrt,
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
    # Windowed, not console: Jana2020 launches this executable directly, and
    # console=True made Windows attach a persistent black console window for
    # this process's entire lifetime, visible behind the Jana2020 Wizard.
    # Nothing depends on that console: every message logged through
    # JanaLogger already writes to log.txt regardless (see jana_superflip.py),
    # and all user interaction/error reporting goes through Qt dialogs, never
    # the console. disable_windowed_traceback stays False, so PyInstaller's
    # own crash dialog still appears for an unhandled exception even without
    # a console.
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
    name="superflip",
)
