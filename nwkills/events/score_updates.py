"""Which score updates from the state blocks can be believed."""
import os
from typing import Iterable, List, Optional, Tuple

ScoreUpdate = Tuple[int, float, int]                  # (player slot, time, score)


class ScoreUpdateFilter:
    """The server repeats a score update in every tick until it is acknowledged, so a real value shows up in several packets within a moment.
    A value that appears once, or only in packets that did not parse cleanly, is usually a mis-read (random values like 222 or -2615 made fake
    teamkills).

    Modes (the NWOBS environment variable chooses one for experiments): '0' keeps everything, '1' keeps every value seen in a clean packet,
    '2' keeps values seen twice within a moment, '3' (default) also keeps a single sighting of a small score."""

    REPEAT_GAP_S = 1.0
    SMALL_SCORE_LIMIT = 60

    def __init__(self, mode: Optional[str] = None):
        self._mode = os.environ.get('NWOBS', '3') if mode is None else mode

    def keep_reliable(self, raw_updates: Iterable[Tuple[float, int, int, bool]]) -> List[ScoreUpdate]:
        """`raw_updates` are (time, player slot, score, packet was read cleanly). The result is sorted by time."""
        if self._mode == '0':
            return [(slot, time_s, score) for time_s, slot, score, _clean in raw_updates]
        times_by_value = {}
        for time_s, slot, score, clean in raw_updates:
            if clean:
                times_by_value.setdefault((slot, score), []).append(time_s)
        kept: List[ScoreUpdate] = []
        for (slot, score), times in times_by_value.items():
            for group in self._group_by_repetition(sorted(times)):
                if self._mode == '1' or len(group) >= 2 or (self._mode == '3' and abs(score) <= self.SMALL_SCORE_LIMIT):
                    kept += [(slot, time_s, score) for time_s in group]
        kept.sort(key=lambda update: update[1])
        return kept

    def _group_by_repetition(self, sorted_times: List[float]) -> List[List[float]]:
        groups = [[sorted_times[0]]]
        for time_s in sorted_times[1:]:
            if time_s - groups[-1][-1] < self.REPEAT_GAP_S:
                groups[-1].append(time_s)
            else:
                groups.append([time_s])
        return groups
