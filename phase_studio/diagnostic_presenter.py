"""Shared diagnostic presentation without constructing a hidden scientific GUI."""
from PySide6.QtWidgets import QWidget
from .app import IterativeSuperflipPipelineQtGUI as _Main


class DiagnosticPresenter(QWidget):
    # Reuse the existing native Qt builders exactly. These presentation-only
    # methods require no workflow, timer, credentials, executable or main window.
    _diagnostic_header = _Main._diagnostic_header
    _diagnostic_input_summary = _Main._diagnostic_input_summary
    _diagnostic_metric_grid = _Main._diagnostic_metric_grid
    _configure_diagnostic_table = staticmethod(_Main._configure_diagnostic_table)
    _build_hkl_validation_dialog = _Main._build_hkl_validation_dialog
    _build_hkl_completeness_dialog = _Main._build_hkl_completeness_dialog
