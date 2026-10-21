"""Regression guards for real-project path and failed-review diagnostics."""
import queue

import pytest

from phase_studio.error_reporting import build_error_report
from phase_studio.review_edma import ReviewEDMAExecutor


@pytest.mark.parametrize('family', ['sharped', 'superflip'])
def test_explicit_edma_context_survives_candidate_path(family):
    report = build_error_report(FileNotFoundError(
        f'C:/Jana2020/project/review_edma/{family}_cycle_003_scientific_raw.cif'),
        subsystem='EDMA', operation='Adjust selected result threshold')
    assert report.subsystem == 'EDMA'
    assert report.category == 'edma_runtime'
    assert 'server' not in report.summary.lower()
    assert 'Execution' in report.guidance or 'log' in report.guidance.lower()


@pytest.mark.parametrize('failure', [OSError('EDMA subprocess failed'),
    ValueError('Invalid EDMA maxima record'), RuntimeError('EDMA did not create coordinate output')])
def test_failed_review_retries_from_completed_threshold(failure):
    events = queue.Queue()
    worker = ReviewEDMAExecutor(events.put)
    key = ('run', 'sharped', 3, 'map-sha')
    completed = []
    def fail(stop):
        raise failure
    request = worker.request(key=key, cache_key=(*key, .4), run_id='run',
        candidate_id='old', source='sharped', cycle=3, threshold=.4,
        job=fail, callback=completed.append)
    worker.complete(events.get(timeout=5))
    assert completed[0].error is failure
    assert worker.requested_threshold(key, .5) == .5
    assert not worker.is_busy(key)
    assert request.threshold == .4
