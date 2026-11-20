"""Finding the game server's packet flow in a capture."""
import collections
from typing import Iterable, List, NamedTuple, Optional, Tuple

from .pcapng_file import CapturedFrame
from .udp import UdpDatagramParser

MINIMUM_PACKETS_IN_FLOW = 50
MINIMUM_SHARE_WITH_LENGTH_HEADER = 0.9
MINIMUM_PAYLOAD_BYTES = 13                 # shorter datagrams are never game state packets
LENGTH_FIELD_MASK = 0x7ff                  # the first 11 bits of a game packet hold its own length in bytes


class FlowKey(NamedTuple):
    """The server -> client direction of a UDP conversation."""
    server_address: str
    server_port: int
    client_address: str
    client_port: int

    def reversed_direction(self) -> Tuple[str, int, str, int]:
        """The same conversation seen from the client: (source address, source port, destination address, destination port)."""
        return self.client_address, self.client_port, self.server_address, self.server_port


class _FlowStatistics:
    def __init__(self):
        self.packet_count = 0
        self.byte_count = 0
        self.packets_with_length_header = 0


class GameServerFlowFinder:
    """The game's state packets come from the server as the biggest UDP flow whose packets start with their own length."""

    def __init__(self, wanted_server_port: Optional[int] = None, datagram_parser: Optional[UdpDatagramParser] = None):
        self._wanted_server_port = wanted_server_port
        self._datagram_parser = datagram_parser or UdpDatagramParser()

    def parse_datagram(self, frame: CapturedFrame):
        """The UDP datagram of a frame, or None when the frame is not a (readable) UDP packet."""
        try:
            datagram = self._datagram_parser.parse(frame.link_type, frame.data)
        except Exception:
            return None
        if datagram is None or datagram.source_port is None:
            return None
        return datagram

    def find_flow_key(self, frames: Iterable[CapturedFrame]) -> Optional[FlowKey]:
        """The server flow of the capture (the frames are read once), or None when there is none."""
        statistics_by_flow = collections.defaultdict(_FlowStatistics)
        for frame in frames:
            datagram = self.parse_datagram(frame)
            if datagram is None or len(datagram.payload) < MINIMUM_PAYLOAD_BYTES:
                continue
            if self._wanted_server_port and datagram.source_port != self._wanted_server_port:
                continue
            statistics = statistics_by_flow[FlowKey(datagram.source_address, datagram.source_port, datagram.destination_address, datagram.destination_port)]
            statistics.packet_count += 1
            statistics.byte_count += len(datagram.payload)
            if self.has_length_header(datagram.payload):
                statistics.packets_with_length_header += 1
        candidates = [(key, statistics) for key, statistics in statistics_by_flow.items()
                      if statistics.packet_count >= MINIMUM_PACKETS_IN_FLOW
                      and statistics.packets_with_length_header >= MINIMUM_SHARE_WITH_LENGTH_HEADER * statistics.packet_count]
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate[1].byte_count)[0]

    @staticmethod
    def has_length_header(payload: bytes) -> bool:
        return (payload[0] | (payload[1] << 8)) & LENGTH_FIELD_MASK == len(payload)

    def collect_payloads(self, frames: Iterable[CapturedFrame], flow_key: FlowKey) -> List[Tuple[float, bytes]]:
        """[(timestamp, payload)] of the given flow, in time order."""
        payloads = []
        for frame in frames:
            datagram = self.parse_datagram(frame)
            if datagram is None or len(datagram.payload) < MINIMUM_PAYLOAD_BYTES:
                continue
            if FlowKey(datagram.source_address, datagram.source_port, datagram.destination_address, datagram.destination_port) == flow_key:
                payloads.append((frame.timestamp_seconds, datagram.payload))
        return sorted(payloads, key=lambda item: item[0])
