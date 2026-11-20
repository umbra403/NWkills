"""What the Packets tab shows about one server packet."""
import bisect
import collections
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..packets.message_reader import RawMessage, ServerMessageReader
from ..packets.server_profile import ServerProfile

QUEUE_BYTE_INDEX = 7
FIRST_MESSAGE_BYTE_INDEX = 8


def is_queued_payload(payload: bytes) -> bool:
    """A queued packet has a zero where the count byte would be (the game replays it without that byte)."""
    return len(payload) > QUEUE_BYTE_INDEX and payload[QUEUE_BYTE_INDEX] == 0


def format_message_types(message_types: Sequence[int]) -> str:
    """[5, 5, 6] -> '5×2 6'."""
    counts = collections.Counter(message_types)
    return ' '.join(('%d×%d' % (message_type, count) if count > 1 else str(message_type)) for message_type, count in sorted(counts.items()))


@dataclass
class PacketSummary:
    queued: bool
    message_count: int
    messages: List[RawMessage] = field(default_factory=list)
    type_text: str = ''

    @classmethod
    def empty(cls) -> 'PacketSummary':
        return cls(queued=False, message_count=0)


class PacketSummarizer:
    """Decodes the message list of one server -> client payload for the packet list."""

    def __init__(self, profile: ServerProfile):
        self._message_reader = ServerMessageReader(profile)

    def summarize(self, payload: bytes) -> PacketSummary:
        queued = is_queued_payload(payload)
        readable = payload[:QUEUE_BYTE_INDEX] + payload[FIRST_MESSAGE_BYTE_INDEX:] if queued else payload
        message_count = readable[QUEUE_BYTE_INDEX] - 1 if len(readable) > QUEUE_BYTE_INDEX else 0
        messages: List[RawMessage] = []
        if message_count > 0:
            try:
                messages = self._message_reader.read(readable).messages
            except Exception:                    # a damaged packet is shown without its messages
                messages = []
        return PacketSummary(queued, message_count, messages, format_message_types([message.message_type for message in messages]))


class PacketSummaryCache:
    """The summaries of the packets of a capture, decoded when first asked for or all at once by the background indexer."""

    PROGRESS_STEP = 500

    def __init__(self, items: List[Tuple[float, bytes]], summarizer: Optional[PacketSummarizer] = None):
        self._items = items
        self._summarizer = summarizer
        self._summaries: Dict[int, PacketSummary] = {}

    def __len__(self) -> int:
        return len(self._items)

    @property
    def cached_count(self) -> int:
        return len(self._summaries)

    def peek(self, index: int) -> Optional[PacketSummary]:
        """The summary if it was decoded already."""
        return self._summaries.get(index)

    def summary(self, index: int) -> PacketSummary:
        summary = self._summaries.get(index)
        if summary is None:
            summary = self._summaries[index] = self._summarizer.summarize(self._items[index][1])
        return summary

    def fill_all(self, should_stop: Callable[[], bool], report_progress: Callable[[int, int], None]) -> None:
        """Decodes every packet that is not cached yet. A packet that cannot be decoded gets an empty summary."""
        total = len(self._items)
        for index in range(total):
            if should_stop():
                return
            if index not in self._summaries:
                try:
                    self._summaries[index] = self._summarizer.summarize(self._items[index][1])
                except Exception:
                    self._summaries[index] = PacketSummary.empty()
            if index % self.PROGRESS_STEP == 0:
                report_progress(index, total)
        report_progress(total, total)


class PacketRowFormatter:
    """The texts of one row of the packet list."""

    HEADERS = ['No.', 'Time (s)', 'Length', 'Flags', 'Msgs', 'Message types']

    @staticmethod
    def flags_text(payload: bytes) -> str:
        return 'queued' if is_queued_payload(payload) else ''

    @classmethod
    def cell_text(cls, column: int, row: int, time_s: float, payload: bytes, summary: Optional[PacketSummary]) -> str:
        """`summary` is only needed for the last two columns."""
        if column == 0:
            return str(row + 1)
        if column == 1:
            return '%.6f' % time_s
        if column == 2:
            return str(len(payload))
        if column == 3:
            return cls.flags_text(payload)
        return str(summary.message_count) if column == 4 else summary.type_text

    @classmethod
    def search_text(cls, row: int, payload: bytes, summary: Optional[PacketSummary]) -> str:
        """What the display filter searches: number, flags, length and (once decoded) the message types."""
        return '%d %s %d %s' % (row + 1, cls.flags_text(payload), len(payload), summary.type_text if summary else '')


class HexDump:
    @staticmethod
    def format(data: bytes, width: int = 16) -> str:
        lines = []
        for offset in range(0, len(data), width):
            chunk = data[offset:offset + width]
            hex_part = ' '.join('%02x' % byte for byte in chunk)
            text_part = ''.join(chr(byte) if 32 <= byte < 127 else '.' for byte in chunk)
            lines.append('%04x  %-*s  %s' % (offset, width * 3 - 1, hex_part, text_part))
        return '\n'.join(lines)


def packet_index_at_time(times: Sequence[float], time_s: float) -> int:
    """The packet at (or just before) a time, for 'show this kill in the packet list'."""
    index = bisect.bisect_left(times, time_s - 0.05)
    return min(index, len(times) - 1)
