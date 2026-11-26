"""A round, and the list of rounds of a capture."""
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union


@dataclass
class Round:
    number: int
    start_s: float
    end_s: float
    kill_count: int                                       # death messages in the round (the sender repeats them: a raw count, not the rows of the kills file)
    signals: str                                          # what started the round
    method: str
    review: str = ''
    kind: str = ''                                        # 'warm-up', 'live', 'pre-live', or '' when the method cannot tell
    tickets_zero: Optional[Tuple[int, str]] = None        # (second, 'team N') when a team's tickets ran out
    kills_after_ticket_zero: Union[int, str] = ''


class RoundTimeline:
    """The rounds of a capture, to ask at which round a moment belongs."""

    TIME_TOLERANCE_S = 1e-9

    def __init__(self, rounds: List[Round]):
        self._rounds = rounds

    @property
    def rounds(self) -> List[Round]:
        return self._rounds

    def round_at(self, time_s: float) -> Optional[Round]:
        """The round that holds the moment, or the last round when it is past the end, or None without rounds."""
        for round_ in self._rounds:
            if round_.start_s <= time_s < round_.end_s + self.TIME_TOLERANCE_S:
                return round_
        return self._rounds[-1] if self._rounds else None

    def number_at(self, time_s: float) -> int:
        round_ = self.round_at(time_s)
        return round_.number if round_ else 1

    def kind_at(self, time_s: float) -> str:
        round_ = self.round_at(time_s)
        return round_.kind if round_ else ''
