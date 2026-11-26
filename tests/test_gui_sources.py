import ast
import glob
import os
import subprocess
import sys
import unittest
import support

GUI_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'nwkills', 'gui')


class GuiSourcesTest(unittest.TestCase):
    """The window cannot run without Qt, so the tests that run everywhere check that its sources are valid for the oldest supported Python
    and keep Qt out of the logic package."""

    def test_every_window_module_parses_as_python_3_9(self):
        files = sorted(glob.glob(os.path.join(GUI_FOLDER, '*.py')))
        self.assertGreater(len(files), 10)
        for path in files:
            with open(path, encoding='utf-8') as source:
                ast.parse(source.read(), path, feature_version=(3, 9))

    def test_the_logic_package_does_not_import_qt(self):
        for path in glob.glob(os.path.join(GUI_FOLDER, '..', 'viewlogic', '*.py')):
            with open(path, encoding='utf-8') as source:
                self.assertNotIn('PySide6', source.read(), path)

    def test_the_window_entry_point_is_exported(self):
        with open(os.path.join(GUI_FOLDER, '__init__.py'), encoding='utf-8') as source:
            self.assertIn('import main', source.read())


class EndProcessNowTest(unittest.TestCase):
    ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

    def run_snippet(self, exit_code):
        path = os.path.join(self.ROOT, 'nwkills', 'gui', 'process_exit.py')       # loaded by path: the package around it needs Qt
        code = ('import importlib.util as u; s = u.spec_from_file_location("process_exit", %r); m = u.module_from_spec(s); s.loader.exec_module(m); '
                'print("before"); m.end_process_now(%d); print("after")' % (path, exit_code))
        return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60)

    def test_the_process_ends_with_the_given_code_and_runs_nothing_after_it(self):
        result = self.run_snippet(3)
        self.assertEqual((result.returncode, result.stdout.strip()), (3, 'before'))

    def test_a_zero_exit_code_is_returned_as_zero(self):
        self.assertEqual(self.run_snippet(0).returncode, 0)


if __name__ == '__main__':
    unittest.main()
