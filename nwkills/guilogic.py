# nwkills - read the Mount & Blade: Warband Napoleonic Wars killfeed from a Wireshark capture.
# Copyright (C) 2026 the nwkills authors. Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""Everything the GUI needs that is not Qt: reading result CSVs, sort keys, filters, round chips, copy/export text, packet summaries.
Kept separate so it can be tested without a display."""
import bisect, collections, csv, os, re

# ---------------------------------------------------------------- tables
def read_csv_table(path):
    """-> (headers, rows) with every cell a string."""
    with open(path, newline='', encoding='utf-8-sig') as f:
        rd = csv.reader(f)
        headers = next(rd, [])
        rows = [r + [''] * (len(headers) - len(r)) for r in rd if r]
    return headers, rows

def write_csv_table(path, headers, rows):
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f); w.writerow(headers); w.writerows(rows)

_NUM = re.compile(r'^-?\d+(\.\d+)?$')
_MMSS = re.compile(r'^\d+:\d\d$')
def cell_key(v):
    """Sort key for one cell: numbers and mm:ss by value, text case-insensitively, empty cells last."""
    s = v.strip()
    if _MMSS.match(s):
        m, sec = s.split(':'); return (0, int(m) * 60 + int(sec), '')
    if _NUM.match(s): return (0, float(s), '')
    if s == '': return (2, 0, '')
    return (1, 0, s.lower())

def is_numeric(v): return bool(_NUM.match(v.strip()) or _MMSS.match(v.strip()))

def numeric_columns(headers, rows):
    out = set()
    for c in range(len(headers)):
        vals = [r[c] for r in rows if r[c].strip() != '']
        if vals and all(is_numeric(v) for v in vals): out.add(c)
    return out

def compile_filters(texts, ignore_case=True):
    """texts: {column: pattern}. -> ({column: compiled regex}, [columns with an invalid pattern]). Empty patterns are skipped."""
    ok, bad = {}, []
    for c, t in texts.items():
        if not t: continue
        try: ok[c] = re.compile(t, re.I if ignore_case else 0)
        except re.error: bad.append(c)
    return ok, bad

def row_passes(row, filters):
    return all(rx.search(row[c]) for c, rx in filters.items())

# ---------------------------------------------------------------- round / kind chips
KIND_CHIPS = [('live', 'Live', {'live'}), ('pre', 'Pre-live', {'pre-live'}),
              ('prelive', 'Pre-live + live', {'pre-live', 'live'}), ('warm', 'Warm-up', {'warm-up'})]

def chip_predicate(headers, kinds, rounds):
    """kinds: set of KIND_CHIPS ids, rounds: set of round numbers as strings. A row passes if it matches ANY selected chip; nothing selected = everything."""
    if not kinds and not rounds: return None
    try: ri, ki = headers.index('round'), headers.index('round_kind')
    except ValueError: return None
    allowed = set()
    for cid, _label, ks in KIND_CHIPS:
        if cid in kinds: allowed |= ks
    return lambda row: row[ki] in allowed or row[ri] in rounds

# ---------------------------------------------------------------- column groups (Players table)
_ROUND_COL = re.compile(r'^(R[^_]*)_(.+)$')

def column_groups(headers):
    """Groups of columns to show or hide together: -> [(label, [column indexes])], only groups with at least two columns.
    The Players table has a total and one column per round for every measure ('kills', 'R3(live)_kills', ...): one group per measure, one per round,
    and the per-round columns / the totals as a whole. The first column (the player name) is in no group."""
    by_metric, by_round, totals, per_round = {}, {}, [], []
    for i, h in enumerate(headers):
        if i == 0: continue
        m = _ROUND_COL.match(h)
        if m:
            by_round.setdefault(m.group(1), []).append(i); per_round.append(i)
            by_metric.setdefault(m.group(2), []).append(i)
        else:
            totals.append(i)
            by_metric.setdefault('score_at_capture' if h.startswith('score_at_capture') else h, []).append(i)
    if not per_round: return []
    out = [('All %s columns' % k, v) for k, v in by_metric.items()]
    out += [('Round %s' % k, v) for k, v in by_round.items()]
    out += [('All per-round columns', per_round), ('All total columns', totals)]
    return [(l, v) for l, v in out if len(v) >= 2]

def group_state(hidden, members):
    """0 = none of the group's columns shown, 2 = all shown, 1 = some (a Qt check state)."""
    shown = sum(1 for i in members if i not in hidden)
    return 0 if shown == 0 else (2 if shown == len(members) else 1)

# ---------------------------------------------------------------- copy / export text
def _clean(v): return re.sub(r'[\t\r\n]+', ' ', v)

def cells_to_tsv(headers, grid, with_header=False):
    """grid: list of rows of cell strings (None = not selected). Tab separated, which Excel, Sheets and LibreOffice paste into columns."""
    lines = []
    if with_header: lines.append('\t'.join(_clean(h) for h in headers))
    for r in grid: lines.append('\t'.join('' if v is None else _clean(v) for v in r))
    return '\n'.join(lines)

# ---------------------------------------------------------------- command line preview
def command_line(o):
    c = 'nwkills "%s" --out "%s"' % (o.get('pcap', ''), o.get('out', ''))
    if o.get('port'): c += ' --port %d' % o['port']
    if o.get('me'): c += ' --me "%s"' % o['me']
    c += ' --jobs %d' % o.get('jobs', 1)
    if o.get('cache'): c += ' --cache "%s"' % o['cache']
    if o.get('limit'): c += ' --limit %d' % o['limit']
    return c

