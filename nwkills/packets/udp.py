"""Picking the UDP datagram out of a captured link-layer frame."""
import struct
from typing import NamedTuple, Optional

LINK_TYPE_NULL = 0                # BSD loopback: a 4-byte family header
LINK_TYPE_ETHERNET = 1
LINK_TYPE_RAW_IP = 101
ETHERTYPE_IPV4 = 0x0800
ETHERTYPE_VLAN = 0x8100
IP_PROTOCOL_UDP = 17


class UdpDatagram(NamedTuple):
    """The addresses and the payload of one IPv4 packet. Ports and payload are None / empty for anything that is not UDP."""
    source_address: str
    destination_address: str
    protocol: int
    source_port: Optional[int]
    destination_port: Optional[int]
    payload: bytes


class UdpDatagramParser:
    """Reads the IPv4 header and the UDP header of a frame."""

    def parse(self, link_type: int, frame_data: bytes) -> Optional[UdpDatagram]:
        """The datagram in the frame, or None when it is not an IPv4 packet on a link type this reader knows."""
        ip_packet = self._strip_link_header(link_type, frame_data)
        if ip_packet is None or ip_packet[0] >> 4 != 4:
            return None
        header_length = (ip_packet[0] & 0xf) * 4
        protocol = ip_packet[9]
        source_address = '.'.join(map(str, ip_packet[12:16]))
        destination_address = '.'.join(map(str, ip_packet[16:20]))
        if protocol != IP_PROTOCOL_UDP:
            return UdpDatagram(source_address, destination_address, protocol, None, None, b'')
        source_port, destination_port, udp_length, _checksum = struct.unpack_from('>HHHH', ip_packet, header_length)
        return UdpDatagram(source_address, destination_address, protocol, source_port, destination_port, ip_packet[header_length + 8: header_length + udp_length])

    @staticmethod
    def _strip_link_header(link_type: int, frame_data: bytes) -> Optional[bytes]:
        if link_type == LINK_TYPE_ETHERNET:
            ether_type = struct.unpack_from('>H', frame_data, 12)[0]
            header_length = 14
            if ether_type == ETHERTYPE_VLAN:
                ether_type = struct.unpack_from('>H', frame_data, 16)[0]
                header_length = 18
            return frame_data[header_length:] if ether_type == ETHERTYPE_IPV4 else None
        if link_type == LINK_TYPE_RAW_IP:
            return frame_data
        if link_type == LINK_TYPE_NULL:
            return frame_data[4:]
        return None
