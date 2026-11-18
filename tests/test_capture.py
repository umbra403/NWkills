import os, struct, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from nwkills import capture, pcap
from nwkills.cli import find_server_flow

def frame(src, sp, dst, dp, payload):
    udp = struct.pack('>HHHH', sp, dp, 8 + len(payload), 0) + payload
    ip = struct.pack('>BBHHHBBH4s4s', 0x45, 0, 20 + len(udp), 0, 0, 64, 17, 0, bytes(map(int, src.split('.'))), bytes(map(int, dst.split('.')))) + udp
    return b'\0' * 12 + b'\x08\x00' + ip

def game(n, i):                                   # a payload whose first 11 bits equal its length, as the reader's check wants
    return struct.pack('<H', n) + bytes([i % 251]) * (n - 2)

def make(path):
    pk, t = [], 1000.0
    for i in range(120):
        t += 0.01
        pk.append((t, 1, frame('10.0.0.5', 7240, '192.168.0.2', 5555, game(40 + i % 7, i))))
        if i % 3 == 0: pk.append((t, 1, frame('192.168.0.2', 5555, '10.0.0.5', 7240, game(20, i))))
        pk.append((t, 1, frame('8.8.8.8', 443, '192.168.0.2', 6000, b'x' * 900)))       # noise (QUIC, voice...)
        pk.append((t, 1, frame('1.1.1.1', 53, '192.168.0.2', 6001, b'dns')))
    capture.write_pcapng(path, pk)
    return pk

def test_roundtrip_and_prune():
    d = tempfile.mkdtemp(); a, b = os.path.join(d, 'a.pcapng'), os.path.join(d, 'b.pcapng')
    pk = make(a)
    _ifs, back = pcap.read_pcapng(a)
    assert len(back) == len(pk) and back[5][2] == pk[5][2] and abs(back[5][0] - pk[5][0]) < 1e-5
    assert [(x[1], x[2]) for x in capture.iter_pcapng(a)] == [(x[1], x[2]) for x in back]      # streaming reader = the normal reader
    key, kept, seen = capture.prune(a, b)
    assert key == ('10.0.0.5', 7240, '192.168.0.2', 5555), key
    assert seen == len(pk) and kept == 120 + 40
    _ifs, small = pcap.read_pcapng(b)
    assert len(small) == kept and os.path.getsize(b) < os.path.getsize(a) / 3
    k2, flow = find_server_flow(small)
    assert k2 == key and len(flow) == 120

def test_no_game_flow():
    d = tempfile.mkdtemp(); a, b = os.path.join(d, 'a.pcapng'), os.path.join(d, 'b.pcapng')
    capture.write_pcapng(a, [(1.0 + i, 1, frame('1.1.1.1', 53, '192.168.0.2', 6001, b'dns')) for i in range(100)])
    try: capture.prune(a, b)
    except RuntimeError as ex: assert 'game server' in str(ex)
    else: raise AssertionError('expected an error')

def test_commands():
    c = capture.start_commands(r'C:\caps\x.etl', 4096)
    assert c[1] == ['pktmon', 'filter', 'add', '-t', 'UDP']
    assert c[2][:3] == ['pktmon', 'start', '--capture'] and '--pkt-size' in c[2] and c[2][c[2].index('--pkt-size') + 1] == '0'
    assert c[2][-2:] == ['--file-size', '4096']
    assert capture.stop_commands('a.etl', 'a.pcapng')[1] == ['pktmon', 'etl2pcap', 'a.etl', '--out', 'a.pcapng']

if __name__ == '__main__':
    for n, f in sorted(globals().items()):
        if n.startswith('test_'): f(); print('ok', n)
