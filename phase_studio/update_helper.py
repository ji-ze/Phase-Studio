"""Independent frozen updater. No Qt, SharpED credentials or scientific jobs."""
from __future__ import annotations

import argparse
import base64
import ctypes
import json
import os
from pathlib import Path
import sys
import threading
import time

from phase_studio.update_manifest import verify_manifest,TRUSTED_KEYS,PROTOCOL,UpdateVerificationError
from phase_studio.update_plan import read_plan
from phase_studio.update_transaction import install,recover,digest,reject_links,_journal_path,_paths
from phase_studio.update_windows import (ProcessGuard,ProcessIdentity,RestartJob,PathGuards,
    validate_phase_studio_executable,elevate,running_at,duplicate_restart_token,CloseHandle)
from phase_studio.update_checker import parse_version


def _status(workspace,name,document):
    import uuid
    path=workspace/name;temp=workspace/(name+'.'+str(uuid.uuid4())+'.tmp')
    reject_links(path);reject_links(temp)
    with temp.open('x',encoding='utf8') as stream:
        json.dump(document,stream);stream.flush();os.fsync(stream.fileno())
    os.replace(temp,path)


def _probe(target,version,workspace,token=None):
    output=workspace/'runtime-check.json'
    output.unlink(missing_ok=True)
    job=RestartJob(target,['--update-runtime-check',str(output)],workspace,token=token)
    try:
        if job.wait(40)!=0:raise UpdateVerificationError('The new runtime could not start.')
        report=json.loads(output.read_text(encoding='utf8'))
        if not report.get('ok') or report.get('version')!=version:
            raise UpdateVerificationError('The new runtime version or bundled updater is invalid.')
    finally:job.abort()


def _restart(target,version,workspace,cwd,token=None):
    acknowledgement=workspace/'startup.json'
    acknowledgement.unlink(missing_ok=True)
    job=RestartJob(target,['--update-health',str(acknowledgement)],cwd,token=token)
    try:
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            if acknowledgement.exists():
                report=json.loads(acknowledgement.read_text(encoding='utf8'))
                if report.get('version')!=version or type(report.get('pid')) is not int:
                    raise UpdateVerificationError('Invalid application startup acknowledgement.')
                with ProcessGuard(report['pid']) as child:
                    if os.path.normcase(child.identity.executable)!=os.path.normcase(str(target)):
                        raise UpdateVerificationError('Startup acknowledgement belongs to another executable.')
                return job
            if not job.alive():raise UpdateVerificationError('The updated application closed before startup completed.')
            threading.Event().wait(.1)
        raise UpdateVerificationError('The updated application did not acknowledge visible startup.')
    except BaseException:job.abort();raise


