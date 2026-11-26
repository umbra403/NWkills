"""The scoreboard check: the server sends every player's score (kills - teamkills) when you connect and on every change, so the kills found can be
compared with it."""
import collections
from dataclasses import dataclass, field
from typing import DefaultDict, Dict, Iterable, List, Optional, Tuple

from ..events.kill_event import KillEvent
from ..roster import PlayerRoster
from ..rounds import Round
from .death_classifier import DeathClassifier

ScoreSeries = List[Tuple[float, int]]


class ScoreboardHistory:
    """slot -> [(time, score)], every change, from the packets whose state block parsed to the end (the large map-change blocks give garbage)."""

    MAXIMUM_SLOT_EXCLUSIVE = 250
    MAXIMUM_SCORE = 150

    def __init__(self, series_by_slot: Dict[int, ScoreSeries]):
        self._series_by_slot = series_by_slot

    @classmethod
    def from_records(cls, packet_records: Iterable[dict]) -> 'ScoreboardHistory':
        series_by_slot: DefaultDict[int, ScoreSeries] = collections.defaultdict(list)
        for record in packet_records:
            state_block = record.get('tail')
            if not state_block or record['L'] - state_block['end'] >= 8 or record.get('err'):
                continue
            for slot, property_number, value in state_block['players']:
                if property_number == 0 and 0 <= slot < cls.MAXIMUM_SLOT_EXCLUSIVE:
                    score = value - 8192 if value >= 4096 else value
                    if abs(score) <= cls.MAXIMUM_SCORE and (not series_by_slot[slot] or series_by_slot[slot][-1][1] != score):
                        series_by_slot[slot].append((record['t'], score))
        return cls(dict(series_by_slot))

    def series(self, slot: int) -> ScoreSeries:
        return self._series_by_slot.get(slot, [])

    def items(self):
        return self._series_by_slot.items()


class ScoreChangeLedger:
    """The point changes the found events explain, per slot: +1 for a kill, -1 for a teamkill, -1 for a team swap."""

    SWAP_WINDOW_BEFORE_S = 0.3
    SWAP_WINDOW_AFTER_S = 2.5

    def __init__(self, events: Iterable[KillEvent], scoreboard: ScoreboardHistory, classifier: Optional[DeathClassifier] = None):
        classifier = classifier or DeathClassifier()
        events = list(events)
        self._changes: DefaultDict[int, List[Tuple[float, int]]] = collections.defaultdict(list)
        for event in events:
            if event.killer_agent is not None and event.killer_agent < 0 and event.victim_slot is not None and event.victim_slot >= 0 and not event.admin_label:
                # a team swap (killer-less death, the player respawns) costs 1 point; leaving the server does not. A swapper who is not seen respawning
                # within 2 minutes still shows the penalty on the scoreboard at that moment: a step of exactly -1 within a moment of the death counts too.
                series = scoreboard.series(event.victim_slot)
                dropped = any(event.time_s - self.SWAP_WINDOW_BEFORE_S <= later_s <= event.time_s + self.SWAP_WINDOW_AFTER_S
                              for (_earlier_s, earlier), (later_s, later) in zip(series, series[1:]) if later - earlier == -1)
                if event.respawn_delay_s or dropped:
                    self._changes[event.victim_slot].append((event.time_s, -1))
        for event in events:
            if event.killer_slot is None or event.killer_slot < 0 or event.admin_label:
                continue          # an admin slay is not a point change (the round-end slay-all was counted as a self-death worth -1)
            death_type = classifier.classify(event)
            if death_type == DeathClassifier.KILL or (classifier.is_self_inflicted(death_type) and event.teamkill):
                self._changes[event.killer_slot].append((event.time_s, -1 if event.teamkill else 1))

    def changes(self, slot: int) -> List[Tuple[float, int]]:
        return self._changes[slot]


@dataclass
class ScoreGapReport:
    gap_by_player_round: DefaultDict[Tuple[str, int], int] = field(default_factory=lambda: collections.defaultdict(int))     # (name, round) -> scoreboard change minus recorded net
    checked_slots_by_player_round: collections.Counter = field(default_factory=collections.Counter)
    first_score_by_player: Dict[str, int] = field(default_factory=dict)
    last_score_by_player: Dict[str, int] = field(default_factory=dict)

    def has_gap(self, name: str, round_number: int) -> bool:
        return (name, round_number) in self.checked_slots_by_player_round

    def player_names(self) -> set:
        return {name for name, _round in self.checked_slots_by_player_round}


