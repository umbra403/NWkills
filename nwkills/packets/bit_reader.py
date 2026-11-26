"""Reading values of any bit width out of a byte buffer."""
from typing import Optional


class BitReader:
    """Reads unsigned integers from a byte buffer. Bits are numbered from 0, the least significant bit of the first byte first,
    which is the order the game writes its packets in."""

    def __init__(self, buffer: bytes):
        self._buffer = buffer
        self._total_bits = len(buffer) * 8

    @property
    def total_bits(self) -> int:
        return self._total_bits

    def read(self, bit_position: int, bit_count: int) -> Optional[int]:
        """The unsigned value of `bit_count` bits starting at `bit_position`, or None when the buffer ends before those bits do."""
        if bit_count == 0:
            return 0
        end_position = bit_position + bit_count
        if end_position > self._total_bits:
            return None
        first_byte = bit_position >> 3
        end_byte = (end_position + 7) >> 3
        shifted_value = int.from_bytes(self._buffer[first_byte:end_byte], 'little') >> (bit_position & 7)
        return shifted_value & ((1 << bit_count) - 1)
