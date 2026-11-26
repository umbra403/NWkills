import unittest
import support
from nwkills.rounds import (ActivityRoundDetector, BoundaryMessageReader, RestartAnnouncementFinder, Round, RoundDetector, RoundTimeline,
                            ServerMessageRoundDetector, ServerTextBoundaryFinder, TicketResetRoundDetector, TicketSeriesFinder, TicketZeroFinder)
from nwkills.rounds.death_times import death_message_times


def record(time_s, bnd=(), texts=(), reset=0, ticket_events=(), deaths=0, spawns=0):
    messages = [(13, [1] * 6, [8] * 6)] * deaths + [(5, [1] * 6, [8] * 6)] * spawns
    return dict(t=time_s, bnd=list(bnd), msgs=list(messages), txt=list(texts), ev=list(ticket_events), rst=reset, tail=None, L=0, err=None)


def death_records(first_s, last_s, count):
    step = (last_s - first_s) / count
    return [record(first_s + step * index, deaths=1) for index in range(count)]


class RoundTimelineTest(unittest.TestCase):
    def setUp(self):
        self.timeline = RoundTimeline([Round(1, 0.0, 100.0, 0, 'capture start', 'x', kind='pre-live'), Round(2, 100.0, 200.0, 0, 'reset message', 'x', kind='live')])

    def test_the_round_that_holds_a_moment(self):
        self.assertEqual((self.timeline.number_at(50.0), self.timeline.number_at(150.0)), (1, 2))
        self.assertEqual(self.timeline.kind_at(150.0), 'live')

    def test_the_end_moment_of_a_round_belongs_to_it(self):
        self.assertEqual(self.timeline.number_at(100.0), 1)       # round 1 holds its end moment too (the first match wins)

    def test_after_the_end_it_is_the_last_round(self):
        self.assertEqual(self.timeline.number_at(999.0), 2)

    def test_without_rounds_it_is_round_one_and_no_kind(self):
        timeline = RoundTimeline([])
        self.assertEqual((timeline.number_at(5.0), timeline.kind_at(5.0), timeline.round_at(5.0)), (1, '', None))

    def test_rounds_are_available(self):
        self.assertEqual(len(self.timeline.rounds), 2)


class DeathMessageTimesTest(unittest.TestCase):
    def test_lists_every_death_message(self):
        self.assertEqual(death_message_times([record(1.0, deaths=2), record(2.0, spawns=3), record(3.0, deaths=1)]), [1.0, 1.0, 3.0])


class BoundaryMessageReaderTest(unittest.TestCase):
    def test_repeats_are_one_boundary(self):
        records = [record(10.0, [('map', 0)]), record(10.03, [('map', 1)]), record(10.06, [('map', 2), ('map', 3)]), record(10.1, [('reset', 0)]),
                   record(10.14, [('reset', 1)]), record(25.0, [('reset', 0)]), record(25.04, [('reset', 1)]), record(40.0, [('map', 0)]),
                   record(46.0, [('map', 190)]), record(46.5, [('map', 0)])]
        self.assertEqual(BoundaryMessageReader().read(records), [(10.0, 'map'), (10.1, 'reset'), (25.0, 'reset'), (40.0, 'map'), (46.5, 'map')])

    def test_the_same_count_again_at_once_is_a_duplicate_delivery(self):
        self.assertEqual(BoundaryMessageReader().read([record(5.0, [('reset', 0)]), record(5.5, [('reset', 0)])]), [(5.0, 'reset')])
        self.assertEqual(BoundaryMessageReader().read([record(5.0, [('reset', 0)]), record(9.0, [('reset', 0)])]), [(5.0, 'reset'), (9.0, 'reset')])

    def test_records_from_before_the_messages_were_kept_give_none(self):
        self.assertIsNone(BoundaryMessageReader().read([dict(t=1.0, msgs=[], txt=[], ev=[])]))

    def test_no_records_no_boundaries(self):
        self.assertEqual(BoundaryMessageReader().read([]), [])


