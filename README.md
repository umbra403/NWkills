# nwkills - read the killfeed from a Wireshark capture (client side only)

Reads the packets your own game client received (UDP, unencrypted) and rebuilds who killed whom, with which weapon
class, and teamkills, split into rounds. No server access needed. Works for NW and NWE (bit widths are calibrated per server automatically).

## Use
1. Capture with Wireshark while playing (save as .pcapng). Start the capture BEFORE joining, so the player list is included.
2. First time only: run `nwkills.exe --setup` (or just run it, or run it on a capture): a short wizard finds or asks for your `mb_warband.exe` and remembers it (`%APPDATA%\nwkills\config.json`). Then: `nwkills.exe capture.pcapng` (or drag the .pcapng onto it). `--exe PATH` still overrides the saved path.
   (Your game exe is only read. It must be the Warband 1.174 / NW 1.210 build, sha256 ff4a28c5...dae13; a warning is printed otherwise.)
3. Output, next to the capture (or from `--out`):
   - `capture_kills.csv` - one row per death/kill.
   - `capture_kills_players.csv` - totals per player, plus per-round columns.
   - `capture_rounds.csv` - the detected rounds.

Options: `--setup`, `--exe PATH`, `--out file.csv`, `--port N` (server UDP port, normally auto-detected), `--me NAME` (part of your own name),
`--jobs N` (CPU cores, default all), `--cache file.pkl` (keep decoded packets so you can re-run the kill logic quickly), `--limit N` (test on the first N packets).
A 2-hour capture (~115k packets) takes roughly 9 minutes on 2 cores.

## Kills file columns
`round, round_kind, time_s, mm:ss, killer, victim, weapon, teamkill, death_type, respawn_s, review, killer_slot, victim_slot`
- `time_s`: seconds since capture start (video time = time_s + your capture/recording offset).
- `weapon`: firearm: musket/rifle | firearm: pistol | melee: bayonet/spear | melee: sword/sabre | melee: couched lance (cavalry) | cavalry: horse charge (rider hit) | melee: hammer/mallet | melee: mace/club? | fists (punch) | artillery: cannonball / shrapnel/canister / explosion | headshot. `headshot` is also what weapon code 0 shows, which includes players leaving the server (see below). Confirmed against video: horse charge (class 3: white horse with an orange burst; the killer agent is the horse, so the killer name is often `?` or stale), hammer/mallet (class 19: handle with a square head), couched lance (class 1: horse and rider icon), fists (class 2: fist-with-burst icon; a killer-less version is shown when killer = victim), cannonball (black ball icon), shrapnel/canister (spray of small balls). `mace/club?` (class 16) is a single sighting.
- `teamkill`: `yes` when the killer's score went down at that kill.
- `respawn_s`: seconds until that victim gets a new agent (normal ~11 s; blank = none within 2 min, e.g. left).
- `review`: flags to check - `killer?` / `victim?` (player could not be resolved), `before-sync` (first ~90 s, before the server announced agent owners), `name-from-later-data(killer|victim)` (name filled in from later sightings of the same agent in this capture), `weapon?` (unknown weapon class, shown as `class N`), `suicide?`, `self`. `(AI)` = bot, `(world)` = no killer.

## Death types (`death_type`)
| type | meaning |
|---|---|
| `kill` | normal blow kill |
| `no-blow death (mount?, not counted)` | known killer but no blow data. Seen on video: no killfeed line (horse deaths). Not counted in any total |
| `horse death (player-owned mount)` | victim agent is a player's horse (no rider properties). Not a player death; not counted in any total |
| `AI/horse death` | victim is a bot or unowned mount. Not a player death; counted as the killer's `ai_kills` |
| `world (left server/fall)` | killer-less death with weapon code 0 (shown as `headshot`). A player leaving the server looks like this, hence the clusters at the end of events |
| `self-inflicted (suicide/fall?)` | killer = victim (class 2, shown in game as a killer-less fist-icon line). A suicide drops the score by 1 (counted as a teamkill); an admin slay (`Slayed Player X` in chat) does not drop the score. Not separated into labels yet |
| `non-blow death (leave/class change?)` | death message without a blow and no known killer |

