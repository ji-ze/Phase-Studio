"""Restore historical audit bytes from immutable Git blobs, without rerunning science."""
import argparse
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/'docs/reviews/2.0.7-ui-terminology/ARCHIVED_EVIDENCE.json'


def export(output):
    manifest=json.loads(MANIFEST.read_text(encoding='utf8'))
    commit=manifest['artifact_snapshot_commit']
    if manifest['schema']!=1 or manifest['archive_format']!='zip-stored-v1' or not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Invalid evidence manifest.')
    paths=set()
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_STORED) as archive:
        for record in sorted(manifest['files'],key=lambda row:row['path']):
            name=record['path'];path=PurePosixPath(name)
            if name in paths or path.is_absolute() or '..' in path.parts or path.parent!=PurePosixPath('docs/reviews/2.0.7-ui-terminology') or '\\' in name:
                raise ValueError('Invalid evidence member path.')
            paths.add(name)
            blob=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
            if hashlib.sha256(blob).hexdigest()!=record['git_blob_sha256']:raise ValueError('Historical Git blob differs.')
            if record['restore_line_endings']=='crlf':data=blob.replace(b'\n',b'\r\n')
            elif record['restore_line_endings']=='lf':data=blob
            else:raise ValueError('Unsupported byte restoration.')
            if len(data)!=record['bytes'] or hashlib.sha256(data).hexdigest()!=record['sha256']:raise ValueError('Original audit bytes differ.')
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.create_system=3;info.external_attr=0o100644<<16;info.compress_type=zipfile.ZIP_STORED
            archive.writestr(info,data)
    if hashlib.sha256(output.read_bytes()).hexdigest()!=manifest['archive_sha256']:raise ValueError('Deterministic archive digest differs.')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    arguments=parser.parse_args();result=export(arguments.output)
    print('PASS: historical evidence restored byte-for-byte; SHA-256 '+result['archive_sha256'])
