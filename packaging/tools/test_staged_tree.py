"""Test the exact Git index in an isolated Git-aware source checkout.

The new repository borrows existing objects read-only. It copies index entries
and historical refs, never commits, checks out, or changes the original tree.
Acceptance output must be a fresh directory under the source repository build/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_TESTS=(
    'tests/test_update_signing.py','tests/test_update_release_workflow.py',
    'tests/test_update_runtime.py','tests/test_update_manifest.py',
    'tests/test_update_windows.py','tests/test_update_transaction.py',
    'tests/test_update_plan.py','tests/test_update_install_ui.py',
    'tests/test_packaging_optimization.py','tests/test_split_distribution.py',
)


def git(root,*arguments,input=None):
    return subprocess.check_output(['git',*arguments],cwd=root,input=input)


def export_index(destination,*,repository=ROOT):
    repository=Path(repository).resolve();destination=Path(destination).resolve()
    if not destination.is_relative_to(repository/'build') or destination.exists():
        raise ValueError('Use a fresh staged-source destination under repository build/.')
    entries=git(repository,'ls-files','--stage','-z')
    if any(record.split(b'\t',1)[0].split()[-1]!=b'0'
           for record in entries.split(b'\0') if record):
        raise ValueError('Resolve unmerged index entries before testing.')
    objects=Path(os.fsdecode(git(repository,'rev-parse','--path-format=absolute',
        '--git-path','objects').strip())).resolve()
    references=git(repository,'for-each-ref','--format=%(refname) %(objectname)')
    destination.mkdir(parents=True)
    git(destination,'init','--quiet')
    git(destination,'config','core.autocrlf','false')
    # Git treats a CR as part of an alternate path: write LF bytes on Windows.
    (destination/'.git/objects/info/alternates').write_bytes((objects.as_posix()+'\n').encode('utf8'))
    git(destination,'update-index','-z','--index-info',input=entries)
    tree=git(destination,'write-tree').decode().strip()
    for line in references.splitlines():
        ref,sha=line.split()
        git(destination,'update-ref',os.fsdecode(ref),sha.decode())
    git(destination,'checkout-index','--all')
    if git(repository,'ls-files','--stage','-z')!=entries:
        raise ValueError('Source index changed during export; repeat with a stable index.')
    # This is a new repository with its own index. The original checkout remains
    # untouched, and scientific git-show comparisons use the real historic refs.
    assert git(destination,'write-tree').decode().strip()==tree
    record={'staged_tree':tree,'source_head':git(repository,'rev-parse','HEAD').decode().strip(),
        'index_entries_sha256':hashlib.sha256(entries).hexdigest(),
        'historical_refs':len(references.splitlines()),'source':str(repository),
        'checkout':str(destination),'committed':False}
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--export-only',action='store_true')
    parser.add_argument('tests',nargs='*')
    args=parser.parse_args()
    output=args.output.resolve()
    record=export_index(output)
    evidence=output.parent/(output.name+'-verification.json')
    if not args.export_only:
        temporary=output.parent/(output.name+'-tmp');temporary.mkdir()
        command=[sys.executable,'-m','pytest',*(args.tests or DEFAULT_TESTS),'-q',
            '-p','no:cacheprovider','--basetemp='+str(temporary/'pytest')]
        environment=os.environ|{'TEMP':str(temporary),'TMP':str(temporary),
            'QT_QPA_PLATFORM':'offscreen','PHASE_STUDIO_STARTUP_PROBE':'1'}
        log=output.parent/(output.name+'-pytest.log')
        with log.open('w',encoding='utf8') as stream:
            result=subprocess.run(command,cwd=output,env=environment,stdout=stream,stderr=subprocess.STDOUT)
        record.update(command=command,returncode=result.returncode,log=str(log))
    evidence.write_text(json.dumps(record,indent=2),encoding='utf8')
    print(json.dumps(record,indent=2))
    return record.get('returncode',0)


if __name__=='__main__':raise SystemExit(main())
