import unittest
import support
from nwkills.packets.packet_decoder import PacketDecoder
from nwkills.packets.profile_calibrator import ProfileCalibrator
from nwkills.packets.server_profile import NW_PROFILE, NWE_PROFILE

UNUSED_LOG = lambda text: None


def player_state_packet(troop_bits):
    """A packet of two messages whose first has type 15 (8-bit field, troop id), followed by a state block."""
    return support.build_packet([(15, [(3, 8), (5, troop_bits)]), (15, [(9, 8), (300 % (1 << troop_bits), troop_bits)])], dict(time=10, player_updates=[(0, 7)]))


class ProfileCalibratorTest(unittest.TestCase):
    def test_without_samples_the_starting_profile_stays(self):
        self.assertEqual(ProfileCalibrator().calibrate([], UNUSED_LOG), NWE_PROFILE)

    def test_the_starting_profile_can_be_chosen(self):
        self.assertEqual(ProfileCalibrator(starting_profile=NW_PROFILE).calibrate([], UNUSED_LOG), NW_PROFILE)

    def test_the_profile_found_reads_the_sample_packets_to_their_end(self):
        for true_width in (4, 9, 12):
            packets = [player_state_packet(true_width)] * 30
            profile = ProfileCalibrator().calibrate(packets, UNUSED_LOG)
            self.assertTrue(all(PacketDecoder(profile).decode(0, 0.0, packet).is_clean for packet in packets), true_width)

    def test_the_profile_found_reads_the_sample_packets_to_their_end(self):
        for true_width in (4, 9, 12):
            packets = [player_state_packet(true_width)] * 30
            profile = ProfileCalibrator().calibrate(packets, UNUSED_LOG)
            self.assertTrue(all(PacketDecoder(profile).decode(0, 0.0, packet).is_clean for packet in packets), true_width)

    def test_the_sample_count_per_type_is_limited(self):
        logged = []
        ProfileCalibrator(samples_per_type=3).calibrate([player_state_packet(10)] * 50, logged.append)
        self.assertIn('/3 clean', logged[0])

    def test_short_packets_and_other_message_counts_are_not_samples(self):
        logged = []
        ProfileCalibrator().calibrate([b'\x00' * 8, support.build_packet([(49, [])] * 5, dict(time=1))], logged.append)
        self.assertEqual(logged, [])


if __name__ == '__main__':
    unittest.main()
