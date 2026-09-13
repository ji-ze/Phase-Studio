"""Create the exact, hash-manifested Jana wrapper payload for ONEFILE."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def package_payload(source: Path, output: Path) -> tuple[Path, Path]:
    source = source.resolve()
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / "jana-wrapper.zip"
    manifest_path = output / "jana-wrapper-manifest.json"
    files = []
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            relative = path.relative_to(source).as_posix()
            data = path.read_bytes()
            files.append({"path": relative, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            archive.writestr(relative, data)
    manifest_path.write_text(json.dumps({"format": 1, "files": files}, indent=2) + "\n", encoding="utf-8")
    return archive_path, manifest_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    package_payload(args.source, args.output)
