"""Controlled crystallographic diagnostics; no phasing or network requests."""
from concurrent.futures import CancelledError
from dataclasses import replace
import json
import math
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import gemmi
import numpy as np

from phase_studio import app as a
from phase_studio import hkl_diagnostics as d


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root/'input.hkl'
        self.cell = gemmi.UnitCell(8.2512,18.8436,6.7032,90,92.58,90)
        self.sg = gemmi.SpaceGroup('P 1 21/n 1')

    def tearDown(self): self.tmp.cleanup()

    def load(self, text, mode=None, **kwargs):
        self.path.write_text(text,encoding='utf8')
        mode = mode or a.REFLECTION_DATA_MODE_INTENSITY_FWHM
        raw = list(d.read_diagnostic_reflections(self.path,mode)[0])
        columns = a.reflection_columns_for_mode(mode)
        result = a.HklLoadResult(self.path,mode,self.cell,self.sg,self.sg.xhm(),'Synthetic controlled fixture',*columns,raw,a.merge_duplicate_reflections(raw))
        result.diagnostics = d.build_diagnostics(result,**kwargs)
        return result

    def test_constant_checks_every_width_not_sample(self):
        load = self.load('\n'.join(f'{i} 2 1 {i} .0527' for i in range(1,65)))
        self.assertTrue(load.diagnostics.statistic('constant_fwhm'))
        load = self.load('\n'.join(f'{i} 2 1 {i} '+('.0527' if i<64 else '.1') for i in range(1,65)))
        self.assertFalse(load.diagnostics.statistic('constant_fwhm'))
        self.assertFalse(load.diagnostics.available('significance'))
        self.assertIsNone(load.diagnostics.statistic('median_significance'))

    def test_zero_phase_populated_and_derived_amplitude(self):
        load = self.load('1 2 1 10 0 2\n2 2 1 0 0 1\n0 0 0 5 0 1\n',a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA)
        report = load.diagnostics
        self.assertEqual(report.count('phase_finite'),3)
        self.assertEqual(report.count('zero_000'),1)
        self.assertEqual(report.statistic('median_significance'),1.25)
        self.assertIn('Derived',report.significance_label)
        self.assertIn('0° is populated',report.phase_status)

    def test_missing_uncertainty_no_poisson_or_fake_metrics(self):
        load = self.load('1 2 1 10\n2 2 1 4\n',a.REFLECTION_DATA_MODE_INTENSITY)
        self.assertFalse(load.diagnostics.available('significance'))
        self.assertEqual(load.diagnostics.count('missing_auxiliary'),2)
        for name in ('merging_statistics','profile_statistics','anomalous_completeness','wilson'):
            self.assertFalse(load.diagnostics.available(name))

    def test_dummy_sigma_not_evidence_of_measurement_uncertainty(self):
        load = self.load('1 2 1 10 1\n',a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA)
        self.assertFalse(load.diagnostics.available('significance'))

    def test_absences_use_actual_nonstandard_setting(self):
        text = '\n'.join(f'{h} {k} {l} 10 2' for h,k,l in [(0,1,0),(0,2,0),(1,0,0),(1,0,1),(2,0,0)])
        load = self.load(text,a.REFLECTION_DATA_MODE_INTENSITY)
        expected = sum(self.sg.operations().is_systematically_absent([r.h,r.k,r.l]) for r in load.reflections)
        self.assertEqual(load.diagnostics.count('systematic_absent_entries'),expected)
        self.assertEqual(load.diagnostics.count('absent_significant_3sigma'),expected)
        self.assertIn((0,1,0),load.diagnostics.absence_examples)
        # P21/n and P21/c differ for h0l: never substitute their settings.
        self.assertNotEqual(self.sg.operations().is_systematically_absent([1,0,1]),gemmi.SpaceGroup('P 1 21/c 1').operations().is_systematically_absent([1,0,1]))

    def test_duplicates_equivalents_and_friedel_policy(self):
        load = self.load('1 2 1 10 .05\n1 2 1 20 .05\n-1 -2 -1 10 .05\n')
        report = load.diagnostics
        self.assertEqual(report.count('parsed_records'),3)
        self.assertEqual(report.count('literal_unique'),2)
        self.assertEqual(report.count('symmetry_orbits'),1)
        self.assertEqual(report.count('exact_duplicate_entries'),1)
        self.assertEqual(report.count('conflicting_duplicate_groups'),1)
        self.assertFalse(report.available('merging_statistics'))
        load.spacegroup = gemmi.SpaceGroup('P 1')
        preserved = d.build_diagnostics(load,friedel_policy='preserve')
        self.assertEqual(preserved.count('symmetry_orbits'),2)
        self.assertEqual([r.value for r in load.reflections],[10,20,10])

    def test_invalid_values_indices_and_negative_intensity(self):
        load = self.load('1 2 1 -3 .05\n2 2 1 0 0\n3 2 1 nan inf\n1.5 2 1 5 .05\n4 2 1 5 -1\n5 2 1 5\n')
        report = load.diagnostics
        self.assertEqual(report.count('invalid_indices'),1)
        self.assertEqual(report.count('rejected_records'),1)
        self.assertEqual(report.count('invalid_values'),1)
        self.assertEqual(report.count('negative_values'),1)
        self.assertEqual(report.count('zero_values'),1)
        self.assertEqual(report.count('invalid_auxiliary'),3)
        self.assertEqual(report.count('missing_auxiliary'),1)
        self.assertEqual(report.statistic('mean_value'),1.75)

    def test_impossible_cell_rejected(self):
        self.cell = gemmi.UnitCell(1,1,1,10,10,170)
        with self.assertRaisesRegex(ValueError,'Invalid unit-cell'): self.load('1 2 1 10 .05\n')

    def test_overlap_needs_units_and_wavelength(self):
        load = self.load('1 2 1 10 .05\n2 2 1 20 .05\n',wavelength=1.0)
        self.assertFalse(load.diagnostics.available('overlap'))
        self.assertFalse(d.build_diagnostics(load,fwhm_units='degrees_2theta').available('overlap'))
        self.assertIn('insufficient',dict(load.diagnostics.overlap)['reason'])

    def test_estimated_overlap_reuses_authority_separated_partial_identical(self):
        load = self.load('1 2 1 10 .05\n-1 -2 -1 20 .05\n2 2 1 30 .05\n3 2 1 40 .05\n')
        for width in (.0001,5,100):
            raw = [a.Reflection(r.h,r.k,r.l,r.value,width,r.phase) for r in load.reflections]
            current = replace(load,reflections=raw)
            from phase_studio import powder_diagnostics
            with patch.object(powder_diagnostics,'superflip_overlap_groups',wraps=powder_diagnostics.superflip_overlap_groups) as grouping:
                report = d.build_diagnostics(current,fwhm_units='degrees_2theta',wavelength=1.0)
                self.assertEqual(grouping.call_count,1)
            overlap = dict(report.overlap)
            self.assertTrue(overlap['available'])
            self.assertTrue(overlap['estimated'])
            self.assertGreaterEqual(overlap['affected'],2)
            self.assertGreaterEqual(overlap['largest'],2)
            self.assertEqual(sum(size*count for size,count in overlap['size_distribution']),overlap['affected'])

    def test_supplied_groups_and_positive_integrated_fraction(self):
        load = self.load('1 2 1 10 .05\n2 2 1 20 .05\n3 2 1 30 .05\n',overlap_groups={(1,2,1):1,(2,2,1):1})
        overlap = dict(load.diagnostics.overlap)
        self.assertEqual(overlap['geometric_group_count'],2)
        self.assertEqual(overlap['integrated_intensity_fraction'],.5)
        analysis = a.analyze_hkl_data(self.path,load.data_mode,self.cell,self.sg,self.sg.xhm(),_loaded=load)
        rows = [dict(row) for row in analysis.diagnostics.shells]
        self.assertTrue(any(row['overlap_fraction']==1 for row in rows))
        self.assertTrue(any(row['overlap_fraction']==0 for row in rows))
        load.reflections[0].value = -10
        report = d.build_diagnostics(load,overlap_groups={(1,2,1):1,(2,2,1):1})
        self.assertNotIn('integrated_intensity_fraction',dict(report.overlap))

    def test_defined_shells_exports_and_original_unchanged(self):
        load = self.load('1 2 1 10 .05\n2 2 1 20 .05\n3 2 1 30 .05\n')
        before = self.path.read_bytes()
        analysis = a.analyze_hkl_data(self.path,load.data_mode,self.cell,self.sg,self.sg.xhm(),_loaded=load)
        report = analysis.diagnostics
        rows = [dict(row) for row in report.shells]
        self.assertTrue(any(row['theory']==0 and row['coverage'] is None for row in rows))
        self.assertTrue(all(row['mean_significance'] is None for row in rows))
        report.export_json(self.root/'report.json',analysis)
        d.export_shell_csv(self.root/'report.csv',report)
        exported = json.loads((self.root/'report.json').read_text(encoding='utf8'))
        self.assertEqual(exported['resolution']['d98'],analysis.d_full_98)
        self.assertIn('n/a',(self.root/'report.csv').read_text())
        self.assertEqual(before,self.path.read_bytes())

    def test_no_valid_reflections_validation_and_analysis(self):
        load = self.load('1.5 0 0 1 .05\n')
        self.assertEqual(load.diagnostics.count('parsed_records'),0)
        self.assertEqual(load.diagnostics.count('rejected_records'),1)
        with self.assertRaisesRegex(ValueError,'No non-zero HKL'): a.analyze_hkl_data(self.path,load.data_mode,self.cell,self.sg,self.sg.xhm(),_loaded=load)

    def test_cache_invalidation_by_file_metadata_format_cell(self):
        self.path.write_text('1 2 1 10 .05\n')
        metadata = a.CrystalMetadata(self.cell,self.sg,self.sg.xhm(),'','manual',None)
        request = a.HklAnalysisRequest('external',str(self.path),'','',str(self.root),a.REFLECTION_DATA_MODE_INTENSITY_FWHM,metadata)
        first = a.build_hkl_load_result(request)
        with patch.object(a,'resolve_hkl_analysis_inputs',side_effect=AssertionError('reloaded')):
            self.assertIs(a.build_hkl_load_result(request),first)
        self.path.write_text('1 2 1 20 .05\n2 2 1 30 .05\n')
        second = a.build_hkl_load_result(request)
        self.assertIsNot(first,second)
        self.assertEqual(len(second.reflections),2)

    def test_cancellation_does_not_poison_cache(self):
        event = threading.Event();event.set()
        with self.assertRaises(CancelledError):
            with d.diagnostic_cancellation(event): self.load('1 2 1 10 .05\n')
        self.assertEqual(len(self.load('1 2 1 10 .05\n').reflections),1)

    def test_custom_significance_thresholds(self):
        load = self.load('1 2 1 2 1\n2 2 1 8 1\n',a.REFLECTION_DATA_MODE_INTENSITY,weak_thresholds=(2.5,))
        self.assertEqual(load.diagnostics.statistic('weak_fraction_below_2.5'),.5)
        with self.assertRaises(ValueError): d.build_diagnostics(load,weak_thresholds=(float('nan'),))

    def test_auto_filename_guess_is_not_uncertainty_evidence(self):
        self.path.write_text('1 2 1 20 .05\n2 2 1 10 .1\n')
        metadata = a.CrystalMetadata(self.cell,self.sg,self.sg.xhm(),'','manual',None)
        request = a.HklAnalysisRequest('external',str(self.path),'','',str(self.root),a.REFLECTION_DATA_MODE_AUTO,metadata)
        load = a.build_hkl_load_result(request)
        self.assertFalse(load.diagnostics.available('column_semantics'))
        self.assertFalse(load.diagnostics.available('significance'))
        inferred = d.cached_analysis(request)
        self.assertTrue(all(dict(row)['mean_significance'] is None for row in inferred.diagnostics.shells))
        explicit = replace(request,configured_mode=a.REFLECTION_DATA_MODE_INTENSITY)
        declared = d.cached_analysis(explicit)
        self.assertTrue(declared.diagnostics.available('significance'))
        self.assertIsNot(inferred,declared)

    def test_inclusive_nonorthogonal_boundary_independent_enumeration(self):
        load = self.load('0 7 5 10 .0527\n')
        analysis = a.analyze_hkl_data(self.path,load.data_mode,self.cell,self.sg,self.sg.xhm(),_loaded=load)
        limits = [math.ceil(length/analysis.d_min)+1 for length in self.cell.parameters[:3]]
        hkls = np.array([(h,k,l) for h in range(-limits[0],limits[0]+1)
                         for k in range(-limits[1],limits[1]+1) for l in range(-limits[2],limits[2]+1)],dtype=np.int32)
        # Independent unit-cell d calculation, not the analysis metric routine.
        ds = self.cell.calculate_d_array(hkls)
        mask = np.any(hkls!=0,axis=1) & np.isfinite(ds) & (ds>=analysis.d_min*(1-1e-12)) & ~self.sg.operations().systematic_absences(hkls)
        allowed = hkls[mask].copy()
        self.sg.switch_to_asu(allowed)
        expected = len(np.unique(allowed,axis=0))
        self.assertEqual(sum(b['theory'] for b in analysis.bins),expected)
        self.assertEqual(sum(b['observed'] for b in analysis.bins),1)


if __name__=='__main__': unittest.main()
