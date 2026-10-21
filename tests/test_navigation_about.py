import os
from pathlib import Path
import subprocess
import sys
import pytest


def test_account_credential_storage_and_connection_are_independent():
    import hashlib
    from phase_studio.credentials import CredentialStore
    from phase_studio.sharped_access import account_state
    from phase_studio.sharped_server_client import DEFAULT_SERVER_URL

    class Backend:
        values = {}

        def read(self, origin):
            return self.values.get(origin, '')

        def write(self, origin, value):
            self.values[origin] = value

        def delete(self, origin):
            self.values.pop(origin, None)

    store = CredentialStore(backend=Backend())
    assert account_state(store)[:2] == ('Not configured', 'Not checked')
    token = 'mock-persisted-key'
    store.set(token, remember=True)
    assert account_state(store)[:2] == ('Securely stored', 'Not checked')
    assert account_state(CredentialStore(backend=store.backend))[:2] == ('Securely stored', 'Not checked')
    fingerprint = hashlib.sha256(token.encode()).hexdigest()
    for status, connection in (('Connected', 'Connected · Authorization verified'),
                               ('Connection unavailable', 'Unavailable'), ('Checking', 'Checking')):
        store._access_verification = {DEFAULT_SERVER_URL: (fingerprint, status)}
        assert account_state(store)[:2] == ('Securely stored', connection)
        assert token not in repr(account_state(store))
    store._access_verification = {DEFAULT_SERVER_URL: (fingerprint, 'Authentication expired')}
    assert account_state(store)[:2] == ('Invalid or rejected', 'Authentication rejected or expired')
    assert account_state(store, entered_token='mock-replacement')[:2] == ('Available for the current session', 'Not checked')
    assert store.get() == token


@pytest.mark.parametrize('scale', ['1', '1.25', '1.5'])
def test_navigation_about_acceptance(scale):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, 'packaging/tools/capture_navigation_about_205.py'], cwd=root,
        env=os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_SCALE_FACTOR': scale},
        capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
