import ast
import glob
import os
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


if __name__ == '__main__':
    unittest.main()
