"""The Packets tab: the packets of the server flow, a display filter, and the decoded messages of the selected packet."""
import re
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSplitter, QTableView, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ..viewlogic import HexDump, PacketSummarizer, packet_index_at_time
from .background_workers import PacketIndexWorker
from .table_models import PacketFilterProxy, PacketTableModel

FILTER_DELAY_MS = 250
COLUMN_WIDTHS = (70, 110, 70, 80, 60)
MAX_FIELDS_SHOWN = 40
EXPAND_MESSAGES_UP_TO = 6
HEADER_BYTES_SHOWN = 12
QUEUED_EXPLANATION = 'yes (byte 7 = 0, the game replays it without the count byte)'


class PacketsTab(QWidget):
    statusMessage = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.index_worker: Optional[PacketIndexWorker] = None
        layout = QVBoxLayout(self)
        layout.addLayout(self._build_filter_bar())
        self.model = PacketTableModel(self)
        self.proxy = PacketFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = self._build_table()
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self._build_detail_panes())
        splitter.setSizes([480, 240])
        layout.addWidget(splitter, 1)
        self.filter_timer = QTimer(self)
        self.filter_timer.setSingleShot(True)
        self.filter_timer.setInterval(FILTER_DELAY_MS)
        self.filter_timer.timeout.connect(self.apply_filter)
        self.filter_box.textChanged.connect(lambda _text: self.filter_timer.start())

    # ---- building
    def _build_filter_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(QLabel('Display filter (regex):'))
        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText('e.g.  queued|^13  — matches number, length, flags and message types')
        self.filter_box.setClearButtonEnabled(True)
        bar.addWidget(self.filter_box, 1)
        self.index_button = QPushButton('Index message types')
        self.index_button.setToolTip('Decode every packet in the background so the filter can search the message types too')
        self.index_button.clicked.connect(self.start_indexing)
        self.index_button.setEnabled(False)
        bar.addWidget(self.index_button)
        self.count_label = QLabel('')
        bar.addWidget(self.count_label)
        return bar

    def _build_table(self) -> QTableView:
        table = QTableView()
        table.setModel(self.proxy)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(20)
        table.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        table.horizontalHeader().setStretchLastSection(True)
        for column, width in enumerate(COLUMN_WIDTHS):
            table.setColumnWidth(column, width)
        table.selectionModel().currentRowChanged.connect(self.show_packet)
        return table

    def _build_detail_panes(self) -> QSplitter:
        fixed_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        panes = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFont(fixed_font)
        self.hex_view = QPlainTextEdit()
        self.hex_view.setReadOnly(True)
        self.hex_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.hex_view.setFont(fixed_font)
        panes.addWidget(self.tree)
        panes.addWidget(self.hex_view)
        return panes

    # ---- contents
    def clear(self) -> None:
        self.stop_indexing()
        self.index_button.setEnabled(False)
        self.model.set_items([])

    def show_packets(self, items: List[Tuple[float, bytes]], summarizer: PacketSummarizer) -> None:
        self.model.set_items(items, summarizer)
        self.index_button.setEnabled(True)
        self.count_label.setText('%s packets' % format(len(items), ','))

    # ---- filter and indexing
    def apply_filter(self) -> None:
        text = self.filter_box.text()
        try:
            self.proxy.set_pattern(re.compile(text, re.IGNORECASE) if text else None)
            self.filter_box.setStyleSheet('')
        except re.error:
            self.filter_box.setStyleSheet('border: 1px solid #c62828;')
            return
        self.count_label.setText('Showing %s of %s packets · message types indexed for %s' % (
            format(self.proxy.rowCount(), ','), format(len(self.model.items), ','), format(self.model.summaries.cached_count, ',')))

    def start_indexing(self) -> None:
        if self.index_worker and self.index_worker.isRunning():
            return
        self.index_worker = PacketIndexWorker(self.model.summaries, self)
        self.index_worker.progress.connect(self._on_index_progress)
        self.index_worker.finished.connect(self.apply_filter)
        self.index_button.setEnabled(False)
        self.index_worker.start()

    def stop_indexing(self) -> None:
        if self.index_worker and self.index_worker.isRunning():
            self.index_worker.stop_requested = True
            self.index_worker.wait(3000)

    def _on_index_progress(self, done: int, total: int) -> None:
        self.statusMessage.emit('Indexing message types … %d / %d' % (done, total))
        if done >= total:
            self.statusMessage.emit('Message types indexed.')
            self.index_button.setEnabled(True)

    # ---- one packet
    def show_packet(self, current, _previous=None) -> None:
        self.tree.clear()
        self.hex_view.clear()
        if not current.isValid():
            return
        row = self.proxy.mapToSource(current).row()
        time_s, payload = self.model.items[row]
        summary = self.model.summaries.summary(row)
        root = QTreeWidgetItem(['Packet %d: %d bytes, t = %.6f s' % (row + 1, len(payload), time_s)])
        root.addChild(QTreeWidgetItem(['Header: %s' % payload[:HEADER_BYTES_SHOWN].hex(' ')]))
        root.addChild(QTreeWidgetItem(['Queued packet: %s' % (QUEUED_EXPLANATION if summary.queued else 'no')]))
        messages_item = QTreeWidgetItem(['Messages: %d' % summary.message_count])
        root.addChild(messages_item)
        for number, message in enumerate(summary.messages, start=1):
            message_item = QTreeWidgetItem(['#%d  type %d  (%d fields)' % (number, message.message_type, len(message.fields))])
            messages_item.addChild(message_item)
            for field_number, field in enumerate(message.fields[:MAX_FIELDS_SHOWN]):
                message_item.addChild(QTreeWidgetItem(['field %d: %s   [%d bits]' % (field_number, field.value, field.bit_width)]))
        self.tree.addTopLevelItem(root)
        root.setExpanded(True)
        messages_item.setExpanded(summary.message_count <= EXPAND_MESSAGES_UP_TO)
        self.hex_view.setPlainText(HexDump.format(payload))

    def show_packet_at_time(self, time_s: float) -> bool:
        """Select the packet at a time (from 'Show in Packets'). False when no packet list is loaded."""
        if not self.model.times:
            self.statusMessage.emit('No packet list loaded.')
            return False
        index = self.proxy.mapFromSource(self.model.index(packet_index_at_time(self.model.times, time_s), 0))
        if not index.isValid():
            self.statusMessage.emit('That packet is hidden by the display filter.')
            return True
        self.table.selectRow(index.row())
        self.table.scrollTo(index, QAbstractItemView.PositionAtCenter)
        self.show_packet(index)
        return True
