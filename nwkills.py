# nwkills - read the Mount & Blade: Warband Napoleonic Wars killfeed from a Wireshark capture.
# Copyright (C) 2026 the nwkills authors. Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import multiprocessing
from nwkills.cli import main
if __name__ == '__main__':
    multiprocessing.freeze_support(); main()
