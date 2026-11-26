import unittest
import support
from nwkills.packets.server_profile import NWE_PROFILE
from nwkills.viewlogic import (HexDump, PacketRowFormatter, PacketSummarizer, PacketSummary, PacketSummaryCache, format_message_types, is_queued_payload,
                               packet_index_at_time)

PLAIN_PAYLOAD = b'\x00' * 7 + b'\x01'              # no queue marker, no messages
QUEUED_PAYLOAD = b'\x00' * 8                        # byte 7 is zero: queued


class QueuedPayloadTest(unittest.TestCase):
    def test_a_zero_in_byte_seven_marks_a_queued_packet(self):
        self.assertTrue(is_queued_payload(QUEUED_PAYLOAD))
        self.assertFalse(is_queued_payload(PLAIN_PAYLOAD))

    def test_a_short_payload_is_not_queued(self):
        self.assertFalse(is_queued_payload(b'\x00' * 7))
        self.assertFalse(is_queued_payload(b''))


class MessageTypeTextTest(unittest.TestCase):
    def test_repeated_types_are_counted(self):
        self.assertEqual(format_message_types([5, 5, 6]), '5×2 6')

    def test_types_are_sorted(self):
        self.assertEqual(format_message_types([12, 5]), '5 12')

    def test_no_types_give_no_text(self):
        self.assertEqual(format_message_types([]), '')


class PacketSummaryTest(unittest.TestCase):
    def test_the_empty_summary_has_no_messages(self):
        self.assertEqual(PacketSummary.empty(), PacketSummary(False, 0, [], ''))


class PacketSummarizerTest(unittest.TestCase):
    def setUp(self):
        self.summarizer = PacketSummarizer(NWE_PROFILE)

    def test_lists_the_message_types_of_a_packet(self):
        summary = self.summarizer.summarize(support.build_packet([(12, [(1, 10)]), (49, [])], dict(time=1)))
        self.assertEqual((summary.queued, summary.message_count, [message.message_type for message in summary.messages]), (False, 2, [12, 49]))
        self.assertIn('12', summary.type_text)

    def test_a_queued_packet_is_read_without_its_queue_byte(self):
        summary = self.summarizer.summarize(support.build_packet([(12, [(1, 10)])], dict(time=1), queued=True))
        self.assertTrue(summary.queued)

    def test_a_packet_without_messages_has_no_types(self):
        summary = self.summarizer.summarize(support.build_packet([], dict(time=1)))
        self.assertEqual((summary.message_count, summary.messages, summary.type_text), (0, [], ''))

    def test_a_damaged_packet_gives_an_empty_summary(self):
        self.assertEqual(self.summarizer.summarize(b'\x01\x00').messages, [])

    def test_a_payload_too_short_for_a_count_has_no_messages(self):
        self.assertEqual(self.summarizer.summarize(b'').message_count, 0)


class FailingSummarizer:
    def summarize(self, payload):
        raise ValueError('cannot decode')


class PacketSummaryCacheTest(unittest.TestCase):
    ITEMS = [(0.0, PLAIN_PAYLOAD), (1.0, QUEUED_PAYLOAD), (2.0, PLAIN_PAYLOAD)]

    def cache(self, summarizer=None):
        return PacketSummaryCache(list(self.ITEMS), summarizer or PacketSummarizer(NWE_PROFILE))

    def test_the_length_is_the_number_of_packets(self):
        self.assertEqual(len(self.cache()), 3)

    def test_nothing_is_decoded_until_asked(self):
        cache = self.cache()
        self.assertEqual((cache.cached_count, cache.peek(0)), (0, None))

    def test_a_summary_is_decoded_once_and_kept(self):
        cache = self.cache()
        first = cache.summary(1)
        self.assertTrue(first.queued)
        self.assertIs(cache.summary(1), first)
        self.assertIs(cache.peek(1), first)
        self.assertEqual(cache.cached_count, 1)

    def test_fill_all_decodes_every_packet_and_reports_the_end(self):
        cache, reports = self.cache(), []
        cache.fill_all(lambda: False, lambda done, total: reports.append((done, total)))
        self.assertEqual(cache.cached_count, 3)
        self.assertEqual(reports[0], (0, 3))
        self.assertEqual(reports[-1], (3, 3))

    def test_fill_all_stops_when_asked(self):
        cache = self.cache()
        cache.fill_all(lambda: True, lambda done, total: None)
        self.assertEqual(cache.cached_count, 0)

    def test_fill_all_keeps_what_was_decoded_already(self):
        cache = self.cache()
        kept = cache.summary(2)
        cache.fill_all(lambda: False, lambda done, total: None)
        self.assertIs(cache.peek(2), kept)

    def test_a_packet_that_cannot_be_decoded_gets_an_empty_summary(self):
        cache = self.cache(FailingSummarizer())
        cache.fill_all(lambda: False, lambda done, total: None)
        self.assertEqual(cache.peek(0), PacketSummary.empty())

    def test_progress_is_reported_every_five_hundred_packets(self):
        cache, reports = PacketSummaryCache([(0.0, PLAIN_PAYLOAD)] * 1001, PacketSummarizer(NWE_PROFILE)), []
        cache.fill_all(lambda: False, lambda done, total: reports.append(done))
        self.assertEqual(reports, [0, 500, 1000, 1001])


