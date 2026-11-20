import csv
import os
import tempfile
import unittest
import support
from nwkills.analysis.player_tally import PlayerTally
from nwkills.analysis.scoreboard import ScoreGapReport
from nwkills.flagbearers import FlagbearerRow
from nwkills.output import FlagbearersCsvWriter, KillsCsvWriter, OutputPaths, PlayersCsvWriter, RoundsCsvWriter
from nwkills.rounds import Round, RoundTimeline
from test_events_kills import kill_event

ROUNDS = [Round(1, 0.0, 100.0, 5, 'capture start', 'server messages', kind='pre-live', review='capture start'),
          Round(2, 100.0, 300.0, 9, 'reset message', 'server messages', kind='live', tickets_zero=(250, 'team 1'), kills_after_ticket_zero=3)]
TIMELINE = RoundTimeline(ROUNDS)


def read_rows(path):
    with open(path, newline='', encoding='utf-8-sig') as csv_file:
        return list(csv.reader(csv_file))


class OutputPathsTest(unittest.TestCase):
    def test_the_other_files_sit_next_to_the_kills_file(self):
        paths = OutputPaths.for_kills_file('/x/cap_kills.csv')
        self.assertEqual((paths.kills, paths.rounds, paths.flagbearers, paths.players), ('/x/cap_kills.csv', '/x/cap_rounds.csv', '/x/cap_flagbearers.csv', '/x/cap_kills_players.csv'))

    def test_a_kills_file_without_the_suffix(self):
        paths = OutputPaths.for_kills_file('/x/result.csv')
        self.assertEqual((paths.rounds, paths.players), ('/x/result_rounds.csv', '/x/result_players.csv'))

    def test_the_default_name_comes_from_the_capture(self):
        self.assertEqual(OutputPaths.for_capture('/x/cap.pcapng').kills, '/x/cap_kills.csv')
        self.assertEqual(OutputPaths.for_capture('/x/cap.pcapng', '/y/mine.csv').kills, '/y/mine.csv')


class CsvWritersTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()

    def path(self, name):
        return os.path.join(self.directory, name)

    def test_the_rounds_file(self):
        RoundsCsvWriter().write(self.path('r.csv'), ROUNDS, [kill_event(10.0), kill_event(150.0), kill_event(160.0)], TIMELINE)
        rows = read_rows(self.path('r.csv'))
        self.assertEqual(rows[0], RoundsCsvWriter.HEADER)
        self.assertEqual(rows[1], ['1', '0', '100', '100', 'capture start', '', '', '', 'pre-live', '1', 'server messages', 'capture start'])
        self.assertEqual(rows[2], ['2', '100', '300', '200', 'reset message', '250', 'team 1', '3', 'live', '2', 'server messages', ''])

    def test_the_files_start_with_a_byte_order_mark(self):
        RoundsCsvWriter().write(self.path('r.csv'), [], [], RoundTimeline([]))
        with open(self.path('r.csv'), 'rb') as csv_file:
            self.assertEqual(csv_file.read(3), b'\xef\xbb\xbf')

    def test_the_flagbearers_file(self):
        FlagbearersCsvWriter().write(self.path('f.csv'), [FlagbearerRow(2, 'live', 'Bob', 4, 'nco', 'flag_france', 3, 125.5, 300.0, '')])
        self.assertEqual(read_rows(self.path('f.csv'))[1], ['2', 'live', 'Bob', '4', 'nco', 'flag_france', '3', '125.5', '2:05', '300.0', ''])

    def test_the_kills_file(self):
        events = [kill_event(150.25, teamkill='yes', respawn_delay_s=12.5), kill_event(160.0, admin_label='admin slay', teamkill='yes', killer='P3', victim='P3')]
        KillsCsvWriter().write(self.path('k.csv'), events, TIMELINE)
        rows = read_rows(self.path('k.csv'))
        self.assertEqual(rows[0], KillsCsvWriter.HEADER)
        self.assertEqual(rows[1], ['2', 'live', '150.25', '2:30', 'P1', 'P2', 'x', 'yes', 'kill', '12.5', '', '1', '2'])
        self.assertEqual(rows[2][7:10], ['', 'admin slay', ''])

    def test_the_kills_file_shows_review_flags_and_empty_slots(self):
        KillsCsvWriter().write(self.path('k.csv'), [kill_event(150.0, killer='?', killer_slot=None)], TIMELINE)
        row = read_rows(self.path('k.csv'))[1]
        self.assertEqual((row[10], row[11], row[12]), ('killer?', '', '2'))

    def test_the_players_file(self):
        tally = PlayerTally()
        tally.add_events([kill_event(10.0), kill_event(150.0), kill_event(160.0), kill_event(170.0, killer_slot=2, victim_slot=1, killer='P2', victim='P1')], TIMELINE)
        gaps = ScoreGapReport()
        gaps.gap_by_player_round[('P1', 2)] = 1
        gaps.checked_slots_by_player_round[('P1', 2)] = 1
        gaps.first_score_by_player['P1'] = 0
        gaps.last_score_by_player['P1'] = 2
        gaps.checked_slots_by_player_round[('Idle', 2)] = 1
        PlayersCsvWriter().write(self.path('p.csv'), tally, gaps, ROUNDS)
        rows = read_rows(self.path('p.csv'))
        self.assertEqual(rows[0][:8], PlayersCsvWriter.FIXED_HEADER)
        self.assertEqual(rows[0][8:12], ['R1(pre-live)_kills', 'R1(pre-live)_deaths', 'R1(pre-live)_teamkills', 'R1(pre-live)_score_gap'])
        self.assertEqual([row[0] for row in rows[1:]], ['P1', 'P2', 'Idle'])
        self.assertEqual(rows[1][1:8], ['3', '1', '0', '0', '0', '2', '1'])           # kills (live rounds only), deaths, teamkills, ai_kills, scores, gap
        self.assertEqual(rows[1][8:16], ['1', '0', '0', '', '2', '1', '0', '1'])      # R1 then R2 columns: counts and the score gap
        self.assertEqual(rows[3][1:4], ['0', '0', '0'])

    def test_warm_up_rounds_are_left_out_of_the_totals(self):
        rounds = [Round(1, 0.0, 100.0, 0, '', '', kind='warm-up'), Round(2, 100.0, 300.0, 0, '', '', kind='live')]
        tally = PlayerTally()
        tally.add_events([kill_event(10.0), kill_event(150.0)], RoundTimeline(rounds))
        PlayersCsvWriter().write(self.path('p.csv'), tally, ScoreGapReport(), rounds)
        self.assertEqual(read_rows(self.path('p.csv'))[1][1], '1')


if __name__ == '__main__':
    unittest.main()
