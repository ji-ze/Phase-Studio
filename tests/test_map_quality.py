"""Pure scientific/profile tests for profile-aware map assessment."""
from dataclasses import FrozenInstanceError
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase_studio.map_quality import (
    FrozenReflection,
    MapQualityMetrics,
    ResultCandidate,
    ValidationProfile,
    compute_map_quality,
    determine_validation_profile,
    make_validation_context,
    profile_definition,
    recommend_best_result,
)


GRID = (16, 0, 15, 16, 0, 15, 16, 0, 15)
CELL = (12.0, 13.0, 14.0, 90.0, 90.0, 90.0)
HKLS = (
    (1, 0, 0), (0, 1, 0), (1, 1, 0), (2, 0, 0),
    (2, 1, 0), (1, 2, 0), (0, 2, 0), (2, 2, 0),
    (3, 1, 0), (1, 3, 0), (3, 2, 0), (2, 3, 0),
)


def synthetic_map(phases=None, amplitudes=None):
    phases = phases or {hkl: 0.19 * hkl[0] + 0.27 * hkl[1] for hkl in HKLS}
    amplitudes = amplitudes or {hkl: 2.0 + 0.37 * index for index, hkl in enumerate(HKLS)}
    coefficients = np.zeros((16, 16, 16), dtype=np.complex128)
    for hkl in HKLS:
        h, k, l = hkl
        coefficient = amplitudes[hkl] * np.exp(1j * phases[hkl])
        coefficients[l % 16, k % 16, h % 16] = coefficient
        coefficients[-l % 16, -k % 16, -h % 16] = np.conj(coefficient)
    return np.fft.ifftn(coefficients).real.reshape(-1), amplitudes


def context_for(amplitudes, free=()):
    return make_validation_context(
        [FrozenReflection(*hkl, amplitudes[hkl]) for hkl in HKLS],
        free_hkls=free,
    )


