"""Regression tests for Autosolve's adaptive cycle-extension policy.

Verifies the three worked examples from the Phase Studio 2.0.0 spec exactly,
using the real, unmodified map_quality.recommend_best_result ranking over
constructed candidate fixtures -- never a fabricated improvement score.

Plain Python test (no pytest dependency); run with
`python tests/test_autosolve_policy.py`.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def make_candidate(cycle, amplitude_rf):
    from phase_studio.map_quality import MapQualityMetrics, ResultCandidate
    return ResultCandidate(
        cycle=cycle,
        source="superflip",
        map_path=f"cycle_{cycle:03d}.xplor",
        structure_path=f"cycle_{cycle:03d}.cif",
        metrics=MapQualityMetrics(amplitude_rf=amplitude_rf, amplitude_cc=0.5, triplet_c3=0.5),
    )


def run_case(name, best_cycle_values, final_expected_limit):
    """best_cycle_values: {cycle: amplitude_rf} for cycles that should become
    the running overall best at that point; every other cycle gets a filler
    value (1.0) that never wins. Runs the policy cycle-by-cycle up to
    final_expected_limit + a safety margin, and asserts the policy actually
    stops there (never runs away, never stops early)."""
    from phase_studio.autosolve_policy import AdaptiveCyclePolicy
    from phase_studio.map_quality import ValidationProfile

    policy = AdaptiveCyclePolicy(ValidationProfile.REFERENCE_FREE, initial=10, block_size=5)
    candidates = []
    stopped_at = None
    cyc = 1
    safety_cap = final_expected_limit + 10
    while cyc <= safety_cap:
        value = best_cycle_values.get(cyc, 1.0)
        candidates.append(make_candidate(cyc, value))
        action = policy.on_cycle_completed(cyc, candidates)
        if action == "stop":
            stopped_at = cyc
            break
        elif action == "extend":
            check(f"{name}: extension only happens at a decision point (cyc={cyc})",
                  cyc == policy.state.current_cycle_limit - policy.block_size)
        cyc += 1
    check(f"{name}: policy stops at exactly the expected limit", stopped_at == final_expected_limit)
    return policy


def main():
    # CASE 1: cycles 1-10, best cycle = 4 -> stop at 10 (best is in the first
    # half of the initial block, i.e. not "found after cycle 5").
    run_case("case1", {4: 0.5}, 10)

    # CASE 2: cycles 1-10, best cycle = 8 -> extend to 15; 11-15 contain no
    # better candidate -> stop at 15.
    run_case("case2", {8: 0.5}, 15)

    # CASE 3: initial best = 8 -> extend to 15; cycle 13 becomes better ->
    # extend to 20; cycle 18 becomes better -> extend to 25; 21-25 do not
    # improve -> stop at 25.
    run_case("case3", {8: 0.5, 13: 0.4, 18: 0.3}, 25)

    # Explicit state-transparency check (spec's AdaptiveCycleState fields).
    from phase_studio.autosolve_policy import AdaptiveCyclePolicy
    from phase_studio.map_quality import ValidationProfile
    policy = AdaptiveCyclePolicy(ValidationProfile.REFERENCE_FREE)
    candidates = [make_candidate(c, 0.5 if c == 4 else 1.0) for c in range(1, 6)]
    for cyc in range(1, 6):
        policy.on_cycle_completed(cyc, candidates[:cyc])
    check("state: current_cycle_limit extended to 8", policy.state.current_cycle_limit == 8)
    check("state: latest_extension_start records the first cycle of the new block", policy.state.latest_extension_start == 6)
    check("state: recommended_cycle_before_extension is the cycle that triggered it", policy.state.recommended_cycle_before_extension == 4)
    check("state: whether_extension_improved_result is True", policy.state.whether_extension_improved_result is True)

    # No usable candidate at all -> stop, never extend indefinitely.
    from phase_studio.map_quality import MapQualityMetrics, ResultCandidate
    empty_policy = AdaptiveCyclePolicy(ValidationProfile.REFERENCE_FREE)
    unusable = [
        ResultCandidate(cycle=c, source="superflip", map_path="m", structure_path="s",
                        metrics=MapQualityMetrics(), usable_map=False)
        for c in range(1, 6)
    ]
    action = None
    for cyc in range(1, 6):
        action = empty_policy.on_cycle_completed(cyc, unusable[:cyc])
    check("no usable candidate at all -> stop, not extend", action == "stop")

    # Independent recommendation streams (Superflip vs SharpED) never compared.
    superflip_candidates = [make_candidate(c, 0.5 if c == 4 else 1.0) for c in range(1, 6)]
    sharped_candidates = [
        ResultCandidate(cycle=c, source="deblurred", map_path=f"d{c}.xplor", structure_path=f"d{c}.cif",
                         metrics=MapQualityMetrics(amplitude_rf=0.4 if c == 5 else 1.0, amplitude_cc=0.5, triplet_c3=0.5))
        for c in range(1, 6)
    ]
    sf_policy = AdaptiveCyclePolicy(ValidationProfile.REFERENCE_FREE)
    sd_policy = AdaptiveCyclePolicy(ValidationProfile.REFERENCE_FREE)
    sf_action = sd_action = None
    for cyc in range(1, 6):
        sf_action = sf_policy.on_cycle_completed(cyc, superflip_candidates[:cyc])
        sd_action = sd_policy.on_cycle_completed(cyc, sharped_candidates[:cyc])
    check("Superflip stream extends independently based on its own cycle-4 best", sf_action == "extend")
    check("SharpED stream extends independently based on its own cycle-5 best", sd_action == "extend")

    failures = [name for name, ok in results_log if not ok]
    print()
    if failures:
        print(f"{len(failures)} of {len(results_log)} checks FAILED:")
        for failure in failures:
            print("  - " + failure)
        return 1
    print(f"All {len(results_log)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
