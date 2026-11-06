"""Real Windows checks. 'passed' covers available checks; inspect completeness."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
FIXTURE_VALUE='Controlled acceptance credential - not a real service key'


def credential_child(origin):
    from phase_studio.credentials import WindowsCredentialBackend
    print(json.dumps(dict(persisted=WindowsCredentialBackend().read(origin)==FIXTURE_VALUE)))


def credential_check():
    from phase_studio.credentials import WindowsCredentialBackend
    backend=WindowsCredentialBackend();origin='https://phase-studio-acceptance-'+uuid.uuid4().hex+'.invalid:443'
    if backend.read(origin):raise ValueError('Disposable credential target already exists.')
    try:
        backend.write(origin,FIXTURE_VALUE)
        process=subprocess.run([sys.executable,__file__,'--credential-check',origin],cwd=ROOT,
            capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        if process.returncode or not json.loads(process.stdout)['persisted']:raise ValueError('WinCred persistence across processes failed.')
    finally:backend.delete(origin)
    if backend.read(origin):raise ValueError('Disposable credential cleanup failed.')
    return dict(passed=True,real_wincred=True,cross_process=True,fixture_only=True,cleaned=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standalone',type=Path,required=True);parser.add_argument('--jana-zip',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--credentials',action='store_true')
    args=parser.parse_args()
    if os.name!='nt':raise ValueError('Actual Windows is required.')
    output=args.output.resolve()
    if not output.is_relative_to(ROOT/'build') or output.exists():raise ValueError('Use a new isolated output under build.')
    output.mkdir(parents=True)
    from phase_studio.update_manifest import UpdateAsset
    from phase_studio.update_package import extract_jana_package
    from phase_studio.version import VERSION
    report=dict(passed=False,is_administrator=bool(ctypes.windll.shell32.IsUserAnAdmin()),
                physical_monitor_acceptance=False,clean_vm_acceptance=False,cases=[])
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Control\FileSystem') as key:
        report['windows_long_paths_enabled']=bool(winreg.QueryValueEx(key,'LongPathsEnabled')[0])
    report['unprefixed_over_260_acceptance']=False
    def save():
        (output/'environment-acceptance.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    if args.credentials:report['credentials']=credential_check()
    save()
    standalone=args.standalone.resolve();archive=args.jana_zip.resolve()
    expected_standalone=hashlib.sha256(standalone.read_bytes()).hexdigest()
    expected_zip=hashlib.sha256(archive.read_bytes()).hexdigest()
    asset=UpdateAsset('jana2020-onedir',archive.name,archive.stat().st_size,expected_zip)
    for name in ('unicode','long-unicode'):
        if name=='long-unicode' and not report['windows_long_paths_enabled']:
            report['cases'].append(dict(case=name,verdict='UNVERIFIED',passed=None,
                reason='Host LongPathsEnabled is disabled. Normal >260-character executable paths cannot be accepted on this host.'))
            save()
            continue
        base=output/(name+' žluťoučký 密度')
        if name=='long-unicode':
            while len(str(base/'Phase_studio.exe'))<=310:base=base/('segment '+('x'*45))
            # Test the explicit Windows extended-length representation without
            # changing the host's system-wide LongPathsEnabled policy.
            base=Path('\\\\?\\'+str(base))
        base.mkdir(parents=True)
        standalone_copy=base/standalone.name;shutil.copy2(standalone,standalone_copy)
        jana=extract_jana_package(archive,base/'jana',asset,VERSION)
        for profile,exe in (('standalone',standalone_copy),('jana',jana/'Phase_studio.exe')):
            destination=base/(profile+'-output')
            env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PHASE_STUDIO_STARTUP_PROBE='1',PHASE_STUDIO_INPUT_UI_ACCEPTANCE='1',QT_SCALE_FACTOR='1')
            try:
                process=subprocess.run([str(exe),'--packaging-acceptance',str(destination)],executable=str(exe),cwd=output if name=='long-unicode' else base,
                    capture_output=True,text=True,timeout=180,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
            except (OSError,subprocess.TimeoutExpired) as error:
                report['failure']=dict(case=name,profile=profile,error_type=type(error).__name__,error=str(error));save()
                raise
            (base/(profile+'-process.txt')).write_text(process.stdout+'\n'+process.stderr,encoding='utf8')
            data=json.loads((destination/'report.json').read_text(encoding='utf8'))
            if process.returncode or not data.get('passed') or not data.get('frozen'):
                report['failure']=dict(case=name,profile=profile,exit_code=process.returncode,report=data);save()
                raise ValueError('Frozen path acceptance failed: '+name+'/'+profile)
            length=len(str(exe))
            if name=='long-unicode' and length<=260:raise ValueError('Long-path fixture did not exceed MAX_PATH.')
            report['cases'].append(dict(case=name,profile=profile,exe_path_characters=length,
                unicode=True,over_260=length>260,extended_length_prefix=name=='long-unicode',passed=True,verdict='PASS',report=str(destination/'report.json')))
            save()
    if hashlib.sha256(standalone.read_bytes()).hexdigest()!=expected_standalone or hashlib.sha256(archive.read_bytes()).hexdigest()!=expected_zip:
        raise ValueError('Original distribution changed during path acceptance.')
    report['original_packages_unchanged']=True;report['passed']=True
    report['complete_path_acceptance']=all(case['verdict']=='PASS' for case in report['cases'])
    save()
    print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--credential-check':credential_child(sys.argv[2])
    else:main()
