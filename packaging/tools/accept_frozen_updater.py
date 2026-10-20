"""Opt-in native helper acceptance with frozen fixture applications.

Builds a disposable public-test-key helper and small PE fixtures under build.
The ephemeral private key stays in this controller's memory. This is a helper
protocol/transaction test, not production-key or actual Jana/GUI acceptance.
"""
from pathlib import Path
import argparse,base64,hashlib,importlib.util,json,os,shutil,subprocess,sys,time,zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def wait_for(path,process=None,seconds=60):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if path.exists():return json.loads(path.read_text(encoding='utf8'))
        if process is not None and process.poll() is not None:raise RuntimeError('Controlled process exited before reporting readiness.')
        time.sleep(.05)
    raise TimeoutError('Controlled acceptance timed out.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args();base=args.directory.resolve()
    if os.name!='nt' or not base.is_relative_to(ROOT/'build') or base.exists():
        raise ValueError('Use a new disposable directory under repository build on Windows.')
    base.mkdir(parents=True)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,PublicFormat,NoEncryption
    from phase_studio.update_transaction import digest,write_inventory
    from phase_studio.update_windows import process_identity
    from phase_studio.update_plan import create_workspace,write_plan
    key=Ed25519PrivateKey.generate();public=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    key_id=hashlib.sha256(public).hexdigest()[:16];keys={key_id:public}
    secret=base64.b64encode(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())).decode('ascii')
    source=base/'source';(source/'phase_studio').mkdir(parents=True)
    for path in (ROOT/'phase_studio').glob('*.py'):shutil.copyfile(path,source/'phase_studio'/path.name)
    (source/'phase_studio/update_trust.py').write_text(f'TRUSTED_KEYS={{{key_id!r}:bytes.fromhex({public.hex()!r})}}\n')
    for relative in ('packaging/pyinstaller/PhaseStudioUpdater.spec','packaging/pyinstaller/release_legal.py',
            'packaging/pyinstaller/windows_version.py','LICENSE','CITATION.cff','AUTHORS.md',
            'THIRD_PARTY_NOTICES.md','RELEASE_NOTES_2_0_2.md','docs/JANA_DEVELOPER_INTEGRATION.md'):
        target=source/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,target)
    def build(spec,label):
        with (base/(label+'.log')).open('w',encoding='utf8') as log:
            subprocess.run([sys.executable,'-m','PyInstaller','--clean','--noconfirm','--distpath',str(base/'bin'),
                '--workpath',str(base/'work'/label),str(spec)],cwd=source,stdout=log,stderr=subprocess.STDOUT,check=True)
    build(source/'packaging/pyinstaller/PhaseStudioUpdater.spec','helper')
    helper=base/'bin/PhaseStudioUpdater.exe'
    fixture=source/'fixture.py'
    fixture.write_text('''import json,os,sys,time
from pathlib import Path
VERSION=__FIXTURE_VERSION__
BAD=__FIXTURE_BAD__
if '--update-runtime-check' in sys.argv:
    if BAD:sys.exit(7)
    Path(sys.argv[-1]).write_text(json.dumps({'ok':True,'version':VERSION}));sys.exit(0)
if '--update-health' in sys.argv:
    Path(sys.argv[-1]).write_text(json.dumps({'version':VERSION,'pid':os.getpid()}))
    while not (Path.cwd()/'fixture-stop-new').exists():time.sleep(.05)
else:
    Path(sys.argv[1]).write_text(json.dumps({'pid':os.getpid()}))
    while not Path(sys.argv[2]).exists():time.sleep(.05)
''')
    template=fixture.read_text();images={}
    for name,version,bad in [('old','2.0.6',False),('new','2.0.7',False),('bad','2.0.8',True)]:
        fixture.write_text(template.replace('__FIXTURE_VERSION__',repr(version)).replace('__FIXTURE_BAD__',repr(bad)))
        spec=source/(name+'.spec')
        spec.write_text("import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(SPECPATH)/'packaging/pyinstaller'))\nfrom windows_version import version_resource\n"
            "a=Analysis([str(Path(SPECPATH)/'fixture.py')],pathex=[],binaries=[],datas=[],hiddenimports=[],hookspath=[],runtime_hooks=[],excludes=['PySide6','numpy','matplotlib'],noarchive=False)\n"
            f"exe=EXE(PYZ(a.pure),a.scripts,a.binaries,a.datas,[],name={name!r},console=True,version=version_resource('Phase Studio controlled fixture',Path(SPECPATH)))\n")
        build(spec,name);images[name]=base/'bin'/(name+'.exe')
    spec=importlib.util.spec_from_file_location('_acceptance_signing',ROOT/'packaging/tools/update_signing.py')
    signing=importlib.util.module_from_spec(spec);spec.loader.exec_module(signing)
    os.environ['LOCALAPPDATA']=str(base/'local-user')
    results=[]
    for profile in ('standalone-onefile','jana2020-onedir'):
        for bad in (False,True):
            label=profile+('-rollback' if bad else '-success');case=base/label;case.mkdir()
            install=case/'Jana with spaces'/'SharpED';install.mkdir(parents=True)
            target=install/('Phase_studio.exe' if profile=='jana2020-onedir' else 'Retained shortcut name.exe')
            shutil.copyfile(images['old'],target);old_hash=digest(target)
            if profile=='jana2020-onedir':
                runtime=install/'_internal';runtime.mkdir();(runtime/'old-runtime.txt').write_text('old runtime');write_inventory(runtime)
            sentinels={case/'project.inflip':b'project context',install/'user notes.txt':b'user data',
                install.parent/'SUPERFLIP'/'superflip.exe':b'scientific executable',install.parent/'SUPERFLIP'/'EDMA.exe':b'EDMA executable'}
            for path,value in sentinels.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
            version='2.0.8' if bad else '2.0.7';new_image=images['bad' if bad else 'new']
            release=case/'release';release.mkdir();names=signing.asset_names(version)
            shutil.copyfile(new_image,release/names[0])
            payload=case/'payload';(payload/'_internal').mkdir(parents=True)
            shutil.copyfile(new_image,payload/'Phase_studio.exe');(payload/'_internal/new-runtime.txt').write_text('new runtime');write_inventory(payload/'_internal')
            with zipfile.ZipFile(release/names[1],'w',zipfile.ZIP_DEFLATED) as archive:
                for path in payload.rglob('*'):
                    if path.is_file():archive.write(path,f'PhaseStudio-Jana2020-{version}/'+path.relative_to(payload).as_posix())
            (release/names[5]).write_text('Controlled acceptance only; not a release.')
            signing.sign_release(release,version,keys=keys,secret=secret)
            manifest=signing.validate_release(release,version,keys=keys);asset=manifest.asset(profile)
            workspace=create_workspace();shutil.copyfile(helper,workspace/helper.name);shutil.copyfile(release/asset.name,workspace/asset.name)
            ready=case/'old-ready.json';stop=case/'stop-old'
            parent=subprocess.Popen([str(target),str(ready),str(stop)],cwd=case,creationflags=subprocess.CREATE_NO_WINDOW)
            controlled_helper=None
            try:
                identity=wait_for(ready,parent);parents=[process_identity(identity['pid'])]
                if parent.pid!=identity['pid']:parents.append(process_identity(parent.pid))
                document=dict(schema=1,session=workspace.name,created=time.time(),target=str(target),old_sha256=old_hash,
                    profile=profile,version=version,source_version='2.0.6',manifest=base64.b64encode((release/'release-manifest.json').read_bytes()).decode('ascii'),
                    signature=base64.b64encode((release/'release-manifest.sig').read_bytes()).decode('ascii'),package=str(workspace/asset.name),
                    parents=[p.json() for p in parents],jana_wait=[],cwd=str(case),restart=profile=='standalone-onefile',
                    jana=profile=='jana2020-onedir',helper_sha256=digest(helper))
                plan=write_plan(workspace,document)
                controlled_helper=subprocess.Popen([str(workspace/helper.name),'--apply-plan',str(plan),'--quiet'],cwd=workspace,creationflags=subprocess.CREATE_NO_WINDOW)
                wait_for(workspace/'helper-ready.json',controlled_helper)
                assert parent.poll() is None and digest(target)==old_hash
                stop.write_text('natural controlled shutdown');parent.wait(timeout=15)
                report=wait_for(workspace/'update-result.json',seconds=90)
                controlled_helper.wait(timeout=15)
                assert report['ok'] is (not bad),report
                assert digest(target)==(old_hash if bad else digest(new_image))
                for path,value in sentinels.items():assert path.read_bytes()==value
                if profile=='jana2020-onedir':
                    assert (install/'_internal'/('old-runtime.txt' if bad else 'new-runtime.txt')).is_file()
                    assert not (workspace/'startup.json').exists()
                else:
                    if not bad:assert (workspace/'startup.json').exists()
                results.append(dict(case=label,passed=True,helper_exit=controlled_helper.returncode,scientific_sentinels_unchanged=True))
            finally:
                stop.write_text('stop');(case/'fixture-stop-new').write_text('natural controlled shutdown')
                if parent.poll() is None:parent.wait(timeout=15)
                if controlled_helper is not None and controlled_helper.poll() is None:controlled_helper.wait(timeout=190)
    (base/'acceptance.json').write_text(json.dumps(dict(results=results,fixture_apps=True,real_phase_studio_gui=False,
        real_jana=False,production_key=False,private_key_written=False),indent=2))
    print('PASS: frozen helper and controlled PE fixtures; both profiles, success and startup-failure rollback. No production key or real Jana acceptance.')


if __name__=='__main__':main()
