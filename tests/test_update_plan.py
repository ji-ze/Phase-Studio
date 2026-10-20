"""Real Windows DPAPI and bounded startup acknowledgement, no real credentials."""
import json
import os
import uuid
from pathlib import Path

import pytest

from phase_studio import update_plan as plans,update_health as health
from phase_studio.update_manifest import UpdateVerificationError

pytestmark=pytest.mark.skipif(os.name!='nt',reason='Windows DPAPI')


def test_dpapi_plan_roundtrip_tamper_and_location(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    folder=plans.workspace_root()/str(uuid.uuid4());folder.mkdir(parents=True)
    document={'schema':1,'session':folder.name,'target':'controlled mock target'}
    path=plans.write_plan(folder,document)
    assert b'controlled mock target' not in path.read_bytes()
    assert plans.read_plan(path)==document
    with pytest.raises(FileExistsError):plans.write_plan(folder,document)
    copy=tmp_path/'update.psupdate';copy.write_bytes(path.read_bytes())
    with pytest.raises(UpdateVerificationError):plans.read_plan(copy)
    data=bytearray(path.read_bytes());data[-1]^=1;path.write_bytes(data)
    with pytest.raises(UpdateVerificationError):plans.read_plan(path)


def test_health_requires_visible_window_and_private_workspace(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));monkeypatch.setattr(health,'_pending',None)
    folder=plans.workspace_root()/str(uuid.uuid4());folder.mkdir(parents=True)
    path=folder/'startup.json';arguments=['PhaseStudio.exe','--update-health',str(path)]
    health.consume(arguments);assert arguments==['PhaseStudio.exe']
    class Window:
        shown=False
        def isVisible(self):return self.shown
    window=Window();health.visible(window);assert not path.exists()
    window.shown=True;health.visible(window)
    assert json.loads(path.read_text())['pid']==os.getpid()
    original=path.read_bytes();health.visible(window);assert path.read_bytes()==original
    with pytest.raises(ValueError):health.consume(['app','--update-health',str(tmp_path/'project.json')])