class ServerTextBoundaryFinderTest(unittest.TestCase):
    def find(self, *records):
        return ServerTextBoundaryFinder().find(list(records))

    def test_map_and_reset_lines_are_boundaries(self):
        self.assertEqual(self.find(record(10.0, texts=['Changed the map to Arena']), record(100.0, texts=['X Has reset the Map.'])), [(10.0, 'map'), (100.0, 'reset')])

    def test_a_type_41_marker_is_a_reset(self):
        self.assertEqual(self.find(record(10.0, texts=['Changed the map to Arena']), record(100.0, reset=1)), [(10.0, 'map'), (100.0, 'reset')])

    def test_repeated_lines_are_merged(self):
        self.assertEqual(self.find(record(100.0, texts=['Has reset the Map']), record(105.0, texts=['Has reset the Map'])), [(100.0, 'reset')])

    def test_a_restart_without_lines_is_recovered_from_friendly_fire(self):
        found = self.find(record(10.0, texts=['Has reset the Map']), record(430.0, texts=['Friendly fire is now on']))
        self.assertEqual(found, [(10.0, 'reset'), (400.0, 'reset')])

    def test_the_restart_snaps_to_a_slay_everyone_line(self):
        found = self.find(record(10.0, texts=['Has reset the Map']), record(395.0, texts=['Boss Slayed Everyone.']), record(430.0, texts=['Friendly fire is now on']))
        self.assertEqual(found, [(10.0, 'reset'), (395.0, 'reset')])

    def test_the_announced_delay_is_used(self):
        found = self.find(record(10.0, texts=['Has reset the Map']), record(430.0, texts=['Friendly fire will be enabled after 20 seconds', 'Friendly fire is now on']))
        self.assertEqual(found[-1], (410.0, 'reset'))

    def test_a_friendly_fire_line_explained_by_a_reset_adds_nothing(self):
        self.assertEqual(self.find(record(100.0, texts=['Has reset the Map']), record(130.0, texts=['Friendly fire is now on'])), [(100.0, 'reset')])

    def test_a_server_without_admin_lines_gives_nothing(self):
        self.assertEqual(self.find(record(10.0, texts=['Changed the map to Arena'])), [])
        self.assertEqual(self.find(record(10.0, texts=['hello'])), [])


class RestartAnnouncementFinderTest(unittest.TestCase):
    def test_finds_admin_lines_announcing_a_restart(self):
        records = [record(10.0, texts=['*Admin Bob: reset and live']), record(12.0, texts=['*Admin Bob: reset and live']), record(60.0, texts=['*Admin Bob: Live on Reset!']),
                   record(90.0, texts=['*Admin Bob: hello']), record(95.0, texts=['Bob: reset and live'])]
        self.assertEqual(RestartAnnouncementFinder().find(records), [10.0, 60.0])


class TicketTest(unittest.TestCase):
    @staticmethod
    def countdown_records(start_tickets=300, reset_at=None):
        records, tickets = [], start_tickets
        for index in range(250):
            time_s = float(index)
            if reset_at is not None and index == reset_at:
                tickets = start_tickets
            tickets -= 1
            records.append(record(time_s, ticket_events=[(36, 400, [0, tickets]), (36, 401, [1, 7 * (index % 3)])], deaths=1))
        return records

    def test_the_series_that_counts_down_is_the_ticket_series(self):
        series = TicketSeriesFinder().find(self.countdown_records())
        self.assertEqual(len(series), 250)
        self.assertEqual(series[0], (0.0, 0, 299))

    def test_no_countdown_no_series(self):
        self.assertIsNone(TicketSeriesFinder().find([record(float(i), ticket_events=[(36, 400, [0, 50])]) for i in range(200)]))

    def test_too_few_readings_are_not_a_series(self):
        self.assertIsNone(TicketSeriesFinder().find(self.countdown_records()[:50]))

    def test_zero_crossings_are_found_once_per_team(self):
        crossings = TicketZeroFinder().find([(1.0, 0, 9), (2.0, 0, 4), (3.0, 0, 3), (4.0, 1, 5), (5.0, 0, 20), (6.0, 0, 2)])
        self.assertEqual(crossings, [(2.0, 0), (4.0, 1), (6.0, 0)])

    def test_a_jump_up_in_tickets_starts_a_round(self):
        records = self.countdown_records(reset_at=120)
        series = TicketSeriesFinder().find(records)
        rounds = TicketResetRoundDetector().detect(records, series)
        self.assertEqual([(round_.number, round_.signals, round_.method) for round_ in rounds], [(1, 'capture start', 'tickets'), (2, 'ticket reset', 'tickets')])
        self.assertEqual(rounds[1].start_s, 120.0)
        self.assertEqual(rounds[0].kill_count, 120)

    def test_short_rounds_and_rounds_with_few_kills_need_review(self):
        records = self.countdown_records(reset_at=70)
        rounds = TicketResetRoundDetector().detect(records, TicketSeriesFinder().find(records))
        self.assertIn('short (<120 s)', rounds[0].review)
        records = [dict(rec, msgs=[]) for rec in records]
        rounds = TicketResetRoundDetector().detect(records, TicketSeriesFinder().find(records))
        self.assertIn('few kills (0): dud?', rounds[0].review)

    def test_the_tickets_running_out_is_noted(self):
        records = self.countdown_records(start_tickets=60)
        rounds = TicketResetRoundDetector().detect(records, TicketSeriesFinder().find(records))
        self.assertEqual(rounds[0].tickets_zero, (54, 'team 0'))


