"""Production-only Authenticode verification, independent of Ed25519 metadata.

No signing keys are read, no signing service is invoked. Unsigned local test
builds are intentionally rejected by this production gate.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_record(record, *, expected_sha256, subject, thumbprints, version):
    fingerprints={v.replace(' ','').upper() for v in thumbprints}
    if not subject or not fingerprints or any(not re.fullmatch('[0-9A-F]{40}',v) for v in fingerprints):
        raise ValueError('Approved certificate subject and SHA-1 certificate thumbprints are required; no default identity is trusted.')
    if record.get('sha256')!=expected_sha256:raise ValueError('Executable changed during Authenticode verification.')
    if record.get('status')!='Valid' or record.get('signature_type')!='Authenticode':
        raise ValueError('A valid embedded Authenticode signature is required.')
    if record.get('signer_subject')!=subject or str(record.get('signer_thumbprint','')).upper() not in fingerprints:
        raise ValueError('Authenticode publisher identity does not match the approved policy.')
    if not all(record.get(key) is True for key in ('signer_chain_valid','timestamp_present','timestamp_chain_valid','timestamp_eku_valid')):
        raise ValueError('Trusted publisher and timestamp certificate chains and timestamp EKU are required.')
    if record.get('product_version')!=version:raise ValueError('Signed executable product version differs.')
    return record


def verify_file(path, *, subject, thumbprints, version):
    if os.name!='nt':raise ValueError('Authenticode production verification requires Windows WinVerifyTrust.')
    path=Path(path).resolve()
    if not path.is_file() or path.is_symlink():raise ValueError('Expected a regular owned executable.')
    expected=sha(path)
    result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
        str(Path(__file__).with_name('authenticode_probe.ps1')),'-File',str(path)],
        capture_output=True,text=True,timeout=120,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise ValueError('Windows Authenticode trust-chain probe failed.')
    record=json.loads(result.stdout.lstrip('\ufeff'))
    validate_record(record,expected_sha256=expected,subject=subject,thumbprints=thumbprints,version=version)
    if sha(path)!=expected:raise ValueError('Executable changed after signature verification.')
    return record


def verify_packages(directory, version, subject, thumbprints, workspace):
    from PyInstaller.archive.readers import CArchiveReader
    from phase_studio.update_manifest import UpdateAsset
    from phase_studio.update_package import extract_jana_package
    from phase_studio.update_transaction import verify_inventory
    directory=Path(directory);workspace=Path(workspace)
    standalone=directory/f'PhaseStudio-{version}-x64.exe'
    archive=directory/f'PhaseStudio-Jana2020-{version}.zip'
    policy=dict(subject=subject,thumbprints=thumbprints,version=version)
    reports={'standalone':verify_file(standalone,**policy)}
    image=CArchiveReader(str(standalone))
    names={name.replace('\\','/'):name for name in image.toc}
    helper_name='phase_studio/updater/PhaseStudioUpdater.exe'
    marker_name='phase_studio/distribution.json'
    if helper_name not in names or marker_name not in names:raise ValueError('Standalone embedded updater contract is missing.')
    helper=image.extract(names[helper_name])
    marker=json.loads(image.extract(names[marker_name]))
    if marker.get('helper_sha256')!=hashlib.sha256(helper).hexdigest():raise ValueError('Signed embedded updater differs from the compiled application contract.')
    extracted_helper=workspace/'PhaseStudioUpdater.exe';extracted_helper.write_bytes(helper)
    reports['standalone_updater']=verify_file(extracted_helper,**policy)
    asset=UpdateAsset('jana2020-onedir',archive.name,archive.stat().st_size,sha(archive))
    jana=extract_jana_package(archive,workspace/'jana',asset,version)
    verify_inventory(jana/'_internal')
    reports['jana']=verify_file(jana/'Phase_studio.exe',**policy)
    jana_helper=jana/'_internal/phase_studio/updater/PhaseStudioUpdater.exe'
    reports['jana_updater']=verify_file(jana_helper,**policy)
    jana_marker=json.loads((jana/'_internal/phase_studio/distribution.json').read_text(encoding='utf8'))
    if jana_marker.get('helper_sha256')!=sha(jana_helper) or sha(jana_helper)!=sha(extracted_helper):
        raise ValueError('The two profiles must contain the identical signed updater and correct embedded hashes.')
    environment=os.environ|{'QT_QPA_PLATFORM':'offscreen','PHASE_STUDIO_STARTUP_PROBE':'1'}
    for name,executable,flag in (('helper',extracted_helper,'--self-check'),
                                 ('standalone',standalone,'--update-runtime-check'),
                                 ('jana',jana/'Phase_studio.exe','--update-runtime-check')):
        output=workspace/(name+'-runtime.json')
        command=[str(executable),flag,str(output)]
        process=subprocess.run(command,cwd=workspace,env=environment,capture_output=True,text=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
        runtime=json.loads(output.read_text(encoding='utf8'))
        if process.returncode or (name=='helper' and runtime!=dict(protocol=1,public_install_enabled=True,frozen=True)) or (name!='helper' and (not runtime.get('ok') or runtime.get('version')!=version or runtime.get('helper_sha256')!=sha(extracted_helper))):
            raise ValueError('Signed runtime/helper startup contract failed: '+name)
        reports[name+'_runtime']=runtime
    spec=importlib.util.spec_from_file_location('signed_frozen_gui',Path(__file__).with_name('accept_frozen_gui.py'))
    gui=importlib.util.module_from_spec(spec);spec.loader.exec_module(gui)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        checks=[pool.submit(gui.verify_profile,exe,workspace/('signed-gui-'+name))
                for name,exe in (('standalone',standalone),('jana',jana/'Phase_studio.exe'))]
        reports['final_frozen_gui']=[job.result() for job in checks]
    return reports


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--directory',type=Path);group.add_argument('--file',type=Path)
    parser.add_argument('--version',required=True);parser.add_argument('--subject',required=True)
    parser.add_argument('--thumbprints',required=True);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();thumbprints=args.thumbprints.split(';')
    try:
        if args.file:records={'file':verify_file(args.file,subject=args.subject,thumbprints=thumbprints,version=args.version)}
        else:
            with tempfile.TemporaryDirectory() as work:
                records=verify_packages(args.directory,args.version,args.subject,thumbprints,Path(work))
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(dict(passed=True,records=records),indent=2),encoding='utf8')
        return 0
    except Exception as error:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(dict(passed=False,error=str(error)),indent=2),encoding='utf8')
        print('Production Authenticode verification failed.',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