class MapQualityScientificTests(unittest.TestCase):
    def test_known_fourier_coefficients_reconstruct_amplitudes(self):
        density, amplitudes = synthetic_map()
        metrics = compute_map_quality(density, GRID, CELL, "ZYX", context_for(amplitudes))
        self.assertLess(metrics.amplitude_rf, 1e-12)
        self.assertAlmostEqual(metrics.amplitude_cc, 1.0, places=12)
        self.assertEqual(metrics.n_measured_reflections, len(HKLS))

    def test_identical_sources_use_identical_context_and_metrics(self):
        density, amplitudes = synthetic_map()
        context = context_for(amplitudes, free=HKLS[:3])
        first = compute_map_quality(density, GRID, CELL, "ZYX", context)
        second = compute_map_quality(density.copy(), GRID, CELL, "ZYX", context)
        self.assertEqual(first, second)
        self.assertEqual(context.triplet_weights, tuple(t.weight for t in context.triplet_set))

    def test_each_map_is_fourier_transformed_once(self):
        density, amplitudes = synthetic_map()
        original = np.fft.fftn
        calls = []

        def counted(values):
            calls.append(values.shape)
            return original(values)

        with patch("phase_studio.map_quality.np.fft.fftn", side_effect=counted):
            compute_map_quality(density, GRID, CELL, "ZYX", context_for(amplitudes))
        self.assertEqual(calls, [(16, 16, 16)])

    def test_multiplicative_map_scaling_is_invariant(self):
        density, amplitudes = synthetic_map()
        context = context_for(amplitudes)
        first = compute_map_quality(density, GRID, CELL, "ZYX", context)
        second = compute_map_quality(7.3 * density, GRID, CELL, "ZYX", context)
        self.assertAlmostEqual(first.amplitude_rf, second.amplitude_rf, places=12)
        self.assertAlmostEqual(first.amplitude_cc, second.amplitude_cc, places=12)
        self.assertAlmostEqual(first.triplet_c3, second.triplet_c3, places=12)

    def test_cyclic_origin_shift_is_invariant(self):
        density, amplitudes = synthetic_map()
        context = context_for(amplitudes)
        shifted = np.roll(density.reshape((16, 16, 16)), (3, -2, 4), axis=(0, 1, 2)).reshape(-1)
        first = compute_map_quality(density, GRID, CELL, "ZYX", context)
        second = compute_map_quality(shifted, GRID, CELL, "ZYX", context)
        self.assertAlmostEqual(first.amplitude_rf, second.amplitude_rf, places=12)
        self.assertAlmostEqual(first.amplitude_cc, second.amplitude_cc, places=12)
        self.assertAlmostEqual(first.triplet_c3, second.triplet_c3, places=12)

    def test_constant_background_is_removed(self):
        density, amplitudes = synthetic_map()
        context = context_for(amplitudes)
        first = compute_map_quality(density, GRID, CELL, "ZYX", context)
        second = compute_map_quality(density + 123.0, GRID, CELL, "ZYX", context)
        for key in ("amplitude_rf", "amplitude_cc", "triplet_c3", "entropy_normalized", "negative_density_mass"):
            self.assertAlmostEqual(getattr(first, key), getattr(second, key), places=10)

    def test_amplitude_perturbation_worsens_rf_and_cc(self):
        density, amplitudes = synthetic_map()
        changed = dict(amplitudes)
        for index, hkl in enumerate(HKLS):
            changed[hkl] *= 0.45 if index % 2 else 1.8
        perturbed, _ = synthetic_map(amplitudes=changed)
        context = context_for(amplitudes)
        baseline = compute_map_quality(density, GRID, CELL, "ZYX", context)
        result = compute_map_quality(perturbed, GRID, CELL, "ZYX", context)
        self.assertGreater(result.amplitude_rf, baseline.amplitude_rf + 0.05)
        self.assertLess(result.amplitude_cc, baseline.amplitude_cc)

    def test_phase_randomization_worsens_triplet_statistic(self):
        density, amplitudes = synthetic_map()
        rng = np.random.default_rng(20260914)
        random_phases = {hkl: float(rng.uniform(-math.pi, math.pi)) for hkl in HKLS}
        randomized, _ = synthetic_map(phases=random_phases, amplitudes=amplitudes)
        context = context_for(amplitudes)
        baseline = compute_map_quality(density, GRID, CELL, "ZYX", context)
        result = compute_map_quality(randomized, GRID, CELL, "ZYX", context)
        self.assertGreater(baseline.triplet_c3, result.triplet_c3)

    def test_reference_phase_agreement_uses_measured_reflections(self):
        phases = {hkl: 0.19 * hkl[0] + 0.27 * hkl[1] for hkl in HKLS}
        density, amplitudes = synthetic_map(phases=phases)
        context = make_validation_context(
            [FrozenReflection(*hkl, amplitudes[hkl]) for hkl in HKLS],
            reference_model="reference.cif",
            reference_phases=phases,
        )
        metrics = compute_map_quality(density, GRID, CELL, "ZYX", context)
        self.assertAlmostEqual(metrics.reference_phase_agreement, 1.0, places=12)
        self.assertEqual(metrics.n_measured_reflections, len(HKLS))

    def test_cropped_map_is_reported_unavailable(self):
        density, amplitudes = synthetic_map()
        cropped_grid = (16, 1, 15, 16, 0, 15, 16, 0, 15)
        metrics = compute_map_quality(density, cropped_grid, CELL, "ZYX", context_for(amplitudes))
        self.assertIsNone(metrics.amplitude_rf)
        self.assertIn("cropped", metrics.unavailable_reason.lower())

    def test_mismatched_cell_and_undersampled_hkl_are_unavailable(self):
        density, amplitudes = synthetic_map()
        cell_context = make_validation_context(
            [FrozenReflection(*hkl, amplitudes[hkl]) for hkl in HKLS],
            unit_cell=CELL,
        )
        mismatch = compute_map_quality(density, GRID, (12.5,) + CELL[1:], "ZYX", cell_context)
        self.assertIn("does not match", mismatch.unavailable_reason)
        undersampled = make_validation_context([FrozenReflection(9, 0, 0, 1.0)])
        invalid = compute_map_quality(density, GRID, CELL, "ZYX", undersampled)
        self.assertIn("undersamples", invalid.unavailable_reason)

    def test_validation_context_is_frozen_and_holdout_never_enters_work(self):
        _density, amplitudes = synthetic_map()
        free = frozenset(HKLS[:3])
        context = context_for(amplitudes, free)
        self.assertTrue({r.hkl for r in context.free_reflections}.isdisjoint({r.hkl for r in context.work_reflections}))
        with self.assertRaises(FrozenInstanceError):
            context.profile = ValidationProfile.REFERENCE_ONLY


