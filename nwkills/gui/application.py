"""Starting the window."""
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .main_window import APPLICATION_NAME, MainWindow
from .self_test import run_self_test


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')
    self_test_requested = '--selftest' in argv
    if self_test_requested:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    app = QApplication.instance() or QApplication([APPLICATION_NAME])
    app.setStyle('Fusion')
    window = MainWindow()
    if self_test_requested:
        window.show()
        app.processEvents()
        run_self_test(window)
        print('gui ok')
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)          # the checks passed; leave without tearing the Qt objects down (a build machine returned 1 from that teardown)
    window.show()
    capture_files = [argument for argument in argv if not argument.startswith('-')]
    if capture_files:
        QTimer.singleShot(0, lambda: window.load_capture(capture_files[0]))
    return app.exec()
