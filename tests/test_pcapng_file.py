import os
import tempfile
import unittest
import support
from nwkills.packets.pcapng_file import CapturedFrame, PcapngReader, PcapngWriter


class PcapngFileTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.path = os.path.join(self.directory, 'capture.pcapng')
        self.frames = [CapturedFrame(1000.5 + i, 1, bytes([i]) * (5 + i)) for i in range(6)]

    def test_frames_survive_a_write_and_read_round_trip(self):
        PcapngWriter().write_frames(self.path, self.frames)
        read_back = list(PcapngReader().read_frames(self.path))
        self.assertEqual([frame.data for frame in read_back], [frame.data for frame in self.frames])
        self.assertEqual([frame.link_type for frame in read_back], [1] * 6)
        for original, copy in zip(self.frames, read_back):
            self.assertAlmostEqual(original.timestamp_seconds, copy.timestamp_seconds, places=5)

    def test_every_link_type_gets_its_own_interface(self):
        mixed = [CapturedFrame(1.0, 1, b'abcd'), CapturedFrame(2.0, 101, b'efgh'), CapturedFrame(3.0, 1, b'ij')]
        PcapngWriter().write_frames(self.path, mixed)
        self.assertEqual([frame.link_type for frame in PcapngReader().read_frames(self.path)], [1, 101, 1])

    def test_an_empty_or_tiny_file_has_no_frames(self):
        with open(self.path, 'wb') as output:
            output.write(b'abc')
        self.assertEqual(list(PcapngReader().read_frames(self.path)), [])

    def test_a_cut_off_file_gives_the_frames_before_the_damage(self):
        PcapngWriter().write_frames(self.path, self.frames)
        with open(self.path, 'r+b') as capture_file:
            capture_file.truncate(os.path.getsize(self.path) - 10)
        self.assertEqual(len(list(PcapngReader().read_frames(self.path))), 5)

    def test_the_writer_accepts_a_generator(self):
        PcapngWriter().write_frames(self.path, (frame for frame in self.frames))
        self.assertEqual(len(list(PcapngReader().read_frames(self.path))), 6)


if __name__ == '__main__':
    unittest.main()
