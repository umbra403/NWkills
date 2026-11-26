"""The state block at the end of a server -> client packet: a time stamp, then changed properties of agents and of players.

Layout, starting right after the message list:
  1. time:         a varint of 23-bit chunks (each chunk is 24 bits: 23 value bits + a 'more' bit); a flag bit; if the flag is set a second
                   time varint, three 17-bit values, an 8-bit and two 10-bit values.
  2. agent list:   gap-coded property updates. A gap of 0 ends the list. index = previous index + gap (the start is -1);
                   agent = index // 29, property = index % 29; the value is as wide as the property says (PROPERTY_BIT_WIDTHS).
  3. player list:  the same coding; player = index // 2; property 0 is a 13-bit score, property 1 a 10-bit ping."""
from typing import List, NamedTuple, Optional, Tuple

from .bit_reader import BitReader

PROPERTY_BIT_WIDTHS = [33, 10, 10, 8, 10, 10, 10, 9, 3, 3, 2, 2, 3, 11, 32, 32, 32, 32, 14, 14, 14, 14, 1, 1, 1, 1, 1, 8, 1]
PROPERTIES_PER_AGENT = len(PROPERTY_BIT_WIDTHS)
PROPERTIES_PER_PLAYER = 2
PLAYER_SCORE_PROPERTY, PLAYER_PING_PROPERTY = 0, 1
PLAYER_SCORE_BITS, PLAYER_PING_BITS = 13, 10
TIME_CHUNK_BITS = 24
TIME_CHUNK_VALUE_BITS = 23
GAP_CHUNK_BITS = 5
GAP_CHUNK_VALUE_BITS = 4
MAXIMUM_TIME_SHIFT = 200
MAXIMUM_GAP_SHIFT = 64
INDEX_MASK = 0xFFFFFFFF                       # gaps can wrap around: the index is a 32-bit value


class PropertyUpdate(NamedTuple):
    """One changed property. `owner` is the agent or player number."""
    owner: int
    property_number: int
    value: int


class StateBlock(NamedTuple):
    time: int                                  # about 1535 per second since the start of the server
    agent_updates: List[PropertyUpdate]
    player_updates: List[PropertyUpdate]
    end_bit: int                               # where the block ends: a packet that was read correctly ends within 8 bits of this


class _TruncatedStateBlock(Exception):
    """The packet ends, or a varint runs on, before the block is complete."""


class StateBlockParser:
    """Reads the state block of a packet."""

    def parse(self, packet: bytes, start_bit: int) -> Optional[StateBlock]:
        """The block starting at `start_bit`, or None when the packet does not hold a complete block there."""
        reader = BitReader(packet)
        try:
            time, position = self._read_time_varint(reader, start_bit)
            position = self._skip_optional_second_time(reader, position)
            agent_updates, position = self._read_property_updates(reader, position, self._agent_property)
            player_updates, position = self._read_property_updates(reader, position, self._player_property)
        except _TruncatedStateBlock:
            return None
        return StateBlock(time, agent_updates, player_updates, position)

    def _skip_optional_second_time(self, reader: BitReader, position: int) -> int:
        has_second_time = self._read_required(reader, position, 1)
        position += 1
        if not has_second_time:
            return position
        _second_time, position = self._read_time_varint(reader, position)
        for vector_component in range(3):
            self._read_required(reader, position + 17 * vector_component, 17)
        position += 51
        self._read_required(reader, position, 8)
        self._read_required(reader, position + 18, 10)
        return position + 28

    @staticmethod
    def _read_required(reader: BitReader, position: int, bit_count: int) -> int:
        value = reader.read(position, bit_count)
        if value is None:
            raise _TruncatedStateBlock()
        return value

    def _read_time_varint(self, reader: BitReader, position: int) -> Tuple[int, int]:
        value, shift = 0, 0
        while True:
            chunk = self._read_required(reader, position, TIME_CHUNK_BITS)
            value |= (chunk & 0x7fffff) << shift
            position += TIME_CHUNK_BITS
            shift += TIME_CHUNK_VALUE_BITS
            if not (chunk >> TIME_CHUNK_VALUE_BITS) & 1:
                return value, position
            if shift > MAXIMUM_TIME_SHIFT:
                raise _TruncatedStateBlock()

    def _read_gap(self, reader: BitReader, position: int) -> Tuple[int, int]:
        value, shift = 0, 0
        while True:
            chunk = self._read_required(reader, position, GAP_CHUNK_BITS)
            value |= (chunk & 15) << shift
            position += GAP_CHUNK_BITS
            shift += GAP_CHUNK_VALUE_BITS
            if not (chunk >> GAP_CHUNK_VALUE_BITS) & 1:
                return value, position
            if shift > MAXIMUM_GAP_SHIFT:
                raise _TruncatedStateBlock()

    def _read_property_updates(self, reader: BitReader, position: int, property_of_index) -> Tuple[List[PropertyUpdate], int]:
        updates = []
        index = -1
        while True:
            gap, position = self._read_gap(reader, position)
            if gap == 0:
                return updates, position
            index = (index + gap) & INDEX_MASK
            owner, property_number, bit_width = property_of_index(index)
            value = self._read_required(reader, position, bit_width)
            updates.append(PropertyUpdate(owner, property_number, value))
            position += bit_width

    @staticmethod
    def _agent_property(index: int) -> Tuple[int, int, int]:
        agent, property_number = divmod(index, PROPERTIES_PER_AGENT)
        return agent, property_number, PROPERTY_BIT_WIDTHS[property_number]

    @staticmethod
    def _player_property(index: int) -> Tuple[int, int, int]:
        player, property_number = divmod(index, PROPERTIES_PER_PLAYER)
        return player, property_number, PLAYER_SCORE_BITS if property_number == PLAYER_SCORE_PROPERTY else PLAYER_PING_BITS
