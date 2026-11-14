"""Regression checks for the main-window presentation changes."""
import os
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def test_idle_and_partial_structure_presentation():
    from PySide6.QtWidgets import QApplication
    import numpy as np
    from phase_studio import app as a

    qt = QApplication.instance() or QApplication([])
    with patch.object(a.IterativeSuperflipPipelineQtGUI, 'load_settings', lambda self: None), \
         patch.object(a.IterativeSuperflipPipelineQtGUI, 'save_settings', lambda self: None), \
         patch.object(a.IterativeSuperflipPipelineQtGUI, 'refresh_sharped_models', lambda self: None):
        window = a.IterativeSuperflipPipelineQtGUI()
        window.timer.stop()
        window.resize(1280, 720)
        window.show()
        qt.processEvents()
        assert window.main_splitter.handleWidth() >= 4
        window.resize(960, 540)
        qt.processEvents()
        assert window.dashboard_scroll.horizontalScrollBar().maximum() > 0
        window.dashboard_scroll.ensureWidgetVisible(window.metrics_reset_btn)
        qt.processEvents()
        assert window.dashboard_scroll.horizontalScrollBar().value() > 0
        window.resize(1280, 720)
        qt.processEvents()
        assert window.inputs['manual_cell_a'].specialValueText() == 'Unset'
        assert window.log_text.placeholderText()
        assert not window.structure_title_texts
        assert not any(button.isEnabled() for button in window.structure_fullscreen_buttons.values())
        assert 'Metrics will appear as phasing cycles complete.' in [
            text.get_text() for text in window.metrics_axes['quality_0'].texts]
        window.reference_atoms_for_plot = [a.AtomSite('C1', 'C', np.array([.1, .1, .1]))]
        window._update_structure_views()
        assert window.structure_fullscreen_buttons['reference'].isEnabled()
        assert not window.structure_fullscreen_buttons['superflip'].isEnabled()
        assert not window.structure_fullscreen_buttons['deblur'].isEnabled()
        assert len(window.structure_axes) == 3
        window.close()
