import collections
import unittest
import support
from nwkills.events.evidence import AgentTime, EvidenceCollector, OwnerSighting, PacketEvidence, ProjectileShot, RawDeath
from nwkills.events.local_player import LocalPlayerTracker
from nwkills.events.ownership import AgentOwnership, RespawnIndex
from nwkills.events.riders import HorseRiderSubstituter, RiderLinkHistory
from nwkills.events.teams import TeamHistory


def death(time_s=10.0, victim=1, killer=2, weapon_class=12, mode=2):
    return RawDeath(time_s, victim, killer, weapon_class, None, mode, 0)


class EvidenceCollectorTest(unittest.TestCase):
    def collect(self, records, mass=()):
        return EvidenceCollector().collect(records, set(mass))

    def test_a_death_message_becomes_a_raw_death(self):
        evidence = self.collect([support.packet_record(5.0, messages=[support.death_message(3, 4, weapon_class=5, mode=2, hit=77)])])
        self.assertEqual(evidence.deaths, [RawDeath(5.0, 3, 4, 5, 77, 2, 0)])

    def test_the_server_repeating_a_death_is_one_death(self):
        records = [support.packet_record(5.0 + 0.5 * i, messages=[support.death_message(3, 4)]) for i in range(4)]
        self.assertEqual(len(self.collect(records).deaths), 1)

    def test_the_same_pair_much_later_is_a_new_death(self):
        records = [support.packet_record(5.0, messages=[support.death_message(3, 4)]), support.packet_record(50.0, messages=[support.death_message(3, 4)])]
        self.assertEqual(len(self.collect(records).deaths), 2)

    def test_self_deaths_of_a_map_change_are_skipped(self):
        records = [support.packet_record(5.0, messages=[(13, [4, 4, 0, 0, 0])])]
        self.assertEqual(self.collect(records, mass=[5.0]).deaths, [])
        self.assertEqual(len(self.collect(records).deaths), 1)

    def test_a_spawn_gives_an_owner_a_team_and_a_spawn_message(self):
        evidence = self.collect([support.packet_record(40.0, messages=[support.spawn_message(7, 3, team=2)])])
        self.assertEqual(evidence.owner_sightings, [OwnerSighting(40.0, 7, 3)])
        self.assertEqual(evidence.spawn_messages, [AgentTime(7, 40.0)])
        self.assertEqual(evidence.team_spawns[7], [(40.0, 2)])

    def test_local_respawns_and_projectiles_are_collected(self):
        evidence = self.collect([support.packet_record(8.0, messages=[(18, [6]), (6, [0, 0, 0, 0, 3, 9])])])
        self.assertEqual(evidence.local_respawns, [AgentTime(5, 8.0)])
        self.assertEqual(evidence.projectile_shots, [ProjectileShot(8.0, 2, 8)])

    def test_state_block_properties(self):
        evidence = self.collect([support.packet_record(50.0, agents=[(4, 27, 6), (4, 13, 1), (4, 7, 9), (5, 6, 1)], players=[(2, 0, 12), (2, 1, 40), (3, 0, 4090)])])
        self.assertEqual(evidence.owner_sightings, [OwnerSighting(50.0, 4, 5)])
        self.assertEqual(evidence.dying_times[4], [50.0])
        self.assertEqual(sorted(evidence.rider_property_times), [4, 5])
        self.assertEqual(evidence.raw_score_updates, [(50.0, 2, 12, True), (50.0, 3, 4090, True)])

    def test_scores_of_4096_and_more_are_negative(self):
        evidence = self.collect([support.packet_record(50.0, players=[(2, 0, 8190)])])
        self.assertEqual(evidence.raw_score_updates[0][2], -2)

    def test_early_owner_sightings_keep_only_their_order(self):
        evidence = self.collect([support.packet_record(10.0, agents=[(4, 27, 6)])])
        self.assertAlmostEqual(evidence.owner_sightings[0].time_s, 10.0e-6)

    def test_an_unclean_packet_gives_no_owners_and_unclean_scores(self):
        record = support.packet_record(50.0, agents=[(4, 27, 6)], players=[(2, 0, 12)])
        record['err'] = 'tail'
        evidence = self.collect([record])
        self.assertEqual(evidence.owner_sightings, [])
        self.assertEqual(evidence.raw_score_updates, [(50.0, 2, 12, False)])

    def test_a_packet_without_state_block_adds_nothing_from_it(self):
        self.assertEqual(self.collect([support.packet_record(50.0, has_state_block=False)]).owner_sightings, [])


