"""The Results tab: one page per result table, held in memory."""
import os
from typing import Dict, List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget

from ..viewlogic import CsvTable, CsvTableFile, MultikillFinder, round_kinds_by_number
from .derived_tabs import MultikillsTabController, PlayersTabController
from .results_page import APPLICATION_NAME, ResultsPage

# (key in the paths the pipeline returns, tab title, with round chips)
TABLES_SHOWN = (('kills', 'Kills', True), ('players', 'Players', False), ('rounds', 'Rounds', False), ('flagbearers', 'Flagbearers', False))
IN_MEMORY_NOTE = 'The results are held in memory only. Export saves CSV files.'


class ResultsTab(QWidget):
    statusMessage = Signal(str)
    jumpRequested = Signal(float)            # a time (s) to show in the Packets tab

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pages: List[ResultsPage] = []
        self.kills_page: Optional[ResultsPage] = None
        self.players_page: Optional[ResultsPage] = None
        self.multikills_page: Optional[ResultsPage] = None
        self.players_controller: Optional[PlayersTabController] = None
        self.multikills_controller: Optional[MultikillsTabController] = None
        self.export_folder = ''
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 0)
        self.info_label = QLabel('')
        bar.addWidget(self.info_label, 1)
        export_button = QPushButton('Export all tables…')
        export_button.clicked.connect(self.export_all)
        bar.addWidget(export_button)
        layout.addLayout(bar)
        self.page_tabs = QTabWidget()
        layout.addWidget(self.page_tabs, 1)

    def show_results(self, paths: Dict[str, str], export_folder: str) -> None:
        """Reads the CSV files the pipeline wrote and shows one page per table."""
        self.page_tabs.clear()
        self.pages = []
        self.players_controller = self.multikills_controller = None
        self.kills_page = self.players_page = self.multikills_page = None
        self.export_folder = export_folder
        converter_players: Optional[CsvTable] = None
        round_kinds = self._read_round_kinds(paths)
        for key, title, with_chips in TABLES_SHOWN:
            path = paths.get(key)
            if not path or not os.path.exists(path):
                continue
            table = CsvTableFile.read(path)
            page = self._add_page(title, table.headers, table.rows, with_chips, round_kinds)
            if key == 'kills':
                self.kills_page = page
                self._add_multikills_page(table.headers)
            if key == 'players':
                self.players_page, converter_players = page, table
        if self.kills_page and self.players_page:
            self.players_controller = PlayersTabController(self.page_tabs, self.kills_page, self.players_page, converter_players)
        self.info_label.setText(IN_MEMORY_NOTE)

    @staticmethod
    def _read_round_kinds(paths: Dict[str, str]) -> Dict[str, str]:
        path = paths.get('rounds')
        if not path or not os.path.exists(path):
            return {}
        table = CsvTableFile.read(path)
        return round_kinds_by_number(table.headers, table.rows)

    def _add_page(self, title: str, headers: List[str], rows: List[List[str]], with_chips: bool = False, round_kinds: Optional[Dict[str, str]] = None
                  ) -> ResultsPage:
        page = ResultsPage(title, headers, rows, with_chips=with_chips, round_kinds=round_kinds)
        page.export_folder = self.export_folder
        page.note.connect(self.statusMessage)
        page.jumpRequested.connect(self.jumpRequested)
        page.view.selectionModel().selectionChanged.connect(lambda *_ignored, page=page: page.update_status())
        self.page_tabs.addTab(page, '%s (%d)' % (title, len(rows)))
        self.pages.append(page)
        return page

    def _add_multikills_page(self, kill_headers: List[str]) -> None:
        """The Multikills tab goes between Kills and Players."""
        if not MultikillFinder.can_read(kill_headers):
            return
        empty = MultikillFinder(kill_headers).find([])
        self.multikills_page = self._add_page('Multikills', empty.headers, empty.rows)
        self.multikills_controller = MultikillsTabController(self.page_tabs, self.kills_page, self.multikills_page)

    def export_all(self) -> None:
        if not self.pages:
            return
        folder = QFileDialog.getExistingDirectory(self, 'Export all tables (unfiltered) to…', self.export_folder)
        if not folder:
            return
        try:
            for page in self.pages:
                CsvTableFile.write(os.path.join(folder, page.title.lower() + '.csv'), page.headers, page.rows)      # Players = the current Kills filters
        except OSError as error:
            QMessageBox.warning(self, APPLICATION_NAME, str(error))
            return
        self.statusMessage.emit('Wrote %d files to %s' % (len(self.pages), folder))
