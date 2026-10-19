"""Validate and extract a verified Jana package into a new staging directory.

This module never writes to an installed application or scientific project.
"""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import zipfile

from .update_manifest import UpdateAsset,UpdateVerificationError

MAX_EXTRACTED_BYTES=2*1024*1024*1024
MAX_FILES=20000
_RESERVED=re.compile(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',re.I)


def verify_package(path: Path,asset: UpdateAsset) -> None:
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size!=asset.size:
        raise UpdateVerificationError('Downloaded package size does not match.')
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
    if digest.hexdigest()!=asset.sha256:
        raise UpdateVerificationError('Downloaded package checksum does not match.')


def _members(archive: zipfile.ZipFile,version: str):
    root=f'PhaseStudio-Jana2020-{version}'
    entries=archive.infolist()
    if not entries or len(entries)>MAX_FILES:
        raise UpdateVerificationError('Invalid package inventory.')
    seen={};total=0;files=[]
    for entry in entries:
        name=entry.filename
        if entry.orig_filename!=name:
            raise UpdateVerificationError('Archive path normalization is forbidden.')
        parts=PurePosixPath(name).parts
        if (not parts or parts[0]!=root or '\\' in name or '\x00' in name
                or name.startswith('/') or any(p in ('.','..') for p in name.split('/') if p)
                or any(p.endswith((' ','.')) or ':' in p or _RESERVED.fullmatch(p)
                    or any(ord(c)<32 for c in p) for p in parts)):
            raise UpdateVerificationError('Unsafe archive path.')
        if len(parts)<2:
            raise UpdateVerificationError('Unexpected archive root entry.')
        relative=PurePosixPath(*parts[1:])
        key=str(relative).casefold()
        if key in seen:
            raise UpdateVerificationError('Duplicate archive path.')
        seen[key]=entry.is_dir()
        mode=entry.external_attr>>16
        if stat.S_ISLNK(mode) or (entry.external_attr & 0xffff)&0x400:
            raise UpdateVerificationError('Archive links are forbidden.')
        if mode and stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR):
            raise UpdateVerificationError('Unsupported archive file type.')
        if parts[1]!='_internal' and not (len(parts)==2 and parts[1]=='Phase_studio.exe' and not entry.is_dir()):
            raise UpdateVerificationError('Unexpected application ownership boundary.')
        total+=entry.file_size
        if total>MAX_EXTRACTED_BYTES or entry.flag_bits&1:
            raise UpdateVerificationError('Unsupported package size or encryption.')
        if not entry.is_dir():files.append((entry,relative))
    for key in seen:
        for parent in PurePosixPath(key).parents:
            if str(parent)!='.' and seen.get(str(parent)) is False:
                raise UpdateVerificationError('Conflicting archive paths.')
    if 'phase_studio.exe' not in seen or not any(str(p).startswith('_internal/') for _,p in files):
        raise UpdateVerificationError('Package is missing the executable or runtime.')
    return files


def extract_jana_package(path: Path,destination: Path,asset: UpdateAsset,version: str) -> Path:
    """Require a fresh directory; inspect the complete inventory before extracting."""
    if asset.profile!='jana2020-onedir':
        raise UpdateVerificationError('Incorrect package profile.')
    verify_package(path,asset)
    destination=Path(destination)
    if destination.exists() or destination.is_symlink():
        raise UpdateVerificationError('Staging directory must be new.')
    try:
        with zipfile.ZipFile(path) as archive:
            files=_members(archive,version)
            destination.mkdir(parents=False)
            try:
                for entry,relative in files:
                    target=destination.joinpath(*relative.parts)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with archive.open(entry) as source,target.open('xb') as output:
                        shutil.copyfileobj(source,output,1024*1024)
                return destination
            except BaseException:
                # Only the fresh staging directory created above is owned here.
                shutil.rmtree(destination)
                raise
    except (zipfile.BadZipFile,OSError,RuntimeError) as exc:
        raise UpdateVerificationError('Package could not be safely extracted.') from exc
