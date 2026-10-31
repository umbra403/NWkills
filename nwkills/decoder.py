"""Emulates the game's packet reader (mb_warband.exe 1.174) over one server->client UDP payload.
Returns the messages (type + field values) and the bit position where the per-tick state block starts."""
from .pktemu import *
from .pktemu import EXTRA
from .emu import Stop, NoStep, M32
import collections, itertools
from .tail import parse_tail

X328 = 12            # item-id bit width (NW: 10, NWE: 12)
STEPINTO = [0x4f5bb0]
IA = 12              # type-5 loadout item bits
T5X = 9              # extra bits after a type-5 message (NWE)
W = [8, 2, 3, 8]
# Server/module specific bit widths (statics inside the game built from the module's tables).
PROFILES = {
    'nwe': dict(X328=12, IA=12, T5X=9, S32C=11, S330=10, STEP=[0x4f5bb0]),
    'nw':  dict(X328=10, IA=10, T5X=0, S32C=0,  S330=9,  STEP=[]),
}
def set_profile(p):
    global X328, IA, T5X, STEPINTO
    if isinstance(p, str): p = PROFILES[p]
    p = dict(p); p.setdefault('S324', 2)
    W[1] = p['S324']; EXTRA[0x87c324] = p['S324']
    X328 = p['X328']; IA = p['IA']; T5X = p['T5X']; STEPINTO = list(p['STEP'])
    EXTRA[0x87c328] = X328; EXTRA[0x87c32c] = p['S32C']; EXTRA[0x87c330] = p['S330']
set_profile('nwe')

def h4f40b0(e, a):                 # type 6: projectile spawn
    for n in (17*3, 9*3, 12, 10, X328, 32, X328, 32): e.readbits(n)
    e.r['eax'] = 0; e.r['esp'] += 0x10

def h4f8b80(e, a):                 # type 5: agent create
    for n in (W[0], W[1], W[2], W[3], 32) + (IA,)*11 + (10, 10, 51, 10, 7, 7, 7, 1) + ((T5X,) if T5X else ()): e.readbits(n)
    e.r['eax'] = 0; e.r['esp'] += 0x10

def h_time(e, a): raise Stop('tail')

def run4(pl, maxsteps=400000, hooks=None):
    EXTRA[0x87c328] = X328
    e = run_packet(pl); e.wr(0x40000010, 1, 1); e.stepmax = 0x486000; e.stepinto |= set(STEPINTO)
    e.nostep = NoStep()
    e.wr(0xdd842c, 4, 29); e.wr(0xdd8430, 4, 0x1c)
    for ad, v in ((0x1d9a20c, 0x50000000), (0x1d9a21c, 0x58000000), (0x1d9a210, 0x50000000), (0x1d9a220, 0x58000000)): e.wr(ad, 4, v)
    e.hooks[0x485430] = lambda e, a: e.r.__setitem__('esp', e.r['esp']+8)
    e.hooks[0x478970] = lambda e, a: e.r.__setitem__('esp', e.r['esp']+8)
    e.hooks[0x4f40b0] = h4f40b0
    for k, v in (hooks or {}).items(): e.hooks[k] = v
    try: res = e.run(0x473ca0, maxsteps=maxsteps)
    except Stop as ex: res = ('stop', str(ex))
    except Exception as ex: res = ('err', repr(ex)[:300])
    return e, res

def msgs_only(pl, maxsteps=400000):
    e, res = run4(pl, maxsteps, hooks={0x4f8b80: h4f8b80, 0x46ee20: h_time})
    ms = []
    for f, c0, c1 in e.calls:
        if f != 0x46fb70: continue
        rs = [r for r in e.reads if c0 <= r[0] < c1]
        ms.append((c0, c1, rs[0][2] if rs else None, [(r[1], r[2]) for r in rs[1:]]))
    return res, e.cursor, ms

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
        except Exception: rec['err'] = 'emu'; return rec
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
    p['STEP'] = [0x4f5bb0]; set_profile(p)
    return p
