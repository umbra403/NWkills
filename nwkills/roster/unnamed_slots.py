"""Which player slots appear in the kill events without a (correct) name, so the roster filler knows where to look."""
from typing import Iterable, Set, Tuple

from .player_roster import PlayerRoster


class UnnamedSlotFinder:
    FIRST_NAME_LATE_TOLERANCE_S = 5.0
    EARLIER_HOLDER_MARGIN_S = 1.0

    def __init__(self, roster: PlayerRoster):
        self._roster = roster

    def find(self, kill_events: Iterable[dict]) -> Tuple[Set[int], Set[int]]:
        """-> (slots without a name at the time of an event, slots whose first known name is provably a later occupant of the slot).
        `kill_events` are the dictionaries of the kill decoder (keys time, killer_slot, victim_slot)."""
        kill_events = list(kill_events)
        unnamed = set()
        for event in kill_events:
            for role in ('killer', 'victim'):
                slot = event[role + '_slot']
                if slot is not None and slot >= 0 and not self._roster.name_at(slot, event['time']):
                    unnamed.add(slot)
        return unnamed, self._slots_with_earlier_unknown_occupant(kill_events)

    def _slots_with_earlier_unknown_occupant(self, kill_events) -> Set[int]:
        """A slot whose first known name only shows up after an event that used the slot, and that name held ANOTHER slot earlier (the player
        rejoined into this slot): the earlier occupant of this slot is unknown, not that name."""
        slots = set()
        for event in kill_events:
            for role in ('killer', 'victim'):
                slot = event[role + '_slot']
                if slot is None or slot < 0:
                    continue
                sightings = self._roster.sightings(slot)
                if not sightings or not sightings[0].name or sightings[0].first_seen_s <= event['time'] + self.FIRST_NAME_LATE_TOLERANCE_S:
                    continue
                first = sightings[0]
                if any(other.name == first.name and other.first_seen_s < first.first_seen_s - self.EARLIER_HOLDER_MARGIN_S
                       for other_slot, other_sightings in self._roster.sightings_by_slot.items() if other_slot != slot for other in other_sightings):
                    slots.add(slot)
        return slots
