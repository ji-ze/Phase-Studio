"""Capture actual selector widgets with explicit file-backed scientific/UI fixtures.
No external jobs, Jana publication or network; fixture metrics are supplied.
"""
import os,sys,json
import numpy as np
from pathlib import Path
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from phase_studio import app as engine
if len(sys.argv)>1 and sys.argv[1]=='before':
    import importlib.util
    spec=importlib.util.spec_from_file_location('selector_baseline',ROOT/'build/result-204-before.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    engine.ResultSelectionDialog=module.ResultSelectionDialog
    engine.ResultSelectionDialog.selection_state=lambda self:{}
    engine.ResultSelectionDialog.restore_selection=lambda self,state:None
    engine.ResultSelectionDialog.set_fallback_message=lambda self,message:self._warning_callout.setText(message)
from test_result_selection_redesign import ResultSelectionRedesignTests
from test_result_selection_viewer import large_cif
from phase_studio.ui_style import apply_phase_studio_style
from phase_studio.app import seal_result_candidate
from types import SimpleNamespace
ResultSelectionRedesignTests.setUpClass()
fixture=ResultSelectionRedesignTests('test_family_selection_warning_and_authoritative_model_count')
fixture.setUp();d=fixture.dialog;qt=fixture.qtapp
apply_phase_studio_style(qt)
out=ROOT/'docs/screenshots/2.0.4-result-selection'/(sys.argv[1] if len(sys.argv)>1 else 'after')/('scale-'+os.environ.get('QT_SCALE_FACTOR','1'))
out.mkdir(parents=True,exist_ok=True)

def capture(name,width=1500,height=900):
    d.resize(width,height);fixture.events();d._request_preview_fit();d._preview_canvas.draw();fixture.events()
    image=d.grab();image.save(str(out/(name+'.png')))
    candidate=d.selected_candidate
    from mpl_toolkits.mplot3d import proj3d
    axis=d._preview_figure.axes[0]
    points=d._preview_fit_coords
    x,y,_=proj3d.proj_transform(*points.T,axis.get_proj())
    pixels=axis.transData.transform(np.column_stack((x,y)))
    viewport=axis.get_position(original=True).transformed(axis.figure.transFigure)
    fraction=float(max(np.ptp(pixels,axis=0)/[viewport.width,viewport.height]))
    if not (len(sys.argv)>1 and sys.argv[1]=='before'):
        assert .70 <= fraction <= .85,(name,fraction)
        assert np.all(pixels.min(axis=0)>[viewport.x0,viewport.y0]),name
        assert np.all(pixels.max(axis=0)<[viewport.x1,viewport.y1]),name
        assert d._footer.geometry().bottom()<d.height(),name
    for path,digest in ((candidate.map_path,candidate.map_sha256),(candidate.structure_path,candidate.structure_sha256),(candidate.jana_model_path,candidate.jana_model_sha256)):
        if digest:assert engine.file_sha256(Path(path))==digest,(name,path)
    (out/(name+'.json')).write_text(json.dumps(dict(logical_size=[d.width(),d.height()],device_pixel_ratio=image.devicePixelRatio(),source=d.active_source,cycle=candidate.cycle,threshold=candidate.edma_sigma,edma_sites=candidate.detected_atom_count,jana_sites=candidate.jana_model_site_count,map_sha256=candidate.map_sha256,model_sha256=candidate.jana_model_sha256,canvas=[d._preview_canvas.width(),d._preview_canvas.height()],projected_fill=fraction),indent=2),encoding='utf8')

def install_shape(name,text):
    candidate=d.selected_candidate
    path=Path(candidate.structure_path).parent/(name+'.cif')
    path.write_text(text,encoding='utf8')
    # Reuse the existing validated two-site fixture model. This intentionally
    # demonstrates distinct candidate/model counts; no handoff is executed.
    path.with_suffix('.m40').write_bytes(Path(candidate.jana_model_path).read_bytes())
    updated=seal_result_candidate(replace(candidate,structure_path=str(path)))
    view=d._views[d.active_source];row=view.table.currentRow();view.ordered[row]=updated;view.selected=updated
    d._render_preview(updated);d._sync_action_button()

try:
    if '--real-only' not in sys.argv:
        capture('00-default-structure-prediction')
        d._superflip_btn.setChecked(True);capture('01-charge-flipping-recommended')
        d._sharped_btn.setChecked(True);capture('02-sharped-recommended')
        d._views['deblurred'].table.selectRow(0);capture('03-sharped-manual')
        text=large_cif(24)
        start=text.index('C1 C ')
        text=text[:start]+'\n'.join(f'C{i+1} C {(.08+i*.032):.6f} .200 .200' for i in range(24))+'\n'
        install_shape('elongated',text);capture('04-elongated')
        install_shape('dense',large_cif(40));capture('05-dense')
        d._cell_button.setChecked(True);capture('06-full-cell')
        d._molecule_button.setChecked(True);capture('07-complete-molecules')
        pending=[]
        def request(c,add,callback):
            req=SimpleNamespace(threshold=.4);pending.append((c,callback,req));return req
        d._adjust_threshold_async=request;d._change_threshold(True);capture('08-threshold-pending')
        original,callback,req=pending[-1]
        path=Path(original.structure_path).parent/'completed-threshold.cif'
        path.write_text(large_cif(44),encoding='utf8')
        path.with_suffix('.m40').write_bytes(Path(original.jana_model_path).read_bytes())
        updated=seal_result_candidate(replace(original,edma_sigma=.4,structure_path=str(path)))
        callback(updated,None,req);capture('09-threshold-completed')
        capture('10-edma-jana-counts')
        d._superflip_btn.setChecked(True);capture('11-family-switch-superflip')
        d._sharped_btn.setChecked(True);capture('12-family-switch-sharped')
        capture('13-selected-summary')
        capture('14-laptop',1280,720)
        capture('15-reduced',1100,640)
        d._sharped_btn.setChecked(True)
        d._views['deblurred'].selected=None
        d._apply_source('deblurred')
        d.grab().save(str(out/'18-no-candidate.png'))
        d._superflip_btn.setChecked(True)
        d.set_fallback_message('SharpED has no completed result. Select a completed charge-flipping solution.')
        capture('19-superflip-fallback')
    real_capture_path=os.environ.get('PHASE_STUDIO_CAPTURE_PROJECT_CYCLE')
    real_root=Path(real_capture_path) if real_capture_path else None
    if real_root is not None and real_root.is_dir():
        import csv
        from dataclasses import fields
        from phase_studio.map_quality import MapQualityMetrics, ResultCandidate, ValidationProfile, profile_definition, recommend_best_result
        from phase_studio.result_selection import create_result_preview_host
        records=list(csv.DictReader((real_root.parent/'metrics.csv').open(encoding='utf8')))
        candidates={'superflip':[], 'deblurred':[]}
        for row in records:
            values={}
            for field in fields(MapQualityMetrics):
                value=row.get(field.name,'')
                if value:
                    values[field.name]=(value if field.name=='unavailable_reason' else
                        int(value) if field.name.startswith('n_') else float(value))
            source='superflip' if row['source']=='superflip' else 'deblurred'
            c=seal_result_candidate(ResultCandidate(int(row['cycle']),source,row['map_path'],
                row['structure_path'],MapQualityMetrics(**values),edma_sigma=.5,
                superflip_initialization=('Previous SharpED XPLOR' if row['model_source']=='deblurred_xplor' else 'No model file'),
                reflection_input_provenance='Existing output; reflection provenance not recorded'))
            candidates[source].append(c)
        old=d
        cell,_,_=engine.parse_cif_cell_and_sg(Path(candidates['superflip'][0].structure_path))
        host=create_result_preview_host(fixture.backend,cell,20.,35.)
        profile=ValidationProfile.REFERENCE_FREE
        d=engine.ResultSelectionDialog(fixture.backend,candidates['superflip'],candidates['deblurred'],
            profile,profile_definition(profile),recommend_best_result(profile,candidates['superflip']),
            recommend_best_result(profile,candidates['deblurred']),superflip_tab_available=True,
            sharped_tab_available=True,initial_source='deblurred',map_feedback_intensity_enabled=False,
            jana_context=True,preview_host=host,parse_structure=fixture.backend._safe_parse_structure,
            reference_atoms=[],source_title=engine.result_source_title)
        old.close();old.deleteLater();fixture.dialog=d
        d._rotate_timer.stop();d._auto_rotate_button.setChecked(False);d.show();fixture.events()
        capture('20-real-project-default')
        for source,label in (('deblurred','16-real-project-sharped'),('superflip','17-real-project-superflip')):
            (d._sharped_btn if source=='deblurred' else d._superflip_btn).setChecked(True)
            d._views[source].table.selectRow(len(d._views[source].ordered)-1)
            capture(label)

finally:
    fixture.tearDown();ResultSelectionRedesignTests.tearDownClass()
