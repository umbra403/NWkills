import unittest
import support
from nwkills.analysis.death_classifier import DeathClassifier
from nwkills.analysis.kill_labels import AdminDeathLabeler, OWNER_UNKNOWN, OwnerlessMountLabeler, WorldKillerLabeler
from nwkills.analysis.player_tally import PlayerTally
from nwkills.analysis.review_flags import KillReviewFlagger
from nwkills.analysis.scoreboard import ScoreChangeLedger, ScoreGapAnalyzer, ScoreboardHistory
from nwkills.events.admin_actions import AdminAction
from nwkills.roster import NameSighting, PlayerRoster
from nwkills.rounds import Round, RoundTimeline
from test_events_kills import kill_event

TIMELINE = RoundTimeline([Round(1, 0.0, 100.0, 0, 'capture start', 'x', kind='pre-live'), Round(2, 100.0, 300.0, 0, 'reset message', 'x', kind='live')])


class DeathClassifierTest(unittest.TestCase):
    def classify(self, **changes):
        return DeathClassifier().classify(kill_event(**changes))

    def test_a_blow_between_two_players_is_a_kill(self):
        self.assertEqual(self.classify(), 'kill')

    def test_the_death_of_an_agent_without_player_is_an_ai_death(self):
        self.assertEqual(self.classify(victim_slot=-1), DeathClassifier.AI_OR_HORSE_DEATH)

    def test_a_killer_less_death_is_the_world(self):
        self.assertEqual(self.classify(killer_agent=-1), DeathClassifier.WORLD_DEATH)

    def test_self_inflicted_deaths_by_weapon(self):
        self.assertEqual(self.classify(killer_slot=2, weapon='headshot'), 'self-inflicted: fall')
        self.assertEqual(self.classify(killer_slot=2, weapon='fists (punch)'), 'self-inflicted: suicide (no admin line)')
        self.assertEqual(self.classify(killer_slot=2, weapon='drowning'), 'self-inflicted: drowning')
        self.assertEqual(self.classify(killer_slot=2, weapon='x'), 'self-inflicted (other)')

    def test_a_player_owned_mount_is_a_horse_death(self):
        self.assertEqual(self.classify(horse=True), DeathClassifier.HORSE_DEATH)

    def test_a_death_without_a_blow(self):
        self.assertEqual(self.classify(mode=1), DeathClassifier.NO_BLOW_KNOWN_KILLER)
        self.assertEqual(self.classify(mode=1, killer_slot=None), DeathClassifier.NO_BLOW_UNKNOWN_KILLER)

    def test_helpers(self):
        self.assertTrue(DeathClassifier.is_self_inflicted('self-inflicted: fall'))
        self.assertFalse(DeathClassifier.is_self_inflicted('kill'))
        self.assertTrue(DeathClassifier.is_uncounted_mount_death(DeathClassifier.HORSE_DEATH))
        self.assertTrue(DeathClassifier.is_uncounted_mount_death(DeathClassifier.NO_BLOW_KNOWN_KILLER))
        self.assertFalse(DeathClassifier.is_uncounted_mount_death('kill'))


