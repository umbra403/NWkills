import unittest
import support
from nwkills.viewlogic import (ALL_SHOWN, KIND_CHIPS, NONE_SHOWN, SOME_SHOWN, ColumnGroup, ColumnGrouper, ColumnMemory, RoundSelection, SelectedCellGrid,
                               TabSeparatedFormatter, round_kinds_by_number, round_menu_label, round_numbers_in)

HEADERS = ['round', 'round_kind']
ROWS = [['1', 'pre-live'], ['2', 'warm-up'], ['3', 'live'], ['4', 'warm-up']]


class RoundSelectionTest(unittest.TestCase):
    def passing(self, selection):
        predicate = selection.row_predicate(HEADERS)
        return ROWS if predicate is None else [row for row in ROWS if predicate(row)]

    def test_the_chips_are_live_pre_prelive_and_warm(self):
        self.assertEqual([chip.chip_id for chip in KIND_CHIPS], ['live', 'pre', 'prelive', 'warm'])

    def test_nothing_selected_lets_every_row_pass(self):
        selection = RoundSelection()
        self.assertTrue(selection.is_empty)
        self.assertIsNone(selection.row_predicate(HEADERS))
        self.assertEqual(self.passing(selection), ROWS)

    def test_a_kind_chip_lets_its_kinds_pass(self):
        selection = RoundSelection()
        selection.set_chip('live', True)
        self.assertEqual(self.passing(selection), [ROWS[2]])
        self.assertFalse(selection.is_empty)

    def test_the_combined_chip_lets_pre_live_and_live_pass(self):
        selection = RoundSelection()
        selection.set_chip('prelive', True)
        self.assertEqual(self.passing(selection), [ROWS[0], ROWS[2]])

    def test_a_row_passes_when_any_selected_button_matches(self):
        selection = RoundSelection()
        selection.set_chip('live', True)
        selection.set_round('2', True)
        self.assertEqual(self.passing(selection), [ROWS[1], ROWS[2]])

    def test_switching_a_button_off_again(self):
        selection = RoundSelection()
        selection.set_chip('live', True)
        selection.set_chip('live', False)
        selection.set_round('2', True)
        selection.set_round('2', False)
        self.assertTrue(selection.is_empty)

    def test_clear_switches_everything_off(self):
        selection = RoundSelection()
        selection.set_chip('warm', True)
        selection.set_round('1', True)
        selection.clear()
        self.assertTrue(selection.is_empty)

    def test_allowed_kinds_are_the_union_of_the_chips(self):
        selection = RoundSelection()
        selection.set_chip('warm', True)
        selection.set_chip('pre', True)
        self.assertEqual(selection.allowed_kinds(), {'warm-up', 'pre-live'})

    def test_a_table_without_round_columns_is_not_filtered(self):
        selection = RoundSelection()
        selection.set_chip('live', True)
        self.assertIsNone(selection.row_predicate(['a']))


class RoundListsTest(unittest.TestCase):
    def test_round_numbers_are_distinct_and_in_numeric_order(self):
        rows = [['10'], ['2'], ['2'], ['1']]
        self.assertEqual(round_numbers_in(['round'], rows), ['1', '2', '10'])

    def test_a_table_without_a_round_column_has_no_round_numbers(self):
        self.assertEqual(round_numbers_in(['a'], [['1']]), [])

    def test_a_menu_label_names_the_kind_when_known(self):
        self.assertEqual(round_menu_label('3', {'3': 'live'}), 'Round 3 (live)')
        self.assertEqual(round_menu_label('3', {'3': ''}), 'Round 3')
        self.assertEqual(round_menu_label('4', {}), 'Round 4')

    def test_round_kinds_by_number_reads_the_rounds_table(self):
        self.assertEqual(round_kinds_by_number(['round', 'kind'], [['1', 'live'], ['2', 'warm-up']]), {'1': 'live', '2': 'warm-up'})
        self.assertEqual(round_kinds_by_number(['round'], [['1']]), {})


