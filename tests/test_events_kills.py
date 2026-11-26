import unittest
import support
from nwkills.events.charge_kills import ChargeKillClaimer
from nwkills.events.evidence import AgentTime, OwnerSighting, PacketEvidence, ProjectileShot, RawDeath
from nwkills.events.kill_builder import KillEventBuilder
from nwkills.events.kill_decoder import KillDecoder
from nwkills.events.kill_event import KillEvent
from nwkills.events.ownership import AgentOwnership
from nwkills.events.score_steps import ScoreStepAssigner, TeamkillCrossChecker
from nwkills.events.score_timeline import ScoreTimeline
from nwkills.events.teams import TeamHistory
from nwkills.events.volley_teamkills import VolleyTeamkillEstimator


def namer(slot, time_s):
    return '?' if slot is None else '(AI)' if slot < 0 else 'P%d' % slot


def kill_event(time_s=10.0, killer_slot=1, victim_slot=2, **changes):
    values = dict(time_s=time_s, killer='P%s' % killer_slot, victim='P%s' % victim_slot, weapon='x', teamkill='', team_verdict=None, killer_slot=killer_slot,
                  victim_slot=victim_slot, killer_agent=10, victim_agent=20, hit=None, score_change=None, score_baseline_s=None, mode=2,
                  respawn_delay_s=None, weapon_class=12, extra_field_count=0)
    values.update(changes)
    return KillEvent(**values)


