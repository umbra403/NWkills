from typing import List, NamedTuple, Optional, Tuple

from ..packets.pcapng_file import PcapngReader
from ..packets.server_flow import FlowKey, GameServerFlowFinder


class ServerFlowCapture(NamedTuple):
    key: Optional[FlowKey]
    payloads: List[Tuple[float, bytes]]       # the game server's packets, in time order
    frame_count: int                          # all frames in the file


class ServerFlowReader:
    """Reads the packets of the game server out of a capture file."""

    def __init__(self, reader: Optional[PcapngReader] = None):
        self._reader = reader or PcapngReader()

    def read(self, capture_path: str, wanted_port: Optional[int] = None) -> ServerFlowCapture:
        """The flow found, or key None and no payloads when the capture has no game server."""
        finder = GameServerFlowFinder(wanted_port)
        frame_count = [0]

        def counted_frames():
            for frame in self._reader.read_frames(capture_path):
                frame_count[0] += 1
                yield frame

        flow_key = finder.find_flow_key(counted_frames())
        if flow_key is None:
            return ServerFlowCapture(None, [], frame_count[0])
        return ServerFlowCapture(flow_key, finder.collect_payloads(self._reader.read_frames(capture_path), flow_key), frame_count[0])
