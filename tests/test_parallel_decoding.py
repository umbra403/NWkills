import unittest
import support
from nwkills.packets.packet_decoder import PacketDecoder
from nwkills.packets.parallel_decoding import ParallelPacketDecoder
from nwkills.packets.server_profile import NWE_PROFILE


class ParallelPacketDecoderTest(unittest.TestCase):
    def setUp(self):
        self.jobs = [(i, i * 0.5, support.build_packet([(12, [(i % 1000, 10)])], dict(time=i))) for i in range(70)]

    def test_results_match_a_single_process_decode_and_keep_the_job_order(self):
        decoded = ParallelPacketDecoder(NWE_PROFILE, 2).decode_all(self.jobs)
        single = PacketDecoder(NWE_PROFILE)
        self.assertEqual([packet.to_legacy_record() for packet in decoded], [single.decode(*job).to_legacy_record() for job in self.jobs])

    def test_progress_is_reported_for_every_packet(self):
        reported = []
        ParallelPacketDecoder(NWE_PROFILE, 2).decode_all(self.jobs, lambda done, total: reported.append((done, total)))
        self.assertEqual((reported[0], reported[-1], len(reported)), ((0, 70), (69, 70), 70))

    def test_no_jobs_give_no_packets(self):
        self.assertEqual(ParallelPacketDecoder(NWE_PROFILE, 1).decode_all([]), [])


if __name__ == '__main__':
    unittest.main()
