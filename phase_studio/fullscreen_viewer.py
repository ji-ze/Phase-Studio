"""Small shared host for temporarily detaching an existing structure viewer.

The live widget is moved rather than copied.  Candidate selection, camera,
threshold controls, view mode, and renderer caches therefore remain the same
objects before, during, and after fullscreen inspection.
"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Line3DCollection

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from phase_studio.structure_camera import StructureCameraController, fit_projected_structure, camera_settings_button


def _enter_fullscreen(window):
    window._windowed_geometry=window.normalGeometry() if window.isMaximized() else window.geometry()
    window._windowed_maximized=window.isMaximized()
    window.showFullScreen()


def _leave_fullscreen(window):
    if getattr(window,'_windowed_maximized',False):
        window.showMaximized()
    else:
        geometry=getattr(window,'_windowed_geometry',window.normalGeometry())
        window.showNormal()
        if geometry.isValid():window.setGeometry(geometry)


class DetachedViewerWindow(QDialog):
    """Host one live viewer widget and restore it to its original container."""

    def __init__(self, parent: QWidget, viewer: QWidget, title: str) -> None:
        super().__init__(parent, Qt.Window)
        self.setObjectName("detachedStructureViewer")
        self.setWindowTitle(title)
        self._viewer = viewer
        self._original_parent = viewer.parentWidget()
        self._original_layout = self._original_parent.layout() if self._original_parent else None
        self._original_index = self._container_index()
        self._restored = False

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)
        bar = QHBoxLayout()
        label = QLabel(title)
        self.title_label = label
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        bar.addWidget(label)
        bar.addStretch(1)
        self.fullscreen_button = QPushButton("Exit fullscreen")
        self.fullscreen_button.setToolTip("Toggle fullscreen (F11)")
        self.close_button = QPushButton("Close viewer")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.close_button.clicked.connect(self.close)
        bar.addWidget(self.fullscreen_button)
        bar.addWidget(self.close_button)
        root.addLayout(bar)
        root.addWidget(viewer, 1)

    def _container_index(self) -> int:
        parent = self._original_parent
        if parent is not None and hasattr(parent, "indexOf"):
            index = int(parent.indexOf(self._viewer))
            if index >= 0:
                return index
        layout = self._original_layout
        return int(layout.indexOf(self._viewer)) if layout is not None else -1

    def open_fullscreen(self) -> None:
        """Use the parent's screen and open as a true fullscreen window."""
        screen = self.parentWidget().screen() if self.parentWidget() is not None else None
        if screen is not None:
            self.setGeometry(screen.availableGeometry())
        _enter_fullscreen(self)
        self.raise_()
        self.activateWindow()

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            _leave_fullscreen(self)
            self.fullscreen_button.setText("Enter fullscreen")
        else:
            _enter_fullscreen(self)
            self.fullscreen_button.setText("Exit fullscreen")

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
            return
        if event.key() == Qt.Key_Escape:
            # Esc leaves true fullscreen without discarding the detached
            # inspection session.  The explicit Close viewer action is the
            # only keyboard-independent way back to the embedded layout.
            if self.isFullScreen():
                _leave_fullscreen(self)
                self.fullscreen_button.setText("Enter fullscreen")
            return
        super().keyPressEvent(event)

    def _restore_viewer(self) -> None:
        if self._restored:
            return
        self._restored = True
        parent = self._original_parent
        if parent is None:
            return
        viewer = self._viewer
        if hasattr(parent, "insertWidget"):
            parent.insertWidget(max(0, self._original_index), viewer)
        elif self._original_layout is not None and hasattr(self._original_layout, "insertWidget"):
            self._original_layout.insertWidget(max(0, self._original_index), viewer, 1)
        else:
            viewer.setParent(parent)
        viewer.show()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._restore_viewer()
        super().closeEvent(event)


