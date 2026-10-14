"""Collect license resources and exclude unused optional Qt features."""
from pathlib import Path
from importlib import metadata
import sys
import runpy

EXCLUDED_QT_BINARIES = {
    "qt6virtualkeyboard.dll", "qtvirtualkeyboardplugin.dll", "qt6pdf.dll", "qpdf.dll",
}


def exclude_unused_qt_plugins(binaries):
    return [item for item in binaries
            if Path(item[0]).name.lower() not in EXCLUDED_QT_BINARIES]


def legal_datas(project_dir):
    resources = []
    version = runpy.run_path(str(project_dir / "phase_studio/version.py"))["VERSION"]
    current_notes = project_dir / f"RELEASE_NOTES_{version.replace('.', '_')}.md"
    if current_notes.is_file() and current_notes.name != "RELEASE_NOTES_2_0_2.md":
        resources.append((str(current_notes), "PhaseStudioLegal"))
    for name in ("LICENSE", "CITATION.cff", "AUTHORS.md", "THIRD_PARTY_NOTICES.md",
                 "RELEASE_NOTES_2_0_2.md", "docs/JANA_DEVELOPER_INTEGRATION.md"):
        path = project_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"Required release notice missing: {name}")
        resources.append((str(path), "PhaseStudioLegal"))
    for package in ("numpy", "matplotlib", "gemmi", "PySide6", "PySide6-Essentials",
                    "PySide6-Addons", "shiboken6", "qtvscodestyle", "truststore",
                    "PyInstaller", "packaging", "pillow", "fonttools", "kiwisolver",
                    "contourpy", "cycler", "python-dateutil", "six", "pyparsing"):
        distribution = metadata.distribution(package)
        for file in distribution.files or ():
            relative = Path(str(file))
            if ("license" in relative.name.lower() or relative.name.lower().startswith("copying")):
                path = Path(distribution.locate_file(file))
                if path.is_file():
                    resources.append((str(path), f"PhaseStudioLegal/dependencies/{package}/{relative.parent.as_posix()}"))
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise FileNotFoundError("Python runtime license not found")
    resources.append((str(python_license), "PhaseStudioLegal/dependencies/Python"))
    for path in sorted((project_dir / "third_party_licenses").rglob("*")):
        if path.is_file():
            resources.append((str(path), "PhaseStudioLegal/upstream/" + path.relative_to(project_dir / "third_party_licenses").parent.as_posix()))
    return resources
