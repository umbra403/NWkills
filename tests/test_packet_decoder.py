import unittest
import support
from nwkills.packets.packet_decoder import BoundaryMessage, DecodedPacket, PacketDecoder, ScriptEvent
from nwkills.packets.server_profile import NWE_PROFILE


def decode(messages, state_block=None, queued=False, keep_all=False):
    payload = support.build_packet(messages, state_block=state_block, queued=queued)
    return PacketDecoder(NWE_PROFILE, keep_all).decode(7, 1.5, payload)


class PacketDecoderTest(unittest.TestCase):
    def test_a_packet_with_only_a_state_block_is_clean(self):
        packet = decode([], dict(time=100))
        self.assertTrue(packet.is_clean and packet.reached_state_block_end)
        self.assertEqual((packet.packet_index, packet.timestamp, packet.state_block.time), (7, 1.5, 100))

    def test_messages_and_state_block_are_both_read(self):
        packet = decode([(12, [(1, 10)]), (49, [])], dict(time=5))
        self.assertEqual(packet.declared_message_count, 2)
        self.assertTrue(packet.is_clean)

    def test_a_cut_off_state_block_is_reported(self):
        packet = decode([(49, [])], dict(time=5, agent_updates=[(7, 9)]))
        truncated = PacketDecoder(NWE_PROFILE).decode(0, 0.0, support.build_packet([(49, [])], dict(time=5, agent_updates=[(7, 9)]))[:-3])
        self.assertFalse(packet.error)
        self.assertIn('tail', truncated.error)
        self.assertFalse(truncated.is_clean)

    def test_a_queued_packet_is_marked_and_has_no_state_block(self):
        packet = decode([(49, [])], dict(time=5), queued=True)
        self.assertTrue(packet.was_queued)
        self.assertEqual(packet.error, 'queued')
        self.assertIsNone(packet.state_block)

    def test_remove_queue_byte_drops_byte_seven(self):
        self.assertEqual(PacketDecoder.remove_queue_byte(bytes(range(10))), bytes([0, 1, 2, 3, 4, 5, 6, 8, 9]))

    def test_only_useful_agent_properties_are_kept_by_default(self):
        updates = [(1 * 29 + 3, 1), (1 * 29 + 7, 200)]
        self.assertEqual([update.property_number for update in decode([], dict(time=1, agent_updates=updates)).state_block.agent_updates], [7])
        self.assertEqual([update.property_number for update in decode([], dict(time=1, agent_updates=updates), keep_all=True).state_block.agent_updates], [3, 7])

    def test_player_updates_are_always_kept(self):
        self.assertEqual(len(decode([], dict(time=1, player_updates=[(0, 12)])).state_block.player_updates), 1)

    def test_a_round_border_message_is_collected(self):
        packet = decode([(0, [(0, 6), (0, 16), (0, 16), (0, 16)])], dict(time=1))
        self.assertTrue(packet.error is None or isinstance(packet.error, str))

    def test_a_same_map_reset_is_a_border(self):
        packet = decode([(41, [])], dict(time=1))
        self.assertEqual(packet.round_boundaries, [BoundaryMessage('reset', 0)])

    def test_a_mount_link_gives_horse_and_rider(self):
        packet = decode([(30, [(6, 10), (3, 10)])], dict(time=1))
        self.assertEqual(packet.mount_links, [(5, 2)])

    def test_server_text_is_collected_as_printable_characters(self):
        text = [(0, 7), (2, 16), (ord('h'), 8), (ord('i'), 8)]
        self.assertEqual(decode([(39, text)], dict(time=1)).server_text_lines, ['hi'])

    def test_the_legacy_record_has_the_keys_later_stages_read(self):
        record = decode([(49, [])], dict(time=9)).to_legacy_record()
        self.assertEqual(sorted(record), sorted(['i', 't', 'L', 'n', 'msgs', 'joins', 'links', 'ev', 'txt', 'rst', 'bnd', 'tail', 'err', 'q']))
        self.assertEqual((record['i'], record['t'], record['n'], record['q']), (7, 1.5, 1, False))
        self.assertEqual(record['tail']['time'], 9)

    def test_the_legacy_record_of_a_packet_without_a_state_block_has_no_tail(self):
        record = decode([(49, [])], dict(time=9), queued=True).to_legacy_record()
        self.assertIsNone(record['tail'])

    def test_a_decoded_packet_without_a_state_block_never_reached_its_end(self):
        self.assertFalse(DecodedPacket(0, 0.0, 80, 0).reached_state_block_end)


class ScriptEventTest(unittest.TestCase):
    def test_a_script_event_with_the_wrapper_value_is_collected(self):
        packet = decode([(36, [(107, 7), (321, 32), (45, 32)])], dict(time=1))
        self.assertEqual(packet.script_events, [ScriptEvent(36, 321, [45])])

    def test_a_script_event_without_the_wrapper_is_ignored(self):
        self.assertEqual(decode([(36, [(1, 7), (321, 32), (45, 32)])], dict(time=1)).script_events, [])


if __name__ == '__main__':
    unittest.main()
