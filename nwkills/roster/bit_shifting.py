"""Names are sent as plain bytes at any bit offset: looking for them means looking at the payload shifted by 0 to 7 bits."""

PRINTABLE_ASCII = bytes(range(0x20, 0x7f))
BIT_OFFSETS = range(8)


def shift_right(payload: bytes, bit_count: int) -> bytes:
    """The payload as a little-endian number shifted right by `bit_count` bits, with the same length."""
    if bit_count == 0:
        return payload
    return (int.from_bytes(payload, 'little') >> bit_count).to_bytes(len(payload), 'little')


def is_printable_ascii(text_bytes: bytes) -> bool:
    return not text_bytes.translate(None, PRINTABLE_ASCII)
