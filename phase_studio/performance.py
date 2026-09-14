"""Opt-in monotonic timing for developer workflow performance audits."""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional


@dataclass(frozen=True)
class TimingRecord:
    name: str
    owner: str
    elapsed_seconds: float
    exclusive_seconds: float


class TimingToken:
    def __init__(self, profiler: "WorkflowProfiler", name: str, owner: str) -> None:
        self.profiler = profiler
        self.name = str(name)
        self.owner = str(owner)
        self.started_at = time.perf_counter()
        self.child_seconds = 0.0
        self.stopped = False

    def stop(self) -> float:
        if self.stopped:
            return 0.0
        self.stopped = True
        elapsed = max(0.0, time.perf_counter() - self.started_at)
        self.profiler._complete(self, elapsed)
        return elapsed


class WorkflowProfiler:
    """Collect nested wall-clock spans without affecting normal log output."""

    ENVIRONMENT_VARIABLE = "PHASE_STUDIO_PROFILE"

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = bool(enabled)
        self.records: list[TimingRecord] = []
        self._local = threading.local()
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls) -> "WorkflowProfiler":
        value = str(os.environ.get(cls.ENVIRONMENT_VARIABLE, "")).strip().casefold()
        return cls(value in {"1", "true", "yes", "on"})

    def _stack(self) -> list[TimingToken]:
        stack = getattr(self._local, "stack", None)
        if stack is None:
            stack = []
            self._local.stack = stack
        return stack

    def start(self, name: str, owner: str = "phase_studio") -> Optional[TimingToken]:
        if not self.enabled:
            return None
        token = TimingToken(self, name, owner)
        self._stack().append(token)
        return token

    def _complete(self, token: TimingToken, elapsed: float) -> None:
        stack = self._stack()
        if stack and stack[-1] is token:
            stack.pop()
        elif token in stack:
            stack.remove(token)
        if stack:
            stack[-1].child_seconds += elapsed
        record = TimingRecord(
            token.name,
            token.owner,
            elapsed,
            max(0.0, elapsed - token.child_seconds),
        )
        with self._lock:
            self.records.append(record)

    @contextmanager
    def stage(self, name: str, owner: str = "phase_studio") -> Iterator[None]:
        token = self.start(name, owner)
        try:
            yield
        finally:
            if token is not None:
                token.stop()

    def report_text(self, outcome: str = "complete") -> str:
        aggregates: dict[tuple[str, str], list[float]] = {}
        with self._lock:
            records = list(self.records)
        for record in records:
            values = aggregates.setdefault((record.name, record.owner), [0.0, 0.0, 0.0])
            values[0] += 1
            values[1] += record.elapsed_seconds
            values[2] += record.exclusive_seconds
        total = sum(r.exclusive_seconds for r in records)
        app = sum(r.exclusive_seconds for r in records if r.owner == "phase_studio")
        external = sum(r.exclusive_seconds for r in records if r.owner != "phase_studio")
        lines = [
            "Phase Studio workflow performance",
            f"Outcome: {outcome}",
            "",
            "Stage                                      Calls    Wall time    App overhead",
            "-----------------------------------------  -------  ------------  ------------",
        ]
        for (name, owner), (calls, wall, exclusive) in sorted(
            aggregates.items(), key=lambda item: (-item[1][1], item[0][0])
        ):
            overhead = f"{exclusive:10.3f} s" if owner == "phase_studio" else "           -"
            lines.append(f"{name[:41]:41}  {int(calls):7d}  {wall:10.3f} s  {overhead}")
        percentage = (100.0 * app / total) if total > 0 else 0.0
        lines.extend([
            "",
            f"Measured total: {total:.3f} s",
            f"External computation/network wait: {external:.3f} s",
            f"Phase Studio-owned overhead: {app:.3f} s ({percentage:.1f}%)",
            "External time includes Superflip, EDMA, SharpED transfer requests, and SharpED server waiting.",
        ])
        return "\n".join(lines) + "\n"

    def write_report(self, path: Path, outcome: str = "complete") -> Optional[Path]:
        if not self.enabled:
            return None
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.report_text(outcome), encoding="utf-8")
        return target


@contextmanager
def profile_stage(
    profiler: Optional[WorkflowProfiler],
    name: str,
    owner: str = "phase_studio",
) -> Iterator[None]:
    if profiler is None:
        yield
        return
    with profiler.stage(name, owner):
        yield
