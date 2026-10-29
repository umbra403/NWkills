import struct, collections

def read_pcapng(path):
    data = open(path,'rb').read()
    off = 0; ifaces = []; pkts = []; endian = '<'
    while off + 12 <= len(data):
        btype = struct.unpack_from('<I', data, off)[0]
        if btype == 0x0A0D0D0A:
            bom = struct.unpack_from('<I', data, off+8)[0]
            endian = '<' if bom == 0x1A2B3C4D else '>'
        btype, blen = struct.unpack_from(endian+'II', data, off)
        body = data[off+8: off+blen-4]
        if btype == 1:
            linktype, _, snap = struct.unpack_from(endian+'HHI', body, 0)
            tsres = 6; o = 8
            while o + 4 <= len(body):
                code, ln = struct.unpack_from(endian+'HH', body, o)
                if code == 0: break
                if code == 9: tsres = body[o+4]
                o += 4 + ((ln+3)//4)*4
            ifaces.append((linktype, snap, tsres))
        elif btype == 6:
            iid, th, tl, cap, orig = struct.unpack_from(endian+'IIIII', body, 0)
            ts = (th<<32 | tl)
            lt, snap, tsres = ifaces[iid]
            div = 2**(tsres&0x7f) if tsres & 0x80 else 10**tsres
            pkts.append((ts/div, lt, body[20:20+cap]))
        off += blen
    return ifaces, pkts

def parse_udp(lt, raw):
    if lt == 1:
        et = struct.unpack_from('>H', raw, 12)[0]; p = 14
        if et == 0x8100: et = struct.unpack_from('>H', raw, 16)[0]; p = 18
        if et != 0x0800: return None
        ip = raw[p:]
    elif lt == 101: ip = raw
    elif lt == 0: ip = raw[4:]
    else: return None
    if ip[0]>>4 != 4: return None
    ihl = (ip[0]&0xf)*4; proto = ip[9]
    src = '.'.join(map(str, ip[12:16])); dst = '.'.join(map(str, ip[16:20]))
    if proto != 17: return (src,dst,proto,None,None,b'')
    sp, dp, ln, ck = struct.unpack_from('>HHHH', ip, ihl)
    return (src,dst,proto,sp,dp,ip[ihl+8: ihl+ln])
