"""Offline real-data screenshots and byte-parity guards for the advanced view."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from phase_studio import app as a, hkl_diagnostics_ui as ui
from phase_studio.hkl_diagnostics import cached_analysis, export_shell_csv
from PySide6.QtCore import QSettings, QRect, QTimer, QPoint
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication, QDialog

OUT = ROOT/'build/acceptance-hkl-advanced-refinement-2.0.5'
OUT.mkdir(parents=True, exist_ok=True)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    qt = QApplication([])
    a.apply_phase_studio_style(qt)
    factor = float(os.environ.get('QT_SCALE_FACTOR', '1'))
    output = OUT/('scale-'+str(factor)); output.mkdir(exist_ok=True)
    evidence = {}
    def settle():
        for _ in range(15): qt.processEvents()
    def snap(name, dialog):
        settle()
        assert dialog.grab().save(str(output/(name+'.png')))
        if hasattr(dialog, 'hkl_close_button'):
            button = dialog.hkl_close_button
            assert dialog.rect().contains(QRect(button.mapTo(dialog,QPoint()),button.size()))
        evidence[name] = dict(client=dialog.size().toTuple(), dpr=dialog.devicePixelRatioF())

    sources = {'ochlor': ROOT/'build/powder-final/wizard-input/ochlor_Superflip.inflip',
               '2int3total': Path.home()/'Documents/flipovani-phase-studio/2int3total.inflip'}
    with tempfile.TemporaryDirectory() as temporary, patch.object(QScreen, 'availableGeometry',
            return_value=QRect(0,0,int(1920/factor),int(1080/factor))):
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,temporary)
        parent = QDialog()
        for dataset, source in sources.items():
            source_hash = sha(source)
            request = a.build_hkl_analysis_request_from_inflip(source,
                work_dir=ROOT/'build/acceptance-hkl-completeness-2.0.5/prepared'/dataset)
            analysis = cached_analysis(request)
            report = ui.presentation_report(analysis)
            original = copy.deepcopy(report)
            expected = json.loads((ROOT/f'build/acceptance-gui-polish-2.0.5/{dataset}-invariants.json').read_text())
            assert source_hash == expected['source_sha256']
            parent.hkl_resolution_summary = ui._resolution_summary(analysis)
            parent.hkl_inspection_analysis = analysis
            report.export_json(output/(dataset+'-before.json'),analysis)
            export_shell_csv(output/(dataset+'-before.csv'),report)
            settings = QSettings(QSettings.IniFormat,QSettings.UserScope,'PhaseStudio','PhaseStudio')
            settings.remove('hklAdvanced');settings.sync()
            dialog = ui._detail_dialog(parent,report);dialog.show();settle()
            geometry = dialog.geometry()
            assert dialog.width()==1050 and dialog.height()==620
            for index, name in enumerate(('input','counts','absences','values','resolution','overlap','availability')):
                dialog.hkl_details_tabs.setCurrentIndex(index);settle()
                assert dialog.geometry()==geometry
                assert dialog.hkl_details_tabs.widget(index).horizontalScrollBar().maximum()==0
                if dataset=='ochlor': snap(f'{index+1:02}-{name}',dialog)
            if dataset=='ochlor':
                table = dialog.hkl_capability_table;table.setCurrentCell(3,0);table.setFocus()
                snap('08-selected-availability',dialog)
                dialog.hkl_details_tabs.setCurrentIndex(4)
                dialog.hkl_disclosures['Resolution methodology'].click()
                snap('09-expanded-methodology',dialog)
                assert dialog.geometry()==geometry
                dialog.hkl_details_tabs.widget(4).verticalScrollBar().setValue(
                    dialog.hkl_details_tabs.widget(4).verticalScrollBar().maximum())
                snap('10-scrolled-methodology',dialog)
                dialog.hkl_details_tabs.setCurrentIndex(5)
                def inspect():
                    child=dialog.hkl_group_detail
                    snap('11-original-overlap-records',child)
                    assert child.records_model.rowCount()==193
                    child.close()
                QTimer.singleShot(0,inspect)
                dialog.hkl_inspect_groups.click()
                dialog.resize(760,480);dialog.hkl_details_tabs.setCurrentIndex(0)
                snap('12-small-window',dialog)
                dialog.hkl_copy_input_summary.click()
                assert report.source in QApplication.clipboard().text()
            report.export_json(output/(dataset+'-after.json'),analysis)
            export_shell_csv(output/(dataset+'-after.csv'),report)
            for extension in ('json','csv'):
                assert (output/(dataset+'-before.'+extension)).read_bytes()==(output/(dataset+'-after.'+extension)).read_bytes()
                # Also compare with the accepted preceding Completeness presentation.
                assert (output/(dataset+'-after.'+extension)).read_bytes()==(
                    ROOT/f'build/acceptance-hkl-completeness-2.0.5/{dataset}-after.{extension}').read_bytes()
            assert report==original and sha(source)==source_hash
            evidence[dataset]=dict(parsed=report.count('parsed_records'),d_min=analysis.d_min,d98=analysis.d_full_98,
                source_sha256=source_hash,json_sha256=sha(output/(dataset+'-after.json')),
                csv_sha256=sha(output/(dataset+'-after.csv')),overlap=dict(report.overlap))
            dialog.close()
        parent.close()
    (output/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')
    print('PASS real reports, original records, byte-identical exports and screenshots at',factor,flush=True)


if __name__=='__main__': run()
