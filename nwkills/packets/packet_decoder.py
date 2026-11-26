"""Decodes one server -> client UDP payload: the message list, then the state block."""
from dataclasses import dataclass, field
from typing import List, NamedTuple, Optional, Tuple

from .message_layouts import PLAYER_JOIN_TYPE, SERVER_TEXT_TYPE
from .message_reader import FIRST_MESSAGE_BIT, ServerMessageReader
from .server_profile import ServerProfile
from .state_block import PropertyUpdate, StateBlock, StateBlockParser

HEADER_BYTES_BEFORE_COUNT = 7
MESSAGE_COUNT_BYTE = 7
AGENT_SPAWN_TYPE, PROJECTILE_TYPE, DEATH_TYPE, LOCAL_RESPAWN_TYPE, HIT_TYPE = 5, 6, 13, 18, 28
KEPT_MESSAGE_TYPES = (AGENT_SPAWN_TYPE, PROJECTILE_TYPE, DEATH_TYPE, LOCAL_RESPAWN_TYPE, HIT_TYPE)
MOUNT_RIDER_LINK_TYPE = 30
MAP_CHANGE_TYPE, RESET_TYPE = 0, 41
SCRIPT_EVENT_TYPES = (36, 37, 38)
SCRIPT_EVENT_WRAPPER = 107
KEPT_AGENT_PROPERTIES = (6, 7, 13, 27)          # rider markers, health, owner
PLAYER_NAME_BITS, PLAYER_NAME_LENGTH_BITS = 8, 16
MINIMUM_NAME_LENGTH, MAXIMUM_NAME_LENGTH = 3, 40
FIRST_PRINTABLE, LAST_PRINTABLE = 32, 126
QUEUED_ERROR = 'queued'
CLEAN_END_TOLERANCE_BITS = 8                      # a packet that was read correctly ends within this many bits of its state block


class KeptMessage(NamedTuple):
    """A message the later stages use. `values` and `bit_widths` include the peer field first."""
    message_type: int
    values: List[int]
    bit_widths: List[int]


class ScriptEvent(NamedTuple):
    message_type: int
    event_number: int
    arguments: List[int]


class BoundaryMessage(NamedTuple):
    """A round border the server announces. `kind` is 'map' (type 0: the client starts loading a new map) or 'reset' (type 41: the same map
    starts again). The server sends each announcement several times in a row; `running_count` counts 0, 1, 2 ... through them."""
    kind: str
    running_count: int


@dataclass
class DecodedPacket:
    packet_index: int
    timestamp: float
    bit_length: int                                   # of the payload without the queue byte
    declared_message_count: int
    kept_messages: List[KeptMessage] = field(default_factory=list)
    player_joins: List[Tuple[int, str]] = field(default_factory=list)          # (player id, name)
    mount_links: List[Tuple[int, int]] = field(default_factory=list)           # (horse agent, rider agent); a rider of -1 means nobody
    script_events: List[ScriptEvent] = field(default_factory=list)
    server_text_lines: List[str] = field(default_factory=list)
    same_map_reset_markers: int = 0
    round_boundaries: List[BoundaryMessage] = field(default_factory=list)
    state_block: Optional[StateBlock] = None
    error: Optional[str] = None
    was_queued: bool = False

    @property
    def reached_state_block_end(self) -> bool:
        return self.state_block is not None and self.bit_length - self.state_block.end_bit < CLEAN_END_TOLERANCE_BITS

    @property
    def is_clean(self) -> bool:
        """True when the messages and the state block were read to the end of the packet."""
        return self.reached_state_block_end and not self.error

    def to_legacy_record(self) -> dict:
        """The dictionary form the later stages still use (removed when they move to this class)."""
        state_block = self.state_block
        return dict(
            i=self.packet_index, t=self.timestamp, L=self.bit_length, n=self.declared_message_count,
            msgs=[tuple(message) for message in self.kept_messages], joins=list(self.player_joins), links=list(self.mount_links),
            ev=[tuple(event) for event in self.script_events], txt=list(self.server_text_lines), rst=self.same_map_reset_markers,
            bnd=[tuple(boundary) for boundary in self.round_boundaries],
            tail=None if state_block is None else dict(time=state_block.time, agents=list(state_block.agent_updates),
                                                        players=list(state_block.player_updates), end=state_block.end_bit),
            err=self.error, q=self.was_queued)


