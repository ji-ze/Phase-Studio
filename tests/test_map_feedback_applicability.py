"""Existing feedback numerics, uncertainty applicability and Wizard submission."""
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

class FeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import QSettings
        cls.settings=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.settings.cleanup)
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,cls.settings.name)
        from PySide6.QtWidgets import QApplication
        from phase_studio.ui_style import apply_phase_studio_style
        cls.qtapp = QApplication.instance() or QApplication([])
        apply_phase_studio_style(cls.qtapp)

    def setUp(self):
        from phase_studio import app, jana_superflip
        self.a, self.j = app, jana_superflip
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        jana_root = self.root / 'JanaActive'
        tools = jana_root / 'SUPERFLIP'
        tools.mkdir(parents=True)
        (tools / 'superflip.exe').write_bytes(b'controlled scientific executable fixture')
        (tools / 'EDMA.exe').write_bytes(b'controlled EDMA fixture')
        active = patch.object(self.j,'application_dir',return_value=jana_root)
        active.start()
        self.addCleanup(active.stop)

    def feedback(self, rows, mode, threshold, damping=.5):
        import gemmi
        predictions = {(1, 0, 0): (4., 0.), (2, 0, 0): (16., 0.), (3, 0, 0): (4., 0.)}
        with patch.object(self.a, 'xplor_fft_predictions', return_value=predictions):
            return self.a.apply_map_feedback_to_reflections(rows, mode, self.root/'map.xplor',
                gemmi.UnitCell(10,10,10,90,90,90), 0, False, 0, True, damping, threshold, lambda s: None)

    def test_threshold_zero_preserves_existing_intensity_numerics_and_input(self):
        rows = [self.a.Reflection(i,0,0,v,None) for i,v in enumerate([10.,20.,30.],1)]
        before = [(r.value,r.sigma) for r in rows]
        out, change = self.feedback(rows, self.a.REFLECTION_DATA_MODE_INTENSITY, 0)
        self.assertEqual([r.value for r in out], [10.,30.,20.])
        self.assertEqual([(r.value,r.sigma) for r in rows], before)
        self.assertTrue(all(r.sigma is None for r in out))
        self.assertAlmostEqual(change, (0+50+100/3)/3)

    def test_measured_intensity_significance(self):
        rows = [self.a.Reflection(i,0,0,v,s) for i,(v,s) in enumerate([(10,1),(20,10),(30,1)],1)]
        out,_ = self.feedback(rows, self.a.REFLECTION_DATA_MODE_INTENSITY, 2.5)
        self.assertEqual([r.value for r in out], [10.,30.,30.])

    def test_amplitudes_use_first_order_intensity_significance(self):
        import gemmi
        rows = [self.a.Reflection(i,0,0,v,s) for i,(v,s) in enumerate([(2,.5),(4,1),(6,.5)],1)]
        predictions = {(i,0,0):(v,0) for i,v in enumerate([1.,9.,16.],1)}
        with patch.object(self.a,'xplor_fft_predictions',return_value=predictions):
            out,_ = self.a.apply_map_feedback_to_reflections(rows,self.a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
                self.root/'map.xplor',gemmi.UnitCell(10,10,10,90,90,90),0,False,0,True,.5,2.5,lambda s:None)
        self.assertAlmostEqual(out[1].value,math.sqrt(18.125))
        self.assertAlmostEqual(out[0].value,math.sqrt(3.125))
        self.assertEqual(out[2].value,6.)
        self.assertEqual([r.sigma for r in out],[.5,1,.5])

    def test_equivalent_intensities_amplitudes_phase_formats_and_strict_boundary(self):
        a=self.a
        for imode,fmode in [(a.REFLECTION_DATA_MODE_INTENSITY,a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA),
                           (a.REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA)]:
            for threshold in (2.,2.5):
                fs=[a.Reflection(i,0,0,f,s,37.) for i,(f,s) in enumerate([(2,.5),(4,1),(6,.5)],1)]
                intensities=[a.Reflection(r.h,0,0,r.value**2,2*r.value*r.sigma,r.phase) for r in fs]
                fout,_=self.feedback(fs,fmode,threshold)
                iout,_=self.feedback(intensities,imode,threshold)
                for before,fr,ir in zip(fs,fout,iout):
                    self.assertAlmostEqual(fr.value**2,ir.value)
                    self.assertEqual(fr.sigma,before.sigma)
                    self.assertEqual(fr.phase,before.phase)
                    self.assertEqual(a.map_feedback_intensity_significance(before,fmode),
                        a.map_feedback_intensity_significance(intensities[before.h-1],imode))
                if threshold==2.:self.assertEqual([r.value for r in fout],[2,4,6])

    def test_significance_helper_rejects_unusable_measurements(self):
        a=self.a
        for mode in (a.REFLECTION_DATA_MODE_INTENSITY,a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
                     a.REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA):
            for value,sigma in [(0,1),(-1,1),(float('nan'),1),(float('inf'),1),
                                (1,None),(1,0),(1,-1),(1,float('nan')),(1,float('inf'))]:
                self.assertIsNone(a.map_feedback_intensity_significance(a.Reflection(1,0,0,value,sigma),mode))
        for mode in (a.REFLECTION_DATA_MODE_INTENSITY_FWHM,a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM,a.REFLECTION_DATA_MODE_AUTO):
            self.assertIsNone(a.map_feedback_intensity_significance(a.Reflection(1,0,0,1,.1),mode))

    def test_only_positive_significance_gate_changes_from_scientific_baseline(self):
        import ast
        import subprocess
        baseline='b628eb9da8b66f9b91b34ab87a6d67eebf0da78c'
        old=ast.parse(subprocess.check_output(['git','show',baseline+':phase_studio/app.py']).decode('utf-8'))
        new=ast.parse(Path(self.a.__file__).read_text(encoding='utf-8'))
        find=lambda tree:next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='apply_map_feedback_to_reflections')
        original,current=find(old),find(new)
        gates=[n for n in ast.walk(current) if isinstance(n,ast.If) and
            ast.dump(n.test)==ast.dump(ast.parse('max_i_over_sigma > 0',mode='eval').body)]
        self.assertEqual(len(gates),1)
        expected=ast.parse('significance = map_feedback_intensity_significance(r, mode)\n'
            'if significance is None or not significance < max_i_over_sigma:\n'
            '    corrected_reflections.append(r)\n    continue').body
        self.assertEqual([ast.dump(n) for n in gates[0].body],[ast.dump(n) for n in expected])
        gates[0].body=ast.parse('if r.value <= 0 or not math.isfinite(float(r.value)) or r.sigma is None or r.sigma <= 0 or not math.isfinite(float(r.sigma)) or (float(r.value) / float(r.sigma)) >= max_i_over_sigma:\n'
            '    corrected_reflections.append(r)\n    continue').body
        self.assertEqual(ast.dump(current),ast.dump(original))

    def test_amplitude_threshold_zero_preserves_existing_damping_and_zero_behavior(self):
        a=self.a
        rows=[a.Reflection(i,0,0,f,None,23.) for i,f in enumerate([0.,4.,6.],1)]
        out,_=self.feedback(rows,a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,0,.5)
        # Original median scale = median(16/16,36/4) = 5; no significance gate.
        self.assertAlmostEqual(out[0].value,math.sqrt(10))
        self.assertAlmostEqual(out[1].value,math.sqrt(48))
        self.assertAlmostEqual(out[2].value,math.sqrt(28))
        self.assertEqual([(r.value,r.sigma,r.phase) for r in rows],[(0.,None,23.),(4.,None,23.),(6.,None,23.)])
        measured=[a.Reflection(r.h,0,0,r.value,1.,r.phase) for r in rows]
        gated,_=self.feedback(measured,a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,2.5,.5)
        self.assertEqual(gated[0].value,0.)
        self.assertAlmostEqual(gated[1].value,math.sqrt(48))
        self.assertEqual(gated[2].value,6.)

    def test_fwhm_can_only_use_existing_uncertainty_independent_mode(self):
        rows = [self.a.Reflection(i,0,0,v,.0527) for i,v in enumerate([10.,20.,30.],1)]
        out,_ = self.feedback(rows,self.a.REFLECTION_DATA_MODE_INTENSITY_FWHM,0)
        self.assertEqual([r.value for r in out],[10.,30.,20.])
        self.assertEqual([r.sigma for r in out],[.0527]*3)
        with self.assertRaisesRegex(ValueError,'FWHM'):
            self.feedback(rows,self.a.REFLECTION_DATA_MODE_INTENSITY_FWHM,2)
        with self.assertRaisesRegex(ValueError,'FWHM'):
            self.feedback(rows,self.a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM,2)

    def test_nonfinite_or_missing_uncertainties_do_not_pass_significance_filter(self):
        for sigma in [None,0,-1,float('nan'),float('inf')]:
            rows = [self.a.Reflection(i,0,0,v,sigma) for i,v in enumerate([10.,20.,30.],1)]
            with self.assertRaisesRegex(ValueError,'measured uncertainties'):
                self.feedback(rows,self.a.REFLECTION_DATA_MODE_INTENSITY,100)
        rows=[self.a.Reflection(1,0,0,10,float('nan')),self.a.Reflection(2,0,0,20,10),self.a.Reflection(3,0,0,30,None)]
        out,_=self.feedback(rows,self.a.REFLECTION_DATA_MODE_INTENSITY,2.5)
        self.assertEqual([r.value for r in out],[10.,30.,30.])

    def test_zero_sentinel_does_not_secretly_filter_zero_observed_values(self):
        # Historical code also corrects zero observations if the map predicts
        # a positive intensity. Do not falsely label the mode "nonzero only".
        rows = [self.a.Reflection(1,0,0,0,None),self.a.Reflection(2,0,0,20,None)]
        out,_ = self.feedback(rows,self.a.REFLECTION_DATA_MODE_INTENSITY,0)
        self.assertGreater(out[0].value,0)

    def input_file(self, powder=True):
        from test_wizard_text_clipping import write_inflip
        path = write_inflip(self.root)
        if powder:
            path.write_text(path.read_text().replace('dataformat amplitude','dataformat intensity fwhm'),encoding='utf8')
        return path

    def wizard(self, powder=True):
        from PySide6.QtWidgets import QDialog
        w = self.j._JanaWorkflowWizard([],self.input_file(powder))
        with patch.object(QDialog,'exec',return_value=QDialog.Rejected): w.run()
        w.dialog.show()
        for _ in range(20): self.qtapp.processEvents()
        w.cycles.setValue(3)
        w.workflow_state['key'] = self.j.WORKFLOW_SUPERFLIP_SHARPED
        w.model_cache['loaded'] = True
        models = ['PEAK A (model prediction)','SEED (cyclic CF)']
        w.model_catalog['values'] = tuple(models)
        w.model_catalog['provenance'] = 'offline'
        w.model.addItems(models)
        w.model_policy_error = ''
        w._go_to_map_feedback()
        self.addCleanup(w.dialog.close)
        for _ in range(10): self.qtapp.processEvents()
        return w

    def test_feedback_noop_messages_keep_original_values(self):
        w=self.wizard(powder=False)
        w.intensity_enabled_checkbox.setChecked(True)
        self.assertEqual(w.intensity_damping_spin.value(),0)
        self.assertIn('No intensity correction',w.intensity_effective_note.text())
        w.intensity_damping_spin.setValue(.3)
        self.assertIn('positive damping',w.intensity_effective_note.text())
        w.missing_enabled_checkbox.setChecked(True)
        self.assertIn('No additions',w.missing_form.labelForField(w.missing_percent_spin).text())
        w.missing_percent_spin.setValue(5)
        self.assertNotIn('No additions',w.missing_form.labelForField(w.missing_percent_spin).text())
        powder=self.wizard()
        self.assertTrue(powder.intensity_enabled_checkbox.isEnabled())
        self.assertIn('no σ filter',powder.intensity_enabled_checkbox.text())
        powder.powder_enabled_checkbox.setChecked(True)
        powder.powder_mix_spin.setValue(0)
        self.assertIn('No repartitioning',powder.powder_form.labelForField(powder.powder_mix_spin).text())

    def test_dynamic_warning_cycles_order_and_noop_states(self):
        w = self.wizard()
        before = w.inflip_path.read_bytes()
        self.assertIn('Map Feedback disabled', w.map_feedback_warning_text.text())
        self.assertNotIn('Scientific warning', w.map_feedback_warning_text.text())
        self.assertNotIn('→', w.feedback_cycle_summary.text())
        self.assertIn('degrees 2θ', w.page3_description.text())
        self.assertIn('experimental', w.intensity_group.title())
        w.intensity_enabled_checkbox.setChecked(True)
        self.assertIn('no effect', w.map_feedback_warning_text.text())
        w.intensity_damping_spin.setValue(.4)
        self.assertIn('Scientific warning', w.map_feedback_warning_text.text())
        self.assertIn('cycles 2–3', w.feedback_cycle_summary.text())
        self.assertNotIn('powder repartitioning', w.feedback_cycle_summary.text())
        w.powder_enabled_checkbox.setChecked(True)
        self.assertIn('no effect: Powder repartitioning', w.map_feedback_warning_text.text())
        w.powder_wavelength_spin.setValue(1.541866)
        self.assertEqual(w.powder_wavelength_spin.value(), 1.541866)
        self.assertIn('intensity correction → powder repartitioning → next cycle', w.feedback_cycle_summary.text())
        w.powder_start_cycle_spin.setValue(2)
        self.assertIn('Powder repartitioning may affect cycles 3', w.feedback_cycle_summary.text())
        w.cycles.setValue(2)
        self.assertEqual(w.powder_start_cycle_spin.value(), 2)
        self.assertIn('subsequent cycle', w._check_page3_validity())
        w.cycles.setValue(1)
        self.assertIn('Map Feedback disabled', w.map_feedback_warning_text.text())
        self.assertIn('at least 2 cycles', w.feedback_applicability_note.text())
        w.cycles.setValue(3)
        self.assertEqual(w.powder_start_cycle_spin.value(), 2)
        self.assertEqual(w.intensity_damping_spin.value(), .4)
        self.assertEqual(w.inflip_path.read_bytes(), before)
        w.powder_enabled_checkbox.setChecked(False)
        w.intensity_enabled_checkbox.setChecked(False)
        self.assertFalse(w.intensity_note.isVisible())
        self.assertFalse(w.powder_note.isVisible())

    def test_powder_panels_independent_and_no_fake_sigma(self):
        w = self.wizard()
        self.assertTrue(w.intensity_group.isVisible() and w.powder_group.isVisible())
        self.assertFalse(w.feedback_has_uncertainty)
        w.intensity_enabled_checkbox.setChecked(True)
        self.assertFalse(w.powder_enabled_checkbox.isChecked())
        self.assertTrue(w.intensity_parameters.isVisible())
        self.assertFalse(w.intensity_sigma_spin.isEnabled())
        w.powder_enabled_checkbox.setChecked(True)
        self.assertTrue(w.intensity_enabled_checkbox.isChecked())
        self.assertTrue(w.powder_parameters.isVisible())
        w.intensity_enabled_checkbox.setChecked(False)
        self.assertTrue(w.powder_enabled_checkbox.isChecked())
        self.assertFalse(w.intensity_parameters.isVisible())

    def test_single_crystal_keeps_completion_and_actual_uncertainty_gate(self):
        w = self.wizard(False)
        self.assertTrue(w.missing_group.isVisible() and w.intensity_group.isVisible())
        self.assertFalse(w.powder_group.isVisible())
        self.assertTrue(w.feedback_has_uncertainty)
        w.intensity_enabled_checkbox.setChecked(True)
        self.assertTrue(w.intensity_sigma_spin.isEnabled())
        self.assertEqual(w.intensity_form.labelForField(w.intensity_sigma_spin).text(),'I/σ(I) limit')
        self.assertIn('first-order approximation',w.intensity_note.text())
        self.assertIn('F/[2σ(F)]',w.intensity_sigma_spin.toolTip())

    def test_stale_legacy_reflection_mode_cannot_override_embedded_fwhm(self):
        path = self.input_file(powder=False)
        text = path.read_text(encoding='utf8')
        text = text.replace('dataformat amplitude', 'reflection_data_mode intensity\ndataformat intensity fwhm')
        path.write_text(text, encoding='utf8')
        loaded = self.a.build_hkl_load_result(
            self.a.build_hkl_analysis_request_from_inflip(path, work_dir=self.root)
        )
        self.assertEqual(loaded.data_mode, self.a.REFLECTION_DATA_MODE_INTENSITY_FWHM)
        self.assertTrue(loaded.format_verified)
        self.assertTrue(loaded.diagnostics.data_type.startswith('Powder'))
        self.assertFalse(loaded.diagnostics.available('significance'))
        from types import SimpleNamespace
        run_config = SimpleNamespace(input_source_mode=self.a.INPUT_MODE_INFLIP,
            reflection_data_mode=self.a.REFLECTION_DATA_MODE_AUTO, hkl=Path(''), jana_inflip=path)
        effective_mode = self.a.IterativeSuperflipPipelineQtGUI._resolve_configured_data_mode(object(), run_config)
        self.assertEqual(effective_mode, self.a.REFLECTION_DATA_MODE_INTENSITY_FWHM)
        from PySide6.QtWidgets import QDialog
        w = self.j._JanaWorkflowWizard([], path)
        with patch.object(QDialog, 'exec', return_value=QDialog.Rejected): w.run()
        w.input_reflections = loaded.reflections
        w.hkl_load_result = loaded
        w._go_to_map_feedback()
        for _ in range(5): self.qtapp.processEvents()
        w._sync_page3_for_data_type()
        self.assertEqual(w._detect_reflection_data_mode(), loaded.data_mode)
        self.assertEqual(w.reflection_type_value.text(), 'Powder / polycrystalline')
        self.assertEqual(w.reflection_format_value.text(), self.a.format_reflection_data_mode(loaded.data_mode))
        self.assertIn('FWHM is not measurement uncertainty', w.page3_description.text())
        self.assertFalse(w.feedback_has_uncertainty)
        self.assertFalse(w.intensity_sigma_spin.isEnabled())
        self.assertFalse(w.missing_group.isVisible())
        self.assertFalse(w.powder_group.isHidden())
        w.model_cache['loaded'] = True
        w.model_catalog['values'] = ('PEAK A (model prediction)',)
        w.model.addItem('PEAK A (model prediction)')
        w.model.setCurrentIndex(0)
        w.model_policy_error = ''
        w.intensity_enabled_checkbox.setChecked(True)
        w.intensity_sigma_spin.setValue(7.0)
        self.assertEqual(w.intensity_sigma_spin.value(), 7.0)
        w.workflow_state['key'] = self.j.WORKFLOW_PHASE_RECYCLING
        w.cycles.setValue(3)
        w.powder_enabled_checkbox.setChecked(True)
        options = w._build_options('recycle')
        self.assertEqual(options.intensity_sigma_threshold, 0.0)
        self.assertTrue(options.enable_powder_repartition)
        w.dialog.close()

    def test_embedded_declared_layout_rejects_extra_inconsistent_columns(self):
        path = self.input_file(powder=False)
        rows = path.read_text(encoding='utf8').replace('dataformat amplitude', 'dataformat intensity fwhm')
        lines = rows.splitlines()
        first = lines.index('fbegin') + 1
        lines[first] += ' 0.5'
        rows = '\n'.join(lines) + '\n'
        path.write_text(rows, encoding='utf8')
        self.assertIsNone(self.a._verified_embedded_reflection_data_mode_from_inflip(path))
        request = self.a.build_hkl_analysis_request_from_inflip(path, work_dir=self.root)
        with self.assertRaisesRegex(ValueError, 'could not be verified'):
            self.a.build_hkl_load_result(request)
        from types import SimpleNamespace
        run_config = SimpleNamespace(input_source_mode=self.a.INPUT_MODE_INFLIP,
            reflection_data_mode=self.a.REFLECTION_DATA_MODE_AUTO, hkl=Path(''), jana_inflip=path,
            map_feedback_intensity_enabled=True)
        with self.assertRaisesRegex(ValueError, 'could not be verified'):
            self.a.IterativeSuperflipPipelineQtGUI._resolve_configured_data_mode(object(), run_config)

    def test_declared_dataitemwidths_phase_sigma_layout_remains_verified(self):
        path = self.input_file(powder=False)
        lines = path.read_text(encoding='utf8').splitlines()
        lines = [line for line in lines if line.strip() != 'dataformat amplitude']
        begin = lines.index('fbegin')
        lines.insert(begin, 'dataitemwidths 4 15 15')
        for index in range(begin + 1, len(lines)):
            if lines[index].strip() == 'endf':
                break
            fields = lines[index].split()
            lines[index] = ' '.join(fields[:4] + ['0.0', '1.0'])
        path.write_text('\n'.join(lines) + '\n', encoding='utf8')
        loaded = self.a.build_hkl_load_result(
            self.a.build_hkl_analysis_request_from_inflip(path, work_dir=self.root)
        )
        self.assertEqual(loaded.data_mode, self.a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA)
        self.assertTrue(loaded.format_verified)
        self.assertEqual(loaded.reflections[0].phase, 0.0)
        self.assertEqual(loaded.reflections[0].sigma, 1.0)

    def test_unverified_map_feedback_does_not_fabricate_type_or_sigma(self):
        path = self.input_file(powder=False)
        path.write_text(path.read_text(encoding='utf8').replace('dataformat amplitude', ''), encoding='utf8')
        from PySide6.QtWidgets import QDialog
        w = self.j._JanaWorkflowWizard([], path)
        with patch.object(QDialog, 'exec', return_value=QDialog.Rejected): w.run()
        w.hkl_load_result = None
        w.input_reflections = []
        w._sync_page3_for_data_type()
        self.assertEqual(w.reflection_type_value.text(), 'Not verified')
        self.assertFalse(w.feedback_has_uncertainty)
        self.assertFalse(w.intensity_sigma_spin.isEnabled())
        self.assertFalse(w.missing_group.isVisible())
        w.dialog.close()

    def test_full_configuration_uses_same_intensity_significance_unit(self):
        a=self.a
        with patch.object(a.IterativeSuperflipPipelineQtGUI,'load_settings'),patch.object(a.IterativeSuperflipPipelineQtGUI,'save_settings'),patch.object(a.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models'):
            win=a.IterativeSuperflipPipelineQtGUI()
        self.addCleanup(win.close)
        win.inputs['map_feedback_intensity_enabled'].setChecked(True)
        from PySide6.QtWidgets import QLabel
        self.assertTrue(any(label.text()=='I/σ(I) limit' for label in win.findChildren(QLabel)))
        self.assertIn('I/σ(I) ≈ F/[2σ(F)]',win.inputs['map_feedback_intensity_max_i_over_sigma'].toolTip())
        from PySide6.QtCore import QSettings
        settings=QSettings(str(self.root/'existing-settings.ini'),QSettings.IniFormat)
        key='inputs/map_feedback_intensity_max_i_over_sigma'
        settings.setValue(key,'3.0')
        settings.setValue('inputs/reflection_data_mode',a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA)
        win.settings=settings
        with patch.object(win,'refresh_sharped_models'):
            a.IterativeSuperflipPipelineQtGUI.load_settings(win)
        self.assertEqual(win.inputs['map_feedback_intensity_max_i_over_sigma'].value(),3.)
        a.IterativeSuperflipPipelineQtGUI.save_settings(win)
        self.assertEqual(float(settings.value(key)),3.)

    def test_one_cycle_collapses_parameters_preserves_values_and_does_not_block(self):
        w = self.wizard()
        w.powder_enabled_checkbox.setChecked(True)
        w.intensity_enabled_checkbox.setChecked(True)
        w.intensity_damping_spin.setValue(.4)
        w.cycles.setValue(1)
        w.model_policy_error = ''
        self.assertFalse(w.intensity_parameters.isVisible() or w.powder_parameters.isVisible())
        self.assertFalse(w.intensity_enabled_checkbox.isEnabled() or w.powder_enabled_checkbox.isEnabled())
        self.assertIsNone(w._check_page3_validity())
        w.cycles.setValue(3)
        self.assertEqual(w.intensity_damping_spin.value(),.4)
        self.assertEqual(w.intensity_start_cycle_spin.maximum(),2)
        self.assertTrue(w.intensity_parameters.isVisible() and w.powder_parameters.isVisible())

    def test_invalid_wavelength_blocks_active_powder_only(self):
        w = self.wizard()
        w.powder_enabled_checkbox.setChecked(True)
        self.assertIn('positive wavelength',w._check_page3_validity())
        w.powder_wavelength_spin.setValue(1.5406)
        self.assertIsNone(w._check_page3_validity())
        w.powder_wavelength_spin.setValue(0)
        w.powder_enabled_checkbox.setChecked(False)
        self.assertIsNone(w._check_page3_validity())

    def test_expanded_form_geometry_and_fixed_footer(self):
        from PySide6.QtWidgets import QLabel
        from PySide6.QtCore import QPoint
        w=self.wizard()
        w._adjust_dialog_size=lambda:None
        w.intensity_enabled_checkbox.setChecked(True);w.intensity_damping_spin.setValue(.3)
        w.powder_enabled_checkbox.setChecked(True);w.powder_wavelength_spin.setValue(1.)
        for width,height in [(900,820),(740,580)]:
            w.dialog.resize(width,height)
            for _ in range(20):self.qtapp.processEvents()
            w._size_stack_to_current_page(w.dialog.width())
            for _ in range(20):self.qtapp.processEvents()
            self.assertFalse(w.scroll_area.isAncestorOf(w.footer))
            self.assertTrue(w.footer.isVisible())
            self.assertFalse(w.scroll_area.horizontalScrollBar().isVisible())
            for group in [w.intensity_group,w.powder_group]:
                for label in group.findChildren(QLabel):
                    if not label.isVisible():continue
                    need=label.heightForWidth(label.width()) if label.wordWrap() else label.fontMetrics().height()
                    self.assertGreaterEqual(label.height(),need)
                    at=label.mapTo(group,QPoint())
                    self.assertGreaterEqual(at.x(),0)
                    self.assertLessEqual(at.x()+label.width(),group.width())
    def test_one_cycle_and_zero_mode_submission(self):
        from PySide6.QtWidgets import QDialog
        for cycles in [1,3]:
            w=self.j._JanaWorkflowWizard([],self.input_file())
            loaded=self.a.build_hkl_load_result(
                self.a.build_hkl_analysis_request_from_inflip(w.inflip_path,work_dir=self.root))
            w.hkl_load_result=loaded
            w.input_reflections=loaded.reflections
            def configure(dialog):
                w.workflow_state['key']=self.j.WORKFLOW_SUPERFLIP_SHARPED
                w.cycles.setValue(cycles)
                w.intensity_enabled_checkbox.setChecked(True)
                w.powder_enabled_checkbox.setChecked(True)
                w.intensity_sigma_spin.setValue(7)
                w._sync_page3_for_data_type()
                w.result['action']='phase_recycling'
                return QDialog.Accepted
            with patch.object(QDialog,'exec',configure): options=w.run()
            self.assertEqual(options.enable_intensity_correction,cycles>1)
            self.assertEqual(options.enable_powder_repartition,cycles>1)
            self.assertEqual(options.intensity_sigma_threshold,0)
            w.dialog.close()

    def test_automatic_wavelength_uses_matching_project_m90_and_keeps_precision(self):
        w=self.wizard()
        w.inflip_path.with_suffix('.m90').write_text('datblock Block1\nlambda 1.541866\nend\n',encoding='utf8')
        w.powder_enabled_checkbox.setChecked(True)
        w.powder_wavelength_spin.setValue(0)
        self.assertEqual(w._map_feedback_wavelength()[0],1.541866)
        self.assertIsNone(w._check_page3_validity())
        from PySide6.QtWidgets import QDialog
        path=self.input_file()
        path.with_suffix('.m90').write_text('lambda 1.541866\nend\n',encoding='utf8')
        submitted=self.j._JanaWorkflowWizard([],path)
        def configure(dialog):
            submitted.workflow_state['key']=self.j.WORKFLOW_SUPERFLIP_SHARPED
            submitted.cycles.setValue(3)
            submitted.powder_enabled_checkbox.setChecked(True)
            submitted.result['action']='phase_recycling'
            return QDialog.Accepted
        with patch.object(QDialog,'exec',configure): options=submitted.run()
        self.assertEqual(submitted.powder_wavelength_spin.value(),0)
        self.assertEqual(options.powder_wavelength,1.541866)
        submitted.dialog.close()

    def test_actual_cycle_engine_combines_methods_and_retries_without_double_application(self):
        import gemmi
        import numpy as np
        from test_jana_completion import make_run_config, CIF
        from phase_studio.xplor_io import XplorMap
        a=self.a
        for intensity,powder,fail_powder,cycles,start in [(True,False,False,2,1),(False,True,False,2,1),(True,True,False,2,1),(True,True,True,2,1),(True,True,False,3,2)]:
            with self.subTest(intensity=intensity,powder=powder,retry=fail_powder):
                work=self.root/f'engine-{intensity}-{powder}-{fail_powder}-{cycles}-{start}'
                work.mkdir()
                inflip=work/'input.inflip';inflip.write_text('title fixture\n')
                cfg=make_run_config(a,work,inflip)
                cfg.cycles=cycles;cfg.reconstruction_mode='superflip';cfg.referencefile_mode='omit'
                cfg.modelfile_source='none';cfg.map_export_format='xplor';cfg.structure_export_format='cif'
                cfg.reflection_data_mode=a.REFLECTION_DATA_MODE_INTENSITY_FWHM
                cfg.run_sharped=False;cfg.run_edma_superflip=False;cfg.run_edma_deblurred=False
                cfg.map_feedback_intensity_enabled=intensity;cfg.map_feedback_intensity_from_cycle=start
                cfg.map_feedback_intensity_damping=.5;cfg.map_feedback_intensity_max_i_over_sigma=0
                cfg.redistribute_overlaps=powder;cfg.powder_redistribution_from_cycle=start
                cfg.powder_wavelength=1.;cfg.powder_separation_factor=.2;cfg.powder_redistribution_mix=1.
                rows=[a.Reflection(1,0,0,10.,.1),a.Reflection(0,1,0,20.,.1)]
                observed=work/'original.hkl';observed.write_text('1 0 0 10 .1\n0 1 0 20 .1\n')
                original=observed.read_bytes()
                cell=gemmi.UnitCell(10,10,10,90,90,90)
                context=a.ReferenceContext(work/'ref.cif',work/'ref.cif',cell,gemmi.SpaceGroup('P 1'),'P 1','C 1',[])
                state=a.PipelineState(cfg=cfg,ref_ctx=context,observed_hkls={cfg.reflection_data_mode:observed},
                    configured_data_mode=cfg.reflection_data_mode,referencefile_mode='omit',explicit_superflip_referencefile=None,
                    modelfile_mode='none',use_xplor_modelfile=False,use_cif_modelfile=False,use_superflip_xplor_modelfile=False,
                    sharped_elements='C',exclude_labels=[],progress_stages=a.cycle_progress_stages(cfg),current_reflections=rows)
                coordinates=np.indices((16,16,16))
                data=np.cos(2*np.pi*coordinates[0]/16)+2*np.cos(2*np.pi*coordinates[1]/16)
                xmap=XplorMap('feedback fixture',(16,0,15,16,0,15,16,0,15),(10,10,10,90,90,90),'ZYX',data)
                source_map=work/'source.xplor';a.write_xplor_map(source_map,xmap)
                expected=rows
                if intensity: expected,_=a.apply_map_feedback_to_reflections(expected,cfg.reflection_data_mode,source_map,cell,0,False,0,True,.5,0,lambda s:None)
                if powder: expected,_=a.redistribute_overlap_reflections(expected,cfg.reflection_data_mode,source_map,cell,1.,.2,1.,lambda s:None)
                calls=[];inputs=[];powder_calls=[0]
                real_intensity=a.apply_map_feedback_to_reflections;real_powder=a.redistribute_overlap_reflections
                def flip(directory,prefix,_context,input_hkl,*args,**kwargs):
                    inputs.append((prefix,Path(input_hkl)))
                    path=Path(directory)/(prefix+'.xplor');a.write_xplor_map(path,xmap);return path
                def correct(*args,**kwargs):
                    calls.append('intensity');return real_intensity(*args,**kwargs)
                def repartition(*args,**kwargs):
                    calls.append('powder');powder_calls[0]+=1
                    if fail_powder and powder_calls[0]==1: raise RuntimeError('controlled powder failure')
                    return real_powder(*args,**kwargs)
                def structure(path,*args,**kwargs):
                    Path(path).parent.mkdir(parents=True,exist_ok=True)
                    Path(path).write_text(CIF,encoding='utf8')
                with patch.object(a.IterativeSuperflipPipelineQtGUI,'load_settings'),patch.object(a.IterativeSuperflipPipelineQtGUI,'save_settings'):
                    win=a.IterativeSuperflipPipelineQtGUI()
                self.addCleanup(win.close)
                with patch.object(a,'run_superflip_cycle',side_effect=flip),patch.object(a,'parse_superflip_cycle_metrics',return_value=a.SuperflipLogMetrics()), \
                     patch.object(a,'export_phased_reflections_from_map'),patch.object(a,'write_structure_bundle',side_effect=structure), \
                     patch.object(a,'write_metrics_csv'),patch.object(a,'write_map_quality_report'), \
                     patch.object(a,'apply_map_feedback_to_reflections',side_effect=correct),patch.object(a,'redistribute_overlap_reflections',side_effect=repartition):
                    if fail_powder:
                        with self.assertRaisesRegex(RuntimeError,'controlled powder failure'): win._run_pipeline_cycles(state)
                        self.assertEqual([r.value for r in state.current_reflections],[10.,20.])
                    win._run_pipeline_cycles(state)
                sequence=(['intensity'] if intensity else [])+(['powder'] if powder else [])
                self.assertEqual(calls,sequence*(2 if fail_powder else 1))
                self.assertEqual([prefix for prefix,_ in inputs],[f'cycle_{n:03d}_superflip' for n in range(1,cycles+1)])
                derived=work/f'cycle_{cycles:03d}_map_feedback_for_superflip.hkl'
                self.assertEqual(inputs[-1][1],derived)
                if start==2:self.assertEqual(inputs[1][1],observed)
                self.assertTrue(derived.is_file())
                written=a.read_hkl(derived,value_col=4,sigma_col=5,include_000=False)
                actual={(r.h,r.k,r.l):r for r in written}
                for r in expected:
                    self.assertAlmostEqual(actual[(r.h,r.k,r.l)].value,r.value,places=5)
                    self.assertEqual(actual[(r.h,r.k,r.l)].sigma,r.sigma)
                self.assertEqual(observed.read_bytes(),original)
                self.assertEqual([r.value for r in rows],[10.,20.])
                self.assertEqual(state.completed_cycles,cycles)

    def test_real_project_powder_metadata_and_original_input_unchanged(self):
        source=os.environ.get('PHASE_STUDIO_TEST_INFLIP')
        if not source: self.skipTest('opt-in real project')
        from shutil import copyfile
        source=Path(source);original=source.read_bytes()
        local=self.root/source.name;copyfile(source,local)
        m90=source.with_suffix('.m90')
        if m90.is_file():copyfile(m90,local.with_suffix('.m90'))
        request=self.a.build_hkl_analysis_request_from_inflip(local,work_dir=self.root)
        result=self.a.build_hkl_load_result(request)
        self.assertEqual(result.data_mode,self.a.REFLECTION_DATA_MODE_INTENSITY_FWHM)
        self.assertGreater(len(result.reflections),0)
        from PySide6.QtWidgets import QDialog
        w=self.j._JanaWorkflowWizard([],local)
        with patch.object(QDialog,'exec',return_value=QDialog.Rejected):w.run()
        w.dialog.show()
        for _ in range(20):self.qtapp.processEvents()
        w.cycles.setValue(3);w._go_to_map_feedback()
        self.assertTrue(w.powder_group.isVisible() and w.intensity_group.isVisible())
        self.assertFalse(w.feedback_has_uncertainty)
        w.intensity_enabled_checkbox.setChecked(True)
        self.assertFalse(w.intensity_sigma_spin.isEnabled())
        if m90.is_file():self.assertEqual(w._map_feedback_wavelength()[0],self.a.parse_m90_wavelength(m90))
        self.assertEqual([(r.value,r.sigma) for r in w.input_reflections],[(r.value,r.sigma) for r in result.reflections])
        self.assertEqual(source.read_bytes(),original)
        real_map=os.environ.get('PHASE_STUDIO_TEST_MAP')
        if real_map:
            import hashlib
            map_path=Path(real_map);map_hash=hashlib.sha256(map_path.read_bytes()).hexdigest()
            before=[(r.h,r.k,r.l,r.value,r.sigma) for r in result.reflections]
            corrected,change=self.a.apply_map_feedback_to_reflections(result.reflections,result.data_mode,map_path,result.cell,0,False,0,True,.3,0,lambda s:None)
            wavelength,_source=w._map_feedback_wavelength()
            combined,powder_change=self.a.redistribute_overlap_reflections(corrected,result.data_mode,map_path,result.cell,wavelength,.2,1.,lambda s:None)
            self.assertEqual([(r.h,r.k,r.l,r.sigma) for r in combined],[(r.h,r.k,r.l,r.sigma) for r in result.reflections])
            self.assertEqual([(r.h,r.k,r.l,r.value,r.sigma) for r in result.reflections],before)
            self.assertEqual(hashlib.sha256(map_path.read_bytes()).hexdigest(),map_hash)
            self.assertIsNotNone(change)
            derived=self.root/'real-project-map-feedback.hkl'
            count=self.a.write_observed_reflections(derived,combined,0,data_mode=result.data_mode,cell=result.cell)
            round_trip=self.a.read_hkl(derived,value_col=4,sigma_col=5,include_000=False)
            self.assertEqual(len(round_trip),count)
            self.assertEqual([(r.h,r.k,r.l,r.sigma) for r in round_trip],[(r.h,r.k,r.l,r.sigma) for r in combined if (r.h,r.k,r.l)!=(0,0,0)])
            print(f'REAL MAP: {map_path.name}, SHA256 {map_hash}; intensity change {change:.8g}%; powder change {powder_change}; wavelength {wavelength:.10g}; {len(combined)} derived reflections; source map unchanged')
        print(f'REAL INPUT: {source.name}, {len(result.reflections)} parsed reflections; original bytes unchanged')
        w.dialog.close()

if __name__=='__main__': unittest.main()
