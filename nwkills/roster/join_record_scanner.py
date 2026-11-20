"""Player names are sent in clear as <0x06><player id><u16 length><ASCII name>, at any bit offset. This scans payloads for them."""
import collections
import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .bit_shifting import BIT_OFFSETS, is_printable_ascii, shift_right
from .name_sighting import NameSighting, PlayerNameHeuristics


class _SightingTally:
    """How often, and between which times, one (name, player id) pair was seen."""
    __slots__ = ('count', 'first_seen_s', 'last_seen_s')

    def __init__(self):
        self.count, self.first_seen_s, self.last_seen_s = 0, 1e18, -1e18

    def add(self, time_s: float) -> None:
        self.count += 1
        self.first_seen_s = min(self.first_seen_s, time_s)
        self.last_seen_s = max(self.last_seen_s, time_s)


class JoinRecordScanner:
    JOIN_RECORD = re.compile(rb'\x06(.)([\x03-\x28])\x00', re.S)
    # the same record under another message type (seen in one recording where the other had 0x06)
    ALTERNATIVE_JOIN_RECORD = re.compile(rb'[\x03\x43\x83\xc3](.)([\x03-\x28])\x00', re.S)
    MINIMUM_PAYLOAD_BYTES = 20

    def scan(self, timed_payloads: Iterable[Tuple[float, bytes]], min_count: int = 1) -> Dict[int, List[NameSighting]]:
        """{slot: [NameSighting, ...]} sorted by first sighting (slot = player id - 1)."""
        timed_payloads = list(timed_payloads)
        tallies: Dict[Tuple[str, int], _SightingTally] = collections.defaultdict(_SightingTally)
        for time_s, payload in timed_payloads:
            if len(payload) >= self.MINIMUM_PAYLOAD_BYTES:
                self._scan_payload(payload, time_s, tallies, self.JOIN_RECORD)
        # Second pass: the join record of a player can reach one recording as another message type than the other (the same bytes after a 0x03
        # header instead of 0x06). Chat lines use that header too, so such a record is only believed for a name already seen as a player name.
        believed_names = {name for (name, _player_id), tally in tallies.items()
                          if tally.count >= 2 or PlayerNameHeuristics.looks_like_player_name(name)}
        if believed_names:
            for time_s, payload in timed_payloads:
                if len(payload) >= self.MINIMUM_PAYLOAD_BYTES:
                    self._scan_payload(payload, time_s, tallies, self.ALTERNATIVE_JOIN_RECORD, believed_names)
        sightings_by_slot: Dict[int, List[NameSighting]] = collections.defaultdict(list)
        for (name, player_id), tally in tallies.items():
            if tally.count >= min_count and (tally.count >= 2 or PlayerNameHeuristics.looks_like_player_name(name)):
                sightings_by_slot[player_id - 1].append(NameSighting(tally.first_seen_s, tally.last_seen_s, name, tally.count))
        return {slot: sorted(sightings) for slot, sightings in sightings_by_slot.items()}

    @staticmethod
    def _scan_payload(payload: bytes, time_s: float, tallies, pattern, only_names: Optional[Set[str]] = None) -> None:
        already_counted = set()
        for bit_offset in BIT_OFFSETS:
            shifted = shift_right(payload, bit_offset)
            for match in pattern.finditer(shifted):
                name_length = match.group(2)[0]
                name_bytes = shifted[match.end():match.end() + name_length]
                if len(name_bytes) != name_length or not is_printable_ascii(name_bytes):
                    continue
                if only_names is not None and name_bytes.decode() not in only_names:
                    continue
                player_id = match.group(1)[0]
                if (name_bytes, player_id) in already_counted:
                    continue
                already_counted.add((name_bytes, player_id))
                tallies[(name_bytes.decode(), player_id)].add(time_s)
