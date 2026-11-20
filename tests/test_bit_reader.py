import unittest
import support
from nwkills.packets.bit_reader import BitReader


class BitReaderTest(unittest.TestCase):
    def test_total_bits_counts_every_bit_of_the_buffer(self):
        self.assertEqual(BitReader(b'\x00\x00\x00').total_bits, 24)

    def test_reads_least_significant_bit_first(self):
        reader = BitReader(bytes([0b10110001]))
        self.assertEqual(reader.read(0, 1), 1)
        self.assertEqual(reader.read(0, 4), 0b0001)
        self.assertEqual(reader.read(4, 4), 0b1011)

    def test_reads_values_that_cross_byte_borders(self):
        writer = support.BitWriter().write(5, 3).write(0x1ABC, 13).write(77, 9)
        reader = BitReader(writer.to_bytes())
        self.assertEqual((reader.read(0, 3), reader.read(3, 13), reader.read(16, 9)), (5, 0x1ABC, 77))

    def test_returns_none_when_the_buffer_ends_first(self):
        reader = BitReader(b'\xff')
        self.assertIsNone(reader.read(4, 5))
        self.assertEqual(reader.read(4, 4), 15)

    def test_zero_bits_read_as_zero_even_past_the_end(self):
        self.assertEqual(BitReader(b'').read(100, 0), 0)


if __name__ == '__main__':
    unittest.main()
