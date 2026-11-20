"""Kills, deaths and teamkills per player and round."""
import collections
from typing import Dict, Iterable, List

from ..events.kill_event import KillEvent
from ..rounds import RoundTimeline
from .death_classifier import DeathClassifier

UNNAMED_KILLERS = ('?', '(AI)', '(world)')


class PlayerTally:
    """Counts what the kills file shows. A death with an admin label, a death of a player's mount and a no-blow death are not counted; a
    teamkill is counted as a teamkill and not as a kill."""

    def __init__(self, classifier: DeathClassifier = None):
        self._classifier = classifier or DeathClassifier()
        self._counts: Dict[str, collections.Counter] = collections.OrderedDict()

    def add_events(self, events: Iterable[KillEvent], timeline: RoundTimeline) -> None:
        for event in events:
            death_type = self._classifier.classify(event)
            round_number = timeline.number_at(event.time_s)
            if event.admin_label or self._classifier.is_uncounted_mount_death(death_type):
                continue
            if death_type == DeathClassifier.AI_OR_HORSE_DEATH:
                if event.killer not in UNNAMED_KILLERS:
                    self._bump(event.killer, 'ai_kills', round_number)
                continue
            if death_type == DeathClassifier.KILL and not event.teamkill and not event.runaway_horse:
                self._bump(event.killer, 'kills', round_number)
            self._bump(event.victim, 'deaths', round_number)
            if event.teamkill:
                self._bump(event.killer, 'teamkills', round_number)

    def _bump(self, name: str, key: str, round_number: int) -> None:
        counts = self._counts.setdefault(name, collections.Counter())
        counts[key] += 1
        counts[(round_number, key)] += 1

    def ensure_player(self, name: str) -> None:
        """Gives a player without counted events a row of zeros."""
        self._counts.setdefault(name, collections.Counter())

    def names(self) -> List[str]:
        return list(self._counts)

    def count(self, name: str, key: str, round_number: int) -> int:
        return self._counts[name][(round_number, key)]

    def total(self, name: str, key: str, round_numbers: Iterable[int]) -> int:
        return sum(self._counts[name][(round_number, key)] for round_number in round_numbers)

    def score(self, name: str, round_numbers: Iterable[int]) -> int:
        """Kills minus teamkills, like the scoreboard."""
        round_numbers = list(round_numbers)
        return self.total(name, 'kills', round_numbers) - self.total(name, 'teamkills', round_numbers)
