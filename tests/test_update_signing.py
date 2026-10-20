import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,PublicFormat,NoEncryption

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('_update_signing_tool',ROOT/'packaging/tools/update_signing.py')
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)


@pytest.fixture
def release(tmp_path):
    directory=tmp_path/'release';directory.mkdir()
    for name in tool.asset_names('2.0.6')[:2]: (directory/name).write_bytes(b'controlled package '+name.encode())
    (directory/'RELEASE_NOTES_2.0.6.md').write_text('Controlled release notes',encoding='utf8')
    key=Ed25519PrivateKey.generate()
    public=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    keys={hashlib.sha256(public).hexdigest()[:16]:public}
    secret=base64.b64encode(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())).decode('ascii')
    return directory,keys,secret


def test_signed_six_asset_contract(release):
    directory,keys,secret=release
    tool.sign_release(directory,'2.0.6',keys=keys,secret=secret)
    assert len(list(directory.iterdir()))==6
    manifest=tool.validate_release(directory,'2.0.6',keys=keys)
    assert manifest.asset('jana2020-onedir').name=='PhaseStudio-Jana2020-2.0.6.zip'
    assert all(secret not in p.read_bytes().decode('utf8',errors='ignore') for p in directory.iterdir())
    before={p.name:p.read_bytes() for p in directory.iterdir()}
    with pytest.raises(ValueError):tool.sign_release(directory,'2.0.6',keys=keys,secret=secret)
    assert before=={p.name:p.read_bytes() for p in directory.iterdir()}


@pytest.mark.parametrize('secret', ['', 'invalid',base64.b64encode(b'wrong length').decode()])
def test_missing_or_invalid_secret_never_writes_metadata(release,secret):
    directory,keys,_=release
    with pytest.raises(ValueError):tool.sign_release(directory,'2.0.6',keys=keys,secret=secret)
    assert not (directory/'release-manifest.json').exists()


def test_unpinned_key_rejected(release):
    directory,keys,secret=release
    with pytest.raises(ValueError,match='compiled public'):tool.sign_release(directory,'2.0.6',keys={},secret=secret)


def test_unexpected_asset_and_tampering(release):
    directory,keys,secret=release
    extra=directory/'private.txt';extra.write_text('never publish')
    with pytest.raises(ValueError):tool.sign_release(directory,'2.0.6',keys=keys,secret=secret)
    extra.unlink()
    tool.sign_release(directory,'2.0.6',keys=keys,secret=secret)
    (directory/'PhaseStudio-2.0.6-x64.exe').write_bytes(b'modified')
    with pytest.raises(ValueError):tool.validate_release(directory,'2.0.6',keys=keys)


def test_one_time_generation_and_public_pin(tmp_path):
    repository=tmp_path/'repo';repository.mkdir()
    with pytest.raises(ValueError):tool.generate(repository/'keys',repository=repository)
    directory=tmp_path/'private-keys'
    public=tool.generate(directory,repository=repository)
    private=(directory/'phase-studio-update-signing-key.txt').read_text().strip()
    assert len(base64.b64decode(private,validate=True))==32
    with pytest.raises(ValueError):tool.generate(directory,repository=repository)
    target=repository/'trust.py'
    tool.pin_public(directory/'phase-studio-update-public.json',destination=target)
    assert private not in target.read_text()
    scope={};exec(target.read_text(),scope)
    assert scope['TRUSTED_KEYS']=={public['key_id']:bytes.fromhex(public['public_key_hex'])}
    tool.pin_public(directory/'phase-studio-update-public.json',destination=target)
    another=tmp_path/'other-private-keys'
    tool.generate(another,repository=repository)
    before=target.read_bytes()
    with pytest.raises(ValueError,match='rotation requires source review'):
        tool.pin_public(another/'phase-studio-update-public.json',destination=target)
    assert target.read_bytes()==before
