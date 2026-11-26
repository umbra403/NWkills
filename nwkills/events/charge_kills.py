"""Cavalry charge kills whose horse has no known owner."""
import collections
from typing import Callable, List, Optional

from .kill_builder import TEAM_KILL_MODE, SCORE_WINDOW_AFTER_S, SCORE_WINDOW_BEFORE_S
from .kill_event import KillEvent
from .score_timeline import ScoreTimeline
from .weapon_names import HORSE_CHARGE_CLASS


class ChargeKillClaimer:
    """A charge kill whose horse was spawned unowned is credited to the rider by the scoreboard. Every score change of +-1 that one of the
    player's own kills explains (same sign, within the window around the kill) is set aside; the changes left over belong to kills we could not
    attribute. A charge kill takes the player of a leftover change in its window when that is the only one; assignments are repeated, so a
    change claimed by a neighbouring charge kill no longer counts as a rival. Such kills are flagged killer-from-score.

    A charge kill that nobody's score can claim, with no unexplained change in the window at all, was most likely made by a horse without a
    rider (horses move on their own and can bump into players hard enough to kill). The kill is nobody's; the victim's death still counts."""

    WINDOWS_S = ((0.3, 0.5), (0.3, 2.5))           # first the changes that arrive with the kill itself, then the wider window

    def __init__(self, scores: ScoreTimeline, namer: Callable[[Optional[int], float], object]):
        self._scores = scores
        self._namer = namer

    def apply(self, events: List[KillEvent]) -> None:
        unexplained = self._unexplained_changes(events)
        unclaimed = [event for event in events if event.weapon_class == HORSE_CHARGE_CLASS and event.mode == TEAM_KILL_MODE
                     and (event.killer_slot is None or event.killer_slot < 0)]
        while unclaimed:
            claim = self._find_claim(unclaimed, unexplained)
            if claim is None:
                break
            event, (slot, change_s, change) = claim
            unexplained[slot].remove((change_s, change))
            unclaimed.remove(event)
            event.killer_slot = slot
            event.killer = self._namer(slot, event.time_s)
            event.teamkill = 'yes' if change < 0 else ''
            event.team_verdict = None
            event.late_sources = list(event.late_sources) + ['killer-from-score']
            event.burst_guess = False
        for event in unclaimed:
            # nobody rides the horse (the link says so, or its rider is dead) and nobody's score claims the kill: a horse without a rider
            if event.horse_without_rider and not any(event.time_s - SCORE_WINDOW_BEFORE_S <= change_s <= event.time_s + SCORE_WINDOW_AFTER_S
                                                     for changes in unexplained.values() for change_s, _change in changes):
                event.killer = '(runaway horse)'
                event.runaway_horse = True

    def _unexplained_changes(self, events: List[KillEvent]):
        """slot -> the one-point score changes that none of the player's own kills explains."""
        unexplained = collections.defaultdict(list)
        for slot, changes in self._scores.single_point_changes().items():
            own_kills = sorted((event.time_s, -1 if event.teamkill else 1) for event in events if event.killer_slot == slot and event.mode == TEAM_KILL_MODE)
            free = sorted(changes)
            for kill_s, sign in own_kills:
                for index, (change_s, change) in enumerate(free):
                    if kill_s - SCORE_WINDOW_BEFORE_S <= change_s <= kill_s + SCORE_WINDOW_AFTER_S and change == sign:
                        del free[index]
                        break
            unexplained[slot] = free
        return unexplained

    def _find_claim(self, unclaimed: List[KillEvent], unexplained):
        for before_s, after_s in self.WINDOWS_S:
            for event in unclaimed:
                candidates = [(slot, change_s, change) for slot, changes in unexplained.items() for change_s, change in changes
                              if event.time_s - before_s <= change_s <= event.time_s + after_s]
                if candidates and len({candidate[0] for candidate in candidates}) == 1:      # one player (he may have two changes in the window: the nearest is taken)
                    return event, min(candidates, key=lambda candidate: abs(candidate[1] - event.time_s))
        return None
