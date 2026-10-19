"""Actual stored ochlor Cycle 1/2/3 data, read-only identity and Qt captures."""
import os,sys,json,tempfile,hashlib
from pathlib import Path
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QSettings,QRect
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication,QToolButton
from phase_studio import result_selection as ui,structure_camera as camera
from viewer_remediation_fixture_205 import real_candidates,make_dialog
scale=float(os.environ.get('QT_SCALE_FACTOR','1'))
OUT=ROOT/'build/acceptance-viewer-remediation-2.0.5'/('scale-'+str(scale));OUT.mkdir(exist_ok=True,parents=True)
qt=QApplication([])
from phase_studio.ui_style import apply_phase_studio_style
apply_phase_studio_style(qt)
candidates=real_candidates();records={}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
source_hashes={p:sha(p) for c in candidates for p in (c.map_path,c.structure_path,c.jana_model_path)}
def settle():
    for _ in range(15):qt.processEvents()
def capture(name,widget,d):
    settle()
    c=d.selected_candidate;s=d._resolved_preview
    expected=d._candidate_presentation(c)
    assert s.identity==d.selection_snapshot.identity
    assert np.array_equal(np.asarray(s.coordinates),expected[1])
    assert tuple((a.label,a.element,tuple(a.frac)) for a in expected[0])==s.atoms
    assert s.detected_count==c.detected_atom_count
    assert widget.grab().save(str(OUT/(name+'.png')))
    records[name]=dict(identity=s.identity,representation=s.representation,rendered_atoms=len(s.atoms),
        coordinate_sha256=hashlib.sha256(np.asarray(s.coordinates).tobytes()).hexdigest(),
        metadata=d._metadata_label.text(),threshold=d._threshold_status.text(),
        detected=c.detected_atom_count,asu=s.composition,jana_sites=c.jana_model_site_count,
        logical_size=widget.size().toTuple(),dpr=widget.devicePixelRatioF(),
        data='Actual stored ochlor '+c.run_id+' outputs, no inference or publication')
with tempfile.TemporaryDirectory() as temporary,patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,int(1920/scale),int(1080/scale))):
    settings=QSettings(str(Path(temporary)/'viewer.ini'),QSettings.IniFormat)
    ui.QSettings=lambda *args:settings;camera.QSettings=lambda *args:settings
    d=make_dialog(candidates);d._auto_rotate_button.setChecked(False);d.show();settle()
    for source in ('deblurred','superflip'):
        d._apply_source(source)
        for cycle in (2,1,3):
            d._views[source].table.selectRow(cycle-1);settle()
            for mode in ('molecule','cell'):
                d._set_view_mode(mode);settle()
                suffix=f'{source}-cycle{cycle}-{mode}'
                capture('selection-'+suffix,d,d)
                before=d._resolved_preview
                d._open_fullscreen();settle()
                detached=d._detached_viewer
                assert d._resolved_preview is before
                assert detached.candidate_identity==before.identity
                assert f'Cycle {cycle}' in detached.title_label.text()
                capture('fullscreen-'+suffix,detached,d)
                detached.close();settle()
                assert d.selected_candidate.cycle==cycle and d._resolved_preview is before
    # The original mismatch: navigate Cycle 2 -> 3 within the SAME detached host.
    d._apply_source('deblurred');d._views['deblurred'].table.selectRow(1);d._open_fullscreen();settle()
    d._step_cycle(1);settle()
    assert 'Cycle 3' in d._detached_viewer.title_label.text()
    assert d._detached_viewer.candidate_identity==d.selection_snapshot.identity
    capture('fullscreen-navigation-cycle3',d._detached_viewer,d)
    d._detached_viewer.close();settle()
    button=next(b for b in d.findChildren(QToolButton) if b.text()=='Camera')
    menu=button.menu();menu.popup(button.mapToGlobal(button.rect().bottomLeft()));settle()
    assert menu.grab().save(str(OUT/'camera-menu.png'));menu.hide()
    d._views['deblurred'].table.selectRow(1);settle();chosen=d.selected_candidate
    d.accept();d._views['deblurred'].table.selectRow(2);settle()
    assert d.selected_candidate==chosen
    records['frozen_handoff_selection']=dict(identity=d.selection_snapshot.identity,map=chosen.map_path,
        map_sha256=chosen.map_sha256,model=chosen.jana_model_path,model_sha256=chosen.jana_model_sha256)
    # A second REAL threshold is available only for run_0009 SharpED Cycle 2.
    # Never pair it with the run_0010 map.
    from dataclasses import replace
    from viewer_remediation_fixture_205 import REAL_RUN,engine
    prior=REAL_RUN.with_name('run_0009')
    alternate=next(prior.glob('review_edma/run_0009/sharped_cycle_002/request_*_0p60sigma/*_edma.cif'))
    c=next(c for c in real_candidates(prior) if c.source=='deblurred' and c.cycle==2)
    altered=engine.seal_result_candidate(replace(c,structure_path=str(alternate),edma_sigma=.6))
    for variant in (c,altered):
        for p in (variant.map_path,variant.structure_path,variant.jana_model_path):source_hashes[p]=sha(p)
        d=make_dialog([variant]);d._auto_rotate_button.setChecked(False);d.show();settle()
        d._open_fullscreen();settle()
        capture(f'real-run9-cycle2-threshold-{variant.edma_sigma:.2f}',d._detached_viewer,d)
        d._detached_viewer.close();d.close()
assert source_hashes=={p:sha(p) for p in source_hashes}
(OUT/'identity-evidence.json').write_text(json.dumps(dict(screenshots=records,unchanged_source_hashes=source_hashes),indent=2),encoding='utf8')
print('PASS real stored cycles/families/representations/fullscreen and frozen selection at',scale,flush=True)