def apply(path,elevated=False,recovery=False):
    path=Path(path).absolute();workspace=path.parent
    plan=read_plan(path)
    fields={'schema','session','created','target','old_sha256','profile','version','source_version',
        'manifest','signature','package','parents','jana_wait','cwd','restart','jana','helper_sha256'}
    if set(plan)!=fields or type(plan['jana']) is not bool or type(plan['restart']) is not bool:
        raise UpdateVerificationError('Unsupported update plan fields.')
    if not isinstance(plan['created'],(int,float)) or not recovery and not 0<=time.time()-plan['created']<3600:
        raise UpdateVerificationError('The prepared update expired; prepare it again.')
    if plan['jana'] and plan['restart']:raise UpdateVerificationError('Direct Jana sessions cannot be automatically restarted.')
    old_version,new_version=parse_version(plan['source_version']),parse_version(plan['version'])
    if old_version is None or new_version is None or new_version<=old_version:
        raise UpdateVerificationError('Update version must be newer than the installed version.')
    manifest=verify_manifest(base64.b64decode(plan['manifest'],validate=True),
        base64.b64decode(plan['signature'],validate=True),release_version=plan['version'])
    asset=manifest.asset(plan['profile'])
    target=reject_links(Path(plan['target']).absolute())
    package=reject_links(Path(plan['package']).absolute())
    if package.parent!=workspace or package.name!=asset.name:
        raise UpdateVerificationError('Package is outside the authenticated workspace.')
    if not getattr(sys,'frozen',False) or Path(sys.executable).resolve().parent!=workspace.resolve():
        raise UpdateVerificationError('The independent helper must run from its private copied workspace.')
    if digest(Path(sys.executable))!=plan['helper_sha256']:
        raise UpdateVerificationError('The copied helper differs from the bundled helper.')
    if not isinstance(plan['parents'],list) or not 1<=len(plan['parents'])<=3:
        raise UpdateVerificationError('The original application process must be identified.')
    if not isinstance(plan['jana_wait'],list) or len(plan['jana_wait'])>8:
        raise UpdateVerificationError('Invalid Jana waiting process context.')
    if target.exists():validate_phase_studio_executable(target)
    if elevated and not ctypes.windll.shell32.IsUserAnAdmin():
        raise UpdateVerificationError('Elevation was not granted.')
    guards=[];input_guards=None;restart_token=None
    try:
        input_guards=PathGuards([path,Path(sys.executable),package])
        for record in ([] if recovery else plan['parents']):
            expected=ProcessIdentity(**record)
            if os.path.normcase(str(Path(expected.executable).resolve()))!=os.path.normcase(str(target.resolve())):
                raise UpdateVerificationError('Update target does not match the original application process.')
            guards.append(ProcessGuard(expected.pid,expected))
        for record in ([] if recovery else plan['jana_wait']):
            expected=ProcessIdentity(**record);guards.append(ProcessGuard(expected.pid,expected))
        if not recovery and ctypes.windll.shell32.IsUserAnAdmin():
            restart_token=duplicate_restart_token(guards[0].handle)
        if not recovery and digest(target)!=plan['old_sha256']:raise UpdateVerificationError('The installed application changed.')
        # Test permissions before asking the UI to close, never after mutation.
        probe=target.parent/('.phase-studio-permission-'+plan['session'])
        try:
            with probe.open('xb'):pass
            probe.unlink()
        except PermissionError:
            if elevated:raise UpdateVerificationError('The installation folder is still not writable.') from None
            elevate(Path(sys.executable),path,recovery=recovery)
            return None  # Elevated helper publishes readiness after repeating every check.
        _status(workspace,'helper-ready.json',{'session':plan['session'],'pid':os.getpid(),'jana':plan['jana']})
        for guard in guards:guard.wait(180)
        if (workspace/'cancelled').exists():raise UpdateVerificationError('The update was cancelled. Installation is unchanged.')
        if not recovery and running_at(target):raise UpdateVerificationError('Another instance of this Phase Studio installation is still running. Installation is unchanged.')
        cwd=Path(plan['cwd']).absolute()
        if not cwd.is_dir():raise UpdateVerificationError('The original application working directory is unavailable.')
        if recovery:
            if running_at(target):raise UpdateVerificationError('Close this Phase Studio installation before recovery.')
            journal=json.loads(_journal_path(target).read_text(encoding='utf8'))
            _stage,backup,_runtime=_paths(target,journal['transaction'])
            if backup.exists():validate_phase_studio_executable(backup)
            # Recovery uses the authenticated original plan and signed new payload.
            from phase_studio.update_package import verify_package
            verify_package(package,asset)
            if asset.profile=='standalone-onefile':new_sha=asset.sha256
            else:
                import zipfile,hashlib
                with zipfile.ZipFile(package) as archive,archive.open(f'PhaseStudio-Jana2020-{manifest.version}/Phase_studio.exe') as source:
                    new_sha=hashlib.file_digest(source,'sha256').hexdigest()
            recover(target,old_sha256=plan['old_sha256'],new_sha256=new_sha)
            result={'version':manifest.version if journal.get('state')=='healthy' else plan['source_version'],
                'profile':asset.profile,'restarted':False,'recovered':True}
            _status(workspace,'update-result.json',{'ok':True,**result})
            return result
        result=install(target,package,asset,manifest.version,old_sha256=plan['old_sha256'],workspace=workspace,
            verify_startup=lambda exe,version:_probe(exe,version,workspace,restart_token),
            restart=(lambda exe,version:_restart(exe,version,workspace,cwd,restart_token)) if plan['restart'] else None)
        result['reopen_from_jana']=plan['jana']
        _status(workspace,'update-result.json',{'ok':True,**result})
        return result
    finally:
        for guard in guards:guard.close()
        if input_guards is not None:input_guards.close()
        if restart_token is not None:CloseHandle(restart_token)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply-plan',type=Path)
    parser.add_argument('--recover-plan',type=Path)
    parser.add_argument('--elevated',action='store_true')
    parser.add_argument('--self-check',type=Path)
    parser.add_argument('--quiet',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.self_check:
        args.self_check.write_text(json.dumps({'protocol':PROTOCOL,'public_install_enabled':bool(TRUSTED_KEYS),
            'frozen':bool(getattr(sys,'frozen',False))}),encoding='utf8')
        return 0
    path=args.recover_plan or args.apply_plan
    if path is None or args.recover_plan is not None and args.apply_plan is not None:return 2
    try:read_plan(path)
    except Exception:
        if not args.quiet:ctypes.windll.user32.MessageBoxW(None,'The update plan is not authenticated for this Windows user. No installation was changed.','Phase Studio update',0x10)
        return 1
    try:
        result=apply(path,args.elevated,recovery=args.recover_plan is not None)
        if result is not None and not args.quiet:
            message=('Phase Studio recovery completed. Reopen the application.' if result.get('recovered') else
                'Phase Studio was updated. Reopen it from Jana2020.' if result.get('reopen_from_jana')
                and not result['restarted'] else 'Phase Studio was updated and restarted.' if result['restarted']
                else 'Phase Studio was updated.')
            ctypes.windll.user32.MessageBoxW(None,message,'Phase Studio update',0x40)
        return 0
    except Exception as exc:
        # No traceback, environment or signing material enters the UI/report.
        text=str(exc) if isinstance(exc,UpdateVerificationError) else 'The update could not be completed. Check the recovery report before retrying.'
        try:_status(path.parent,'update-result.json',{'ok':False,'message':text,'error_type':type(exc).__name__})
        except OSError:pass
        if not args.quiet and ((path.parent/'helper-ready.json').exists() or args.recover_plan is not None):
            ctypes.windll.user32.MessageBoxW(None,text,'Phase Studio update',0x10)
        return 1


if __name__=='__main__':raise SystemExit(main())
