"""Read-only UI states; no reflection calculations or output changes."""
from dataclasses import dataclass


@dataclass(frozen=True)
class EffectiveOperation:
    selected: bool
    active: bool
    status: str
    reason: str
    target_cycle: int | None


def effective_operation(enabled, start, total, magnitude, *, compatible=True, available=True):
    if not enabled:
        return EffectiveOperation(False, False, 'Disabled', 'Not selected', None)
    if not compatible:
        return EffectiveOperation(True, False, 'Unavailable', 'Incompatible input format', None)
    if total <= 1 or start >= total:
        return EffectiveOperation(True, False, 'Not eligible', 'No eligible subsequent cycle is configured', None)
    if magnitude <= 0:
        return EffectiveOperation(True, False, 'Configured but inactive', 'Configured magnitude is zero; observed values are retained unchanged', start + 1)
    if not available:
        return EffectiveOperation(True, False, 'Unavailable', 'Required measured metadata are unavailable', start + 1)
    return EffectiveOperation(True, True, 'Waiting for eligible cycle results',
                              f'After cycle {start} → eligible input for cycle {start + 1}', start + 1)


def recorded_feedback_state(reports):
    operations = [op for report in reports for op in report.get('operations', ())
                  if op.get('status') != 'Disabled']
    if not operations:
        return 'Disabled', False
    if all(op.get('status') == 'No numerical change' or
           (op.get('status') == 'Applied' and op.get('modified_reflections') == 0 and
            op.get('added_reflections', 0) == 0) for op in operations):
        return 'No reflection changes applied', True
    return 'Recorded cycle observations available', True
