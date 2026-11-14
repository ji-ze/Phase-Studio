"""Opt-in real-result loading in source/frozen GUIs; never submit inference."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

_APPLICATION = None


def run(directory, configuration):
    target=Path(directory).resolve()
    existed=target.exists()
    try:
        return _run(directory,configuration)
    except Exception:
        import traceback
        from .error_reporting import sanitize_error_details
        report={'passed':False,'frozen':bool(getattr(sys,'frozen',False)),
                'details':sanitize_error_details(traceback.format_exc()),'inference_submitted_by_this_probe':False}
        if not existed and target.is_dir():
            (target/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
        from PySide6.QtWidgets import QApplication
        qt=QApplication.instance()
        if qt:
            for widget in qt.topLevelWidgets():widget.close()
            qt.processEvents()
        return 1


def _run(directory, configuration):
    global _APPLICATION
    import gemmi
    import numpy as np
    from PySide6.QtCore import QSettings,QRect
    from PySide6.QtGui import QScreen
    from PySide6.QtWidgets import QApplication
    from . import app as a
    from .map_quality import ResultCandidate,profile_definition,recommend_best_result
    from .result_selection import ResultSelectionDialog,create_result_preview_host
    target=Path(directory).resolve();target.mkdir(parents=True,exist_ok=False)
    spec=json.loads(Path(configuration).read_text(encoding='utf8'))
    os.environ['PHASE_STUDIO_STARTUP_PROBE']='1'
    qt=QApplication.instance() or QApplication([]);a.apply_phase_studio_style(qt)
    _APPLICATION=qt
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(target/'settings'))
    report={'frozen':bool(getattr(sys,'frozen',False)),'operation':'actual result-map reading and EDMA-derived structure GUI loading',
            'inference_submitted_by_this_probe':False,'records':[]}
    def forbidden(*args,**kwargs):raise AssertionError('GUI-loading probe must never submit inference or phasing')
    with patch.multiple(a.IterativeSuperflipPipelineQtGUI,load_settings=lambda self:None,
            save_settings=lambda self:None,refresh_sharped_models=lambda self:None), \
            patch.object(a,'run_sharped_deblur',forbidden),patch.object(a,'run_superflip_cycle',forbidden), \
            patch.object(a.SharpEDServerClient,'upload',forbidden),patch.object(a.SharpEDServerClient,'execute',forbidden), \
            patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,1920,1040)):
        for index,item in enumerate(spec['records']):
            mp=Path(item['map']);cif=Path(item['structure'])
            assert a.file_sha256(mp)==item['map_sha256'] and a.file_sha256(cif)==item['structure_sha256']
            xmap=a.read_xplor_map(mp);assert np.isfinite(xmap.data).all()
            atoms=a.parse_cif_atoms(cif)
            cell=gemmi.UnitCell(*xmap.cell);sg=gemmi.SpaceGroup(item['spacegroup'])
            ctx=a.ReferenceContext(cif,cif,cell,sg,sg.hm,item['composition'],[])
            rows=a.read_hkl(Path(item['input_hkl']),*a.reflection_columns_for_mode(item['mode'])[:2])
            validation=a.build_validation_context(rows,item['mode'],ctx,frozenset())
            metrics=a.compute_map_quality(xmap.data,xmap.grid,xmap.cell,xmap.axis_order,validation)
            model=cif.with_suffix('.m40')
            candidate=ResultCandidate(item.get('cycle',1),'deblurred',str(mp),str(cif),metrics,usable_structure=bool(atoms),
                map_sha256=item['map_sha256'],structure_sha256=item['structure_sha256'],
                candidate_id=f"live-{item['job_id']}-{item['map_sha256'][:16]}",run_id=f"live-job-{item['job_id']}",
                sharped_model=item['model'],edma_sigma=item['threshold'],detected_atom_count=len(atoms),
                jana_model_path=str(model) if model.is_file() else '',jana_model_sha256=a.file_sha256(model) if model.is_file() else '',
                jana_model_site_count=a._m40_model_count(model) if model.is_file() else None,
                reflection_input_provenance='Actual source reflection file SHA-256 '+a.file_sha256(Path(item['input_hkl'])))
            backend=a.IterativeSuperflipPipelineQtGUI();backend.timer.stop()
            recommendation=recommend_best_result(validation.profile,[candidate])
            selector=ResultSelectionDialog(backend,[],[candidate],validation.profile,profile_definition(validation.profile),
                recommend_best_result(validation.profile,[]),recommendation,superflip_tab_available=False,
                sharped_tab_available=True,initial_source='deblurred',map_feedback_intensity_enabled=False,jana_context=False,
                preview_host=create_result_preview_host(backend,cell,30,-60),parse_structure=a.parse_cif_atoms,
                reference_atoms=[],source_title=a.result_source_title)
            selector._rotate_timer.stop();selector._auto_rotate_enabled=False
            selector.setWindowTitle(f"Live SharpED result {item['job_id']} — {item['dataset']} — {item['model']}")
            selector.resize(1600,1000);selector.show()
            for _ in range(20):qt.processEvents()
            assert selector.preview_candidate_id==candidate.candidate_id or not atoms
            rendered=len(selector._resolved_preview.atoms) if selector._resolved_preview else 0
            assert rendered>0 if atoms else rendered==0
            assert selector.grab().save(str(target/f"{index:02d}-job-{item['job_id']}.png"))
            assert a.file_sha256(mp)==item['map_sha256'] and a.file_sha256(cif)==item['structure_sha256']
            report['records'].append({'job_id':item['job_id'],'dataset':item['dataset'],'model':item['model'],
                'map_sha256':item['map_sha256'],'structure_sha256':item['structure_sha256'],
                'loaded_values':int(xmap.data.size),'dimensions':[int(xmap.grid[i]) for i in (0,3,6)],
                'source_cif_sites':len(atoms),'rendered_atoms':rendered,
                'metric_unavailable_reason':metrics.unavailable_reason,'has_density_variation':bool(np.std(xmap.data)>0),
                'candidate_identity_verified':True,'source_files_unchanged':True,'passed':True})
            selector.close();backend.close();qt.processEvents()
    report['passed']=bool(report['records']) and all(r['passed'] for r in report['records'])
    (target/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    from matplotlib import pyplot as plt
    plt.close('all');qt.processEvents()
    return 0 if report['passed'] else 1
