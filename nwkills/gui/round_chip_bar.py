"""The row of round and round-kind buttons above the Kills table."""
from typing import Dict, List

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QToolButton, QWidget

from ..viewlogic import KIND_CHIPS, RoundSelection, round_menu_label, round_numbers_in


class RoundChipBar(QWidget):
    """Edits a RoundSelection and says when it changed."""
    selectionChanged = Signal()

    def __init__(self, selection: RoundSelection, headers: List[str], rows: List[List[str]], round_kinds: Dict[str, str], parent=None):
        super().__init__(parent)
        self.selection = selection
        self.kind_buttons: Dict[str, QPushButton] = {}
        self.round_actions: List[QAction] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel('Rounds (any combination):'))
        self.all_button = QPushButton('All')
        self.all_button.setCheckable(True)
        self.all_button.setChecked(True)
        self.all_button.clicked.connect(self.select_all)
        layout.addWidget(self.all_button)
        for chip in KIND_CHIPS:
            button = QPushButton(chip.label)
            button.setCheckable(True)
            button.toggled.connect(lambda on, chip_id=chip.chip_id: self.set_chip(chip_id, on))
            layout.addWidget(button)
            self.kind_buttons[chip.chip_id] = button
        round_numbers = round_numbers_in(headers, rows)
        if round_numbers:
            layout.addWidget(self._build_round_menu_button(round_numbers, round_kinds))
        layout.addStretch(1)

    def _build_round_menu_button(self, round_numbers: List[str], round_kinds: Dict[str, str]) -> QToolButton:
        button = QToolButton()
        button.setText('Round numbers…')
        button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(button)
        for round_number in round_numbers:
            action = QAction(round_menu_label(round_number, round_kinds), menu)
            action.setCheckable(True)
            action.toggled.connect(lambda on, round_number=round_number: self.set_round(round_number, on))
            menu.addAction(action)
            self.round_actions.append(action)
        button.setMenu(menu)
        return button

    def select_all(self) -> None:
        """Switches every button off: nothing selected means every row is shown."""
        for button in self.kind_buttons.values():
            button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(False)
        for action in self.round_actions:
            action.blockSignals(True)
            action.setChecked(False)
            action.blockSignals(False)
        self.selection.clear()
        self.all_button.setChecked(True)
        self.selectionChanged.emit()

    def set_chip(self, chip_id: str, selected: bool) -> None:
        self.selection.set_chip(chip_id, selected)
        self._sync_all_button()
        self.selectionChanged.emit()

    def set_round(self, round_number: str, selected: bool) -> None:
        self.selection.set_round(round_number, selected)
        self._sync_all_button()
        self.selectionChanged.emit()

    def _sync_all_button(self) -> None:
        self.all_button.blockSignals(True)
        self.all_button.setChecked(self.selection.is_empty)
        self.all_button.blockSignals(False)
