"""Read-only real-data parity and actual Qt screenshots; no network or phasing."""
import os
import sys
import json
import hashlib
import tempfile
import time
import importlib.util
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from phase_studio import app as a,hkl_diagnostics_ui as ui
from phase_studio.hkl_diagnostics import export_shell_csv,cached_analysis
OUT=ROOT/'build/acceptance-hkl-completeness-2.0.5'
OUT.mkdir(parents=True,exist_ok=True)
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run():
    from PySide6.QtCore import QSettings,Qt,QRect,QPoint
    from PySide6.QtGui import QScreen
    from PySide6.QtWidgets import QApplication,QPushButton
    factor=float(os.environ.get('QT_SCALE_FACTOR','1'))
    qt=QApplication([]);a.apply_phase_studio_style(qt)
    spec=importlib.util.spec_from_file_location('phase_studio._completeness_before',OUT/'before-hkl_diagnostics_ui.py')
    before=importlib.util.module_from_spec(spec);spec.loader.exec_module(before)
    sources={'ochlor':ROOT/'build/powder-final/wizard-input/ochlor_Superflip.inflip',
             '2int3total':Path.home()/'Documents/flipovani-phase-studio/2int3total.inflip'}
    cache={}
    for name,source in sources.items():
        request=a.build_hkl_analysis_request_from_inflip(source,work_dir=OUT/'prepared'/name)
        cache[name]=(a.build_hkl_load_result(request),cached_analysis(request))
    expected={'ochlor':(631,1.1990790613015834,1.1990790613015834),
              '2int3total':(328606,.7255092594101177,.8161153076022714)}
    evidence={}
    def settle():
        for _ in range(12):qt.processEvents()
    captures=OUT/('scale-'+str(factor));captures.mkdir(exist_ok=True)
    def snap(name,dialog):
        settle()
        assert dialog.grab().save(str(captures/(name+'.png')))
        close=next((b for b in dialog.findChildren(QPushButton) if b.text()=='Close'),None)
        if close is not None:
            assert dialog.rect().contains(QRect(close.mapTo(dialog,QPoint()),close.size()))
        print(name,dialog.size().toTuple(),'DPR',dialog.devicePixelRatioF(),flush=True)
    with tempfile.TemporaryDirectory() as tmp,patch.object(a.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models',lambda self:None),patch.object(a.IterativeSuperflipPipelineQtGUI,'load_settings',lambda self:None),patch.object(a.IterativeSuperflipPipelineQtGUI,'save_settings',lambda self:None),patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,int(1920/factor),int(1080/factor))):
        QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
        win=a.IterativeSuperflipPipelineQtGUI();win.timer.stop()
        for name,(load,analysis) in cache.items():
            source=sources[name]
            old_evidence=json.loads((ROOT/f'build/acceptance-gui-polish-2.0.5/{name}-invariants.json').read_text())
            assert sha(source)==old_evidence['source_sha256']
            assert (len(analysis.reflections_raw),analysis.d_min,analysis.d_full_98)==expected[name]
            old_report=before.presentation_report(analysis)
            new_report=ui.presentation_report(analysis)
            for label,report in [('before',old_report),('after',new_report)]:
                report.export_json(OUT/f'{name}-{label}.json',analysis)
                export_shell_csv(OUT/f'{name}-{label}.csv',report)
            for extension in ('json','csv'):
                assert (OUT/f'{name}-before.{extension}').read_bytes()==(OUT/f'{name}-after.{extension}').read_bytes()
            summary=dict(parsed=len(analysis.reflections_raw),d_min=analysis.d_min,d98=analysis.d_full_98,
                         source_sha256=sha(source),csv_sha256=sha(OUT/f'{name}-after.csv'),json_sha256=sha(OUT/f'{name}-after.json'))
            settings=QSettings(QSettings.IniFormat,QSettings.UserScope,'PhaseStudio','PhaseStudio')
            settings.setValue('hklCompleteness/resolutionAxis','stl')
            start=time.perf_counter();dialog=ui.completeness_dialog(win,analysis)
            summary['dialog_construct_seconds']=time.perf_counter()-start
            dialog.show();settle()
            if name=='ochlor':
                old=before.completeness_dialog(win,analysis);old.show();snap('00-before-analysis',old)
                old.hkl_plot_tabs.setCurrentIndex(1);snap('00-before-overlap',old);old.close()
                snap('01-analysis-default',dialog)
                dialog.hkl_resolution_axis.setCurrentIndex(1);snap('02-analysis-d-axis',dialog)
                dialog.hkl_histogram_scale.setCurrentIndex(0);snap('03-histogram-log',dialog)
                dialog.hkl_plot_tabs.setCurrentIndex(1);snap('04-overlap',dialog)
                dialog.hkl_bins_table.selectRow(10);snap('05-overlap-selected-bin',dialog)
                detail=ui.overlap_group_dialog(dialog,analysis,new_report)
                detail.show();snap('06-overlap-group-detail',detail)
                assert detail.records_model.rowCount()==193
                from collections import Counter
                groups=Counter(detail.records_model.groups[detail.records_model.indices])
                assert Counter(groups.values())=={2:81,3:9,4:1}
                overlap=dict(new_report.overlap)
                assert overlap['total_groups']==529 and overlap['non_overlapping_groups']==438
                assert overlap['group_count']==91 and overlap['affected']==193 and overlap['largest']==4
                assert abs(overlap['fraction']*100-30.5863708399)<1e-9
                assert abs(overlap['integrated_intensity_fraction']*100-21.0635613111)<1e-9
                summary['overlap']={k:overlap[k] for k in ('total_groups','non_overlapping_groups','group_count','affected','fraction','integrated_intensity_fraction','largest','size_distribution')}
                detail.close()
                dialog.resize(820,740);snap('07-reduced-window',dialog)
            else:
                snap('08-large-analysis',dialog)
                start=time.perf_counter()
                for i in range(20):
                    dialog.hkl_histogram_focus.setCurrentIndex(i%2)
                    dialog.hkl_resolution_axis.setCurrentIndex(i%2)
                summary['twenty_queued_display_updates_seconds']=time.perf_counter()-start
                start=time.perf_counter()
                for i in range(5):
                    dialog.hkl_resolution_axis.setCurrentIndex(i%2)
                    dialog.hkl_canvas.draw()
                    qt.processEvents()
                summary['five_rendered_axis_changes_seconds']=time.perf_counter()-start
                dialog.hkl_histogram_reset.click()
            active=dialog.hkl_plot_figures[dialog.hkl_plot_tabs.currentIndex()]
            active.savefig(captures/(name+'-selected-plot.svg'),bbox_inches='tight')
            new_report.export_json(OUT/f'{name}-after.json',analysis)
            export_shell_csv(OUT/f'{name}-after.csv',new_report)
            for extension in ('json','csv'):
                assert (OUT/f'{name}-before.{extension}').read_bytes()==(OUT/f'{name}-after.{extension}').read_bytes()
            assert sha(source)==old_evidence['source_sha256']
            evidence[name]=summary
            dialog.close()
        win.close();settle()
    (captures/'evidence.json').write_text(json.dumps(evidence,indent=2))
    print('Real diagnostic parity and Qt capture passed',flush=True)


if __name__=='__main__':run()
