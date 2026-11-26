"""The scoreboard of every player over time."""
import collections
from typing import Dict, Iterable, List, Tuple

from .score_updates import ScoreUpdate


class ScoreTimeline:
    """slot -> [(time, score)] in time order, from the reliable score updates."""

    def __init__(self, updates: Iterable[ScoreUpdate]):
        self._scores_by_slot: Dict[int, List[Tuple[float, int]]] = collections.defaultdict(list)
        for slot, time_s, score in updates:
            self._scores_by_slot[slot].append((time_s, score))

    def slots(self) -> List[int]:
        return list(self._scores_by_slot)

    def history(self, slot: int) -> List[Tuple[float, int]]:
        return self._scores_by_slot.get(slot, [])

    def scores_before(self, slot: int, time_s: float) -> List[int]:
        """The scores sent strictly before `time_s`."""
        return [score for sent_s, score in self.history(slot) if sent_s < time_s]

    def times_before(self, slot: int, time_s: float) -> List[float]:
        return [sent_s for sent_s, _score in self.history(slot) if sent_s < time_s]

    def scores_between(self, slot: int, first_s: float, last_s: float) -> List[int]:
        """The scores sent from `first_s` to `last_s`, both included."""
        return [score for sent_s, score in self.history(slot) if first_s <= sent_s <= last_s]

    def timed_scores_between(self, slot: int, first_s: float, last_s: float) -> List[Tuple[float, int]]:
        return [(sent_s, score) for sent_s, score in self.history(slot) if first_s <= sent_s <= last_s]

    def single_point_changes(self) -> Dict[int, List[Tuple[float, int]]]:
        """slot -> [(time, +1 or -1)] for every step of exactly one point between two consecutive scores."""
        changes: Dict[int, List[Tuple[float, int]]] = collections.defaultdict(list)
        for slot, history in self._scores_by_slot.items():
            for (_before_s, before), (after_s, after) in zip(history, history[1:]):
                if abs(after - before) == 1:
                    changes[slot].append((after_s, after - before))
        return changes