class AgentOwnershipTest(unittest.TestCase):
    def setUp(self):
        self.ownership = AgentOwnership([OwnerSighting(10.0, 1, 5), OwnerSighting(50.0, 1, 6), OwnerSighting(10.0, 1, 5), OwnerSighting(70.0, 2, 8)])

    def test_sightings_are_sorted_and_unique(self):
        self.assertEqual(len(self.ownership.sightings), 3)
        self.assertEqual(self.ownership.sightings_of(1), [OwnerSighting(10.0, 1, 5), OwnerSighting(50.0, 1, 6)])
        self.assertEqual(self.ownership.sightings_of(99), [])

    def test_owner_at_is_the_latest_sighting_before_the_moment(self):
        self.assertEqual(self.ownership.owner_at(1, 30.0), 5)
        self.assertEqual(self.ownership.owner_at(1, 60.0), 6)

    def test_owner_at_needs_the_sighting_to_be_a_moment_old(self):
        self.assertIsNone(self.ownership.owner_at(1, 10.1))
        self.assertIsNone(self.ownership.owner_at(99, 10.0))

    def test_owner_learned_later_from_data_after_the_event(self):
        self.assertEqual(self.ownership.owner_learned_later(2, 60.0, [], []), 8)

    def test_owner_learned_later_ignores_sightings_after_the_next_death(self):
        self.assertIsNone(self.ownership.owner_learned_later(2, 60.0, [65.0], []))

    def test_owner_learned_later_ignores_sightings_with_a_spawn(self):
        self.assertIsNone(self.ownership.owner_learned_later(2, 60.0, [], [70.1]))

    def test_owner_learned_later_needs_agreement(self):
        ownership = AgentOwnership([OwnerSighting(70.0, 2, 8), OwnerSighting(80.0, 2, 9)])
        self.assertIsNone(ownership.owner_learned_later(2, 60.0, [], []))

    def test_add_sightings(self):
        self.ownership.add_sightings([OwnerSighting(5.0, 3, 1)])
        self.assertEqual(self.ownership.owner_at(3, 20.0), 1)

    def test_has_sighting_near(self):
        self.assertTrue(self.ownership.has_sighting_near(1, 12.0, 4.0))
        self.assertFalse(self.ownership.has_sighting_near(1, 30.0, 4.0))


class RespawnIndexTest(unittest.TestCase):
    def setUp(self):
        sightings = [OwnerSighting(100.0, 5, 3), OwnerSighting(140.0, 6, 3), OwnerSighting(500.0, 7, 3)]
        self.index = RespawnIndex(AgentOwnership(sightings), [AgentTime(6, 140.0), AgentTime(7, 500.0)])

    def test_the_delay_to_the_next_spawn_of_the_slot(self):
        self.assertEqual(self.index.delay_after_death(3, 5, 110.0), 30.0)

    def test_a_respawn_over_two_minutes_away_is_not_reported(self):
        self.assertIsNone(self.index.delay_after_death(3, 6, 200.0))

    def test_only_sightings_with_a_spawn_message_count(self):
        self.assertEqual(self.index.delay_after_death(3, 9, 90.0), 50.0)       # the sighting at 100 s has no spawn message

    def test_the_dead_agent_itself_does_not_count(self):
        self.assertIsNone(self.index.delay_after_death(3, 6, 139.0))

    def test_unknown_slots_have_no_delay(self):
        self.assertIsNone(self.index.delay_after_death(9, 1, 0.0))


class LocalPlayerTrackerTest(unittest.TestCase):
    def test_the_slot_whose_agent_died_before_an_unowned_respawn_is_the_local_player(self):
        ownership = AgentOwnership([OwnerSighting(1e-6, 4, 7)])
        tracker = LocalPlayerTracker(ownership, [AgentTime(9, 55.0)])
        self.assertEqual(tracker.detect_slot([death(50.0, victim=4)]), 7)

    def test_a_respawn_of_an_owned_agent_is_not_the_local_player(self):
        ownership = AgentOwnership([OwnerSighting(1e-6, 4, 7), OwnerSighting(55.0, 9, 2)])
        self.assertIsNone(LocalPlayerTracker(ownership, [AgentTime(9, 55.0)]).detect_slot([death(50.0, victim=4)]))

    def test_no_deaths_no_slot(self):
        self.assertIsNone(LocalPlayerTracker(AgentOwnership([]), []).detect_slot([]))

    def test_the_next_respawn_agent_becomes_the_local_players(self):
        ownership = AgentOwnership([OwnerSighting(1e-6, 4, 7)])
        LocalPlayerTracker(ownership, [AgentTime(9, 55.0), AgentTime(12, 155.0)]).add_respawn_ownership([death(50.0, victim=4), death(150.0, victim=9)], 7)
        self.assertEqual(ownership.owner_at(9, 100.0), 7)
        self.assertEqual(ownership.owner_at(12, 200.0), 7)

    def test_without_a_starting_agent_nothing_is_added(self):
        ownership = AgentOwnership([])
        LocalPlayerTracker(ownership, [AgentTime(9, 55.0)]).add_respawn_ownership([death(50.0, victim=4)], 7)
        self.assertEqual(ownership.sightings, [])


