import hashlib
import zipfile

import pytest

from phase_studio import update_transaction as t
from phase_studio.update_manifest import UpdateAsset, UpdateVerificationError


def test_generation_uses_every_file_not_paths_or_application_version(tmp_path):
    left=tmp_path/'2.0.6';right=tmp_path/'2.0.7'
    for root in (left,right):
        root.mkdir();(root/'runtime.dll').write_bytes(b'identical runtime')
        t.write_inventory(root)
    assert t.runtime_generation(left)==t.runtime_generation(right)
    (right/'runtime.dll').write_bytes(b'changed runtime')
    with pytest.raises(UpdateVerificationError):t.runtime_generation(right)
    t.write_inventory(right)
    assert t.runtime_generation(left)!=t.runtime_generation(right)


@pytest.mark.parametrize('failure',[False,True])
def test_identical_runtime_never_renamed_and_survives_startup_failure(tmp_path,monkeypatch,failure):
    root=tmp_path/'installation';root.mkdir()
    target=root/'Phase_studio.exe';target.write_bytes(b'old executable')
    runtime=root/'_internal';runtime.mkdir()
    (runtime/'runtime.dll').write_bytes(b'shared runtime');t.write_inventory(runtime)
    before={p.relative_to(runtime): (p.read_bytes(),p.stat().st_mtime_ns)
        for p in runtime.rglob('*') if p.is_file()}
    workspace=tmp_path/'workspace';workspace.mkdir();package=workspace/'new.zip'
    with zipfile.ZipFile(package,'w') as archive:
        archive.writestr('PhaseStudio-Jana2020-2.0.7/Phase_studio.exe',b'new executable')
        for relative,(contents,_mtime) in before.items():
            archive.writestr('PhaseStudio-Jana2020-2.0.7/_internal/'+relative.as_posix(),contents)
    asset=UpdateAsset('jana2020-onedir',package.name,package.stat().st_size,t.digest(package))
    original=t._replace
    def checked(source,destination,**kwargs):
        assert source!=runtime and destination!=runtime
        return original(source,destination,**kwargs)
    monkeypatch.setattr(t,'_replace',checked)
    def startup(executable,version):
        assert executable.read_bytes()==b'new executable' and version=='2.0.7'
        if failure:raise RuntimeError('controlled startup failure')
    def install():
        return t.install(target,package,asset,'2.0.7',old_sha256=hashlib.sha256(b'old executable').hexdigest(),
            workspace=workspace,verify_startup=startup)
    if failure:
        with pytest.raises(RuntimeError):install()
    else:assert install()['retained_runtime'] is True
    assert target.read_bytes()==(b'old executable' if failure else b'new executable')
    assert before=={p.relative_to(runtime):(p.read_bytes(),p.stat().st_mtime_ns)
        for p in runtime.rglob('*') if p.is_file()}
    assert not t._journal_path(target).exists()
