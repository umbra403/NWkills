# nwkills - read the killfeed from a Wireshark capture (client side only)

Reads the packets your own game client received (UDP, unencrypted) and rebuilds who killed whom, with which weapon
class, and teamkills, split into rounds. No server access needed. Works for NW and NWE (bit widths are calibrated per server automatically).

## Use
1. Capture with Wireshark while playing (save as .pcapng). Start the capture BEFORE joining, so the player list is included.
2. Run `nwkills.exe capture.pcapng` (or drag the .pcapng onto it). No game files are needed: the packet reader is plain Python (`nwkills/nreader.py`, a table of message layouts), so nothing from the game ships with the tool.
3. Output, next to the capture (or from `--out`):
   - `capture_kills.csv` - one row per death/kill.
   - `capture_kills_players.csv` - totals per player, plus per-round columns.
   - `capture_rounds.csv` - the detected rounds.
   - `capture_flagbearers.csv` - who spawned carrying a flag, per round.

Options: `--out file.csv`, `--port N` (server UDP port, normally auto-detected), `--me NAME` (part of your own name),
`--jobs N` (CPU cores, default all), `--cache file.pkl` (keep decoded packets so you can re-run the kill logic quickly), `--limit N` (test on the first N packets).
A 2-hour capture (~115k packets) takes about 1-3 minutes.

## The window (`nwkills-gui.exe`)
Open or drop a `.pcapng`; the **Packets** tab lists the server's packets Wireshark-style (regex display filter, message tree and hex dump of the selected packet; "Index message types" lets the filter search message types too).
**Options** mirrors the command line (port, your name, worker processes, cache, packet limit, output folder) and shows the equivalent command. **Convert** runs the same pipeline as the command line, with a stage bar and an overall bar, and writes the same CSV files.
**Results** has one tab per CSV. Click a column label to sort; the box under each label is a regular expression for that column (all boxes must match; the "Ignore case" box applies to all). On Kills, the round chips pick any combination of Live, Pre-live, Pre-live + live, Warm-up and single rounds.
**Players is computed from whatever the Kills tab shows**: round chips and column filters there decide which kills are counted, and which per-round columns appear. With no round chosen, warm-up rounds are left out, as in the CSV. The "Teamkills count negatively" box (on by default) makes kills = kills − teamkills, in the totals and per round; off, kills are kills only. Score columns come from the scoreboard data in the CSV for the included rounds. Unfiltered, the table equals the CSV's totals.
Select cells (drag, Shift/Ctrl, or the row numbers) and press Ctrl+C: they are copied as tab-separated text that pastes into Excel, Sheets or a CSV editor ("Copy with headers" adds the header row). "Export shown rows" saves exactly what the table shows, in its current order and columns; "Show in Packets" jumps from a kill to the packet list.
Built with PySide6 (LGPL-3.0). From source: `pip install -r requirements-gui.txt`, then `python nwkills_gui.py [capture.pcapng]`.

