import os
import tempfile
import unittest
import support
from nwkills import cli
from nwkills.packets.pcapng_file import PcapngWriter
from nwkills.packets.server_flow import FlowKey
from test_server_flow import CLIENT, SERVER, game_capture


class ReadServerFlowTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), 'a.pcapng')

    def test_returns_the_game_flow_with_its_payloads_and_the_frame_count(self):
        frames = game_capture(120)
        PcapngWriter().write_frames(self.path, frames)
        flow = cli.read_server_flow(self.path)
        self.assertEqual(flow.key, FlowKey(SERVER, 7240, CLIENT, 5555))
        self.assertEqual((len(flow.payloads), flow.frame_count), (120, len(frames)))

    def test_a_capture_without_a_game_flow_has_no_key_and_no_payloads(self):
        PcapngWriter().write_frames(self.path, game_capture(10))
        flow = cli.read_server_flow(self.path)
        self.assertEqual((flow.key, flow.payloads), (None, []))


if __name__ == '__main__':
    unittest.main()
