"""Check built distribution boundaries, embedded version and wrapper staging."""
import argparse
import hashlib
from pathlib import Path
import runpy
from PyInstaller.archive.readers import CArchiveReader


def check_distribution(directory, profile, wrapper_source=None):
    directory = Path(directory)
    name = {"standalone": "PhaseStudio", "installer": "PhaseStudioJanaInstaller", "wrapper": "superflip"}[profile]
    exe = directory / f"{name}.exe"
    archive = CArchiveReader(str(exe)).open_embedded_archive("PYZ.pyz")
    modules = set(archive.toc)
    version = runpy.run_path(str(Path(__file__).resolve().parents[2] / "phase_studio/version.py"))["VERSION"]
    assert version in archive.extract("phase_studio.version").co_consts, "Wrong embedded version"
    assert (directory / "_internal").is_dir(), "ONEDIR runtime missing"
    if profile == "installer":
        assert "phase_studio.app" not in modules, "Installer imports scientific main GUI"
        assert "phase_studio.jana_superflip" not in modules, "Installer imports wrapper workflow"
        assert "phase_studio.jana_installer" in modules or "jana_installer" in CArchiveReader(str(exe)).toc
        payload = directory / "JanaIntegration"
        assert (payload / "superflip.exe").is_file()
        assert (payload / "_internal").is_dir()
        assert not list(directory.rglob("PhaseStudio.exe")), "Standalone executable bundled with installer"
        if wrapper_source:
            def hashes(root):
                return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in root.rglob("*") if p.is_file()}
            assert hashes(payload) == hashes(Path(wrapper_source)), "Staged wrapper differs from authoritative build"
    else:
        assert "phase_studio.jana_installer" not in modules, "Installation-management UI in scientific product"
        assert not (directory / "JanaIntegration").exists(), "Installation payload in scientific product"
        assert "phase_studio.app" in modules or "app" in CArchiveReader(str(exe)).toc
    print(f"PASS {profile}: {version}, ONEDIR, distribution boundary verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--profile", choices=("standalone", "installer", "wrapper"), required=True)
    parser.add_argument("--wrapper-source", type=Path)
    args = parser.parse_args()
    check_distribution(args.directory, args.profile, args.wrapper_source)
