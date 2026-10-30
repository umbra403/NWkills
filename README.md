# nwkills - read the killfeed from a Wireshark capture (client side only)

Reads the packets your own game client received (UDP, unencrypted) and rebuilds who killed whom, with which weapon
class, and teamkills. No server access needed. Works for NW and NWE (bit widths are calibrated per server automatically).

## Use
1. Capture with Wireshark while playing (save as .pcapng). Start the capture BEFORE joining, so the player list is included.
2. First time only: run `nwkills.exe --setup` (or just run it, or run it on a capture): a short wizard finds or asks for your `mb_warband.exe` and remembers it (`%APPDATA%\nwkills\config.json`). Then: `nwkills.exe capture.pcapng` (or drag the .pcapng onto it). `--exe PATH` still overrides the saved path.
   (Your game exe is only read. It must be the Warband 1.174 / NW 1.210 build, sha256 ff4a28c5...dae13; a warning is printed otherwise.)
3. Output: `capture_kills.csv` (one row per kill) and `capture_players.csv` (kills, deaths, teamkills per player, with the same three numbers for every round; overall totals exclude warm-up rounds; teamkills are not counted in kills).

Options: `--out file.csv`, `--port N` (server UDP port, normally auto-detected), `--me NAME` (part of your own name),
`--jobs N` (CPU cores, default all), `--cache file.pkl` (keep decoded packets so you can re-run the kill logic quickly), `--limit N` (test on the first N packets).
A 2-hour capture (~115k packets) takes ~9 minutes on 2 cores.

## Columns
`time_s` seconds since capture start (video time = time_s + your capture/recording offset). `weapon`: firearm / pistol / bayonet or spear / sword / cannonball / shrapnel / explosion / headshot (+ the musket from the projectile). `teamkill`: killer's score went down at that kill.
`review` flags rows to check: `killer?` / `victim?` (player could not be resolved; `(AI)` = bot), `weapon?` (unknown weapon class), `self`.

## Death types (`death_type`, provisional)
`kill` normal blow kill | `AI/horse death` victim is a bot or mount (not counted as a player death) | `world (fall/drown?)` no killer agent |
`self-inflicted (suicide/fall?)` killer = victim | `non-blow death (leave/class change?)` death message without a blow. `respawn_s` = seconds until that player gets a new agent
(normal deaths ~11 s; blank = none within 2 min, e.g. left). The split inside the last three types is a guess until we have a capture with known suicide / class change / leave / drowning / fall events.
`kills` in the players file includes teamkills; `ai_kills` are bot/horse kills.

## Known limits
- About 96% of kills have both names resolved; the rest are flagged in `review` (`killer?`, `victim?`, `before-sync` = first ~90 s before the server announced agent owners, `(world)` = no killer, `(AI)` = bot).
- Class 2 is shown as "self-inflicted?" (mostly killer = victim) and counted as a teamkill when your score dropped. Classes 1, 3, 16, 19 and a few others are not identified yet (shown as `class N`).
- Round starts / dud rounds are not detected yet.
- Built for exactly the exe build above; `nwkills/data/ins_subset.pkl` is the instruction trace the decoder needs (generated from that exe).

## Rounds
Written to `<name>_rounds.csv` and as `round` / `round_kind` columns in the kills CSV.
- **Server messages (preferred):** the server's own chat lines "Changed the map to ..." (map load) and "Has reset the Map." (admin reset, also a type-41 marker). Typical admin pattern: map change = warm-up round (friendly fire off 30 s), then reset = LIVE round. A map change followed by a reset is labelled `warm-up` (filter as dud); everything after a reset is `live`.
- **Tickets:** on NWE the module's team-ticket event adds `tickets_zero_at_s` (round decided) and `kills_after_tickets_zero`.
- **Fallback** (no such chat lines): activity lulls and map-load signals.
