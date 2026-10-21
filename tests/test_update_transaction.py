import hashlib
from pathlib import Path
import zipfile

import pytest

from phase_studio import update_transaction as t
from phase_studio.update_manifest import UpdateAsset,UpdateVerificationError


def sha(data):return hashlib.sha256(data).hexdigest()


@pytest.mark.skipif(__import__('os').name!='nt',reason='Windows sharing semantics')
def test_atomic_rename_waits_for_actual_windows_reader(tmp_path):
    import threading
    source=tmp_path/'new.bin';target=tmp_path/'old.bin'
    source.write_bytes(b'new verified payload');target.write_bytes(b'old payload')
    reader=target.open('rb');timer=threading.Timer(.25,reader.close);timer.start()
    try:t._replace(source,target,timeout=2.)
    finally:timer.cancel();reader.close();timer.join()
    assert target.read_bytes()==b'new verified payload' and not source.exists()


@pytest.mark.skipif(__import__('os').name!='nt',reason='Windows sharing semantics')
def test_permanent_reader_retains_old_payload_and_new_source(tmp_path):
    source=tmp_path/'new.bin';target=tmp_path/'old.bin'
    source.write_bytes(b'new');target.write_bytes(b'old')
    with target.open('rb'):
        with pytest.raises(OSError):t._replace(source,target,timeout=.02)
    assert target.read_bytes()==b'old' and source.read_bytes()==b'new'


def test_other_rename_errors_are_not_retried(tmp_path,monkeypatch):
    calls=[]
    def missing(*args):calls.append(args);raise FileNotFoundError('Controlled missing source')
    monkeypatch.setattr(t.os,'replace',missing)
    with pytest.raises(FileNotFoundError):t._replace(tmp_path/'missing',tmp_path/'destination')
    assert len(calls)==1


@pytest.fixture(params=['standalone-onefile','jana2020-onedir'])
def installation(tmp_path,request):
    root=tmp_path/'Jana ünicode with spaces'/'SharpED';root.mkdir(parents=True)
    target=root/('Phase_studio.exe' if request.param=='jana2020-onedir' else 'My shortcut target.exe')
    target.write_bytes(b'old executable')
    workspace=tmp_path/'workspace';workspace.mkdir()
    sentinel=root.parent/'SUPERFLIP';sentinel.mkdir()
    (sentinel/'superflip.exe').write_bytes(b'scientific binary')
    (sentinel/'EDMA.exe').write_bytes(b'EDMA untouched')
    project=tmp_path/'project.inflip';project.write_bytes(b'project unchanged')
    (root/'user notes.txt').write_bytes(b'unrelated file')
    package=workspace/'new-package'
    if request.param=='jana2020-onedir':
        runtime=root/'_internal';runtime.mkdir();(runtime/'old.dll').write_bytes(b'old runtime')
        t.write_inventory(runtime)
        new=workspace/'new';(new/'_internal').mkdir(parents=True)
        (new/'Phase_studio.exe').write_bytes(b'new executable')
        (new/'_internal/new.dll').write_bytes(b'new runtime')
        t.write_inventory(new/'_internal')
        with zipfile.ZipFile(package,'w') as archive:
            for file in new.rglob('*'):
                if file.is_file():archive.write(file,'PhaseStudio-Jana2020-2.0.6/'+file.relative_to(new).as_posix())
    else:package.write_bytes(b'new executable')
    asset=UpdateAsset(request.param,package.name,package.stat().st_size,t.digest(package))
    snapshots={p:p.read_bytes() for p in (project,sentinel/'superflip.exe',sentinel/'EDMA.exe',root/'user notes.txt')}
    yield target,package,asset,workspace
    assert all(p.read_bytes()==data for p,data in snapshots.items())


def install(fixture,**kwargs):
    target,package,asset,workspace=fixture
    return t.install(target,package,asset,'2.0.6',old_sha256=sha(b'old executable'),
        workspace=workspace,verify_startup=lambda exe,version:None,**kwargs)


def test_transactional_replacement(installation):
    target,package,asset,workspace=installation
    report=install(installation)
    assert target.read_bytes()==b'new executable'
    assert report['profile']==asset.profile
    assert not t._journal_path(target).exists()
    if asset.profile=='jana2020-onedir':
        assert not (target.parent/'_internal/old.dll').exists()
        assert (target.parent/'_internal/new.dll').read_bytes()==b'new runtime'


@pytest.mark.parametrize('stage',['before-backup','executable-backed-up','runtime-backed-up',
    'executable-installed','runtime-installed','healthy'])
def test_failure_restores_complete_previous_installation(installation,stage):
    target,package,asset,workspace=installation
    if asset.profile=='standalone-onefile' and stage.startswith('runtime-'):pytest.skip('No runtime in ONEFILE')
    def fault(point):
        if point==stage:raise OSError('controlled failure')
    with pytest.raises(OSError):install(installation,fault=fault)
    assert target.read_bytes()==b'old executable'
    if asset.profile=='jana2020-onedir':
        assert (target.parent/'_internal/old.dll').read_bytes()==b'old runtime'
        assert not (target.parent/'_internal/new.dll').exists()


def test_power_interruption_recovery(installation):
    target,package,asset,workspace=installation
    def interrupt(point):
        if point=='executable-installed':raise SystemExit('simulated power interruption')
    with pytest.raises(SystemExit):install(installation,fault=interrupt)
    assert t._journal_path(target).exists()
    t.recover(target,old_sha256=sha(b'old executable'),new_sha256=sha(b'new executable'))
    assert target.read_bytes()==b'old executable'
    assert not t._journal_path(target).exists()


def test_changed_installation_rejected(installation):
    target,package,asset,workspace=installation
    target.write_bytes(b'user changed executable')
    with pytest.raises(UpdateVerificationError):install(installation)
    assert target.read_bytes()==b'user changed executable'


def test_unrelated_internal_file_prevents_destructive_update(installation):
    target,package,asset,workspace=installation
    if asset.profile!='jana2020-onedir':pytest.skip('ONEDIR only')
    extra=target.parent/'_internal/user-science.m40';extra.write_bytes(b'never remove')
    with pytest.raises(UpdateVerificationError):install(installation)
    assert extra.read_bytes()==b'never remove'
    assert target.read_bytes()==b'old executable'


def test_concurrent_updater_rejected(installation):
    target,*_=installation
    with t.installation_lock(target):
        with pytest.raises(UpdateVerificationError,match='Another updater'):install(installation)


def test_startup_failure_rolls_back(installation):
    target,package,asset,workspace=installation
    def failed(*_):raise RuntimeError('new application failed to start')
    with pytest.raises(RuntimeError):
        t.install(target,package,asset,'2.0.6',old_sha256=sha(b'old executable'),workspace=workspace,verify_startup=failed)
    assert target.read_bytes()==b'old executable'
