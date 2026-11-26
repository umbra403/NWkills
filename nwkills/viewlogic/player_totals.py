"""The Players table, computed from the kill rows the Kills tab shows."""
import collections
from typing import Dict, List, Optional, Sequence, Tuple

from .csv_tables import CsvTable

NOT_COUNTED_PREFIXES = ('admin', 'horse death', 'no-blow death')
AI_DEATH = 'AI/horse death'
NO_PLAYER_NAMES = ('?', '(AI)', '(world)')
SCOREBOARD_COLUMNS = ('score_at_capture_start', 'score_at_capture_end')
ROUND_MEASURES = ('kills', 'deaths', 'teamkills', 'score_gap')


def parse_int(text) -> Optional[int]:
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def round_label(round_number: str, round_kind: str) -> str:
    """'R3(live)'."""
    return 'R%s' % round_number + ('(%s)' % round_kind if round_kind else '')


class _Counts:
    """Counts per player: in total and per round."""

    def __init__(self):
        self._by_player: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

    def add(self, player: str, round_number: str, measure: str) -> None:
        self._by_player[player][measure] += 1
        self._by_player[player][(round_number, measure)] += 1

    def get(self, player: str, measure: str, round_number: Optional[str] = None) -> int:
        key = measure if round_number is None else (round_number, measure)
        return self._by_player[player][key]

    @property
    def players(self) -> set:
        return set(self._by_player)


class PlayerTotalsCalculator:
    """Counting rules are the ones the converter uses for its own players file: admin slays, mount deaths and no-blow deaths are not counted;
    AI deaths only credit the killer's ai_kills; a teamkill is not a kill. The columns that need the scoreboard (score at capture start and end,
    score_gap) come from the converter's players file, for the rounds that are included."""

    def __init__(self, kill_headers: Sequence[str], player_headers: Sequence[str], player_rows: Sequence[Sequence[str]]):
        self._kill_column = {header: index for index, header in enumerate(kill_headers)}
        self._player_column = {header: index for index, header in enumerate(player_headers)}
        self._converter_rows = {row[0]: row for row in player_rows}

    def compute(self, kill_rows: Sequence[Sequence[str]], net_kills: bool = True, exclude_warm_up: bool = True, include_all_players: bool = False) -> CsvTable:
        """net_kills: kills = kills - teamkills (as the scoreboard does), also per round. exclude_warm_up: leave warm-up rounds out (what the converter does
        for its totals). include_all_players: also list the players of the converter's file that have no kill row."""
        counts, kinds = self._count(kill_rows, exclude_warm_up)
        round_numbers = sorted(kinds, key=lambda text: (parse_int(text) is None, parse_int(text) or 0, text))
        players = counts.players | (set(self._converter_rows) if include_all_players else set())
        round_columns = [(number, measure) for number in round_numbers for measure in ROUND_MEASURES]
        headers = ['player', 'kills', 'deaths', 'teamkills', 'ai_kills', 'score_at_capture_start', 'score_at_capture_end', 'score_gap']
        headers += ['%s_%s' % (round_label(number, kinds[number]), measure) for number, measure in round_columns]
        rows = [self._player_row(player, counts, kinds, round_columns, net_kills) for player in players]
        rows.sort(key=lambda row: (-int(row[1]), row[0].lower()))
        return CsvTable(headers, rows)

    def _count(self, kill_rows, exclude_warm_up) -> Tuple[_Counts, Dict[str, str]]:
        column = self._kill_column
        counts, kinds = _Counts(), {}
        for row in kill_rows:
            if exclude_warm_up and row[column['round_kind']] == 'warm-up':
                continue
            round_number, death_type = row[column['round']], row[column['death_type']]
            killer, victim = row[column['killer']], row[column['victim']]
            kinds[round_number] = row[column['round_kind']]
            if death_type.startswith(NOT_COUNTED_PREFIXES):
                continue
            if death_type == AI_DEATH:
                if killer not in NO_PLAYER_NAMES:
                    counts.add(killer, round_number, 'ai_kills')
                continue
            is_teamkill = row[column['teamkill']] != ''
            if death_type == 'kill' and not is_teamkill and killer != '(runaway horse)':
                counts.add(killer, round_number, 'kills')
            counts.add(victim, round_number, 'deaths')
            if is_teamkill:
                counts.add(killer, round_number, 'teamkills')
        return counts, kinds

    @staticmethod
    def _value(counts: _Counts, player: str, measure: str, net_kills: bool, round_number: Optional[str] = None) -> int:
        value = counts.get(player, measure, round_number)
        if measure == 'kills' and net_kills:
            value -= counts.get(player, 'teamkills', round_number)
        return value

    def _converter_cell(self, player: str, column_name: str) -> str:
        converter_row = self._converter_rows.get(player)
        if converter_row is None or column_name not in self._player_column:
            return ''
        return converter_row[self._player_column[column_name]]

    def _player_row(self, player, counts, kinds, round_columns, net_kills) -> List[str]:
        per_round, gaps = [], []
        for round_number, measure in round_columns:
            if measure == 'score_gap':
                gap = self._converter_cell(player, '%s_score_gap' % round_label(round_number, kinds[round_number]))
                per_round.append(gap)
                if parse_int(gap) is not None:
                    gaps.append(int(gap))
            else:
                per_round.append(str(self._value(counts, player, measure, net_kills, round_number)))
        converter_start, converter_end = (self._converter_cell(player, name) for name in SCOREBOARD_COLUMNS)
        return ([player, str(self._value(counts, player, 'kills', net_kills)), str(counts.get(player, 'deaths')), str(counts.get(player, 'teamkills')),
                 str(counts.get(player, 'ai_kills')), converter_start, converter_end, str(sum(gaps)) if gaps else ''] + per_round)