class KillLabelsTest(unittest.TestCase):
    def test_world_deaths_name_the_world_as_killer(self):
        events = [kill_event(killer_agent=-1), kill_event()]
        WorldKillerLabeler().apply(events)
        self.assertEqual([event.killer for event in events], ['(world)', 'P1'])

    def label(self, event, action):
        AdminDeathLabeler().apply([event], [action])
        return event.admin_label

    def test_a_self_death_of_the_slain_player_is_an_admin_slay(self):
        event = kill_event(10.0, killer_agent=5, victim_agent=5, victim='Bob')
        self.assertEqual(self.label(event, AdminAction(10.5, 'slay', 'Boss', 'Bob')), 'admin slay')

    def test_a_slay_of_another_player_does_not_match(self):
        event = kill_event(10.0, killer_agent=5, victim_agent=5, victim='Bob')
        self.assertIsNone(self.label(event, AdminAction(10.5, 'slay', 'Boss', 'Alice')))

    def test_slay_all_labels_self_and_world_deaths(self):
        self.assertEqual(self.label(kill_event(10.0, killer_agent=5, victim_agent=5), AdminAction(10.0, 'slay_all', 'Boss', None)), 'admin: slayed everyone')
        self.assertEqual(self.label(kill_event(10.0, killer_agent=-1), AdminAction(10.0, 'slay_all', 'Boss', None)), 'admin: slayed everyone')

    def test_swap_all_labels_world_deaths_only(self):
        self.assertEqual(self.label(kill_event(10.0, killer_agent=-1), AdminAction(10.0, 'swap_all', 'Boss', None)), 'admin: swapped everyone to spectators')
        self.assertIsNone(self.label(kill_event(10.0, killer_agent=5, victim_agent=5), AdminAction(10.0, 'swap_all', 'Boss', None)))

    def test_deaths_outside_the_window_are_not_labelled(self):
        self.assertIsNone(self.label(kill_event(20.0, killer_agent=5, victim_agent=5), AdminAction(10.0, 'slay_all', 'Boss', None)))

    def test_an_old_label_is_cleared(self):
        event = kill_event(20.0)
        event.admin_label = 'stale'
        self.assertIsNone(self.label(event, AdminAction(10.0, 'slay_all', 'Boss', None)))

    def test_ownerless_victims_of_no_blow_deaths_are_labelled(self):
        event = kill_event(mode=1, victim='?', victim_slot=None)
        OwnerlessMountLabeler(DeathClassifier()).apply([event])
        self.assertEqual(event.victim, OWNER_UNKNOWN)

    def test_a_charging_horse_without_owner_is_labelled(self):
        event = kill_event(killer='?', killer_slot=None, weapon='cavalry: horse charge (rider hit)')
        OwnerlessMountLabeler(DeathClassifier()).apply([event])
        self.assertEqual(event.killer, OWNER_UNKNOWN)

    def test_other_unknown_names_stay(self):
        event = kill_event(killer='?', killer_slot=None, victim='?', victim_slot=None)
        OwnerlessMountLabeler(DeathClassifier()).apply([event])
        self.assertEqual((event.killer, event.victim), ('?', '?'))


class KillReviewFlaggerTest(unittest.TestCase):
    def flags(self, **changes):
        return KillReviewFlagger(TIMELINE).flags_for(kill_event(**changes))

    def test_a_clean_kill_has_no_flags(self):
        self.assertEqual(self.flags(), [])

    def test_unknown_names(self):
        self.assertEqual(self.flags(time_s=50.0, killer='?'), ['before-sync'])
        self.assertEqual(self.flags(time_s=150.0, killer='?', victim='player#3'), ['killer?', 'victim?'])

    def test_weapon_flags(self):
        self.assertEqual(self.flags(weapon='class 31'), ['weapon?'])
        self.assertEqual(self.flags(weapon='thrown axe (ico_axethrow)'), ['weapon?'])

    def test_notes_from_the_decoder(self):
        self.assertEqual(self.flags(runaway_horse=True, burst_guess=True, late_sources=['killer']), ['runaway-horse', 'teamkill?(burst)', 'name-from-later-data(killer)'])

    def test_a_self_death_is_flagged_unless_an_admin_did_it(self):
        self.assertEqual(self.flags(killer='Bob', victim='Bob'), ['self'])
        self.assertEqual(self.flags(killer='Bob', victim='Bob', admin_label='admin slay'), [])

    def test_score_disagreement_is_flagged(self):
        self.assertEqual(self.flags(time_s=150.0, score_contradicts_team=True, score_baseline_s=120.0), ['teamkill?(score disagrees)'])

    def test_a_baseline_from_an_earlier_round_proves_nothing(self):
        self.assertEqual(self.flags(time_s=150.0, score_contradicts_team=True, score_baseline_s=50.0), [])


