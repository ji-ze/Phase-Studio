"""Narrow, journaled replacement of Phase Studio-owned Windows files only.

The independent helper authenticates the plan, parent process and signed
manifest before calling this module. No scientific invocation is executed here.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import shutil
import uuid
import time

from .update_manifest import UpdateAsset,UpdateVerificationError
from .update_package import verify_package,extract_jana_package

INVENTORY='phase_studio/installation.json'


def digest(path):
    with Path(path).open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def reject_links(path):
    path=Path(path).absolute()
    for item in (path,*path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.stat(follow_symlinks=False),'st_file_attributes',0)&0x400):
            raise UpdateVerificationError('Installation or staging paths may not contain links.')
    return path


def _replace(source,destination,*,timeout=5.):
    """Bound Windows sharing delays without weakening atomicity or ownership.

    Real complete runtimes can be briefly held by another Windows component
    after extraction/hash inspection. Re-extracting on each attempt recreates
    the delay. Keep the verified tree and retry only the atomic rename.
    Permanent permissions and other errors still fail into existing rollback.
    """
    deadline=time.monotonic()+timeout
    while True:
        reject_links(source);reject_links(destination)
        try:return os.replace(source,destination)
        except OSError as exc:
            if getattr(exc,'winerror',None) not in (5,32,33) or time.monotonic()>=deadline:raise
            time.sleep(min(.1,max(0.,deadline-time.monotonic())))


def runtime_files(directory):
    files={}
    for path in directory.rglob('*'):
        reject_links(path)
        if path.is_file():files[path.relative_to(directory).as_posix()]=digest(path)
    return files


def write_inventory(runtime):
    """Build-time only, after the complete owned runtime has been assembled."""
    runtime=Path(runtime);reject_links(runtime)
    files=runtime_files(runtime);files.pop(INVENTORY,None)
    path=runtime/INVENTORY;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'schema':1,'files':files},sort_keys=True,separators=(',',':')),encoding='utf8')


def verify_inventory(runtime):
    runtime=Path(runtime);reject_links(runtime)
    try:
        document=json.loads((runtime/INVENTORY).read_text(encoding='utf8'))
        if set(document)!={'schema','files'} or type(document['schema']) is not int or document['schema']!=1:
            raise ValueError
        expected=document['files']
        if not isinstance(expected,dict) or not expected or INVENTORY in expected:raise ValueError
        actual=runtime_files(runtime);actual.pop(INVENTORY)
        if actual!=expected:raise ValueError
    except (OSError,ValueError,KeyError,TypeError):
        raise UpdateVerificationError('Runtime ownership inventory is missing or changed. Use manual migration; no files were removed.') from None


def runtime_generation(runtime):
    """Content identity independent of application version and directory name.

    Validate ownership first. Include the inventory itself so no metadata file
    can change unnoticed when deciding whether replacement may retain runtime.
    """
    verify_inventory(runtime)
    manifest=runtime_files(Path(runtime))
    return hashlib.sha256(json.dumps(manifest,sort_keys=True,
        separators=(',',':')).encode('utf8')).hexdigest()


def _journal_path(target):
    return target.parent/('.phase-studio-update-'+hashlib.sha256(target.name.casefold().encode()).hexdigest()[:16]+'.json')


def _paths(target,transaction):
    if str(uuid.UUID(transaction))!=transaction:raise UpdateVerificationError('Invalid transaction identity.')
    return (target.parent/('.phase-studio-stage-'+transaction),
        target.parent/('.phase-studio-backup-'+transaction+'.exe'),
        target.parent/('.phase-studio-runtime-'+transaction))


def _write(path,document):
    temp=path.with_suffix('.tmp')
    reject_links(path);reject_links(temp)
    with temp.open('w',encoding='utf8') as stream:
        json.dump(document,stream,sort_keys=True,separators=(',',':'));stream.flush();os.fsync(stream.fileno())
    _replace(temp,path)


@contextmanager
def installation_lock(target):
    """Kernel-backed lock; a process crash releases it without stale PID guesses."""
    import msvcrt
    path=_journal_path(Path(target)).with_suffix('.lock')
    reject_links(path)
    with path.open('a+b') as stream:
        stream.seek(0,2)
        if stream.tell()==0:stream.write(b'\0');stream.flush()
        stream.seek(0)
        try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise UpdateVerificationError('Another updater owns this installation.') from None
        try:yield
        finally:
            stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)


def _remove_owned_runtime(path):
    # Never remove a shared Jana/application root. Only a complete inventory-
    # verified runtime directory generated by this application's build is owned.
    verify_inventory(path)
    shutil.rmtree(path)


def _clean_backup_runtime(path,expected):
    actual=runtime_files(path)
    if not isinstance(expected,dict) or any(expected.get(name)!=value for name,value in actual.items()):
        raise UpdateVerificationError('Backup directory contains changed or unrelated files.')
    shutil.rmtree(path)


def _rollback(target,document):
    stage,backup,runtime_backup=_paths(target,document['transaction'])
    runtime=target.parent/'_internal'
    if backup.exists():
        if digest(backup)!=document['old_sha256']:raise UpdateVerificationError('Backup integrity verification failed.')
        if target.exists() and digest(target)!=document['new_sha256']:
            raise UpdateVerificationError('Installation changed during recovery; backup retained.')
        if document['profile']=='jana2020-onedir' and runtime_backup.exists():
            verify_inventory(runtime_backup)
            if runtime.exists():_remove_owned_runtime(runtime)
            _replace(runtime_backup,runtime)
        _replace(backup,target)
        if digest(target)!=document['old_sha256']:raise UpdateVerificationError('Restored executable verification failed.')
    if stage.exists():
        # This exact newly-created transaction directory is never an install root.
        reject_links(stage)
        for child in stage.rglob('*'):reject_links(child)
        shutil.rmtree(stage)


def recover(target,*,old_sha256,new_sha256):
    target=reject_links(Path(target).absolute())
    with installation_lock(target):
        journal=_journal_path(target)
        document=json.loads(journal.read_text(encoding='utf8'))
        if (document.get('target')!=str(target) or document.get('old_sha256')!=old_sha256
                or document.get('new_sha256')!=new_sha256
                or document.get('profile') not in ('standalone-onefile','jana2020-onedir')):
            raise UpdateVerificationError('Recovery journal does not match the authenticated update plan.')
        if document.get('state')=='healthy':
            if digest(target)!=new_sha256:raise UpdateVerificationError('Healthy installation changed; backups retained.')
            stage,backup,runtime_backup=_paths(target,document['transaction'])
            if backup.exists():
                if digest(backup)!=old_sha256:raise UpdateVerificationError('Backup integrity verification failed.')
                backup.unlink()
            if runtime_backup.exists():_clean_backup_runtime(runtime_backup,document.get('old_runtime_files'))
            if document.get('retained_runtime') and (stage/'_internal').exists():
                _remove_owned_runtime(stage/'_internal')
            if stage.exists():stage.rmdir()
            journal.unlink();return
        _rollback(target,document)
        journal.unlink()


def install(target,package,asset:UpdateAsset,version,*,old_sha256,workspace,
            verify_startup,restart=None,fault=None):
    """Copy across drives, then rename locally; retain backups through health check.

    verify_startup and restart belong to the authenticated helper, never to
    downloaded code or JSON. fault is an explicit injection point for tests.
    """
    target=reject_links(Path(target).absolute())
    workspace=reject_links(Path(workspace).absolute())
    if workspace.is_relative_to(target.parent):raise UpdateVerificationError('Update workspace must be outside the installation.')
    if target.suffix.lower()!='.exe' or not target.is_file():raise UpdateVerificationError('Installed executable not found.')
    if asset.profile not in ('standalone-onefile','jana2020-onedir'):raise UpdateVerificationError('Unsupported installation profile.')
    if asset.profile=='jana2020-onedir' and target.name!='Phase_studio.exe':
        raise UpdateVerificationError('Legacy wrapper installations require manual migration.')
    with installation_lock(target):
        journal=_journal_path(target)
        if journal.exists():raise UpdateVerificationError('An interrupted update requires authenticated recovery first.')
        if digest(target)!=old_sha256:raise UpdateVerificationError('Installed executable changed; update cancelled.')
        verify_package(Path(package),asset)
        transaction=str(uuid.uuid4());stage,backup,runtime_backup=_paths(target,transaction)
        runtime=target.parent/'_internal'
        if asset.profile=='jana2020-onedir':verify_inventory(runtime)
        onedir=asset.profile=='jana2020-onedir'
        # Extract directly into the installation's own local staging directory.
        # An elevated helper must never copy an attacker-editable extracted DLL
        # tree from a user cache into a protected installation.
        if onedir:
            extract_jana_package(Path(package),stage,asset,version)
            verify_inventory(stage/'_internal')
            new_sha=digest(stage/'Phase_studio.exe')
        else:
            stage.mkdir();new_sha=asset.sha256
        retain_runtime=onedir and runtime_generation(runtime)==runtime_generation(stage/'_internal')
        document={'schema':1,'transaction':transaction,'target':str(target),'profile':asset.profile,
            'old_sha256':old_sha256,'new_sha256':new_sha,'state':'prepared',
            'retained_runtime':retain_runtime,
            'old_runtime_files':runtime_files(runtime) if onedir else None}
        lease=None
        try:
            if not onedir:shutil.copyfile(Path(package),stage/target.name)
            if digest(stage/target.name)!=new_sha:raise UpdateVerificationError('Staged executable integrity failed.')
            _write(journal,document)
            def checkpoint(name):
                document['state']=name;_write(journal,document)
                if fault is not None:fault(name)
            checkpoint('before-backup')
            # Recheck just before the first mutation while holding the install lock.
            if digest(target)!=old_sha256:raise UpdateVerificationError('Installation changed during staging.')
            _replace(target,backup);checkpoint('executable-backed-up')
            if onedir and not retain_runtime:
                _replace(runtime,runtime_backup);checkpoint('runtime-backed-up')
            _replace(stage/target.name,target);checkpoint('executable-installed')
            if onedir and not retain_runtime:
                _replace(stage/'_internal',runtime);checkpoint('runtime-installed')
            if retain_runtime and runtime_generation(runtime)!=runtime_generation(stage/'_internal'):
                raise UpdateVerificationError('Retained runtime changed during installation.')
            if digest(target)!=new_sha:raise UpdateVerificationError('Installed executable differs from verified package.')
            verify_startup(target,version)
            if restart is not None:lease=restart(target,version)
            checkpoint('healthy')
            if lease is not None:lease.commit();lease=None
        except Exception:
            if lease is not None:lease.abort()
            _rollback(target,document)
            journal.unlink(missing_ok=True)
            raise
        else:
            cleanup_pending=False
            try:
                backup.unlink()
                if runtime_backup.exists():_clean_backup_runtime(runtime_backup,document['old_runtime_files'])
                if retain_runtime:_remove_owned_runtime(stage/'_internal')
                stage.rmdir();journal.unlink()
            except OSError:
                cleanup_pending=True  # The verified healthy version remains usable.
        return {'version':version,'profile':asset.profile,'installed_sha256':new_sha,
            'retained_runtime':retain_runtime,
            'restarted':restart is not None,'cleanup_pending':cleanup_pending}
