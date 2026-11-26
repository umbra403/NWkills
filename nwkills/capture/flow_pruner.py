"""Keeping only the game server's packets of a big capture."""
from typing import Callable, NamedTuple, Optional

from ..packets.pcapng_file import CapturedFrame, PcapngReader, PcapngWriter
from ..packets.server_flow import FlowKey, GameServerFlowFinder

NO_GAME_SERVER_MESSAGE = 'could not find the game server in the capture. Was the game connected to a server while capturing?'


class PruneResult(NamedTuple):
    flow_key: FlowKey
    packets_kept: int
    packets_seen: int


class _Counter:
    def __init__(self):
        self.count = 0


class ServerFlowPruner:
    """Writes the game flow of a capture (both directions) to a new, much smaller capture. Works on a memory-mapped file."""

    def __init__(self, reader: Optional[PcapngReader] = None, writer: Optional[PcapngWriter] = None):
        self._reader = reader or PcapngReader()
        self._writer = writer or PcapngWriter()

    def prune(self, source_path: str, destination_path: str, wanted_server_port: Optional[int] = None,
              log: Optional[Callable[[str], None]] = None) -> PruneResult:
        finder = GameServerFlowFinder(wanted_server_port)
        flow_key = finder.find_flow_key(self._reader.read_frames(source_path))
        if flow_key is None:
            raise RuntimeError(NO_GAME_SERVER_MESSAGE)
        frames_seen, frames_kept = _Counter(), _Counter()
        self._writer.write_frames(destination_path, self._count(self._frames_of_flow(source_path, finder, flow_key, frames_seen), frames_kept))
        if log:
            log('kept %d of %d packets (server %s:%d)' % (frames_kept.count, frames_seen.count, flow_key.server_address, flow_key.server_port))
        return PruneResult(flow_key, frames_kept.count, frames_seen.count)

    def _frames_of_flow(self, path: str, finder: GameServerFlowFinder, flow_key: FlowKey, frames_seen: _Counter):
        both_directions = (tuple(flow_key), flow_key.reversed_direction())
        for frame in self._reader.read_frames(path):
            frames_seen.count += 1
            datagram = finder.parse_datagram(frame)
            if datagram and (datagram.source_address, datagram.source_port, datagram.destination_address, datagram.destination_port) in both_directions:
                yield frame

    @staticmethod
    def _count(frames, frames_kept: _Counter):
        for frame in frames:
            frames_kept.count += 1
            yield frame
