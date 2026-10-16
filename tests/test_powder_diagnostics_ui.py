"""Missing wavelength never creates dependent numbers; explicit input is required."""
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def check():
    import tempfile
    from unittest.mock import patch
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication,QDialog
    from phase_studio import app as a
    qt=QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
        path=root/'missing.inflip'
        path.write_text('dimension 3\ncell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\ndataformat intensity fwhm\nfbegin\n1 0 0 10 .1\n0 1 0 20 .1\n2 0 0 30 .1\nendf\n')
        before=path.read_bytes()
        win=a.IterativeSuperflipPipelineQtGUI()
        request=a.build_hkl_analysis_request_from_inflip(path,work_dir=root/'work')
        load=a.build_hkl_load_result(request)
        analysis=a.analyze_hkl_data(load.hkl_path,load.data_mode,load.cell,load.spacegroup,load.spacegroup_hm,_loaded=load)
        for result,builder in ((load,win._build_hkl_validation_dialog),(analysis,win._build_hkl_completeness_dialog)):
            dialog=builder(result);dialog.show()
            for _ in range(20):qt.processEvents()
            assert not dialog.diagnostics.available('overlap')
            assert not dialog.hkl_wavelength_apply.isEnabled()
            assert dialog.hkl_wavelength_spin.value()==0
            if hasattr(dialog,'hkl_plot_tabs'):
                assert all(dialog.hkl_plot_tabs.tabText(i)!='Peak overlap' for i in range(dialog.hkl_plot_tabs.count()))
            dialog.hkl_wavelength_spin.setValue(1.)
            with patch.object(QDialog,'exec',return_value=QDialog.Rejected):dialog.hkl_wavelength_apply.click()
            review=dialog.hkl_wavelength_result
            overlap=dict(review.diagnostics.overlap)
            assert overlap['available'] and overlap['wavelength']==1.
            assert overlap['wavelength_source']=='user-entered diagnostic wavelength'
            assert overlap['affected']==2
            assert not result.diagnostics.available('overlap')
            if hasattr(result,'d_full_98'):
                assert review.diagnostics.shells==dialog.diagnostics.shells or all(dict(x)['coverage']==dict(y)['coverage'] for x,y in zip(review.diagnostics.shells,dialog.diagnostics.shells))
            review.close();dialog.close()
        assert path.read_bytes()==before
        win.timer.stop();win.close()

def test_missing_wavelength_requires_user_input_at_three_scales():
    for scale in ('1','1.25','1.5'):
        result=subprocess.run([sys.executable,__file__,'--child'],cwd=ROOT,capture_output=True,text=True,
                              env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale},timeout=60)
        assert result.returncode==0,result.stdout+result.stderr

if __name__=='__main__':check()
