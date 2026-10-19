"""Bounded public update downloads without authenticated application clients."""
from __future__ import annotations

import http.client
from pathlib import Path
import ssl
import threading
from urllib.parse import urljoin,urlsplit

from .update_checker import REPOSITORY
from .update_manifest import MAX_PACKAGE_BYTES,UpdateVerificationError

TIMEOUT=15
CHUNK=256*1024
CDN_HOSTS=frozenset({'release-assets.githubusercontent.com','objects.githubusercontent.com',
    'github-releases.githubusercontent.com'})


class DownloadCancelled(Exception):
    pass


def validate_download_url(value: str,*,initial: bool=True) -> str:
    try:
        url=urlsplit(value)
        if (url.scheme!='https' or url.username is not None or url.password is not None
                or url.port not in (None,443) or url.fragment or '\\' in value):
            raise ValueError
        if url.hostname=='github.com':
            if not url.path.startswith(f'/{REPOSITORY}/releases/download/') or url.query:
                raise ValueError
        elif initial or url.hostname not in CDN_HOSTS:
            raise ValueError
        return value
    except (ValueError,TypeError,AttributeError) as exc:
        raise UpdateVerificationError('Unapproved update download URL.') from exc


def download(url: str,destination: Path,*,expected_size: int,
             cancel: threading.Event | None=None,progress=None,connection_factory=None) -> Path:
    """Create a fresh partial file and publish it only after exact length checks.

    Signature/hash verification remains mandatory after this transport step.
    Redirects receive only constant public headers, never SharpED credentials.
    """
    if type(expected_size) is not int or not 0<expected_size<=MAX_PACKAGE_BYTES:
        raise UpdateVerificationError('Invalid expected download size.')
    validate_download_url(url)
    destination=Path(destination)
    partial=destination.with_name(destination.name+'.part')
    if destination.exists() or destination.is_symlink() or partial.exists() or partial.is_symlink():
        raise UpdateVerificationError('Download destination must be new.')
    factory=connection_factory or http.client.HTTPSConnection
    created=False
    try:
        for redirect in range(6):
            if cancel is not None and cancel.is_set():raise DownloadCancelled()
            validate_download_url(url,initial=redirect==0)
            parsed=urlsplit(url)
            connection=factory(parsed.hostname,timeout=TIMEOUT,context=ssl.create_default_context())
            try:
                path=parsed.path+('?' + parsed.query if parsed.query else '')
                connection.request('GET',path,headers={'User-Agent':'PhaseStudio-Updater/1',
                    'Accept':'application/octet-stream','Accept-Encoding':'identity'})
                response=connection.getresponse()
                if response.status in (301,302,303,307,308):
                    target=response.getheader('Location')
                    if not target:raise UpdateVerificationError('Update redirect is missing.')
                    url=urljoin(url,target)
                    continue
                if response.status!=200:
                    raise UpdateVerificationError('Update download is unavailable.')
                length=response.getheader('Content-Length')
                if length is not None and int(length)!=expected_size:
                    raise UpdateVerificationError('Update download size differs from release metadata.')
                if response.getheader('Content-Encoding') not in (None,'identity'):
                    raise UpdateVerificationError('Unexpected download encoding.')
                received=0
                with partial.open('xb') as output:
                    created=True
                    while True:
                        if cancel is not None and cancel.is_set():raise DownloadCancelled()
                        chunk=response.read(min(CHUNK,expected_size-received+1))
                        if not chunk:break
                        received+=len(chunk)
                        if received>expected_size:
                            raise UpdateVerificationError('Update download exceeds its declared size.')
                        output.write(chunk)
                        if progress is not None:progress(received,expected_size)
                if received!=expected_size:
                    raise UpdateVerificationError('Update download was interrupted.')
                # Hard-link creation never replaces a concurrently created target.
                import os
                os.link(partial,destination)
                partial.unlink()
                return destination
            finally:
                connection.close()
        raise UpdateVerificationError('Too many update redirects.')
    except (OSError,http.client.HTTPException,ValueError) as exc:
        if isinstance(exc,UpdateVerificationError):raise
        raise UpdateVerificationError('Update download failed; installation is unchanged.') from exc
    finally:
        if created:partial.unlink(missing_ok=True)
