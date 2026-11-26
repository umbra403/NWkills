"""One results table with its filters, chips, column chooser, copy and export buttons."""
import os
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QToolButton, QVBoxLayout,
                               QWidget)

from ..viewlogic import (ColumnFilters, ColumnMemory, CsvTableFile, ResultsScope, RoundSelection, SelectedCellGrid, TabSeparatedFormatter)
from .columns_popup import ColumnsPopup
from .filter_header import FilterHeaderView, ResultsTableView
from .round_chip_bar import RoundChipBar
from .table_models import ResultsFilterProxy, ResultsTableModel

APPLICATION_NAME = 'nwkills'
MIN_COLUMN_WIDTH = 90
MAX_COLUMN_WIDTH = 380
ROW_HEIGHT = 22
NOTHING_SELECTED_HINT = 'Nothing selected: click cells, drag, or click a row number (Shift/Ctrl for several).'


class ResultsPage(QWidget):
    jumpRequested = Signal(float)
    note = Signal(str)
    scopeChanged = Signal()      # the rows this table shows changed (filters, chips)

    def __init__(self, title: str, headers: List[str], rows: List[List[str]], with_chips: bool = False, round_kinds: Optional[Dict[str, str]] = None,
                 parent=None):
        super().__init__(parent)
        self.title, self.headers, self.rows = title, headers, rows
        self.selection = RoundSelection()
        self.scope_description = ''
        self.export_folder = ''
        self.model = ResultsTableModel(headers, rows, self)
        self.proxy = ResultsFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.view = ResultsTableView(self)
        self.header_view = FilterHeaderView(self.view)
        self.view.setHorizontalHeader(self.header_view)
        self.view.setModel(self.proxy)
        self.header_view.setSortIndicator(-1, Qt.AscendingOrder)      # start in file order; a click on a label sorts
        self.view.setSortingEnabled(True)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.view.setAlternatingRowColors(True)
        self.view.setWordWrap(False)
        self.view.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.header_view.setSectionResizeMode(QHeaderView.Interactive)
        self._fit_column_widths()
        self.header_view.set_columns(len(headers))
        self.header_view.filterChanged.connect(self.apply_filters)
        self.view.horizontalScrollBar().valueChanged.connect(self.header_view.reposition)
        self.view.copyRequested.connect(self.copy_selection)

        self.toolbar_layout = self._build_toolbar()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 0)
        layout.addLayout(self.toolbar_layout)
        self.chip_bar: Optional[RoundChipBar] = None
        if with_chips:
            self.chip_bar = RoundChipBar(self.selection, headers, rows, round_kinds or {}, self)
            self.chip_bar.selectionChanged.connect(self.apply_filters)
            layout.addWidget(self.chip_bar)
        layout.addWidget(self.view, 1)
        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        self.apply_filters()

    def _build_toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        self.ignore_case_box = QCheckBox('Ignore case')
        self.ignore_case_box.setChecked(True)
        self.ignore_case_box.toggled.connect(self.apply_filters)
        clear_button = QPushButton('Clear filters')
        clear_button.clicked.connect(self.header_view.clear_filters)
        self.columns_button = QToolButton()
        self.columns_button.setText('Columns ▾')
        self.columns_button.clicked.connect(self.toggle_columns_popup)
        self.columns_popup: Optional[ColumnsPopup] = None
        self.rebuild_columns_popup()
        copy_button = QPushButton('Copy selection')
        copy_button.clicked.connect(lambda: self.copy_selection(False))
        copy_with_headers_button = QPushButton('Copy with headers')
        copy_with_headers_button.clicked.connect(lambda: self.copy_selection(True))
        for widget in (self.ignore_case_box, clear_button, self.columns_button):
            toolbar.addWidget(widget)
        toolbar.addStretch(1)
        toolbar.addWidget(copy_button)
        toolbar.addWidget(copy_with_headers_button)
        if 'time_s' in self.headers:
            jump_button = QPushButton('Show in Packets')
            jump_button.clicked.connect(self.request_jump)
            toolbar.addWidget(jump_button)
        export_button = QPushButton('Export shown rows as CSV…')
        export_button.clicked.connect(self.export_shown_rows)
        toolbar.addWidget(export_button)
        return toolbar

    def _fit_column_widths(self) -> None:
        self.view.resizeColumnsToContents()
        for column in range(len(self.headers)):
            self.header_view.resizeSection(column, min(max(self.header_view.sectionSize(column), MIN_COLUMN_WIDTH), MAX_COLUMN_WIDTH))

    # ---- columns drop-down
    def rebuild_columns_popup(self) -> None:
        """(Re)build the Columns drop-down for the current headers."""
        if self.columns_popup is not None:
            self.columns_popup.hide()
            self.columns_popup.deleteLater()
        self.columns_popup = ColumnsPopup(self, self.headers, self.header_view)

    def toggle_columns_popup(self) -> None:
        self.columns_popup.toggle_under(self.columns_button)

    # ---- contents
    def replace_data(self, headers: List[str], rows: List[List[str]], sort_name: Optional[str] = None, sort_order=Qt.DescendingOrder) -> None:
        """Swap in new contents (the Players table is recomputed from the Kills tab). Filter texts, hidden columns and the sort order are kept by column NAME."""
        old_headers = self.headers
        hidden = {column for column in range(len(old_headers)) if self.header_view.isSectionHidden(column)}
        memory = ColumnMemory(old_headers, self.header_view.filter_texts(), hidden, self.header_view.sortIndicatorSection(), self.header_view.sortIndicatorOrder())
        self.header_view.setSortIndicator(-1, Qt.AscendingOrder)
        self.headers, self.rows = headers, rows
        self.model = ResultsTableModel(headers, rows, self)
        self.proxy.setSourceModel(self.model)
        for column in range(len(headers)):
            self.header_view.setSectionHidden(column, False)
        self.header_view.set_columns(len(headers))
        for column, header in enumerate(headers):
            self.header_view.set_filter_text_quietly(column, memory.filter_text(header))
            if memory.is_hidden(header):
                self.header_view.setSectionHidden(column, True)
        self._fit_column_widths()
        self.rebuild_columns_popup()
        self.apply_filters()
        sort = memory.sort_for(headers, sort_name, sort_order)
        if sort:
            self.header_view.setSortIndicator(*sort)
        self.header_view.reposition()

    def scope(self) -> ResultsScope:
        """The rows shown right now, plus whether any filter is active and whether the user chose rounds/kinds (chips or a filter on round_kind)."""
        rows = [self.rows[self.proxy.mapToSource(self.proxy.index(row, 0)).row()] for row in range(self.proxy.rowCount())]
        texts = self.header_view.filter_texts()
        kind_filtered = 'round_kind' in self.headers and bool(texts.get(self.headers.index('round_kind'), ''))
        return ResultsScope(rows, not self.selection.is_empty or any(texts.values()), not self.selection.is_empty or kind_filtered)

    # ---- filtering
    def apply_filters(self, *_ignored) -> None:
        column_filters = ColumnFilters.compile(self.header_view.filter_texts(), self.ignore_case_box.isChecked())
        self.header_view.mark_invalid(column_filters.invalid_columns)
        self.proxy.set_filters(column_filters, self.selection.row_predicate(self.headers))
        self.update_status()
        self.scopeChanged.emit()

    def update_status(self) -> None:
        selection_model = self.view.selectionModel()
        selected = len({index.row() for index in selection_model.selectedIndexes()}) if selection_model else 0
        self.status_label.setText('Showing %d of %d rows%s%s' % (self.proxy.rowCount(), len(self.rows), ' · %d selected' % selected if selected else '',
                                                                 ' · ' + self.scope_description if self.scope_description else ''))

    # ---- copy / export / jump
    def selection_grid(self):
        """-> (headers, grid) of the selected cells in the order the columns are shown."""
        header_view = self.view.horizontalHeader()
        cells = {}
        for index in self.view.selectionModel().selectedIndexes():
            if header_view.isSectionHidden(index.column()):
                continue
            cells[(index.row(), header_view.visualIndex(index.column()))] = index.data()
        return SelectedCellGrid.build(cells, lambda visual: self.headers[header_view.logicalIndex(visual)])

    def copy_selection(self, with_header: bool = False) -> None:
        headers, grid = self.selection_grid()
        if not grid:
            self.note.emit(NOTHING_SELECTED_HINT)
            return
        QGuiApplication.clipboard().setText(TabSeparatedFormatter.format(headers, grid, with_header))
        self.note.emit('Copied %d rows × %d columns as tab-separated text (paste into Excel, Sheets or a CSV editor).' % (len(grid), len(headers)))

    def shown_table(self):
        """-> (headers, rows) of what is on screen: visible columns in their shown order, filtered and sorted rows."""
        header_view = self.view.horizontalHeader()
        visible = [header_view.logicalIndex(visual) for visual in range(header_view.count()) if not header_view.isSectionHidden(header_view.logicalIndex(visual))]
        rows = [[self.proxy.index(row, column).data() for column in visible] for row in range(self.proxy.rowCount())]
        return [self.headers[column] for column in visible], rows

    def export_shown_rows(self) -> None:
        suggested = self.title.lower().replace(' ', '') + '.csv'
        if self.export_folder:
            suggested = os.path.join(self.export_folder, suggested)
        path, _filter = QFileDialog.getSaveFileName(self, 'Export shown rows', suggested, 'CSV files (*.csv)')
        if not path:
            return
        headers, rows = self.shown_table()
        try:
            CsvTableFile.write(path, headers, rows)
        except OSError as error:
            QMessageBox.warning(self, APPLICATION_NAME, 'Could not write %s:\n%s' % (path, error))
            return
        self.note.emit('Exported %d rows to %s' % (len(rows), path))

    def request_jump(self) -> None:
        index = self.view.currentIndex()
        if not index.isValid():
            self.note.emit('Select a row first.')
            return
        try:
            self.jumpRequested.emit(float(self.proxy.index(index.row(), self.headers.index('time_s')).data()))
        except ValueError:
            pass
