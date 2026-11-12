"""Native (pure Python) reader for the NW server->client message stream.
Gives the same output as decoder.msgs_only() without running the game's own code.
Message layout: 6-bit type, a peer field (width = 4-bit value at packet bit 64, plus 1), then a type-specific body.
Body widths marked by a symbol depend on the server's module (see decoder.PROFILES / calibrate)."""

class Unknown(Exception):
    """A message type this reader has no layout for."""

# fixed body layouts; strings are server-specific widths (resolved from the profile)
F = {
    1: (1, 2, 3),
    2: (3, 5, 13, 13, 13, 13),         # second field = faction-count width (5 on NW and NWE, confirmed on 107 queued packets), like the two fields of types 0 and 63
    5: (10, 8, 'S324', 3, 8, 32) + ('IA',)*11 + (10, 10, 51, 10, 7, 7, 7, 1, 'T5X'),
    6: (10, 51, 27, 12, 10, 'X328', 32, 'X328', 32),
    9: (10, 10, 6, 10, 10, 10, 12, 12, 12, 12),
    11: (10,)*5 + (12,)*4,
    12: (10,), 14: (8, 3), 15: (8, 'S324'), 16: (8,), 17: (14,), 18: (10,), 19: (10,),
    21: (10, 'S330', 12, 15, 15, 15, 5),
    22: (12, 12, 12), 23: (10,), 24: (10, 10),
    25: (10, 1), 26: (10, 1), 27: (10, 1),
    28: (10,)*8 + (8, 8, 1, 12, 2),
    29: (10, 10, 7, 7, 7),
    30: (10, 10), 34: (7,),
    35: (7, 32), 36: (7, 32, 32), 37: (7, 32, 32, 32), 38: (7, 32, 32, 32, 32),
    4: (8, 13, 13),
    8: (10, 17, 17, 17, 12, 12, 12, 12),
    10: (10, 14, 13, 13, 13, 12, 12, 12, 12),
    31: (17,),
    50: (8, 10),
    61: (),
    41: (), 42: (14,),
    45: (14,), 46: (14,) + (17,)*3 + (12,)*4,
    47: (14,) + (17,)*3 + (12,)*4 + (17,),
    48: (14, 10) + (17,)*3 + (12,)*4 + (14, 1),
    49: (),
    51: (10, 2, 10),
    52: (10, 'S330', 12, 15, 15, 15, 5),
    54: (8,), 55: (),
    57: (7, 10), 58: (10,), 59: (8,), 60: (10, 1),
}
STRING_TYPES = (0, 3, 7, 13, 20, 32, 33, 39, 40, 43, 44, 53, 56, 62, 63)       # bodies whose length depends on the data
KNOWN = set(F) | set(STRING_TYPES)

def read_messages(pl, prof):
    """-> (res, cursor, ms) like decoder.msgs_only. ms: (start_bit, end_bit, type, [(nbits, value), ...]) (first field is the peer)."""
    total = len(pl) * 8
    val = int.from_bytes(pl, 'little')
    sym = dict(prof)
    cur = [68]
    ms = []
    class Eof(Exception): pass
    def rd(n, out):
        p = cur[0]
        if p + n > total: raise Eof()
        v = (val >> p) & ((1 << n) - 1)
        cur[0] = p + n; out.append((n, v)); return v
    def string(out, cap):
        n = rd(16, out)
        if n <= cap:
            for _ in range(n): rd(8, out)
    n_msgs = pl[7] - 1 if len(pl) > 7 else 0
    hw = ((val >> 64) & 15) + 1
    try:
        for _ in range(n_msgs):
            c0 = cur[0]; out = []
            t = rd(6, out); out.clear()
            if t not in KNOWN: raise Unknown(t)
            rd(hw, out)
            if t in F:
                for w in F[t]:
                    if t == 5 and w == 'T5X' and not sym['T5X']: continue
                    rd(sym[w] if isinstance(w, str) else w, out)
            elif t in (3, 32, 33, 39):
                rd(7 if t == 39 else 8, out); n = rd(16, out)
                if t == 3:
                    if n <= 255:
                        for _ in range(n): rd(8, out)
                elif n <= 299:                      # longer strings are rejected by the game: nothing more is read
                    for _ in range(n): rd(8, out)
                if t == 3:
                    rd(1, out); rd(10, out)
                    for _ in range(32): rd(8, out)
                    rd(3, out); rd(sym['S324'], out)
            elif t == 62:
                rd(16, out); n = rd(10, out)
                if n <= 450:
                    for _ in range(n): rd(8, out)
            elif t == 40:
                rd(8, out); rd(5, out); k = rd(5, out)
                for _ in range(k): rd(32, out)
            elif t == 13:
                rd(10, out); rd(10, out); rd(5, out); f = rd(2, out); g = rd(1, out)
                if g:
                    for _ in range(3): rd(7, out)
                if f == 3: rd(7, out)
                if f & 1:
                    for _ in range(3): rd(11, out)
                if f & 2: rd(9, out)
            elif t in (43, 44):
                rd(14, out)
                for w in ((17, 17, 17, 12, 12, 12, 12, 17, 17, 17, 12, 12, 12, 12, 17) if t == 44 else (17, 17, 17, 12, 12, 12, 12, 17)): rd(w, out)
                if rd(1, out): rd(20, out)
            elif t == 7:
                rd(14, out); rd(10, out)
                if rd(1, out): rd(14, out)
                rd(4, out); rd(sym['S32C'], out)
                for w in (32, 32, 17, 17, 17, 12, 12, 12, 12): rd(w, out)
            elif t == 20:
                if rd(1, out):
                    rd(14, out); rd(sym['S330'], out); rd(12, out)
                else:
                    rd(sym['S330'], out); rd(12, out)
                    for w in (15, 15, 15, 5): rd(w, out)
            elif t in (0, 63):
                if t == 63:
                    if not rd(1, out):
                        rd(32, out); ms.append((c0, cur[0], t, out)); continue
                    rd(8, out); rd(2, out); rd(16, out); rd(32, out); rd(16, out); rd(10, out); rd(32, out)
                else:
                    rd(16, out)
                for _ in range(16): rd(8, out)
                if t == 0:
                    rd(32, out); rd(16, out); rd(10, out)
                string(out, 49); string(out, 399)
            elif t in (53, 56):
                string(out, 49); rd(14, out); rd(14, out); string(out, 49); rd(16, out); string(out, 49); rd(16, out); string(out, 49)
                rd(8, out); rd(8, out)
                a = rd(1, out); b = rd(1, out); c = rd(1, out)
                if c:                                  # list of 32-bit values, each followed by a 'more' bit
                    while True:
                        rd(32, out)
                        if not rd(1, out): break
                rd(10, out)
                if t == 53:
                    for _ in range(8): rd(8, out)
            ms.append((c0, cur[0], t, out))
    except Eof:
        return ('stop', 'eof'), cur[0], ms
    return ('stop', 'tail'), cur[0], ms
