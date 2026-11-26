"""Volleys: several kills by one player within a short time."""
import collections
from typing import Dict, List, Sequence, Tuple

from .csv_tables import CsvTable

REQUIRED_KILL_COLUMNS = ('round', 'round_kind', 'time_s', 'mm:ss', 'killer', 'victim', 'weapon', 'teamkill', 'death_type', 'review')
OUTPUT_HEADERS = ['killer', 'kills', 'enemy_kills', 'teamkills', 'weapon', 'round', 'round_kind', 'time_s', 'mm:ss', 'span_s', 'victims', 'review']
NOT_A_PLAYER = ('?', '(AI)', '(world)', '(runaway horse)')
WINDOW_TOLERANCE_S = 1e-9


class MultikillFinder:
    """One multikill = the first kill of a killer in a round plus every later kill by the same killer within `window_s` seconds of that first one;
    the next kill after it starts the next one. Only groups of 2 or more are listed. Counted: ordinary kills with any weapon; AI/horse deaths, admin
    and no-blow deaths are not."""

    def __init__(self, kill_headers: Sequence[str]):
        self._column = {header: index for index, header in enumerate(kill_headers)}

    @staticmethod
    def can_read(kill_headers: Sequence[str]) -> bool:
        return set(REQUIRED_KILL_COLUMNS) <= set(kill_headers)

    def find(self, kill_rows: Sequence[Sequence[str]], window_s: float = 1.0, include_teamkills: bool = True, best_only: bool = False,
             exclude_warm_up: bool = True) -> CsvTable:
        """include_teamkills=False leaves teamkill rows out before grouping. best_only keeps each killer's biggest volley (most kills, then most enemy
        kills, then the earliest). exclude_warm_up leaves warm-up rounds out, as the Players tab does. Biggest volleys first."""
        volleys = []
        for (killer, _round_number), rows in self._rows_by_killer_and_round(kill_rows, include_teamkills, exclude_warm_up).items():
            rows.sort(key=lambda row: self._time(row))
            volleys += [self._volley_row(killer, volley) for volley in self._split_into_volleys(rows, window_s)]
        volleys.sort(key=lambda row: (-int(row[1]), -int(row[2]), float(row[7])))
        if best_only:
            volleys = self._biggest_per_killer(volleys)
        return CsvTable(list(OUTPUT_HEADERS), volleys)

    def _time(self, row) -> float:
        return float(row[self._column['time_s']])

    def _rows_by_killer_and_round(self, kill_rows, include_teamkills, exclude_warm_up) -> Dict[Tuple[str, str], list]:
        column = self._column
        groups = collections.defaultdict(list)
        for row in kill_rows:
            if exclude_warm_up and row[column['round_kind']] == 'warm-up':
                continue
            if row[column['death_type']] != 'kill' or row[column['killer']] in NOT_A_PLAYER:
                continue
            if not include_teamkills and row[column['teamkill']] != '':
                continue
            try:
                self._time(row)
            except ValueError:
                continue
            groups[(row[column['killer']], row[column['round']])].append(row)
        return groups

    def _split_into_volleys(self, sorted_rows: list, window_s: float) -> List[list]:
        volleys, start = [], 0
        while start < len(sorted_rows):
            first_time = self._time(sorted_rows[start])
            end = start
            while end + 1 < len(sorted_rows) and self._time(sorted_rows[end + 1]) - first_time <= window_s + WINDOW_TOLERANCE_S:
                end += 1
            if end > start:
                volleys.append(sorted_rows[start:end + 1])
            start = end + 1
        return volleys

    def _volley_row(self, killer: str, volley: list) -> List[str]:
        column = self._column
        teamkill_count = sum(1 for row in volley if row[column['teamkill']] != '')
        review_flags = sorted({flag for row in volley for flag in row[column['review']].split() if flag})
        weapons = '/'.join(sorted({row[column['weapon']].split(': ', 1)[-1] for row in volley}))
        first = volley[0]
        return [killer, str(len(volley)), str(len(volley) - teamkill_count), str(teamkill_count), weapons, first[column['round']], first[column['round_kind']],
                first[column['time_s']], first[column['mm:ss']], '%.2f' % (self._time(volley[-1]) - self._time(first)),
                '; '.join(row[column['victim']] for row in volley), ' '.join(review_flags)]

    @staticmethod
    def _biggest_per_killer(sorted_volleys: List[List[str]]) -> List[List[str]]:
        seen, kept = set(), []
        for volley in sorted_volleys:
            if volley[0] not in seen:
                seen.add(volley[0])
                kept.append(volley)
        return kept
