"""Independent, coalescing executor for interactive EDMA threshold review."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Hashable, Optional


@dataclass(frozen=True)
class ReviewRequest:
    key: Hashable
    cache_key: Hashable
    run_id: str
    candidate_id: str
    source: str
    cycle: int
    threshold: float
    generation: int


@dataclass(frozen=True)
class ReviewOutcome:
    request: ReviewRequest
    value: object = None
    error: Optional[BaseException] = None
    elapsed: float = 0.0
    cache_hit: bool = False


@dataclass
class _Task:
    request: ReviewRequest
    job: Callable[[threading.Event], object]
    callback: Callable[[ReviewOutcome], None]
    stop_event: threading.Event


class ReviewEDMAExecutor:
    """One running job per candidate, with latest-request-wins coalescing.

    Jobs run on dedicated daemon threads. ``publish`` only enqueues immutable
    outcomes; the GUI owner calls :meth:`complete` on its Qt thread.
    """

    def __init__(self, publish: Callable[[ReviewOutcome], None]) -> None:
        self._publish = publish
        self._lock = threading.RLock()
        self._generation = 0
        self._running: dict[Hashable, _Task] = {}
        self._pending: dict[Hashable, _Task] = {}
        self._latest_generation: dict[Hashable, int] = {}
        self._latest_threshold: dict[Hashable, float] = {}
        self._cache: dict[Hashable, object] = {}
        self._callbacks: dict[int, Callable[[ReviewOutcome], None]] = {}

    def requested_threshold(self, key: Hashable, fallback: float) -> float:
        with self._lock:
            return float(self._latest_threshold.get(key, fallback))

    def remember(self, cache_key: Hashable, value: object) -> None:
        with self._lock:
            self._cache.setdefault(cache_key, value)

    def request(
        self, *, key: Hashable, cache_key: Hashable, run_id: str,
        candidate_id: str, source: str, cycle: int, threshold: float,
        job: Callable[[threading.Event], object],
        callback: Callable[[ReviewOutcome], None],
    ) -> ReviewRequest:
        with self._lock:
            self._generation += 1
            request = ReviewRequest(
                key=key, cache_key=cache_key, run_id=str(run_id),
                candidate_id=str(candidate_id), source=str(source), cycle=int(cycle),
                threshold=float(threshold), generation=self._generation,
            )
            self._latest_generation[key] = request.generation
            self._latest_threshold[key] = request.threshold
            self._callbacks[request.generation] = callback
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._publish(ReviewOutcome(request, cached, elapsed=0.0, cache_hit=True))
                return request
            task = _Task(request, job, callback, threading.Event())
            if key in self._running:
                previous = self._pending.get(key)
                if previous is not None:
                    previous.stop_event.set()
                    self._callbacks.pop(previous.request.generation, None)
                self._pending[key] = task
            else:
                self._start_locked(task)
            return request

    def _start_locked(self, task: _Task) -> None:
        self._running[task.request.key] = task

        def worker() -> None:
            started = time.perf_counter()
            try:
                value = task.job(task.stop_event)
                outcome = ReviewOutcome(
                    task.request, value=value, elapsed=time.perf_counter() - started,
                )
            except BaseException as exc:
                outcome = ReviewOutcome(
                    task.request, error=exc, elapsed=time.perf_counter() - started,
                )
            self._publish(outcome)

        threading.Thread(
            target=worker,
            name=f"review-edma-{task.request.source}-{task.request.cycle}-{task.request.generation}",
            daemon=True,
        ).start()

    def complete(self, outcome: ReviewOutcome) -> None:
        callback = None
        with self._lock:
            key = outcome.request.key
            running = self._running.get(key)
            if running is not None and running.request.generation == outcome.request.generation:
                self._running.pop(key, None)
            if outcome.error is None and outcome.value is not None:
                self._cache[outcome.request.cache_key] = outcome.value
            stored_callback = self._callbacks.pop(outcome.request.generation, None)
            if self._latest_generation.get(key) == outcome.request.generation:
                callback = stored_callback
                if outcome.error is not None:
                    # The displayed completed candidate remains authoritative.
                    # A retry steps from that threshold, not the failed request.
                    self._latest_threshold.pop(key, None)
            pending = self._pending.pop(key, None)
            if pending is not None:
                self._start_locked(pending)
        if callback is not None:
            callback(outcome)

    def cancel_all(self) -> None:
        with self._lock:
            for task in self._running.values():
                task.stop_event.set()
            for task in self._pending.values():
                task.stop_event.set()
            self._pending.clear()
            self._latest_generation.clear()
            self._latest_threshold.clear()
            self._callbacks.clear()

    def is_busy(self, key: Hashable) -> bool:
        with self._lock:
            return key in self._running or key in self._pending
