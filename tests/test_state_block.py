import unittest
import support
from nwkills.packets.message_reader import FIRST_MESSAGE_BIT
from nwkills.packets.state_block import PropertyUpdate, StateBlockParser, PROPERTIES_PER_AGENT


def packet_with_state_block(**state_block):
    return support.build_packet([], state_block=state_block)


class StateBlockParserTest(unittest.TestCase):
    def setUp(self):
        self.parser = StateBlockParser()

    def test_reads_the_time_of_an_empty_block(self):
        packet = packet_with_state_block(time=12345)
        block = self.parser.parse(packet, FIRST_MESSAGE_BIT)
        self.assertEqual((block.time, block.agent_updates, block.player_updates), (12345, [], []))

    def test_a_long_time_uses_a_second_chunk(self):
        block = self.parser.parse(packet_with_state_block(time=(5 << 23) + 77), FIRST_MESSAGE_BIT)
        self.assertEqual(block.time, (5 << 23) + 77)

    def test_reads_agent_properties_by_index(self):
        updates = [(1 * PROPERTIES_PER_AGENT + 7, 300), (40 * PROPERTIES_PER_AGENT + 6, 5)]
        block = self.parser.parse(packet_with_state_block(time=1, agent_updates=updates), FIRST_MESSAGE_BIT)
        self.assertEqual(block.agent_updates, [PropertyUpdate(1, 7, 300), PropertyUpdate(40, 6, 5)])

    def test_reads_player_score_and_ping(self):
        block = self.parser.parse(packet_with_state_block(time=1, player_updates=[(6, 4000), (7, 55)]), FIRST_MESSAGE_BIT)
        self.assertEqual(block.player_updates, [PropertyUpdate(3, 0, 4000), PropertyUpdate(3, 1, 55)])

    def test_the_end_bit_is_where_the_block_stops(self):
        packet = packet_with_state_block(time=1, agent_updates=[(7, 9)])
        block = self.parser.parse(packet, FIRST_MESSAGE_BIT)
        self.assertLess(len(packet) * 8 - block.end_bit, 8)

    def test_a_block_cut_short_gives_none(self):
        packet = packet_with_state_block(time=1, agent_updates=[(7, 9)])
        self.assertIsNone(self.parser.parse(packet[:-3], FIRST_MESSAGE_BIT))

    def test_a_start_past_the_end_gives_none(self):
        self.assertIsNone(self.parser.parse(b'\x00' * 10, 200))

    def test_a_time_that_never_ends_gives_none(self):
        self.assertIsNone(self.parser.parse(b'\xff' * 100, 0))

    def test_the_optional_second_time_block_is_skipped(self):
        writer = support.BitWriter()
        support.write_time(writer, 99)
        writer.write(1, 1)
        support.write_time(writer, 5)
        for _ in range(3):
            writer.write(0, 17)
        writer.write(0, 28)
        support.write_gap(writer, 0)
        support.write_gap(writer, 0)
        block = self.parser.parse(writer.to_bytes() + b'\0', 0)
        self.assertEqual((block.time, block.agent_updates), (99, []))


if __name__ == '__main__':
    unittest.main()
