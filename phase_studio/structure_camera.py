"""Shared, lightweight camera interaction for Phase Studio 3-D viewers."""

from __future__ import annotations

import math
import time
import weakref
from typing import Callable, Iterable, Optional

import numpy as np


def structure_marker_sizes(atom_count: int):
    """Shared display-only marker areas; isolated sites stay clearly visible."""
    scale = min(1.0, (320.0 / max(1, atom_count)) ** .32)
    return np.full(atom_count, max(24.0, 130.0 * scale), dtype=np.float64)


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
from PySide6.QtCore import Qt, QTimer, QSettings, QObject, QEvent


class _CameraVisibility(QObject):
    def __init__(self, controller):
        super().__init__(controller.canvas)
        self._controller = weakref.ref(controller)
        controller.canvas.installEventFilter(self)
        controller.canvas.window().installEventFilter(self)

    def eventFilter(self, watched, event):
        controller = self._controller()
        if controller is None:
            return False
        relevant = {QEvent.ParentChange,QEvent.Hide,QEvent.WindowDeactivate,QEvent.Show,QEvent.WindowActivate}
        if event.type() not in relevant:
            return False
        if event.type() == QEvent.ParentChange:
            controller.canvas.window().installEventFilter(self)
        owner = controller.canvas.window()
        if event.type() in {QEvent.Hide, QEvent.WindowDeactivate}:
            timer = getattr(owner,'_rotate_timer',getattr(owner,'_rotation_timer',None))
            if timer is not None: timer.stop()
            controller._release(None)
        elif event.type() in {QEvent.Show,QEvent.WindowActivate}:
            timer = getattr(owner,'_rotate_timer',getattr(owner,'_rotation_timer',None))
            enabled = getattr(owner,'_auto_rotate_enabled',getattr(owner,'_auto_rotate',False))
            if timer is not None and enabled: timer.start()
        return False


