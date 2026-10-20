"""Independent ONEFILE helper: no Qt or scientific executables."""
import runpy,sys
from pathlib import Path
project_dir=Path(SPECPATH).resolve().parent.parent
sys.path.insert(0,str(Path(SPECPATH)))
from release_legal import legal_datas
from windows_version import version_resource
version=runpy.run_path(str(project_dir/'phase_studio/version.py'))['VERSION']
a=Analysis([str(project_dir/'phase_studio/update_helper.py')],pathex=[str(project_dir)],
    binaries=[],datas=legal_datas(project_dir),hiddenimports=['cryptography','pefile'],
    hookspath=[],runtime_hooks=[],excludes=['PySide6','matplotlib','numpy','gemmi'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='PhaseStudioUpdater',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=False,console=True,
    version=version_resource('PhaseStudioUpdater',project_dir))
