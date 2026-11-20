"""Reads the message list at the start of a server -> client packet.

Packet header (bit positions): 0-10 packet length in bytes, 24-39 sequence number, 40-55 acknowledgement, 56-63 message count + 1,
64-67 width of the peer field - 1. The messages start at bit 68; each is a 6-bit type, a peer field, and a body that depends on the type."""
from typing import List, NamedTuple, Tuple

from .message_layouts import (AGENT_SPAWN_EXTRA, CHAT_TYPES, FIXED_LAYOUTS, KNOWN_MESSAGE_TYPES, PLAYER_JOIN_TYPE, SERVER_TEXT_TYPE, resolve_width)
from .server_profile import ServerProfile

FIRST_MESSAGE_BIT = 68
MESSAGE_COUNT_BYTE = 7
PEER_WIDTH_BIT = 64
MESSAGE_TYPE_BITS = 6
PLAYER_JOIN_NAME_CAP = 255                      # the game rejects longer names: nothing more is read
CHAT_TEXT_CAP = 299                              # the same for chat and server text lines
MAP_TRANSFER_CAP = 450
SHORT_STRING_CAP = 49                            # the two strings of the server-info message
LONG_STRING_CAP = 399
GAME_MODE_BYTES = 16


class UnknownMessageType(Exception):
    """The packet holds a message type this reader has no layout for."""


class RawField(NamedTuple):
    bit_width: int
    value: int


class RawMessage(NamedTuple):
    start_bit: int
    end_bit: int
    message_type: int
    fields: List[RawField]                       # the first field is the peer field


class MessageReadResult(NamedTuple):
    ran_out_of_data: bool                        # True when the packet ended in the middle of a message
    end_bit: int                                 # where the next section (the state block) starts
    messages: List[RawMessage]


class _EndOfPacket(Exception):
    pass


class _BitCursor:
    """A reading position in a packet; every value read is also recorded as a field of the message being read."""

    def __init__(self, payload: bytes):
        self._packet_value = int.from_bytes(payload, 'little')
        self._total_bits = len(payload) * 8
        self.position = FIRST_MESSAGE_BIT
        self.fields: List[RawField] = []

    def begin_message(self) -> None:
        self.fields = []

    def peek_bits(self, start_bit: int, bit_count: int) -> int:
        return (self._packet_value >> start_bit) & ((1 << bit_count) - 1)

    def read(self, bit_count: int) -> int:
        if self.position + bit_count > self._total_bits:
            raise _EndOfPacket()
        value = (self._packet_value >> self.position) & ((1 << bit_count) - 1)
        self.position += bit_count
        self.fields.append(RawField(bit_count, value))
        return value

    def read_many(self, bit_count: int, times: int) -> None:
        for _ in range(times):
            self.read(bit_count)

    def read_string(self, maximum_length: int) -> None:
        """A 16-bit length and that many 8-bit characters; a string longer than the maximum is rejected by the game and its characters are not read."""
        length = self.read(16)
        if length <= maximum_length:
            self.read_many(8, length)


