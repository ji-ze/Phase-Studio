"""Public stable-release metadata only; independent of authenticated API clients."""
from dataclasses import dataclass
import http.client
import json
import re
import ssl
import logging
import time
from datetime import datetime
from urllib.parse import urlsplit, unquote

from .version import VERSION

REPOSITORY = 'ji-ze/Phase-Studio'
RELEASES_URL = f'https://github.com/{REPOSITORY}/releases'
API_HOST = 'api.github.com'
API_PATH = f'/repos/{REPOSITORY}/releases?per_page=100'
CHECK_INTERVAL = 24 * 60 * 60
REQUEST_TIMEOUT = 4.0  # Applied to connection and response socket operations.
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_PAGES = 5
RETRY_INTERVAL = 15 * 60
_VERSION = re.compile(r'[vV]?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?', re.ASCII)


def parse_version(value):
    """Stable SemVer only: optional tag prefix/build metadata, no prereleases."""
    if not isinstance(value, str) or len(value) > 128:
        return None
    match = _VERSION.fullmatch(value)
    return tuple(map(int, match.group(1, 2, 3))) if match else None


@dataclass(frozen=True)
class Release:
    version: tuple
    url: str = RELEASES_URL

    @property
    def label(self):
        return '.'.join(map(str, self.version))


def validated_release_url(value, tag=None, version=None):
    """Accept only the official repository's release page, never asset URLs."""
    try:
        url = urlsplit(value if isinstance(value,str) else '')
        prefix = f'/{REPOSITORY}/releases/tag/'
        if (url.scheme=='https' and url.netloc=='github.com' and not url.query and not url.fragment
                and url.path.startswith(prefix) and url.path[len(prefix):]
                and (tag is None or unquote(url.path[len(prefix):])==tag)
                and (version is None or parse_version(unquote(url.path[len(prefix):]))==version)):
            return url.geturl()
    except ValueError:
        pass
    return RELEASES_URL


def release_from_json(data):
    if not isinstance(data, dict) or data.get('draft') is not False or data.get('prerelease') is not False:
        return None
    version = parse_version(data.get('tag_name'))
    return Release(version,validated_release_url(data.get('html_url'),data.get('tag_name'))) if version is not None else None


def is_newer(release, installed=VERSION):
    current = parse_version(installed)
    if current is None and isinstance(installed, str):
        # Stable releases supersede prereleases of the same numeric version.
        # Prerelease GitHub assets remain excluded by release_from_json.
        prerelease = re.fullmatch(
            r'[vV]?((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))-'
            r'(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)'
            r'(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*'
            r'(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?', installed, re.ASCII)
        if prerelease is not None:
            return release.version >= parse_version(prerelease.group(1))
    return current is not None and release.version > current


@dataclass(frozen=True)
class CheckResult:
    release: Release | None = None
    error: str = ''
    retry_after: int = 0
    detail: str = ''


def fetch_release_check(connection_factory=None):
    """Bounded public HTTPS pages; select highest published stable SemVer.

    http.client deliberately bypasses any authenticated urllib opener installed
    by another subsystem. Only an allowlisted host/path and constant headers are
    sent. A failure has no technical text suitable for the normal GUI.
    """
    factory = connection_factory or http.client.HTTPSConnection
    best = None
    invalid_tags = False
    try:
        for page in range(1,MAX_PAGES+1):
            connection = factory(API_HOST, timeout=REQUEST_TIMEOUT, context=ssl.create_default_context())
            try:
                connection.request('GET', API_PATH+f'&page={page}', headers={
                    'User-Agent': f'PhaseStudio/{VERSION}',
                    'Accept': 'application/vnd.github+json',
                    'X-GitHub-Api-Version': '2022-11-28',
                })
                response = connection.getresponse()
                if response.status != 200:
                    header=getattr(response,'getheader',lambda _key:None)
                    limited=response.status==429 or response.status==403 and header('X-RateLimit-Remaining')=='0'
                    try:
                        retry=int(header('Retry-After') or 0)
                        retry=max(retry,int(float(header('X-RateLimit-Reset') or 0)-time.time()) if limited else 0)
                    except (ValueError,TypeError,OverflowError):retry=0
                    return CheckResult(error='rate-limit' if limited else 'service',retry_after=min(CHECK_INTERVAL,max(0,retry)),detail=f'HTTP {response.status}')
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw)>MAX_RESPONSE_BYTES:
                    return CheckResult(error='metadata-size')
                data=json.loads(raw.decode('utf8'))
                if not isinstance(data,list):return CheckResult(error='metadata-schema')
                for item in data:
                    if not isinstance(item,dict):return CheckResult(error='metadata-schema')
                    if not isinstance(item.get('draft'),bool) or not isinstance(item.get('prerelease'),bool):
                        return CheckResult(error='metadata-schema')
                    if item.get('draft') is not False or item.get('prerelease') is not False:
                        continue
                    if 'published_at' not in item:return CheckResult(error='metadata-schema')
                    if not item.get('published_at'):continue
                    try:
                        published=item['published_at']
                        if not isinstance(published,str) or datetime.fromisoformat(published.replace('Z','+00:00')).tzinfo is None:
                            return CheckResult(error='metadata-publication')
                    except ValueError:return CheckResult(error='metadata-publication')
                    release=release_from_json(item)
                    if release is None:invalid_tags=True
                    elif best is None or release.version>best.version:best=release
                if len(data)<100:
                    return CheckResult(best,error='metadata-version' if invalid_tags and best is None else '')
            finally:
                try:connection.close()
                except OSError:pass
        return CheckResult(error='metadata-pagination')
    except (OSError, http.client.HTTPException) as exc:
        return CheckResult(error='network',detail=type(exc).__name__)
    except (ValueError, UnicodeError):
        return CheckResult(error='metadata-json')


def fetch_latest_release(connection_factory=None):
    """Compatibility adapter for callers which only need a release or None."""
    result=fetch_release_check(connection_factory)
    if result.error:logging.getLogger(__name__).warning('GitHub release check failed: %s',result.error)
    return result.release if not result.error else None
