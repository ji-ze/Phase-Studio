import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from phase_studio import update_windows as windows
from phase_studio.update_manifest import UpdateVerificationError

pytestmark=pytest.mark.skipif(os.name!='nt',reason='Native Windows process and job contract')


def test_process_identity_and_pid_reuse_guard():
    identity=windows.process_identity(os.getpid())
    assert identity.created>0 and Path(identity.executable).is_file()
    from dataclasses import replace
    with pytest.raises(UpdateVerificationError):windows.ProcessGuard(os.getpid(),replace(identity,created=identity.created+1))
    with windows.ProcessGuard(os.getpid(),identity) as guard:
        with pytest.raises(UpdateVerificationError,match='still running'):guard.wait(.001)


def test_inputs_cannot_be_modified_or_deleted_while_guarded(tmp_path):
    file=tmp_path/'signed-package.bin';file.write_bytes(b'verified package')
    guard=windows.PathGuards([file])
    try:
        assert file.read_bytes()==b'verified package'
        with pytest.raises(OSError):file.write_bytes(b'tampered')
        with pytest.raises(OSError):file.unlink()
    finally:guard.close()
    file.unlink()


def test_owned_restart_job_abort_does_not_kill_unrelated_process(tmp_path):
    unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],creationflags=subprocess.CREATE_NO_WINDOW)
    marker=tmp_path/'started'
    job=windows.RestartJob(sys.executable,['-c',
        'from pathlib import Path;import time;Path('+repr(str(marker))+').write_text("started");time.sleep(30)'],tmp_path)
    try:
        deadline=time.monotonic()+10
        while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
        assert marker.exists() and job.alive()
        job.abort()
        assert unrelated.poll() is None
    finally:
        job.abort();unrelated.terminate();unrelated.wait(timeout=10)


def test_job_can_release_successful_process(tmp_path):
    marker=tmp_path/'done'
    job=windows.RestartJob(sys.executable,['-c',
        'from pathlib import Path;import time;time.sleep(.2);Path('+repr(str(marker))+').write_text("healthy")'],tmp_path)
    job.commit()
    deadline=time.monotonic()+10
    while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
    assert marker.read_text()=='healthy'
