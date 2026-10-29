import argparse, collections, csv, json, os, struct, sys, time, multiprocessing as mp

def _init(exe, prof):
    from . import emu, decoder
    emu.load_exe(exe); decoder.set_profile(prof)

def _work(a):
    from .decoder import one
    return one(a)

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
    ap.add_argument('pcap', help='.pcapng captured while you were connected to the server')
    ap.add_argument('--exe', required=True, help='path to your mb_warband.exe (the game is only read, never modified)')
    ap.add_argument('--out', help='output CSV (default: <pcap>_kills.csv)')
    ap.add_argument('--port', type=int, help='server UDP port (default: auto-detect)')
    ap.add_argument('--me', help='part of your own player name (used as the local player)')
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument('--cache', help='pickle file to save/reuse decoded packets (re-run the kill logic without re-decoding)')
    ap.add_argument('--limit', type=int, help='only decode the first N packets (test)')
    a = ap.parse_args(argv)
    from . import emu
    from .pcap import read_pcapng
    from .roster import build_roster, lookup
    from .events import decode, WCODE
    if not emu.load_exe(a.exe):
        print('WARNING: this mb_warband.exe is not the build the tables were made for (Warband 1.174 / NW 1.210); results may be wrong.', file=sys.stderr)
    t = time.time()
    cache = None
    if a.cache and os.path.exists(a.cache):
        import pickle
        recs, ros = pickle.load(open(a.cache, 'rb')); print('loaded %d decoded packets from %s' % (len(recs), a.cache))
    else:
        print('reading capture ...'); ifs, pk = read_pcapng(a.pcap)
        key, flow = find_server_flow(pk, a.port)
        if not flow: sys.exit('could not find the game server flow in the capture (try --port)')
        print('server flow %s:%d -> %s:%d, %d packets' % (key[0], key[1], key[2], key[3], len(flow)))
        if a.limit: flow = flow[:a.limit]
        t0 = flow[0][0]
        ros = build_roster([(ts - t0, pl) for ts, pl in flow])
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
            pickle.dump((recs, ros), open(a.cache, 'wb'))
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
    out = a.out or os.path.splitext(a.pcap)[0] + '_kills.csv'
    known = set(WCODE)
    with open(out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f); w.writerow(['time_s', 'mm:ss', 'killer', 'victim', 'weapon', 'teamkill', 'review', 'killer_slot', 'victim_slot'])
        for e in ev:
            flags = []
            if not isinstance(e['killer'], str) or e['killer'].startswith(('?', 'player#')): flags.append('killer?')
            if not isinstance(e['victim'], str) or e['victim'].startswith(('?', 'player#')): flags.append('victim?')
            if e['weapon'].startswith('class '): flags.append('weapon?')
            if e['killer'] == e['victim'] and e['killer'] not in ('?', '(AI)'): flags.append('self')
            w.writerow([e['time'], '%d:%02d' % divmod(int(e['time']), 60), e['killer'], e['victim'], e['weapon'], e['teamkill'], ' '.join(flags), e['killer_slot'], e['victim_slot']])
    st = collections.defaultdict(lambda: collections.Counter())
    for e in ev:
        st[e['killer']]['kills'] += 1; st[e['victim']]['deaths'] += 1
        if e['teamkill']: st[e['killer']]['teamkills'] += 1
    sp = os.path.splitext(out)[0] + '_players.csv'
    with open(sp, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f); w.writerow(['player', 'kills', 'deaths', 'teamkills'])
        for n, c in sorted(st.items(), key=lambda kv: -kv[1]['kills']): w.writerow([n, c['kills'], c['deaths'], c['teamkills']])
    print('%d kills -> %s\nper player -> %s\ndone in %.0f s' % (len(ev), out, sp, time.time() - t))

if __name__ == '__main__':
    mp.freeze_support(); main()
