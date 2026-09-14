"""Regression coverage for measured Phase Studio workflow overhead fixes."""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


class PerformanceRegressionTests(unittest.TestCase):
    def test_sharped_polling_only_accelerates_the_bounded_early_window(self):
        from phase_studio.sharped_server_client import polling_delay_seconds

        self.assertEqual([polling_delay_seconds(i, 2) for i in range(1, 6)],
                         [1.0, 1.0, 2.0, 2.0, 2.0])
        self.assertEqual([polling_delay_seconds(i, 1) for i in range(1, 5)],
                         [1.0, 1.0, 1.0, 1.0])

    def test_phase_recycling_reuses_the_map_already_loaded_for_composition(self):
        import gemmi
        from phase_studio import app

        temp = Path(tempfile.mkdtemp())
        source = temp / "source.xplor"
        output = temp / "output.xplor"
        expected_output = temp / "expected.xplor"
        grid = (8, 0, 7, 8, 0, 7, 8, 0, 7)
        cell = (10.0, 11.0, 12.0, 90.0, 90.0, 90.0)
        values = np.linspace(-2.0, 3.0, 8 ** 3, dtype=np.float64)
        app.write_xplor_map(source, app.XplorMap("fixture", grid, cell, "ZYX", values))
        reflections = [
            app.Reflection(1, 0, 0, 10.0, 1.0),
            app.Reflection(0, 1, 0, 12.0, 1.0),
            app.Reflection(1, 1, 1, 8.0, 1.0),
        ]

        loaded = app.read_xplor_map(source)
        hkls = [(r.h, r.k, r.l) for r in reflections]
        old_predictions = app.xplor_fft_predictions(source, hkls)
        expected, _used = app.synthesize_xplor_map_from_phases(
            reflections,
            app.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
            loaded.grid,
            loaded.cell,
            loaded.axis_order,
            {hkl: phase for hkl, (_intensity, phase) in old_predictions.items()},
            "composed",
            gemmi.SpaceGroup("P 1"),
        )

        reads = 0
        original_read = app.read_xplor_map

        def counted_read(path):
            nonlocal reads
            reads += 1
            return original_read(path)

        with patch.object(app, "read_xplor_map", counted_read):
            app.compose_fobs_phicalc_map(
                output,
                reflections,
                app.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
                source,
                "composed",
                gemmi.SpaceGroup("P 1"),
                lambda _message: None,
            )

        actual = original_read(output)
        app.write_xplor_map(expected_output, expected)
        serialized_expected = original_read(expected_output)
        self.assertEqual(reads, 1)
        self.assertEqual(actual.grid, serialized_expected.grid)
        self.assertTrue(np.array_equal(actual.data, serialized_expected.data))

    def test_profiler_is_silent_by_default_and_reports_nested_owned_time(self):
        from phase_studio.performance import WorkflowProfiler

        temp = Path(tempfile.mkdtemp())
        disabled = WorkflowProfiler(False)
        with disabled.stage("unused"):
            pass
        self.assertEqual(disabled.records, [])
        self.assertIsNone(disabled.write_report(temp / "disabled.txt"))
        self.assertFalse((temp / "disabled.txt").exists())

        profiler = WorkflowProfiler(True)
        root = profiler.start("Total workflow")
        with profiler.stage("Phase Studio preparation"):
            time.sleep(0.001)
        with profiler.stage("Superflip process", "external"):
            time.sleep(0.001)
        self.assertIsNotNone(root)
        root.stop()
        report_path = profiler.write_report(temp / "workflow_performance.txt")
        report = report_path.read_text(encoding="utf-8")
        self.assertIn("External computation/network wait:", report)
        self.assertIn("Phase Studio-owned overhead:", report)
        self.assertIn("Superflip process", report)

    def test_gui_queue_coalesces_rendering_with_a_short_timer(self):
        from PySide6.QtWidgets import QApplication
        from phase_studio import app as appmod
        import test_jana_completion as fixtures

        application = QApplication.instance() or QApplication([sys.argv[0]])
        window, cycle_results = fixtures.build_window(appmod, cycles=1)
        window.timer.stop()
        self.assertEqual(window.timer.interval(), 50)

        calls = {"plot": 0, "structure": 0, "actions": 0}
        window._update_plot = lambda: calls.__setitem__("plot", calls["plot"] + 1)
        window._update_structure_views = lambda: calls.__setitem__(
            "structure", calls["structure"] + 1
        )
        window._update_action_states = lambda: calls.__setitem__(
            "actions", calls["actions"] + 1
        )
        cif = cycle_results[0].superflip_edma_cif
        window.msg_queue.put(("structure_update", ("superflip", cif)))
        window.msg_queue.put(("structure_update", ("deblur", cif)))
        window.msg_queue.put(("validation_profile", "reference_free"))
        window.msg_queue.put(("validation_profile", "reference_free"))
        window.msg_queue.put(("log", "first"))
        window.msg_queue.put(("log", "second"))
        window._poll_queue()

        self.assertEqual(calls, {"plot": 1, "structure": 1, "actions": 1})
        window.close()
        application.processEvents()


if __name__ == "__main__":
    unittest.main(verbosity=2)