class ProfileAndRecommendationTests(unittest.TestCase):
    def test_all_four_profile_metric_sets(self):
        expected = {
            (True, True): (ValidationProfile.REFERENCE_AND_HOLDOUT, ("reference_f05", "r_free", "omit_map_correlation")),
            (True, False): (ValidationProfile.REFERENCE_ONLY, ("reference_f05", "reference_rmsd", "reference_phase_agreement")),
            (False, True): (ValidationProfile.HOLDOUT_ONLY, ("r_free", "cc_free", "omit_map_correlation")),
            (False, False): (ValidationProfile.REFERENCE_FREE, ("amplitude_rf", "amplitude_cc", "triplet_c3")),
        }
        for flags, (profile, keys) in expected.items():
            selected = determine_validation_profile(*flags)
            self.assertEqual(selected, profile)
            self.assertEqual(tuple(metric.key for metric in profile_definition(selected).primary_metrics), keys)

    @staticmethod
    def candidate(cycle, source, **metrics):
        return ResultCandidate(cycle, source, "map", "model", MapQualityMetrics(**metrics), True, True)

    def test_exact_lexicographic_order_for_every_profile(self):
        cases = (
            (ValidationProfile.REFERENCE_AND_HOLDOUT, "reference_f05", 0.7, 0.8),
            (ValidationProfile.REFERENCE_ONLY, "reference_f05", 0.7, 0.8),
            (ValidationProfile.HOLDOUT_ONLY, "r_free", 0.3, 0.2),
            (ValidationProfile.REFERENCE_FREE, "amplitude_rf", 0.3, 0.2),
        )
        for profile, key, left, right in cases:
            first = self.candidate(1, "deblurred", **{key: left})
            second = self.candidate(2, "superflip", **{key: right})
            self.assertEqual(recommend_best_result(profile, (first, second)).recommended_candidate, second)

    def test_superflip_can_beat_sharped(self):
        sf = self.candidate(4, "superflip", amplitude_rf=0.10, amplitude_cc=0.8, triplet_c3=0.7)
        sharped = self.candidate(4, "deblurred", amplitude_rf=0.20, amplitude_cc=0.9, triplet_c3=0.9)
        self.assertEqual(recommend_best_result(ValidationProfile.REFERENCE_FREE, (sharped, sf)).recommended_candidate, sf)

    def test_missing_primary_is_excluded_and_missing_tiebreaker_is_safe(self):
        missing = self.candidate(1, "superflip", amplitude_cc=1.0)
        usable = self.candidate(2, "deblurred", amplitude_rf=0.2)
        self.assertEqual(recommend_best_result(ValidationProfile.REFERENCE_FREE, (missing, usable)).recommended_candidate, usable)
        unavailable = recommend_best_result(ValidationProfile.REFERENCE_FREE, (missing,))
        self.assertIsNone(unavailable.recommended_candidate)
        self.assertIn("unavailable", unavailable.reason.lower())

        earlier_missing = self.candidate(1, "superflip", amplitude_rf=0.2)
        later_complete_metrics = self.candidate(2, "deblurred", amplitude_rf=0.2, amplitude_cc=0.9)
        skipped = recommend_best_result(ValidationProfile.REFERENCE_FREE, (later_complete_metrics, earlier_missing))
        self.assertEqual(skipped.recommended_candidate, earlier_missing)
        self.assertIn("skipped", skipped.reason.lower())

    def test_true_ties_prefer_complete_then_earlier_then_stable_source(self):
        values = dict(amplitude_rf=0.2, amplitude_cc=0.8, triplet_c3=0.4)
        later = self.candidate(2, "superflip", **values)
        early_sharped = self.candidate(1, "deblurred", **values)
        early_sf = self.candidate(1, "superflip", **values)
        incomplete = ResultCandidate(0, "superflip", "map", "", MapQualityMetrics(**values), True, False)
        result = recommend_best_result(ValidationProfile.REFERENCE_FREE, (later, early_sharped, early_sf, incomplete))
        self.assertEqual(result.recommended_candidate, early_sf)

    def test_recommendation_and_manual_selection_remain_separate(self):
        best = self.candidate(1, "superflip", amplitude_rf=0.1)
        other = self.candidate(2, "deblurred", amplitude_rf=0.2)
        recommendation = recommend_best_result(ValidationProfile.REFERENCE_FREE, (best, other))
        changed = recommendation.with_selected(other)
        self.assertEqual(changed.recommended_candidate, best)
        self.assertEqual(changed.selected_candidate, other)


if __name__ == "__main__":
    unittest.main(verbosity=2)