class PacketDecoder:
    """Decodes packets for one server profile."""

    def __init__(self, profile: ServerProfile, keep_all_agent_properties: bool = False,
                 state_block_parser: Optional[StateBlockParser] = None):
        self._message_reader = ServerMessageReader(profile)
        self._state_block_parser = state_block_parser or StateBlockParser()
        self._keep_all_agent_properties = keep_all_agent_properties

    def decode(self, packet_index: int, timestamp: float, payload: bytes) -> DecodedPacket:
        was_queued = len(payload) > MESSAGE_COUNT_BYTE and payload[MESSAGE_COUNT_BYTE] == 0
        if was_queued:
            payload = self.remove_queue_byte(payload)
        message_count = payload[MESSAGE_COUNT_BYTE] - 1 if len(payload) > MESSAGE_COUNT_BYTE else 0
        packet = DecodedPacket(packet_index, timestamp, len(payload) * 8, message_count, was_queued=was_queued)
        state_block_start = FIRST_MESSAGE_BIT
        if message_count > 0:
            state_block_start = self._read_messages(packet, payload, message_count)
            if state_block_start is None:
                return packet
        if was_queued:
            packet.error = packet.error or QUEUED_ERROR          # the game never reads the state block of a stored packet
            return packet
        state_block = self._state_block_parser.parse(payload, state_block_start)
        if state_block is None:
            packet.error = (packet.error or '') + 'tail'
        else:
            packet.state_block = self._keep_useful_updates(state_block)
        return packet

    @staticmethod
    def remove_queue_byte(payload: bytes) -> bytes:
        """A message count of -1 (byte 7 = 0) makes the game store the packet and replay it later without that byte."""
        return payload[:HEADER_BYTES_BEFORE_COUNT] + payload[HEADER_BYTES_BEFORE_COUNT + 1:]

    def _read_messages(self, packet: DecodedPacket, payload: bytes, message_count: int) -> Optional[int]:
        """Fill the message fields of `packet`. Returns where the state block starts, or None when the messages could not be read."""
        try:
            result = self._message_reader.read(payload)
        except Exception:                              # an unknown message type, or a layout that does not fit
            packet.error = 'msg'
            return None
        if len(result.messages) != message_count:
            packet.error = 'count%d/%d' % (len(result.messages), message_count)
        self._extract_message_content(packet, result.messages)
        return result.end_bit

    def _extract_message_content(self, packet: DecodedPacket, messages) -> None:
        packet.kept_messages = [KeptMessage(message.message_type, [field.value for field in message.fields], [field.bit_width for field in message.fields])
                                for message in messages if message.message_type in KEPT_MESSAGE_TYPES]
        packet.player_joins = self._extract_player_joins(messages)
        packet.mount_links = self._extract_mount_links(messages)
        packet.server_text_lines = [self._printable_text(message.fields) for message in messages if message.message_type == SERVER_TEXT_TYPE]
        packet.same_map_reset_markers = sum(1 for message in messages if message.message_type == RESET_TYPE and len(message.fields) == 1
                                            and message.fields[0].bit_width in (1, 3))
        packet.round_boundaries = [BoundaryMessage('map' if message.message_type == MAP_CHANGE_TYPE else 'reset',
                                                   message.fields[0].value if message.fields else 0)
                                   for message in messages if message.message_type in (MAP_CHANGE_TYPE, RESET_TYPE)]
        packet.script_events = [ScriptEvent(message.message_type, message.fields[2].value, [field.value for field in message.fields[3:]])
                                for message in messages if message.message_type in SCRIPT_EVENT_TYPES and len(message.fields) >= 4
                                and message.fields[1].value == SCRIPT_EVENT_WRAPPER]

    @staticmethod
    def _printable_text(fields) -> str:
        return ''.join(chr(field.value) for field in fields if field.bit_width == 8 and FIRST_PRINTABLE <= field.value <= LAST_PRINTABLE)

    @staticmethod
    def _extract_player_joins(messages) -> List[Tuple[int, str]]:
        """Join records (type 3: flag, player id, name length, name characters), found as messages so any bit offset works."""
        joins = []
        for message in messages:
            if message.message_type != PLAYER_JOIN_TYPE:
                continue
            fields = message.fields
            if len(fields) < 4 or fields[1].bit_width != PLAYER_NAME_BITS or fields[2].bit_width != PLAYER_NAME_LENGTH_BITS:
                continue
            name_length = fields[2].value
            if not MINIMUM_NAME_LENGTH <= name_length <= MAXIMUM_NAME_LENGTH or len(fields) < 3 + name_length:
                continue
            characters = [field.value for field in fields[3:3 + name_length] if field.bit_width == 8]
            if len(characters) == name_length and all(FIRST_PRINTABLE <= character <= LAST_PRINTABLE for character in characters):
                joins.append((fields[1].value, ''.join(map(chr, characters))))
        return joins

    @staticmethod
    def _extract_mount_links(messages) -> List[Tuple[int, int]]:
        """Type 30 sets a horse's rider (agent + 1, 0 = nobody): what the client keeps in the horse agent's rider field."""
        return [(message.fields[1].value - 1, message.fields[2].value - 1) for message in messages
                if message.message_type == MOUNT_RIDER_LINK_TYPE and len(message.fields) >= 3
                and message.fields[1].bit_width == 10 and message.fields[2].bit_width == 10]

    def _keep_useful_updates(self, state_block: StateBlock) -> StateBlock:
        if self._keep_all_agent_properties:
            return state_block
        useful_updates = [update for update in state_block.agent_updates if update.property_number in KEPT_AGENT_PROPERTIES]
        return StateBlock(state_block.time, useful_updates, state_block.player_updates, state_block.end_bit)