class PlayerTallyTest(unittest.TestCase):
    def tally(self, events):
        tally = PlayerTally()
        tally.add_events(events, TIMELINE)
        return tally

    def test_kills_and_deaths_are_counted_per_round(self):
        tally = self.tally([kill_event(10.0), kill_event(20.0), kill_event(150.0)])
        self.assertEqual((tally.count('P1', 'kills', 1), tally.count('P1', 'kills', 2), tally.count('P2', 'deaths', 1)), (2, 1, 2))
        self.assertEqual((tally.total('P1', 'kills', [1, 2]), tally.total('P1', 'kills', [2])), (3, 1))

    def test_a_teamkill_is_not_a_kill(self):
        tally = self.tally([kill_event(10.0, teamkill='yes')])
        self.assertEqual((tally.total('P1', 'kills', [1]), tally.total('P1', 'teamkills', [1]), tally.total('P2', 'deaths', [1])), (0, 1, 1))

    def test_admin_deaths_and_mounts_are_not_counted(self):
        tally = self.tally([kill_event(10.0, admin_label='admin slay'), kill_event(11.0, horse=True), kill_event(12.0, mode=1)])
        self.assertEqual(tally.names(), [])

    def test_a_runaway_horse_kill_is_not_a_kill(self):
        tally = self.tally([kill_event(10.0, runaway_horse=True, killer='(runaway horse)')])
        self.assertNotIn('(runaway horse)', tally.names())

    def test_kills_of_ai_victims_are_ai_kills(self):
        tally = self.tally([kill_event(10.0, victim_slot=-1, victim='(AI)')])
        self.assertEqual(tally.total('P1', 'ai_kills', [1]), 1)
        self.assertEqual(tally.names(), ['P1'])

    def test_unnamed_killers_get_no_ai_kills(self):
        self.assertEqual(self.tally([kill_event(10.0, victim_slot=-1, killer='?')]).names(), [])

    def test_score_is_kills_minus_teamkills(self):
        tally = self.tally([kill_event(10.0), kill_event(20.0), kill_event(30.0, teamkill='yes')])
        self.assertEqual(tally.score('P1', [1]), 1)

    def test_ensure_player_gives_a_row_of_zeros(self):
        tally = PlayerTally()
        tally.ensure_player('Nobody')
        self.assertEqual((tally.names(), tally.total('Nobody', 'kills', [1])), (['Nobody'], 0))


def score_record(time_s, *scores):
    return support.packet_record(time_s, players=[(slot, 0, score if score >= 0 else score + 8192) for slot, score in scores])


class ScoreboardHistoryTest(unittest.TestCase):
    def test_changes_are_listed_per_slot_and_repeats_dropped(self):
        history = ScoreboardHistory.from_records([score_record(1.0, (1, 0)), score_record(2.0, (1, 0)), score_record(3.0, (1, 2), (2, -1))])
        self.assertEqual(history.series(1), [(1.0, 0), (3.0, 2)])
        self.assertEqual(history.series(2), [(3.0, -1)])
        self.assertEqual(history.series(9), [])

    def test_unreliable_packets_are_left_out(self):
        record = score_record(1.0, (1, 4))
        record['err'] = 'tail'
        far = score_record(2.0, (1, 4))
        far['L'] = 500
        self.assertEqual(ScoreboardHistory.from_records([record, far, support.packet_record(3.0, has_state_block=False)]).series(1), [])

    def test_huge_scores_are_ignored(self):
        self.assertEqual(ScoreboardHistory.from_records([score_record(1.0, (1, 200))]).series(1), [])

    def test_items_lists_the_series(self):
        self.assertEqual(list(dict(ScoreboardHistory.from_records([score_record(1.0, (1, 1))]).items())), [1])


class ScoreChangeLedgerTest(unittest.TestCase):
    def ledger(self, events, records=()):
        return ScoreChangeLedger(events, ScoreboardHistory.from_records(records))

    def test_kills_and_teamkills_are_plus_and_minus_one(self):
        ledger = self.ledger([kill_event(10.0), kill_event(20.0, teamkill='yes')])
        self.assertEqual(ledger.changes(1), [(10.0, 1), (20.0, -1)])

    def test_admin_deaths_and_other_kinds_are_not_changes(self):
        ledger = self.ledger([kill_event(10.0, admin_label='admin slay'), kill_event(11.0, horse=True), kill_event(12.0, killer_slot=None)])
        self.assertEqual(ledger.changes(1), [])

    def test_a_teamkilling_self_death_counts(self):
        self.assertEqual(self.ledger([kill_event(10.0, killer_slot=2, teamkill='yes')]).changes(2), [(10.0, -1)])

    def test_a_team_swap_costs_a_point_when_the_player_respawns(self):
        ledger = self.ledger([kill_event(10.0, killer_agent=-1, killer='(world)', killer_slot=None, respawn_delay_s=5.0)])
        self.assertEqual(ledger.changes(2), [(10.0, -1)])

    def test_a_swap_without_respawn_counts_when_the_scoreboard_dropped(self):
        records = [score_record(5.0, (2, 4)), score_record(11.0, (2, 3))]
        ledger = self.ledger([kill_event(10.0, killer_agent=-1, killer_slot=None)], records)
        self.assertEqual(ledger.changes(2), [(10.0, -1)])

    def test_leaving_the_server_costs_nothing(self):
        self.assertEqual(self.ledger([kill_event(10.0, killer_agent=-1, killer_slot=None)]).changes(2), [])


