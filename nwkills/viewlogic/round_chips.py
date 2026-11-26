"""The round and round-kind buttons above the Kills table."""
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional, Set

from .row_filters import RowPredicate


@dataclass(frozen=True)
class KindChip:
    chip_id: str
    label: str
    round_kinds: FrozenSet[str]              # the values of the round_kind column this button lets through


KIND_CHIPS = (
    KindChip('live', 'Live', frozenset({'live'})),
    KindChip('pre', 'Pre-live', frozenset({'pre-live'})),
    KindChip('prelive', 'Pre-live + live', frozenset({'pre-live', 'live'})),
    KindChip('warm', 'Warm-up', frozenset({'warm-up'})),
)


class RoundSelection:
    """Which kind buttons and round numbers are switched on. A row passes when it matches ANY selected button; nothing selected = every row."""

    def __init__(self, chips: Iterable[KindChip] = KIND_CHIPS):
        self._chips = {chip.chip_id: chip for chip in chips}
        self.chip_ids: Set[str] = set()
        self.round_numbers: Set[str] = set()

    def set_chip(self, chip_id: str, selected: bool) -> None:
        (self.chip_ids.add if selected else self.chip_ids.discard)(chip_id)

    def set_round(self, round_number: str, selected: bool) -> None:
        (self.round_numbers.add if selected else self.round_numbers.discard)(round_number)

    def clear(self) -> None:
        self.chip_ids.clear()
        self.round_numbers.clear()

    @property
    def is_empty(self) -> bool:
        return not self.chip_ids and not self.round_numbers

    def allowed_kinds(self) -> Set[str]:
        allowed: Set[str] = set()
        for chip_id in self.chip_ids:
            allowed |= self._chips[chip_id].round_kinds
        return allowed

    def row_predicate(self, headers: List[str]) -> Optional[RowPredicate]:
        """None when every row passes (nothing selected, or the table has no round / round_kind column)."""
        if self.is_empty:
            return None
        try:
            round_column, kind_column = headers.index('round'), headers.index('round_kind')
        except ValueError:
            return None
        allowed_kinds, round_numbers = self.allowed_kinds(), set(self.round_numbers)
        return lambda row: row[kind_column] in allowed_kinds or row[round_column] in round_numbers


def round_numbers_in(headers: List[str], rows: Iterable[List[str]]) -> List[str]:
    """The distinct round numbers of a table, in numeric order of their text length then text."""
    if 'round' not in headers:
        return []
    column = headers.index('round')
    return sorted({row[column] for row in rows}, key=lambda text: (len(text), text))


def round_menu_label(round_number: str, round_kinds: Dict[str, str]) -> str:
    kind = round_kinds.get(round_number, '')
    return 'Round %s%s' % (round_number, ' (%s)' % kind if kind else '')


def round_kinds_by_number(headers: List[str], rows: Iterable[List[str]]) -> Dict[str, str]:
    """From the rounds table: round number -> its kind. Empty when the table lacks the columns."""
    if 'round' not in headers or 'kind' not in headers:
        return {}
    number_column, kind_column = headers.index('round'), headers.index('kind')
    return {row[number_column]: row[kind_column] for row in rows}
