import os
import tempfile
import unittest
import support
from nwkills.viewlogic import ColumnFilters, CsvTable, CsvTableFile, cell_sort_key, is_numeric, numeric_column_indexes


class CsvTableFileTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), 't.csv')

    def test_a_written_table_reads_back_the_same(self):
        CsvTableFile.write(self.path, ['a', 'b'], [['1', 'x,"y"'], ['2', 'line\nbreak']])
        self.assertEqual(CsvTableFile.read(self.path), (['a', 'b'], [['1', 'x,"y"'], ['2', 'line\nbreak']]))

    def test_the_file_starts_with_a_byte_order_mark_for_excel(self):
        CsvTableFile.write(self.path, ['a'], [])
        with open(self.path, 'rb') as csv_file:
            self.assertEqual(csv_file.read(3), b'\xef\xbb\xbf')

    def test_short_rows_are_padded_and_empty_lines_skipped(self):
        with open(self.path, 'w', newline='', encoding='utf-8-sig') as csv_file:
            csv_file.write('a,b,c\r\n1\r\n\r\n2,3,4\r\n')
        self.assertEqual(CsvTableFile.read(self.path).rows, [['1', '', ''], ['2', '3', '4']])

    def test_an_empty_file_has_no_headers_and_no_rows(self):
        open(self.path, 'w').close()
        self.assertEqual(CsvTableFile.read(self.path), CsvTable([], []))


class CellSortingTest(unittest.TestCase):
    def test_numbers_and_times_sort_by_value_before_text_and_empty_cells_last(self):
        values = ['10', '9', '2', '1:05', '0:59', 'abc', 'Abd', '']
        self.assertEqual(sorted(values, key=cell_sort_key), ['2', '9', '10', '0:59', '1:05', 'abc', 'Abd', ''])

    def test_a_time_sorts_by_its_seconds(self):
        self.assertLess(cell_sort_key('0:59'), cell_sort_key('1:05'))
        self.assertLess(cell_sort_key('1:05'), cell_sort_key('100'))

    def test_text_sorts_without_regard_to_case(self):
        self.assertLess(cell_sort_key('abc'), cell_sort_key('Abd'))
        self.assertEqual(cell_sort_key('ABC'), cell_sort_key('abc'))

    def test_spaces_around_a_cell_are_ignored(self):
        self.assertEqual(cell_sort_key(' 3 '), cell_sort_key('3'))

    def test_negative_and_decimal_numbers_are_numbers(self):
        self.assertEqual(cell_sort_key('-1.5')[:2], (0, -1.5))

    def test_is_numeric(self):
        self.assertEqual([is_numeric(text) for text in ('5', '-5', '5.25', '1:05', ' 7 ', 'x', '', '1:5')], [True, True, True, True, True, False, False, False])

    def test_numeric_columns_are_those_with_only_numbers_in_their_filled_cells(self):
        rows = [['a', '1', '', 'x'], ['b', '2.5', '3', '4']]
        self.assertEqual(numeric_column_indexes(4, rows), {1, 2})

    def test_a_column_without_any_filled_cell_is_not_numeric(self):
        self.assertEqual(numeric_column_indexes(1, [[''], ['']]), set())

    def test_no_rows_means_no_numeric_columns(self):
        self.assertEqual(numeric_column_indexes(2, []), set())


class ColumnFiltersTest(unittest.TestCase):
    def test_empty_texts_are_skipped_and_invalid_ones_reported(self):
        filters = ColumnFilters.compile({0: 'bay', 1: '(', 2: ''})
        self.assertEqual((list(filters.patterns), filters.invalid_columns), ([0], [1]))

    def test_a_row_passes_when_every_filtered_cell_matches(self):
        filters = ColumnFilters.compile({0: 'bay', 1: '^x'})
        self.assertTrue(filters.accepts(['Bayonet', 'xyz']))
        self.assertFalse(filters.accepts(['Bayonet', 'yxz']))
        self.assertFalse(filters.accepts(['sword', 'xyz']))

    def test_matching_ignores_case_unless_asked_not_to(self):
        self.assertTrue(ColumnFilters.compile({0: 'bay'}, ignore_case=True).accepts(['Bayonet']))
        self.assertFalse(ColumnFilters.compile({0: 'bay'}, ignore_case=False).accepts(['Bayonet']))

    def test_without_filters_every_row_passes(self):
        filters = ColumnFilters({})
        self.assertTrue(filters.accepts(['anything']))
        self.assertFalse(filters.is_active)

    def test_is_active_when_a_pattern_is_set(self):
        self.assertTrue(ColumnFilters.compile({0: 'a'}).is_active)
        self.assertFalse(ColumnFilters.compile({0: '('}).is_active)


if __name__ == '__main__':
    unittest.main()
