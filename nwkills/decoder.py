"""Reads the message stream of one server->client UDP payload (pure Python, see nreader.py) and the per-tick state block
that follows it. Returns the messages (type + field values) and the bit position where the state block starts."""
import collections, itertools
from .tail import parse_tail
from .nreader import read_messages, Unknown

# Server/module specific bit widths (they come from the module's item/skin/etc. tables, so every server differs a little).
# calibrate() finds them from the capture itself; these are only the starting points.
PROFILES = {
    'nwe': dict(S324=11, S32C=11, S330=10, X328=12, IA=12, T5X=9),
    'nw':  dict(S324=10, S32C=11, S330=9,  X328=10, IA=9,  T5X=11),
}
CUR = dict(PROFILES['nwe'])
def set_profile(p):
    global CUR
    if isinstance(p, str): p = PROFILES[p]
    CUR = dict(p)
set_profile('nwe')

def msgs_only(pl):
    return read_messages(pl, CUR)

KEEP = (5, 6, 13, 18, 28)
import os as _os
_ALLPROPS = bool(_os.environ.get('NWKEEP_ALL_AGENT_PROPS'))      # research switch: keep every agent property (health etc.)
def one(a):
    k, ts, pl = a
    n = pl[7]-1 if len(pl) > 7 else 0
    rec = dict(i=k, t=ts, L=len(pl)*8, n=n, msgs=[], ev=[], txt=[], rst=0, tail=None, err=None)
    pos = 68
    if n > 0:
        try: r, cur, ms = msgs_only(pl)
        except Exception: rec['err'] = 'msg'; return rec
        if not (isinstance(r, tuple) and r[0] == 'stop'): rec['err'] = 'nostop'; return rec
        if len(ms) != n: rec['err'] = 'count%d/%d' % (len(ms), n)
        pos = cur
        rec['msgs'] = [(m[2], [v for b, v in m[3]], [b for b, v in m[3]]) for m in ms if m[2] in KEEP]
        # module script events (message types 36/37/38 with the 107 wrapper): (type, event number, args)
        # server text lines (type 39) and the same-map reset marker (type 41 with a single 1- or 3-bit field)
        rec['txt'] = [''.join(chr(v) for b, v in m[3] if b == 8 and 32 <= v < 127) for m in ms if m[2] == 39]
        rec['rst'] = sum(1 for m in ms if m[2] == 41 and len(m[3]) == 1 and m[3][0][0] in (1, 3))
        rec['ev'] = [(m[2], m[3][2][1], [v for b, v in m[3][3:]]) for m in ms if m[2] in (36, 37, 38) and len(m[3]) >= 4 and m[3][1][1] == 107]
    t = parse_tail(pl, pos)
    if t is None: rec['err'] = (rec['err'] or '') + 'tail'
    else:
        rec['tail'] = dict(time=t['time'], agents=[x for x in t['agents'] if _ALLPROPS or x[1] in (6, 7, 13, 27)], players=t['players'], end=t['end'])
    return rec

# ---- per-server calibration ------------------------------------------------------------------
def _bits(b, pos, n):
    i = pos >> 3; j = (pos + n + 7) >> 3
    return (int.from_bytes(b[i:j], 'little') >> (pos & 7)) & ((1 << n) - 1)
def _clean(pl):
    r = one((0, 0, pl))
    return bool(r['tail'] and r['L'] - r['tail']['end'] < 8 and not r['err'])
def _score(pls): return sum(_clean(p) for p in pls)
def calibrate(payloads, log=print, per_type=24):
    """Find the bit widths for this server by maximising the number of packets that parse to their end."""
    strata = collections.defaultdict(list)
    for pl in payloads:
        if len(pl) > 12 and 2 <= pl[7] <= 3:
            t = _bits(pl, 68, 6)
            if t in (5, 6, 7, 15, 20) and len(strata[t]) < per_type: strata[t].append(pl)
    p = dict(PROFILES['nwe'])
    def search(keys, grids, pls):
        if not pls: return
        bestv = None
        for combo in itertools.product(*grids):
            q = dict(p); q.update(dict(zip(keys, combo))); set_profile(q)
            s = _score(pls)
            if bestv is None or s > bestv[0]: bestv = (s, combo)
        p.update(dict(zip(keys, bestv[1]))); set_profile(p)
        log('  %s = %s  (%d/%d clean)' % (keys, bestv[1], bestv[0], len(pls)))
    search(['S324'], [range(2, 13)], strata[15])
    search(['S32C'], [range(8, 14)], strata[7])
    search(['S330'], [range(8, 13)], strata[20])
    search(['X328'], [range(8, 14)], strata[6])
    search(['IA', 'T5X'], [range(8, 14), (0, 9, 8, 10, 1, 2, 3, 4, 5, 6, 7, 11, 12)], strata[5])
    set_profile(p)
    return p