The exact causes inside the last few types are still provisional (no capture with known fall / drown / class change events yet).

## Players file
- `kills` = kills minus teamkills over all non-warm-up rounds (like the scoreboard). `deaths`, `teamkills` over the same rounds. `ai_kills` = bot kills.
- `score_at_capture_start` / `score_at_capture_end`: scoreboard values the server sends when you join and on every change. `score_gap` = scoreboard change minus what was recorded as kills/teamkills (0 = nothing missed; positive = score we did not see as kills, e.g. kills before you joined). Rounds where a score reset inside the round (player rejoined / slot reused) are skipped.
- Per round, four columns `R<n>(<kind>)_kills|_deaths|_teamkills|_score_gap`. Per-round `kills` do NOT subtract teamkills (plain counts). Warm-up rounds keep their columns but are left out of the overall totals.
- Not counted in totals: horse deaths, `no-blow death` rows, deaths of `(AI)` victims (those go to the killer's `ai_kills`).

## Rounds file and round kinds
`round, start_s, end_s, length_s, started_by, tickets_zero_at_s, tickets_zero_team, kills_after_tickets_zero, kind, death_msgs, method, review`
Kinds: `pre-live` (from capture start until the first detected start), `warm-up` (not live; excluded from totals), `live`.

How round starts are found, in order of preference:
- **Server messages (preferred):** the server's own chat lines "Changed the map to ..." (map load) and "Has reset the Map." (admin reset, also a type-41 marker). Admin pattern: map change = warm-up round (friendly fire off), then reset = LIVE round.
- **Restarts with no reset line:** the server prints "Friendly fire is now on" a fixed delay (parsed from the "Friendly fire will turn back on after N seconds" line; 30 s on NWE, 20 s early on Wed) after every round start; start = that time minus the delay. This found the Thursday restarts at 3:49 / 18:18 and the Friday one at 5:54.
- **Warm-up rule:** a segment is a warm-up when a map change is followed by a reset, when two resets come less than 60 s apart, or when an admin says "reset and live" (also "rest/restart ... live") inside it.
- **Tickets (NWE):** the team-ticket event adds `tickets_zero_at_s` (round decided) and `kills_after_tickets_zero`.
- **Fallback** (no such chat lines): activity lulls and map-load signals.

## Weapon classes (from the exe)
The client picks the killfeed icon with a jump table on the 5-bit weapon class: 0 headshot, 1 couched lance, 2 punch, 3 horse impact, 4 bow, 5 crossbow (the module draws muskets with it), 6 thrown axe, 7 thrown knife, 8 javelin, 9 thrown stone, 10 pistol, 11 musket, 12 one-handed sword, 13 two-handed sword, 14 one-handed axe, 15 two-handed axe, 16 blunt (mace/club), 17 spear (bayonet), 18 morningstar, 19 maul (hammer), 20-26 custom icons 1-7 (20 cannonball, 21 canister, 22 explosion seen on video). Values above 26 draw no icon.

## Names
Slots are reused. When a player's name later appears (repeatedly) in a different slot, the old slot is treated as unknown from then on, and the new occupant's name is looked up from later data in the capture (otherwise the old name stuck to whoever took the slot). Near-simultaneous repeats of the same death message (same victim within 6 s) are dropped.

## Known limits
- About 96% of kills have both names resolved; the rest are flagged in `review`.
- Weapon classes come from the exe's killfeed icon table (27 classes, 0-26; see below). Labels with an `(ico_...)` suffix come from the table only (the art has not been seen on video) and carry the `weapon?` flag. Class 23 (`ico_custom_4`) is a module-defined icon; all 4 sightings are killer = victim. Class 3 (horse charge) kills usually have no killer name: the killer agent is the horse, not the rider.
- Built for exactly the exe build above; `nwkills/data/ins_subset.pkl` is the instruction trace the decoder needs (generated from that exe).
Push this folder to a repo; the workflow `build-windows` produces `nwkills.exe` as an artifact. Local: `python nwkills.py ...` (Python 3.10+, no dependencies).
