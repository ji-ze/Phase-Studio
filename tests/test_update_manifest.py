"""Synthetic signing keys only; no live release or private production material."""
import copy

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat

from phase_studio import update_manifest as m


@pytest.fixture
def signed():
    key=Ed25519PrivateKey.generate()
    public=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    document=dict(schema=1,application='Phase Studio',repository='ji-ze/Phase-Studio',
        version='2.0.6',channel='stable',os='windows',arch='x64',minimum_updater_protocol=1,
        signature_algorithm='Ed25519',key_id='ephemeral-test',assets=[
            dict(profile='standalone-onefile',name='PhaseStudio-2.0.6-x64.exe',size=12,sha256='a'*64),
            dict(profile='jana2020-onedir',name='PhaseStudio-Jana2020-2.0.6.zip',size=34,sha256='b'*64)])
    def verify(document=document,**kwargs):
        raw=m.canonical_manifest(document)
        return m.verify_manifest(raw,key.sign(raw),release_version='2.0.6',
            trusted_keys={'ephemeral-test':public},**kwargs)
    return key,public,document,verify


def test_signed_profiles(signed):
    key,public,document,verify=signed
    result=verify()
    assert result.asset('standalone-onefile').size==12
    assert result.asset('jana2020-onedir').name=='PhaseStudio-Jana2020-2.0.6.zip'
    with pytest.raises(m.UpdateVerificationError):result.asset('unknown')


def test_no_production_key_fails_closed(signed):
    key,public,document,verify=signed
    raw=m.canonical_manifest(document)
    with pytest.raises(m.UpdateVerificationError,match='No trusted'):
        m.verify_manifest(raw,key.sign(raw),release_version='2.0.6',trusted_keys={})


@pytest.mark.parametrize('field,value',[
    ('schema',2),('schema',True),('minimum_updater_protocol',2),('minimum_updater_protocol',False),
    ('repository','other/repository'),('application','Other'),('channel','preview'),
    ('os','linux'),('arch','arm64'),('version','2.0.7'),('version','v2.0.6'),
    ('signature_algorithm','none'),('key_id','untrusted'),('unknown_critical',True),
])
def test_signed_but_incompatible_metadata(signed,field,value):
    key,public,document,verify=signed
    changed=copy.deepcopy(document);changed[field]=value
    with pytest.raises(m.UpdateVerificationError):verify(changed)


@pytest.mark.parametrize('field,value',[
    ('name','other.exe'),('name','../PhaseStudio-2.0.6-x64.exe'),('size',0),
    ('size',True),('size',m.MAX_PACKAGE_BYTES+1),('sha256','X'*64),('sha256','a'*63),
    ('profile','jana2020-onedir'),('unexpected',1),
])
def test_invalid_assets(signed,field,value):
    key,public,document,verify=signed
    changed=copy.deepcopy(document);changed['assets'][0][field]=value
    with pytest.raises(m.UpdateVerificationError):verify(changed)


def test_tampering_and_canonical_bytes(signed):
    key,public,document,verify=signed
    raw=m.canonical_manifest(document)
    for content,signature in [(raw+b' ',key.sign(raw)),(raw,key.sign(raw)[:-1]),
            (raw,b'\0'*64),(raw.replace(b'"size":12',b'"size":13'),key.sign(raw)),
            (b'{"schema":1,"schema":1}',b'\0'*64)]:
        with pytest.raises(m.UpdateVerificationError):
            m.verify_manifest(content,signature,release_version='2.0.6',trusted_keys={'ephemeral-test':public})
