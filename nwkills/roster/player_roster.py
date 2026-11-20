"""The names of the players per slot, over time."""
import collections
from typing import Dict, Iterable, List, Optional

from .join_record_scanner import JoinRecordScanner
from .name_sighting import NameSighting, PlayerNameHeuristics


class PlayerRoster:
    """slot -> the names seen in that slot, sorted by first sighting. Slots get reused when players leave and join, so a lookup is
    always for a moment in time."""

    SLOT_REUSE_TOLERANCE_S = 5.0          # a name is the slot's holder from this long before its first sighting
    UNKNOWN_MARK_TOLERANCE_S = 1.0

    def __init__(self, sightings_by_slot: Optional[Dict[int, List[NameSighting]]] = None):
        self._sightings_by_slot = sightings_by_slot if sightings_by_slot is not None else {}

    @classmethod
    def scan(cls, timed_payloads, min_count: int = 1) -> 'PlayerRoster':
        return cls(JoinRecordScanner().scan(timed_payloads, min_count))

    @property
    def sightings_by_slot(self) -> Dict[int, List[NameSighting]]:
        return self._sightings_by_slot

    def sightings(self, slot: int) -> List[NameSighting]:
        return self._sightings_by_slot.get(slot) or []

    def has_slot(self, slot: int) -> bool:
        return slot in self._sightings_by_slot

    def name_count(self) -> int:
        return sum(len(sightings) for sightings in self._sightings_by_slot.values())

    def name_at(self, slot: int, time_s: float) -> Optional[str]:
        """The name holding this slot at that time: the latest name first seen at or before it (a few seconds early is allowed)."""
        sightings = self._sightings_by_slot.get(slot)
        if not sightings:
            return None
        current = sightings[0]
        for sighting in sightings:
            if sighting.first_seen_s <= time_s + self.SLOT_REUSE_TOLERANCE_S:
                current = sighting
        return current.name

    def slot_of_name_containing(self, text: str) -> Optional[int]:
        """The last slot (in slot order of insertion) that ever held a name containing the text, ignoring case."""
        found = None
        for slot, sightings in self._sightings_by_slot.items():
            if any(text.lower() in sighting.name.lower() for sighting in sightings):
                found = slot
        return found

    def merge_join_records(self, packet_records: Iterable[dict]) -> int:
        """Add the names from parsed join messages (record['joins'] = [(player id, name)], found by the decoder at any bit offset). The byte scan
        only matches one of the layouts the record is sent in; this catches the rest. Returns how many entries were new."""
        totals: Dict[tuple, list] = {}
        for record in packet_records:
            for player_id, name in record.get('joins') or ():
                total = totals.setdefault((player_id, name), [0, record['t'], record['t']])
                total[0] += 1
                total[1] = min(total[1], record['t'])
                total[2] = max(total[2], record['t'])
        new_entries = 0
        for (player_id, name), (count, first_seen_s, last_seen_s) in totals.items():
            sightings = self._sightings_by_slot.setdefault(player_id - 1, [])
            for index, sighting in enumerate(sightings):
                if sighting.name == name:
                    sightings[index] = NameSighting(min(sighting.first_seen_s, first_seen_s), max(sighting.last_seen_s, last_seen_s),
                                                    name, max(sighting.count, count))
                    break
            else:
                sightings.append(NameSighting(first_seen_s, last_seen_s, name, count))
                new_entries += 1
            sightings.sort()
        return new_entries

    def retire_moved_names(self) -> Dict[int, float]:
        """A name can only hold one slot at a time. When a name first shows up in another slot later, its old slot is no longer that player's
        from that moment (they left and rejoined); mark it unknown (an entry with an empty name) so a stale name is not reused for whoever took
        the slot. Returns {slot: time_from_which_the_name_is_unknown}."""
        first_sightings_by_name = collections.defaultdict(list)
        for slot, sightings in self._sightings_by_slot.items():
            for sighting in sightings:
                if sighting.name:
                    first_sightings_by_name[sighting.name].append((sighting.first_seen_s, slot, sighting.count))
        unknown_since: Dict[int, float] = {}
        for name, first_sightings in first_sightings_by_name.items():
            first_sightings.sort()
            for (_first_1, old_slot, _count_1), (first_2, new_slot, count_2) in zip(first_sightings, first_sightings[1:]):
                if old_slot == new_slot:
                    continue
                if count_2 < 2 and not PlayerNameHeuristics.looks_like_player_name(name):
                    continue          # a one-off sighting can be a coincidental byte pattern: it must at least look like a real name
                holders = [sighting for sighting in self._sightings_by_slot[old_slot] if sighting.first_seen_s <= first_2 + self.SLOT_REUSE_TOLERANCE_S]
                if holders and holders[-1].name == name:          # also when another name takes the slot later: the stretch in between is unknown
                    if not any((not sighting.name) and abs(sighting.first_seen_s - first_2) < self.UNKNOWN_MARK_TOLERANCE_S
                               for sighting in self._sightings_by_slot[old_slot]):
                        self._sightings_by_slot[old_slot] = sorted(self._sightings_by_slot[old_slot] + [NameSighting(first_2, first_2, '', 0)])
                    unknown_since[old_slot] = min(unknown_since.get(old_slot, 1e18), first_2)
        return unknown_since
