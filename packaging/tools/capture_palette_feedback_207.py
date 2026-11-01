"""Actual Qt palette/metadata evidence; optional private stored models stay local."""
import os,sys,argparse,json,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path(os.environ.get('PHASE_STUDIO_AUDIT_SOURCE_ROOT',str(ROOT)))
sys.path.insert(0,str(SOURCE))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen');os.environ['PHASE_STUDIO_STARTUP_PROBE']='1'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage');parser.add_argument('--data');parser.add_argument('--diagnostics');parser.add_argument('--width',type=int,default=1920);parser.add_argument('--height',type=int,default=1140)
    args=parser.parse_args()
    from PySide6.QtCore import QSettings,QRect
    from PySide6.QtGui import QScreen
    from PySide6.QtWidgets import QApplication,QToolButton,QTabWidget
    from phase_studio import app as a,structure_camera as camera
    qt=QApplication([]);a.apply_phase_studio_style(qt);qt._phase_color_palette='phase'
    factor=float(os.environ.get('QT_SCALE_FACTOR','1'));width=int(args.width/factor);height=int(args.height/factor)
    out=ROOT/'build/palette-feedback207'/args.stage;out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp,patch.object(a.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models',lambda self:None),patch.object(a.IterativeSuperflipPipelineQtGUI,'load_settings',lambda self:None),patch.object(a.IterativeSuperflipPipelineQtGUI,'save_settings',lambda self:None),patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,width,height)):
        settings=QSettings(str(Path(tmp)/'camera.ini'),QSettings.IniFormat)
        with patch.object(camera,'QSettings',lambda *args:settings):
            win=a.IterativeSuperflipPipelineQtGUI();win.timer.stop()
            if args.data:
                root=Path(args.data)
                paths=[root/'Selexipag-64_14-Rohlicek_Jana-better-final.cif',
                    root/'run_0001/cycle_007/edma_superflip/cycle_007_superflip_edma.cif',
                    root/'run_0001/cycle_007/edma_deblurred/cycle_007_deblurred_edma.cif']
            else:
                p=Path(tmp)/'synthetic.cif'
                p.write_text("data_fixture\n_cell_length_a 10\n_cell_length_b 10\n_cell_length_c 10\n_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n_space_group_name_H-M_alt 'P 1'\nloop_\n_atom_site_label\n_atom_site_type_symbol\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\nC1 C .1 .1 .1\nN1 N .2 .1 .1\nO1 O .3 .1 .1\nS1 S .4 .1 .1\n")
                paths=[p]*3
            win.structure_cell=a.parse_cif_cell_and_sg(paths[0])[0]
            for role,attr,p in zip(('reference','superflip','deblur'),('reference_atoms_for_plot','superflip_atoms_for_plot','deblur_atoms_for_plot'),paths):
                win._structure_source_paths[role]=p;setattr(win,attr,win._classic_structure_atoms(p))
            if args.data:
                run=Path(args.data)/'run_0001/cycle_007'
                win.results=[a.CycleResult(7,'recorded',None,None,
                    run/'cycle_007_superflip.xplor',paths[1],None,
                    run/'cycle_007_deblurred.xplor',paths[2],None,
                    superflip_edma_sigma=1.5,deblur_edma_sigma=1.5,sharped_model='SEED (cyclic CF)')]
                win._sync_classic_review_controls()
                compositions={'reference':win._classic_structure_composition('reference')}
                for role,p in zip(('superflip','deblur'),paths[1:]):
                    formula=a.edma_asu_composition_from_cif(p)
                    compositions[role]=('EDMA asymmetric-unit composition',formula)
                    controls=win.classic_review_controls[role]
                    controls['metadata'].setText(f'<b>Recorded cycle 7</b><br>EDMA asymmetric-unit composition: {formula}<br>{len(a.parse_cif_atoms(p))} EDMA sites')
                    controls['metadata'].setVisible(True)
                    controls['threshold_actions'].setVisible(True)
                    controls['add'].setEnabled(False);controls['remove'].setEnabled(False)
                win._classic_structure_composition=lambda role:compositions[role]
            win._update_structure_views();win.show();qt.processEvents();win.resize(width,height)
            menu=win.findChild(QToolButton,'structureCameraMenu').menu()
            palettes=next(action.menu() for action in menu.actions() if action.text()=='Element colors')
            evidence={}
            for value,word in [('phase','Current'),('cpk','CPK')]:
                next(action for action in palettes.actions() if word in action.text()).trigger()
                for _ in range(10):qt.processEvents()
                win.structure_canvas.draw();win.grab().save(str(out/(value+'.png')))
                evidence[value]=[d.atom_base_colors.tolist() for d in win._structure_depth_artists]
            (out/'artist-colors.json').write_text(json.dumps(evidence))
            if args.diagnostics and hasattr(win,'_receive_feedback_diagnostics'):
                from phase_studio.feedback_diagnostics import load_summaries
                from phase_studio.feedback_diagnostics_ui import FeedbackDiagnosticsDialog
                reports=load_summaries(args.diagnostics)
                for report in reports:
                    if report['source_cycle']<=7:win._receive_feedback_diagnostics(report)
                win.feedback_summary.setText('Recorded replay · '+win.feedback_summary.text())
                qt.processEvents();win.grab().save(str(out/'feedback-overview.png'))
                dialog=FeedbackDiagnosticsDialog(win,reports,args.diagnostics)
                dialog.cycle.setCurrentIndex(dialog.cycle.findData(5));dialog.show()
                for _ in range(5):qt.processEvents()
                dialog.grab().save(str(out/'feedback-summary.png'))
                tabs=dialog.findChild(QTabWidget)
                for index,name in [(1,'feedback-chart'),(2,'feedback-reflections')]:
                    tabs.setCurrentIndex(index);qt.processEvents();dialog.grab().save(str(out/(name+'.png')))
                dialog.close()
            win.close()


if __name__=='__main__':main()
