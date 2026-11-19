# nwkills

Reads the killfeed of *Mount & Blade: Warband* (Napoleonic Wars, NW and NW Extended) from a network capture, purely on
your own computer. It decodes the packets your game client received and rebuilds who killed whom, with which weapon,
teamkills, rounds, scores and flagbearers, and writes them as CSV files (or shows them in a window).

No server access, no API key, no game files and no internet connection are needed.

## Download and build
- **Windows:** download `nwkills-gui.exe` (window) or `nwkills.exe` (command line) from the [Releases](../../releases) page.
  Each release also lists SHA-256 checksums in `SHA256SUMS.txt`. The executables are built from this source by GitHub Actions
  (`.github/workflows/build.yml`).
- **From source** (Python 3.9 or newer; on Windows write `py -3` instead of `python`):
  - command line, no dependencies: `python nwkills.py capture.pcapng`
  - window: `python -m pip install -r requirements-gui.txt`, then `python nwkills_gui.py [capture.pcapng]`
- **Building the executables yourself:** push the repository to GitHub; the `build-windows` workflow builds both. Tag a
  version (`git tag v0.1 && git push --tags`) to attach them to a release.

## Use
1. **Record a capture** while you play, starting it *before* you join the server so the player list is included:
   - with the window's **Capture** tab (Windows 10 1809 or later, no extra software): run `nwkills-gui.exe` as
     administrator, press *Start capture*, join and play, then press *Stop and open*; or
   - with Wireshark, saving as `.pcapng`.
2. **Read it:** open the `.pcapng` in the window (or drop it onto it) and press *Convert*, or run
   `nwkills.exe capture.pcapng`. A two-hour capture takes one to three minutes.
3. **Look at the result.** The window shows the tables (kills, multikills, players, rounds, flagbearers) with sorting, filters and
   copy/export. The window writes no files until you press an Export button. The command line writes
   `capture_kills.csv`, `capture_kills_players.csv`, `capture_rounds.csv` and `capture_flagbearers.csv` next to the capture.

Command line options: `--out FILE`, `--port N` (server UDP port, normally detected), `--me NAME` (part of your own player
name), `--jobs N`, `--cache FILE` (keep decoded packets for quick re-runs), `--limit N` (only the first N packets).

More detail is in [docs/](docs/index.adoc): the [window](docs/window.adoc), [capturing](docs/capturing.adoc), the
[output files](docs/output-files.adoc) and [how the tool works](docs/how-it-works.adoc).

## Troubleshooting
**Windows blocks the program.** The exe is not code-signed, so Windows may warn about it.
- *"Windows protected your PC" (SmartScreen):* click *More info*, then *Run anyway*. Or right-click the file, open
  *Properties* and tick *Unblock*.
- *Antivirus removes it:* single-file Python programs are sometimes flagged by mistake. Restore it from the quarantine and add
  an exclusion. You can compare the file with the checksum in the release (`Get-FileHash nwkills-gui.exe` in PowerShell).
- *"Smart App Control blocked an app that isn't trusted" (some Windows 11 installs):* there is no "Run anyway". Run from
  source, or turn Smart App Control off in Windows Security (this cannot be undone without reinstalling Windows).

**`SyntaxError: Non-ASCII character ... no encoding declared`** (running from source): you are using Python 2. Install
Python 3 from python.org and run `py -3 nwkills_gui.py`.

**"could not find the game server flow in the capture":** the capture must have been recorded while connected to a server.
If several servers were in it, give the server's UDP port (`--port`, or the Options tab).

**Capturing says it needs administrator rights:** close the window, right-click `nwkills-gui.exe` and choose
*Run as administrator*.

**Names or kills look wrong:** the `review` column of the kills file flags rows to check; see
[the output files](docs/output-files.adoc#review-flags).

## Privacy
Captures contain player names and IP addresses. Please do not post whole captures publicly; share the CSV, or a small
trimmed capture, when reporting a bug.

## Licence
GPL-3.0-or-later, see [LICENSE](LICENSE). The window uses PySide6 (LGPL-3.0). Not affiliated with TaleWorlds or the
Napoleonic Wars team; no game files are included.