class ServerMessageReader:
    """Reads the messages of a packet for one server profile."""

    def __init__(self, profile: ServerProfile):
        self._profile = profile
        self._data_dependent_readers = {
            PLAYER_JOIN_TYPE: self._read_player_join, 32: self._read_chat, 33: self._read_chat, SERVER_TEXT_TYPE: self._read_chat,
            62: self._read_map_transfer_chunk, 40: self._read_agent_list, 13: self._read_death, 43: self._read_position_update,
            44: self._read_position_update, 7: self._read_type7, 20: self._read_type20, 0: self._read_server_info, 63: self._read_server_info,
            53: self._read_scene_info, 56: self._read_scene_info,
        }

    def read(self, payload: bytes) -> MessageReadResult:
        """Read all messages announced by the packet header. Raises UnknownMessageType for a type without a layout."""
        cursor = _BitCursor(payload)
        messages: List[RawMessage] = []
        message_count = payload[MESSAGE_COUNT_BYTE] - 1 if len(payload) > MESSAGE_COUNT_BYTE else 0
        peer_field_bits = cursor.peek_bits(PEER_WIDTH_BIT, 4) + 1
        try:
            for _ in range(message_count):
                start_bit = cursor.position
                cursor.begin_message()
                message_type = cursor.read(MESSAGE_TYPE_BITS)
                cursor.begin_message()
                if message_type not in KNOWN_MESSAGE_TYPES:
                    raise UnknownMessageType(message_type)
                cursor.read(peer_field_bits)
                self._read_body(cursor, message_type)
                messages.append(RawMessage(start_bit, cursor.position, message_type, cursor.fields))
        except _EndOfPacket:
            return MessageReadResult(True, cursor.position, messages)
        return MessageReadResult(False, cursor.position, messages)

    def _read_body(self, cursor: _BitCursor, message_type: int) -> None:
        layout = FIXED_LAYOUTS.get(message_type)
        if layout is not None:
            self._read_fixed_layout(cursor, message_type, layout)
        else:
            self._data_dependent_readers[message_type](cursor, message_type)

    def _read_fixed_layout(self, cursor: _BitCursor, message_type: int, layout) -> None:
        for width in layout:
            if message_type == 5 and width == AGENT_SPAWN_EXTRA and not self._profile.agent_spawn_extra_bits:
                continue
            cursor.read(resolve_width(width, self._profile))

    def _read_player_join(self, cursor: _BitCursor, message_type: int) -> None:
        cursor.read(8)
        name_length = cursor.read(16)
        if name_length <= PLAYER_JOIN_NAME_CAP:
            cursor.read_many(8, name_length)
        cursor.read(1)
        cursor.read(10)
        cursor.read_many(8, 32)
        cursor.read(3)
        cursor.read(self._profile.troop_id_bits)

    @staticmethod
    def _read_chat(cursor: _BitCursor, message_type: int) -> None:
        cursor.read(7 if message_type == SERVER_TEXT_TYPE else 8)
        text_length = cursor.read(16)
        if text_length <= CHAT_TEXT_CAP:
            cursor.read_many(8, text_length)

    @staticmethod
    def _read_map_transfer_chunk(cursor: _BitCursor, message_type: int) -> None:
        cursor.read(16)
        chunk_length = cursor.read(10)
        if chunk_length <= MAP_TRANSFER_CAP:
            cursor.read_many(8, chunk_length)

    @staticmethod
    def _read_agent_list(cursor: _BitCursor, message_type: int) -> None:
        cursor.read(8)
        cursor.read(5)
        entry_count = cursor.read(5)
        cursor.read_many(32, entry_count)

    @staticmethod
    def _read_death(cursor: _BitCursor, message_type: int) -> None:
        cursor.read(10)
        cursor.read(10)
        cursor.read(5)
        blow_kind = cursor.read(2)
        has_extra_position = cursor.read(1)
        if has_extra_position:
            cursor.read_many(7, 3)
        if blow_kind == 3:
            cursor.read(7)
        if blow_kind & 1:
            cursor.read_many(11, 3)
        if blow_kind & 2:
            cursor.read(9)

    @staticmethod
    def _read_position_update(cursor: _BitCursor, message_type: int) -> None:
        cursor.read(14)
        widths = (17, 17, 17, 12, 12, 12, 12, 17, 17, 17, 12, 12, 12, 12, 17) if message_type == 44 else (17, 17, 17, 12, 12, 12, 12, 17)
        for width in widths:
            cursor.read(width)
        if cursor.read(1):
            cursor.read(20)

    def _read_type7(self, cursor: _BitCursor, message_type: int) -> None:
        cursor.read(14)
        cursor.read(10)
        if cursor.read(1):
            cursor.read(14)
        cursor.read(4)
        cursor.read(self._profile.type7_id_bits)
        for width in (32, 32, 17, 17, 17, 12, 12, 12, 12):
            cursor.read(width)

    def _read_type20(self, cursor: _BitCursor, message_type: int) -> None:
        if cursor.read(1):
            cursor.read(14)
            cursor.read(self._profile.scene_prop_bits)
            cursor.read(12)
        else:
            cursor.read(self._profile.scene_prop_bits)
            cursor.read(12)
            for width in (15, 15, 15, 5):
                cursor.read(width)

    @staticmethod
    def _read_server_info(cursor: _BitCursor, message_type: int) -> None:
        """Type 0 (scene name and welcome text, sent at a map change) and type 63 (the early variant of it)."""
        if message_type == 63:
            if not cursor.read(1):
                cursor.read(32)
                return
            for width in (8, 2, 16, 32, 16, 10, 32):
                cursor.read(width)
        else:
            cursor.read(16)
        cursor.read_many(8, GAME_MODE_BYTES)
        if message_type == 0:
            cursor.read(32)
            cursor.read(16)
            cursor.read(10)
        cursor.read_string(SHORT_STRING_CAP)
        cursor.read_string(LONG_STRING_CAP)

    @staticmethod
    def _read_scene_info(cursor: _BitCursor, message_type: int) -> None:
        """Types 53 and 56 share a handler; 53 ends with 64 more bits."""
        cursor.read_string(SHORT_STRING_CAP)
        cursor.read(14)
        cursor.read(14)
        cursor.read_string(SHORT_STRING_CAP)
        cursor.read(16)
        cursor.read_string(SHORT_STRING_CAP)
        cursor.read(16)
        cursor.read_string(SHORT_STRING_CAP)
        cursor.read(8)
        cursor.read(8)
        cursor.read(1)
        cursor.read(1)
        has_value_list = cursor.read(1)
        if has_value_list:
            while True:
                cursor.read(32)
                if not cursor.read(1):
                    break
        cursor.read(10)
        if message_type == 53:
            cursor.read_many(8, 8)
