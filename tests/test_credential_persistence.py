"""Persistent manual keys survive configuration and transport failures."""
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from phase_studio.credentials import CredentialStore, WindowsCredentialBackend
from phase_studio.sharped_server_client import SharpEDServerClient, SharpEDServerError, DEFAULT_SERVER_URL

KEY = 'SYNTHETIC-PERSISTENCE-KEY'
OTHER = 'SYNTHETIC-REPLACEMENT-KEY'


class Backend:
    def __init__(self):
        self.values = {}
        self.fail = False

    def read(self, origin):
        if self.fail:
            raise OSError('mock secure storage unavailable')
        return self.values.get(origin, '')

    def write(self, origin, token):
        if self.fail:
            raise OSError('mock secure storage unavailable')
        self.values[origin] = token

    def delete(self, origin):
        self.values.pop(origin, None)


class Settings:
    def __init__(self, **values):
        self.values = values

    def value(self, key, default=None):
        return self.values.get(key, default)

    def remove(self, key):
        self.values.pop(key, None)

    def sync(self):
        pass


def test_default_save_restart_replace_and_explicit_remove():
    backend = Backend()
    store = CredentialStore(backend)
    store.set(KEY)
    restarted = CredentialStore(backend)
    assert restarted.get() == KEY
    restarted.save_input(OTHER)
    assert CredentialStore(backend).get() == OTHER
    restarted.remove()
    assert CredentialStore(backend).get() == ''


def test_empty_configuration_and_session_only_do_not_delete_saved_key():
    backend = Backend()
    store = CredentialStore(backend)
    store.set(KEY)
    store.save_input('')
    store.set('')
    assert store.get() == CredentialStore(backend).get() == KEY
    store.set(OTHER, remember=False)
    assert store.get() == OTHER
    assert CredentialStore(backend).get() == KEY


def test_existing_wincred_target_independent_of_version_exe_and_mode():
    assert WindowsCredentialBackend.target('https://jana.fzu.cz:443') == (
        'FZU/PhaseStudio/SharpED/02a521db7d35b875df402fb1368231394000deffad26098c4affe9e134f9f45c'
    )


def test_legacy_migration_writes_before_scrubbing_both_copies():
    backend = Backend()
    shared = Settings(**{'inputs/sharped_api_token': KEY, 'inputs/cycles': 3})
    legacy = Settings(api_token=KEY)
    assert CredentialStore(backend).load_settings(shared, legacy) == KEY
    assert CredentialStore(backend).get() == KEY
    assert shared.values == {'inputs/cycles': 3}
    assert not legacy.values


def test_failed_migration_retains_old_copy_and_retries_successfully():
    backend = Backend()
    backend.fail = True
    shared = Settings(**{'inputs/sharped_api_token': KEY})
    legacy = Settings(api_token=KEY)
    store = CredentialStore(backend)
    assert store.load_settings(shared, legacy) == KEY
    assert shared.value('inputs/sharped_api_token') == legacy.value('api_token') == KEY
    backend.fail = False
    assert store.load_settings(shared, legacy) == KEY
    assert CredentialStore(backend).get() == KEY
    assert not shared.values and not legacy.values


def test_secure_read_failure_is_retryable_not_cached_forever():
    backend = Backend()
    CredentialStore(backend).set(KEY)
    store = CredentialStore(backend)
    backend.fail = True
    assert store.get() == ''
    backend.fail = False
    assert store.get() == KEY


@pytest.mark.parametrize('failure', [URLError(TimeoutError('mock timeout')),
    HTTPError(DEFAULT_SERVER_URL, 503, 'mock unavailable', {}, io.BytesIO(b'mock failed upload'))])
def test_failed_upload_then_retry_uses_same_persisted_credential(failure):
    backend = Backend()
    CredentialStore(backend).set(KEY)
    store = CredentialStore(backend)
    client = SharpEDServerClient()
    calls = []

    def transport(request, **kwargs):
        calls.append(request.get_header('Authorization'))
        if len(calls) == 1:
            raise failure
        return io.BytesIO(b'{"success":true,"job_id":1,"token":"mock-job"}')

    with TemporaryDirectory() as directory, patch('phase_studio.sharped_server_client.urlopen', transport):
        path = Path(directory) / 'ochlor.xplor'
        path.write_bytes(b'XPLOR\x00\xff')
        with pytest.raises(SharpEDServerError):
            client.upload(path, store.get(), 'C', 'default', .2)
        store.save_input('')  # A configuration save after the failure.
        assert client.upload(path, CredentialStore(backend).get(), 'C', 'default', .2).job_id == 1
    assert calls == ['Bearer ' + KEY] * 2
    assert store.get() == CredentialStore(backend).get() == KEY


def test_invalid_unicode_key_cannot_replace_saved_credential():
    backend = Backend()
    store = CredentialStore(backend)
    store.set(KEY)
    with pytest.raises(SharpEDServerError):
        store.set('polluted σ instructions')
    assert store.get() == CredentialStore(backend).get() == KEY
