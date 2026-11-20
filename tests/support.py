"""Builders for the byte strings the tests feed to the code: bit-packed game packets, IPv4 frames and pcapng files."""
import os
import sys
import struct
from typing import List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

PEER_FIELD_BITS = 4                                   # the packets built here use a 4-bit peer field (header value 3)


class BitWriter:
    """Packs unsigned values into bytes, least significant bit first, as the game does."""

    def __init__(self):
        self._value = 0
        self.bit_count = 0

    def write(self, value: int, bit_width: int) -> 'BitWriter':
        assert 0 <= value < (1 << bit_width) or bit_width == 0, (value, bit_width)
        self._value |= value << self.bit_count
        self.bit_count += bit_width
        return self

    def to_bytes(self) -> bytes:
        return self._value.to_bytes((self.bit_count + 7) // 8, 'little')


def write_gap(writer: BitWriter, gap: int) -> None:
    """A gap in the state block's property lists: 5-bit chunks, 4 value bits each, bit 4 = more follows."""
    while True:
        chunk = gap & 15
        gap >>= 4
        writer.write(chunk | (16 if gap else 0), 5)
        if not gap:
            return


def write_time(writer: BitWriter, time: int) -> None:
    while True:
        chunk = time & 0x7fffff
        time >>= 23
        writer.write(chunk | ((1 << 23) if time else 0), 24)
        if not time:
            return


def write_state_block(writer: BitWriter, time: int = 0, agent_updates: Sequence[Tuple[int, int]] = (), player_updates: Sequence[Tuple[int, int]] = ()) -> None:
    """agent_updates are (index, value) pairs, ascending; the widths are those of the property the index selects."""
    from nwkills.packets.state_block import PROPERTY_BIT_WIDTHS, PROPERTIES_PER_AGENT
    write_time(writer, time)
    writer.write(0, 1)
    previous = -1
    for index, value in agent_updates:
        write_gap(writer, index - previous)
        writer.write(value, PROPERTY_BIT_WIDTHS[index % PROPERTIES_PER_AGENT])
        previous = index
    write_gap(writer, 0)
    previous = -1
    for index, value in player_updates:
        write_gap(writer, index - previous)
        writer.write(value, 13 if index % 2 == 0 else 10)
        previous = index
    write_gap(writer, 0)


def build_packet(messages: Sequence[Tuple[int, Sequence[Tuple[int, int]]]], state_block: Optional[dict] = None, queued: bool = False) -> bytes:
    """A server packet. messages: (type, [(value, bit_width), ...]) with the fields after the peer field (the peer is 0, 4 bits)."""
    writer = BitWriter()
    writer.write(0, 11).write(0, 13).write(0, 16).write(0, 16)                   # length (patched below), padding, sequence, ack
    writer.write(0 if queued else len(messages) + 1, 8)
    writer.write(PEER_FIELD_BITS - 1, 4)
    for message_type, fields in messages:
        writer.write(message_type, 6).write(0, PEER_FIELD_BITS)
        for value, bit_width in fields:
            writer.write(value, bit_width)
    if state_block is not None:
        write_state_block(writer, **state_block)
    payload = bytearray(writer.to_bytes())
    payload[0] = len(payload) & 0xff
    payload[1] = (payload[1] & 0xf8) | (len(payload) >> 8)
    if queued:
        payload = payload[:7] + b'\x00' + payload[7:]            # a queued packet carries one extra byte 7 that the game removes
    return bytes(payload)


def game_payload(length: int, filler: int = 0) -> bytes:
    """A payload whose first 11 bits equal its length, as the server flow finder expects."""
    return struct.pack('<H', length) + bytes([filler % 251]) * (length - 2)


def ethernet_udp_frame(source: str, source_port: int, destination: str, destination_port: int, payload: bytes) -> bytes:
    udp = struct.pack('>HHHH', source_port, destination_port, 8 + len(payload), 0) + payload
    ip = struct.pack('>BBHHHBBH4s4s', 0x45, 0, 20 + len(udp), 0, 0, 64, 17, 0, bytes(map(int, source.split('.'))), bytes(map(int, destination.split('.')))) + udp
    return b'\0' * 12 + b'\x08\x00' + ip
