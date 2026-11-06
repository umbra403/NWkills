"""Flagbearers: who spawned carrying a flag (regimental colours), per round.

NWE has dedicated '*_flag_bearer' troops: every spawn of one counts (the flag item is filled in when the loadout shows it, else 'unknown').
The rest of this note describes the NW module, where only some NCO troops can pick a flag.

An agent-spawn message (type 5) carries the owner (player slot), a troop id and the spawned loadout (item ids). In the NW module only the NCO
troops (and two French 'colours' troops) can pick a flag; the flag is one of the items in that troop's inventory. A spawn counts as a flagbearer
when the troop can carry a flag AND the loadout contains one of that troop's flag items (troop index = field - 1, item index = id - 1, both
taken from the module's troops.txt / item_kinds1.txt). Loadout ids are not reliable for items outside the troop's own inventory (the
server's item table differs from the module files for armour), which is why the troop is required as well."""
import json, os, collections

def load_table(here, kind='nw'):
    p = os.path.join(here, 'data', 'flag_troops_%s.json' % kind)
    return json.load(open(p)) if os.path.exists(p) else None

def server_kind(recs):
    """'nw' when every loadout id fits 10 bits (NW module), else 'nwe' (the NWE module has more than 1024 items)."""
    mx = 0
    for r in recs:
        for ty, v, w in r['msgs']:
            if ty == 5 and len(v) >= 21: mx = max(mx, max(v[7:18]))
    return 'nw' if mx <= 1023 else 'nwe'

def spawns(recs):
    """Type-5 spawns, repeats of the same spawn removed: [(t, agent, owner_slot, troop_index, [item_index...])]."""
    out = []; last = {}
    for r in recs:
        t = r['t']
        for ty, v, w in r['msgs']:
            if ty != 5 or len(v) < 21 or v[1] <= 0: continue
            a, own, tr = v[1] - 1, v[2] - 1, v[3] - 1
            items = tuple(x - 1 for x in v[7:18] if x)
            key = (a, own, tr, items)
            if key in last and t - last[key] < 8: last[key] = t; continue      # the server repeats a spawn message for a few ticks
            last[key] = t
            out.append((t, a, own, tr, items))
    return out

def flagbearers(recs, table, rounds, round_of, kind_of, namer):
    """-> rows [round, round_kind, player, owner_slot, troop, flag, spawns, first_spawn_s, last_spawn_s, review]"""
    troops = table['troops']; items = table['items']
    agg = collections.OrderedDict()
    for t, a, own, tr, its in spawns(recs):
        info = troops.get(str(tr))
        if not info or own < 0: continue
        got = [m for m in its if m in info['flags']]
        if not got and not table.get('always'): continue
        rn = round_of(rounds, t)
        key = (rn, own, info['name'], items[str(got[0])] if got else 'itm_unknown')
        e = agg.setdefault(key, [0, t, t]); e[0] += 1; e[2] = t
    rows = []
    for (rn, own, tn, fl), (n, t0, t1) in agg.items():
        nm = namer(own, t0)
        rows.append([rn, kind_of(rounds, t0), nm, own, tn.replace('trp_', ''), fl.replace('itm_', ''), n, round(t0, 1), round(t1, 1), 'name?' if nm.startswith(('?', 'player#')) else ''])
    rows.sort(key=lambda r: (r[0], r[2].lower(), r[7]))
    return rows