class PacketRowFormatterTest(unittest.TestCase):
    SUMMARY = PacketSummary(False, 2, [], '5×2')

    def test_the_headers(self):
        self.assertEqual(PacketRowFormatter.HEADERS, ['No.', 'Time (s)', 'Length', 'Flags', 'Msgs', 'Message types'])

    def test_flags_text_names_a_queued_packet(self):
        self.assertEqual((PacketRowFormatter.flags_text(QUEUED_PAYLOAD), PacketRowFormatter.flags_text(PLAIN_PAYLOAD)), ('queued', ''))

    def test_each_column_has_its_text(self):
        texts = [PacketRowFormatter.cell_text(column, 4, 1.5, QUEUED_PAYLOAD, self.SUMMARY) for column in range(6)]
        self.assertEqual(texts, ['5', '1.500000', '8', 'queued', '2', '5×2'])

    def test_the_first_four_columns_need_no_summary(self):
        self.assertEqual(PacketRowFormatter.cell_text(0, 0, 0.0, PLAIN_PAYLOAD, None), '1')

    def test_the_search_text_holds_number_flags_length_and_types(self):
        self.assertEqual(PacketRowFormatter.search_text(0, QUEUED_PAYLOAD, self.SUMMARY), '1 queued 8 5×2')

    def test_the_search_text_without_a_summary_has_no_types(self):
        self.assertEqual(PacketRowFormatter.search_text(2, PLAIN_PAYLOAD, None), '3  8 ')


class HexDumpTest(unittest.TestCase):
    def test_a_line_has_the_offset_the_bytes_and_the_text(self):
        self.assertEqual(HexDump.format(b'AB'), '0000  ' + '41 42'.ljust(47) + '  AB')

    def test_unprintable_bytes_are_dots(self):
        self.assertTrue(HexDump.format(b'\x00\xff').endswith('  ..'))

    def test_long_data_wraps_at_the_width(self):
        lines = HexDump.format(bytes(range(40))).split('\n')
        self.assertEqual((len(lines), lines[1][:4], lines[2][:4]), (3, '0010', '0020'))

    def test_the_width_can_be_changed(self):
        self.assertEqual(len(HexDump.format(bytes(6), width=4).split('\n')), 2)

    def test_no_data_gives_no_lines(self):
        self.assertEqual(HexDump.format(b''), '')


class PacketIndexAtTimeTest(unittest.TestCase):
    TIMES = [0.0, 1.0, 2.0]

    def test_the_packet_at_or_just_after_the_time_is_found(self):
        self.assertEqual(packet_index_at_time(self.TIMES, 1.5), 2)
        self.assertEqual(packet_index_at_time(self.TIMES, 1.0), 1)

    def test_a_small_lead_is_allowed(self):
        self.assertEqual(packet_index_at_time(self.TIMES, 1.03), 1)

    def test_a_time_after_the_last_packet_gives_the_last(self):
        self.assertEqual(packet_index_at_time([0.0, 1.0], 99), 1)

    def test_a_time_before_the_first_gives_the_first(self):
        self.assertEqual(packet_index_at_time(self.TIMES, -5), 0)


if __name__ == '__main__':
    unittest.main()
