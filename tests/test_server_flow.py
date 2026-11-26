import unittest
import support
from nwkills.packets.pcapng_file import CapturedFrame
from nwkills.packets.server_flow import FlowKey, GameServerFlowFinder

SERVER, CLIENT = '10.0.0.5', '192.168.0.2'


def frame(source, source_port, destination, destination_port, payload, timestamp=1.0):
    return CapturedFrame(timestamp, 1, support.ethernet_udp_frame(source, source_port, destination, destination_port, payload))


def game_capture(packet_count=120):
    frames = []
    for i in range(packet_count):
        frames.append(frame(SERVER, 7240, CLIENT, 5555, support.game_payload(40 + i % 7, i), 1000 + i * 0.01))
        frames.append(frame(CLIENT, 5555, SERVER, 7240, support.game_payload(20, i), 1000 + i * 0.01))
        frames.append(frame('8.8.8.8', 443, CLIENT, 6000, b'x' * 900, 1000 + i * 0.01))        # a bigger flow without length headers
    return frames


class FlowKeyTest(unittest.TestCase):
    def test_reversed_direction_swaps_server_and_client(self):
        key = FlowKey('1.1.1.1', 10, '2.2.2.2', 20)
        self.assertEqual(key.reversed_direction(), ('2.2.2.2', 20, '1.1.1.1', 10))


class GameServerFlowFinderTest(unittest.TestCase):
    def test_finds_the_flow_whose_packets_start_with_their_length(self):
        key = GameServerFlowFinder().find_flow_key(game_capture())
        self.assertEqual(key, FlowKey(SERVER, 7240, CLIENT, 5555))

    def test_a_wanted_port_limits_the_search_to_that_server_port(self):
        self.assertIsNone(GameServerFlowFinder(wanted_server_port=9999).find_flow_key(game_capture()))
        self.assertEqual(GameServerFlowFinder(wanted_server_port=7240).find_flow_key(game_capture()).server_port, 7240)

    def test_a_capture_without_a_game_flow_gives_none(self):
        noise = [frame('1.1.1.1', 53, CLIENT, 6001, b'dns' * 10) for _ in range(100)]
        self.assertIsNone(GameServerFlowFinder().find_flow_key(noise))

    def test_too_few_packets_are_not_a_flow(self):
        self.assertIsNone(GameServerFlowFinder().find_flow_key(game_capture(10)))

    def test_has_length_header_compares_the_first_11_bits_with_the_length(self):
        self.assertTrue(GameServerFlowFinder.has_length_header(support.game_payload(300)))
        self.assertFalse(GameServerFlowFinder.has_length_header(b'\x05\x00' + b'x' * 20))

    def test_parse_datagram_ignores_frames_that_cannot_be_read(self):
        finder = GameServerFlowFinder()
        self.assertIsNone(finder.parse_datagram(CapturedFrame(1.0, 1, b'\x00' * 3)))
        self.assertIsNone(finder.parse_datagram(CapturedFrame(1.0, 999, b'\x00' * 40)))
        self.assertEqual(finder.parse_datagram(game_capture(1)[0]).source_port, 7240)

    def test_collect_payloads_gives_the_flow_in_time_order(self):
        frames = list(reversed(game_capture(60)))
        key = FlowKey(SERVER, 7240, CLIENT, 5555)
        payloads = GameServerFlowFinder().collect_payloads(frames, key)
        self.assertEqual(len(payloads), 60)
        self.assertEqual([timestamp for timestamp, _ in payloads], sorted(timestamp for timestamp, _ in payloads))


if __name__ == '__main__':
    unittest.main()
