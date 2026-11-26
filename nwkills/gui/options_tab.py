"""The Options tab: server, performance and export settings, and the command line they amount to."""
import os
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..viewlogic import ConversionRequest, default_export_folder

DEFAULT_SERVER_PORT = 7240
DEFAULT_PACKET_LIMIT = 200000


class OptionsTab(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        for group in (self._build_server_group(), self._build_performance_group(), self._build_export_group(), self._build_command_line_group()):
            layout.addWidget(group)
        layout.addStretch(1)
        for toggle in (self.auto_port_box, self.cache_box, self.limit_box):
            toggle.toggled.connect(lambda _value: self.changed.emit())
        for spin_box in (self.port_spin, self.jobs_spin, self.limit_spin):
            spin_box.valueChanged.connect(lambda _value: self.changed.emit())
        for line_edit in (self.own_name_edit, self.output_folder_edit):
            line_edit.textChanged.connect(lambda _value: self.changed.emit())

    # ---- building
    def _build_server_group(self) -> QGroupBox:
        group = QGroupBox('Server')
        form = QFormLayout(group)
        self.auto_port_box = QCheckBox('Detect server port automatically')
        self.auto_port_box.setChecked(True)
        form.addRow(self.auto_port_box)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(DEFAULT_SERVER_PORT)
        self.port_spin.setEnabled(False)
        form.addRow('Port (--port)', self.port_spin)
        self.auto_port_box.toggled.connect(lambda automatic: self.port_spin.setEnabled(not automatic))
        self.own_name_edit = QLineEdit()
        self.own_name_edit.setPlaceholderText('part of your own player name')
        form.addRow('My player name (--me)', self.own_name_edit)
        return group

    def _build_performance_group(self) -> QGroupBox:
        group = QGroupBox('Performance')
        form = QFormLayout(group)
        self.jobs_spin = QSpinBox()
        self.jobs_spin.setRange(1, 64)
        self.jobs_spin.setValue(max(1, os.cpu_count() or 2))
        form.addRow('Worker processes (--jobs)', self.jobs_spin)
        self.cache_box = QCheckBox('Cache decoded packets in the export folder (re-runs skip decoding)  (--cache)')
        self.cache_box.setChecked(False)
        form.addRow(self.cache_box)
        row = QHBoxLayout()
        self.limit_box = QCheckBox('Only read the first')
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(100, 100000000)
        self.limit_spin.setValue(DEFAULT_PACKET_LIMIT)
        self.limit_spin.setEnabled(False)
        row.addWidget(self.limit_box)
        row.addWidget(self.limit_spin)
        row.addWidget(QLabel('packets (--limit, for quick tests)'))
        row.addStretch(1)
        self.limit_box.toggled.connect(self.limit_spin.setEnabled)
        form.addRow(row)
        return group

    def _build_export_group(self) -> QGroupBox:
        group = QGroupBox('Export')
        form = QFormLayout(group)
        row = QHBoxLayout()
        self.output_folder_edit = QLineEdit()
        browse_button = QPushButton('Browse…')
        browse_button.clicked.connect(self.browse_output_folder)
        row.addWidget(self.output_folder_edit, 1)
        row.addWidget(browse_button)
        form.addRow('Default export folder (--out)', row)
        self.output_folder_edit.setPlaceholderText('empty = next to the capture. Converting writes no files here: CSV files appear only when you export.')
        return group

    def _build_command_line_group(self) -> QGroupBox:
        group = QGroupBox('Equivalent command line')
        layout = QVBoxLayout(group)
        self.command_line_label = QLabel()
        self.command_line_label.setWordWrap(True)
        self.command_line_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.command_line_label.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        layout.addWidget(self.command_line_label)
        return group

    # ---- values
    def server_port(self) -> Optional[int]:
        """None = detect the port automatically."""
        return None if self.auto_port_box.isChecked() else self.port_spin.value()

    def build_request(self, capture_path: Optional[str]) -> ConversionRequest:
        return ConversionRequest.from_form(capture_path, self.output_folder_edit.text(), self.server_port(), self.own_name_edit.text(), self.jobs_spin.value(),
                                           self.cache_box.isChecked(), self.limit_spin.value() if self.limit_box.isChecked() else None)

    def export_folder(self, capture_path: Optional[str]) -> str:
        return default_export_folder(self.output_folder_edit.text(), capture_path)

    def show_command_line(self, capture_path: Optional[str]) -> None:
        self.command_line_label.setText(self.build_request(capture_path).command_line())

    def browse_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, 'Default export folder', self.output_folder_edit.text() or os.path.expanduser('~'))
        if folder:
            self.output_folder_edit.setText(folder)

    # ---- remembered between runs
    def restore(self, settings) -> None:
        self.own_name_edit.setText(settings.value('me', ''))
        self.output_folder_edit.setText(settings.value('outdir', ''))
        self.jobs_spin.setValue(int(settings.value('jobs', self.jobs_spin.value())))
        self.cache_box.setChecked(settings.value('cache_on', 'false') == 'true')

    def save(self, settings) -> None:
        settings.setValue('me', self.own_name_edit.text())
        settings.setValue('outdir', self.output_folder_edit.text())
        settings.setValue('jobs', self.jobs_spin.value())
        settings.setValue('cache_on', 'true' if self.cache_box.isChecked() else 'false')
