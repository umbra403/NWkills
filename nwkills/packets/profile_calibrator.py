"""Finds a server's bit widths (ServerProfile) from the packets of its own capture."""
import collections
import itertools
from typing import Callable, Dict, Iterable, List, Sequence

from .bit_reader import BitReader
from .message_reader import FIRST_MESSAGE_BIT, MESSAGE_TYPE_BITS
from .packet_decoder import PacketDecoder
from .server_profile import NWE_PROFILE, ServerProfile

MESSAGE_TYPE_AGENT_SPAWN, MESSAGE_TYPE_PROJECTILE, MESSAGE_TYPE_TYPE7, MESSAGE_TYPE_PLAYER_STATE, MESSAGE_TYPE_TYPE20 = 5, 6, 7, 15, 20
SAMPLE_PACKET_TYPES = (MESSAGE_TYPE_AGENT_SPAWN, MESSAGE_TYPE_PROJECTILE, MESSAGE_TYPE_TYPE7, MESSAGE_TYPE_PLAYER_STATE, MESSAGE_TYPE_TYPE20)
DEFAULT_SAMPLES_PER_TYPE = 24
MINIMUM_PAYLOAD_BYTES = 12


class ProfileCalibrator:
    """Tries candidate widths one group at a time and keeps the ones for which most sample packets parse to their end. A sample is a packet with
    two or three messages whose first message has one of the types that carry the width in question."""

    def __init__(self, samples_per_type: int = DEFAULT_SAMPLES_PER_TYPE, starting_profile: ServerProfile = NWE_PROFILE):
        self._samples_per_type = samples_per_type
        self._starting_profile = starting_profile

    def calibrate(self, payloads: Iterable[bytes], log: Callable[[str], None] = print) -> ServerProfile:
        samples = self._collect_samples(payloads)
        profile = self._starting_profile
        profile = self._search(profile, ['troop_id_bits'], [range(2, 13)], samples[MESSAGE_TYPE_PLAYER_STATE], log)
        profile = self._search(profile, ['type7_id_bits'], [range(8, 14)], samples[MESSAGE_TYPE_TYPE7], log)
        profile = self._search(profile, ['scene_prop_bits'], [range(8, 13)], samples[MESSAGE_TYPE_TYPE20], log)
        profile = self._search(profile, ['item_id_bits'], [range(8, 14)], samples[MESSAGE_TYPE_PROJECTILE], log)
        profile = self._search(profile, ['loadout_item_bits', 'agent_spawn_extra_bits'],
                               [range(8, 14), (0, 9, 8, 10, 1, 2, 3, 4, 5, 6, 7, 11, 12)], samples[MESSAGE_TYPE_AGENT_SPAWN], log)
        return profile

    def _collect_samples(self, payloads: Iterable[bytes]) -> Dict[int, List[bytes]]:
        samples = collections.defaultdict(list)
        for payload in payloads:
            if len(payload) > MINIMUM_PAYLOAD_BYTES and 2 <= payload[7] <= 3:
                first_message_type = BitReader(payload).read(FIRST_MESSAGE_BIT, MESSAGE_TYPE_BITS)
                if first_message_type in SAMPLE_PACKET_TYPES and len(samples[first_message_type]) < self._samples_per_type:
                    samples[first_message_type].append(payload)
        return samples

    def _search(self, profile: ServerProfile, field_names: Sequence[str], candidate_grids, sample_packets: List[bytes], log) -> ServerProfile:
        if not sample_packets:
            return profile
        best_score, best_values = None, None
        for values in itertools.product(*candidate_grids):
            score = self._count_clean_packets(profile.with_values(**dict(zip(field_names, values))), sample_packets)
            if best_score is None or score > best_score:
                best_score, best_values = score, values
        log('  %s = %s  (%d/%d clean)' % (list(field_names), best_values, best_score, len(sample_packets)))
        return profile.with_values(**dict(zip(field_names, best_values)))

    @staticmethod
    def _count_clean_packets(profile: ServerProfile, packets: List[bytes]) -> int:
        decoder = PacketDecoder(profile)
        return sum(decoder.decode(0, 0, packet).is_clean for packet in packets)
