"""Controlled security fixtures are not production signing/approval evidence."""
import importlib.util
import json
import os
from pathlib import Path
import struct
import zipfile
import pytest
import yaml

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'packaging/tools'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
auth=load('verify_authenticode');transform=load('verify_signing_transform')


def evidence():
    return dict(sha256='a'*64,status='Valid',signature_type='Authenticode',signer_subject='CN=CONTROLLED TEST FIXTURE',
        signer_thumbprint='B'*40,signer_chain_valid=True,timestamp_present=True,timestamp_chain_valid=True,
        timestamp_eku_valid=True,product_version='2.0.7')
POLICY=dict(expected_sha256='a'*64,subject='CN=CONTROLLED TEST FIXTURE',thumbprints=['B'*40],version='2.0.7')


def test_certificate_policy_accepts_only_complete_bound_evidence():
    assert auth.validate_record(evidence(),**POLICY)==evidence()


@pytest.mark.parametrize('field,value',[
    ('sha256','c'*64),('status','NotSigned'),('status','HashMismatch'),('signature_type','Catalog'),
    ('signer_subject','CN=Unapproved publisher'),('signer_thumbprint','D'*40),('signer_chain_valid',False),
    ('timestamp_present',False),('timestamp_chain_valid',False),('timestamp_eku_valid',False),('product_version','2.0.6'),
])
def test_signature_and_timestamp_fail_closed(field,value):
    with pytest.raises(ValueError):auth.validate_record(evidence()|{field:value},**POLICY)


@pytest.mark.parametrize('change',[{'subject':''},{'thumbprints':[]},{'thumbprints':['not an approved fingerprint']}])
def test_no_default_publisher_identity(change):
    with pytest.raises(ValueError):auth.validate_record(evidence(),**(POLICY|change))


def pe_fixture():
    raw=bytearray(519);raw[:2]=b'MZ';struct.pack_into('<I',raw,60,64);raw[64:68]=b'PE\0\0'
    struct.pack_into('<H',raw,84,224);struct.pack_into('<H',raw,88,0x10b)
    raw[-7:]=b'PAYLOAD'
    checksum,security=transform.pe_offsets(raw)
    result=bytearray(raw)+b'\0'+b'CONTROLLED-CERT!'
    struct.pack_into('<I',result,checksum,123)
    struct.pack_into('<II',result,security,520,16)
    return bytes(raw),bytes(result)


def test_only_authenticode_fields_and_appendix_may_change():
    before,after=pe_fixture()
    transform.assert_signing_only(before,after)
    modified=bytearray(after);modified[400]^=1
    with pytest.raises(ValueError,match='payload'):transform.assert_signing_only(before,modified)
    modified=bytearray(after);modified[519]=1
    with pytest.raises(ValueError):transform.assert_signing_only(before,modified)
    with pytest.raises(ValueError):transform.assert_signing_only(before,after+b'additional payload')


def test_nested_jana_signing_cannot_modify_third_party_bytes(tmp_path):
    before,after=pe_fixture();version='2.0.7'
    unsigned=tmp_path/'unsigned';signed=tmp_path/'signed';unsigned.mkdir();signed.mkdir()
    for folder,data in ((unsigned,before),(signed,after)):
        (folder/'PhaseStudio-2.0.7-x64.exe').write_bytes(data)
        with zipfile.ZipFile(folder/'PhaseStudio-Jana2020-2.0.7.zip','w') as archive:
            archive.writestr('PhaseStudio-Jana2020-2.0.7/Phase_studio.exe',data)
            archive.writestr('PhaseStudio-Jana2020-2.0.7/_internal/Qt6Core.dll',b'Original third-party library')
    transform.compare_packages(unsigned,signed,version)
    with zipfile.ZipFile(signed/'PhaseStudio-Jana2020-2.0.7.zip','w') as archive:
        archive.writestr('PhaseStudio-Jana2020-2.0.7/Phase_studio.exe',after)
        archive.writestr('PhaseStudio-Jana2020-2.0.7/_internal/Qt6Core.dll',b'Modified third-party library')
    with pytest.raises(ValueError,match='third-party'):transform.compare_packages(unsigned,signed,version)


def test_actual_windows_gate_rejects_wrong_publisher(tmp_path):
    if os.name!='nt':pytest.skip('Actual Windows trust API required')
    # Read only: a Microsoft-owned executable must never qualify as Phase Studio.
    executable=Path(os.environ['SystemRoot'])/'System32/cmd.exe'
    with pytest.raises(ValueError):
        auth.verify_file(executable,subject=POLICY['subject'],thumbprints=POLICY['thumbprints'],version='2.0.7')


def test_workflow_orders_helper_signing_before_embedding_and_final_manifest():
    text=(ROOT/'.github/workflows/windows-release.yml').read_text(encoding='utf8')
    workflow=yaml.safe_load(text);jobs=workflow['jobs']
    assert jobs['sign-updater']['needs']=='build'
    assert set(jobs['embed-signed-updater']['needs'])=={'build','sign-updater'}
    assert set(jobs['sign']['needs'])=={'build','embed-signed-updater'}
    assert jobs['publish']['if']=='inputs.publish'
    assert 'RELEASE_ACCEPTANCE_SHA' in text
    assert text.count('signpath/github-action-submit-signing-request@f6d04783b4569d051e0c80105fe66e82819d0092')==2
    sign=text.split('\n  sign:\n')[1].split('\n  publish:\n')[0]
    assert sign.index('verify_signing_transform.py')<sign.index('verify_authenticode.py')<sign.index('update_signing.py sign')
    publish=text.split('\n  publish:\n')[1]
    assert publish.index('verify_authenticode.py')<publish.index('git/refs')<publish.index('--draft=false')
    assert 'generate --' not in text and '--clobber' not in text


def test_existing_ed25519_key_and_verifier_are_not_rotated():
    import subprocess
    for name in ('update_trust.py','update_manifest.py','update_helper.py'):
        original=subprocess.check_output(['git','show','v2.0.6:phase_studio/'+name],cwd=ROOT)
        assert (ROOT/'phase_studio'/name).read_bytes().replace(b'\r\n',b'\n')==original.replace(b'\r\n',b'\n')
    assert '1c016867382d60e0' in (ROOT/'phase_studio/update_trust.py').read_text()
