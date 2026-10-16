"""Public stable-release metadata only; independent of authenticated API clients."""
from dataclasses import dataclass
import http.client
import json
import re
import ssl

from .version import VERSION

REPOSITORY = 'ji-ze/Phase-Studio'
RELEASES_URL = f'https://github.com/{REPOSITORY}/releases'
API_HOST = 'api.github.com'
API_PATH = f'/repos/{REPOSITORY}/releases/latest'
CHECK_INTERVAL = 24 * 60 * 60
REQUEST_TIMEOUT = 4.0  # Applied to connection and response socket operations.
MAX_RESPONSE_BYTES = 256 * 1024
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

    @property
    def label(self):
        return '.'.join(map(str, self.version))


def release_from_json(data):
    if not isinstance(data, dict) or data.get('draft') is not False or data.get('prerelease') is not False:
        return None
    version = parse_version(data.get('tag_name'))
    return Release(version) if version is not None else None


def is_newer(release, installed=VERSION):
    current = parse_version(installed)
    return current is not None and release.version > current


def fetch_latest_release(connection_factory=None):
    """One bounded HTTPS GET. No redirects, cookies, auth, project data or retries.

    http.client deliberately bypasses any authenticated urllib opener installed
    by another subsystem. Only an allowlisted host/path and constant headers are
    sent. A failure has no technical text suitable for the normal GUI.
    """
    factory = connection_factory or http.client.HTTPSConnection
    connection = None
    try:
        connection = factory(API_HOST, timeout=REQUEST_TIMEOUT, context=ssl.create_default_context())
        connection.request('GET', API_PATH, headers={
            'User-Agent': f'PhaseStudio/{VERSION}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        })
        response = connection.getresponse()
        if response.status != 200:
            return None
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            return None
        return release_from_json(json.loads(raw.decode('utf8')))
    except (OSError, http.client.HTTPException, ValueError, UnicodeError):
        return None
    finally:
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass
