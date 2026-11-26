import unittest
import support
from nwkills.viewlogic import MultikillFinder, PlayerTotalsCalculator
from nwkills.viewlogic.player_totals import parse_int, round_label

KILL_HEADERS = ['round', 'round_kind', 'killer', 'victim', 'teamkill', 'death_type']
PLAYER_HEADERS = ['player', 'score_at_capture_start', 'score_at_capture_end', 'score_gap', 'R2(live)_score_gap', 'R1(warm-up)_score_gap']
PLAYER_ROWS = [['A', '0', '3', '1', '1', '0'], ['Z', '', '', '', '', '']]
KILL_ROWS = [['2', 'live', 'A', 'B', '', 'kill'], ['2', 'live', 'A', 'C', '', 'kill'], ['2', 'live', 'B', 'A', 'yes', 'kill'],
             ['2', 'live', 'A', '(AI)', '', 'AI/horse death'], ['2', 'live', 'A', 'A', '', 'admin slay'], ['1', 'warm-up', 'B', 'A', '', 'kill']]


class HelpersTest(unittest.TestCase):
    def test_parse_int(self):
        self.assertEqual((parse_int('12'), parse_int(''), parse_int(None), parse_int('x')), (12, None, None, None))

    def test_round_label(self):
        self.assertEqual((round_label('3', 'live'), round_label('3', '')), ('R3(live)', 'R3'))


class PlayerTotalsCalculatorTest(unittest.TestCase):
    def totals(self, **options):
        table = PlayerTotalsCalculator(KILL_HEADERS, PLAYER_HEADERS, PLAYER_ROWS).compute(KILL_ROWS, **options)
        return table, {row[0]: dict(zip(table.headers, row)) for row in table.rows}

    def test_warm_up_admin_and_ai_rows_do_not_count_as_kills_and_deaths(self):
        _table, players = self.totals()
        self.assertEqual((players['A']['kills'], players['A']['deaths'], players['A']['ai_kills']), ('2', '1', '1'))

    def test_players_of_the_converter_file_without_a_kill_row_are_left_out_by_default(self):
        self.assertNotIn('Z', self.totals()[1])

    def test_all_players_can_be_included(self):
        self.assertIn('Z', self.totals(include_all_players=True)[1])

    def test_a_teamkill_counts_against_the_killer_when_net(self):
        _table, players = self.totals()
        self.assertEqual((players['B']['kills'], players['B']['teamkills']), ('-1', '1'))

    def test_teamkills_do_not_subtract_when_not_net(self):
        self.assertEqual(self.totals(net_kills=False)[1]['B']['kills'], '0')

    def test_per_round_columns_follow_the_round_and_its_kind(self):
        table, players = self.totals()
        self.assertEqual(players['A']['R2(live)_kills'], '2')
        self.assertNotIn('R1(warm-up)_kills', table.headers)

    def test_warm_up_rounds_can_be_included(self):
        table, players = self.totals(exclude_warm_up=False, include_all_players=True)
        self.assertEqual((players['A']['deaths'], 'R1(warm-up)_deaths' in table.headers), ('2', True))

    def test_rounds_are_in_numeric_order(self):
        table, _players = self.totals(exclude_warm_up=False)
        self.assertLess(table.headers.index('R1(warm-up)_kills'), table.headers.index('R2(live)_kills'))

    def test_the_score_gap_comes_from_the_converter_file_for_the_included_rounds(self):
        _table, players = self.totals()
        self.assertEqual((players['A']['score_gap'], players['A']['R2(live)_score_gap']), ('1', '1'))
        self.assertEqual((players['A']['score_at_capture_start'], players['A']['score_at_capture_end']), ('0', '3'))

    def test_a_player_the_converter_does_not_know_has_empty_scoreboard_cells(self):
        _table, players = self.totals()
        self.assertEqual((players['B']['score_at_capture_start'], players['B']['score_gap']), ('', ''))

    def test_the_best_player_comes_first_then_by_name(self):
        table, _players = self.totals()
        self.assertEqual([row[0] for row in table.rows], ['A', 'C', 'B'])

    def test_a_runaway_horse_gets_no_kill(self):
        rows = [['1', 'live', '(runaway horse)', 'A', '', 'kill']]
        table = PlayerTotalsCalculator(KILL_HEADERS, PLAYER_HEADERS, PLAYER_ROWS).compute(rows)
        self.assertEqual([row[0] for row in table.rows if row[1] != '0'], [])

    def test_no_kill_rows_give_the_fixed_columns_only(self):
        table = PlayerTotalsCalculator(KILL_HEADERS, PLAYER_HEADERS, PLAYER_ROWS).compute([])
        self.assertEqual((len(table.headers), table.rows), (8, []))


