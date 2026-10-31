import argparse, collections, csv, json, os, struct, sys, time, multiprocessing as mp

def _init(exe, prof):
    from . import emu, decoder
    emu.load_exe(exe); decoder.set_profile(prof)

def _work(a):
    from .decoder import one
    return one(a)

def death_type(e, burst=False):
    """Provisional classification (no ground truth yet for the non-blow kinds).
    Server-log evidence: a player leaving shows as a killer-less death with weapon code 0 (shown as 'headshot')."""
    vs, ks = e['victim_slot'], e['killer_slot']
    if vs is not None and vs < 0: return 'AI/horse death'
    if e['killer_agent'] is not None and e['killer_agent'] < 0:
        return 'world (left server/fall)'
    if ks is not None and ks == vs: return 'self-inflicted (suicide/fall?)'
    if e.get('horse'): return 'horse death (player-owned mount)'     # victim agent is the player's horse (no rider properties); not a player death, no score
    if e.get('mode') != 2:
        if ks is not None and ks >= 0: return 'no-blow death (mount?, not counted)'      # known killer, no blow data and no killfeed line (seen on video: horse deaths); not counted
        return 'non-blow death (leave/class change?)'
    return 'kill'

def find_server_flow(pkts, want_port=None):
    from .pcap import parse_udp
    flows = collections.defaultdict(lambda: [0, 0, 0])      # key -> [packets, bytes, header-ok]
    store = collections.defaultdict(list)
    for ts, lt, raw in pkts:
        try: u = parse_udp(lt, raw)
        except Exception: continue
        if not u or u[3] is None or len(u[5]) < 13: continue
        src, dst, proto, sp, dp, pl = u
        if want_port and sp != want_port: continue
        key = (src, sp, dst, dp)
        f = flows[key]; f[0] += 1; f[1] += len(pl)
        if (pl[0] | (pl[1] << 8)) & 0x7ff == len(pl): f[2] += 1
        store[key].append((ts, pl))
    cands = [(k, v) for k, v in flows.items() if v[0] >= 50 and v[2] >= 0.9 * v[0]]
    if not cands: return None, []
    key, _ = max(cands, key=lambda kv: kv[1][1])             # biggest flow = server -> client
    return key, sorted(store[key], key=lambda x: x[0])