class ScoreGapAnalyzerTest(unittest.TestCase):
    ROSTER = PlayerRoster({1: [NameSighting(0.0, 500.0, 'Alice', 9)]})

    def analyze(self, events, records, rounds=None, resets=()):
        scoreboard = ScoreboardHistory.from_records(records)
        ledger = ScoreChangeLedger(events, scoreboard)
        return ScoreGapAnalyzer(self.ROSTER).analyze(scoreboard, ledger, rounds or TIMELINE.rounds, list(resets))

    def test_a_round_that_adds_up_has_no_gap(self):
        records = [score_record(1.0, (1, 0)), score_record(12.0, (1, 1)), score_record(22.0, (1, 2))]
        report = self.analyze([kill_event(11.0), kill_event(21.0)], records)
        self.assertEqual(report.gap_by_player_round[('Alice', 1)], 0)
        self.assertTrue(report.has_gap('Alice', 1))
        self.assertEqual((report.first_score_by_player['Alice'], report.last_score_by_player['Alice']), (0, 2))

    def test_a_missing_kill_shows_as_a_gap(self):
        records = [score_record(1.0, (1, 0)), score_record(12.0, (1, 1)), score_record(22.0, (1, 2))]
        report = self.analyze([kill_event(11.0)], records)
        self.assertEqual(report.gap_by_player_round[('Alice', 1)], 1)

    def test_players_without_a_name_are_skipped(self):
        records = [score_record(1.0, (5, 0)), score_record(12.0, (5, 1))]
        report = self.analyze([], records)
        self.assertEqual(report.player_names(), set())

    def test_the_second_round_counts_from_the_score_at_its_start(self):
        records = [score_record(1.0, (1, 0)), score_record(50.0, (1, 4)), score_record(105.0, (1, 4)), score_record(150.0, (1, 5))]
        report = self.analyze([kill_event(149.0)], records)
        self.assertEqual(report.gap_by_player_round[('Alice', 2)], 0)

    def test_a_scoreboard_reset_a_little_after_the_start_is_followed(self):
        records = [score_record(1.0, (1, 0)), score_record(50.0, (1, 9)), score_record(130.0, (1, 0)), score_record(150.0, (1, 1))]
        report = self.analyze([kill_event(149.0)], records)
        self.assertEqual(report.gap_by_player_round[('Alice', 2)], 0)

    def test_a_jump_no_kills_explain_is_skipped(self):
        records = [score_record(1.0, (1, 0)), score_record(12.0, (1, 40))]
        self.assertFalse(self.analyze([], records).has_gap('Alice', 1))

    def test_a_slot_that_changes_hands_inside_the_round_is_skipped(self):
        roster = PlayerRoster({1: [NameSighting(0.0, 40.0, 'Alice', 9), NameSighting(50.0, 90.0, 'Bob', 9)]})
        scoreboard = ScoreboardHistory.from_records([score_record(1.0, (1, 0)), score_record(60.0, (1, 1))])
        report = ScoreGapAnalyzer(roster).analyze(scoreboard, ScoreChangeLedger([], scoreboard), TIMELINE.rounds[:1], [])
        self.assertFalse(report.has_gap('Alice', 1))

    def test_a_round_without_a_score_before_its_start_is_skipped(self):
        report = self.analyze([], [score_record(150.0, (1, 1))])
        self.assertFalse(report.has_gap('Alice', 2))


if __name__ == '__main__':
    unittest.main()