MULTIKILL_HEADERS = ['round', 'round_kind', 'time_s', 'mm:ss', 'killer', 'victim', 'weapon', 'teamkill', 'death_type', 'review']


def kill_row(round_number, kind, time_s, killer, victim, weapon='artillery: cannonball', teamkill='', death_type='kill', review=''):
    return [round_number, kind, str(time_s), '0:00', killer, victim, weapon, teamkill, death_type, review]


MULTIKILL_ROWS = [kill_row('1', 'live', 10.0, 'G', 'a'), kill_row('1', 'live', 10.0, 'G', 'b', teamkill='yes'), kill_row('1', 'live', 10.4, 'G', 'c'),
                  kill_row('1', 'live', 50.0, 'G', 'd'), kill_row('1', 'live', 60.0, 'H', 'e'),
                  kill_row('1', 'live', 60.5, 'H', 'f', weapon='artillery: shrapnel/canister'), kill_row('2', 'live', 70.0, 'J', 'g'),
                  kill_row('2', 'live', 70.1, 'J', 'h', weapon='melee: sword/sabre'), kill_row('2', 'live', 80.0, 'K', 'i'),
                  kill_row('2', 'live', 80.0, 'K', 'j', death_type='AI/horse death'), kill_row('3', 'warm-up', 90.0, 'L', 'm'),
                  kill_row('3', 'warm-up', 90.0, 'L', 'n')]


class MultikillFinderTest(unittest.TestCase):
    def find(self, rows=None, **options):
        return MultikillFinder(MULTIKILL_HEADERS).find(MULTIKILL_ROWS if rows is None else rows, **options)

    def test_can_read_needs_all_the_kill_columns(self):
        self.assertTrue(MultikillFinder.can_read(MULTIKILL_HEADERS))
        self.assertFalse(MultikillFinder.can_read(['round', 'killer']))

    def test_volleys_of_two_or_more_with_any_weapon_are_listed_biggest_first(self):
        table = self.find()
        self.assertEqual([(row[0], row[1], row[2], row[3], row[5]) for row in table.rows], [('G', '3', '2', '1', '1'), ('H', '2', '2', '0', '1'), ('J', '2', '2', '0', '2')])

    def test_warm_up_ai_deaths_and_single_kills_do_not_count(self):
        self.assertEqual({row[0] for row in self.find().rows}, {'G', 'H', 'J'})

    def test_a_volley_row_has_its_span_victims_and_weapons(self):
        first, _second, third = self.find().rows
        self.assertEqual((first[9], first[10]), ('0.40', 'a; b; c'))
        self.assertEqual(third[4], 'cannonball/sword/sabre')

    def test_teamkills_can_be_left_out_before_grouping(self):
        self.assertEqual([(row[0], row[1]) for row in self.find(include_teamkills=False).rows], [('G', '2'), ('H', '2'), ('J', '2')])

    def test_the_window_decides_what_belongs_to_a_volley(self):
        self.assertEqual([row[0] for row in self.find(window_s=0.3).rows], ['J', 'G'])

    def test_warm_up_can_be_included(self):
        self.assertEqual(len(self.find(exclude_warm_up=False).rows), 4)

    def test_best_only_keeps_each_killers_biggest(self):
        rows = MULTIKILL_ROWS + [kill_row('2', 'live', 100.0, 'G', 'p'), kill_row('2', 'live', 100.0, 'G', 'q')]
        self.assertEqual(len(self.find(rows).rows), 4)
        self.assertEqual([row[0] for row in self.find(rows, best_only=True).rows], ['G', 'H', 'J'])

    def test_review_flags_of_the_volley_are_collected(self):
        rows = [kill_row('1', 'live', 1.0, 'G', 'a', review='killer?'), kill_row('1', 'live', 1.5, 'G', 'b', review='killer? x')]
        self.assertEqual(self.find(rows).rows[0][11], 'killer? x')

    def test_rows_without_a_time_are_ignored(self):
        rows = [kill_row('1', 'live', '', 'G', 'a'), kill_row('1', 'live', 1.0, 'G', 'b')]
        self.assertEqual(self.find(rows).rows, [])

    def test_a_killer_that_is_not_a_player_makes_no_volley(self):
        rows = [kill_row('1', 'live', 1.0, '(AI)', 'a'), kill_row('1', 'live', 1.1, '(AI)', 'b')]
        self.assertEqual(self.find(rows).rows, [])

    def test_no_rows_give_the_headers_only(self):
        table = self.find([])
        self.assertEqual((table.headers[0], table.headers[-1], table.rows), ('killer', 'review', []))


if __name__ == '__main__':
    unittest.main()
