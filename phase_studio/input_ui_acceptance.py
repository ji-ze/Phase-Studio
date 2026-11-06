"""Explicit opt-in source/frozen UI verification using controlled reflection files."""
import hashlib
import json
import os
from pathlib import Path
import sys

_APPLICATION = None


def run(directory):
    global _APPLICATION
    from PySide6.QtCore import QSettings, Qt, QRect
    from PySide6.QtGui import QFontInfo, QScreen
    from PySide6.QtWidgets import QApplication, QLabel
    from unittest.mock import patch
    import gemmi
    from . import app as a
    from . import hkl_diagnostics as diagnostics
    from .about_ui import AboutDialog
    from .legal_content import source_text, overview_html, legal_directory
    from .input_analysis_ui import analyze_data_dialog, TABS
    directory = Path(directory).absolute()
    directory.mkdir(parents=True,exist_ok=True)
    os.environ['PHASE_STUDIO_STARTUP_PROBE']='1'
    _APPLICATION = QApplication.instance() or QApplication([])
    q = _APPLICATION
    a.apply_phase_studio_style(q)
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(directory/'settings'))
    report = dict(frozen=bool(getattr(sys,'frozen',False)),scale=os.environ.get('QT_SCALE_FACTOR','1'),passed=False,profiles=[])
    legal_hashes={}
    for name in ('AUTHORS.md','LICENSE','CITATION.cff','THIRD_PARTY_NOTICES.md'):
        path=legal_directory()/name
        assert path.is_file(), 'Missing bundled legal authority: '+name
        legal_hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    assert source_text('LICENSE').startswith('MIT License')
    assert 'Permission is hereby granted, free of charge' in source_text('LICENSE')
    assert 'cff-version: 1.2.0' in source_text('CITATION.cff')
    report['legal_file_sha256']=legal_hashes
    def settle():
        for _ in range(20): q.processEvents()
    def snap(name,widget):
        settle()
        assert widget.grab().save(str(directory/(name+'.png')))
    scale=float(os.environ.get('QT_SCALE_FACTOR','1'))
    with patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,int(1920/scale),int(1040/scale))):
        win = a.IterativeSuperflipPipelineQtGUI()
        splash = a.PhaseStudioSplash()
        splash.set_status('Finalizing workspace...',86)
        splash.show();settle()
        title=splash.findChild(QLabel,'splashTitle')
        brand=win.findChild(QLabel,'brandTitle')
        actual=QFontInfo(title.font())
        assert actual.family()=='Science Gothic' and actual.weight()==400
        assert brand is not None and QFontInfo(brand.font()).family()==actual.family()
        assert title.fontMetrics().horizontalAdvance(title.text())<=title.width()
        report['splash_font']=dict(family=actual.family(),weight=int(actual.weight()),spacing=title.font().letterSpacing(),main_family=QFontInfo(brand.font()).family())
        snap('splash',splash);splash.close()
        for jana in (False,True):
            name='jana' if jana else 'standalone'
            about=AboutDialog(win,jana=jana)
            about.show();settle()
            first=about.documents[0].toPlainText()
            assert 'Jiří Zelenka' in first and 'kucerakova@fzu.cz' in first
            assert '**' not in first and '# Authors' not in first
            assert about.credits.toPlainText()==source_text('LICENSE')
            assert 'mailto:zelenka@fzu.cz' in about.documents[0].toHtml()
            third=about.documents[3].toHtml()
            assert '<table' in third
            snap(name+'-about',about)
            about.tabs.setCurrentIndex(2);about.search.setText('permission');about.find_next()
            assert 'permission' in about.credits.textCursor().selectedText().lower()
            snap(name+'-license',about)
            about.close()
            profile=dict(profile=name,legal_exact=True,tabs=[])
            for powder in (False,True):
                source=directory/(name+('-powder' if powder else '-single')+'.hkl')
                mode=a.REFLECTION_DATA_MODE_INTENSITY_FWHM if powder else a.REFLECTION_DATA_MODE_INTENSITY
                source.write_text('\n'.join(f'{h} {k} {l} {100/(h*h+k*k+l*l)} '+('.0527' if powder else '2')
                    for h in range(1,8) for k in range(1,5) for l in range(1,4)),encoding='utf8')
                before=hashlib.sha256(source.read_bytes()).hexdigest()
                raw=list(diagnostics.read_diagnostic_reflections(source,mode)[0])
                cell=gemmi.UnitCell(10,11,12,90,102,90);sg=gemmi.SpaceGroup('P 1')
                load=a.HklLoadResult(source,mode,cell,sg,sg.xhm(),'Synthetic controlled acceptance fixture',
                    *a.reflection_columns_for_mode(mode),raw,a.merge_duplicate_reflections(raw))
                load.diagnostics=diagnostics.build_diagnostics(load, fwhm_units='degrees_2theta',wavelength=1.0) if powder else diagnostics.build_diagnostics(load)
                analysis=a.analyze_hkl_data(source,mode,cell,sg,sg.xhm(),load.source_note,_loaded=load)
                dialog=analyze_data_dialog(win,analysis)
                dialog.show();settle()
                assert tuple(dialog.analysis_tabs.tabText(i) for i in range(7))==TABS
                for i,tab in enumerate(TABS):
                    dialog.analysis_tabs.setCurrentIndex(i);settle()
                    snap(name+('-powder-' if powder else '-single-')+str(i+1),dialog)
                    for pair in range(3):
                        dialog.analysis_plot_pair.setCurrentIndex(pair);settle()
                        for fig in [dialog.analysis_figures[i]] if i in dialog.analysis_figures else []:
                            fig.canvas.draw()
                            for axis in fig.axes:
                                bbox=axis.get_tightbbox(fig.canvas.get_renderer())
                                assert bbox.x0>=-1 and bbox.y0>=-1 and bbox.x1<=fig.bbox.width+1 and bbox.y1<=fig.bbox.height+1
                    dialog.analysis_plot_pair.setCurrentIndex(0)
                assert sum(r['records'] for r in dialog.analysis_rows)==84
                assert source.read_bytes() and hashlib.sha256(source.read_bytes()).hexdigest()==before
                if powder:
                    assert all(r['significance_count']==0 for r in dialog.analysis_rows)
                profile['tabs'].append(dict(powder=powder,count=7,input_sha256=before,unchanged=True))
                dialog.close()
            report['profiles'].append(profile)
        win.close()
    from matplotlib import pyplot as plt
    plt.close('all')
    report['passed']=True
    (directory/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    return 0
