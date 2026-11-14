"""Capture actual Result Selection widgets; no phasing/inference or handoff."""
import os,sys,argparse,csv,json
from pathlib import Path
from dataclasses import replace,fields
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('stage');parser.add_argument('--source-root',type=Path,default=ROOT)
parser.add_argument('--run',type=Path);parser.add_argument('--diagnostics',type=Path)
args=parser.parse_args();sys.path[:0]=[str(args.source_root),str(args.source_root/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QDialog,QTabWidget
from PySide6.QtCore import QRect
from PySide6.QtGui import QScreen
from phase_studio import app as a
from phase_studio.map_quality import MapQualityMetrics
import test_jana_completion as fixture

out=ROOT/'build/feedback-selection207'/args.stage;out.mkdir(parents=True,exist_ok=True)
qt=QApplication([]);a.apply_phase_studio_style(qt)
with patch.multiple(a.IterativeSuperflipPipelineQtGUI,refresh_sharped_models=lambda self:None,
    load_settings=lambda self:None,save_settings=lambda self:None),patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,1920,1140)):
    backend,results=fixture.build_window(a,cycles=3);backend.timer.stop()
    backend.results=[replace(r,cycle=r.cycle+6,powder_repartition_avg_change_percent=None) for r in results]
    if args.diagnostics and not args.run:
        for index,result in enumerate(backend.results):
            path=args.diagnostics/f'feedback_diagnostics/cycle_{result.cycle-1:04d}.json'
            if path.exists():
                record=json.loads(path.read_text(encoding='utf8'))
                means={op['operation']:op.get('legacy_mean_percent') for op in record['operations']}
                backend.results[index]=replace(result,powder_repartition_avg_change_percent=means.get('powder'),
                                               intensity_correction_avg_change_percent=means.get('intensity'))
    if args.run:
        recorded=list(csv.DictReader((args.run/'metrics.csv').open()))
        def quality(row):
            data={}
            for f in fields(MapQualityMetrics):
                value=row.get(f.name)
                if value:
                    data[f.name]=value if f.name=='unavailable_reason' else int(value) if f.name.startswith('n_') or f.name in ('reference_tp','reference_fp') else float(value)
            return MapQualityMetrics(**data)
        def path(value):
            # Original absolute paths are read only. Prefer the caller-selected run.
            p=Path(value);parts=p.parts
            index=next((i for i,v in enumerate(parts) if v.startswith('cycle_')),None)
            return args.run.joinpath(*parts[index:]) if index is not None else p
        actual=[]
        for cycle in range(7,10):
            sf=next(r for r in recorded if int(r['cycle'])==cycle and r['source']=='superflip')
            sh=next(r for r in recorded if int(r['cycle'])==cycle and r['source']!='superflip')
            actual.append(replace(backend.results[cycle-7],cycle=cycle,
                validation_profile=sf['validation_profile'],superflip_quality=quality(sf),deblur_quality=quality(sh),
                superflip_map=path(sf['map_path']),superflip_edma_cif=path(sf['structure_path']),
                deblur_map=path(sh['map_path']),deblur_edma_cif=path(sh['structure_path']),
                superflip_edma_sigma=1.5,deblur_edma_sigma=1.5,sharped_model='SEED (cyclic CF)',
                powder_repartition_avg_change_percent=float(sf['powder_repartition_avg_change_percent'])))
        backend.results=actual
        backend.reference_atoms_for_plot=a.parse_cif_atoms(args.run.parent/'Selexipag-64_14-Rohlicek_Jana-better-final.cif')
    backend.last_run_config.redistribute_overlaps=True
    if args.diagnostics:backend.last_run_config.work_dir=args.diagnostics
    opened=[]
    with patch.object(a.ResultSelectionDialog,'exec',lambda d:opened.append(d) or QDialog.Rejected):backend.open_result_selector('jana')
    dialog=opened[0];dialog._rotate_timer.stop();dialog._auto_rotate_enabled=False
    dialog.show();dialog.resize(1500,950)
    for source,button in [('superflip',dialog._superflip_btn),('deblurred',dialog._sharped_btn)]:
        button.click();view=dialog._views[source];view.selected=next(c for c in view.ordered if c.cycle==8)
        for _ in range(8):qt.processEvents()
        dialog.grab().save(str(out/f'jana-{source}.png'))
        if hasattr(dialog,'_feedback_label'):
            (out/f'{source}-summary.txt').write_text(dialog._feedback_label.accessibleName(),encoding='utf8')
    if hasattr(dialog,'_feedback_details_button') and dialog._feedback_details_button.isEnabled():
        dialog._feedback_details_button.click();qt.processEvents();details=dialog._feedback_dialog
        for tab,name in [(0,'step'),(2,'reflections'),(3,'cumulative')]:
            details.findChild(QTabWidget).setCurrentIndex(tab);qt.processEvents();details.grab().save(str(out/f'details-{name}.png'))
        details.close()
    dialog.close();backend.close()
