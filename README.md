# nwkills - read the killfeed from a Wireshark capture (client side only)

Reads the packets your own game client received (UDP, unencrypted) and rebuilds who killed whom, with which weapon
class, and teamkills, split into rounds. No server access needed. Works for NW and NWE (bit widths are calibrated per server automatically).

## Use
1. Capture with Wireshark while playing (save as .pcapng). Start the capture BEFORE joining, so the player list is included.
2. First time only: run `nwkills.exe --setup` (or just run it, or run it on a capture): a short wizard finds or asks for your `mb_warband.exe` and remembers it (`%APPDATA%\nwkills\config.json`). Then: `nwkills.exe capture.pcapng` (or drag the .pcapng onto it). `--exe PATH` still overrides the saved path.
   (Your game exe is only read. It must be the Warband 1.174 / NW 1.210 build, sha256 ff4a28c5...dae13; a warning is printed otherwise.)
3. Output, next to the capture (or from `--out`):
   - `[capture]_kills.csv` - one row per death/kill.
   - `[capture]_kills_players.csv` - totals per player, plus per-round columns.
   - `[capture]_rounds.csv` - the detected rounds.

Options: `--setup`, `--exe PATH`, `--out file.csv`, `--port N` (server UDP port, normally auto-detected), `--me NAME` (part of your own name),
`--jobs N` (CPU cores, default all), `--cache file.pkl` (keep decoded packets so you can re-run the kill logic quickly), `--limit N` (test on the first N packets).
A 2-hour capture (~115k packets) takes roughly 9 minutes on 2 cores.

## Kills file columns
`round, round_kind, time_s, mm:ss, killer, victim, weapon, teamkill, death_type, respawn_s, review, killer_slot, victim_slot`
- `time_s`: seconds since capture start (video time = time_s + your capture/recording offset).
- `weapon`: firearm: musket/rifle | firearm: pistol | melee: bayonet/spear | melee: sword/sabre | artillery: cannonball / shrapnel/canister / explosion | headshot. `headshot` is also what weapon code 0 shows, which includes players leaving the server (see below).
- `teamkill`: `yes` when the killer's score went down at that kill.
- `respawn_s`: seconds until that victim gets a new agent (normal ~11 s; blank = none within 2 min, e.g. left).
- `review`: flags to check - `killer?` / `victim?` (player could not be resolved), `before-sync` (first ~90 s, before the server announced agent owners), `name-from-later-data(killer|victim)` (name filled in from later sightings of the same agent in this capture), `weapon?` (unknown weapon class, shown as `class N`), `suicide?`, `self`. `(AI)` = bot, `(world)` = no killer.

## Death types (`death_type`)
| type | meaning |
|---|---|
| `kill` | normal blow kill |
| `kill (no blow detail)` | known, different killer but the blow data is missing. Mostly the death of a player-owned horse is now split out (below), so what remains is rare |
| `horse death (player-owned mount)` | victim agent is a player's horse (no rider properties). Not a player death; not counted in any total |
| `AI/horse death` | victim is a bot or unowned mount. Not a player death; counted as the killer's `ai_kills` |
| `world (left server/fall)` | killer-less death with weapon code 0 (shown as `headshot`). A player leaving the server looks like this, hence the clusters at the end of events |
| `self-inflicted (suicide/fall?)` | killer = victim (class 2). A suicide drops the score by 1 (counted as a teamkill); an admin slay (`Slayed Player X` in chat) does not drop the score. Not separated into labels yet |
| `non-blow death (leave/class change?)` | death message without a blow and no known killer |

The exact causes inside the last few types are still provisional (no capture with known fall / drown / class change events yet).

## Players file
- `kills` = kills minus teamkills over all non-warm-up rounds (like the scoreboard). `deaths`, `teamkills` over the same rounds. `ai_kills` = bot kills.
- `score_at_capture_start` / `score_at_capture_end`: scoreboard values the server sends when you join and on every change. `score_gap` = scoreboard change minus what was recorded as kills/teamkills (0 = nothing missed; positive = score we did not see as kills, e.g. kills before you joined). Rounds where a score reset inside the round (player rejoined / slot reused) are skipped.
- Per round, four columns `R<n>(<kind>)_kills|_deaths|_teamkills|_score_gap`. Per-round `kills` do NOT subtract teamkills (plain counts). Warm-up rounds keep their columns but are left out of the overall totals.
- Not counted in totals: horse deaths, deaths of `(AI)` victims (those go to the killer's `ai_kills`).

## Rounds file and round kinds
`round, start_s, end_s, length_s, started_by, tickets_zero_at_s, tickets_zero_team, kills_after_tickets_zero, kind, death_msgs, method, review`
Kinds: `pre-live` (from capture start until the first detected start), `warm-up` (not live; excluded from totals), `live`.

How round starts are found, in order of preference:
- **Server messages (preferred):** the server's own chat lines "Changed the map to ..." (map load) and "Has reset the Map." (admin reset, also a type-41 marker). Admin pattern: map change = warm-up round (friendly fire off), then reset = LIVE round.
- **Restarts with no reset line:** the server prints "Friendly fire is now on" a fixed delay (parsed from the "Friendly fire will turn back on after N seconds" line; 30 s on NWE, 20 s early on Wed) after every round start; start = that time minus the delay. This found the Thursday restarts at 3:49 / 18:18 and the Friday one at 5:54.
- **Warm-up rule:** a segment is a warm-up when a map change is followed by a reset, when two resets come less than 60 s apart, or when an admin says "reset and live" (also "rest/restart ... live") inside it.
- **Tickets (NWE):** the team-ticket event adds `tickets_zero_at_s` (round decided) and `kills_after_tickets_zero`.
- **Fallback** (no such chat lines): activity lulls and map-load signals.

## Known limits
- About 96% of kills have both names resolved; the rest are flagged in `review`.
- Classes 1, 3, 16, 19, 23 and a few others are not identified yet (shown as `class N`).
- Built for exactly the exe build above; `nwkills/data/ins_subset.pkl` is the instruction trace the decoder needs (generated from that exe).