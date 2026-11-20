"""Names and labels the kills file shows instead of a plain '?'."""
from typing import Iterable, List

from ..events.admin_actions import AdminAction
from ..events.kill_event import KillEvent
from .death_classifier import DeathClassifier

WORLD = '(world)'
OWNER_UNKNOWN = '(AI/mount, owner unknown)'


class WorldKillerLabeler:
    """A killer-less death (the server killed the agent: a team swap, or leaving) names the world as killer."""

    def apply(self, events: Iterable[KillEvent]) -> None:
        for event in events:
            if event.killer_agent is not None and event.killer_agent < 0:
                event.killer = WORLD


class AdminDeathLabeler:
    """Admin actions announced by the server ("X Slayed Player Y.", "X Slayed Everyone.", "X Swapped Everyone to Spectators"): the deaths they cause
    are labelled and left out of kills, deaths and teamkills (the scoreboard check still sees the -1 an admin slay gives)."""

    WINDOW_BEFORE_S = 2.5
    WINDOW_AFTER_S = 1.5

    def apply(self, events: Iterable[KillEvent], actions: List[AdminAction]) -> None:
        for event in events:
            event.admin_label = None
            killed_self = event.killer_agent is not None and event.killer_agent == event.victim_agent
            killed_by_world = event.killer_agent is not None and event.killer_agent < 0
            for action in actions:
                if not (action.time_s - self.WINDOW_BEFORE_S <= event.time_s <= action.time_s + self.WINDOW_AFTER_S):
                    continue
                if action.kind == 'slay' and killed_self and event.victim == action.target and event.victim_slot is not None and event.victim_slot >= 0:
                    event.admin_label = 'admin slay'
                elif action.kind == 'slay_all' and (killed_self or killed_by_world):
                    event.admin_label = 'admin: slayed everyone'
                elif action.kind == 'swap_all' and killed_by_world:
                    event.admin_label = 'admin: swapped everyone to spectators'
                if event.admin_label:
                    break


class OwnerlessMountLabeler:
    """A no-blow death (mount / AI unit) whose owner was never seen is labelled as such instead of '?': the label reads the same in every
    recording. The same for a charging horse whose owner was never seen."""

    def __init__(self, classifier: DeathClassifier):
        self._classifier = classifier

    def apply(self, events: Iterable[KillEvent]) -> None:
        for event in events:
            if event.victim == '?' and self._classifier.classify(event).startswith('no-blow death'):
                event.victim = OWNER_UNKNOWN
            if event.killer == '?' and event.killer_slot is None and 'horse charge' in event.weapon:
                event.killer = OWNER_UNKNOWN
