"""Names that were never announced with the usual join record (for example because you joined later)."""
import collections
import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .bit_shifting import BIT_OFFSETS, is_printable_ascii, shift_right
from .name_sighting import NameSighting
from .player_roster import PlayerRoster


class RosterFiller:
    """Such names still show up next to the player id in chat and other records. For slots that need a name, this takes the printable string
    that repeats at two or more separate moments."""

    MINIMUM_PAYLOAD_BYTES = 20
    MINIMUM_ALPHANUMERIC = 4
    MINIMUM_TAGGED_LENGTH = 8

    def __init__(self, minimum_clusters: int = 2, cluster_gap_s: float = 10.0):
        self._minimum_clusters = minimum_clusters
        self._cluster_gap_s = cluster_gap_s

    def fill(self, roster: PlayerRoster, timed_payloads: Iterable[Tuple[float, bytes]], slots_needing_names: Iterable[int],
             unknown_since: Optional[Dict[int, float]] = None, earlier_occupant_slots: Iterable[int] = ()) -> PlayerRoster:
        """`unknown_since`: slots whose old name was retired (see PlayerRoster.retire_moved_names). `earlier_occupant_slots`: slots whose first
        known name is provably a later occupant (that name held another slot before): look for an earlier occupant and keep the later names."""
        unknown_since = unknown_since or {}
        earlier_occupant_slots = set(earlier_occupant_slots)
        sightings_by_slot = roster.sightings_by_slot
        slots = [slot for slot in slots_needing_names
                 if slot is not None and slot >= 0 and (slot not in sightings_by_slot or slot in unknown_since or slot in earlier_occupant_slots)]
        if not slots:
            return roster
        player_ids = bytes(sorted({slot + 1 for slot in slots if slot + 1 < 256}))
        if not player_ids:
            return roster
        pattern = re.compile(b'([' + b''.join(b'\\x%02x' % player_id for player_id in player_ids) + b'])([\\x04-\\x28])\\x00', re.S)
        sighting_times = self._collect_sighting_times(pattern, timed_payloads, unknown_since)
        self._drop_names_not_earlier_than_first_known(sighting_times, sightings_by_slot, unknown_since, earlier_occupant_slots)
        for player_id, (_score, name, first_seen_s, last_seen_s, count) in self._pick_best_names(sighting_times).items():
            old_sightings = sightings_by_slot.get(player_id - 1, [])
            new_sighting = NameSighting(first_seen_s, last_seen_s, name, count)
            if player_id - 1 in earlier_occupant_slots and player_id - 1 not in unknown_since:
                sightings_by_slot[player_id - 1] = sorted(old_sightings + [new_sighting])
            else:
                sightings_by_slot[player_id - 1] = sorted([sighting for sighting in old_sightings if player_id - 1 in unknown_since] + [new_sighting])
        return roster

    def _collect_sighting_times(self, pattern, timed_payloads, unknown_since) -> Dict[Tuple[int, str], List[float]]:
        times_by_player_and_name = collections.defaultdict(list)
        for time_s, payload in timed_payloads:
            if len(payload) < self.MINIMUM_PAYLOAD_BYTES:
                continue
            counted_in_payload = set()
            for bit_offset in BIT_OFFSETS:
                shifted = shift_right(payload, bit_offset)
                for match in pattern.finditer(shifted):
                    player_id = match.group(1)[0]
                    if time_s < unknown_since.get(player_id - 1, -1):
                        continue
                    name_length = match.group(2)[0]
                    name_bytes = shifted[match.end():match.end() + name_length]
                    if len(name_bytes) == name_length and is_printable_ascii(name_bytes):
                        name = name_bytes.decode()
                        if sum(character.isalnum() for character in name) >= self.MINIMUM_ALPHANUMERIC and (player_id, name) not in counted_in_payload:
                            counted_in_payload.add((player_id, name))
                            times_by_player_and_name[(player_id, name)].append(time_s)
        return times_by_player_and_name

    @staticmethod
    def _drop_names_not_earlier_than_first_known(sighting_times, sightings_by_slot, unknown_since: Dict[int, float], earlier_occupant_slots: Set[int]) -> None:
        """For a slot that needs an EARLIER occupant, only names sighted before the first known one are new."""
        for (player_id, name) in list(sighting_times):
            slot = player_id - 1
            if slot in earlier_occupant_slots and slot not in unknown_since and sightings_by_slot.get(slot):
                first_known = sightings_by_slot[slot][0]
                if min(sighting_times[(player_id, name)]) >= first_known.first_seen_s - 1 or name in [sighting.name for sighting in sightings_by_slot[slot]]:
                    del sighting_times[(player_id, name)]

    def _pick_best_names(self, sighting_times) -> Dict[int, tuple]:
        best: Dict[int, tuple] = {}
        for (player_id, name), times in sighting_times.items():
            times.sort()
            cluster_count = 1 + sum(1 for earlier, later in zip(times, times[1:]) if later - earlier > self._cluster_gap_s)
            is_tagged = (' ' not in name) and len(name) >= self.MINIMUM_TAGGED_LENGTH and ('_' in name or '[' in name)
            if cluster_count >= self._minimum_clusters or is_tagged:
                score = (min(cluster_count, 2) if not is_tagged else cluster_count + 1, 1 if is_tagged else 0, len(times))
                if player_id not in best or score > best[player_id][0]:
                    best[player_id] = (score, name, times[0], times[-1], len(times))
        return best
