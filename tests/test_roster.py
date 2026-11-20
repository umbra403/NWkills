import unittest
import support
from nwkills.roster import JoinRecordScanner, NameSighting, PlayerNameHeuristics, PlayerRoster, RosterFiller, UnnamedSlotFinder
from nwkills.roster.bit_shifting import is_printable_ascii, shift_right


class BitShiftingTest(unittest.TestCase):
    def test_shift_right_moves_bits_towards_the_start(self):
        self.assertEqual(shift_right(b'\x00\xff', 4), b'\xf0\x0f')

    def test_shift_by_zero_returns_the_payload_itself(self):
        self.assertEqual(shift_right(b'abc', 0), b'abc')

    def test_is_printable_ascii(self):
        self.assertTrue(is_printable_ascii(b'Hello [CER]'))
        self.assertFalse(is_printable_ascii(b'bad\x01'))


class PlayerNameHeuristicsTest(unittest.TestCase):
    def test_real_names_are_plausible(self):
        self.assertTrue(PlayerNameHeuristics.looks_like_player_name('[CER]Nr32_JAw'))

    def test_short_names_are_not(self):
        self.assertFalse(PlayerNameHeuristics.looks_like_player_name('abc'))

    def test_quotes_and_backslashes_are_not(self):
        self.assertFalse(PlayerNameHeuristics.looks_like_player_name('abcdefg"hij'))
        self.assertFalse(PlayerNameHeuristics.looks_like_player_name('abcdefg\\hij'))

    def test_mostly_symbols_are_not(self):
        self.assertFalse(PlayerNameHeuristics.looks_like_player_name('ab-----------'))


class JoinRecordScannerTest(unittest.TestCase):
    def test_finds_a_name_with_its_player_id(self):
        roster = JoinRecordScanner().scan([(1.0, support.join_record(4, 'Napoleon'))])
        self.assertEqual(roster, {3: [NameSighting(1.0, 1.0, 'Napoleon', 1)]})

    def test_counts_packets_and_keeps_first_and_last_time(self):
        roster = JoinRecordScanner().scan([(5.0, support.join_record(2, 'Napoleon')), (1.0, support.join_record(2, 'Napoleon')), (9.0, support.join_record(2, 'Napoleon'))])
        self.assertEqual(roster[1], [NameSighting(1.0, 9.0, 'Napoleon', 3)])

    def test_finds_a_name_at_any_bit_offset(self):
        shifted = (int.from_bytes(support.join_record(7, 'Kutuzov12'), 'little') << 3).to_bytes(40, 'little')
        self.assertEqual(JoinRecordScanner().scan([(2.0, shifted)])[6][0].name, 'Kutuzov12')

    def test_a_single_sighting_of_an_implausible_name_is_dropped(self):
        self.assertEqual(JoinRecordScanner().scan([(1.0, support.join_record(4, 'a b c'))]), {})

    def test_min_count_drops_rare_names(self):
        self.assertEqual(JoinRecordScanner().scan([(1.0, support.join_record(4, 'Napoleon'))], min_count=2), {})

    def test_the_alternative_record_counts_only_for_names_seen_as_players(self):
        payloads = [(1.0, support.join_record(4, 'Napoleon')), (2.0, b'\x11' * 12 + b'\x03\x04\x08\x00Napoleon' + b'\x11' * 12),
                    (3.0, b'\x11' * 12 + b'\x03\x05\x08\x00Stranger1' + b'\x11' * 12)]
        sightings = JoinRecordScanner().scan(payloads)
        self.assertEqual(sightings[3][0].count, 2)
        self.assertNotIn(4, sightings)

    def test_short_payloads_are_ignored(self):
        self.assertEqual(JoinRecordScanner().scan([(1.0, b'\x06\x01\x03\x00abc')]), {})


class PlayerRosterTest(unittest.TestCase):
    def setUp(self):
        self.roster = PlayerRoster({1: [NameSighting(0.0, 50.0, 'First', 4), NameSighting(100.0, 200.0, 'Second', 3)], 2: [NameSighting(10.0, 20.0, 'Other', 2)]})

    def test_scan_builds_a_roster_from_payloads(self):
        self.assertEqual(PlayerRoster.scan([(1.0, support.join_record(4, 'Napoleon'))]).name_at(3, 5.0), 'Napoleon')

    def test_sightings_and_slots(self):
        self.assertEqual(len(self.roster.sightings(1)), 2)
        self.assertEqual(self.roster.sightings(9), [])
        self.assertTrue(self.roster.has_slot(2) and not self.roster.has_slot(9))
        self.assertEqual(self.roster.name_count(), 3)

    def test_name_at_gives_the_holder_at_that_time(self):
        self.assertEqual(self.roster.name_at(1, 60.0), 'First')
        self.assertEqual(self.roster.name_at(1, 150.0), 'Second')

    def test_a_name_counts_a_few_seconds_before_its_first_sighting(self):
        self.assertEqual(self.roster.name_at(1, 96.0), 'Second')
        self.assertEqual(self.roster.name_at(1, 94.0), 'First')

    def test_before_all_sightings_the_first_name_is_used(self):
        self.assertEqual(self.roster.name_at(2, 0.0), 'Other')

    def test_an_unknown_slot_has_no_name(self):
        self.assertIsNone(self.roster.name_at(9, 1.0))

    def test_slot_of_name_containing_ignores_case_and_gives_the_last_match(self):
        self.assertEqual(self.roster.slot_of_name_containing('OTHER'), 2)
        self.assertIsNone(self.roster.slot_of_name_containing('nobody'))

    def test_merge_join_records_adds_new_names_and_extends_known_ones(self):
        records = [dict(t=300.0, joins=[(2, 'Second')]), dict(t=5.0, joins=[(4, 'Fresh')]), dict(t=6.0, joins=[])]
        self.assertEqual(self.roster.merge_join_records(records), 1)
        self.assertEqual(self.roster.sightings(1)[1], NameSighting(100.0, 300.0, 'Second', 3))
        self.assertEqual(self.roster.sightings(3), [NameSighting(5.0, 5.0, 'Fresh', 1)])

    def test_retire_moved_names_marks_the_old_slot_unknown(self):
        roster = PlayerRoster({1: [NameSighting(0.0, 50.0, 'Napoleon', 5)], 4: [NameSighting(300.0, 400.0, 'Napoleon', 5)]})
        unknown_since = roster.retire_moved_names()
        self.assertEqual(unknown_since, {1: 300.0})
        self.assertEqual(roster.name_at(1, 310.0), '')
        self.assertEqual(roster.name_at(1, 100.0), 'Napoleon')

    def test_retire_moved_names_ignores_a_name_that_stays(self):
        self.assertEqual(self.roster.retire_moved_names(), {})

    def test_retire_moved_names_does_not_mark_twice(self):
        roster = PlayerRoster({1: [NameSighting(0.0, 50.0, 'Napoleon', 5)], 4: [NameSighting(300.0, 400.0, 'Napoleon', 5)]})
        roster.retire_moved_names()
        roster.retire_moved_names()
        self.assertEqual(len(roster.sightings(1)), 2)


