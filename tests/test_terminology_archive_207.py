import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def test_historical_evidence_is_byte_exact_and_deterministic(tmp_path):
    spec=importlib.util.spec_from_file_location('archive_terminology',ROOT/'packaging/tools/archive_terminology_evidence.py')
    tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
    first,second=tmp_path/'first.zip',tmp_path/'second.zip'
    manifest=tool.export(first);tool.export(second)
    assert first.read_bytes()==second.read_bytes()
    assert hashlib.sha256(first.read_bytes()).hexdigest()==manifest['archive_sha256']
    with zipfile.ZipFile(first) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist())=={r['path'] for r in manifest['files']}
        for row in manifest['files']:
            data=archive.read(row['path'])
            assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
    assert len(manifest['files'])==8
