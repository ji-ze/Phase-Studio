"""Check release boundaries, embedded version, and Jana payload integrity."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import runpy
import zipfile

from PyInstaller.archive.readers import CArchiveReader


NAMES = {
    "standalone": "PhaseStudio-1.0.10-x64.exe",
    "installer": "PhaseStudio-Jana2020-Installer-1.0.10-x64.exe",
    "wrapper": "superflip.exe",
    "store": "PhaseStudio.exe",
}


def _exe_from_path(path: Path, profile: str) -> Path:
    path = Path(path)
    return path if path.is_file() else path / NAMES[profile]


def _archive_names(reader: CArchiveReader) -> set[str]:
    return {str(name).replace("\\", "/") for name in reader.toc}


def check_distribution(path, profile, wrapper_source=None):
    exe = _exe_from_path(Path(path), profile)
    assert exe.is_file(), f"Executable missing: {exe}"
    reader = CArchiveReader(str(exe))
    pyz = reader.open_embedded_archive("PYZ.pyz")
    modules = set(pyz.toc)
    names = _archive_names(reader)
    raw_names = {str(name).replace("\\", "/"): str(name) for name in reader.toc}
    version = runpy.run_path(str(Path(__file__).resolve().parents[2] / "phase_studio/version.py"))["VERSION"]
    assert version in pyz.extract("phase_studio.version").co_consts, "Wrong embedded version"

    if profile == "installer":
        assert "phase_studio.app" not in modules, "Installer imports scientific main GUI"
        assert "phase_studio.jana_superflip" not in modules, "Installer imports wrapper workflow"
        assert "phase_studio.jana_installer" in modules
        payload_names = {name for name in names if name.startswith("JanaIntegrationPayload/")}
        archive_name = "JanaIntegrationPayload/jana-wrapper.zip"
        manifest_name = "JanaIntegrationPayload/jana-wrapper-manifest.json"
        assert {archive_name, manifest_name} <= payload_names, "Embedded wrapper package missing"
        assert not any(name.endswith("/PhaseStudio.exe") for name in names), "Standalone bundled with installer"
        if wrapper_source:
            source = Path(wrapper_source)
            source_files = {str(item.relative_to(source)).replace("\\", "/"): item
                            for item in source.rglob("*") if item.is_file()}
            manifest = json.loads(reader.extract(raw_names[manifest_name]).decode("utf-8"))
            manifest_files = {item["path"]: item for item in manifest["files"]}
            assert set(manifest_files) == set(source_files), "Embedded payload file set differs from authoritative wrapper"
            with zipfile.ZipFile(io.BytesIO(reader.extract(raw_names[archive_name]))) as archive:
                archived_files = {name for name in archive.namelist() if not name.endswith("/")}
                assert archived_files == set(source_files), "Wrapper ZIP omits authoritative files"
                for relative, source_path in source_files.items():
                    embedded = archive.read(relative)
                    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
                    assert hashlib.sha256(embedded).hexdigest() == source_hash == manifest_files[relative]["sha256"], \
                        f"Embedded payload differs: {relative}"
    else:
        assert "phase_studio.jana_installer" not in modules, "Installation UI in scientific product"
        assert not any(name.startswith("JanaIntegration") for name in names), "Installation payload in scientific product"
        assert "phase_studio.app" in modules

    form = "ONEDIR" if profile in {"wrapper", "store"} else "ONEFILE"
    if form == "ONEDIR":
        assert (exe.parent / "_internal").is_dir(), "ONEDIR runtime missing"
    print(f"PASS {profile}: {version}, {form}, distribution boundary verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--profile", choices=tuple(NAMES), required=True)
    parser.add_argument("--wrapper-source", type=Path)
    args = parser.parse_args()
    check_distribution(args.path, args.profile, args.wrapper_source)