def camera_settings_button(parent):
    """One shared persisted visual preference, independent of scientific options."""
    from PySide6.QtGui import QAction, QActionGroup, QPainter, QPen
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QMenu, QToolButton, QApplication
    class CameraButton(QToolButton):
        def paintEvent(self,event):
            super().paintEvent(event)
            painter=QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            color=self.palette().buttonText().color()
            if not self.isEnabled(): color.setAlpha(100)
            painter.setPen(QPen(color,1.5,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
            x,y=self.width()-13.0,self.height()/2.0
            painter.drawPolyline([QPointF(x-4,y-2),QPointF(x,y+2),QPointF(x+4,y-2)])
            painter.end()

        def keyPressEvent(self,event):
            if event.key() in (Qt.Key_Return,Qt.Key_Enter,Qt.Key_Space,Qt.Key_Down):
                self.showMenu();event.accept();return
            super().keyPressEvent(event)
    button = CameraButton(parent)
    button.setObjectName('structureCameraMenu')
    button.setAccessibleName('Camera preferences')
    button.setStyleSheet('QToolButton#structureCameraMenu { padding-right:26px; } '
        'QToolButton#structureCameraMenu::menu-indicator { image:none; width:0px; }')
    button.setText('Camera')
    button.setMinimumWidth(button.fontMetrics().horizontalAdvance('Camera')+38)
    button.setToolTip('Camera preferences')
    button.setPopupMode(QToolButton.InstantPopup)
    menu = QMenu(button)
    action = QAction('Invert mouse rotation', menu)
    action.setCheckable(True)
    settings = QSettings('PhaseStudio', 'PhaseStudio')
    def refresh():
        action.blockSignals(True)
        action.setChecked(str(settings.value('viewer/invertMouseRotation', 'false')).lower() == 'true')
        action.blockSignals(False)
    def save(value):
        settings.setValue('viewer/invertMouseRotation', bool(value))
        settings.sync()
    refresh()
    action.toggled.connect(save)
    menu.aboutToShow.connect(refresh)
    menu.addAction(action)
    sensitivity = menu.addMenu('Rotation sensitivity')
    sensitivity_group = QActionGroup(sensitivity)
    for title, value in (('Slow · 0.5×',.5),('Normal · 1×',1.),('Fast · 2×',2.)):
        item=sensitivity.addAction(title);item.setCheckable(True);sensitivity_group.addAction(item)
        item.setData(value)
        item.setChecked(str(settings.value('viewer/rotationSensitivity',1.))==str(value))
        item.triggered.connect(lambda _checked=False,v=value: (settings.setValue('viewer/rotationSensitivity',v),settings.sync()))
    palettes=menu.addMenu('Element colors')
    palette_group=QActionGroup(palettes)
    app=QApplication.instance()
    app._phase_color_palette=str(settings.value('viewer/elementPalette','phase'))
    def palette_changed(value):
        settings.setValue('viewer/elementPalette',value);settings.sync()
        app._phase_color_palette=value
        for window in app.topLevelWidgets():
            callback=getattr(window,'_refresh_viewer_palette',None)
            if callback is not None:callback()
    for title,value in (('Current Phase Studio palette','phase'),('Conventional CPK-style palette','cpk')):
        item=palettes.addAction(title);item.setCheckable(True);palette_group.addAction(item)
        item.setData(value)
        item.setChecked(app._phase_color_palette==value)
        item.triggered.connect(lambda _checked=False,v=value:palette_changed(v))
    palettes.setToolTip('Conventional colors for common elements; other elements retain the consistent Phase Studio palette.')
    def refresh_visual_preferences():
        try:value=float(settings.value('viewer/rotationSensitivity',1.))
        except (ValueError,TypeError):value=1.
        for item in sensitivity_group.actions():item.setChecked(item.data()==value)
        for item in palette_group.actions():item.setChecked(item.data()==str(settings.value('viewer/elementPalette','phase')))
    menu.aboutToShow.connect(refresh_visual_preferences)
    refresh_visual_preferences()
    # Retain the Python wrappers as well as Qt ownership across popup cycles.
    button._camera_submenus=(sensitivity,palettes)
    button._camera_action_groups=(sensitivity_group,palette_group)
    button._camera_menu_actions=tuple(menu.actions())+tuple(sensitivity.actions())+tuple(palettes.actions())
    button.setMenu(menu)
    return button


def camera_basis(elev, azim, roll=0):
    """World-to-screen orthonormal basis matching Axes3D's camera convention."""
    el, az, rotation = np.deg2rad([elev, azim, roll])
    toward = np.array([np.cos(el)*np.cos(az), np.cos(el)*np.sin(az), np.sin(el)])
    right = np.array([-np.sin(az), np.cos(az), 0.])
    up = np.cross(toward, right)
    return np.array([np.cos(rotation)*right-np.sin(rotation)*up,
                     np.sin(rotation)*right+np.cos(rotation)*up, toward])


def camera_angles(basis):
    toward = basis[2]
    elev = np.arcsin(np.clip(toward[2], -1., 1.))
    azim = np.arctan2(toward[1], toward[0])
    right = np.array([-np.sin(azim), np.cos(azim), 0.])
    up = np.cross(toward, right)
    roll = np.arctan2(-np.dot(basis[0], up), np.dot(basis[0], right))
    return tuple(np.rad2deg([elev, azim, roll]))


def trackball_rotation(before, after):
    """Shortest proper rotation between screen-space sphere vectors."""
    cross = np.cross(before, after)
    dot = float(np.clip(np.dot(before, after), -1., 1.))
    if dot < -1 + 1e-10:
        helper = np.eye(3)[np.argmin(np.abs(before))]
        axis = np.cross(before, helper); axis /= np.linalg.norm(axis)
        return 2*np.outer(axis, axis)-np.eye(3)
    skew = np.array([[0., -cross[2], cross[1]], [cross[2], 0., -cross[0]], [-cross[1], cross[0], 0.]])
    return np.eye(3)+skew+skew@skew/max(1e-12, 1+dot)


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
        self._pending_rotation = None
        self._last_input = -math.inf
        self._frame_timer = QTimer(canvas)
        self._frame_timer.setSingleShot(True)
        self._frame_timer.setInterval(16)
        reference = weakref.ref(self)
        self._frame_timer.timeout.connect(lambda: reference() and reference()._flush_rotation())
        self._visibility = _CameraVisibility(self)
        canvas.mpl_connect("button_press_event", self._press)
        canvas.mpl_connect("motion_notify_event", self._motion)
        canvas.mpl_connect("button_release_event", self._release)
        canvas.mpl_connect("scroll_event", self._scroll)
        canvas.mpl_connect("key_press_event", self._key)
        canvas.mpl_connect('figure_leave_event', self._release)

    def refresh_axes(self) -> None:
        active = set(self._axes())
        self._fit_spans = {axis: spans for axis, spans in self._fit_spans.items() if axis in active}
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
        self._last_input = time.monotonic()
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
            'basis': camera_basis(axis.elev, axis.azim, getattr(axis, 'roll', 0)),
            'inverted': str(QSettings('PhaseStudio','PhaseStudio').value('viewer/invertMouseRotation','false')).lower() == 'true',
        }
        try:
            sensitivity=float(QSettings('PhaseStudio','PhaseStudio').value('viewer/rotationSensitivity',1.))
            self._drag['sensitivity']=max(.25,min(3.,sensitivity)) if math.isfinite(sensitivity) else 1.
        except (ValueError,TypeError):
            self._drag['sensitivity']=1.
        self._interaction('press')  # Pause automatic motion before the first move.
        set_cursor = getattr(self.canvas, "setCursor", None)
        if callable(set_cursor):
            set_cursor(Qt.SizeAllCursor if mode == "pan" else Qt.ClosedHandCursor)

    def _sphere(self, x, y, axis):
        viewport = axis.get_position(original=True).transformed(axis.figure.transFigure)
        radius = max(1., min(viewport.width, viewport.height)*.45)
        point = np.array([(x-(viewport.x0+viewport.width/2))/radius,
                          (y-(viewport.y0+viewport.height/2))/radius, 0.])
        length = float(np.dot(point, point))
        if length <= 1:
            point[2] = math.sqrt(1-length)
        else:
            point /= math.sqrt(length)
        return point

    def _flush_rotation(self):
        pending, self._pending_rotation = self._pending_rotation, None
        if pending is None:
            return
        axis, x0, y0, x1, y1, start_basis, inverted = pending
        if not self._valid_axis(axis):
            return
        rotation = trackball_rotation(self._sphere(x0,y0,axis), self._sphere(x1,y1,axis))
        basis = (rotation.T if inverted else rotation)@start_basis
        elev, azim, roll = camera_angles(basis)
        self._orientation_changed(elev, azim, axis)
        # Owner callbacks retain their established metadata/depth-cue hooks.
        axis.view_init(elev=elev, azim=azim, roll=roll)
        self.canvas.draw_idle()

    def _motion(self, event) -> None:
        if self._drag is None:
            return
        self._last_input = time.monotonic()
        dx = float(getattr(event, "x", self._drag["x"])) - self._drag["x"]
        dy = float(getattr(event, "y", self._drag["y"])) - self._drag["y"]
        if math.hypot(dx, dy) < self.DRAG_THRESHOLD_PX and not self._drag["moved"]:
            return
        self._drag["moved"] = True
        axis = self._drag["axis"]
        if self._drag["mode"] == "rotate":
            dx*=self._drag.get('sensitivity',1.);dy*=self._drag.get('sensitivity',1.)
            self._pending_rotation = (axis, self._drag['x'], self._drag['y'],
                                      self._drag['x']+dx, self._drag['y']+dy,
                                      self._drag['basis'], self._drag['inverted'])
            if not self._frame_timer.isActive():
                self._frame_timer.start()
            self._interaction("rotate")
        else:
            self._pan(axis, dx, dy)
            self._interaction("pan")
            self.canvas.draw_idle()

    def _pan(self, axis, dx: float, dy: float) -> None:
        spans = np.asarray([hi - lo for lo, hi in self._drag["limits"]], dtype=np.float64)
        pixels = max(120.0, float(min(self.canvas.width(), self.canvas.height())))
        right, up, _toward = camera_basis(axis.elev, axis.azim, getattr(axis,'roll',0))
        delta = (-dx * right - dy * up) * (float(np.mean(spans)) / pixels)
        limits = tuple(
            (lo + float(delta[i]), hi + float(delta[i]))
            for i, (lo, hi) in enumerate(self._drag["limits"])
        )
        axis.set_xlim3d(*limits[0], auto=False)
        axis.set_ylim3d(*limits[1], auto=False)
        axis.set_zlim3d(*limits[2], auto=False)

    def _release(self, _event) -> None:
        if self._drag is not None:
            self._last_input = time.monotonic()
        self._frame_timer.stop()
        self._flush_rotation()  # The last desired orientation is never dropped.
        self._drag = None
        unset_cursor = getattr(self.canvas, "unsetCursor", None)
        if callable(unset_cursor):
            unset_cursor()

    def _scroll(self, event) -> None:
        axis = getattr(event, "inaxes", None)
        if not self._valid_axis(axis):
            return
        self.active_axis = axis
        self._last_input = time.monotonic()
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

    def allow_auto_rotation(self):
        return (self.canvas.isVisible() and self.canvas.window().isActiveWindow()
                and self._drag is None and self._pending_rotation is None
                and time.monotonic()-self._last_input >= 2.)

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
