# nwkills - read the Mount & Blade: Warband Napoleonic Wars killfeed from a Wireshark capture.
# Copyright (C) 2026 the nwkills authors. Licensed under the GNU General Public License v3.0 or later; see LICENSE.
# Entry point of the desktop window (nwkills-gui.exe). The command line tool is nwkills.py.
import multiprocessing, sys
if __name__ == '__main__':
    multiprocessing.freeze_support()
    from nwkills.gui import main
    sys.exit(main(sys.argv[1:]))
