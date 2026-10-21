"""Disposable transaction compatibility check using actual optimized packages.

Same-version packaging fixtures intentionally exercise the transaction layer,
not the public updater's strictly-newer-version gate or production signing.
"""
from pathlib import Path
import argparse,json,os,shutil,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True);parser.add_argument('--optimized',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    base=args.output.resolve()
    if not base.is_relative_to(ROOT/'build') or base.exists():raise ValueError('A new isolated directory under build is required.')
    base.mkdir(parents=True)
    from phase_studio import update_transaction as t
    from phase_studio.update_manifest import UpdateAsset
    from phase_studio.update_windows import RestartJob
    old=args.baseline.resolve()/'PhaseStudio-Jana2020-2.0.6'
    optimized=args.optimized.resolve();archive=optimized/'release/PhaseStudio-Jana2020-2.0.6.zip'
    asset=UpdateAsset('jana2020-onedir',archive.name,archive.stat().st_size,t.digest(archive))
    new_sha=t.digest(optimized/'PhaseStudio-Jana2020-2.0.6/Phase_studio.exe')
    results=[]
    os.environ.update(QT_QPA_PLATFORM='windows',PHASE_STUDIO_STARTUP_PROBE='1',PHASE_STUDIO_ACCEPTANCE_STARTUP_ONLY='1')
    for mode in ('success','startup-failure','interruption'):
        # Journal staging adds a UUID component; use short disposable roots so
        # legacy Windows MAX_PATH does not invalidate long upstream licenses.
        case=base/{'success':'s','startup-failure':'f','interruption':'i'}[mode]
        case.mkdir();target_dir=case/'p'
        shutil.copytree(old,target_dir);target=target_dir/'Phase_studio.exe';old_sha=t.digest(target)
        sentinel=target_dir.parent/'SUPERFLIP';sentinel.mkdir()
        fixed={sentinel/'superflip.exe':b'Superflip sentinel',sentinel/'EDMA.exe':b'EDMA sentinel',case/'project.inflip':b'project sentinel',target_dir/'user-notes.txt':b'unrelated file'}
        for path,data in fixed.items():path.write_bytes(data)
        workspace=case/'workspace';workspace.mkdir()
        def probe(exe,version):
            output=workspace/'probe.json'
            completed=subprocess.run([str(exe),'--update-runtime-check',str(output)],capture_output=True,timeout=60)
            report=json.loads(output.read_text(encoding='utf8'));assert completed.returncode==0 and report['ok'] and report['version']==version
            if mode=='startup-failure':raise RuntimeError('Controlled failure after successful frozen runtime probe.')
        def restart(exe,version):
            directory=workspace/'restart';job=RestartJob(exe,['--packaging-acceptance',str(directory)],workspace)
            try:
                assert job.wait(60)==0
                report=json.loads((directory/'acceptance.json').read_text(encoding='utf8'));assert report['ok'] and report['visible']
                return job
            except BaseException:job.abort();raise
        def fault(state):
            if mode=='interruption' and state=='executable-installed':raise SystemExit('Controlled power-loss boundary')
        retries=[]
        for attempt in range(3):
            try:
                t.install(target,archive,asset,'2.0.6',old_sha256=old_sha,workspace=workspace,verify_startup=probe,
                    restart=restart if mode=='success' else None,fault=fault)
                break
            except RuntimeError:
                if mode!='startup-failure':raise
                break
            except SystemExit:
                if mode!='interruption':raise
                t.recover(target,old_sha256=old_sha,new_sha256=new_sha)
                break
            except OSError as exc:
                # A manual retry is legitimate only after proving rollback.
                # Preserve observed failures instead of pretending first-pass success.
                assert t.digest(target)==old_sha;t.verify_inventory(target_dir/'_internal')
                retries.append(dict(attempt=attempt+1,windows_error=getattr(exc,'winerror',None),old_runtime_restored=True))
                if getattr(exc,'winerror',None) not in (5,32,33) or attempt==2:raise
                time.sleep(.5)
        assert t.digest(target)==(new_sha if mode=='success' else old_sha)
        t.verify_inventory(target_dir/'_internal')
        for path,data in fixed.items():assert path.read_bytes()==data
        assert (target_dir/'_internal/qtvscodestyle').exists() is (mode!='success')
        results.append(dict(case=mode,passed=True,actual_packages=True,scientific_and_unrelated_sentinels_unchanged=True,manual_retry_simulation=retries))
    (base/'acceptance.json').write_text(json.dumps(dict(results=results,transaction_layer=True,public_update=False,
        production_signature=False,strict_version_gate_tested=False,real_jana=False),indent=2),encoding='utf8')
    print('PASS: actual ONEDIR packages, complete runtime replacement, frozen restart, rollback and interrupted recovery; public installation remains disabled.')


if __name__=='__main__':main()
