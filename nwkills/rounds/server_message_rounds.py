"""Rounds from the server's own boundary signals."""
from typing import List, Optional

from .boundary_signals import BoundaryTime, RestartAnnouncementFinder
from .death_times import death_message_times
from .round_model import Round
from .ticket_rounds import TicketReading, TicketZeroFinder

SIGNAL_TEXTS = {'capture start': 'capture start', 'map': 'map change message', 'reset': 'reset message'}


class ServerMessageRoundDetector:
    """One round per stretch between two boundaries. A map change (or a quick reset) followed by the real admin reset is a warm-up round;
    which round is live stays inferred, the borders do not."""

    QUICK_RESET_S = 60
    MINIMUM_KILLS = 25

    def __init__(self, restart_finder: Optional[RestartAnnouncementFinder] = None, zero_finder: Optional[TicketZeroFinder] = None):
        self._restart_finder = restart_finder or RestartAnnouncementFinder()
        self._zero_finder = zero_finder or TicketZeroFinder()

    def detect(self, packet_records: List[dict], boundaries: List[BoundaryTime], ticket_series: Optional[List[TicketReading]] = None) -> List[Round]:
        first_s, last_s = packet_records[0]['t'], packet_records[-1]['t']
        starts = [first_s] + [time_s for time_s, _kind in boundaries]
        kinds = ['capture start'] + [kind for _time_s, kind in boundaries]
        zero_crossings = self._zero_finder.find(ticket_series) if ticket_series else []
        restart_calls = self._restart_finder.find(packet_records)
        kill_times = death_message_times(packet_records)
        rounds = []
        for index, start_s in enumerate(starts):
            end_s = starts[index + 1] if index + 1 < len(starts) else last_s
            zeros = [(time_s, team) for time_s, team in zero_crossings if start_s <= time_s < end_s]
            kill_count = sum(1 for time_s in kill_times if start_s <= time_s < end_s)
            kills_after_zero = sum(1 for time_s in kill_times if zeros and zeros[0][0] <= time_s < end_s)
            next_kind = kinds[index + 1] if index + 1 < len(kinds) else None
            next_start_s = starts[index + 1] if index + 1 < len(starts) else None
            announced_live = index > 0 and any(start_s <= call_s < end_s for call_s in restart_calls)           # the admin announced 'reset and live' inside this segment
            is_warm_up = (kinds[index] == 'map' or (kinds[index] == 'reset' and next_kind == 'reset' and next_start_s - start_s < self.QUICK_RESET_S)
                          or (announced_live and next_kind is not None))
            is_live = not is_warm_up and kinds[index] != 'capture start'
            review = []
            if is_warm_up and kinds[index] == 'map' and next_kind != 'reset':
                review.append('not live (map change, no admin reset followed): dud?')
            elif is_warm_up:
                review.append('not live (warm-up before admin reset): dud?')
            elif kinds[index] == 'capture start':
                review.append('capture start (before first map change/reset)')
            if kill_count < self.MINIMUM_KILLS:
                review.append('few kills (%d)' % kill_count)
            rounds.append(Round(number=index + 1, start_s=start_s, end_s=end_s, kill_count=kill_count, signals=SIGNAL_TEXTS[kinds[index]],
                                method='server messages', review='; '.join(review), kind='warm-up' if is_warm_up else ('live' if is_live else 'pre-live'),
                                tickets_zero=(round(zeros[0][0]), 'team %d' % zeros[0][1]) if zeros else None,
                                kills_after_ticket_zero=kills_after_zero if zeros else ''))
        return rounds
