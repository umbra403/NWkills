"""Qt models: the result tables and the packet list, each with the proxy that sorts and filters it."""
from typing import List, Optional, Tuple

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor

from ..viewlogic import (ColumnFilters, PacketRowFormatter, PacketSummarizer, PacketSummaryCache, cell_sort_key, is_queued_payload, numeric_column_indexes)
from ..viewlogic.row_filters import RowPredicate

REVIEW_FLAG_COLOR = QColor(255, 170, 0, 70)
QUEUED_FLAG_COLOR = QColor(255, 220, 90, 90)
RIGHT_ALIGNED_PACKET_COLUMNS = (0, 1, 2, 4)
FLAGS_COLUMN = 3


class ResultsTableModel(QAbstractTableModel):
    """A read-only table of strings (one result CSV)."""

    def __init__(self, headers: List[str], rows: List[List[str]], parent=None):
        super().__init__(parent)
        self.headers, self.rows = headers, rows
        self.sort_keys = [[cell_sort_key(value) for value in row] for row in rows]
        self.numeric_columns = numeric_column_indexes(len(headers), rows)
        self.review_column = headers.index('review') if 'review' in headers else -1

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, column = index.row(), index.column()
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            return self.rows[row][column]
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignRight | Qt.AlignVCenter) if column in self.numeric_columns else int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.BackgroundRole and column == self.review_column and self.rows[row][column]:
            return REVIEW_FLAG_COLOR                      # a review flag stands out
        return None


class ResultsFilterProxy(QSortFilterProxyModel):
    """Sorts by cell_sort_key and filters by one regex per column plus the round/kind chips."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.column_filters = ColumnFilters({})
        self.row_predicate: Optional[RowPredicate] = None

    def set_filters(self, column_filters: ColumnFilters, row_predicate: Optional[RowPredicate]) -> None:
        self.column_filters, self.row_predicate = column_filters, row_predicate
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        if model is None:
            return True
        values = model.rows[source_row]
        if self.row_predicate and not self.row_predicate(values):
            return False
        return self.column_filters.accepts(values)

    def lessThan(self, left, right):
        model = self.sourceModel()
        return model.sort_keys[left.row()][left.column()] < model.sort_keys[right.row()][right.column()]


class PacketTableModel(QAbstractTableModel):
    """The packets of the server flow. Message types are decoded when a row is first shown (or by the background indexer)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: List[Tuple[float, bytes]] = []
        self.times: List[float] = []
        self.summaries = PacketSummaryCache([])

    def set_items(self, items: List[Tuple[float, bytes]], summarizer: Optional[PacketSummarizer] = None) -> None:
        self.beginResetModel()
        self.items, self.times = items, [time_s for time_s, _payload in items]
        self.summaries = PacketSummaryCache(items, summarizer)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(PacketRowFormatter.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return PacketRowFormatter.HEADERS[section]
        return None

    def search_text(self, row: int) -> str:
        """The text the display filter searches."""
        return PacketRowFormatter.search_text(row, self.items[row][1], self.summaries.peek(row))

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, column = index.row(), index.column()
        time_s, payload = self.items[row]
        if role == Qt.DisplayRole:
            summary = self.summaries.summary(row) if column > FLAGS_COLUMN else None
            return PacketRowFormatter.cell_text(column, row, time_s, payload, summary)
        if role == Qt.TextAlignmentRole and column in RIGHT_ALIGNED_PACKET_COLUMNS:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.BackgroundRole and column == FLAGS_COLUMN and is_queued_payload(payload):
            return QUEUED_FLAG_COLOR
        return None


class PacketFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pattern = None

    def set_pattern(self, pattern) -> None:
        self.pattern = pattern
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        return self.pattern is None or bool(self.pattern.search(self.sourceModel().search_text(source_row)))