def main(argv=None):
    ap = argparse.ArgumentParser(description='Read Mount & Blade: Warband Napoleonic Wars kills from a Wireshark capture (client side).')
    ap.add_argument('pcap', nargs='?', help='.pcapng captured while you were connected to the server')
    ap.add_argument('--exe', help='path to your mb_warband.exe (optional: remembered after the first-run setup; the game is only read, never modified)')
    ap.add_argument('--setup', action='store_true', help='run the setup wizard (set or change the saved mb_warband.exe path) and exit')
    ap.add_argument('--out', help='output CSV (default: <pcap>_kills.csv)')
    ap.add_argument('--port', type=int, help='server UDP port (default: auto-detect)')
    ap.add_argument('--me', help='part of your own player name (used as the local player)')
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument('--cache', help='pickle file to save/reuse decoded packets (re-run the kill logic without re-decoding)')
    ap.add_argument('--limit', type=int, help='only decode the first N packets (test)')
    a = ap.parse_args(argv)
    from . import config
    if a.setup:
        config.wizard(); return
    if not a.pcap:
        if config.load().get('exe') is None and sys.stdin is not None and sys.stdin.isatty():
            if not config.wizard(): return
            print('Setup done. Now run:  nwkills.exe capture.pcapng   (or drag the .pcapng onto nwkills.exe)'); return
        ap.error('give the .pcapng capture to read (or run with --setup)')
    a.exe = config.resolve_exe(a.exe)
    if not a.exe: return
    from . import emu
    from .pcap import read_pcapng
    from .roster import build_roster, lookup
    from .events import decode, WCODE
    if not emu.load_exe(a.exe):
        print('WARNING: this mb_warband.exe is not the build the tables were made for (Warband 1.174 / NW 1.210); results may be wrong.', file=sys.stderr)
    t = time.time()
    cache = None; flow_items = None
    if a.cache and os.path.exists(a.cache):
        import pickle
        _c = pickle.load(open(a.cache, 'rb')); recs, ros = _c[0], _c[1]; flow_items = _c[2] if len(_c) > 2 else None; print('loaded %d decoded packets from %s' % (len(recs), a.cache))
    else:
        print('reading capture ...'); ifs, pk = read_pcapng(a.pcap)
        key, flow = find_server_flow(pk, a.port)
        if not flow: sys.exit('could not find the game server flow in the capture (try --port)')
        print('server flow %s:%d -> %s:%d, %d packets' % (key[0], key[1], key[2], key[3], len(flow)))
        if a.limit: flow = flow[:a.limit]
        t0 = flow[0][0]
        flow_items = [(ts - t0, pl) for ts, pl in flow]
        ros = build_roster(flow_items)
        print('%d player names found' % sum(len(v) for v in ros.values()))
        from . import decoder
        print('calibrating bit widths for this server ...')
        prof = decoder.calibrate([pl for ts, pl in flow[:60000]], log=lambda m: print(m, flush=True))
        jobs = [(k, ts - t0, pl) for k, (ts, pl) in enumerate(flow) if len(pl) > 12]
        recs = []
        with mp.Pool(a.jobs, initializer=_init, initargs=(a.exe, prof)) as p:
            for i, r in enumerate(p.imap(_work, jobs, chunksize=32)):
                recs.append(r)
                if i % 5000 == 0: print('  decoded %d / %d packets  (%.0f s)' % (i, len(jobs), time.time() - t), flush=True)
        good = sum(1 for r in recs if r['tail'] and r['L'] - r['tail']['end'] < 8)
        print('%d/%d packets parsed cleanly' % (good, len(recs)))
        if a.cache:
            import pickle
            pickle.dump((recs, ros, flow_items), open(a.cache, 'wb'))
    from .roster import retire_moved
    _since = retire_moved(ros)
    def namer(s, tt):
        if s is None: return '?'
        if s < 0: return '(AI)'
        return lookup(ros, s, tt) or 'player#%d' % s
    me = None
    if a.me:
        for s, v in ros.items():
            if any(a.me.lower() in x[2].lower() for x in v): me = s
    here = os.path.dirname(os.path.abspath(__file__))
    items = json.load(open(os.path.join(here, 'data', 'items.json')))
    ev, ls = decode(recs, None, me, items, namer)
    need = set(e[r + '_slot'] for e in ev for r in ('killer', 'victim') if e[r + '_slot'] is not None and e[r + '_slot'] >= 0 and not lookup(ros, e[r + '_slot'], e['time']))
    if need and flow_items is None:
        _i, _pk = read_pcapng(a.pcap); _k, _f = find_server_flow(_pk, a.port); flow_items = [(ts - _f[0][0], pl) for ts, pl in _f]
    if need and flow_items:
        from .roster import fill_roster
        fill_roster(ros, flow_items, need, since=_since)
        ev, ls = decode(recs, None, me, items, namer)
    for e in ev:
        if e['killer_agent'] is not None and e['killer_agent'] < 0: e['killer'] = '(world)'
    from .rounds import detect, round_of
    def rkind(rs, t):
        n = round_of(rs, t)
        return next((r.get('kind', '') for r in rs if r['n'] == n), '')
    rounds = detect(recs)
    wt = sorted(e['time'] for e in ev if e['killer_agent'] is not None and e['killer_agent'] < 0)
    burst_t = set(t for t in wt if sum(1 for u in wt if abs(u - t) <= 10) >= 3)
    out = a.out or os.path.splitext(a.pcap)[0] + '_kills.csv'
    with open(os.path.splitext(out)[0].replace('_kills', '') + '_rounds.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f); w.writerow(['round', 'start_s', 'end_s', 'length_s', 'started_by', 'tickets_zero_at_s', 'tickets_zero_team', 'kills_after_tickets_zero', 'kind', 'death_msgs', 'method', 'review'])
        for r in rounds: w.writerow([r['n'], round(r['start']), round(r['end']), round(r['end'] - r['start']), r['signals'], r['tickets_zero'][0] if r['tickets_zero'] else '', r['tickets_zero'][1] if r['tickets_zero'] else '', r.get('kills_after_zero', ''), r.get('kind', ''), r['kills'], r['method'], r['review']])
    known = set(WCODE)
    with open(out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f); w.writerow(['round', 'round_kind', 'time_s', 'mm:ss', 'killer', 'victim', 'weapon', 'teamkill', 'death_type', 'respawn_s', 'review', 'killer_slot', 'victim_slot'])
        for e in ev:
            flags = []
            if e['killer'] == '?' and e['time'] < 90: flags.append('before-sync')
            elif not isinstance(e['killer'], str) or e['killer'].startswith(('?', 'player#')): flags.append('killer?')
            if e['victim'] == '?' and e['time'] < 90: flags.append('before-sync')
            elif not isinstance(e['victim'], str) or e['victim'].startswith(('?', 'player#')): flags.append('victim?')
            if e.get('late'): flags.append('name-from-later-data(%s)' % '+'.join(e['late']))
            if e['weapon'].startswith('class ') or '(ico_' in e['weapon']: flags.append('weapon?')      # not yet seen on video (label from the exe's icon table only)
            
            if e['killer'] == e['victim'] and e['killer'] not in ('?', '(AI)', '(world)'): flags.append('self')
            w.writerow([round_of(rounds, e['time']), rkind(rounds, e['time']), e['time'], '%d:%02d' % divmod(int(e['time']), 60), e['killer'], e['victim'], e['weapon'], e['teamkill'], death_type(e, e['time'] in burst_t), '' if e.get('respawn') is None else e['respawn'], ' '.join(flags), e['killer_slot'], e['victim_slot']])
    st = collections.defaultdict(lambda: collections.Counter())
    def bump(name, key, rn):
        st[name][key] += 1; st[name][(rn, key)] += 1
    for e in ev:
        dt = death_type(e, e['time'] in burst_t)
        rn = round_of(rounds, e['time'])
        if dt.startswith(('horse death', 'no-blow death')): continue
        if dt == 'AI/horse death':
            if e['killer'] not in ('?', '(AI)', '(world)'): bump(e['killer'], 'ai_kills', rn)
            continue
        if dt == 'kill' and not e['teamkill']: bump(e['killer'], 'kills', rn)      # teamkills are counted separately, not as kills
        bump(e['victim'], 'deaths', rn)
        if e['teamkill']: bump(e['killer'], 'teamkills', rn)
    sp = os.path.splitext(out)[0] + '_players.csv'
    # --- scoreboard check: the server sends every player's current score (kills - teamkills) when you connect and on every change.
    sb = collections.defaultdict(list)                       # slot -> [(t, score)]
    for r in recs:
        tl = r.get('tail')
        if not tl: continue
        for p_, pr, v in tl['players']:
            if pr == 0 and 0 <= p_ < 250:
                sc = v - 8192 if v >= 4096 else v
                if abs(sc) <= 150 and (not sb[p_] or sb[p_][-1][1] != sc): sb[p_].append((r['t'], sc))
    gap = collections.defaultdict(int); gapn = collections.Counter()     # (name, round) -> scoreboard change minus recorded net
    sc0 = {}; sc1 = {}
    BASE = 6.0       # the scoreboard reset lands a few seconds after the detected round start
    byslot = collections.defaultdict(list)
    for e in ev:
        if e['killer_slot'] is None or e['killer_slot'] < 0: continue
        dt = death_type(e, False)
        if dt == 'kill' or (dt.startswith('self') and e['teamkill']):
            byslot[e['killer_slot']].append((e['time'], -1 if e['teamkill'] else 1))
    for slot, ser in sb.items():
        for r in rounds:
            tb = r['start'] + BASE if r['start'] > 0 else ser[0][0]
            before = [v_ for t_, v_ in ser if t_ <= tb]
            inr = [v_ for t_, v_ in ser if tb < t_ < r['end']]
            if r['start'] > 0:
                if not before: continue
                s0_ = before[-1]
            else: s0_ = ser[0][1]
            vals = [s0_] + inr
            if any(b_ - a_ < -15 for a_, b_ in zip(vals, vals[1:])): continue      # score reset inside the round (slot reused / player rejoined)
            nm = lookup(ros, slot, tb)
            if not nm: continue
            net = sum(d for t_, d in byslot[slot] if tb < t_ < r['end'])
            gap[(nm, r['n'])] += (vals[-1] - s0_) - net; gapn[(nm, r['n'])] += 1
        nm = lookup(ros, slot, ser[0][0])
        if nm: sc0[nm] = ser[0][1]; sc1[nm] = ser[-1][1]
    kinds = {r['n']: r.get('kind', '') for r in rounds}
    cols = []
    for r in rounds:
        lab = 'R%d' % r['n'] + ('(%s)' % r['kind'] if r.get('kind') else '')
        cols += [((r['n'], k), '%s_%s' % (lab, k)) for k in ('kills', 'deaths', 'teamkills', 'score_gap')]
    keep = [r['n'] for r in rounds if r.get('kind') != 'warm-up']      # overall totals leave out warm-up rounds
    tot = lambda c, k: sum(c[(rn, k)] for rn in keep)
    for nm in set(n for n, _ in gap) | set(st): st[nm]            # make sure every scoreboard player has a row
    rows = list(st.items())
    net = lambda c: tot(c, 'kills') - tot(c, 'teamkills')           # overall kills = kills minus teamkills (like the scoreboard)
    rows.sort(key=lambda nc: -net(nc[1]))
    with open(sp, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f); w.writerow(['player', 'kills', 'deaths', 'teamkills', 'ai_kills', 'score_at_capture_start', 'score_at_capture_end', 'score_gap'] + [h for _, h in cols])
        for n, c in rows:
            gaps = [gap[(n, rn)] for rn in keep if (n, rn) in gapn]
            row = [n, net(c), tot(c, 'deaths'), tot(c, 'teamkills'), tot(c, 'ai_kills'), sc0.get(n, ''), sc1.get(n, ''), sum(gaps) if gaps else '']
            for (rn, k), _h in cols:
                row.append((gap[(n, rn)] if (n, rn) in gapn else '') if k == 'score_gap' else c[(rn, k)])
            w.writerow(row)
    print('%d kills -> %s\nper player -> %s\ndone in %.0f s' % (len(ev), out, sp, time.time() - t))

if __name__ == '__main__':
    mp.freeze_support(); main()
