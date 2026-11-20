import unittest
import support
from nwkills import guilogic
from nwkills.packets.server_profile import NWE_PROFILE


class PacketSummarizerTest(unittest.TestCase):
    def setUp(self):
        self.summarizer = guilogic.PacketSummarizer(NWE_PROFILE)

    def test_lists_the_message_types_of_a_packet(self):
        summary = self.summarizer.summarize(support.build_packet([(12, [(1, 10)]), (49, [])], dict(time=1)))
        self.assertEqual((summary['queued'], summary['n'], [message.message_type for message in summary['msgs']]), (False, 2, [12, 49]))
        self.assertIn('12', summary['types'])

    def test_a_queued_packet_is_read_without_its_queue_byte(self):
        summary = self.summarizer.summarize(support.build_packet([(12, [(1, 10)])], dict(time=1), queued=True))
        self.assertTrue(summary['queued'])

    def test_a_packet_without_messages_has_no_types(self):
        summary = self.summarizer.summarize(support.build_packet([], dict(time=1)))
        self.assertEqual((summary['n'], summary['msgs'], summary['types']), (0, [], ''))

    def test_a_damaged_packet_gives_an_empty_summary(self):
        self.assertEqual(self.summarizer.summarize(b'\x01\x00')['msgs'], [])


if __name__ == '__main__':
    unittest.main()
