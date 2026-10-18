"""Actual QtAgg/DPI acceptance with real powder data and labelled fixtures."""
import os
import sys
import json
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QSettings, QRect
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication, QLabel
from phase_studio import app as a
from phase_studio.version import VERSION
from phase_studio.hkl_diagnostics_ui import _detail_dialog, presentation_report
from test_hkl_diagnostics import DiagnosticsTests


def main():
    scale=os.environ.get('QT_SCALE_FACTOR','1')
    out=ROOT/('build/acceptance-hkl-ui-refinement-'+VERSION)/('dpi-'+scale)
    out.mkdir(parents=True,exist_ok=True)
    qt=QApplication([]); a.apply_phase_studio_style(qt)
    evidence={}
    def settle():
        for _ in range(30): qt.processEvents()
    def capture(name,dialog,kind):
        settle()
        dialog.grab().save(str(out/(name+'.png')))
        evidence[name]=dict(geometry=dialog.geometry().getRect(),dpi=dialog.devicePixelRatioF(),data=kind)
    with tempfile.TemporaryDirectory() as temporary, patch.object(a.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models',lambda self:None), patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,int(2560/float(scale)),int(1600/float(scale)))):
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,temporary)
        win=a.IterativeSuperflipPipelineQtGUI(); win.timer.stop()
        source=ROOT/'build/powder-final/wizard-input/ochlor_Superflip.inflip'
        source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
        load=a.build_hkl_load_result(a.build_hkl_analysis_request_from_inflip(source,work_dir=Path(temporary)/'ochlor'))
        analysis=a.analyze_hkl_data(load.hkl_path,load.data_mode,load.cell,load.spacegroup,load.spacegroup_hm,load.source_note,_loaded=load)
        report=presentation_report(analysis)
        before=Path(temporary)/'before.json'; report.export_json(before,analysis)
        dialog=win._build_hkl_completeness_dialog(analysis)
        dialog.resize(1180,940); dialog.show(); settle()
        capture('01-completeness-analysis',dialog,'Real ochlor powder')
        original=dialog.size()
        dialog.hkl_plot_tabs.setCurrentIndex(1); settle()
        assert dialog.size()==original
        assert dialog.hkl_bin_columns[2][0]=='input'
        assert sum(row['affected'] for row in dialog.hkl_overlap_bin_rows)==193
        capture('02-completeness-overlap',dialog,'Real ochlor powder')
        canvas=dialog.hkl_overlap_canvas; canvas.draw()
        renderer=canvas.get_renderer()
        for axis in dialog.hkl_overlap_figure.axes:
            for label in (axis.xaxis.label,axis.yaxis.label,axis.title):
                box=label.get_window_extent(renderer)
                assert box.y0>=-1 and box.x0>=-1 and box.y1<=canvas.height()*canvas.devicePixelRatioF()+2
        dialog.hkl_content_splitter.setSizes([300,320]); settle()
        capture('03-enlarged-overlap-table',dialog,'Real ochlor powder')
        dialog.hkl_plot_tabs.setCurrentIndex(0); settle()
        assert dialog.hkl_bin_columns[2][0]=='observed'
        detail=_detail_dialog(dialog,report); detail.show(); settle()
        initial=detail.size()
        names=['input','counts-symmetry','absences-duplicates','values','resolution','peak-overlap','availability']
        for index,name in enumerate(names):
            detail.hkl_details_tabs.setCurrentIndex(index); settle()
            assert detail.size()==initial
            assert detail.hkl_close_button.isVisible()
            assert detail.hkl_details_tabs.widget(index).horizontalScrollBar().maximum()==0
            capture(f'{index+4:02}-{name}',detail,'Real ochlor powder')
        detail.hkl_details_tabs.setCurrentIndex(5)
        detail.hkl_disclosures['Overlap methodology'].click(); settle()
        assert detail.size()==initial
        capture('11-overlap-methodology-expanded',detail,'Real ochlor powder')
        detail.hkl_disclosures['Group details'].click(); settle()
        capture('12-overlap-group-details',detail,'Real ochlor powder')
        detail.close(); dialog.close()
        fixture=DiagnosticsTests(); fixture.setUp()
        for name,text,mode,kwargs in [
            ('13-amplitudes','\n'.join(f'{h} {k} 1 {h*k+3} 0 1.2' for h in range(1,8) for k in range(1,6)),a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,{}),
            ('14-varying-widths','\n'.join(f'{h} {k} 1 {h*k+1} {.04+h*.005}' for h in range(1,9) for k in range(1,7)),a.REFLECTION_DATA_MODE_INTENSITY_FWHM,dict(fwhm_units='degrees_2theta',wavelength=1.54)),
            ('15-no-overlap-capability','1 2 1 10 .05\n2 2 1 20 .08',a.REFLECTION_DATA_MODE_INTENSITY_FWHM,{})]:
            synthetic=fixture.load(text,mode,**kwargs)
            if kwargs:
                from phase_studio.hkl_diagnostics import build_diagnostics
                synthetic.powder_diagnostic_context=dict(kwargs,separation_factor=.2)
                synthetic.diagnostics=build_diagnostics(synthetic)
            x=a.analyze_hkl_data(synthetic.hkl_path,synthetic.data_mode,synthetic.cell,synthetic.spacegroup,synthetic.spacegroup_hm,synthetic.source_note,_loaded=synthetic)
            view=win._build_hkl_completeness_dialog(x); view.resize(1180,940); view.show(); settle()
            if name.startswith('14'):
                assert view.hkl_plot_tabs.count()==2
                view.hkl_plot_tabs.setCurrentIndex(1);settle()
            if name.startswith('15'):assert view.hkl_plot_tabs.count()==1
            capture(name,view,'Synthetic controlled fixture; genuine amplitude sigma column' if name.startswith('13') else 'Synthetic controlled fixture')
            for figure in view.hkl_plot_figures.values(): figure.canvas.draw()
            view.close()
        fixture.tearDown()
        after=Path(temporary)/'after.json'; report.export_json(after,analysis)
        assert before.read_bytes()==after.read_bytes()
        assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
        evidence['science']=dict(overlap=dict(report.overlap),d_min=analysis.d_min,d98=analysis.d_full_98,
            unchanged_report_sha256=hashlib.sha256(before.read_bytes()).hexdigest(),source_sha256=source_hash)
        win.close()
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False),encoding='utf8')
    print('PASS: actual QtAgg, 7 tabs, contextual tables, axes and unchanged real ochlor report at DPI '+scale)


if __name__=='__main__':
    main()
