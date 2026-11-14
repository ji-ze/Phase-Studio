"""Cancellable keyed input work with queued metadata/completion/error signals."""
import threading
from concurrent.futures import CancelledError
from PySide6.QtCore import QObject, Signal, Slot


class InputReadinessLoader(QObject):
    metadata = Signal(object)
    completed = Signal(object)
    failed = Signal(object)
    _metadata_arrived = Signal(int, object)
    _result_arrived = Signal(int, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.generation = 0
        self.key = None
        self.state = 'Unavailable'
        self._cancel = threading.Event()
        self._metadata_arrived.connect(self._deliver_metadata)
        self._result_arrived.connect(self._deliver_result)

    def cancel(self):
        self._cancel.set()
        self.generation += 1
        self.state = 'Cancelled'

    def start(self, key, load):
        if self.key == key and self.state in ('Loading', 'Parsed', 'Validated'):
            return False
        self.cancel()
        generation = self.generation
        self._cancel = cancel = threading.Event()
        self.destroyed.connect(lambda *_: cancel.set())
        self.key = key
        self.state = 'Loading'

        def emit(signal, *values):
            if not cancel.is_set():
                try:
                    signal.emit(generation, *values)
                except RuntimeError:
                    if not cancel.is_set():
                        raise

        def metadata(value):
            emit(self._metadata_arrived, value)

        def worker():
            from .hkl_diagnostics import diagnostic_cancellation
            try:
                with diagnostic_cancellation(cancel):
                    result = load(metadata)
                emit(self._result_arrived, result, None)
            except CancelledError:
                return
            except Exception as error:
                emit(self._result_arrived, None, error)

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()
        return True

    @Slot(int, object)
    def _deliver_metadata(self, generation, metadata):
        if generation == self.generation and not self._cancel.is_set():
            self.state = 'Parsed'
            self.metadata.emit(metadata)

    @Slot(int, object, object)
    def _deliver_result(self, generation, result, error):
        if generation != self.generation or self._cancel.is_set():
            return
        self.state = 'Invalid' if error else 'Validated'
        (self.failed if error else self.completed).emit(error if error else result)
