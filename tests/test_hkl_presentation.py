"""Display-only amplitude additions retain every validated diagnostic field."""
from dataclasses import asdict
import csv
import json
import unittest

import test_hkl_diagnostics as fixtures
from phase_studio import app as a
from phase_studio.hkl_diagnostics import export_shell_csv
from phase_studio.hkl_diagnostics_ui import presentation_report


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.DiagnosticsTests();self.fixture.setUp()

    def tearDown(self):self.fixture.tearDown()

    def test_signed_direct_ratio_and_secondary_derived_unchanged(self):
        load=self.fixture.load('1 2 1 5 0 2\n2 2 1 -4 0 2\n3 2 1 0 0 1\n0 0 0 50 0 1\n',a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA)
        old=asdict(load.diagnostics)
        values=[(r.value,r.sigma,r.phase) for r in load.reflections]
        displayed=presentation_report(load)
        self.assertAlmostEqual(displayed.statistic('mean_f_over_sigma'),(2.5-2+0)/3)
        self.assertEqual(displayed.statistic('median_f_over_sigma'),0)
        self.assertAlmostEqual(displayed.statistic('mean_significance'),.75)
        self.assertEqual(asdict(load.diagnostics),old)
        self.assertEqual([(r.value,r.sigma,r.phase) for r in load.reflections],values)
        self.assertIs(displayed,presentation_report(load))

    def test_shell_export_keeps_old_values_and_adds_direct_full_precision(self):
        load=self.fixture.load('1 2 1 5.123456789 0 1.23456789\n2 2 1 3 0 2\n',a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA)
        analysis=a.analyze_hkl_data(load.hkl_path,load.data_mode,load.cell,load.spacegroup,load.spacegroup_hm,_loaded=load)
        original=asdict(analysis.diagnostics)
        displayed=presentation_report(analysis)
        for before,after in zip(analysis.diagnostics.shells,displayed.shells):
            after=dict(after)
            for key,value in before:self.assertEqual(value,after[key])
        path=self.fixture.root/'direct.csv';export_shell_csv(path,displayed)
        rows=list(csv.DictReader(path.open()))
        expected=5.123456789/1.23456789
        self.assertTrue(any(row['mean_f_over_sigma']==str(expected) for row in rows))
        path=self.fixture.root/'direct.json';displayed.export_json(path,analysis)
        data=json.loads(path.read_text(encoding='utf8'))
        self.assertIn('mean_f_over_sigma',dict(data['statistics']))
        self.assertEqual(asdict(analysis.diagnostics),original)

    def test_powder_has_no_new_significance(self):
        load=self.fixture.load('1 2 1 12 .05\n')
        report=presentation_report(load)
        self.assertIsNone(report.statistic('mean_f_over_sigma'))
        self.assertFalse(report.available('significance'))

    def test_missing_and_invalid_uncertainties_not_fabricated(self):
        load=self.fixture.load('1 2 1 3 0 1\n2 2 1 4 0 0\n3 2 1 5 0 -2\n4 2 1 6 0 inf\n',a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA)
        self.assertEqual(presentation_report(load).statistic('mean_f_over_sigma'),3)


if __name__=='__main__':unittest.main()