class KillEventBuilderTest(unittest.TestCase):
    def builder(self, sightings=(), scores=(), team_spawns=None, evidence=None, items=None, spawn_times=None, death_times=None):
        evidence = evidence or PacketEvidence()
        return KillEventBuilder(AgentOwnership(sightings), ScoreTimeline(scores), TeamHistory(team_spawns or {}), evidence, spawn_times or {},
                                death_times or {}, namer, items)

    OWNERS = [OwnerSighting(1.0, 20, 1), OwnerSighting(1.0, 21, 2)]

    def test_names_come_from_the_owners_of_the_agents(self):
        [event] = self.builder(self.OWNERS).build([RawDeath(10.0, 21, 20, 12, None, 2, 0)])
        self.assertEqual((event.killer, event.victim, event.killer_slot, event.victim_slot), ('P1', 'P2', 1, 2))

    def test_an_unknown_owner_shows_as_a_question_mark(self):
        [event] = self.builder().build([RawDeath(10.0, 21, 20, 12, None, 2, 0)])
        self.assertEqual((event.killer, event.victim), ('?', '?'))

    def test_the_killer_can_be_learned_from_later_data(self):
        [event] = self.builder([OwnerSighting(15.0, 20, 1)]).build([RawDeath(10.0, 21, 20, 12, None, 2, 0)])
        self.assertEqual((event.killer_slot, event.late_sources), (1, ['killer']))

    def test_time_is_rounded_to_two_places(self):
        [event] = self.builder().build([RawDeath(10.12345, 21, 20, 12, None, 2, 0)])
        self.assertEqual(event.time_s, 10.12)

    def test_weapon_names(self):
        events = self.builder().build([RawDeath(10.0, 21, 20, 20, None, 2, 0), RawDeath(20.0, 21, 20, 0, None, 1, 0), RawDeath(30.0, 21, 20, 0, None, 2, 0)])
        self.assertEqual([event.weapon for event in events], ['artillery: cannonball', 'no blow (mode 1)', 'headshot'])

    def test_a_headshot_names_the_item_that_was_shot(self):
        evidence = PacketEvidence(projectile_shots=[ProjectileShot(9.8, 20, 1)])
        [event] = self.builder(evidence=evidence, items=['itm_none', 'itm_musket']).build([RawDeath(10.0, 21, 20, 0, None, 2, 0)])
        self.assertEqual(event.weapon, 'headshot (musket)')

    def test_the_score_change_of_the_killer_goes_with_the_kill(self):
        [event] = self.builder(self.OWNERS, scores=[(1, 5.0, 3), (1, 10.5, 4)]).build([RawDeath(10.0, 21, 20, 12, None, 2, 0)])
        self.assertEqual((event.score_change, event.score_baseline_s, event.teamkill), (1, 5.0, ''))

    def test_a_lost_point_is_a_teamkill_when_the_teams_are_unknown(self):
        [event] = self.builder(self.OWNERS, scores=[(1, 5.0, 3), (1, 10.5, 2)]).build([RawDeath(10.0, 21, 20, 12, None, 2, 0)])
        self.assertEqual((event.score_change, event.teamkill), (-1, 'yes'))

    def test_the_first_score_of_a_player_is_counted_from_zero(self):
        [event] = self.builder(self.OWNERS, scores=[(1, 10.5, -1)]).build([RawDeath(10.0, 21, 20, 12, None, 2, 0)])
        self.assertEqual((event.score_change, event.score_baseline_s), (-1, None))

    def test_a_jump_to_zero_means_the_scoreboard_was_reset(self):
        [event] = self.builder(self.OWNERS, scores=[(1, 5.0, 30), (1, 10.5, 1)]).build([RawDeath(10.0, 21, 20, 12, None, 2, 0)])
        self.assertEqual(event.score_change, 1)

    def test_no_change_means_no_score_change(self):
        [event] = self.builder(self.OWNERS, scores=[(1, 5.0, 3), (1, 10.5, 3)]).build([RawDeath(10.0, 21, 20, 12, None, 2, 0)])
        self.assertIsNone(event.score_change)

    def test_the_teams_decide_a_teamkill(self):
        teams = {20: [(1.0, 1)], 21: [(1.0, 1)]}
        [event] = self.builder(self.OWNERS, team_spawns=teams).build([RawDeath(10.0, 21, 20, 12, None, 2, 0)])
        self.assertEqual((event.team_verdict, event.teamkill), (True, 'yes'))
        teams = {20: [(1.0, 1)], 21: [(1.0, 2)]}
        [event] = self.builder(self.OWNERS, team_spawns=teams).build([RawDeath(10.0, 21, 20, 12, None, 2, 0)])
        self.assertEqual((event.team_verdict, event.teamkill), (False, ''))

    def test_a_death_without_a_blow_has_no_team_verdict(self):
        teams = {20: [(1.0, 1)], 21: [(1.0, 1)]}
        [event] = self.builder(self.OWNERS, team_spawns=teams).build([RawDeath(10.0, 21, 20, 12, None, 1, 0)])
        self.assertIsNone(event.team_verdict)

    def test_the_respawn_delay_of_the_victim(self):
        evidence = PacketEvidence(spawn_messages=[AgentTime(30, 40.0)])
        [event] = self.builder(self.OWNERS + [OwnerSighting(40.0, 30, 2)], evidence=evidence).build([RawDeath(10.0, 21, 20, 12, None, 2, 0)])
        self.assertEqual(event.respawn_delay_s, 30.0)

    def test_a_death_without_a_blow_of_an_agent_that_never_rode_is_a_horse(self):
        evidence = PacketEvidence()
        evidence.rider_property_times[99].append(1.0)
        [event] = self.builder(self.OWNERS, evidence=evidence).build([RawDeath(10.0, 21, 20, 12, None, 1, 0)])
        self.assertTrue(event.horse)

    def test_an_agent_that_showed_rider_properties_is_a_rider(self):
        evidence = PacketEvidence()
        evidence.rider_property_times[21].append(9.0)
        [event] = self.builder(self.OWNERS, evidence=evidence).build([RawDeath(10.0, 21, 20, 12, None, 1, 0)])
        self.assertFalse(event.horse)


