"""The Columns drop-down of a results table."""
import time
from typing import Iterable, List, Set

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ..viewlogic import ALL_SHOWN, NONE_SHOWN, SOME_SHOWN, ColumnGrouper
from .filter_header import FilterHeaderView

REOPEN_GUARD_S = 0.25          # a click on the button that closed the popup must not reopen it
MAX_POPUP_HEIGHT = 460
MIN_POPUP_WIDTH = 260
CHECK_STATES = {NONE_SHOWN: Qt.Unchecked, SOME_SHOWN: Qt.PartiallyChecked, ALL_SHOWN: Qt.Checked}


class ColumnsPopup(QFrame):
    """Unlike a menu it stays open while columns are ticked; it closes on a click anywhere outside it, or on the Columns button again.
    Besides one box per column it has one box per group of columns (all kills columns, all columns of one round, ...); a group box is partly ticked
    when only some of its columns are shown."""

    def __init__(self, parent, headers: List[str], header_view: FilterHeaderView):
        super().__init__(parent, Qt.Popup)
        self.headers, self.header_view = headers, header_view
        self.closed_at = 0.0
        self.setFrameShape(QFrame.StyledPanel)
        self.groups = ColumnGrouper.group(headers)
        self.group_boxes: List[QCheckBox] = []
        self.column_boxes: List[QCheckBox] = []
        self.body = QWidget()
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)
        layout.addLayout(self._build_show_hide_buttons())
        if self.groups:
            self._add_group_boxes(layout)
        for column, header in enumerate(headers):
            box = QCheckBox(header)
            box.toggled.connect(lambda on, column=column: self.set_columns([column], on))
            layout.addWidget(box)
            self.column_boxes.append(box)
        layout.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(self.body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.addWidget(self.scroll)
        self.refresh()

    def _build_show_hide_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        show_all = QPushButton('Show all')
        show_all.clicked.connect(lambda: self.set_columns(range(len(self.headers)), True))
        hide_all = QPushButton('Hide all')
        hide_all.clicked.connect(lambda: self.set_columns(range(1, len(self.headers)), False))     # the first column (name / round) stays
        row.addWidget(show_all)
        row.addWidget(hide_all)
        row.addStretch(1)
        return row

    def _add_group_boxes(self, layout: QVBoxLayout) -> None:
        layout.addWidget(self._bold_label('Groups'))
        for group_index, group in enumerate(self.groups):
            box = QCheckBox(group.label)
            box.setTristate(True)
            box.clicked.connect(lambda _checked=False, group_index=group_index: self.toggle_group(group_index))
            layout.addWidget(box)
            self.group_boxes.append(box)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)
        layout.addWidget(self._bold_label('Columns'))

    @staticmethod
    def _bold_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet('font-weight: bold;')
        return label

    def hidden_columns(self) -> Set[int]:
        return {column for column in range(len(self.headers)) if self.header_view.isSectionHidden(column)}

    def refresh(self) -> None:
        hidden = self.hidden_columns()
        for column, box in enumerate(self.column_boxes):
            box.blockSignals(True)
            box.setChecked(column not in hidden)
            box.blockSignals(False)
        for box, group in zip(self.group_boxes, self.groups):
            box.blockSignals(True)
            box.setCheckState(CHECK_STATES[group.check_state(hidden)])
            box.blockSignals(False)

    def set_columns(self, columns: Iterable[int], show: bool) -> None:
        for column in columns:
            self.header_view.setSectionHidden(column, not show)
        self.header_view.reposition()
        self.refresh()

    def toggle_group(self, group_index: int) -> None:
        """A group that is fully shown gets hidden; otherwise (hidden or partly shown) all its columns get shown."""
        group = self.groups[group_index]
        self.set_columns(group.members, group.columns_to_show_after_toggle(self.hidden_columns()))

    def hideEvent(self, event):
        self.closed_at = time.monotonic()
        super().hideEvent(event)

    def toggle_under(self, button) -> None:
        if self.isVisible():
            self.hide()
        elif time.monotonic() - self.closed_at > REOPEN_GUARD_S:
            self.refresh()
            self.open_under(button)

    def open_under(self, button) -> None:
        self.body.adjustSize()
        width = max(self.body.sizeHint().width() + 30, MIN_POPUP_WIDTH)
        height = min(self.body.sizeHint().height() + 10, MAX_POPUP_HEIGHT)
        self.resize(width, height)
        self.move(button.mapToGlobal(QPoint(0, button.height())))
        self.show()