class TeamHistoryTest(unittest.TestCase):
    def setUp(self):
        self.teams = TeamHistory({1: [(50.0, 2), (10.0, 1)]})

    def test_the_team_of_the_latest_spawn(self):
        self.assertEqual((self.teams.team_at(1, 20.0), self.teams.team_at(1, 60.0)), (1, 2))

    def test_a_spawn_a_moment_after_counts(self):
        self.assertEqual(self.teams.team_at(1, 49.97), 2)

    def test_before_the_first_spawn_or_for_an_unknown_agent_there_is_no_team(self):
        self.assertIsNone(self.teams.team_at(1, 5.0))
        self.assertIsNone(self.teams.team_at(9, 5.0))


class RiderLinkHistoryTest(unittest.TestCase):
    def test_links_come_from_type_30_messages(self):
        history = RiderLinkHistory([support.packet_record(40.0, links=[(5, 8)]), support.packet_record(20.0, links=[(5, -1)])])
        self.assertTrue(history.knows_horse(5))
        self.assertEqual(history.links_of(5), [(20.0, -1), (40.0, 8)])

    def test_a_rider_spawn_followed_by_an_unowned_horse_spawn_is_a_link(self):
        record = support.packet_record(60.0, messages=[support.spawn_message(8, 3, team=1), support.spawn_message(5, -1, team=0)])
        self.assertEqual(RiderLinkHistory([record]).links_of(5), [(60.0, 8)])

    def test_spawn_order_in_the_first_30_seconds_means_nothing(self):
        record = support.packet_record(10.0, messages=[support.spawn_message(8, 3, team=1), support.spawn_message(5, -1, team=0)])
        self.assertFalse(RiderLinkHistory([record]).knows_horse(5))

    def test_an_unknown_horse(self):
        self.assertFalse(RiderLinkHistory([]).knows_horse(1))


class HorseRiderSubstituterTest(unittest.TestCase):
    def substitute(self, deaths, links, spawns=None, death_times=None):
        history = RiderLinkHistory([support.packet_record(time_s, links=[link]) for time_s, link in links])
        HorseRiderSubstituter(history, spawns or {}, death_times or {}).substitute(deaths)
        return deaths

    def test_the_rider_is_credited_instead_of_the_horse(self):
        [charge] = self.substitute([death(100.0, victim=1, killer=5, weapon_class=3)], [(50.0, (5, 8))])
        self.assertEqual((charge.killer_agent, charge.horse_agent, charge.via_rider_link), (8, 5, True))

    def test_other_weapons_are_left_alone(self):
        [blow] = self.substitute([death(100.0, killer=5, weapon_class=12)], [(50.0, (5, 8))])
        self.assertEqual((blow.killer_agent, blow.via_rider_link), (5, False))

    def test_a_horse_without_a_rider_is_marked(self):
        [charge] = self.substitute([death(100.0, killer=5, weapon_class=3)], [(50.0, (5, -1))])
        self.assertEqual((charge.killer_agent, charge.horse_without_rider), (5, True))

    def test_a_rider_who_died_since_the_link_is_gone(self):
        [charge] = self.substitute([death(100.0, killer=5, weapon_class=3)], [(50.0, (5, 8))], death_times={8: [70.0]})
        self.assertTrue(charge.horse_without_rider)

    def test_a_rider_agent_spawned_again_since_the_link_is_gone(self):
        [charge] = self.substitute([death(100.0, killer=5, weapon_class=3)], [(50.0, (5, 8))], spawns={8: [80.0]})
        self.assertTrue(charge.horse_without_rider)

    def test_a_link_from_before_the_horse_spawned_again_does_not_count(self):
        [charge] = self.substitute([death(100.0, killer=5, weapon_class=3)], [(50.0, (5, 8))], spawns={5: [90.0]})
        self.assertEqual((charge.killer_agent, charge.via_rider_link, charge.horse_without_rider), (5, False, False))

    def test_a_horse_with_no_links_is_left_alone(self):
        [charge] = self.substitute([death(100.0, killer=5, weapon_class=3)], [])
        self.assertEqual(charge.killer_agent, 5)


if __name__ == '__main__':
    unittest.main()