class VolleyTeamkillEstimatorTest(unittest.TestCase):
    def volley(self, victims=('A_x', 'B_x', 'A_y'), **changes):
        return [kill_event(10.0 + 0.5 * index, victim=name, victim_slot=index + 5, killer='A_z', **changes) for index, name in enumerate(victims)]

    def test_the_net_score_change_gives_the_number_of_teamkills(self):
        events = self.volley()
        VolleyTeamkillEstimator(ScoreTimeline([(1, 5.0, 10), (1, 12.0, 11)])).apply(events)      # 3 kills, net +1: one teamkill
        self.assertEqual([event.teamkill for event in events].count('yes'), 1)
        self.assertEqual([event.in_volley for event in events], [True] * 3)
        self.assertTrue(all(event.burst_guess for event in events))

    def test_victims_with_the_killers_regiment_prefix_are_the_likeliest_teamkills(self):
        events = self.volley(victims=('B_x', 'A_x', 'B_y'))
        VolleyTeamkillEstimator(ScoreTimeline([(1, 5.0, 10), (1, 12.0, 11)])).apply(events)
        self.assertEqual([event.teamkill for event in events], ['', 'yes', ''])

    def test_a_net_change_of_the_number_of_kills_means_no_teamkills(self):
        events = self.volley()
        VolleyTeamkillEstimator(ScoreTimeline([(1, 5.0, 10), (1, 12.0, 13)])).apply(events)
        self.assertEqual([event.teamkill for event in events], ['', '', ''])
        self.assertEqual([event.burst_guess for event in events], [False] * 3)

    def test_a_single_kill_is_not_a_volley(self):
        events = [kill_event()]
        VolleyTeamkillEstimator(ScoreTimeline([])).apply(events)
        self.assertIsNone(events[0].in_volley)

    def test_a_volley_with_team_verdicts_everywhere_is_left_alone(self):
        events = self.volley(team_verdict=False)
        VolleyTeamkillEstimator(ScoreTimeline([(1, 5.0, 10), (1, 12.0, 9)])).apply(events)
        self.assertEqual([event.teamkill for event in events], ['', '', ''])
        self.assertTrue(all(event.in_volley for event in events))

    def test_an_impossible_change_leaves_the_verdicts(self):
        events = self.volley()
        VolleyTeamkillEstimator(ScoreTimeline([(1, 5.0, 10), (1, 12.0, 10)])).apply(events)      # 3 kills, change 0: odd count, not possible
        self.assertEqual([event.teamkill for event in events], ['', '', ''])


class ChargeKillClaimerTest(unittest.TestCase):
    def charge(self, time_s=10.0, **changes):
        return kill_event(time_s, killer_slot=None, killer='?', weapon_class=3, **changes)

    def test_a_charge_kill_without_a_killer_takes_the_player_whose_score_changed(self):
        event = self.charge()
        ChargeKillClaimer(ScoreTimeline([(4, 5.0, 3), (4, 10.2, 4)]), namer).apply([event])
        self.assertEqual((event.killer_slot, event.killer, event.teamkill, event.late_sources, event.burst_guess), (4, 'P4', '', ['killer-from-score'], False))

    def test_a_lost_point_makes_it_a_teamkill(self):
        event = self.charge()
        ChargeKillClaimer(ScoreTimeline([(4, 5.0, 3), (4, 10.2, 2)]), namer).apply([event])
        self.assertEqual(event.teamkill, 'yes')

    def test_two_players_with_changes_in_the_window_leave_the_kill_alone(self):
        event = self.charge()
        ChargeKillClaimer(ScoreTimeline([(4, 5.0, 3), (4, 10.2, 4), (5, 5.0, 3), (5, 10.3, 4)]), namer).apply([event])
        self.assertIsNone(event.killer_slot)

    def test_a_change_explained_by_the_players_own_kill_is_not_available(self):
        own = kill_event(10.0, killer_slot=4)
        event = self.charge(10.1)
        ChargeKillClaimer(ScoreTimeline([(4, 5.0, 3), (4, 10.2, 4)]), namer).apply([own, event])
        self.assertIsNone(event.killer_slot)

    def test_a_horse_without_rider_and_without_a_score_change_is_a_runaway(self):
        event = self.charge(horse_without_rider=True)
        ChargeKillClaimer(ScoreTimeline([]), namer).apply([event])
        self.assertEqual((event.killer, event.runaway_horse), ('(runaway horse)', True))

    def test_a_horse_with_a_rider_is_not_a_runaway(self):
        event = self.charge()
        ChargeKillClaimer(ScoreTimeline([]), namer).apply([event])
        self.assertIsNone(event.runaway_horse)

    def test_other_weapons_are_not_claimed(self):
        event = kill_event(10.0, killer_slot=None, weapon_class=12)
        ChargeKillClaimer(ScoreTimeline([(4, 5.0, 3), (4, 10.2, 4)]), namer).apply([event])
        self.assertIsNone(event.killer_slot)


