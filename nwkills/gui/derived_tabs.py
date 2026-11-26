"""The Players and Multikills tabs: tables computed from the rows the Kills tab shows right now."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QLabel, QTabWidget

from ..viewlogic import CsvTable, MultikillFinder, PlayerTotalsCalculator, scope_note
from .results_page import ResultsPage

REFRESH_DELAY_MS = 200
FIRST_ADDED_TOOLBAR_POSITION = 3             # after 'Ignore case', 'Clear filters' and 'Columns'


def _delayed_refresh_timer(parent, refresh) -> QTimer:
    """Typing in a filter changes the Kills tab at every key: the derived table is recomputed once typing pauses."""
    timer = QTimer(parent)
    timer.setSingleShot(True)
    timer.setInterval(REFRESH_DELAY_MS)
    timer.timeout.connect(refresh)
    return timer


class PlayersTabController:
    """Keeps the Players table equal to the totals of the kill rows the Kills tab shows."""

    def __init__(self, tabs: QTabWidget, kills_page: ResultsPage, players_page: ResultsPage, converter_players: CsvTable):
        self.tabs, self.kills_page, self.players_page = tabs, kills_page, players_page
        self.calculator = PlayerTotalsCalculator(kills_page.headers, converter_players.headers, converter_players.rows)
        self.net_kills_box = QCheckBox('Teamkills count negatively')
        self.net_kills_box.setChecked(True)
        self.net_kills_box.setToolTip('On: kills = kills − teamkills, also per round (like the in-game scoreboard). Off: kills are kills only.')
        players_page.toolbar_layout.insertWidget(FIRST_ADDED_TOOLBAR_POSITION, self.net_kills_box)
        self.timer = _delayed_refresh_timer(players_page, self.refresh)
        kills_page.scopeChanged.connect(self.timer.start)
        self.net_kills_box.toggled.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        scope = self.kills_page.scope()
        table = self.calculator.compute(scope.rows, net_kills=self.net_kills_box.isChecked(), exclude_warm_up=not scope.rounds_chosen,
                                        include_all_players=not scope.any_filter_active)
        self.players_page.scope_description = scope_note('totals', len(scope.rows), len(self.kills_page.rows), scope.rounds_chosen)
        self.players_page.replace_data(table.headers, table.rows, sort_name='kills')
        self.tabs.setTabText(self.tabs.indexOf(self.players_page), 'Players (%d)' % len(table.rows))


class MultikillsTabController:
    """Keeps the Multikills table equal to the volleys of the kill rows the Kills tab shows."""

    def __init__(self, tabs: QTabWidget, kills_page: ResultsPage, multikills_page: ResultsPage):
        self.tabs, self.kills_page, self.page = tabs, kills_page, multikills_page
        self.finder = MultikillFinder(kills_page.headers)
        self.window_spin = QDoubleSpinBox()
        self.window_spin.setRange(0.1, 60.0)
        self.window_spin.setDecimals(1)
        self.window_spin.setSingleStep(0.5)
        self.window_spin.setValue(1.0)
        self.window_spin.setSuffix(' s')
        self.window_spin.setToolTip('Kills by one player within this time of the first kill of a multikill belong to it.')
        self.teamkills_box = QCheckBox('Include teamkills')
        self.teamkills_box.setChecked(True)
        self.teamkills_box.setToolTip('On: teamkills count towards a multikill (the teamkills column says how many). '
                                      'Off: they are left out before the kills are grouped.')
        self.best_only_box = QCheckBox('Only each player\'s biggest')
        self.best_only_box.setChecked(False)
        self.best_only_box.setToolTip('Off: every multikill of 2 or more. On: one row per player, the biggest.')
        for position, widget in enumerate((QLabel('Time window:'), self.window_spin, self.teamkills_box, self.best_only_box)):
            multikills_page.toolbar_layout.insertWidget(FIRST_ADDED_TOOLBAR_POSITION + position, widget)
        self.timer = _delayed_refresh_timer(multikills_page, self.refresh)
        kills_page.scopeChanged.connect(self.timer.start)
        self.window_spin.valueChanged.connect(self.timer.start)
        self.teamkills_box.toggled.connect(self.refresh)
        self.best_only_box.toggled.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        scope = self.kills_page.scope()
        table = self.finder.find(scope.rows, window_s=self.window_spin.value(), include_teamkills=self.teamkills_box.isChecked(),
                                 best_only=self.best_only_box.isChecked(), exclude_warm_up=not scope.rounds_chosen)
        self.page.scope_description = scope_note('multikills', len(scope.rows), len(self.kills_page.rows), scope.rounds_chosen)
        self.page.replace_data(table.headers, table.rows, sort_name='kills')
        self.tabs.setTabText(self.tabs.indexOf(self.page), 'Multikills (%d)' % len(table.rows))
