"""Local-format provenance and read-only grouping regressions."""
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from phase_studio import app as a
from phase_studio import hkl_diagnostics as d
from phase_studio.powder_diagnostics import standard_powder_context,superflip_overlap_groups


class PowderDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.path=self.root/'project.inflip'
        self.cell=a.gemmi.UnitCell(10,10,10,90,90,90)

    def tearDown(self):self.temp.cleanup()

    def source(self,extra='',columns='intensity fwhm',rows='1 0 0 10 .1\n0 1 0 20 .1\n2 0 0 30 .1'):
        self.path.write_text('dimension 3\ncell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\n'+extra+'\ndataformat '+columns+'\nfbegin\n'+rows+'\nendf\n')
        return self.path

    def load(self):
        return a.build_hkl_load_result(a.build_hkl_analysis_request_from_inflip(self.path,work_dir=self.root/'work'))

    def test_standard_units_and_missing_wavelength(self):
        self.source()
        report=self.load().diagnostics
        self.assertEqual(report.fwhm_units,'degrees_2theta')
        self.assertFalse(report.available('overlap'))
        self.assertIn('Wavelength missing',dict(report.overlap)['reason'])
        self.assertFalse(report.available('significance'))

    def test_inflip_precedes_m90_and_metadata_cache_invalidation(self):
        self.source('lambda 1.2\nfwhmseparation .5')
        with patch.object(a,'parse_m90_wavelength',return_value=1.54):
            self.path.with_suffix('.m90').write_text('first')
            first=self.load()
            self.assertEqual(dict(first.diagnostics.overlap)['wavelength'],1.2)
            self.source()
            second=self.load()
            self.assertEqual(dict(second.diagnostics.overlap)['wavelength'],1.54)
        self.path.with_suffix('.m90').write_text('lambda 1.7\n')
        third=self.load()
        self.assertIsNot(second,third)
        self.assertEqual(dict(third.diagnostics.overlap)['wavelength'],1.7)

    def test_explicit_groups_need_no_wavelength_and_do_not_recompute(self):
        self.source(columns='intensity group',rows='1 0 0 10 7\n2 0 0 20 7\n3 0 0 30 0')
        before=self.path.read_bytes()
        with patch('phase_studio.powder_diagnostics.superflip_overlap_groups',side_effect=AssertionError('must not recompute')):
            report=self.load().diagnostics
        overlap=dict(report.overlap)
        self.assertTrue(report.available('overlap'))
        self.assertFalse(overlap.get('estimated',False))
        self.assertEqual((overlap['total_groups'],overlap['non_overlapping_groups'],overlap['group_count'],overlap['affected']),(2,1,1,2))
        self.assertEqual(overlap['fraction'],2/3)
        self.assertEqual(overlap['integrated_intensity_fraction'],.5)
        self.assertEqual(before,self.path.read_bytes())
        self.assertFalse(report.available('significance'))

    def test_invalid_metadata_is_actionable_not_defaulted(self):
        for extra in ('lambda nan','lambda -1','fwhmseparation 0','fwhmseparation inf'):
            self.source(extra)
            report=self.load().diagnostics
            self.assertFalse(report.available('overlap'))
            self.assertIn('Invalid',dict(report.overlap)['reason'])
        self.source(columns='intensity group',rows='1 0 0 10 1.5')
        self.assertIn('error',standard_powder_context(self.path))

    def test_plain_external_columns_do_not_establish_units(self):
        self.source('lambda 1')
        p=self.root/'external.hkl';p.write_text('1 0 0 10 .1\n0 1 0 20 .1')
        meta=a.resolve_crystal_metadata(a.METADATA_SOURCE_INFLIP,jana_inflip=self.path)
        request=a.HklAnalysisRequest('external',str(p),str(self.path),'',str(self.root),a.REFLECTION_DATA_MODE_INTENSITY_FWHM,meta)
        report=a.build_hkl_load_result(request).diagnostics
        self.assertEqual(report.fwhm_units,'input units')
        self.assertFalse(report.available('overlap'))

    def test_unmapped_columns_are_rejected_instead_of_guessing_width(self):
        self.source('lambda 1',columns='intensity dummy fwhm',rows='1 0 0 10 99 .1')
        with self.assertRaisesRegex(ValueError,'Unsupported diagnostic powder column order'):
            self.load()

    def test_inclusive_boundary_transitivity_and_separated(self):
        rows=[a.Reflection(i,0,0,10.,1.) for i in (1,2,3,4)]
        angles={1:10.,2:11.,3:12.,4:20.}
        with patch.object(a,'reflection_d_spacing',side_effect=lambda cell,h,k,l:h),patch.object(a,'bragg_two_theta_deg',side_effect=lambda h,w:angles[h]):
            groups=superflip_overlap_groups(rows,self.cell,1.,1.)
        self.assertEqual(groups,{(1,0,0):1,(2,0,0):1,(3,0,0):1})

    def test_identical_positions_equivalent_records_and_invalid_inputs(self):
        rows=[a.Reflection(1,0,0,10.,.01),a.Reflection(-1,0,0,20.,.01),a.Reflection(0,1,0,30.,.01)]
        groups=superflip_overlap_groups(rows,self.cell,1.,.2)
        self.assertEqual(len(groups),3)  # input records, not merged symmetry orbits
        for bad in (math.nan,math.inf,0.,-1.):
            with self.assertRaises(ValueError):superflip_overlap_groups(rows,self.cell,bad,.2)
            with self.assertRaises(ValueError):superflip_overlap_groups([a.Reflection(1,0,0,10.,bad)],self.cell,1.,.2)
        with self.assertRaises(ValueError):superflip_overlap_groups(rows+rows[:1],self.cell,1.,.2)

    def test_grouping_does_not_call_repartitioning(self):
        self.source('lambda 1')
        with patch.object(a,'assign_powder_overlap_groups',side_effect=AssertionError('Map Feedback is unchanged')):
            report=self.load().diagnostics
        self.assertEqual(dict(report.overlap)['affected'],2)
        self.assertTrue(dict(report.overlap)['estimated'])

if __name__=='__main__':unittest.main()
