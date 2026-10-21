"""OAuth grants persist independently of manual keys, without extending expiry."""
import json
import os
import subprocess
import sys
import time
from unittest.mock import patch

import pytest

from phase_studio.credentials import CredentialStore, credential_origin
from phase_studio.oauth import OAuthCredential, SCOPE
from phase_studio.error_reporting import build_error_report


TOKEN = 'SYNTHETIC-CACHED-OAUTH-NOT-A-REAL-TOKEN'


class Backend:
    def __init__(self):
        self.values = {}
    def read(self, target):
        return self.values.get(target, '')
    def write(self, target, value):
        self.values[target] = value
    def delete(self, target):
        self.values.pop(target, None)


def grant(backend):
    store = CredentialStore(backend)
    assert store.get() == ''
    store.activate_oauth(OAuthCredential(TOKEN, time.monotonic()+900))
    assert not store.oauth_storage_error
    return store


def test_new_store_restores_once_and_registers_redaction():
    backend = Backend()
    first = grant(backend)
    record = json.loads(backend.read(first.oauth_target()))
    assert record['expires_at_utc'] <= time.time()+900
    with patch('phase_studio.credentials.time.monotonic', return_value=42):
        second = CredentialStore(backend)
        assert second.authentication_method() == 'oauth'
        assert second.get() == TOKEN
        assert 42+60 < second._oauth.expires_at <= 42+900
        assert second._oauth.usable(now=42)
    assert TOKEN not in build_error_report(RuntimeError(TOKEN)).diagnostic_block()
    assert TOKEN not in repr(second._oauth)


@pytest.mark.parametrize('field,value', [
    ('schema', True), ('issuer', 'https://other.invalid'),
    ('resource', 'https://other.invalid'), ('client_id', 'other-app'),
    ('scope', 'other'), ('access_token', 'invalid\nheader'),
    ('expires_at_utc', float('nan')), ('expires_at_utc', float('inf')),
    ('expires_at_utc', True), ('expires_at_utc', 0),
    ('expires_at_utc', 10**1000),
    ('saved_at_utc', time.time()+3600), ('expires_at_utc', time.time()+7200)])
def test_corrupt_or_wrong_origin_cache_is_not_used_or_silently_deleted(field, value):
    backend = Backend()
    store = grant(backend)
    record = json.loads(backend.read(store.oauth_target()))
    record[field] = value
    backend.write(store.oauth_target(), json.dumps(record))
    assert CredentialStore(backend).get() == ''
    assert backend.read(store.oauth_target())


@pytest.mark.parametrize('raw', ['', 'not json', '[]', '{"schema":1}', 'null', '['*1100+']'*1100])
def test_missing_or_malformed_cache(raw):
    backend = Backend()
    backend.write(CredentialStore.oauth_target(), raw)
    assert CredentialStore(backend).authentication_method() == 'manual'


def test_expiration_margin_and_clock_rollback():
    backend = Backend()
    store = grant(backend)
    record = json.loads(backend.read(store.oauth_target()))
    with patch('phase_studio.credentials.time.time', return_value=record['expires_at_utc']-30):
        assert CredentialStore(backend).get() == ''
    with patch('phase_studio.credentials.time.time', return_value=record['saved_at_utc']-1):
        assert CredentialStore(backend).get() == ''


def test_manual_key_separate_logout_and_session_only_choice():
    backend = Backend()
    manual_origin = credential_origin('https://jana.fzu.cz')
    backend.write(manual_origin, 'SYNTHETIC-MANUAL-KEY')
    store = grant_with_manual = CredentialStore(backend)
    store.activate_oauth(OAuthCredential(TOKEN, time.monotonic()+900))
    restored = CredentialStore(backend)
    assert restored.get() == TOKEN
    restored.sign_out_oauth()
    assert CredentialStore(backend).get() == 'SYNTHETIC-MANUAL-KEY'
    grant_with_manual.activate_oauth(OAuthCredential(TOKEN, time.monotonic()+900), remember=False)
    assert grant_with_manual.get() == TOKEN
    assert backend.read(manual_origin) == 'SYNTHETIC-MANUAL-KEY'
    assert not backend.read(store.oauth_target())


def test_server_rejection_invalidates_only_matching_oauth_grant():
    backend = Backend()
    store = grant(backend)
    store.reject_oauth('retired-token')
    assert CredentialStore(backend).get() == TOKEN
    store.reject_oauth(TOKEN)
    assert not store._oauth.usable()
    assert CredentialStore(backend).get() == ''


def test_storage_failure_leaves_session_usable_and_reports_fixed_nonsecret_state():
    backend = Backend()
    backend.write = lambda *args: (_ for _ in ()).throw(OSError('storage unavailable'))
    store = CredentialStore(backend)
    store.activate_oauth(OAuthCredential(TOKEN, time.monotonic()+900))
    assert store.get() == TOKEN and store.oauth_storage_error


def test_wall_deadline_is_not_extended_by_activation():
    backend = Backend()
    actual_deadline = time.time()+120
    store = CredentialStore(backend)
    store.activate_oauth(OAuthCredential(TOKEN, time.monotonic()+900, SCOPE, actual_deadline))
    assert json.loads(backend.read(store.oauth_target()))['expires_at_utc'] <= actual_deadline


@pytest.mark.skipif(os.name != 'nt', reason='Native current-user Windows Credential Manager')
def test_independent_windows_processes_share_secure_grant(tmp_path):
    script = ('from phase_studio.oauth_diagnostics import run_credential_check; '
              'import sys; raise SystemExit(run_credential_check(sys.argv[1], sys.argv[2]))')
    # This subprocess tests the real current-user Credential Manager. The
    # release workflow runs the parent pytest process with Qt offscreen; that
    # setting intentionally disables the app's default credential backend and
    # must not leak into this native integration test.
    child_env = os.environ.copy()
    child_env.pop('QT_QPA_PLATFORM', None)
    try:
        for phase in ('oauth-write', 'oauth-read'):
            output = tmp_path/(phase+'.json')
            process = subprocess.run([sys.executable, '-c', script, str(output), phase],
                capture_output=True, timeout=30, env=child_env)
            assert process.returncode == 0
            assert json.loads(output.read_text())['success']
            assert TOKEN not in output.read_text()
    finally:
        cleanup = subprocess.run([sys.executable, '-c', script,
            str(tmp_path/'remove.json'), 'oauth-remove'], capture_output=True, timeout=30, env=child_env)
        assert cleanup.returncode == 0
