"""Everything that turns the bytes of a capture file into decoded game packets.

pcapng_file     reads and writes capture files
udp             picks the UDP datagram out of a captured frame
server_flow     finds the game server's packet flow in a capture
bit_reader      reads values of any bit width out of a byte buffer
server_profile  the bit widths that differ from one server to the next
message_layouts the field layouts of the server's message types
message_reader  reads the message list at the start of a packet
state_block     reads the state block (time, agent and player updates) at the end of a packet
packet_decoder  combines both readers into one decoded packet
profile_calibrator  finds the bit widths of a server from its own packets
parallel_decoding   decodes many packets on several processes
"""
