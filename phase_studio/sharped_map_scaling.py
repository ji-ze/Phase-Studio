"""Reversible signed power scaling of map voxel values around SharpED.

The SharpED server sees an XPLOR map whose voxel values have been raised to a
configurable exponent ``a``; the map it returns is raised to ``1/a`` again
before anything downstream in Phase Studio (EDMA, symmetrization, metrics,
phase recycling, export, Jana2020 hand-off) ever looks at it. Downstream code
therefore always works in the original map-value domain.

The transform is *signed* -- ``sign(x)*|x|**a`` rather than ``x**a`` -- because
crystallographic density maps legitimately contain negative voxel values and
``x**a`` is not real-valued for a negative ``x`` and a non-integer ``a``.

Two exponents are special:

``a = 1.0`` (the default)
    Exact identity. No NumPy power is evaluated and the map file that reaches
    the server is byte-for-byte the file Phase Studio produced before this
    feature existed. This is what keeps the default workflow numerically
    identical to every previous release.

``a = 0.0``
    Bypass. ``x**0`` discards the magnitude and is not invertible, so instead
    of pretending otherwise the transform is switched off entirely.

Everything here is pure and NumPy-only: no Qt, no I/O, no global state. See
``tests/test_sharped_map_scaling.py``.
"""
from __future__ import annotations

import math
from typing import Union

import numpy as np

# The default exponent. Must stay 1.0: it is the exact-identity fast path that
# makes the feature backward-compatible.
SHARPED_MAP_VALUE_EXPONENT_DEFAULT = 1.0

# The exponent that explicitly disables the transform (see module docstring).
SHARPED_MAP_VALUE_EXPONENT_BYPASS = 0.0

# Practical GUI bounds, kept next to the maths so the spin box and the
# validation below cannot drift apart.
SHARPED_MAP_VALUE_EXPONENT_MIN = 0.0
SHARPED_MAP_VALUE_EXPONENT_MAX = 10.0

# Exponents this close to 1.0 are treated as exactly 1.0. The GUI spin box has
# 3 decimals, so anything inside this window is a value the user cannot
# distinguish from the default anyway.
_IDENTITY_TOLERANCE = 1e-12


def normalize_map_value_exponent(value: object) -> float:
    """Coerce a stored/typed exponent to a valid float, defaulting on garbage.

    Only genuinely unusable input (non-numeric, NaN, infinite, negative) falls
    back to the default; a finite in-range number is returned unchanged so the
    user's value is never silently rounded.
    """
    try:
        exponent = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return SHARPED_MAP_VALUE_EXPONENT_DEFAULT
    if not math.isfinite(exponent) or exponent < 0.0:
        return SHARPED_MAP_VALUE_EXPONENT_DEFAULT
    return exponent


def map_value_scaling_is_identity(exponent: object) -> bool:
    """True when no transform must be evaluated at all.

    Covers both special exponents: ``1.0`` (mathematically the identity) and
    ``0.0`` (the explicit bypass). Callers use this to skip reading, rewriting
    and re-serializing the map entirely.
    """
    value = normalize_map_value_exponent(exponent)
    return value == SHARPED_MAP_VALUE_EXPONENT_BYPASS or abs(value - 1.0) <= _IDENTITY_TOLERANCE


def describe_map_value_exponent(exponent: object) -> str:
    """The one execution-log line for a SharpED request, or "" when default.

    Returns an empty string for ``a = 1.0`` so the default workflow's log is
    unchanged; callers that want a diagnostic line for the default case format
    it themselves at their DETAIL tier.
    """
    value = normalize_map_value_exponent(exponent)
    if value == SHARPED_MAP_VALUE_EXPONENT_BYPASS:
        return "[SharpED] Map value scaling disabled"
    if abs(value - 1.0) <= _IDENTITY_TOLERANCE:
        return ""
    return f"[SharpED] Map value exponent: {value:.3f}"


def _validated_exponent(exponent: object, *, inverse: bool) -> float:
    value = float(exponent)  # type: ignore[arg-type]
    if not math.isfinite(value):
        raise ValueError(f"SharpED map value exponent must be finite, got {exponent!r}.")
    if value < 0.0:
        raise ValueError(f"SharpED map value exponent must not be negative, got {value!r}.")
    if inverse and value == SHARPED_MAP_VALUE_EXPONENT_BYPASS:
        # Guarded rather than divided by: 1/0 is exactly the non-invertibility
        # that makes a = 0 a bypass instead of a transform.
        raise ValueError("SharpED map value exponent 0 disables the transform; it has no inverse.")
    return value


def _signed_power(values: Union[np.ndarray, "list[float]"], power: float) -> np.ndarray:
    """``sign(x)*|x|**power`` on a fresh array, never touching the input.

    Zeros come back as exact ``+0.0`` (``arr < 0`` is False for ``-0.0``), so a
    zero voxel stays a zero voxel for every ``power > 0`` with no signed-zero
    artifact leaking into the serialized map.
    """
    arr = np.asarray(values)
    if arr.size and not np.all(np.isfinite(arr)):
        # Phase Studio's XPLOR reader only ever produces finite maps. Refuse
        # loudly rather than invent a numerical policy for NaN/inf here.
        raise ValueError(
            "Cannot apply the SharpED map value exponent: the map contains "
            "non-finite values (NaN or infinity)."
        )
    work = arr if arr.dtype.kind == "f" else arr.astype(np.float64)
    magnitude = np.abs(work)
    powered = np.power(magnitude, power)
    return np.where(work < 0, -powered, powered)


def apply_signed_power(values: Union[np.ndarray, "list[float]"], exponent: object) -> np.ndarray:
    """Forward transform applied to the map sent to the SharpED server.

    ``y = sign(x) * |x|**a``. For the two identity exponents the input array
    itself is handed back untouched -- no power is evaluated and no
    floating-point round-trip is introduced -- so ``a = 1`` reproduces the
    pre-feature workflow exactly. Otherwise a new array is returned; the
    caller's array is never modified in place.
    """
    if map_value_scaling_is_identity(exponent):
        return np.asarray(values)
    return _signed_power(values, _validated_exponent(exponent, inverse=False))


def invert_signed_power(values: Union[np.ndarray, "list[float]"], exponent: object) -> np.ndarray:
    """Inverse transform applied to the map returned by the SharpED server.

    ``x = sign(y) * |y|**(1/a)``, the exact inverse of :func:`apply_signed_power`,
    with the same identity fast paths and the same no-in-place-modification
    guarantee.
    """
    if map_value_scaling_is_identity(exponent):
        return np.asarray(values)
    return _signed_power(values, 1.0 / _validated_exponent(exponent, inverse=True))
