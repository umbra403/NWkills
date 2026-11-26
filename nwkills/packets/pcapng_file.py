"""Reading and writing pcapng capture files."""
import mmap
import os
import struct
from typing import Iterable, Iterator, NamedTuple

SECTION_HEADER_BLOCK = 0x0A0D0D0A
INTERFACE_DESCRIPTION_BLOCK = 1
ENHANCED_PACKET_BLOCK = 6
BYTE_ORDER_MAGIC = 0x1A2B3C4D
TIMESTAMP_RESOLUTION_OPTION = 9
END_OF_OPTIONS = 0
DEFAULT_TIMESTAMP_RESOLUTION = 6          # microseconds, the pcapng default when the option is missing
ENHANCED_PACKET_HEADER_BYTES = 28         # block type, block length, then five 32-bit fields, before the packet data
MINIMUM_BLOCK_BYTES = 12


class CapturedFrame(NamedTuple):
    """One captured link-layer frame."""
    timestamp_seconds: float
    link_type: int
    data: bytes


class PcapngReader:
    """Reads the frames of a pcapng file through a memory map, so a capture of several GB does not have to fit in memory."""

    def read_frames(self, path: str) -> Iterator[CapturedFrame]:
        """Yield every frame in file order. A damaged or cut-off tail ends the iteration quietly."""
        if os.path.getsize(path) < MINIMUM_BLOCK_BYTES:
            return
        with open(path, 'rb') as capture_file:
            file_map = mmap.mmap(capture_file.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                yield from self._read_blocks(file_map)
            finally:
                file_map.close()

    def _read_blocks(self, file_map) -> Iterator[CapturedFrame]:
        offset, byte_order, interfaces, file_size = 0, '<', [], len(file_map)
        while offset + MINIMUM_BLOCK_BYTES <= file_size:
            block_type = struct.unpack_from('<I', file_map, offset)[0]
            if block_type == SECTION_HEADER_BLOCK:
                byte_order_magic = struct.unpack_from('<I', file_map, offset + 8)[0]
                byte_order = '<' if byte_order_magic == BYTE_ORDER_MAGIC else '>'
            block_type, block_length = struct.unpack_from(byte_order + 'II', file_map, offset)
            if block_length < MINIMUM_BLOCK_BYTES or offset + block_length > file_size:
                break
            if block_type == INTERFACE_DESCRIPTION_BLOCK:
                body = file_map[offset + 8: offset + block_length - 4]
                interfaces.append(self._read_interface(body, byte_order))
            elif block_type == ENHANCED_PACKET_BLOCK:
                yield self._read_packet(file_map, offset, byte_order, interfaces)
            offset += block_length

    @staticmethod
    def _read_interface(body: bytes, byte_order: str):
        """-> (link type, timestamp resolution) of an interface description block."""
        link_type = struct.unpack_from(byte_order + 'HHI', body, 0)[0]
        timestamp_resolution = DEFAULT_TIMESTAMP_RESOLUTION
        option_offset = 8
        while option_offset + 4 <= len(body):
            option_code, option_length = struct.unpack_from(byte_order + 'HH', body, option_offset)
            if option_code == END_OF_OPTIONS:
                break
            if option_code == TIMESTAMP_RESOLUTION_OPTION:
                timestamp_resolution = body[option_offset + 4]
            option_offset += 4 + ((option_length + 3) // 4) * 4
        return link_type, timestamp_resolution

    @staticmethod
    def _read_packet(file_map, offset: int, byte_order: str, interfaces) -> CapturedFrame:
        interface_id, time_high, time_low, captured_length, _original_length = struct.unpack_from(byte_order + 'IIIII', file_map, offset + 8)
        link_type, timestamp_resolution = interfaces[interface_id]
        ticks_per_second = 2 ** (timestamp_resolution & 0x7f) if timestamp_resolution & 0x80 else 10 ** timestamp_resolution
        data_start = offset + ENHANCED_PACKET_HEADER_BYTES
        return CapturedFrame((time_high << 32 | time_low) / ticks_per_second, link_type, bytes(file_map[data_start: data_start + captured_length]))


class PcapngWriter:
    """Writes frames as a little-endian pcapng file with microsecond timestamps."""

    def write_frames(self, path: str, frames: Iterable[CapturedFrame]) -> None:
        interface_index_by_link_type = {}
        with open(path, 'wb') as output:
            output.write(struct.pack('<IIIHHqI', SECTION_HEADER_BLOCK, 28, BYTE_ORDER_MAGIC, 1, 0, -1, 28))
            for frame in frames:
                if frame.link_type not in interface_index_by_link_type:
                    interface_index_by_link_type[frame.link_type] = len(interface_index_by_link_type)
                    output.write(struct.pack('<IIHHII', INTERFACE_DESCRIPTION_BLOCK, 20, frame.link_type, 0, 262144, 20))
                self._write_packet(output, frame, interface_index_by_link_type[frame.link_type])

    @staticmethod
    def _write_packet(output, frame: CapturedFrame, interface_index: int) -> None:
        microseconds = int(round(frame.timestamp_seconds * 1e6))
        padding = (-len(frame.data)) % 4
        block_length = 32 + len(frame.data) + padding
        output.write(struct.pack('<IIIIIII', ENHANCED_PACKET_BLOCK, block_length, interface_index, microseconds >> 32, microseconds & 0xffffffff,
                                 len(frame.data), len(frame.data)))
        output.write(frame.data)
        output.write(b'\0' * padding)
        output.write(struct.pack('<I', block_length))
