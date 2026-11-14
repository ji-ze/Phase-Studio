"""Shared scientific readiness; never changes observations or configuration."""
from collections import OrderedDict
import math
from pathlib import Path
import tempfile
import threading
from .validation_issues import ValidationIssue


class ReflectionReadinessError(ValueError):
    def __init__(self, issue):
        self.issue = issue
        super().__init__(str(issue))


def genuine_uncertainties(data_mode, reflections, *, verified=True):
    from . import app as a
    mode = a.normalize_reflection_data_mode(data_mode)
    if not verified or mode == a.REFLECTION_DATA_MODE_AUTO or a.reflection_mode_has_fwhm(mode):
        return False
    return any((r.h, r.k, r.l) != (0, 0, 0) and math.isfinite(float(r.value)) and
               r.sigma is not None and math.isfinite(float(r.sigma)) and r.sigma > 0
               for r in reflections)


def significance_issue(data_mode, threshold, available):
    if threshold <= 0 or available:
        return None
    from .app import format_reflection_data_mode
    return ValidationIssue(
        'The selected reflection data (' + format_reflection_data_mode(data_mode) +
        ') do not contain verified finite positive measured uncertainties required by the configured significance threshold. '
        'Review the reflection filtering threshold or select input with genuine measured uncertainties. '
        'Your configuration has not been changed.',
        'significance_unavailable', 'i_over_sigma_min', 'Superflip', True)


def validate_loaded_significance(data_mode, threshold, reflections, *, verified=True):
    from .app import validate_reflection_filter_policy, reflection_mode_has_fwhm
    try:
        validate_reflection_filter_policy(data_mode, threshold)
    except ValueError as error:
        if reflection_mode_has_fwhm(data_mode) and threshold > 0:
            raise ReflectionReadinessError(ValidationIssue(str(error), 'significance_fwhm', 'i_over_sigma_min', 'Superflip', True)) from error
        raise
    if threshold > 0 and reflections:
        issue = significance_issue(data_mode, threshold, genuine_uncertainties(data_mode, reflections, verified=verified))
        if issue:
            raise ReflectionReadinessError(issue)


_cache = OrderedDict()
_lock = threading.Lock()


def configuration_source(cfg):
    from . import app as a
    mode = a.normalize_input_source_mode(cfg.input_source_mode)
    embedded = mode == a.INPUT_MODE_INFLIP or (mode == a.INPUT_MODE_INFLIP_OVERRIDES and a.uses_embedded_hkl(cfg.hkl))
    return Path(cfg.jana_inflip if embedded else cfg.hkl), embedded


def configuration_identity(cfg, data_mode):
    from .hkl_diagnostics import source_identity
    path, embedded = configuration_source(cfg)
    return source_identity(path), data_mode, embedded


def configuration_cached(cfg, data_mode):
    try:
        key = configuration_identity(cfg, data_mode)
    except OSError:
        return False
    with _lock:
        return key in _cache


def validate_configuration_significance(cfg, data_mode):
    """Use the native extraction/reader contract, outside the run directory."""
    from . import app as a
    if cfg.i_over_sigma_min <= 0:
        return
    key = configuration_identity(cfg, data_mode)
    with _lock:
        available = _cache.get(key)
    if available is None:
        path, embedded = configuration_source(cfg)
        configured = getattr(cfg, 'reflection_data_mode', data_mode)
        verified = a._verified_embedded_reflection_data_mode_from_inflip(path) is not None if embedded else a.normalize_reflection_data_mode(configured) != a.REFLECTION_DATA_MODE_AUTO
        verified = verified and data_mode != a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA
        with tempfile.TemporaryDirectory(prefix='phase-studio-preflight-') as temporary:
            source = a.extract_embedded_hkl_from_inflip(path, Path(temporary)) if embedded else path
            value_col, sigma_col, include_000 = a.reflection_columns_for_mode(data_mode)
            rows = a.read_hkl(source, value_col, sigma_col, include_000)
            available = genuine_uncertainties(data_mode, rows, verified=verified)
        if key != configuration_identity(cfg, data_mode):
            raise ValueError('Reflection input changed during validation. Review the input and try again.')
        with _lock:
            _cache[key] = available
            while len(_cache) > 3:
                _cache.popitem(last=False)
    issue = significance_issue(data_mode, cfg.i_over_sigma_min, available)
    if issue:
        raise ReflectionReadinessError(issue)