class ScoreStepAssignerTest(unittest.TestCase):
    def test_two_events_a_moment_apart_get_one_step_each(self):
        events = [kill_event(10.0), kill_event(11.0)]
        ScoreStepAssigner(ScoreTimeline([(1, 5.0, 5), (1, 10.2, 6), (1, 11.2, 5)])).apply(events)
        self.assertEqual([event.score_change for event in events], [1, -1])
        self.assertEqual([event.teamkill for event in events], ['', 'yes'])

    def test_a_team_verdict_is_not_overwritten(self):
        events = [kill_event(10.0, team_verdict=False), kill_event(11.0)]
        ScoreStepAssigner(ScoreTimeline([(1, 5.0, 5), (1, 10.2, 4), (1, 11.2, 3)])).apply(events)
        self.assertEqual((events[0].score_change, events[0].teamkill), (-1, ''))

    def test_a_different_number_of_steps_changes_nothing(self):
        events = [kill_event(10.0), kill_event(11.0)]
        ScoreStepAssigner(ScoreTimeline([(1, 5.0, 5), (1, 10.2, 6)])).apply(events)
        self.assertEqual([event.score_change for event in events], [None, None])

    def test_events_with_the_same_timestamp_are_left_to_the_volley_logic(self):
        events = [kill_event(10.0), kill_event(10.0)]
        ScoreStepAssigner(ScoreTimeline([(1, 5.0, 5), (1, 10.2, 6), (1, 10.4, 7)])).apply(events)
        self.assertEqual([event.score_change for event in events], [None, None])

    def test_events_in_a_volley_are_skipped(self):
        events = [kill_event(10.0, in_volley=True), kill_event(11.0, in_volley=True)]
        ScoreStepAssigner(ScoreTimeline([(1, 5.0, 5), (1, 10.2, 6), (1, 11.2, 5)])).apply(events)
        self.assertEqual([event.score_change for event in events], [None, None])


class TeamkillCrossCheckerTest(unittest.TestCase):
    def check(self, *events):
        TeamkillCrossChecker().apply(list(events))
        return [event.score_contradicts_team for event in events]

    def test_a_lost_point_against_a_friendly_verdict_is_a_contradiction(self):
        self.assertEqual(self.check(kill_event(team_verdict=False, score_change=-1)), [True])

    def test_agreement_is_not_a_contradiction(self):
        self.assertEqual(self.check(kill_event(team_verdict=True, score_change=-1)), [False])

    def test_no_team_verdict_or_no_score_change_gives_false(self):
        self.assertEqual(self.check(kill_event(team_verdict=None, score_change=-1), kill_event(100.0, team_verdict=True)), [False, False])

    def test_two_kills_close_together_say_nothing(self):
        self.assertEqual(self.check(kill_event(10.0, team_verdict=False, score_change=-1), kill_event(11.0, team_verdict=False, score_change=-1)), [False, False])

    def test_volleys_say_nothing(self):
        self.assertEqual(self.check(kill_event(team_verdict=False, score_change=-1, in_volley=True)), [False])


class KillDecoderTest(unittest.TestCase):
    def records(self):
        """Player 1 (agent 0) shoots player 2 (agent 1) at 100 s; the victim is flagged dying and respawns as agent 2 at 130 s."""
        return [
            support.packet_record(40.0, messages=[support.spawn_message(0, 1, team=1), support.spawn_message(1, 2, team=2)]),
            support.packet_record(100.0, messages=[support.death_message(1, 0, weapon_class=5)], agents=[(1, 13, 1)], players=[(1, 0, 1)]),
            support.packet_record(130.0, messages=[support.spawn_message(2, 2, team=2)]),
        ]

    def decode(self, records=None, local_slot=None):
        return KillDecoder(namer).decode(records if records is not None else self.records(), local_slot)

    def test_a_kill_is_found_with_names_weapon_and_respawn_delay(self):
        events, local_slot = self.decode()
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual((event.killer, event.victim, event.weapon, event.teamkill, event.respawn_delay_s), ('P1', 'P2', 'firearm: musket/rifle', '', 30.0))
        self.assertEqual(event.team_verdict, False)

    def test_a_death_message_without_the_dying_flag_is_not_a_kill(self):
        records = self.records()
        records[1]['tail']['agents'] = []
        self.assertEqual(self.decode(records)[0], [])

    def test_the_second_death_of_one_agent_within_seconds_is_dropped(self):
        records = self.records() + [support.packet_record(103.0, messages=[support.death_message(1, 0, weapon_class=5)], agents=[(1, 13, 1)])]
        self.assertEqual(len(self.decode(records)[0]), 1)

    def test_the_given_local_slot_is_returned(self):
        self.assertEqual(self.decode(local_slot=7)[1], 7)


if __name__ == '__main__':
    unittest.main()
