import hashlib
from pathlib import Path
import stat
import zipfile

import pytest

from phase_studio.update_manifest import UpdateAsset,UpdateVerificationError
from phase_studio.update_package import extract_jana_package,verify_package


def package(tmp_path,extras=()):
    path=tmp_path/'package.zip'
    root='PhaseStudio-Jana2020-2.0.6/'
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr(root+'Phase_studio.exe',b'MZ controlled executable fixture')
        archive.writestr(root+'_internal/runtime.dll',b'controlled runtime')
        for name,data in extras:
            if isinstance(name,str) and '\\' in name:
                info=zipfile.ZipInfo();info.filename=name
                archive.writestr(info,data)
            else:archive.writestr(name,data)
    return path,UpdateAsset('jana2020-onedir','PhaseStudio-Jana2020-2.0.6.zip',
        path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest())


def test_extract_new_stage_and_preserve_other_files(tmp_path):
    path,asset=package(tmp_path)
    sentinel=tmp_path/'science.inflip';sentinel.write_bytes(b'unchanged')
    stage=extract_jana_package(path,tmp_path/'stage',asset,'2.0.6')
    assert (stage/'Phase_studio.exe').read_bytes().startswith(b'MZ')
    assert (stage/'_internal/runtime.dll').read_bytes()==b'controlled runtime'
    assert sentinel.read_bytes()==b'unchanged'
    with pytest.raises(UpdateVerificationError):extract_jana_package(path,stage,asset,'2.0.6')


@pytest.mark.parametrize('name',[
    '../escape','/absolute','C:/escape','Other/Phase_studio.exe',
    'PhaseStudio-Jana2020-2.0.6/../escape',
    'PhaseStudio-Jana2020-2.0.6/_internal/../../escape',
    'PhaseStudio-Jana2020-2.0.6/_internal\\escape',
    'PhaseStudio-Jana2020-2.0.6/_internal/CON.txt',
    'PhaseStudio-Jana2020-2.0.6/_internal/trailing.',
    'PhaseStudio-Jana2020-2.0.6/_internal/file:stream',
    'PhaseStudio-Jana2020-2.0.6/science.m40',
    'PhaseStudio-Jana2020-2.0.6/phase_studio.EXE',
    'PhaseStudio-Jana2020-2.0.6/_internal/runtime.dll/child',
])
def test_reject_unsafe_inventory_before_creating_stage(tmp_path,name):
    path,asset=package(tmp_path,[(name,b'invalid')])
    with pytest.raises(UpdateVerificationError):extract_jana_package(path,tmp_path/'stage',asset,'2.0.6')
    assert not (tmp_path/'stage').exists()


def test_reject_symlink(tmp_path):
    info=zipfile.ZipInfo('PhaseStudio-Jana2020-2.0.6/_internal/link')
    info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
    path,asset=package(tmp_path,[(info,b'../../science')])
    with pytest.raises(UpdateVerificationError):extract_jana_package(path,tmp_path/'stage',asset,'2.0.6')


def test_corrupted_download(tmp_path):
    path,asset=package(tmp_path)
    path.write_bytes(path.read_bytes()+b'tampered')
    with pytest.raises(UpdateVerificationError):verify_package(path,asset)


def test_missing_runtime_and_malformed_zip(tmp_path):
    for data in (b'not a zip',):
        path=tmp_path/'invalid.zip';path.write_bytes(data)
        asset=UpdateAsset('jana2020-onedir',path.name,len(data),hashlib.sha256(data).hexdigest())
        with pytest.raises(UpdateVerificationError):extract_jana_package(path,tmp_path/'stage',asset,'2.0.6')
    path=tmp_path/'missing.zip'
    with zipfile.ZipFile(path,'w') as z:z.writestr('PhaseStudio-Jana2020-2.0.6/Phase_studio.exe',b'MZ')
    asset=UpdateAsset('jana2020-onedir',path.name,path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(UpdateVerificationError):extract_jana_package(path,tmp_path/'stage',asset,'2.0.6')
