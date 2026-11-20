"""The bottom bar: Convert, Cancel, the log switch and the two progress bars."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from ..viewlogic import ProgressReport


class ConversionFooter(QWidget):
    convertRequested = Signal()
    cancelRequested = Signal()
    logToggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        self.convert_button = QPushButton('Convert')
        self.convert_button.setEnabled(False)
        self.convert_button.setStyleSheet('font-weight: bold; padding: 6px 22px;')
        self.convert_button.clicked.connect(lambda: self.convertRequested.emit())
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(lambda: self.cancelRequested.emit())
        log_button = QPushButton('Log')
        log_button.setCheckable(True)
        log_button.toggled.connect(lambda shown: self.logToggled.emit(shown))
        layout.addWidget(self.convert_button)
        layout.addWidget(self.cancel_button)
        layout.addWidget(log_button)
        self.stage_label = QLabel('Idle')
        self.stage_bar = self._percent_bar()
        self.overall_bar = self._percent_bar()
        stage_column = QVBoxLayout()
        stage_column.addWidget(self.stage_label)
        stage_column.addWidget(self.stage_bar)
        overall_column = QVBoxLayout()
        overall_column.addWidget(QLabel('Overall'))
        overall_column.addWidget(self.overall_bar)
        layout.addLayout(stage_column, 1)
        layout.addLayout(overall_column, 1)

    @staticmethod
    def _percent_bar() -> QProgressBar:
        bar = QProgressBar()
        bar.setRange(0, 100)
        return bar

    def set_convert_enabled(self, enabled: bool) -> None:
        self.convert_button.setEnabled(enabled)

    def _set_bars(self, stage_percent: int, overall_percent: int) -> None:
        self.stage_bar.setRange(0, 100)
        self.stage_bar.setValue(stage_percent)
        self.overall_bar.setValue(overall_percent)

    def start(self) -> None:
        self.convert_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._set_bars(0, 0)
        self.stage_label.setText('Starting …')

    def show_progress(self, report: ProgressReport) -> None:
        self.stage_label.setText(report.label)
        if report.stage_fraction is None:
            self.stage_bar.setRange(0, 0)                    # a busy bar: this stage cannot say how far it is
        else:
            self.stage_bar.setRange(0, 100)
            self.stage_bar.setValue(int(report.stage_fraction * 100))
        self.overall_bar.setValue(int(report.overall_percent))

    def finish(self) -> None:
        self.convert_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._set_bars(100, 100)
        self.stage_label.setText('Finished')

    def stop(self, label: str) -> None:
        """The run ended without results ('Cancelled' or 'Failed')."""
        self._set_bars(0, 0)
        self.convert_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.stage_label.setText(label)
