"""Prepare real reports once, then render unchanged data in actual Qt dialogs."""
import hashlib
import json
import os
from pathlib import Path
import pickle
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from phase_studio import app as a
from phase_studio.hkl_diagnostics import cached_analysis, export_shell_csv
from phase_studio.hkl_diagnostics_ui import presentation_report, _resolution_summary, _detail_dialog
from phase_studio.version import VERSION

OUT=ROOT/('build/acceptance-hkl-advanced-final-'+VERSION)
OUT.mkdir(parents=True,exist_ok=True)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    baseline=json.loads((ROOT/'build/hkl-presentation/real-acceptance.json').read_text(encoding='utf8'))
    cache={}
    inputs=[('ochlor', Path(os.environ.get('PHASE_STUDIO_TEST_INFLIP',str(ROOT/'build/powder-final/wizard-input/ochlor_Superflip.inflip')))),
            ('2int3total',Path(os.environ['PHASE_STUDIO_LARGE_INFLIP']))]
    for name,source in inputs:
        original_hash=sha(source)
        request=a.build_hkl_analysis_request_from_inflip(source,work_dir=OUT/'prepared'/name)
        analysis=cached_analysis(request)
        report=presentation_report(analysis)
        accepted=baseline[name]
        assert original_hash==accepted['input_sha256']
        assert analysis.d_min==accepted['d_min'] and analysis.d_full_98==accepted['d98']
        assert len(analysis.reflections_raw)==accepted['parsed_records']
        assert report.statistic('mean_f_over_sigma')==accepted['mean_F_over_sigma']
        assert report.statistic('median_f_over_sigma')==accepted['median_F_over_sigma']
        report.export_json(OUT/(name+'-before.json'),analysis)
        export_shell_csv(OUT/(name+'-before.csv'),report)
        invariant=dict(source_sha256=original_hash,parsed=report.count('parsed_records'),d_min=analysis.d_min,d98=analysis.d_full_98,
            mean_f_over_sigma=report.statistic('mean_f_over_sigma'),median_f_over_sigma=report.statistic('median_f_over_sigma'),
            counts=dict(report.counts),statistics=dict(report.statistics),overlap=dict(report.overlap),
            report_sha256=sha(OUT/(name+'-before.json')),csv_sha256=sha(OUT/(name+'-before.csv')))
        cache[name]=(report,_resolution_summary(analysis),invariant)
        assert sha(source)==original_hash
        print(name+' baseline unchanged',flush=True)
    # Locally generated, trusted cache: rendering does not run scientific analysis.
    (OUT/'prepared-reports.pickle').write_bytes(pickle.dumps(cache))
    (OUT/'numerical-invariants.json').write_text(json.dumps({k:v[2] for k,v in cache.items()},indent=2),encoding='utf8')


def capture():
    from PySide6.QtCore import QSettings,QRect,Qt
    from PySide6.QtGui import QScreen
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication,QDialog,QLabel
    scale=os.environ.get('QT_SCALE_FACTOR','1')
    output=OUT/('dpi-'+scale);output.mkdir(exist_ok=True)
    qt=QApplication([]);a.apply_phase_studio_style(qt)
    cache=pickle.loads((OUT/'prepared-reports.pickle').read_bytes())
    evidence={}
    def settle():
        for _ in range(20):qt.processEvents()
    def snap(name,dialog):
        settle();dialog.grab().save(str(output/(name+'.png')))
        evidence[name]=dict(client=dialog.geometry().getRect(),frame=dialog.frameGeometry().getRect(),dpi=dialog.devicePixelRatioF())
    with tempfile.TemporaryDirectory() as temporary, patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,int(2560/float(scale)),int(1600/float(scale)))):
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,temporary)
        parent=QDialog()
        names=['input','counts-symmetry','absences-duplicates','values','resolution','peak-overlap','availability']
        for dataset,(report,summary,invariant) in cache.items():
            parent.hkl_resolution_summary=summary
            # Start each dataset with an unused geometry namespace.
            settings=QSettings(QSettings.IniFormat,QSettings.UserScope,'PhaseStudio','PhaseStudio')
            settings.remove('hklAdvanced');settings.sync()
            dialog=_detail_dialog(parent,report);dialog.show();settle()
            original=dialog.geometry()
            assert dialog.width()==1050 and 520<=dialog.height()<=540
            report.export_json(output/(dataset+'-before.json'))
            before=sha(output/(dataset+'-before.json'))
            for index,name in enumerate(names):
                dialog.hkl_details_tabs.setCurrentIndex(index);settle()
                assert dialog.geometry()==original
                page=dialog.hkl_details_tabs.widget(index)
                assert page.horizontalScrollBar().maximum()==0
                assert dialog.hkl_close_button.isVisible() and dialog.rect().contains(dialog.hkl_close_button.geometry())
                if dataset=='ochlor' or index in (3,4,6):snap(dataset+f'-{index+1:02}-'+name,dialog)
            table=dialog.hkl_capability_table
            assert abs(table.columnWidth(0)-.25*table.viewport().width())<2
            assert abs(table.columnWidth(1)-.18*table.viewport().width())<2
            table.setCurrentCell(0,0);table.setFocus();QTest.keyClick(table,Qt.Key_Down);settle()
            assert table.currentRow()==1
            assert report.capabilities[1].reason in dialog.hkl_capability_table.item(1,0).toolTip() or '<i>' in dialog.hkl_capability_reason.text()
            if dataset=='ochlor':
                assert '2 HKL: 81 groups' in dialog.hkl_group_distribution.text()
                assert '3 HKL: 9 groups' in dialog.hkl_group_distribution.text()
                assert '4 HKL: 1 group' in dialog.hkl_group_distribution.text()
                for number,index,title in [(8,5,'Overlap methodology'),(9,4,'Resolution methodology'),(10,6,'Methodology and data provenance')]:
                    dialog.hkl_details_tabs.setCurrentIndex(index)
                    if index==5:dialog.hkl_disclosures['Group details'].click()
                    dialog.hkl_disclosures[title].click();settle()
                    assert dialog.geometry()==original
                    snap(dataset+f'-{number:02}-expanded-'+str(index),dialog)
                    page=dialog.hkl_details_tabs.widget(index)
                    page.verticalScrollBar().setValue(page.verticalScrollBar().maximum());settle()
                    assert dialog.hkl_close_button.isVisible()
                    dialog.hkl_disclosures[title].click()
            report.export_json(output/(dataset+'-after.json'))
            export_shell_csv(output/(dataset+'-after.csv'),report)
            assert before==sha(output/(dataset+'-after.json'))
            assert invariant['csv_sha256']==sha(output/(dataset+'-after.csv'))
            assert all('Science Gothic' not in label.font().family() for label in dialog.findChildren(QLabel))
            dialog.resize(1100,650);settle();resized=dialog.size();dialog.close()
            restored=_detail_dialog(parent,report);restored.show();settle()
            assert restored.size()==resized
            restored.close()
        parent.close()
    (output/'geometry.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')
    print('PASS final real-data Qt acceptance at '+scale)


if __name__=='__main__':
    prepare() if '--prepare' in sys.argv else capture()
