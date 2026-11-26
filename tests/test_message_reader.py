import unittest
import support
from nwkills.packets.message_reader import FIRST_MESSAGE_BIT, ServerMessageReader
from nwkills.packets.server_profile import NWE_PROFILE


def string_fields(text):
    return [(len(text), 16)] + [(ord(character), 8) for character in text]


class ServerMessageReaderTest(unittest.TestCase):
    def setUp(self):
        self.reader = ServerMessageReader(NWE_PROFILE)

    def test_reads_fixed_layout_messages_in_order(self):
        packet = support.build_packet([(12, [(77, 10)]), (49, []), (14, [(5, 8), (2, 3)])], state_block=dict())
        result = self.reader.read(packet)
        self.assertFalse(result.ran_out_of_data)
        self.assertEqual([message.message_type for message in result.messages], [12, 49, 14])
        self.assertEqual([field.value for field in result.messages[0].fields], [0, 77])
        self.assertEqual(result.messages[0].start_bit, FIRST_MESSAGE_BIT)
        self.assertEqual(result.messages[0].end_bit, result.messages[1].start_bit)
        self.assertEqual(result.end_bit, result.messages[2].end_bit)

    def test_reads_a_chat_text(self):
        packet = support.build_packet([(39, [(0, 7)] + string_fields('hello'))], state_block=dict())
        message = self.reader.read(packet).messages[0]
        self.assertEqual(''.join(chr(field.value) for field in message.fields if field.bit_width == 8), 'hello')

    def test_a_string_over_the_cap_is_not_read(self):
        packet = support.build_packet([(39, [(0, 7), (400, 16)]), (49, [])], state_block=dict())
        self.assertEqual([message.message_type for message in self.reader.read(packet).messages], [39, 49])

    def test_every_six_bit_message_type_has_a_reader(self):
        from nwkills.packets.message_layouts import KNOWN_MESSAGE_TYPES
        self.assertEqual(KNOWN_MESSAGE_TYPES, frozenset(range(64)))      # so UnknownMessageType only guards against a future change

    def test_a_packet_that_ends_inside_a_message_is_reported(self):
        packet = support.build_packet([(14, [(5, 8), (2, 3)])])
        result = self.reader.read(packet[:9])
        self.assertTrue(result.ran_out_of_data)
        self.assertEqual(result.messages, [])

    def test_a_packet_with_no_messages_ends_at_the_first_message_bit(self):
        packet = support.build_packet([], state_block=dict())
        result = self.reader.read(packet)
        self.assertEqual((result.messages, result.end_bit), ([], FIRST_MESSAGE_BIT))

    def test_the_agent_spawn_extra_bits_follow_the_profile(self):
        spawn = [(1, 10), (0, 8), (0, 11), (0, 3), (0, 8), (0, 32)] + [(0, 12)] * 11 + [(0, 10), (0, 10), (0, 51), (0, 10), (0, 7), (0, 7), (0, 7), (0, 1)]
        with_extra = support.build_packet([(5, spawn + [(0, 9)])], state_block=dict())
        without_extra = support.build_packet([(5, spawn)], state_block=dict())
        self.assertEqual(self.reader.read(with_extra).messages[0].end_bit - self.reader.read(without_extra).messages[0].end_bit, 0)
        no_extra_reader = ServerMessageReader(NWE_PROFILE.with_values(agent_spawn_extra_bits=0))
        self.assertEqual(self.reader.read(with_extra).messages[0].end_bit - 9, no_extra_reader.read(with_extra).messages[0].end_bit)


if __name__ == '__main__':
    unittest.main()