class ScoreGapAnalyzer:
    """Per player and round: how much the scoreboard changed minus the net of the kills and teamkills found. 0 means the round is complete."""

    RESET_LANDING_S = 6.0                # the scoreboard reset lands a few seconds after the detected round start
    ADMIN_RESET_WINDOW_S = 60.0
    ADMIN_RESET_DELAY_S = 0.5
    RESET_SEARCH_S = 120.0
    CAPTURE_START_KILL_DELAY_S = 0.1
    SLOT_CHANGE_TOLERANCE_S = 5.0
    LARGEST_STEP = 15

    def __init__(self, roster: PlayerRoster):
        self._roster = roster

    def analyze(self, scoreboard: ScoreboardHistory, ledger: ScoreChangeLedger, rounds: List[Round], admin_reset_times: List[float]) -> ScoreGapReport:
        report = ScoreGapReport()
        for slot, series in scoreboard.items():
            for round_ in rounds:
                self._analyze_round(report, slot, series, round_, ledger, admin_reset_times)
            name = self._roster.name_at(slot, series[0][0])
            if name:
                report.first_score_by_player[name] = series[0][1]
                report.last_score_by_player[name] = series[-1][1]
        return report

    def _analyze_round(self, report: ScoreGapReport, slot: int, series: ScoreSeries, round_: Round, ledger: ScoreChangeLedger,
                       admin_reset_times: List[float]) -> None:
        not_first_round = round_.start_s > 0
        window_start_s = round_.start_s + self.RESET_LANDING_S if not_first_round else series[0][0]
        if not_first_round:
            for reset_s in admin_reset_times:          # an admin reset zeroes the scoreboard; it can come well after the detected round start
                if round_.start_s + self.RESET_LANDING_S < reset_s < round_.start_s + self.ADMIN_RESET_WINDOW_S:
                    window_start_s = max(window_start_s, reset_s + self.ADMIN_RESET_DELAY_S)
            before = [score for time_s, score in series if time_s <= window_start_s]
            if not before:
                return
            start_score = before[-1]
        else:
            start_score = series[0][1]
        scores_in_round = [score for time_s, score in series if window_start_s < time_s < round_.end_s]
        window_start_s, start_score, scores_in_round = self._follow_scoreboard_reset(series, round_, window_start_s, start_score, scores_in_round)
        if not_first_round and start_score != 0 and scores_in_round:
            # a player whose score was not re-sent after the reset (no change yet) still shows last round's value: if the first value of the round
            # fits counting from 0 but not from that stale value, the round started from 0
            first_change_s = next(time_s for time_s, _score in series if time_s > window_start_s)
            explained = sum(change for time_s, change in ledger.changes(slot) if window_start_s < time_s <= first_change_s + 0.05)
            if scores_in_round[0] - start_score != explained and scores_in_round[0] == explained:
                start_score = 0
        values = [start_score] + scores_in_round
        if any(abs(after - before) > self.LARGEST_STEP for before, after in zip(values, values[1:])):
            return          # score reset inside the round, or a jump no kills can explain (slot reused / player rejoined)
        name = self._roster.name_at(slot, window_start_s)
        if not name:
            return
        if any(window_start_s + self.SLOT_CHANGE_TOLERANCE_S < sighting.first_seen_s < round_.end_s and sighting.name != name
               for sighting in self._roster.sightings(slot)):
            return          # the slot changed hands inside this round: its score and events belong to two players
        first_kill_offset = 0 if not_first_round else self.CAPTURE_START_KILL_DELAY_S          # capture start: the first score we see already contains the kills of that same moment
        net = sum(change for time_s, change in ledger.changes(slot) if window_start_s + first_kill_offset < time_s < round_.end_s)
        report.gap_by_player_round[(name, round_.number)] += (values[-1] - start_score) - net
        report.checked_slots_by_player_round[(name, round_.number)] += 1

    def _follow_scoreboard_reset(self, series: ScoreSeries, round_: Round, window_start_s: float, start_score: int, scores_in_round: List[int]):
        """The scoreboard reset (score falls to 0 for everyone) can land well after the detected start: if the score drops by 2 or more in the first
        2 minutes of the round, count from the value after that drop (kills only ever add 1, a teamkill takes 1 off)."""
        if round_.start_s <= 0:
            return window_start_s, start_score, scores_in_round
        previous = start_score
        for time_s, score in [(time_s, score) for time_s, score in series if round_.start_s < time_s < round_.end_s]:
            if time_s > round_.start_s + self.RESET_SEARCH_S:
                break
            if abs(score - previous) >= 2 and -1 <= score <= 1 and time_s > window_start_s:      # a reset goes to 0 (or -1 / 1 if the first event follows at once), from above or, after teamkills, from below; seen up to 64 s after a map change
                return time_s, score, [later for later_s, later in series if time_s < later_s < round_.end_s]
            previous = score
        return window_start_s, start_score, scores_in_round
