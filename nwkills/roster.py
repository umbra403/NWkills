"""Player names are sent in clear as <0x06><player id><u16 length><ASCII name>, at any bit offset. Scan payloads for them.
Slots get reused when players leave/join, so the roster is time-aware: slot -> [(first_s, last_s, name)]."""
import collections, re
PAT = re.compile(rb'\x06(.)([\x03-\x28])\x00', re.S)
PRINT = bytes(range(0x20, 0x7f))
def _shift(b, s):
    return b if s == 0 else (int.from_bytes(b, 'little') >> s).to_bytes(len(b), 'little')
def scan_payload(pl, t, rec):
    seen = set()
    for k in range(8):
        b = _shift(pl, k)
        for m in PAT.finditer(b):
            L = m.group(2)[0]; s = m.end(); chunk = b[s:s+L]
            if len(chunk) == L and not chunk.translate(None, PRINT):
                key = (chunk, m.group(1)[0])
                if key in seen: continue
                seen.add(key)
                r = rec[(chunk.decode(), m.group(1)[0])]
                r[0] += 1; r[1] = min(r[1], t); r[2] = max(r[2], t)
def build_roster(items, min_count=1):
    """items: iterable of (t_seconds, payload). Returns {slot: [(first,last,name,count), ...]} sorted by first sighting (slot = player_id-1)."""
    rec = collections.defaultdict(lambda: [0, 1e18, -1e18])
    for t, pl in items:
        if len(pl) >= 20: scan_payload(pl, t, rec)
    out = collections.defaultdict(list)
    for (name, pid), (c, a, b) in rec.items():
        if c >= min_count and (c >= 2 or len(name) >= 6): out[pid-1].append((a, b, name, c))
    return {s: sorted(v) for s, v in out.items()}
def lookup(roster, slot, t):
    """Name holding this slot at time t: the latest name first seen at or before t (slots are reused when players leave)."""
    v = roster.get(slot)
    if not v: return None
    cur = v[0]
    for x in v:
        if x[0] <= t + 5: cur = x
    return cur[2]
