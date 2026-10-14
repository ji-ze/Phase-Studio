"""Shared, lightweight camera interaction for Phase Studio 3-D viewers."""

from __future__ import annotations

import math
from typing import Callable, Iterable, Optional

import numpy as np


def set_structure_viewport_clip(axis) -> None:
    """Clip to this panel rectangle rather than Axes3D's artificial square."""
    viewport = axis.get_position(original=True).transformed(axis.figure.transFigure)
    for artist in (*axis.collections, *axis.lines):
        artist.set_clip_path(None)
        artist.set_clip_box(viewport)
        artist.set_clip_on(True)


def fit_projected_structure(axis, coordinates, *, fill: float = 0.78) -> bool:
    """Frame displayed Cartesian geometry in the laid-out panel, without editing it.

    Orthographic projection makes scale linear. Use the actual subplot rectangle
    (Axes3D's drawing box is square even on a rectangular canvas), then centre
    the projected bounding box by changing camera limits only. Call after layout.
    """
    from mpl_toolkits.mplot3d import proj3d

    points = np.asarray(coordinates, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or not len(points) or not np.isfinite(points).all():
        return False
    axis.apply_aspect()  # Axes3D otherwise keeps its old square until draw().
    viewport = axis.get_position(original=True).transformed(axis.figure.transFigure)
    if viewport.width <= 1 or viewport.height <= 1:
        return False
    center = (points.min(axis=0) + points.max(axis=0)) / 2
    radius = max(float(np.max(np.linalg.norm(points - center, axis=1))), 1e-3)
    axis.set_proj_type("ortho")

    def limits(focus):
        axis.set_xlim3d(focus[0] - radius, focus[0] + radius, auto=False)
        axis.set_ylim3d(focus[1] - radius, focus[1] + radius, auto=False)
        axis.set_zlim3d(focus[2] - radius, focus[2] + radius, auto=False)

    def project():
        x, y, _ = proj3d.proj_transform(*points.T, axis.get_proj())
        return axis.transData.transform(np.column_stack((x, y)))

    limits(center)
    zoom = 1.0
    axis.set_box_aspect((1, 1, 1), zoom=zoom)
    projected = project()
    span = np.ptp(projected, axis=0)
    occupied = max(span[0] / viewport.width, span[1] / viewport.height)
    if occupied <= 1e-8:
        return False  # A single coincident site has no molecular extent to fit.
    zoom *= float(fill) / occupied
    axis.set_box_aspect((1, 1, 1), zoom=zoom)
    projected = project()
    target = np.asarray([viewport.x0 + viewport.width / 2, viewport.y0 + viewport.height / 2])
    midpoint = (projected.min(axis=0) + projected.max(axis=0)) / 2
    # Measure the projection's camera-translation Jacobian. This also respects
    # the actual cell geometry and arbitrary viewing orientation.
    derivatives = []
    step = max(radius * .01, 1e-5)
    for index in range(3):
        shifted = center.copy()
        shifted[index] += step
        limits(shifted)
        pixels = project()
        derivatives.append(((pixels.min(axis=0) + pixels.max(axis=0)) / 2 - midpoint) / step)
    delta = np.linalg.lstsq(np.asarray(derivatives).T, target - midpoint, rcond=None)[0]
    limits(center + delta)
    axis._phase_fit_zoom = zoom
    # Artists can extend outside Axes3D's artificial square. Their projected
    # geometry remains within this panel's rectangular viewport and margins.
    set_structure_viewport_clip(axis)
    return True
from PySide6.QtCore import Qt


class StructureCameraController:
    """Canvas-only orbit, screen-space pan and multiplicative zoom.

    Geometry and artists are never rebuilt.  Rotation can be synchronized by
    the owner while limits remain local to the panel where a pan/zoom starts.
    """

    DRAG_THRESHOLD_PX = 3.0

    def __init__(
        self,
        canvas,
        axes: Callable[[], Iterable[object]],
        *,
        fit: Callable[[], None],
        reset: Callable[[], None],
        orientation_changed: Callable[[float, float, object], None],
        interaction: Optional[Callable[[str], None]] = None,
        toggle_auto_rotate: Optional[Callable[[], None]] = None,
    ) -> None:
        self.canvas = canvas
        self._axes = axes
        self._fit = fit
        self._reset = reset
        self._orientation_changed = orientation_changed
        self._interaction = interaction or (lambda _kind: None)
        self._toggle_auto_rotate = toggle_auto_rotate
        self._drag = None
        self.active_axis = None
        self._fit_spans = {}
        canvas.mpl_connect("button_press_event", self._press)
        canvas.mpl_connect("motion_notify_event", self._motion)
        canvas.mpl_connect("button_release_event", self._release)
        canvas.mpl_connect("scroll_event", self._scroll)
        canvas.mpl_connect("key_press_event", self._key)

    def refresh_axes(self) -> None:
        for axis in self._axes():
            disable = getattr(axis, "disable_mouse_rotation", None)
            if callable(disable):
                disable()
            self._fit_spans.setdefault(
                axis,
                np.asarray([
                    float(hi) - float(lo)
                    for lo, hi in (axis.get_xlim3d(), axis.get_ylim3d(), axis.get_zlim3d())
                ], dtype=np.float64),
            )

    def _valid_axis(self, axis) -> bool:
        return axis is not None and axis in list(self._axes())

    def _press(self, event) -> None:
        axis = getattr(event, "inaxes", None)
        if not self._valid_axis(axis):
            return
        self.active_axis = axis
        self.refresh_axes()
        if bool(getattr(event, "dblclick", False)) and getattr(event, "button", None) == 1:
            self._fit()
            self._interaction("fit")
            return
        button = getattr(event, "button", None)
        key = str(getattr(event, "key", "") or "").lower()
        mode = "pan" if button in (2, 3) or (button == 1 and "shift" in key) else "rotate" if button == 1 else ""
        if not mode:
            return
        limits = tuple(
            (float(pair[0]), float(pair[1]))
            for pair in (axis.get_xlim3d(), axis.get_ylim3d(), axis.get_zlim3d())
        )
        self._drag = {
            "axis": axis, "mode": mode,
            "x": float(getattr(event, "x", 0.0)), "y": float(getattr(event, "y", 0.0)),
            "elev": float(axis.elev), "azim": float(axis.azim), "limits": limits,
            "moved": False,
        }
        set_cursor = getattr(self.canvas, "setCursor", None)
        if callable(set_cursor):
            set_cursor(Qt.SizeAllCursor if mode == "pan" else Qt.ClosedHandCursor)

    def _motion(self, event) -> None:
        if self._drag is None:
            return
        dx = float(getattr(event, "x", self._drag["x"])) - self._drag["x"]
        dy = float(getattr(event, "y", self._drag["y"])) - self._drag["y"]
        if math.hypot(dx, dy) < self.DRAG_THRESHOLD_PX and not self._drag["moved"]:
            return
        self._drag["moved"] = True
        axis = self._drag["axis"]
        if self._drag["mode"] == "rotate":
            width = max(240.0, float(self.canvas.width()))
            height = max(240.0, float(self.canvas.height()))
            elev = max(-89.5, min(89.5, self._drag["elev"] + dy * 180.0 / height))
            azim = (self._drag["azim"] - dx * 180.0 / width) % 360.0
            self._orientation_changed(elev, azim, axis)
            self._interaction("rotate")
        else:
            self._pan(axis, dx, dy)
            self._interaction("pan")
        self.canvas.draw_idle()

    def _pan(self, axis, dx: float, dy: float) -> None:
        spans = np.asarray([hi - lo for lo, hi in self._drag["limits"]], dtype=np.float64)
        pixels = max(120.0, float(min(self.canvas.width(), self.canvas.height())))
        az = math.radians(float(axis.azim))
        el = math.radians(float(axis.elev))
        right = np.asarray((-math.sin(az), math.cos(az), 0.0))
        up = np.asarray((-math.cos(az) * math.sin(el), -math.sin(az) * math.sin(el), math.cos(el)))
        delta = (-dx * right - dy * up) * (float(np.mean(spans)) / pixels)
        limits = tuple(
            (lo + float(delta[i]), hi + float(delta[i]))
            for i, (lo, hi) in enumerate(self._drag["limits"])
        )
        axis.set_xlim3d(*limits[0], auto=False)
        axis.set_ylim3d(*limits[1], auto=False)
        axis.set_zlim3d(*limits[2], auto=False)

    def _release(self, _event) -> None:
        self._drag = None
        unset_cursor = getattr(self.canvas, "unsetCursor", None)
        if callable(unset_cursor):
            unset_cursor()

    def _scroll(self, event) -> None:
        axis = getattr(event, "inaxes", None)
        if not self._valid_axis(axis):
            return
        self.active_axis = axis
        step = float(getattr(event, "step", 1.0 if getattr(event, "button", "up") == "up" else -1.0))
        factor = math.pow(0.88, step)
        factor = max(0.45, min(2.2, factor))
        base = self._fit_spans.get(axis)
        if base is None:
            base = np.asarray([
                float(hi) - float(lo)
                for lo, hi in (axis.get_xlim3d(), axis.get_ylim3d(), axis.get_zlim3d())
            ], dtype=np.float64)
            self._fit_spans[axis] = base
        for index, (getter, setter) in enumerate((
            (axis.get_xlim3d, axis.set_xlim3d),
            (axis.get_ylim3d, axis.set_ylim3d),
            (axis.get_zlim3d, axis.set_zlim3d),
        )):
            low, high = map(float, getter())
            center = (low + high) / 2.0
            fit_span = max(float(base[index]), 1.0e-6)
            span = max(fit_span * 0.01, min(fit_span * 100.0, (high - low) * factor))
            half = span / 2.0
            setter(center - half, center + half, auto=False)
        self._interaction("zoom")
        self.canvas.draw_idle()

    def _key(self, event) -> None:
        if self._valid_axis(getattr(event, "inaxes", None)):
            self.active_axis = event.inaxes
        key = str(getattr(event, "key", "") or "").lower()
        if key == "f":
            self._fit()
        elif key == "r":
            self._reset()
        elif key in {" ", "space"} and self._toggle_auto_rotate is not None:
            self._toggle_auto_rotate()
        else:
            return
        self.canvas.draw_idle()
