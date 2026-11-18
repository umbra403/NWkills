# nwkills - read the Mount & Blade: Warband Napoleonic Wars killfeed from a Wireshark capture.
# Copyright (C) 2026 the nwkills authors. Licensed under the GNU General Public License v3.0 or later; see LICENSE.
# Python 2 or a very old Python 3 cannot run this tool; say so plainly (this check must stay plain ASCII and Python 2 parsable).
import sys
if sys.version_info < (3, 9):
    sys.exit('nwkills needs Python 3.9 or newer. You are running Python %d.%d. On Windows try: py -3 nwkills_gui.py' % sys.version_info[:2])
import multiprocessing
from nwkills.cli import main
if __name__ == '__main__':
    multiprocessing.freeze_support(); main()
