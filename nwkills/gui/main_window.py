"""The main window: opens a capture, shows its packets, runs the conversion, shows the results."""
import os
import time
import traceback
from typing import Optional

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget

from ..packets.server_flow import FlowKey
from ..viewlogic import OverallProgress, PacketSummarizer, StaleResultFolderSweeper, TemporaryResultFolder
from .background_workers import CaptureLoadWorker, ConversionWorker, LoadedPacketList
from .capture_tab import CaptureTab
from .conversion_footer import ConversionFooter
from .options_tab import OptionsTab
from .packets_tab import PacketsTab
from .results_tab import ResultsTab

APPLICATION_NAME = 'nwkills'
CAPTURE_FILE_SUFFIXES = ('.pcapng', '.pcap')
PACKETS_TAB, OPTIONS_TAB, RESULTS_TAB, CAPTURE_TAB = range(4)
LOG_HEIGHT = 130
MAX_ERROR_TEXT = 600


def _short(message: str, limit: int) -> str:
    return message if len(message) < limit else message[-limit:]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APPLICATION_NAME)
        self.resize(1280, 820)
        self.setAcceptDrops(True)
        self.settings = QSettings('nwkills', 'nwkills')
        self.capture_path: Optional[str] = None
        self.load_worker: Optional[CaptureLoadWorker] = None
        self.conversion_worker: Optional[ConversionWorker] = None
        self.result_folder = TemporaryResultFolder()
        self.progress_calculator = OverallProgress()
        self.conversion_started_at_s = 0.0
        StaleResultFolderSweeper().sweep()

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(self._build_top_bar())

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.packets_tab, self.options_tab, self.results_tab, self.capture_tab = PacketsTab(), OptionsTab(), ResultsTab(), CaptureTab()
        for tab, title in ((self.packets_tab, 'Packets'), (self.options_tab, 'Options'), (self.results_tab, 'Results'), (self.capture_tab, 'Capture')):
            self.tabs.addTab(tab, title)
        self.tabs.setTabEnabled(RESULTS_TAB, False)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(LOG_HEIGHT)
        self.log_view.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.log_view.hide()
        layout.addWidget(self.log_view)
        self.footer = ConversionFooter()
        layout.addWidget(self.footer)
        self.statusBar().showMessage('Open a capture to begin.')
        self._connect_signals()
        self.options_tab.restore(self.settings)
        self.capture_tab.folder_edit.setText(self.settings.value('capdir', ''))
        self.show_command_line()

    def _build_top_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 6)
        open_button = QPushButton('Open .pcapng…')
        open_button.clicked.connect(self.open_capture_dialog)
        bar.addWidget(open_button)
        capture_button = QPushButton('Capture…')
        capture_button.setToolTip('Record the game traffic with Windows\' built-in pktmon (no Wireshark needed)')
        capture_button.clicked.connect(lambda: self.tabs.setCurrentIndex(CAPTURE_TAB))
        bar.addWidget(capture_button)
        self.file_label = QLabel('No capture loaded. Open one, or drop a .pcapng onto this window.')
        bar.addWidget(self.file_label, 1)
        return bar

    def _connect_signals(self) -> None:
        self.options_tab.changed.connect(self.show_command_line)
        self.packets_tab.statusMessage.connect(self.statusBar().showMessage)
        self.results_tab.statusMessage.connect(self.statusBar().showMessage)
        self.results_tab.jumpRequested.connect(self.show_in_packets)
        self.capture_tab.statusMessage.connect(self.statusBar().showMessage)
        self.capture_tab.logMessage.connect(self.log_view.appendPlainText)
        self.capture_tab.captureSaved.connect(self.load_capture)
        self.footer.convertRequested.connect(self.convert)
        self.footer.cancelRequested.connect(self.cancel_conversion)
        self.footer.logToggled.connect(self.log_view.setVisible)

    def show_command_line(self, *_ignored) -> None:
        self.options_tab.show_command_line(self.capture_path)

    # ------------------------------------------------------------ loading
    def open_capture_dialog(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, 'Open capture', self.settings.value('lastdir', ''), 'Wireshark captures (*.pcapng *.pcap);;All files (*)')
        if path:
            self.load_capture(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.toLocalFile().lower().endswith(CAPTURE_FILE_SUFFIXES) for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.toLocalFile().lower().endswith(CAPTURE_FILE_SUFFIXES):
                self.load_capture(url.toLocalFile())
                break

    def load_capture(self, path: str) -> None:
        if self.conversion_worker and self.conversion_worker.isRunning():
            QMessageBox.information(self, APPLICATION_NAME, 'A conversion is running. Cancel it first.')
            return
        self.packets_tab.clear()
        self.capture_path = path
        self.settings.setValue('lastdir', os.path.dirname(path))
        self.footer.set_convert_enabled(False)
        self.file_label.setText('Loading %s …' % os.path.basename(path))
        self.statusBar().showMessage('Reading capture …')
        self.show_command_line()
        self.load_worker = CaptureLoadWorker(path, self.options_tab.server_port(), self)
        self.load_worker.message.connect(self.statusBar().showMessage)
        self.load_worker.message.connect(self.log_view.appendPlainText)
        self.load_worker.loaded.connect(self.on_loaded)
        self.load_worker.failed.connect(self.on_load_failed)
        self.load_worker.start()

    def on_loaded(self, loaded: LoadedPacketList) -> None:
        self.packets_tab.show_packets(loaded.items, PacketSummarizer(loaded.profile))
        key: FlowKey = loaded.server_flow_key
        self.file_label.setText('%s   ·   %.0f MB   ·   %s packets, %s from the server   ·   server %s:%d' % (
            os.path.basename(self.capture_path), loaded.file_size / 1e6, format(loaded.frame_count, ','), format(len(loaded.items), ','),
            key.server_address, key.server_port))
        self.footer.set_convert_enabled(True)
        self.statusBar().showMessage('Loaded. Set options if needed, then press Convert.')
        self.tabs.setCurrentIndex(PACKETS_TAB)

    def on_load_failed(self, message: str) -> None:
        self.file_label.setText('Could not load %s' % os.path.basename(self.capture_path or ''))
        self.statusBar().showMessage('Load failed.')
        self.log_view.appendPlainText(message)
        QMessageBox.warning(self, APPLICATION_NAME, _short(message, 400))

    def show_in_packets(self, time_s: float) -> None:
        if self.packets_tab.show_packet_at_time(time_s):
            self.tabs.setCurrentIndex(PACKETS_TAB)

    # ------------------------------------------------------------ converting
    def convert(self) -> None:
        if not self.capture_path:
            return
        self.save_settings()
        request = self.options_tab.build_request(self.capture_path)
        if request.cache_path and not os.path.isdir(os.path.dirname(request.cache_path)):
            try:
                os.makedirs(os.path.dirname(request.cache_path))
            except OSError as error:
                QMessageBox.warning(self, APPLICATION_NAME, 'Cannot create the folder for the cache:\n%s' % error)
                return
        self.packets_tab.stop_indexing()
        # The converter writes its files into a temporary folder; the tables are read into memory and the folder is deleted. CSV files are only written by Export.
        self.result_folder.create()
        request.kills_path = self.result_folder.file_path(os.path.basename(request.kills_path))
        self.log_view.clear()
        self.footer.start()
        self.conversion_started_at_s = time.time()
        self.conversion_worker = ConversionWorker(request, self)
        self.conversion_worker.progress.connect(self.on_progress)
        self.conversion_worker.message.connect(self.log_view.appendPlainText)
        self.conversion_worker.finished_ok.connect(self.on_conversion_done)
        self.conversion_worker.failed.connect(self.on_conversion_failed)
        self.conversion_worker.start()
        self.statusBar().showMessage('Converting …')

    def cancel_conversion(self) -> None:
        if self.conversion_worker:
            self.conversion_worker.cancel()
            self.statusBar().showMessage('Cancelling …')

    def on_progress(self, stage: str, fraction: float) -> None:
        self.footer.show_progress(self.progress_calculator.report(stage, fraction))

    def on_conversion_failed(self, message: str) -> None:
        self.result_folder.discard()
        if not message:
            self.footer.stop('Cancelled')
            self.statusBar().showMessage('Cancelled.')
            return
        self.footer.stop('Failed')
        self.statusBar().showMessage('Conversion failed.')
        self.log_view.appendPlainText(message)
        QMessageBox.warning(self, APPLICATION_NAME, 'Conversion failed:\n\n' + _short(message, MAX_ERROR_TEXT))

    def on_conversion_done(self, paths) -> None:
        self.footer.finish()
        try:
            self.results_tab.show_results(paths, self.options_tab.export_folder(self.capture_path))
            self.tabs.setTabEnabled(RESULTS_TAB, True)
            self.tabs.setCurrentIndex(RESULTS_TAB)
        except Exception:
            self.log_view.appendPlainText(traceback.format_exc())
            QMessageBox.warning(self, APPLICATION_NAME, 'The results could not be shown:\n' + traceback.format_exc()[-400:])
            return
        finally:
            self.result_folder.discard()
        self.statusBar().showMessage('Done in %.0f s. Nothing has been written to disk: use Export to save CSV files.' % (time.time() - self.conversion_started_at_s))

    # ------------------------------------------------------------ closing
    def save_settings(self) -> None:
        self.options_tab.save(self.settings)
        self.settings.setValue('capdir', self.capture_tab.folder_edit.text())

    def closeEvent(self, event):
        if not self.capture_tab.allow_window_to_close():
            event.ignore()
            return
        self.save_settings()
        self.packets_tab.stop_indexing()
        if self.conversion_worker and self.conversion_worker.isRunning():
            self.conversion_worker.cancel()
            self.conversion_worker.wait(5000)
        self.result_folder.discard()
        event.accept()
