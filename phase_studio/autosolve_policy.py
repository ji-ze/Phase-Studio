"""Autosolve's adaptive cycle-extension policy.

Pure orchestration policy: no Qt, no I/O, no scientific computation. The only
scientific authority consulted is map_quality.recommend_best_result, called
unmodified -- this module decides how many cycles to run, never what makes
one cycle's result better than another's.

Algorithm: decision points occur every time a block boundary is reached,
starting at `initial`. At each decision point, extend iff
the overall-best candidate (by the real, unmodified recommendation ranking)
falls inside the block that was *just* completed -- i.e. the block improved
on whatever was known before it started. The current Autosolve caller uses a
fixed five-cycle initial search followed by three-cycle refinement blocks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from phase_studio.map_quality import ResultCandidate, ValidationProfile, recommend_best_result


def should_extend(
    profile: ValidationProfile,
    candidates_up_to_limit: Sequence[ResultCandidate],
    limit: int,
    block_size: int = 5,
) -> bool:
    """True iff the block of cycles [limit-block_size+1, limit] contains the
    overall-best candidate among candidates_up_to_limit -- i.e. that block
    produced a new recommendation better than everything before it."""
    best = recommend_best_result(profile, candidates_up_to_limit)
    recommended = best.recommended_candidate
    if recommended is None:
        return False
    return int(recommended.cycle) > (limit - block_size)


@dataclass
class AdaptiveCycleState:
    """Transparent, explicit adaptive-cycle bookkeeping -- orchestration
    policy, not scientific scoring. Never inferred indirectly from widget
    text."""

    current_cycle_limit: int = 5
    latest_extension_start: Optional[int] = None
    recommended_cycle_before_extension: Optional[int] = None
    whether_extension_improved_result: Optional[bool] = None


class AdaptiveCyclePolicy:
    """Drives block-based adaptive extension for one Autosolve stage."""

    def __init__(
        self,
        profile: ValidationProfile,
        *,
        initial: int = 5,
        block_size: int = 3,
    ) -> None:
        self.profile = profile
        self.initial = int(initial)
        self.block_size = int(block_size)
        self.state = AdaptiveCycleState(current_cycle_limit=self.initial)

    def on_cycle_completed(self, cyc: int, candidates: Sequence[ResultCandidate]) -> str:
        """Call once per completed cycle, in order. Returns "continue"
        (this cycle was not a decision point, or an extension was just
        granted), "extend" (the just-completed block improved the
        recommendation -- the caller should raise the cycle budget by
        block_size and keep going), or "stop" (the just-completed block did
        not improve the recommendation -- the caller should stop this
        stage's cycling)."""
        if cyc != self.state.current_cycle_limit:
            return "continue"
        recommendation = recommend_best_result(self.profile, candidates)
        recommended_cycle = (
            int(recommendation.recommended_candidate.cycle)
            if recommendation.recommended_candidate is not None
            else None
        )
        self.state.recommended_cycle_before_extension = recommended_cycle
        improved = should_extend(self.profile, candidates, self.state.current_cycle_limit, self.block_size)
        self.state.whether_extension_improved_result = improved
        if not improved:
            return "stop"
        self.state.latest_extension_start = self.state.current_cycle_limit + 1
        self.state.current_cycle_limit += self.block_size
        return "extend"
