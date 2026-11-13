# nwkills - capture the game traffic with Windows' built-in pktmon, then keep only the game server's packets.
# Copyright (C) 2026 the nwkills authors. Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""Capture without Wireshark.

pktmon (Packet Monitor) ships with Windows 10 1809 and later and needs administrator rights. We capture all UDP at the
network adapters, convert the trace to pcapng, find the game server's flow with the same rule the reader uses, and write a
small pcapng that holds only that flow (both directions). Everything else that was captured is dropped and never kept.

The pruning works on a memory-mapped file, so a capture of several GB does not have to fit in memory.
"""
import collections, mmap, os, shutil, struct, subprocess, sys, time

DEFAULT_BUFFER_MB = 4096          # pktmon's circular log; it overwrites its own start when full (default would be 512)


# ------------------------------------------------------------------ pktmon
def is_windows(): return sys.platform.startswith('win')

def is_admin():
    if not is_windows(): return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception: return False

def pktmon_path(): return shutil.which('pktmon')

def start_commands(etl, size_mb=DEFAULT_BUFFER_MB):
    """The pktmon command lines that start a capture of all UDP at the network adapters, with whole packets."""
    return [['pktmon', 'filter', 'remove'],
            ['pktmon', 'filter', 'add', '-t', 'UDP'],
            ['pktmon', 'start', '--capture', '--comp', 'nics', '--pkt-size', '0', '--file-name', etl, '--file-size', str(int(size_mb))]]

def stop_commands(etl, pcapng):
    return [['pktmon', 'stop'], ['pktmon', 'etl2pcap', etl, '--out', pcapng]]

def _run(cmd, check=True, timeout=600):
    flags = 0x08000000 if is_windows() else 0                 # CREATE_NO_WINDOW: no console flash from the window version
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, creationflags=flags)
    out = p.stdout.decode('utf-8', 'replace').strip()
    if check and p.returncode != 0: raise RuntimeError('%s failed (exit %d):\n%s' % (' '.join(cmd[:3]), p.returncode, out))
    return out

def check_ready():
    """Returns an error text when capturing cannot start here, else None."""
    if not is_windows(): return 'Capturing needs Windows (pktmon). On other systems, capture with Wireshark or tcpdump and open the file.'
    if not pktmon_path(): return 'pktmon was not found. It is part of Windows 10 (version 1809) and later.'
    if not is_admin(): return 'Capturing needs administrator rights. Close this window, right-click nwkills-gui.exe and choose "Run as administrator".'
    return None

def start(etl, size_mb=DEFAULT_BUFFER_MB):
    err = check_ready()
    if err: raise RuntimeError(err)
    os.makedirs(os.path.dirname(os.path.abspath(etl)), exist_ok=True)
    _run(['pktmon', 'stop'], check=False)                      # an earlier session that was left running would block the new one
    if os.path.exists(etl): os.remove(etl)
    try:
        for c in start_commands(etl, size_mb): _run(c)
    except Exception:
        _run(['pktmon', 'filter', 'remove'], check=False); raise

def stop_and_convert(etl, pcapng):
    """Stop the capture and convert the trace. Raises when no trace could be written."""
    try:
        for c in stop_commands(etl, pcapng): _run(c, check=(c[1] != 'stop'))
    finally:
        _run(['pktmon', 'filter', 'remove'], check=False)
    if not os.path.exists(pcapng) or os.path.getsize(pcapng) < 100:
        raise RuntimeError('pktmon produced no capture file. Was anything captured?')


def discard(etl):
    """Stop a running capture and throw it away."""
    try: _run(['pktmon', 'stop'], check=False)
    finally:
        _run(['pktmon', 'filter', 'remove'], check=False)
        try: os.remove(etl)
        except OSError: pass

def finish(etl, final, want_port=None, log=None):
    """Stop, convert, keep only the game server's packets in `final`, and delete the big temporary files. Returns (kept, seen)."""
    raw = final + '.raw.pcapng'
    try:
        if log: log('Stopping the capture and converting it ...')
        stop_and_convert(etl, raw)
        if log: log('Looking for the game server ...')
        _key, kept, seen = prune(raw, final, want_port, log)
        return kept, seen
    finally:
        for f in (raw, etl):
            try: os.remove(f)
            except OSError: pass

