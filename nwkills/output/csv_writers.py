"""One writer per CSV file. The files are UTF-8 with a byte order mark so that Excel opens them correctly."""
import csv
from typing import Iterable, List

from ..analysis.death_classifier import DeathClassifier
from ..analysis.player_tally import PlayerTally
from ..analysis.review_flags import KillReviewFlagger
from ..analysis.scoreboard import ScoreGapReport
from ..events.kill_event import KillEvent
from ..flagbearers import FlagbearerRow
from ..rounds import Round, RoundTimeline

FILE_ENCODING = 'utf-8-sig'


def format_minutes_seconds(seconds: float) -> str:
    return '%d:%02d' % divmod(int(seconds), 60)


def _open_for_csv(path: str):
    return open(path, 'w', newline='', encoding=FILE_ENCODING)


class RoundsCsvWriter:
    HEADER = ['round', 'start_s', 'end_s', 'length_s', 'started_by', 'tickets_zero_at_s', 'tickets_zero_team', 'kills_after_tickets_zero', 'kind',
              'death_msgs', 'method', 'review']

    def write(self, path: str, rounds: List[Round], events: Iterable[KillEvent], timeline: RoundTimeline) -> None:
        """death_msgs = rows of the kills file in that round (one per death). The raw message count is not used: the server sends every death once
        per recipient and each recording catches a different number of those copies, so raw counts differ between recordings."""
        rows_per_round = {}
        for event in events:
            round_number = timeline.number_at(event.time_s)
            rows_per_round[round_number] = rows_per_round.get(round_number, 0) + 1
        with _open_for_csv(path) as output:
            writer = csv.writer(output)
            writer.writerow(self.HEADER)
            for round_ in rounds:
                zero = round_.tickets_zero
                writer.writerow([round_.number, round(round_.start_s), round(round_.end_s), round(round_.end_s - round_.start_s), round_.signals,
                                 zero[0] if zero else '', zero[1] if zero else '', round_.kills_after_ticket_zero, round_.kind,
                                 rows_per_round.get(round_.number, 0), round_.method, round_.review])


class FlagbearersCsvWriter:
    HEADER = ['round', 'round_kind', 'player', 'player_slot', 'class', 'flag', 'spawns', 'first_spawn_s', 'first_spawn_mm:ss', 'last_spawn_s', 'review']

    def write(self, path: str, rows: Iterable[FlagbearerRow]) -> None:
        with _open_for_csv(path) as output:
            writer = csv.writer(output)
            writer.writerow(self.HEADER)
            for row in rows:
                writer.writerow([row.round_number, row.round_kind, row.player, row.owner_slot, row.troop, row.flag, row.spawn_count, row.first_spawn_s,
                                 format_minutes_seconds(row.first_spawn_s), row.last_spawn_s, row.review])


class KillsCsvWriter:
    HEADER = ['round', 'round_kind', 'time_s', 'mm:ss', 'killer', 'victim', 'weapon', 'teamkill', 'death_type', 'respawn_s', 'review', 'killer_slot',
              'victim_slot']

    def __init__(self, classifier: DeathClassifier = None):
        self._classifier = classifier or DeathClassifier()

    def write(self, path: str, events: Iterable[KillEvent], timeline: RoundTimeline) -> None:
        flagger = KillReviewFlagger(timeline)
        with _open_for_csv(path) as output:
            writer = csv.writer(output)
            writer.writerow(self.HEADER)
            for event in events:
                writer.writerow([timeline.number_at(event.time_s), timeline.kind_at(event.time_s), event.time_s, format_minutes_seconds(event.time_s),
                                 event.killer, event.victim, event.weapon, '' if event.admin_label else event.teamkill,
                                 event.admin_label or self._classifier.classify(event), '' if event.respawn_delay_s is None else event.respawn_delay_s,
                                 ' '.join(flagger.flags_for(event)), event.killer_slot, event.victim_slot])


class PlayersCsvWriter:
    FIXED_HEADER = ['player', 'kills', 'deaths', 'teamkills', 'ai_kills', 'score_at_capture_start', 'score_at_capture_end', 'score_gap']
    PER_ROUND_COUNTS = ('kills', 'deaths', 'teamkills', 'score_gap')

    def write(self, path: str, tally: PlayerTally, score_gaps: ScoreGapReport, rounds: List[Round]) -> None:
        """Overall totals leave out warm-up rounds. kills = kills minus teamkills (like the scoreboard); the rows are sorted by that."""
        counted_rounds = [round_.number for round_ in rounds if round_.kind != 'warm-up']
        for name in sorted(score_gaps.player_names() - set(tally.names())):
            tally.ensure_player(name)               # every scoreboard player gets a row
        names = sorted(tally.names(), key=lambda name: -tally.score(name, counted_rounds))
        columns = [(round_, kind) for round_ in rounds for kind in self.PER_ROUND_COUNTS]
        with _open_for_csv(path) as output:
            writer = csv.writer(output)
            writer.writerow(self.FIXED_HEADER + ['%s_%s' % (self._round_label(round_), kind) for round_, kind in columns])
            for name in names:
                gaps = [score_gaps.gap_by_player_round[(name, number)] for number in counted_rounds if score_gaps.has_gap(name, number)]
                row = [name, tally.score(name, counted_rounds), tally.total(name, 'deaths', counted_rounds), tally.total(name, 'teamkills', counted_rounds),
                       tally.total(name, 'ai_kills', counted_rounds), score_gaps.first_score_by_player.get(name, ''), score_gaps.last_score_by_player.get(name, ''),
                       sum(gaps) if gaps else '']
                for round_, kind in columns:
                    if kind == 'score_gap':
                        row.append(score_gaps.gap_by_player_round[(name, round_.number)] if score_gaps.has_gap(name, round_.number) else '')
                    else:
                        row.append(tally.count(name, kind, round_.number))
                writer.writerow(row)

    @staticmethod
    def _round_label(round_: Round) -> str:
        return 'R%d' % round_.number + ('(%s)' % round_.kind if round_.kind else '')