## Kills file columns
`round, round_kind, time_s, mm:ss, killer, victim, weapon, teamkill, death_type, respawn_s, review, killer_slot, victim_slot`
- `time_s`: seconds since capture start (video time = time_s + your capture/recording offset).
- `weapon`: firearm: musket/rifle | firearm: pistol | melee: bayonet/spear | melee: sword/sabre | melee: couched lance (cavalry) | cavalry: horse charge (rider hit) | melee: hammer/mallet | melee: mace/club? | fists (punch) | artillery: cannonball / shrapnel/canister / explosion | headshot. `headshot` is also what weapon code 0 shows, which includes players leaving the server (see below). Confirmed against video: horse charge (class 3: white horse with an orange burst; the killer agent is the horse, so the killer name is often `?` or stale), hammer/mallet (class 19: handle with a square head), couched lance (class 1: horse and rider icon), fists (class 2: fist-with-burst icon; a killer-less version is shown when killer = victim), cannonball (black ball icon), shrapnel/canister (spray of small balls). `mace/club?` (class 16) is a single sighting.
- `teamkill`: `yes` when killer and victim were on the same team. The team of each agent is read from its spawn message (the same test the game client makes before it prints "killed teammate"). When a spawn message of either agent is not in the capture (agents already present at the start), the killer's score change decides instead (-1 = teamkill). Suicides and falls use the score change. The `review` flag `teamkill?(score disagrees)` marks a single kill where the teams say one thing and the killer's score change the other (rare: the check is skipped when the score was read against a baseline from an earlier round, or when the same player made two kills within 3 s). Volleys (artillery, canister) now get an exact verdict per kill; the old `teamkill?(burst)` guess only remains for volleys whose spawn messages are missing.
- Horse-charge kills (`cavalry: horse charge`): like the game client, the killer is the rider of the horse. The rider is read from the packets (a rider is spawned together with its horse; a later mount or dismount message changes it). If the capture holds neither, the one player whose score rises by 1 at that moment is taken (`name-from-later-data(killer-from-score)`). A horse nobody rides and nobody's score claims shows `(runaway horse)` with the review flag `runaway-horse` and counts as nobody's kill (the victim's death still counts); `(AI)` if nothing is known.
- `respawn_s`: seconds until that victim gets a new agent (normal ~11 s; blank = none within 2 min, e.g. left).
- `review`: flags to check - `killer?` / `victim?` (player could not be resolved), `before-sync` (name unresolved in the first ~90 s of the capture), `name-from-later-data(killer|victim)` (name filled in from later sightings of the same agent in this capture), `weapon?` (unknown weapon class, shown as `class N`), `self`. `(AI)` = bot, `(world)` = no killer.

## Death types (`death_type`)
| type | meaning |
|---|---|
| `kill` | normal blow kill |
| `no-blow death (mount?, not counted)` | known killer but no blow data. Seen on video: no killfeed line (horse deaths). Not counted in any total |
| `horse death (player-owned mount)` | victim agent is a player's horse (no rider properties). Not a player death; not counted in any total |
| `AI/horse death` | victim is a bot or unowned mount. Not a player death; counted as the killer's `ai_kills` |
| `world (team swap / left server)` | killer-less death with weapon code 0 (shown as `headshot`). Confirmed for your own team swap (test capture with chat markers); a player leaving the server looks the same, hence the clusters at the end of events. Your own disconnect death is not in the capture |
| `self-inflicted: fall` | killer = victim with weapon class 0. Confirmed by chat markers (2 falls). Score -1 |
| `self-inflicted: drowning` | killer = victim with weapon class 23 (icon 4). Confirmed on video. Score -1 |
| `self-inflicted: suicide (no admin line)` | killer = victim with weapon class 2 (fist icon). Confirmed for suicide (2 cases); admin slays use the same packets and icon; they are told apart only by the server's `Slayed Player` line (see below), so this label means no such line was seen. Score -1 (counted as a teamkill) |
| `non-blow death (leave/class change?)` | death message without a blow and no known killer |

The exact causes inside the last few types are still provisional (no capture with known fall / drown / class change events yet).

## Players file
- `kills` = kills minus teamkills over all non-warm-up rounds (like the scoreboard). `deaths`, `teamkills` over the same rounds. `ai_kills` = bot kills.
- `score_at_capture_start` / `score_at_capture_end`: scoreboard values the server sends when you join and on every change. `score_gap` = scoreboard change minus what was recorded as kills/teamkills (0 = nothing missed; positive = score we did not see as kills, e.g. kills before you joined). Scores are read only from packets that parsed to the end (the big map-change blocks give garbage values). The scoreboard reset after a round start can land more than a minute late (seen: 64 s); when the score jumps to 0 (or -1 / 1) by 2 or more in the first 2 minutes of a round, counting starts from that value. A player whose score was never re-sent after the reset (first value of the round fits counting from 0, not from last round's value) is counted from 0. Rounds with a jump of more than 15 inside the round (player rejoined / slot reused) are skipped. Several kills by one player within 2.5 s share one scoreboard change: the number of teamkills among them is taken from the total change, which of them are teamkills is a guess (victims with the killer's regiment prefix first) and those rows carry `teamkill?(burst)` in `review`. Remaining gaps are normally 0 to +-2. Teamkills are read from the same score changes: a jump of 2 or more to 0 is a reset, not a teamkill.
- A team swap (a killer-less death after which the player respawns) costs the player 1 point and is counted as such in `score_gap` (it is not a kill or a death in the totals). Leaving the server costs nothing.
- Per round, four columns `R<n>(<kind>)_kills|_deaths|_teamkills|_score_gap`. Per-round `kills` do NOT subtract teamkills (plain counts). Warm-up rounds keep their columns but are left out of the overall totals.
- Not counted in totals: horse deaths, `no-blow death` rows, deaths of `(AI)` victims (those go to the killer's `ai_kills`).

## Rounds file and round kinds
`round, start_s, end_s, length_s, started_by, tickets_zero_at_s, tickets_zero_team, kills_after_tickets_zero, kind, death_msgs, method, review`
`death_msgs` is the number of rows in the kills file for that round (one per death, copies removed). It is not the raw message count: the server sends every death once per recipient and each recording catches a different number of those copies.
Kinds: `pre-live` (from capture start until the first detected start), `warm-up` (not live; excluded from totals), `live`.

How round starts are found, in order of preference:
- **Server messages (preferred):** the server's own chat lines "Changed the map to ..." (map load) and "Has reset the Map." (admin reset, also a type-41 marker). Admin pattern: map change = warm-up round (friendly fire off), then reset = LIVE round.
- **Restarts with no reset line:** the server prints "Friendly fire is now on" a fixed delay (parsed from the "Friendly fire will turn back on after N seconds" line; 30 s on NWE, 20 s early on Wed) after every round start; start = that time minus the delay. This found the Thursday restarts at 3:49 / 18:18 and the Friday one at 5:54.
- **Warm-up rule:** a segment is a warm-up when it starts with a map change (a round only goes live with an admin reset; the review flag says whether a reset followed), when two resets come less than 60 s apart, or when an admin says "reset and live" or "Live on Reset!" (also "rest/restart ... live") inside it.
- **Tickets (NWE):** the team-ticket event adds `tickets_zero_at_s` (round decided) and `kills_after_tickets_zero`.
- **Fallback** (no such chat lines): activity lulls and map-load signals.

## Flagbearers file
`round, round_kind, player, player_slot, class, flag, spawns, first_spawn_s, first_spawn_mm:ss, last_spawn_s, review`
One row per player, round, class and flag. The class comes from the spawn message's troop id and the module's troops.txt (troop index = field minus 1); the flag from item_kinds1.txt. Both tables are bundled (`data/flag_troops_nw.json`, `data/flag_troops_nwe.json`).
- **NW:** a spawn counts when the class can carry a flag (NCO classes, French `colours` classes) AND a flag item of that class is in the spawned loadout.
- **NWE:** it has dedicated `*_flag_bearer` classes; every spawn of one counts. `flag` is filled in when the loadout shows the flag item, otherwise `unknown` (about 40 % of NWE rows on the Tuesday capture).
- The server type is chosen from the largest loadout item id in the capture (above 1023 = NWE); another module needs its own two table files.
- Loadout item ids are only trusted for the flag itself, and only together with the class: the servers' item tables differ from the module files for armour, so armour/other items are not decoded.
- Misses: your own respawns (no spawn message, only a type-18 update), and agents already on the map when you connected. Check on the two NWEVENT captures (two viewpoints of one event): 23 of 28 (player, flag) pairs identical, the rest are roster-slot differences.
- `review = name?` means the player's name could not be resolved.

## Weapon classes (from the exe)
The client picks the killfeed icon with a jump table on the 5-bit weapon class: 0 headshot, 1 couched lance, 2 punch, 3 horse impact, 4 bow, 5 crossbow (the module draws muskets with it), 6 thrown axe, 7 thrown knife, 8 javelin, 9 thrown stone, 10 pistol, 11 musket, 12 one-handed sword, 13 two-handed sword, 14 one-handed axe, 15 two-handed axe, 16 blunt (mace/club), 17 spear (bayonet), 18 morningstar, 19 maul (hammer), 20-26 custom icons 1-7 (20 cannonball, 21 canister, 22 explosion seen on video). Values above 26 draw no icon.

## Names
Slots are reused. When a player's name later appears (repeatedly) in a different slot, the old slot is treated as unknown from then on, and the new occupant's name is looked up from later data in the capture (otherwise the old name stuck to whoever took the slot). Near-simultaneous repeats of the same death message (same victim within 6 s) are dropped.

## Known limits
- About 96% of kills have both names resolved; the rest are flagged in `review`.
- Weapon classes come from the exe's killfeed icon table (27 classes, 0-26; see below). Labels with an `(ico_...)` suffix come from the table only (the art has not been seen on video) and carry the `weapon?` flag. Class 23 (`ico_custom_4`) is drowning: confirmed on video (a player drowning himself; the capture has exactly one such row, killer = victim, score -1). Weapon `drowning`, death type `self-inflicted: drowning`. Class 3 (horse charge) kills usually have no killer name: the killer agent is the horse, not the rider.
- Built for Warband 1.174 / NW 1.210 packets. The message layouts in `nreader.py` were worked out from the game's own reader and checked against it on all four captures (about 400,000 messages, identical); the per-server bit widths are found from each capture (the `calibrating bit widths` step). A message type nobody has seen with a rare flag set makes that one packet unreadable (it is skipped, not mis-read).
- Not tested on Windows; the exe is built by GitHub Actions.

## Download and build
- **Windows exe:** download `nwkills.exe` (command line) or `nwkills-gui.exe` (window) from the [Releases](../../releases) page. Windows SmartScreen may warn about an unknown publisher (More info > Run anyway); the exe is built from this source by GitHub Actions.
- **From source:** `python nwkills.py capture.pcapng` (Python 3.10+, no dependencies).
- **Making a release (maintainer):** `git tag v0.1 && git push --tags`; the `build-windows` workflow builds the exe and attaches it to the release.

## Privacy
Captures contain player names and IP addresses. Please do not post whole captures publicly; share the CSV, or a small trimmed capture, when reporting a bug.

## Licence
GPL-3.0-or-later, see [LICENSE](LICENSE). Not affiliated with TaleWorlds or the Napoleonic Wars team; no game files are included.

## Comparing two recordings of one event
Two recordings of the same session give the same kills for the stretch where they overlap (a test pair of 2,542 kills matched on 2,538 rows; the other four were in the first three seconds of the later recording). What can still differ, because one recording lacks the data:
- A mount or AI unit that was already alive before the later recording started: its owner is unknown there, so the row is `no-blow death (mount?, not counted)` with victim `(AI/mount, owner unknown)`, where the earlier recording has `(AI)` / `AI/horse death` (and counts it in `ai_kills`).
- `respawn_s` can differ by up to about 0.3 s (the packets arrive at slightly different moments); it is only filled when the next spawn of the same player is a spawn message.
- Rounds that start before the later recording began are shorter there, and the last round ends at each recording's last packet.
- Score columns (`score_gap`, score at start/end) come from score updates that only some packets carry, so they can differ for a few players.

## Packets the game stores and replays later
A packet whose message count reads as -1 is stored by the game and replayed with the next packet; the tool reads those too (their tail is ignored, as in the game). Reset blocks (the server killing every agent at a map change) that are NOT announced by an admin line are recognised and left out of the kill list.

## Admin actions
The server prints a text line for admin actions. The tool reads three of them and labels the deaths they cause in the `death_type` column; these rows stay in the kills file but are not counted as kills, deaths or teamkills:

| `death_type` | line | deaths labelled |
|---|---|---|
| `admin slay` | `X Slayed Player Y.` | Y's self-death within about 2 s |
| `admin: slayed everyone` | `X Slayed Everyone.` | every self-death or killer-less death in that moment |
| `admin: swapped everyone to spectators` | `X Swapped Everyone to Spectators` | the killer-less deaths in that moment |

A fist self-death with no such line is `self-inflicted: suicide (no admin line)`. Checked on 8 captures: none of 232 such rows has any other admin line for the victim within 15 s (6 are followed by `Revived Player`, 2 by `Toggled Beacon`). Other lines (bans, beacons) are not used.

A cavalry charge kill whose horse has no known owner is credited to the one player whose score changes by 1 at that moment (first within 0.5 s of the kill, then within 2.5 s) and is not explained by one of that player's own kills, if all such changes belong to one player (`review`: `name-from-later-data(killer-from-score)`); otherwise the killer stays `(AI)`. Artillery volleys that produce no score update count as half teamkills (the server only sends a score when it changes).