def show_detached_viewer(
    owner: QWidget,
    viewer: QWidget,
    title: str,
    existing: Optional[DetachedViewerWindow] = None,
) -> DetachedViewerWindow:
    """Raise an existing host or create one; never multiply identical viewers."""
    if existing is not None and not existing._restored:
        existing.raise_()
        existing.activateWindow()
        return existing
    window = DetachedViewerWindow(owner, viewer, title)
    window.open_fullscreen()
    return window


class SingleStructureViewerWindow(QDialog):
    """Independent interactive canvas for exactly one scientific structure.

    ``presentation`` returns a dictionary containing atoms, Cartesian
    coordinates, bonds, optional cell segments, fit center/radius and compact
    metadata.  State-changing controls call the owner first and then request
    the same authoritative presentation again, so this window never owns a
    second candidate or threshold state.
    """

    def __init__(
        self, parent: QWidget, title: str, presentation: Callable[[], dict],
        *, color_for: Callable[[str], str], set_mode: Optional[Callable[[str], None]] = None,
        adjust_threshold: Optional[Callable[[bool], None]] = None,
        previous_cycle: Optional[Callable[[], None]] = None,
        next_cycle: Optional[Callable[[], None]] = None,
        latest_cycle: Optional[Callable[[], None]] = None,
        elev: float = 20.0, azim: float = 35.0,
        roll: float = 0.0, camera_limits=None, camera_zoom=None,
    ) -> None:
        super().__init__(parent, Qt.Window)
        self.setObjectName("singleStructureViewer")
        self.setWindowTitle(title)
        self._presentation = presentation
        self._color_for = color_for
        self._elev, self._azim = float(elev), float(azim)
        self._roll = float(roll)
        self._initial_camera = (camera_limits,camera_zoom) if camera_limits is not None else None
        self._auto_rotate = False
        self._user_camera_interacted = False
        self._fit = None
        self._rotation_timer = QTimer(self)
        self._rotation_timer.setInterval(45)
        self._rotation_timer.timeout.connect(self._rotate_camera)
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(0)
        self._fit_timer.timeout.connect(self._apply_initial_fit)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(5)
        bar = QHBoxLayout()
        self.title_label = QLabel(title)
        font = self.title_label.font(); font.setBold(True); self.title_label.setFont(font)
        bar.addWidget(self.title_label)
        bar.addStretch(1)

        primary_controls = QHBoxLayout()
        primary_controls.setSpacing(5)
        secondary_controls = QHBoxLayout()
        secondary_controls.setSpacing(5)

        def action(layout, text: str, callback: Callable[[], None]) -> QPushButton:
            button = QPushButton(text)
            button.clicked.connect(callback)
            layout.addWidget(button)
            return button

        if previous_cycle is not None:
            action(primary_controls, "Previous", lambda: self._change(previous_cycle))
        if next_cycle is not None:
            action(primary_controls, "Next", lambda: self._change(next_cycle))
        if latest_cycle is not None:
            action(primary_controls, "Latest", lambda: self._change(latest_cycle))
        if previous_cycle is not None or next_cycle is not None or latest_cycle is not None:
            primary_controls.addSpacing(8)
        primary_controls.addStretch(1)
        primary_controls.addWidget(camera_settings_button(self))
        action(primary_controls, "Fit", self.fit)
        action(primary_controls, "Reset view", self.reset_view)
        self.auto_rotate_button = action(primary_controls, "Auto rotate: Off", self._toggle_auto_rotate)
        self.auto_rotate_button.setCheckable(True)
        bar.addLayout(primary_controls)
        root.addLayout(bar)

        if adjust_threshold is not None:
            self.add_atoms_button=action(secondary_controls, "+ atoms", lambda: self._change(lambda: adjust_threshold(True)))
            self.remove_atoms_button=action(secondary_controls, "- atoms", lambda: self._change(lambda: adjust_threshold(False)))
        secondary_controls.addStretch(1)
        if set_mode is not None:
            action(secondary_controls, "Complete molecules", lambda: self._change(lambda: set_mode("molecule")))
            action(secondary_controls, "Full cell", lambda: self._change(lambda: set_mode("cell")))
        secondary_controls.addSpacing(8)
        self.fullscreen_button = action(primary_controls, "Enter fullscreen", self.toggle_fullscreen)
        self.fullscreen_button.setObjectName("fullscreenToggle")
        self.close_button = action(secondary_controls, "Close viewer", self.close)
        self.metadata_label = QLabel("")
        self.metadata_label.setWordWrap(True)
        self.metadata_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.legend_label = QLabel("")
        self.legend_label.setWordWrap(True)
        info_row = QHBoxLayout()
        info_row.setSpacing(8)
        scientific_info = QVBoxLayout()
        scientific_info.setSpacing(1)
        scientific_info.addWidget(self.metadata_label)
        scientific_info.addWidget(self.legend_label)
        info_row.addLayout(scientific_info, 1)
        info_row.addLayout(secondary_controls)
        root.addLayout(info_row)
        self.figure = Figure(figsize=(12, 7), dpi=100)
        self.figure.patch.set_facecolor("#ffffff")
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setObjectName("singleStructureCanvas")
        self.canvas.setToolTip("")
        camera_hint = QLabel(
            "Left-drag: rotate · Right/Middle/Shift-left-drag: pan · "
            "Wheel: zoom · Double-click: fit"
        )
        camera_hint.setObjectName("structureInteractionHint")
        camera_hint.setAlignment(Qt.AlignRight)
        camera_hint.setToolTip(
            "Left-drag: rotate · Right/Middle/Shift-left-drag: pan · "
            "Wheel: zoom · Double-click: fit"
        )
        hint_font = camera_hint.font()
        if hint_font.pointSizeF() > 8.0:
            hint_font.setPointSizeF(8.0)
            camera_hint.setFont(hint_font)
        camera_hint.setVisible(True)
        self.canvas.setToolTip("")
        root.addWidget(camera_hint)
        root.addWidget(self.canvas, 1)
        self._camera = StructureCameraController(
            self.canvas,
            lambda: self.figure.axes[:1],
            fit=self.fit,
            reset=self.reset_view,
            orientation_changed=self._orientation_changed,
            interaction=self._camera_interaction,
            toggle_auto_rotate=lambda: self.auto_rotate_button.click(),
        )
        self.render()
        if self._initial_camera is not None and self.figure.axes:
            limits,zoom=self._initial_camera
            axis=self.figure.axes[0]
            axis.set_xlim3d(*limits[0]);axis.set_ylim3d(*limits[1]);axis.set_zlim3d(*limits[2])
            if zoom is not None:
                axis.set_box_aspect((1,1,1),zoom=zoom);axis._phase_fit_zoom=zoom
            self._user_camera_interacted=True

    def _change(self, callback: Callable[[], None]) -> None:
        callback()
        self.render()

    def _refresh_viewer_palette(self):
        self._geometry_signature=None
        self.render()

    def render(self) -> None:
        data = self._presentation() or {}
        self.candidate_identity=data.get('candidate_identity')
        for name,key in (('add_atoms_button','add_atoms'),('remove_atoms_button','remove_atoms')):
            button=getattr(self,name,None)
            if button is not None:
                button.setEnabled(data.get(key+'_available',True))
                button.setToolTip(data.get(key+'_reason',''))
        atoms = list(data.get('atoms', ()))
        coords = np.asarray(data.get('coords', ()), dtype=np.float64).reshape(-1,3)
        geometry_signature = (coords.tobytes(), tuple(tuple(bond) for bond in data.get('bonds',())),
            np.asarray(data.get('cell_segments',())).tobytes(), data.get('atom_size',34.),
            tuple((getattr(atom,'label',''),getattr(atom,'element','')) for atom in atoms))
        if geometry_signature == getattr(self,'_geometry_signature',None):
            title = str(data.get('title','')).strip()
            if title:
                self.setWindowTitle(title); self.title_label.setText(title)
            self.metadata_label.setText(str(data.get('metadata','')))
            return  # Reuse persistent collections and the exact camera.
        self._geometry_signature = geometry_signature
        previous_limits = None
        previous_zoom = None
        if self.figure.axes:
            old_axis = self.figure.axes[0]
            previous_limits = (old_axis.get_xlim3d(), old_axis.get_ylim3d(), old_axis.get_zlim3d())
            previous_zoom = getattr(old_axis, "_phase_fit_zoom", None)
            self._elev = float(self.figure.axes[0].elev)
            self._azim = float(self.figure.axes[0].azim)
            self._roll = float(self.figure.axes[0].roll)
        self.figure.clear()
        axis = self.figure.add_subplot(1, 1, 1, projection="3d")
        atoms = list(data.get("atoms", ()))
        coords = np.asarray(data.get("coords", ()), dtype=np.float64).reshape(-1, 3)
        signature = (coords.tobytes(), str(data.get("metadata", "")), str(data.get("title", "")),
                     tuple((getattr(atom, "label", ""), getattr(atom, "element", "")) for atom in atoms))
        preserve_camera = signature == getattr(self, "_presentation_signature", None) and previous_limits is not None
        self._presentation_signature = signature
        if len(atoms) and len(coords):
            axis.set_proj_type("ortho")
            axis.view_init(elev=self._elev, azim=self._azim, roll=getattr(self,'_roll',0.))
            colors = [self._color_for(str(getattr(atom, "element", "C"))) for atom in atoms]
            count_scale = max(0.20, min(1.0, (320.0 / max(1, len(atoms))) ** 0.32))
            sizes = np.asarray([
                max(3.0, min(90.0, float(data.get("atom_size", 34.0)) * count_scale))
            ] * len(atoms))
            axis.scatter(coords[:, 0], coords[:, 1], coords[:, 2], s=sizes, c=colors,
                         edgecolors="#ffffff", linewidths=0.2, depthshade=False)
            bonds = list(data.get("bonds", ()))
            if bonds:
                axis.add_collection3d(Line3DCollection(
                    [np.asarray((coords[i], coords[j])) for i, j in bonds],
                    colors="#5d6b86", linewidths=max(0.28, 1.25 * count_scale),
                ))
            segments = list(data.get("cell_segments", ()))
            self._fit_coordinates = np.vstack((coords, np.asarray(segments).reshape(-1, 3))) if segments else coords
            if segments:
                axis.add_collection3d(Line3DCollection(
                    segments, colors="#44b7ff", linewidths=0.75, alpha=0.75,
                ))
            fit = data.get("fit")
            if fit is None:
                center = (coords.min(axis=0) + coords.max(axis=0)) / 2.0
                radius = max(1.0e-3, float(np.max(np.linalg.norm(coords - center, axis=1))))
                fit = (center, radius)
            self._fit = fit
            if not preserve_camera:
                self._user_camera_interacted = False
        else:
            axis.text2D(0.5, 0.5, "Structure unavailable", ha="center", va="center", transform=axis.transAxes, fontfamily="Segoe UI")
            self._fit = None
        axis.set_axis_off()
        title = str(data.get("title", "")).strip()
        if title:
            self.setWindowTitle(title)
            self.title_label.setText(title)
        self.metadata_label.setText(str(data.get("metadata", "")))
        elements = sorted({str(getattr(atom, "element", "C")) for atom in atoms})
        self.legend_label.setText(
            "<b>Elements:</b> " + " &nbsp; ".join(
                f'<span style="color:{self._color_for(element)}">&#9632;</span> {element}'
                for element in elements
            ) if elements else ""
        )
        self.figure.subplots_adjust(left=0.005, right=0.995, bottom=0.005, top=0.995)
        self._camera.refresh_axes()
        self.canvas.draw_idle()
        # The first fit must see the native canvas size.  The queued fit runs
        # after layout; the short timer coalesces any ensuing resize burst.
        if preserve_camera and self._user_camera_interacted:
            axis.set_xlim3d(*previous_limits[0], auto=False)
            axis.set_ylim3d(*previous_limits[1], auto=False)
            axis.set_zlim3d(*previous_limits[2], auto=False)
            if previous_zoom is not None:
                axis.set_box_aspect((1,1,1), zoom=previous_zoom)
                axis._phase_fit_zoom = previous_zoom
        else:
            self._fit_timer.start()

    def _apply_initial_fit(self) -> None:
        if not self._user_camera_interacted:
            self.fit()

    def _orientation_changed(self, elev: float, azim: float, axis) -> None:
        self._elev, self._azim = float(elev), float(azim)
        axis.view_init(elev=self._elev, azim=self._azim)

    def _camera_interaction(self, kind: str) -> None:
        if kind in {"rotate", "pan", "zoom"}:
            self._user_camera_interacted = True

    def fit(self) -> None:
        if self._fit is None or not self.figure.axes:
            return
        axis = self.figure.axes[0]
        fit_projected_structure(axis, self._fit_coordinates)
        self.canvas.draw_idle()

    def reset_view(self) -> None:
        self._elev, self._azim = 20.0, 35.0
        self._user_camera_interacted = False
        if self.figure.axes:
            self.figure.axes[0].view_init(elev=self._elev, azim=self._azim)
        self.fit()

    def _toggle_auto_rotate(self) -> None:
        self._auto_rotate = bool(self.auto_rotate_button.isChecked())
        self.auto_rotate_button.setText(
            "Auto rotate: On" if self._auto_rotate else "Auto rotate: Off"
        )
        if self._auto_rotate:
            self._rotation_timer.start()
        else:
            self._rotation_timer.stop()

    def _rotate_camera(self) -> None:
        """Advance only the current camera; prepared geometry stays untouched."""
        if not self.figure.axes or not self._camera.allow_auto_rotation():
            return
        axis = self.figure.axes[0]
        self._elev = float(axis.elev)
        self._azim = (float(axis.azim) + 0.6) % 360.0
        axis.view_init(elev=self._elev, azim=self._azim, roll=axis.roll)
        self.canvas.draw_idle()

    def open_maximized(self) -> None:
        from phase_studio.ui_branding import fit_dialog_to_available_screen
        from PySide6.QtCore import QSize
        fit_dialog_to_available_screen(
            self, QSize(1400, 860), width_fraction=0.92, height_fraction=0.90,
        )
        self.show()
        self.raise_()
        self.activateWindow()
        self._fit_timer.start()

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            _leave_fullscreen(self); self.fullscreen_button.setText("Enter fullscreen")
        else:
            _enter_fullscreen(self); self.fullscreen_button.setText("Exit fullscreen")
        if not self._user_camera_interacted:
            self._fit_timer.start()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not self._user_camera_interacted:
            self._fit_timer.start()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_F11:
            self.toggle_fullscreen(); return
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            _leave_fullscreen(self); self.fullscreen_button.setText("Enter fullscreen"); return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._rotation_timer.stop()
        super().closeEvent(event)


def show_single_structure_viewer(
    owner: QWidget, title: str, presentation: Callable[[], dict], *,
    color_for: Callable[[str], str], existing: Optional[SingleStructureViewerWindow] = None,
    **callbacks,
) -> SingleStructureViewerWindow:
    if existing is not None and existing.isVisible():
        existing.render(); existing.raise_(); existing.activateWindow(); return existing
    window = SingleStructureViewerWindow(
        owner, title, presentation, color_for=color_for, **callbacks,
    )
    window.open_maximized()
    return window
