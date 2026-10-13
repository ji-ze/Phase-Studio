"""Create and verify the public Jana developer ZIP and primary checksums."""
from pathlib import Path
import argparse
import hashlib
import shutil
import tempfile
import zipfile


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def package_release(developer: Path, release: Path):
    developer, release = developer.resolve(), release.resolve()
    if developer.name != "PhaseStudio-Jana2020-2.0.2":
        raise ValueError("Wrong developer package root")
    if not (developer / "Phase_studio.exe").is_file() or not (developer / "_internal").is_dir():
        raise ValueError("Complete ONEDIR runtime required")
    release.mkdir(parents=True, exist_ok=True)
    archive_path = release / "PhaseStudio-Jana2020-2.0.2.zip"
    paths = sorted(path for path in developer.rglob("*") if path.is_file())
    expected = {f"{developer.name}/{p.relative_to(developer).as_posix()}": p for p in paths}
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for relative, path in expected.items():
            archive.write(path, relative)
    with zipfile.ZipFile(archive_path) as archive, tempfile.TemporaryDirectory(dir=release) as temp:
        root = Path(temp).resolve()
        if set(archive.namelist()) != set(expected) or archive.testzip() is not None:
            raise ValueError("ZIP membership or CRC failure")
        for name in archive.namelist():
            if root not in (root / name).resolve().parents:
                raise ValueError("Unsafe archive member")
        archive.extractall(root)
        for relative, path in expected.items():
            if digest(root / relative) != digest(path):
                raise ValueError(f"Extracted runtime differs: {relative}")
    repo = Path(__file__).resolve().parents[2]
    shutil.copyfile(repo / "RELEASE_NOTES_2_0_2.md", release / "RELEASE_NOTES_2_0_2.md")
    artifacts = [release / "PhaseStudio-2.0.2-x64.exe", archive_path]
    available = [path for path in artifacts if path.is_file()]
    (release / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in available), encoding="ascii",
    )
    print(f"PASS developer ZIP: extracted and verified {len(expected)} files")
    return archive_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--developer", required=True, type=Path)
    parser.add_argument("--release", required=True, type=Path)
    args = parser.parse_args()
    package_release(args.developer, args.release)
