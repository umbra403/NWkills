import struct
import unittest
import support
from nwkills.packets import udp
from nwkills.packets.udp import UdpDatagramParser


class UdpDatagramParserTest(unittest.TestCase):
    def setUp(self):
        self.parser = UdpDatagramParser()
        self.frame = support.ethernet_udp_frame('10.0.0.5', 7240, '192.168.0.2', 5555, b'hello')

    def test_reads_addresses_ports_and_payload_of_an_ethernet_frame(self):
        datagram = self.parser.parse(udp.LINK_TYPE_ETHERNET, self.frame)
        self.assertEqual((datagram.source_address, datagram.source_port, datagram.destination_address, datagram.destination_port),
                         ('10.0.0.5', 7240, '192.168.0.2', 5555))
        self.assertEqual(datagram.payload, b'hello')

    def test_reads_a_raw_ip_frame(self):
        self.assertEqual(self.parser.parse(udp.LINK_TYPE_RAW_IP, self.frame[14:]).payload, b'hello')

    def test_reads_a_loopback_frame(self):
        self.assertEqual(self.parser.parse(udp.LINK_TYPE_NULL, b'\x02\0\0\0' + self.frame[14:]).payload, b'hello')

    def test_reads_a_vlan_tagged_frame(self):
        tagged = self.frame[:12] + struct.pack('>HHH', 0x8100, 5, 0x0800) + self.frame[14:]
        self.assertEqual(self.parser.parse(udp.LINK_TYPE_ETHERNET, tagged).payload, b'hello')

    def test_a_frame_that_is_not_ipv4_gives_none(self):
        self.assertIsNone(self.parser.parse(udp.LINK_TYPE_ETHERNET, self.frame[:12] + b'\x86\xdd' + self.frame[14:]))

    def test_an_unknown_link_type_gives_none(self):
        self.assertIsNone(self.parser.parse(999, self.frame))

    def test_a_tcp_packet_has_no_ports(self):
        tcp_frame = bytearray(self.frame)
        tcp_frame[14 + 9] = 6
        datagram = self.parser.parse(udp.LINK_TYPE_ETHERNET, bytes(tcp_frame))
        self.assertEqual((datagram.protocol, datagram.source_port, datagram.payload), (6, None, b''))


if __name__ == '__main__':
    unittest.main()