# ------------------------------------------------------------------ pcapng, streaming
def iter_pcapng(path):
    """Yield (timestamp, linktype, raw bytes) of every packet; same results as pcap.read_pcapng, but memory-mapped."""
    with open(path, 'rb') as f:
        if os.path.getsize(path) < 12: return
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            off, ifaces, endian, n = 0, [], '<', len(mm)
            while off + 12 <= n:
                btype = struct.unpack_from('<I', mm, off)[0]
                if btype == 0x0A0D0D0A:
                    endian = '<' if struct.unpack_from('<I', mm, off + 8)[0] == 0x1A2B3C4D else '>'
                btype, blen = struct.unpack_from(endian + 'II', mm, off)
                if blen < 12 or off + blen > n: break          # damaged or cut-off tail
                if btype == 1:
                    body = mm[off + 8: off + blen - 4]
                    linktype, _, snap = struct.unpack_from(endian + 'HHI', body, 0)
                    tsres, o = 6, 8
                    while o + 4 <= len(body):
                        code, ln = struct.unpack_from(endian + 'HH', body, o)
                        if code == 0: break
                        if code == 9: tsres = body[o + 4]
                        o += 4 + ((ln + 3) // 4) * 4
                    ifaces.append((linktype, tsres))
                elif btype == 6:
                    iid, th, tl, cap, _orig = struct.unpack_from(endian + 'IIIII', mm, off + 8)
                    lt, tsres = ifaces[iid]
                    div = 2 ** (tsres & 0x7f) if tsres & 0x80 else 10 ** tsres
                    yield ((th << 32 | tl) / div, lt, bytes(mm[off + 28: off + 28 + cap]))
                off += blen
        finally:
            mm.close()

def write_pcapng(path, packets):
    """Write (timestamp, linktype, raw) packets as a pcapng with microsecond timestamps."""
    ifidx = {}
    with open(path, 'wb') as f:
        f.write(struct.pack('<IIIHHqI', 0x0A0D0D0A, 28, 0x1A2B3C4D, 1, 0, -1, 28))
        for ts, lt, raw in packets:
            if lt not in ifidx:
                ifidx[lt] = len(ifidx)
                f.write(struct.pack('<IIHHII', 1, 20, lt, 0, 262144, 20))              # interface description, no options
            t = int(round(ts * 1e6)); pad = (-len(raw)) % 4; blen = 32 + len(raw) + pad
            f.write(struct.pack('<IIIIIII', 6, blen, ifidx[lt], t >> 32, t & 0xffffffff, len(raw), len(raw)))
            f.write(raw); f.write(b'\0' * pad); f.write(struct.pack('<I', blen))


# ------------------------------------------------------------------ pruning
def _flow_of(lt, raw):
    from .pcap import parse_udp
    try: u = parse_udp(lt, raw)
    except Exception: return None
    if not u or u[3] is None: return None
    return u

def find_server_key(path, want_port=None):
    """Streaming version of cli.find_server_flow: the (src, sport, dst, dport) of the server -> client flow, or None."""
    flows = collections.defaultdict(lambda: [0, 0, 0])
    for _ts, lt, raw in iter_pcapng(path):
        u = _flow_of(lt, raw)
        if not u or len(u[5]) < 13: continue
        src, dst, _proto, sp, dp, pl = u
        if want_port and sp != want_port: continue
        f = flows[(src, sp, dst, dp)]; f[0] += 1; f[1] += len(pl)
        if (pl[0] | (pl[1] << 8)) & 0x7ff == len(pl): f[2] += 1
    cands = [(k, v) for k, v in flows.items() if v[0] >= 50 and v[2] >= 0.9 * v[0]]
    if not cands: return None
    return max(cands, key=lambda kv: kv[1][1])[0]

def prune(src, dst, want_port=None, log=None):
    """Write the game flow of `src` (both directions) to `dst`. Returns (server key, packets kept, packets seen)."""
    key = find_server_key(src, want_port)
    if key is None: raise RuntimeError('could not find the game server in the capture. Was the game connected to a server while capturing?')
    s_ip, s_port, c_ip, c_port = key
    seen = [0]
    def keep():
        for pkt in iter_pcapng(src):
            seen[0] += 1
            u = _flow_of(pkt[1], pkt[2])
            if u and ((u[0], u[3], u[1], u[4]) == key or (u[0], u[3], u[1], u[4]) == (c_ip, c_port, s_ip, s_port)): yield pkt
    kept = [0]
    def counted():
        for pkt in keep(): kept[0] += 1; yield pkt
    write_pcapng(dst, counted())
    if log: log('kept %d of %d packets (server %s:%d)' % (kept[0], seen[0], s_ip, s_port))
    return key, kept[0], seen[0]

def stamp_name(prefix='capture'): return '%s_%s' % (prefix, time.strftime('%Y-%m-%d_%H%M'))