class RosterFillerTest(unittest.TestCase):
    def payloads(self, player_id, name, times):
        return [(time_s, support.name_record(player_id, name)) for time_s in times]

    def test_fills_a_slot_whose_name_repeats_at_separate_moments(self):
        roster = PlayerRoster()
        RosterFiller().fill(roster, self.payloads(5, 'Wellington', [1.0, 2.0, 60.0]), [4])
        self.assertEqual(roster.sightings(4), [NameSighting(1.0, 60.0, 'Wellington', 3)])

    def test_a_name_seen_in_one_moment_only_is_not_enough(self):
        roster = PlayerRoster()
        RosterFiller().fill(roster, self.payloads(5, 'Wellington', [1.0, 2.0, 3.0]), [4])
        self.assertEqual(roster.sightings(4), [])

    def test_a_tagged_name_is_enough_with_one_moment(self):
        roster = PlayerRoster()
        RosterFiller().fill(roster, self.payloads(5, '[CER]Wellington', [1.0]), [4])
        self.assertEqual(roster.name_at(4, 1.0), '[CER]Wellington')

    def test_slots_that_have_a_name_are_left_alone(self):
        roster = PlayerRoster({4: [NameSighting(0.0, 9.0, 'Known', 3)]})
        RosterFiller().fill(roster, self.payloads(5, 'Wellington', [1.0, 2.0, 60.0]), [4])
        self.assertEqual(roster.name_at(4, 5.0), 'Known')

    def test_no_slots_needing_names_changes_nothing(self):
        roster = PlayerRoster()
        self.assertIs(RosterFiller().fill(roster, [], []), roster)

    def test_a_retired_slot_keeps_its_old_name_and_ignores_sightings_before_the_retirement(self):
        roster = PlayerRoster({4: [NameSighting(0.0, 9.0, 'Old', 3)]})
        RosterFiller().fill(roster, self.payloads(5, 'Wellington', [1.0, 2.0, 60.0, 70.0, 130.0]), [4], unknown_since={4: 50.0})
        self.assertEqual([sighting.name for sighting in roster.sightings(4)], ['Old', 'Wellington'])
        self.assertEqual(roster.sightings(4)[1].first_seen_s, 60.0)

    def test_an_earlier_occupant_is_added_before_the_known_name(self):
        roster = PlayerRoster({4: [NameSighting(100.0, 200.0, 'Later', 3)]})
        RosterFiller().fill(roster, self.payloads(5, 'Earlier1', [1.0, 20.0]), [4], earlier_occupant_slots=[4])
        self.assertEqual([sighting.name for sighting in roster.sightings(4)], ['Earlier1', 'Later'])


class UnnamedSlotFinderTest(unittest.TestCase):
    def test_slots_without_a_name_at_the_event_are_found(self):
        roster = PlayerRoster({1: [NameSighting(0.0, 9.0, 'Known', 3)]})
        events = [dict(time=5.0, killer_slot=1, victim_slot=2), dict(time=6.0, killer_slot=-1, victim_slot=None)]
        self.assertEqual(UnnamedSlotFinder(roster).find(events), ({2}, set()))

    def test_a_slot_whose_first_name_comes_late_and_held_another_slot_before_is_flagged(self):
        roster = PlayerRoster({1: [NameSighting(500.0, 600.0, 'Napoleon', 3)], 2: [NameSighting(0.0, 100.0, 'Napoleon', 3)]})
        unnamed, earlier = UnnamedSlotFinder(roster).find([dict(time=10.0, killer_slot=1, victim_slot=None)])
        self.assertEqual(earlier, {1})

    def test_a_first_name_that_is_not_late_is_not_flagged(self):
        roster = PlayerRoster({1: [NameSighting(8.0, 600.0, 'Napoleon', 3)], 2: [NameSighting(0.0, 100.0, 'Napoleon', 3)]})
        self.assertEqual(UnnamedSlotFinder(roster).find([dict(time=10.0, killer_slot=1, victim_slot=None)])[1], set())


if __name__ == '__main__':
    unittest.main()
