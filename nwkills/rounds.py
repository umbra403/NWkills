"""Round-boundary detection from decoded packet records.
Signals: mass score reset (many players' score >0 -> <=0 within 10 s),
type-51 flood (full resync, >=500 msgs / 5 s), packet gap >=2 s.
Signals within MERGE seconds are merged into one boundary."""
import collections
MERGE = 60.0

def _lull_ends(recs, min_len=40, frac=0.3):
    """Round starts inside a map: activity (spawns+deaths) falls to <30 % of
    the median for >=40 s (everyone dead, between rounds), then a new wave
    spawns. Returns the time the lull ends."""
    import statistics
    act = collections.Counter()
    for r in recs:
        for m in r['msgs']:
            if m[0] in (5, 13):
                act[int(r['t'] // 10)] += 1
    nb = int(recs[-1]['t'] // 10) + 1
    a = [act.get(i, 0) for i in range(nb)]
    sm = [sum(a[max(0, i - 1):i + 2]) for i in range(nb)]
    pos = [x for x in sm if x > 0]
    if not pos:
        return []
    med = statistics.median(pos)
    out = []; i = 0
    while i < nb:
        if sm[i] < frac * med:
            j = i
            while j < nb and sm[j] < frac * med:
                j += 1
            if j - i >= min_len // 10 and j < nb:
                out.append((j * 10.0, 'lull-end(%ds)' % ((j - i) * 10)))
            i = j
        else:
            i += 1
    return out

def _signals(recs):
    sig = _lull_ends(recs)
    prev = None
    sc = {}; drops = collections.defaultdict(set); t51 = collections.Counter()
    for r in recs:
        t = r['t']
        if prev is not None and t - prev >= 2.0:
            sig.append((prev, 'gap%.0fs' % (t - prev)))
        prev = t
        for m in r['msgs']:
            if m[0] == 51:
                t51[int(t // 5)] += 1
        tl = r.get('tail')
        if tl and r['L'] - tl['end'] < 8:
            b = int(t // 10)
            for pl, p, val in tl['players']:
                if p == 0 and pl < 300:
                    x = val - 8192 if val >= 4096 else val
                    if sc.get(pl, 0) > 0 and x <= 0:
                        drops[b].add(pl)
                    sc[pl] = x
    for b, s in drops.items():
        if len(s) >= 15:
            sig.append((b * 10.0, 'score-reset(%d)' % len(s)))
    for b, n in t51.items():
        if n >= 500:
            sig.append((b * 5.0, 'resync'))
    return sorted(sig)

def _ticket_series(recs):
    """Find the module's team-ticket event: a script event with two args
    (team 0/1, value) whose value mostly counts down. Returns [(t, team, value)] or None."""
    groups = collections.defaultdict(list)
    for r in recs:
        for ty, ev, args in r.get('ev', ()):
            if len(args) == 2 and args[0] in (0, 1) and args[1] <= 5000:
                groups[(ty, ev)].append((r['t'], args[0], args[1]))
    best = None
    for key, l in groups.items():
        if len(l) < 100: continue
        last = {}; dec = tot = 0
        for t, team, v in sorted(l):
            if team in last:
                tot += 1
                if 0 < last[team] - v <= 10: dec += 1
            last[team] = v
        sc = dec / max(tot, 1)
        if sc > 0.3 and (best is None or sc > best[0]): best = (sc, key, sorted(l))
    return best[2] if best else None

def detect_tickets(recs, series, reset_jump=60, merge=30.0, zero=5):
    t_first, t_last = recs[0]['t'], recs[-1]['t']
    cur = {}; resets = []; zeros = []   # zeros: (t, team)
    for t, team, v in series:
        p = cur.get(team)
        if p is not None and v - p >= reset_jump:
            if resets and t - resets[-1] < merge: pass
            else: resets.append(t)
        if v <= zero and (p is None or p > zero): zeros.append((t, team))
        if p is None or v < p or v - p >= reset_jump or t - cur.get((team, 't'), t) > 60: cur[team] = v
        cur[(team, 't')] = t
    starts = [t_first] + resets
    kt = [r['t'] for r in recs for m in r['msgs'] if m[0] == 13]
    out = []
    for i, s0 in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else t_last
        z = [(t, tm) for t, tm in zeros if s0 <= t < e]
        nk = sum(1 for t in kt if s0 <= t < e)
        rev = []
        if e - s0 < 120: rev.append('short (<120 s)')
        if nk < 25: rev.append('few kills (%d): dud?' % nk)
        out.append(dict(n=i + 1, start=s0, end=e, kills=nk,
                        signals='capture start' if i == 0 else 'ticket reset',
                        tickets_zero=(round(z[0][0]), 'team %d' % z[0][1]) if z else None,
                        review='; '.join(rev), method='tickets'))
    return out

def _zeros(series, zero=5):
    cur = {}; out = []
    for t, team, v in series:
        p = cur.get(team)
        if v <= zero and (p is None or p > zero): out.append((t, team))
        cur[team] = v
    return out

def server_events(recs, merge=60.0, ff_delay=30.0, near=12.0):
    """Round boundaries announced by the server itself: text lines 'Changed the map to ...' (map load) and
    'Has reset the Map.' (admin reset; also a type-41 marker). Every round start is also followed, 30 s later,
    by 'Friendly fire is now on' - so a restart done without those lines (e.g. admin 'Slayed Everyone')
    is recovered from that message (start = t - 30 s, snapped to a nearby 'Slayed Everyone' line).
    Returns [(t, kind)] with kind 'map' or 'reset'."""
    import re
    ev = []; ff = []; slay = []; delay = ff_delay
    for r in recs:
        for tx in r.get('txt', ()):
            m = re.search(r'(?:after|to) (\d+) second', tx)
            if m and ('Friendly fire' in tx or 'friendly fire' in tx): delay = float(m.group(1))   # server-configured FF delay (20/30 s ...)
            if 'Changed the map to' in tx: ev.append((r['t'], 'map'))
            elif 'Has reset the Map' in tx: ev.append((r['t'], 'reset'))
            elif 'Friendly fire is now on' in tx: ff.append((r['t'], delay))
            elif 'Slayed Everyone' in tx: slay.append(r['t'])
        if r.get('rst'): ev.append((r['t'], 'reset'))
    ev.sort()
    if not any(k == 'reset' for t, k in ev) and not ff: return []   # server without admin chat lines
    if not any(k == 'reset' for t, k in ev) and not any(k == 'map' for t, k in ev): return []
    out = []
    for t, k in ev:
        if out and out[-1][1] == k and t - out[-1][0] < (merge if k == 'map' else 20.0): continue
        if out and t - out[-1][0] < 3: continue
        out.append((t, k))
    prev_ff = None
    for tf, dl in sorted(ff):
        if prev_ff is not None and tf - prev_ff < 15: continue
        prev_ff = tf
        ts = tf - dl
        if any(abs(t - ts) <= 10 or tf - 50 <= t <= tf - 10 for t, k in out): continue      # explained by a map change / reset line (delay may be unknown at capture start)
        sn = [u for u in slay if abs(u - ts) <= near]
        out.append((min(sn, key=lambda u: abs(u - ts)) if sn else ts, 'reset'))
    out.sort()
    return out

def detect_server(recs, ev, series=None):
    t_first, t_last = recs[0]['t'], recs[-1]['t']
    starts = [t_first] + [t for t, k in ev]
    kinds = ['capture start'] + [k for t, k in ev]
    zeros = _zeros(series) if series else []
    kt = [r['t'] for r in recs for m in r['msgs'] if m[0] == 13]
    out = []
    for i, s0 in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else t_last
        z = [(t, tm) for t, tm in zeros if s0 <= t < e]
        nk = sum(1 for t in kt if s0 <= t < e)
        kz = sum(1 for t in kt if z and z[0][0] <= t < e)
        nxt = kinds[i + 1] if i + 1 < len(kinds) else None
        e_next = starts[i + 1] if i + 1 < len(starts) else None
        warm = (kinds[i] == 'map' and nxt == 'reset') or (kinds[i] == 'reset' and nxt == 'reset' and e_next - s0 < 60)   # map change (or quick reset) followed by the real admin reset = warm-up round
        live = not warm and kinds[i] != 'capture start'
        rev = []
        if warm: rev.append('not live (warm-up before admin reset): dud?')
        elif kinds[i] == 'capture start': rev.append('capture start (before first map change/reset)')
        if nk < 25: rev.append('few kills (%d)' % nk)
        out.append(dict(n=i + 1, start=s0, end=e, kills=nk, kills_after_zero=kz if z else '',
                        signals={'capture start': 'capture start', 'map': 'map change', 'reset': 'map reset (live)'}[kinds[i]],
                        kind='warm-up' if warm else ('live' if live else 'pre-live'),
                        tickets_zero=(round(z[0][0]), 'team %d' % z[0][1]) if z else None,
                        review='; '.join(rev), method='server messages'))
    return out

def detect(recs):
    """Returns list of round dicts: n, start, end, signals, review."""
    if recs:
        ev = server_events(recs)
        if ev: return detect_server(recs, ev, _ticket_series(recs))
    if recs:
        ser = _ticket_series(recs)
        if ser: return detect_tickets(recs, ser)
    sig = _signals(recs)
    if not recs:
        return []
    t_first, t_last = recs[0]['t'], recs[-1]['t']
    cuts = []
    for t, s in sig:
        if cuts and t - cuts[-1][0] < MERGE:
            cuts[-1][1].append(s)
        else:
            cuts.append([t, [s]])
    # drop boundaries in first/last 30 s of the capture
    cuts = [c for c in cuts if t_first + 30 < c[0] < t_last - 5 or any(x.startswith('gap') for x in c[1])]
    starts = [t_first] + [c[0] for c in cuts]
    why = ['capture start'] + [','.join(sorted(set(c[1]))) for c in cuts]
    kt = [r['t'] for r in recs for m in r['msgs'] if m[0] == 13]
    out = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else t_last
        nk = sum(1 for t in kt if s <= t < e)
        rev = []
        if e - s < 60: rev.append('short (<60 s)')
        if nk < 25: rev.append('few kills (%d): dud?' % nk)
        out.append(dict(n=i + 1, start=s, end=e, signals=why[i], kills=nk, tickets_zero=None, review='; '.join(rev), method='activity'))
    return out

def round_of(rounds, t):
    for r in rounds:
        if r['start'] <= t < r['end'] + 1e-9:
            return r['n']
    return rounds[-1]['n'] if rounds else 1