class ColumnGroupingTest(unittest.TestCase):
    HEADERS = ['player', 'kills', 'deaths', 'score_at_capture_start', 'score_at_capture_end', 'score_gap', 'R1(live)_kills', 'R1(live)_deaths',
               'R2(pre-live)_kills', 'R2(pre-live)_deaths']

    def groups(self, headers=None):
        return {group.label: list(group.members) for group in ColumnGrouper.group(headers or self.HEADERS)}

    def test_one_group_per_measure(self):
        groups = self.groups()
        self.assertEqual((groups['All kills columns'], groups['All deaths columns']), ([1, 6, 8], [2, 7, 9]))
        self.assertEqual(groups['All score_at_capture columns'], [3, 4])

    def test_a_single_column_is_no_group(self):
        self.assertNotIn('All score_gap columns', self.groups())

    def test_one_group_per_round(self):
        groups = self.groups()
        self.assertEqual((groups['Round R1(live)'], groups['Round R2(pre-live)']), ([6, 7], [8, 9]))

    def test_per_round_columns_and_totals_as_wholes(self):
        groups = self.groups()
        self.assertEqual((groups['All per-round columns'], groups['All total columns']), ([6, 7, 8, 9], [1, 2, 3, 4, 5]))

    def test_the_first_column_is_in_no_group(self):
        self.assertTrue(all(0 not in members for members in self.groups().values()))

    def test_a_table_without_per_round_columns_has_no_groups(self):
        self.assertEqual(ColumnGrouper.group(['round', 'time_s', 'killer', 'review']), [])


class ColumnGroupTest(unittest.TestCase):
    def test_check_state_is_none_some_or_all(self):
        group = ColumnGroup('g', [1, 2])
        self.assertEqual((group.check_state({1, 2}), group.check_state({1}), group.check_state(set())), (NONE_SHOWN, SOME_SHOWN, ALL_SHOWN))

    def test_a_click_hides_a_fully_shown_group_and_shows_any_other(self):
        group = ColumnGroup('g', [1, 2])
        self.assertFalse(group.columns_to_show_after_toggle(set()))
        self.assertTrue(group.columns_to_show_after_toggle({1}))
        self.assertTrue(group.columns_to_show_after_toggle({1, 2}))


class ColumnMemoryTest(unittest.TestCase):
    def setUp(self):
        self.memory = ColumnMemory(['player', 'kills', 'deaths'], {0: 'ann', 1: '', 2: 'x'}, {2}, 1, 'descending')

    def test_filter_texts_are_remembered_by_name_and_empty_ones_dropped(self):
        self.assertEqual((self.memory.filter_text('player'), self.memory.filter_text('kills'), self.memory.filter_text('other')), ('ann', '', ''))

    def test_hidden_columns_are_remembered_by_name(self):
        self.assertEqual((self.memory.is_hidden('deaths'), self.memory.is_hidden('kills')), (True, False))

    def test_the_remembered_sort_is_found_in_the_new_table(self):
        self.assertEqual(self.memory.sort_for(['player', 'x', 'kills'], None, None), (2, 'descending'))

    def test_the_default_sort_is_used_when_the_remembered_column_is_gone(self):
        self.assertEqual(self.memory.sort_for(['player', 'deaths'], 'deaths', 'asc'), (1, 'asc'))

    def test_no_sort_when_neither_exists(self):
        self.assertIsNone(self.memory.sort_for(['player'], 'kills', 'asc'))
        self.assertIsNone(self.memory.sort_for(['player'], None, None))

    def test_without_a_sorted_column_nothing_is_remembered(self):
        memory = ColumnMemory(['a'], {}, set(), -1, 'asc')
        self.assertEqual(memory.sort_for(['a'], 'a', 'desc'), (0, 'desc'))

    def test_a_filter_text_of_a_column_past_the_headers_is_ignored(self):
        memory = ColumnMemory(['a'], {5: 'x'}, set(), -1, 'asc')
        self.assertEqual(memory.filter_text('a'), '')


class TabSeparatedFormatterTest(unittest.TestCase):
    def test_clean_turns_tabs_and_line_breaks_into_a_space(self):
        self.assertEqual(TabSeparatedFormatter.clean('a\tb\r\nc'), 'a b c')

    def test_rows_are_tab_separated_and_unselected_cells_empty(self):
        self.assertEqual(TabSeparatedFormatter.format(['a', 'b'], [['1', 'x\ty'], ['2', None]]), '1\tx y\n2\t')

    def test_the_header_line_is_optional(self):
        self.assertEqual(TabSeparatedFormatter.format(['a', 'b'], [['1', '2']], with_header=True), 'a\tb\n1\t2')

    def test_nothing_to_format(self):
        self.assertEqual(TabSeparatedFormatter.format([], []), '')


class SelectedCellGridTest(unittest.TestCase):
    def test_the_grid_covers_the_selected_rows_and_columns(self):
        cells = {(2, 0): 'a', (2, 3): 'b', (5, 3): 'c'}
        headers, grid = SelectedCellGrid.build(cells, lambda column: 'h%d' % column)
        self.assertEqual((headers, grid), (['h0', 'h3'], [['a', 'b'], [None, 'c']]))

    def test_no_cells_give_an_empty_grid(self):
        self.assertEqual(SelectedCellGrid.build({}, str), ([], []))


if __name__ == '__main__':
    unittest.main()
