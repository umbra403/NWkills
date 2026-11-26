import unittest
import support
from nwkills.events.admin_actions import AdminAction, AdminActionFinder
from nwkills.events.mass_deaths import MapChangeDeathFilter
from nwkills.events.score_timeline import ScoreTimeline
from nwkills.events.score_updates import ScoreUpdateFilter
from nwkills.events.weapon_names import WEAPON_NAMES, weapon_name


class WeaponNamesTest(unittest.TestCase):
    def test_known_classes_have_names(self):
        self.assertEqual(weapon_name(20), 'artillery: cannonball')
        self.assertEqual(weapon_name(3), 'cavalry: horse charge (rider hit)')

    def test_unknown_classes_are_named_by_number(self):
        self.assertEqual(weapon_name(31), 'class 31')

    def test_every_class_up_to_26_is_named(self):
        self.assertEqual(sorted(WEAPON_NAMES), list(range(27)))


class AdminActionFinderTest(unittest.TestCase):
    def find(self, *records):
        return AdminActionFinder().find(records)

    def test_finds_the_three_kinds_of_actions(self):
        actions = self.find(support.packet_record(1.0, texts=['Boss Slayed Player Bob.']), support.packet_record(5.0, texts=['Boss Slayed Everyone.']),
                            support.packet_record(9.0, texts=['Boss Swapped Everyone to Spectators']))
        self.assertEqual(actions, [AdminAction(1.0, 'slay', 'Boss', 'Bob'), AdminAction(5.0, 'slay_all', 'Boss', None), AdminAction(9.0, 'swap_all', 'Boss', None)])

    def test_the_second_copy_within_a_second_is_dropped(self):
        self.assertEqual(len(self.find(support.packet_record(1.0, texts=['Boss Slayed Everyone.']), support.packet_record(1.5, texts=['Boss Slayed Everyone.']))), 1)

    def test_a_repeat_after_a_second_is_a_new_action(self):
        self.assertEqual(len(self.find(support.packet_record(1.0, texts=['Boss Slayed Everyone.']), support.packet_record(3.0, texts=['Boss Slayed Everyone.']))), 2)

    def test_other_text_is_ignored(self):
        self.assertEqual(self.find(support.packet_record(1.0, texts=['Bob joined the game.'])), [])


class ScoreUpdateFilterTest(unittest.TestCase):
    RAW = [(1.0, 3, 5, True), (1.2, 3, 5, True),         # seen twice: believed
           (10.0, 4, 500, True),                           # seen once, large: dropped
           (11.0, 5, 7, True),                             # seen once, small: kept in mode 3
           (12.0, 6, 8, False)]                            # only in an unclean packet: dropped

    def test_default_mode_keeps_repeated_values_and_single_small_ones(self):
        self.assertEqual(ScoreUpdateFilter('3').keep_reliable(self.RAW), [(3, 1.0, 5), (3, 1.2, 5), (5, 11.0, 7)])

    def test_mode_two_needs_a_repeat(self):
        self.assertEqual(ScoreUpdateFilter('2').keep_reliable(self.RAW), [(3, 1.0, 5), (3, 1.2, 5)])

    def test_mode_one_keeps_every_clean_value(self):
        self.assertEqual([update[0] for update in ScoreUpdateFilter('1').keep_reliable(self.RAW)], [3, 3, 4, 5])

    def test_mode_zero_keeps_everything_in_order(self):
        self.assertEqual(len(ScoreUpdateFilter('0').keep_reliable(self.RAW)), 5)

    def test_the_same_value_far_apart_is_two_sightings(self):
        raw = [(1.0, 3, 500, True), (50.0, 3, 500, True)]
        self.assertEqual(ScoreUpdateFilter('3').keep_reliable(raw), [])

    def test_the_mode_comes_from_the_environment_by_default(self):
        import os
        os.environ['NWOBS'] = '0'
        try:
            self.assertEqual(len(ScoreUpdateFilter().keep_reliable(self.RAW)), 5)
        finally:
            del os.environ['NWOBS']


class ScoreTimelineTest(unittest.TestCase):
    def setUp(self):
        self.timeline = ScoreTimeline([(1, 10.0, 0), (1, 20.0, 1), (1, 30.0, 0), (2, 15.0, 5)])

    def test_slots_and_history(self):
        self.assertEqual(self.timeline.slots(), [1, 2])
        self.assertEqual(self.timeline.history(1), [(10.0, 0), (20.0, 1), (30.0, 0)])
        self.assertEqual(self.timeline.history(9), [])

    def test_scores_before_excludes_the_moment_itself(self):
        self.assertEqual(self.timeline.scores_before(1, 20.0), [0])
        self.assertEqual(self.timeline.times_before(1, 20.0), [10.0])

    def test_scores_between_includes_both_ends(self):
        self.assertEqual(self.timeline.scores_between(1, 20.0, 30.0), [1, 0])
        self.assertEqual(self.timeline.timed_scores_between(1, 20.0, 30.0), [(20.0, 1), (30.0, 0)])

    def test_single_point_changes_lists_steps_of_one(self):
        self.assertEqual(self.timeline.single_point_changes(), {1: [(20.0, 1), (30.0, -1)]})

    def test_bigger_steps_are_not_single_point_changes(self):
        self.assertEqual(ScoreTimeline([(1, 1.0, 0), (1, 2.0, 5)]).single_point_changes(), {})


class MapChangeDeathFilterTest(unittest.TestCase):
    def records(self, agent_count, spread_s=0.05):
        return [support.packet_record(100.0 + i * spread_s, messages=[(13, [i + 1, i + 1, 0, 0, 0])]) for i in range(agent_count)]

    def test_a_block_of_self_deaths_is_found(self):
        self.assertEqual(len(MapChangeDeathFilter().find_block_times(self.records(10), [])), 10)

    def test_a_few_self_deaths_are_not_a_block(self):
        self.assertEqual(MapChangeDeathFilter().find_block_times(self.records(5), []), set())

    def test_a_block_announced_by_an_admin_is_kept(self):
        self.assertEqual(MapChangeDeathFilter().find_block_times(self.records(10), [100.0]), set())

    def test_deaths_by_somebody_else_are_not_self_deaths(self):
        records = [support.packet_record(100.0 + i * 0.05, messages=[(13, [i + 1, 99, 0, 0, 0])]) for i in range(10)]
        self.assertEqual(MapChangeDeathFilter().find_block_times(records, []), set())

    def test_self_deaths_spread_over_a_long_time_are_not_a_block(self):
        self.assertEqual(MapChangeDeathFilter().find_block_times(self.records(10, spread_s=2.0), []), set())


if __name__ == '__main__':
    unittest.main()
