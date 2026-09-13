"""PE version resources derived exclusively from the runtime version source."""
import runpy
from pathlib import Path
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
    VarFileInfo, VarStruct,
)


def version_resource(product, project_dir):
    version = runpy.run_path(str(Path(project_dir) / "phase_studio/version.py"))["VERSION"]
    parts = tuple(int(part) for part in version.split(".")) + (0,)
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=parts, prodvers=parts, mask=0x3f, flags=0,
                          OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
        kids=[StringFileInfo([StringTable("040904b0", [
            StringStruct("FileDescription", product), StringStruct("ProductName", "Phase Studio"),
            StringStruct("FileVersion", version), StringStruct("ProductVersion", version),
        ])]), VarFileInfo([VarStruct("Translation", [1033, 1200])])],
    )
