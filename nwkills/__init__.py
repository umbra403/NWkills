# Python 2 or a very old Python 3 cannot run this tool; say so plainly (this check must stay plain ASCII and Python 2 parsable).
import sys
if sys.version_info < (3, 9):
    sys.exit('nwkills needs Python 3.9 or newer. You are running Python %d.%d. On Windows try: py -3 nwkills_gui.py' % sys.version_info[:2])
