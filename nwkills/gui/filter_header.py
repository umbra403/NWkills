"""The table header with a regular expression box under every column label."""
from typing import Dict, Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase, QKeySequence
from PySide6.QtWidgets import QHeaderView, QLineEdit, QTableView

FILTER_BOX_HEIGHT = 24
FILTER_BOX_PADDING = 6
INVALID_PATTERN_STYLE = 'QLineEdit { border: 1px solid #c62828; }'


class FilterHeaderView(QHeaderView):
    """Column header with a regex box under every label."""
    filterChanged = Signal()
    filter_boxes = ()      # class-level default: Qt may call updateGeometries() while the base class is still being constructed

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.filter_boxes = []
        self.setSectionsClickable(True)
        self.setSortIndicatorShown(True)
        self.setHighlightSections(False)
        self.sectionResized.connect(self.reposition)
        self.sectionMoved.connect(self.reposition)

    def set_columns(self, column_count: int) -> None:
        for box in self.filter_boxes:
            box.deleteLater()
        self.filter_boxes = []
        for _column in range(column_count):
            box = QLineEdit(self)
            box.setPlaceholderText('regex')
            box.setClearButtonEnabled(True)
            box.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
            box.textChanged.connect(lambda _text: self.filterChanged.emit())
            self.filter_boxes.append(box)
            box.show()
        self.reposition()

    def filter_texts(self) -> Dict[int, str]:
        return {column: box.text() for column, box in enumerate(self.filter_boxes)}

    def set_filter_text_quietly(self, column: int, text: str) -> None:
        box = self.filter_boxes[column]
        box.blockSignals(True)
        box.setText(text)
        box.blockSignals(False)

    def mark_invalid(self, invalid_columns: Iterable[int]) -> None:
        invalid = set(invalid_columns)
        for column, box in enumerate(self.filter_boxes):
            box.setStyleSheet(INVALID_PATTERN_STYLE if column in invalid else '')
            box.setToolTip('Not a valid regular expression (ignored)' if column in invalid else '')

    def clear_filters(self) -> None:
        for box in self.filter_boxes:
            box.blockSignals(True)
            box.clear()
            box.blockSignals(False)
        self.filterChanged.emit()

    def sizeHint(self):
        size = super().sizeHint()
        size.setHeight(size.height() + FILTER_BOX_HEIGHT + FILTER_BOX_PADDING)
        return size

    def updateGeometries(self):
        super().updateGeometries()
        self.reposition()

    def paintSection(self, painter, rect, logicalIndex):
        rect.setHeight(rect.height() - FILTER_BOX_HEIGHT - FILTER_BOX_PADDING)
        super().paintSection(painter, rect, logicalIndex)

    def reposition(self, *_ignored):
        top = self.height() - FILTER_BOX_HEIGHT - 3
        for column, box in enumerate(self.filter_boxes):
            if self.isSectionHidden(column):
                box.hide()
                continue
            box.setGeometry(self.sectionViewportPosition(column) + 2, top, max(10, self.sectionSize(column) - 4), FILTER_BOX_HEIGHT)
            box.show()


class ResultsTableView(QTableView):
    copyRequested = Signal(bool)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copyRequested.emit(False)
            return
        super().keyPressEvent(event)
