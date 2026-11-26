"""The Capture tab: record the game traffic with Windows' built-in pktmon."""
import os
import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget

from ..capture import pktmon
from ..viewlogic import describe_running_capture
from .background_workers import PktmonFinishWorker

APPLICATION_NAME = 'nwkills'
TICK_INTERVAL_MS = 1000
EXPLANATION = ('Records the game traffic with <b>pktmon</b>, the packet monitor built into Windows 10 and 11, so Wireshark is not needed. '
               'It captures all UDP traffic on this computer while you play; when you press Stop, only the game server\'s packets are kept and everything else is thrown away. '
               'Start the capture <b>before</b> you join the server, so the player list is included. Needs administrator rights: right-click nwkills-gui.exe and choose "Run as administrator".')
BUFFER_TOOLTIP = ('pktmon logs into a circular file of this size and overwrites the start of the capture when it is full. 4096 MB holds several hours of play. '
                  'The file is deleted after conversion.')


class CaptureTab(QWidget):
    captureSaved = Signal(str)               # the .pcapng of a finished capture
    statusMessage = Signal(str)
    logMessage = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.capturing = False
        self.started_at_s = 0.0
        self.trace_path: Optional[str] = None
        self.final_path: Optional[str] = None
        self.finish_worker: Optional[PktmonFinishWorker] = None
        layout = QVBoxLayout(self)
        explanation = QLabel(EXPLANATION)
        explanation.setWordWrap(True)
        explanation.setTextFormat(Qt.RichText)
        layout.addWidget(explanation)
        layout.addWidget(self._build_settings_group())
        layout.addLayout(self._build_buttons())
        self.state_label = QLabel()
        self.state_label.setWordWrap(True)
        layout.addWidget(self.state_label)
        layout.addStretch(1)
        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(TICK_INTERVAL_MS)
        self.tick_timer.timeout.connect(self.show_running_state)
        self.refresh_state()

    def _build_settings_group(self) -> QGroupBox:
        group = QGroupBox('Capture')
        form = QFormLayout(group)
        row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        browse_button = QPushButton('Browse…')
        browse_button.clicked.connect(self.browse_folder)
        row.addWidget(self.folder_edit, 1)
        row.addWidget(browse_button)
        form.addRow('Save captures in', row)
        self.buffer_spin = QSpinBox()
        self.buffer_spin.setRange(512, 65536)
        self.buffer_spin.setSingleStep(512)
        self.buffer_spin.setValue(pktmon.DEFAULT_BUFFER_MB)
        self.buffer_spin.setSuffix(' MB')
        self.buffer_spin.setToolTip(BUFFER_TOOLTIP)
        form.addRow('Temporary log size', self.buffer_spin)
        return group

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.start_button = QPushButton('Start capture')
        self.start_button.setStyleSheet('font-weight: bold; padding: 6px 22px;')
        self.start_button.clicked.connect(self.start_capture)
        self.stop_button = QPushButton('Stop and open')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_capture)
        row.addWidget(self.start_button)
        row.addWidget(self.stop_button)
        row.addStretch(1)
        return row

    # ---- folder
    def browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, 'Save captures in', self.folder_edit.text() or os.path.expanduser('~'))
        if folder:
            self.folder_edit.setText(folder)

    def capture_folder(self) -> str:
        return self.folder_edit.text().strip() or os.path.join(os.path.expanduser('~'), 'Documents', 'nwkills captures')

    # ---- state
    def refresh_state(self) -> None:
        if self.capturing:
            return
        problem = pktmon.PktmonCapture().check_ready()
        self.start_button.setEnabled(problem is None and not (self.finish_worker and self.finish_worker.isRunning()))
        self.state_label.setText(problem or 'Ready. Press Start capture, then join the server.')

    def show_running_state(self) -> None:
        if not self.capturing:
            return
        try:
            logged_bytes = os.path.getsize(self.trace_path)
        except OSError:
            logged_bytes = 0
        text, _nearly_full = describe_running_capture(int(time.time() - self.started_at_s), logged_bytes, self.buffer_spin.value())
        self.state_label.setText(text)
        self.state_label.setTextFormat(Qt.RichText)

    def _set_controls_enabled(self, idle: bool) -> None:
        self.folder_edit.setEnabled(idle)
        self.buffer_spin.setEnabled(idle)

    # ---- start and stop
    def start_capture(self) -> None:
        base = os.path.join(self.capture_folder(), pktmon.timestamped_capture_name())
        try:
            self.trace_path, self.final_path = base + '.etl', base + '.pcapng'
            pktmon.PktmonCapture().start(self.trace_path, self.buffer_spin.value())
        except Exception as error:
            QMessageBox.warning(self, APPLICATION_NAME, 'The capture could not be started:\n\n%s' % error)
            self.refresh_state()
            return
        self.capturing = True
        self.started_at_s = time.time()
        self.tick_timer.start()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self._set_controls_enabled(False)
        self.show_running_state()
        self.statusMessage.emit('Capturing …')

    def stop_capture(self) -> None:
        if not self.capturing:
            return
        self.capturing = False
        self.tick_timer.stop()
        self.stop_button.setEnabled(False)
        self.state_label.setTextFormat(Qt.PlainText)
        self.state_label.setText('Stopping and converting … (a long capture can take a minute or two)')
        self.finish_worker = PktmonFinishWorker(self.trace_path, self.final_path, self)
        self.finish_worker.message.connect(self.logMessage)
        self.finish_worker.message.connect(self.statusMessage)
        self.finish_worker.done.connect(self._on_finished)
        self.finish_worker.failed.connect(self._on_failed)
        self.finish_worker.start()

    def _return_to_idle(self) -> None:
        self._set_controls_enabled(True)
        self.stop_button.setEnabled(False)
        self.state_label.setTextFormat(Qt.PlainText)
        self.refresh_state()

    def _on_finished(self, path: str, info: str) -> None:
        self._return_to_idle()
        self.state_label.setText('Saved %s (%s).' % (path, info))
        self.statusMessage.emit('Capture saved. Loading it …')
        self.captureSaved.emit(path)

    def _on_failed(self, message: str) -> None:
        self._return_to_idle()
        self.state_label.setText('The capture failed.')
        self.logMessage.emit(message)
        QMessageBox.warning(self, APPLICATION_NAME, 'The capture could not be completed:\n\n' + (message if len(message) < 600 else message[-600:]))

    # ---- closing the window
    def allow_window_to_close(self) -> bool:
        """Asks what to do with a running capture. False = the user wants to keep capturing, so the window stays open."""
        if self.capturing:
            box = QMessageBox(QMessageBox.Question, APPLICATION_NAME, 'A capture is still running.', QMessageBox.NoButton, self)
            keep_button = box.addButton('Stop and keep it', QMessageBox.AcceptRole)
            discard_button = box.addButton('Discard it', QMessageBox.DestructiveRole)
            box.addButton('Keep capturing', QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is keep_button:
                self.stop_capture()
                self.finish_worker.wait()
            elif box.clickedButton() is discard_button:
                self.capturing = False
                self.tick_timer.stop()
                pktmon.PktmonCapture().discard(self.trace_path)
            else:
                return False
        elif self.finish_worker and self.finish_worker.isRunning():
            self.finish_worker.wait()
        return True
