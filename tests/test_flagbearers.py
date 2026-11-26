import json
import os
import tempfile
import unittest
import support
from nwkills.rounds import Round, RoundTimeline
from nwkills.flagbearers import FlagTable, FlagbearerReport, ServerKindDetector, SpawnExtractor

TABLE = FlagTable(dict(troops={'3': dict(name='trp_nco', flags=[40])}, items={'40': 'itm_flag_france'}))
TIMELINE = RoundTimeline([Round(1, 0.0, 100.0, 0, '', '', kind='live'), Round(2, 100.0, 1000.0, 0, '', '', kind='live')])
NAMER = lambda slot, time_s: 'P%d' % slot if slot != 9 else '?'


def spawn_record(time_s, agent=1, owner=2, troop=3, items=(40,)):
    return support.packet_record(time_s, messages=[support.spawn_message(agent, owner, troop=troop, items=items)])


class FlagTableTest(unittest.TestCase):
    def test_load_reads_the_table_of_a_server_kind(self):
        directory = tempfile.mkdtemp()
        with open(os.path.join(directory, 'flag_troops_nw.json'), 'w') as table_file:
            json.dump(dict(troops={'1': dict(name='trp_x', flags=[2])}, items={'2': 'itm_y'}, always=True), table_file)
        table = FlagTable.load(directory, 'nw')
        self.assertEqual((table.troops['1']['name'], table.items['2'], table.every_spawn_counts), ('trp_x', 'itm_y', True))

    def test_load_gives_none_without_a_table(self):
        self.assertIsNone(FlagTable.load(tempfile.mkdtemp(), 'nwe'))

    def test_every_spawn_counts_is_off_by_default(self):
        self.assertFalse(TABLE.every_spawn_counts)

    def test_the_tables_that_ship_with_the_tool_load(self):
        data_directory = os.path.join(os.path.dirname(__file__), '..', 'nwkills', 'data')
        self.assertIsNotNone(FlagTable.load(data_directory, 'nw'))


class ServerKindDetectorTest(unittest.TestCase):
    def test_small_item_ids_mean_the_nw_module(self):
        self.assertEqual(ServerKindDetector().detect([spawn_record(1.0, items=(5, 1000))]), 'nw')

    def test_item_ids_over_1023_mean_the_nwe_module(self):
        self.assertEqual(ServerKindDetector().detect([spawn_record(1.0, items=(5, 1500))]), 'nwe')

    def test_a_capture_without_spawns_is_nw(self):
        self.assertEqual(ServerKindDetector().detect([]), 'nw')


class SpawnExtractorTest(unittest.TestCase):
    def test_a_spawn_has_agent_owner_troop_and_items(self):
        [spawn] = SpawnExtractor().extract([spawn_record(5.0, agent=7, owner=3, troop=2, items=(10, 11))])
        self.assertEqual((spawn.time_s, spawn.agent, spawn.owner_slot, spawn.troop_index, spawn.item_indexes), (5.0, 7, 3, 2, (10, 11)))

    def test_repeats_of_a_spawn_message_are_dropped(self):
        self.assertEqual(len(SpawnExtractor().extract([spawn_record(5.0), spawn_record(7.0), spawn_record(9.0)])), 1)

    def test_the_same_spawn_much_later_counts_again(self):
        self.assertEqual(len(SpawnExtractor().extract([spawn_record(5.0), spawn_record(50.0)])), 2)

    def test_other_messages_are_ignored(self):
        self.assertEqual(SpawnExtractor().extract([support.packet_record(5.0, messages=[support.death_message(1, 2)])]), [])


class FlagbearerReportTest(unittest.TestCase):
    def build(self, records, table=TABLE):
        return FlagbearerReport(table, TIMELINE, NAMER).build(records)

    def test_a_troop_that_can_carry_a_flag_with_the_flag_in_its_loadout_is_a_flagbearer(self):
        [row] = self.build([spawn_record(5.0)])
        self.assertEqual((row.round_number, row.round_kind, row.player, row.owner_slot, row.troop, row.flag, row.spawn_count), (1, 'live', 'P2', 2, 'nco', 'flag_france', 1))
        self.assertEqual((row.first_spawn_s, row.last_spawn_s, row.review), (5.0, 5.0, ''))

    def test_a_loadout_without_the_flag_is_not(self):
        self.assertEqual(self.build([spawn_record(5.0, items=(41,))]), [])

    def test_a_troop_that_cannot_carry_flags_is_not(self):
        self.assertEqual(self.build([spawn_record(5.0, troop=4)]), [])

    def test_agents_without_an_owner_are_not(self):
        self.assertEqual(self.build([spawn_record(5.0, owner=-1)]), [])

    def test_with_every_spawn_counting_the_flag_may_be_unknown(self):
        table = FlagTable(dict(troops={'3': dict(name='trp_x_flag_bearer', flags=[40])}, items={'40': 'itm_flag'}, always=True))
        [row] = self.build([spawn_record(5.0, items=())], table)
        self.assertEqual(row.flag, 'unknown')

    def test_spawns_of_a_player_in_one_round_are_counted_together(self):
        [row] = self.build([spawn_record(5.0), spawn_record(50.0), spawn_record(150.0)])[:1]
        self.assertEqual((row.spawn_count, row.first_spawn_s, row.last_spawn_s), (2, 5.0, 50.0))

    def test_rows_are_sorted_by_round_then_name(self):
        rows = self.build([spawn_record(150.0, owner=1), spawn_record(5.0, owner=3), spawn_record(6.0, agent=2, owner=1)])
        self.assertEqual([(row.round_number, row.player) for row in rows], [(1, 'P1'), (1, 'P3'), (2, 'P1')])

    def test_an_unknown_name_needs_review(self):
        [row] = self.build([spawn_record(5.0, owner=9)])
        self.assertEqual(row.review, 'name?')


if __name__ == '__main__':
    unittest.main()
