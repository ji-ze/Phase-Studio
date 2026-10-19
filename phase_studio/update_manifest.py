"""Authenticated update metadata; verification precedes any installation authority.

No production trust key is inferred from downloaded metadata or user settings.
Release engineering must provision the reviewed public key in TRUSTED_KEYS.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from .update_checker import REPOSITORY, parse_version

TRUSTED_KEYS: dict[str, bytes] = {}
PROTOCOL = 1
MAX_MANIFEST_BYTES = 64 * 1024
MAX_PACKAGE_BYTES = 1024 * 1024 * 1024
PROFILES = ('standalone-onefile', 'jana2020-onedir')


class UpdateVerificationError(ValueError):
    """Untrusted or unsupported update; the existing installation stays intact."""


def canonical_manifest(document: dict) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf8')


@dataclass(frozen=True)
class UpdateAsset:
    profile: str
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class VerifiedManifest:
    version: str
    key_id: str
    assets: tuple[UpdateAsset, ...]
    sha256: str

    def asset(self, profile: str) -> UpdateAsset:
        for asset in self.assets:
            if asset.profile == profile:
                return asset
        raise UpdateVerificationError('Unsupported installation profile.')


def _unique_object(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise UpdateVerificationError('Duplicate manifest field.')
        result[key] = value
    return result


def verify_manifest(raw: bytes, signature: bytes, *, release_version: str,
                    trusted_keys: dict[str, bytes] | None = None) -> VerifiedManifest:
    """Verify detached raw Ed25519 signature over canonical UTF-8 JSON.

    An explicit trust map is for isolated tests/release tooling. Runtime callers
    use the compiled trust map; downloaded keys cannot establish trust.
    """
    if not isinstance(raw,bytes) or len(raw)>MAX_MANIFEST_BYTES or not raw:
        raise UpdateVerificationError('Invalid manifest size.')
    if not isinstance(signature,bytes) or len(signature)!=64:
        raise UpdateVerificationError('Invalid manifest signature.')
    try:
        document=json.loads(raw.decode('utf8'),object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        if not isinstance(document,dict) or canonical_manifest(document)!=raw:
            raise UpdateVerificationError('Manifest is not canonical JSON.')
    except (ValueError,UnicodeError,TypeError,RecursionError) as exc:
        raise UpdateVerificationError('Invalid canonical manifest.') from exc
    fields={'schema','application','repository','version','channel','os','arch',
        'minimum_updater_protocol','signature_algorithm','key_id','assets'}
    if set(document)!=fields:
        raise UpdateVerificationError('Unsupported manifest fields.')
    keys=TRUSTED_KEYS if trusted_keys is None else trusted_keys
    key_id=document['key_id']
    if not isinstance(key_id,str) or key_id not in keys:
        raise UpdateVerificationError('No trusted release signing key is configured.')
    if document['signature_algorithm']!='Ed25519':
        raise UpdateVerificationError('Unsupported signature algorithm.')
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
        Ed25519PublicKey.from_public_bytes(keys[key_id]).verify(signature,raw)
    except ImportError as exc:
        raise UpdateVerificationError('Signature verification is unavailable.') from exc
    except (ValueError,TypeError,InvalidSignature) as exc:
        raise UpdateVerificationError('Release signature verification failed.') from exc
    version=document['version']
    if (not isinstance(version,str) or parse_version(version) is None
            or version!='.'.join(map(str,parse_version(version))) or version!=release_version):
        raise UpdateVerificationError('Release version does not match the manifest.')
    if (type(document['schema']) is not int or document['schema']!=1
            or type(document['minimum_updater_protocol']) is not int
            or not 1<=document['minimum_updater_protocol']<=PROTOCOL
            or document['application']!='Phase Studio' or document['repository']!=REPOSITORY
            or document['channel']!='stable' or document['os']!='windows' or document['arch']!='x64'):
        raise UpdateVerificationError('Unsupported release compatibility metadata.')
    records=document['assets']
    if not isinstance(records,list) or len(records)!=2:
        raise UpdateVerificationError('Both distribution profiles are required.')
    assets=[]
    for profile,name in zip(PROFILES,(f'PhaseStudio-{version}-x64.exe',f'PhaseStudio-Jana2020-{version}.zip')):
        matches=[item for item in records if isinstance(item,dict) and item.get('profile')==profile]
        if len(matches)!=1:
            raise UpdateVerificationError('Missing or duplicate distribution profile.')
        item=matches[0]
        if (set(item)!={'profile','name','size','sha256'} or item['name']!=name
                or type(item['size']) is not int or not 0<item['size']<=MAX_PACKAGE_BYTES
                or not isinstance(item['sha256'],str) or re.fullmatch('[0-9a-f]{64}',item['sha256']) is None):
            raise UpdateVerificationError('Invalid release asset metadata.')
        assets.append(UpdateAsset(profile,name,item['size'],item['sha256']))
    return VerifiedManifest(version,key_id,tuple(assets),hashlib.sha256(raw).hexdigest())
