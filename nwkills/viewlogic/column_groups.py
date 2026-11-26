"""Columns that are shown or hidden together (the Players table has one column per measure and round)."""
import re
from dataclasses import dataclass
from typing import Collection, Dict, List, Sequence

NONE_SHOWN, SOME_SHOWN, ALL_SHOWN = 0, 1, 2        # the values of Qt's check states

_PER_ROUND_COLUMN = re.compile(r'^(R[^_]*)_(.+)$')


@dataclass(frozen=True)
class ColumnGroup:
    label: str
    members: Sequence[int]                 # column indexes

    def check_state(self, hidden_columns: Collection[int]) -> int:
        shown = sum(1 for column in self.members if column not in hidden_columns)
        if shown == 0:
            return NONE_SHOWN
        return ALL_SHOWN if shown == len(self.members) else SOME_SHOWN

    def columns_to_show_after_toggle(self, hidden_columns: Collection[int]) -> bool:
        """What a click on the group's box does: a fully shown group gets hidden, anything else gets shown (True = show)."""
        return self.check_state(hidden_columns) != ALL_SHOWN


class ColumnGrouper:
    """Finds the groups of a table's columns: one per measure ('kills', 'R3(live)_kills' ...), one per round, all per-round columns and all totals.
    The first column (the player name) is in no group, and a group of a single column is not a group."""

    @classmethod
    def group(cls, headers: List[str]) -> List[ColumnGroup]:
        by_measure: Dict[str, List[int]] = {}
        by_round: Dict[str, List[int]] = {}
        totals: List[int] = []
        per_round: List[int] = []
        for column, header in enumerate(headers):
            if column == 0:
                continue
            match = _PER_ROUND_COLUMN.match(header)
            if match:
                by_round.setdefault(match.group(1), []).append(column)
                per_round.append(column)
                by_measure.setdefault(match.group(2), []).append(column)
            else:
                totals.append(column)
                measure = 'score_at_capture' if header.startswith('score_at_capture') else header
                by_measure.setdefault(measure, []).append(column)
        if not per_round:
            return []
        groups = [ColumnGroup('All %s columns' % measure, members) for measure, members in by_measure.items()]
        groups += [ColumnGroup('Round %s' % round_label, members) for round_label, members in by_round.items()]
        groups += [ColumnGroup('All per-round columns', per_round), ColumnGroup('All total columns', totals)]
        return [group for group in groups if len(group.members) >= 2]
