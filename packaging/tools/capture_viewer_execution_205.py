"""Reuse the offline execution capture, adding the final metrics checkpoint.

Scientific files here are explicitly synthetic UI fixtures, never handoff data.
"""
from pathlib import Path

source = Path(__file__).with_name("capture_execution_acceptance_205.py").resolve()
code = source.read_text(encoding="utf-8").replace(
    "acceptance-execution-2.0.5", "acceptance-viewer-remediation-2.0.5/execution"
)
checkpoint = "backend.results.append(replace(result,cycle=3))"
assert code.count(checkpoint) == 1
code = code.replace(checkpoint, """stage('Finalizing cycle', 'Calculating metrics')
backend._apply_cycle_progress_state(engine.CycleProgressState(
    3,3,'Finalizing cycle',7,7,detail='Calculating metrics',busy=True))
capture('11-final-cycle-finalizing')
""" + checkpoint)
exec(compile(code, str(source), "exec"), {"__file__": str(source), "__name__": "__main__"})