# ---------------------------------------------------------------- progress
STAGES = [('read', 'Reading capture', 10), ('roster', 'Calibrating for this server', 5), ('decode', 'Decoding packets', 55),
          ('events', 'Reading kill events', 15), ('rounds', 'Detecting rounds and flagbearers', 5), ('players', 'Scores and per-player totals', 10)]
BUSY = {'roster', 'events', 'rounds', 'players'}      # stages that report no fraction

def overall_progress(stage, frac):
    """-> (label, overall 0..100, stage fraction 0..1 or None when the stage has no measurable progress)"""
    if stage == 'done': return 'Finished', 100.0, 1.0
    done = 0.0
    for sid, label, w in STAGES:
        if sid == stage: return label, done + w * (0.0 if sid in BUSY else frac), (None if sid in BUSY else frac)
        done += w
    return stage, done, None

# ---------------------------------------------------------------- packets
def packet_info(pl):
    """Decode the message list of one server->client payload for display. Needs the decoder profile to be set."""
    from . import decoder
    queued = len(pl) > 7 and pl[7] == 0
    q = pl[:7] + pl[8:] if queued else pl
    n = q[7] - 1 if len(q) > 7 else 0
    msgs = []
    if n > 0:
        try: _r, _cur, msgs = decoder.msgs_only(q)
        except Exception: msgs = []
    return dict(queued=queued, n=n, msgs=msgs, types=type_summary([m[2] for m in msgs]))

def type_summary(types):
    c = collections.Counter(types)
    return ' '.join(('%d×%d' % (t, k) if k > 1 else str(t)) for t, k in sorted(c.items()))

def hexdump(b, width=16):
    out = []
    for i in range(0, len(b), width):
        ch = b[i:i + width]
        out.append('%04x  %-*s  %s' % (i, width * 3 - 1, ' '.join('%02x' % x for x in ch), ''.join(chr(x) if 32 <= x < 127 else '.' for x in ch)))
    return '\n'.join(out)

def packet_at_time(times, t):
    """Index of the packet at (or just before) time t, for 'show this kill in the packet list'."""
    i = bisect.bisect_left(times, t - 0.05)
    return min(i, len(times) - 1)

# ---------------------------------------------------------------- players table derived from kill rows
def _int(v):
    try: return int(v)
    except (TypeError, ValueError): return None

def round_label(n, kind): return 'R%s' % n + ('(%s)' % kind if kind else '')

def player_totals(kh, krows, ph, prows, net=True, exclude_warm=True, all_players=False):
    """Players table computed from the kill rows given (the rows the Kills tab currently shows).
    Counting rules are the ones the converter uses for its own players file: admin slays, mount deaths and no-blow deaths are not counted;
    AI deaths only credit the killer's ai_kills; a teamkill is not a kill. net=True: kills = kills - teamkills (as the scoreboard), also per round.
    exclude_warm: leave warm-up rounds out (what the converter does for its totals). all_players: also list players from the converter's file that have no row.
    Columns that need the scoreboard (score at capture start/end, score_gap) come from the converter's players file for the rounds that are included.
    -> (headers, rows)"""
    ix = {h: i for i, h in enumerate(kh)}
    R, RK, KI, VI, TKI, DT = (ix[h] for h in ('round', 'round_kind', 'killer', 'victim', 'teamkill', 'death_type'))
    c = collections.defaultdict(collections.Counter)
    kinds = {}
    for row in krows:
        if exclude_warm and row[RK] == 'warm-up': continue
        rn, dt = row[R], row[DT]
        kinds[rn] = row[RK]
        def bump(name, key): c[name][key] += 1; c[name][(rn, key)] += 1
        if dt.startswith(('admin', 'horse death', 'no-blow death')): continue
        if dt == 'AI/horse death':
            if row[KI] not in ('?', '(AI)', '(world)'): bump(row[KI], 'ai_kills')
            continue
        tk = row[TKI] != ''
        if dt == 'kill' and not tk and row[KI] != '(runaway horse)': bump(row[KI], 'kills')
        bump(row[VI], 'deaths')
        if tk: bump(row[KI], 'teamkills')
    rounds = sorted(kinds, key=lambda s: (_int(s) is None, _int(s) or 0, s))
    pidx = {h: i for i, h in enumerate(ph)}
    old = {r[0]: r for r in prows}
    names = set(c)
    if all_players: names |= set(old)
    def val(n, key, rn=None):
        v = c[n][key] if rn is None else c[n][(rn, key)]
        return v - (c[n]['teamkills'] if rn is None else c[n][(rn, 'teamkills')]) if (key == 'kills' and net) else v
    heads = ['player', 'kills', 'deaths', 'teamkills', 'ai_kills', 'score_at_capture_start', 'score_at_capture_end', 'score_gap']
    cols = []
    for rn in rounds:
        lab = round_label(rn, kinds[rn])
        for k in ('kills', 'deaths', 'teamkills', 'score_gap'): cols.append((rn, k)); heads.append('%s_%s' % (lab, k))
    rows = []
    for n in names:
        o = old.get(n)
        gaps = []
        per = []
        for rn, k in cols:
            if k == 'score_gap':
                g = o[pidx['%s_score_gap' % round_label(rn, kinds[rn])]] if o and '%s_score_gap' % round_label(rn, kinds[rn]) in pidx else ''
                per.append(g)
                if _int(g) is not None: gaps.append(int(g))
            else: per.append(str(val(n, k, rn)))
        rows.append([n, str(val(n, 'kills')), str(c[n]['deaths']), str(c[n]['teamkills']), str(c[n]['ai_kills']),
                     o[pidx['score_at_capture_start']] if o else '', o[pidx['score_at_capture_end']] if o else '', str(sum(gaps)) if gaps else ''] + per)
    rows.sort(key=lambda r: (-int(r[1]), r[0].lower()))
    return heads, rows
