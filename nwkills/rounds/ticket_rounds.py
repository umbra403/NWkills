"""Rounds from the module's team tickets, for servers that send no round-border messages."""
import collections
from typing import Dict, Iterable, List, Optional, Tuple

from .death_times import death_message_times
from .round_model import Round

TicketReading = Tuple[float, int, int]               # (time, team 0/1, tickets)
ZeroCrossing = Tuple[float, int]                      # (time, team)


class TicketSeriesFinder:
    """Finds the module's team-ticket event: a script event with two arguments (team 0/1, value) whose value mostly counts down."""

    MAXIMUM_TICKETS = 5000
    MINIMUM_READINGS = 100
    MAXIMUM_STEP_DOWN = 10
    MINIMUM_COUNTDOWN_SHARE = 0.3

    def find(self, packet_records: Iterable[dict]) -> Optional[List[TicketReading]]:
        readings_by_event = collections.defaultdict(list)
        for record in packet_records:
            for message_type, event_number, arguments in record.get('ev', ()):
                if len(arguments) == 2 and arguments[0] in (0, 1) and arguments[1] <= self.MAXIMUM_TICKETS:
                    readings_by_event[(message_type, event_number)].append((record['t'], arguments[0], arguments[1]))
        best = None
        for readings in readings_by_event.values():
            if len(readings) < self.MINIMUM_READINGS:
                continue
            share = self._countdown_share(sorted(readings))
            if share > self.MINIMUM_COUNTDOWN_SHARE and (best is None or share > best[0]):
                best = (share, sorted(readings))
        return best[1] if best else None

    def _countdown_share(self, sorted_readings: List[TicketReading]) -> float:
        latest: Dict[int, int] = {}
        decreasing = total = 0
        for _time_s, team, tickets in sorted_readings:
            if team in latest:
                total += 1
                if 0 < latest[team] - tickets <= self.MAXIMUM_STEP_DOWN:
                    decreasing += 1
            latest[team] = tickets
        return decreasing / max(total, 1)


class TicketZeroFinder:
    """The moments a team's tickets ran out (fell to 5 or fewer)."""

    ZERO_LIMIT = 5

    def find(self, series: Iterable[TicketReading]) -> List[ZeroCrossing]:
        latest: Dict[int, int] = {}
        crossings: List[ZeroCrossing] = []
        for time_s, team, tickets in series:
            previous = latest.get(team)
            if tickets <= self.ZERO_LIMIT and (previous is None or previous > self.ZERO_LIMIT):
                crossings.append((time_s, team))
            latest[team] = tickets
        return crossings


class TicketResetRoundDetector:
    """A round starts when a team's tickets jump back up."""

    RESET_JUMP = 60
    MERGE_S = 30.0
    STALE_AFTER_S = 60
    MINIMUM_ROUND_S = 120
    MINIMUM_KILLS = 25

    def detect(self, packet_records: List[dict], series: Iterable[TicketReading]) -> List[Round]:
        first_s, last_s = packet_records[0]['t'], packet_records[-1]['t']
        reference: Dict[int, int] = {}             # the tickets a jump is measured from
        updated_s: Dict[int, float] = {}
        resets: List[float] = []
        zero_crossings: List[ZeroCrossing] = []
        for time_s, team, tickets in series:
            previous = reference.get(team)
            if previous is not None and tickets - previous >= self.RESET_JUMP:
                if not (resets and time_s - resets[-1] < self.MERGE_S):
                    resets.append(time_s)
            if tickets <= TicketZeroFinder.ZERO_LIMIT and (previous is None or previous > TicketZeroFinder.ZERO_LIMIT):
                zero_crossings.append((time_s, team))
            if previous is None or tickets < previous or tickets - previous >= self.RESET_JUMP or time_s - updated_s.get(team, time_s) > self.STALE_AFTER_S:
                reference[team] = tickets
            updated_s[team] = time_s
        starts = [first_s] + resets
        kill_times = death_message_times(packet_records)
        rounds = []
        for index, start_s in enumerate(starts):
            end_s = starts[index + 1] if index + 1 < len(starts) else last_s
            zeros = [(time_s, team) for time_s, team in zero_crossings if start_s <= time_s < end_s]
            kill_count = sum(1 for time_s in kill_times if start_s <= time_s < end_s)
            review = []
            if end_s - start_s < self.MINIMUM_ROUND_S:
                review.append('short (<120 s)')
            if kill_count < self.MINIMUM_KILLS:
                review.append('few kills (%d): dud?' % kill_count)
            rounds.append(Round(number=index + 1, start_s=start_s, end_s=end_s, kill_count=kill_count,
                                signals='capture start' if index == 0 else 'ticket reset',
                                tickets_zero=(round(zeros[0][0]), 'team %d' % zeros[0][1]) if zeros else None,
                                review='; '.join(review), method='tickets'))
        return rounds
