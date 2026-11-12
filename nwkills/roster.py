"""Player names are sent in clear as <0x06><player id><u16 length><ASCII name>, at any bit offset. Scan payloads for them.
Slots get reused when players leave/join, so the roster is time-aware: slot -> [(first_s, last_s, name)]."""
import collections, re
PAT = re.compile(rb'\x06(.)([\x03-\x28])\x00', re.S)
PRINT = bytes(range(0x20, 0x7f))
def _shift(b, s):
    return b if s == 0 else (int.from_bytes(b, 'little') >> s).to_bytes(len(b), 'little')
PAT_ALT = re.compile(rb'[\x03\x43\x83\xc3](.)([\x03-\x28])\x00', re.S)     # same record under another message type (seen in one recording where the other had 0x06)
def scan_payload(pl, t, rec, pat=None, only=None):
    seen = set()
    for k in range(8):
        b = _shift(pl, k)
        for m in (pat or PAT).finditer(b):
            L = m.group(2)[0]; s = m.end(); chunk = b[s:s+L]
            if len(chunk) == L and not chunk.translate(None, PRINT):
                if only is not None and chunk.decode() not in only: continue
                key = (chunk, m.group(1)[0])
                if key in seen: continue
                seen.add(key)
                r = rec[(chunk.decode(), m.group(1)[0])]
                r[0] += 1; r[1] = min(r[1], t); r[2] = max(r[2], t)
def _plausible_single(name):
    """A name seen in only one packet is accepted only if it looks like a real player name. Random bytes that happen to match the
    <0x06><id><length> pattern give strings like m.\"_\\Dt, which used to take over a slot (and all its kills) in one capture."""
    if len(name) < 6 or '"' in name or '\\' in name: return False
    al = sum(c.isalnum() for c in name)
    return al >= 5 and al >= 0.6 * len(name)
def build_roster(items, min_count=1):
    """items: iterable of (t_seconds, payload). Returns {slot: [(first,last,name,count), ...]} sorted by first sighting (slot = player_id-1)."""
    rec = collections.defaultdict(lambda: [0, 1e18, -1e18])
    items = list(items)
    for t, pl in items:
        if len(pl) >= 20: scan_payload(pl, t, rec)
    # Second pass: the join record of a player can reach one recording as another message type than the other (the same bytes after a 0x03
    # header instead of 0x06). Chat lines use that header too, so such a record is only believed for a name already seen as a player name.
    known = set(n for (n, pid), (c, a, b) in rec.items() if c >= 2 or _plausible_single(n))
    items = list(items)
    if known:
        for t, pl in items:
            if len(pl) >= 20: scan_payload(pl, t, rec, PAT_ALT, known)
    out = collections.defaultdict(list)
    for (name, pid), (c, a, b) in rec.items():
        if c >= min_count and (c >= 2 or _plausible_single(name)): out[pid-1].append((a, b, name, c))
    return {s: sorted(v) for s, v in out.items()}
def lookup(roster, slot, t):
    """Name holding this slot at time t: the latest name first seen at or before t (slots are reused when players leave)."""
    v = roster.get(slot)
    if not v: return None
    cur = v[0]
    for x in v:
        if x[0] <= t + 5: cur = x
    return cur[2]

def retire_moved(roster):
    """A name can only hold one slot at a time. When a name first shows up in another slot later, its old slot is no longer
    that player's from that moment (they left and rejoined); mark it unknown ('' entry) so a stale name is not reused for
    whoever took the slot. Returns {slot: time_from_which_the_name_is_unknown}."""
    firsts = collections.defaultdict(list)
    for sl, v in roster.items():
        for x in v:
            if x[2]: firsts[x[2]].append((x[0], sl, x[3]))
    since = {}
    for nm, lst in firsts.items():
        lst.sort()
        for (f1, s1, c1), (f2, s2, c2) in zip(lst, lst[1:]):
            if s1 == s2 or (c2 < 2 and not _plausible_single(nm)): continue      # a one-off sighting can be a coincidental byte pattern: it must at least look like a real name
            cur = [x for x in roster[s1] if x[0] <= f2 + 5]
            if cur and cur[-1][2] == nm:      # also when another name takes the slot later: the stretch in between is unknown
                if not any((not x[2]) and abs(x[0] - f2) < 1 for x in roster[s1]):
                    roster[s1] = sorted(roster[s1] + [(f2, f2, '', 0)])
                since[s1] = min(since.get(s1, 1e18), f2)
    return since

def fill_roster(roster, items, need_slots, min_clusters=2, gap=10.0, since=None, early=()):
    """Names that were never announced with the usual join record (e.g. you joined later) still show up next to the player id in
    chat/other records. For slots that need a name, take the printable string that repeats at >=2 separate moments."""
    since = since or {}
    early = set(early)       # slots whose first known name is provably a later occupant (that name held another slot before): look for an earlier occupant, keep the later names
    need = [s for s in need_slots if s is not None and s >= 0 and (s not in roster or s in since or s in early)]
    if not need: return roster
    cls = bytes(sorted(set(s + 1 for s in need if s + 1 < 256)))
    if not cls: return roster
    pat = re.compile(b'([' + b''.join(b'\\x%02x' % c for c in cls) + b'])([\\x04-\\x28])\\x00', re.S)
    seen = collections.defaultdict(list)                     # (pid, name) -> times
    for t, pl in items:
        if len(pl) < 20: continue
        done = set()
        for k in range(8):
            b = _shift(pl, k)
            for m in pat.finditer(b):
                if t < since.get(m.group(1)[0] - 1, -1): continue
                L = m.group(2)[0]; ch = b[m.end():m.end()+L]
                if len(ch) == L and not ch.translate(None, PRINT):
                    nm = ch.decode()
                    if sum(c.isalnum() for c in nm) >= 4 and (m.group(1)[0], nm) not in done:
                        done.add((m.group(1)[0], nm)); seen[(m.group(1)[0], nm)].append(t)
    for (pid, nm) in list(seen):
        if pid - 1 in early and pid - 1 not in since and roster.get(pid - 1):
            if min(seen[(pid, nm)]) >= roster[pid - 1][0][0] - 1 or nm in [x[2] for x in roster[pid - 1]]: del seen[(pid, nm)]       # only names sighted before the first known one are new
    best = {}
    for (pid, nm), ts in seen.items():
        ts.sort(); clusters = 1 + sum(1 for a, b in zip(ts, ts[1:]) if b - a > gap)
        tagged = (' ' not in nm) and len(nm) >= 8 and ('_' in nm or '[' in nm)
        if clusters >= min_clusters or tagged:
            sc = (min(clusters, 2) if not tagged else clusters + 1, 1 if tagged else 0, len(ts))
            if pid not in best or sc > best[pid][0]: best[pid] = (sc, nm, ts[0], ts[-1], len(ts))
    for pid, (sc, nm, a, b, c) in best.items():
        old = roster.get(pid - 1, [])
        if pid - 1 in early and pid - 1 not in since:
            roster[pid - 1] = sorted(old + [(a, b, nm, c)])
        else:
            roster[pid - 1] = sorted([x for x in old if pid - 1 in since] + [(a, b, nm, c)])
    return roster
