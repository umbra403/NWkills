"""Decoding many packets on several processes."""
import multiprocessing
from typing import Callable, List, Optional, Tuple

from .packet_decoder import DecodedPacket, PacketDecoder
from .server_profile import ServerProfile

CHUNK_SIZE = 32

_worker_decoder: Optional[PacketDecoder] = None       # one decoder per worker process, created when the process starts


def _initialize_worker(profile: ServerProfile, keep_all_agent_properties: bool) -> None:
    global _worker_decoder
    _worker_decoder = PacketDecoder(profile, keep_all_agent_properties)


def _decode_in_worker(job: Tuple[int, float, bytes]) -> DecodedPacket:
    packet_index, timestamp, payload = job
    return _worker_decoder.decode(packet_index, timestamp, payload)


class ParallelPacketDecoder:
    """Decodes a list of (packet index, timestamp, payload) jobs with a pool of worker processes. The results keep the order of the jobs."""

    def __init__(self, profile: ServerProfile, process_count: int, keep_all_agent_properties: bool = False):
        self._profile = profile
        self._process_count = process_count
        self._keep_all_agent_properties = keep_all_agent_properties

    def decode_all(self, jobs: List[Tuple[int, float, bytes]], on_progress: Callable[[int, int], None] = lambda done, total: None) -> List[DecodedPacket]:
        packets = []
        with multiprocessing.Pool(self._process_count, initializer=_initialize_worker,
                                  initargs=(self._profile, self._keep_all_agent_properties)) as pool:
            for done, packet in enumerate(pool.imap(_decode_in_worker, jobs, chunksize=CHUNK_SIZE)):
                packets.append(packet)
                on_progress(done, len(jobs))
        return packets
