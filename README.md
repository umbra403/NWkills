# nwkills - read the killfeed from a Wireshark capture (client side only)

Reads the packets your own game client received (UDP, unencrypted) and rebuilds who killed whom, with which weapon
class, and teamkills. No server access needed. Works for NW and NWE (bit widths are calibrated per server automatically).

## Use
1. Capture with Wireshark while playing (save as .pcapng). Start the capture BEFORE joining, so the player list is included.
2. Run:  `nwkills.exe capture.pcapng --exe "C:\path\to\mb_warband.exe"`
   (Your game exe is only read. It must be the Warband 1.174 / NW 1.210 build, sha256 ff4a28c5...dae13; a warning is printed otherwise.)
3. Output: `capture_kills.csv` (one row per kill) and `capture_players.csv` (kills / deaths / teamkills per player).

Options: `--out file.csv`, `--port N` (server UDP port, normally auto-detected), `--me NAME` (part of your own name),
`--jobs N` (CPU cores, default all), `--cache file.pkl` (keep decoded packets so you can re-run the kill logic quickly), `--limit N` (test on the first N packets).
A 2-hour capture (~115k packets) takes ~9 minutes on 2 cores.

## Columns
`time_s` seconds since capture start (video time = time_s + your capture/recording offset). `weapon`: firearm / pistol / bayonet or spear / sword / cannonball / shrapnel / explosion / headshot (+ the musket from the projectile). `teamkill`: killer's score went down at that kill.
`review` flags rows to check: `killer?` / `victim?` (player could not be resolved; `(AI)` = bot), `weapon?` (unknown weapon class), `self`.

## Known limits
- ~75% of kills have both names resolved on a busy server; unresolved rows are flagged `review`.
- Weapon classes 1, 2, 3, 16, 19 are not identified yet (shown as `class N`).
- Round starts / dud rounds are not detected yet.
- Built for exactly the exe build above; `nwkills/data/ins_subset.pkl` is the instruction trace the decoder needs (generated from that exe).

## Build (GitHub Actions)
Push this folder to a repo; the workflow `build-windows` produces `nwkills.exe` as an artifact. Local: `python nwkills.py ...` (Python 3.10+, no dependencies).