class ServerMessageRoundDetectorTest(unittest.TestCase):
    def detect(self, boundaries, records=None, series=None):
        records = records or death_records(0.0, 600.0, 100)
        return ServerMessageRoundDetector().detect(records, boundaries, series)

    def test_every_boundary_starts_a_round(self):
        rounds = self.detect([(100.0, 'map'), (130.0, 'reset')])
        self.assertEqual([(round_.number, round_.start_s, round_.signals) for round_ in rounds],
                         [(1, 0.0, 'capture start'), (2, 100.0, 'map change message'), (3, 130.0, 'reset message')])
        self.assertEqual(rounds[0].end_s, 100.0)
        self.assertEqual(rounds[-1].end_s, 594.0)

    def test_a_map_change_followed_by_a_reset_is_a_warm_up(self):
        rounds = self.detect([(100.0, 'map'), (130.0, 'reset')])
        self.assertEqual([round_.kind for round_ in rounds], ['pre-live', 'warm-up', 'live'])
        self.assertIn('not live (warm-up before admin reset): dud?', rounds[1].review)
        self.assertIn('capture start', rounds[0].review)

    def test_a_map_change_alone_is_a_warm_up_that_is_a_dud(self):
        rounds = self.detect([(100.0, 'map')])
        self.assertEqual(rounds[1].kind, 'warm-up')
        self.assertIn('no admin reset followed', rounds[1].review)

    def test_two_quick_resets_make_the_first_a_warm_up(self):
        rounds = self.detect([(100.0, 'reset'), (130.0, 'reset')])
        self.assertEqual([round_.kind for round_ in rounds], ['pre-live', 'warm-up', 'live'])

    def test_an_announced_restart_makes_the_segment_a_warm_up(self):
        records = death_records(0.0, 600.0, 100)
        records[40] = dict(records[40], txt=['*Admin Bob: reset and live'])
        rounds = self.detect([(100.0, 'reset'), (300.0, 'reset')], records)
        self.assertEqual(rounds[1].kind, 'warm-up')

    def test_rounds_with_few_deaths_are_flagged(self):
        rounds = self.detect([(100.0, 'reset')], death_records(0.0, 600.0, 10))
        self.assertIn('few kills (', rounds[1].review)

    def test_ticket_zero_and_kills_after_it(self):
        series = [(150.0, 0, 9), (160.0, 0, 3)]
        rounds = self.detect([(100.0, 'reset')], series=series)
        self.assertEqual(rounds[1].tickets_zero, (160, 'team 0'))
        self.assertGreater(rounds[1].kills_after_ticket_zero, 0)
        self.assertEqual(rounds[0].kills_after_ticket_zero, '')


class ActivityRoundDetectorTest(unittest.TestCase):
    def test_a_gap_in_the_packets_is_a_border(self):
        records = [record(float(index), deaths=1) for index in range(100)] + [record(200.0 + index, deaths=1) for index in range(100)]
        rounds = ActivityRoundDetector().detect(records)
        self.assertIn('gap101s', rounds[1].signals)
        self.assertEqual(rounds[1].start_s, 99.0)

    def test_a_long_lull_followed_by_activity_is_a_border(self):
        records = [record(float(index), deaths=1, spawns=1) for index in range(200)] + [record(float(index), deaths=0) for index in range(200, 300)] \
                  + [record(float(index), deaths=1, spawns=1) for index in range(300, 400)]
        rounds = ActivityRoundDetector().detect(records)
        self.assertTrue(any(round_.signals.startswith('lull-end') for round_ in rounds))

    def test_a_quiet_capture_is_one_round(self):
        rounds = ActivityRoundDetector().detect([record(float(index), deaths=1) for index in range(100)])
        self.assertEqual((len(rounds), rounds[0].signals, rounds[0].method), (1, 'capture start', 'activity'))

    def test_no_records_no_rounds(self):
        self.assertEqual(ActivityRoundDetector().detect([]), [])

    def test_short_rounds_are_flagged(self):
        records = [record(float(index), deaths=1) for index in range(30)] + [record(100.0 + index, deaths=1) for index in range(30)]
        self.assertIn('short (<60 s)', ActivityRoundDetector().detect(records)[0].review)


class RoundDetectorTest(unittest.TestCase):
    def test_boundary_messages_win(self):
        records = death_records(0.0, 600.0, 100)
        records[10] = dict(records[10], bnd=[('reset', 0)])
        self.assertEqual(RoundDetector().detect(records)[0].method, 'server messages')

    def test_text_lines_are_used_for_records_without_boundary_messages(self):
        records = [{key: value for key, value in rec.items() if key != 'bnd'} for rec in death_records(0.0, 600.0, 100)]
        records[10] = dict(records[10], txt=['Changed the map to Arena'])
        records[20] = dict(records[20], txt=['X Has reset the Map.'])
        self.assertEqual(RoundDetector().detect(records)[1].signals, 'map change message')

    def test_tickets_are_next(self):
        records = TicketTest.countdown_records(reset_at=120)
        self.assertEqual(RoundDetector().detect(records)[0].method, 'tickets')

    def test_activity_is_the_last_resort(self):
        self.assertEqual(RoundDetector().detect(death_records(0.0, 600.0, 100))[0].method, 'activity')

    def test_no_records_no_rounds(self):
        self.assertEqual(RoundDetector().detect([]), [])


if __name__ == '__main__':
    unittest.main()
