"""Kills of one player a fraction of a second apart, and the check of the team verdict against the scoreboard."""
import collections
from typing import List

from .kill_builder import SCORE_WINDOW_AFTER_S, SCORE_WINDOW_BEFORE_S
from .kill_event import KillEvent
from .score_timeline import ScoreTimeline


class ScoreStepAssigner:
    """Events of one player a fraction of a second apart (a kill and then a fall or drowning) each have their own score step, but the window used
    for a single kill reads the first step for both. When the number of steps equals the number of events, this hands them out in order.
    Volleys (several events with the same timestamp) are handled by VolleyTeamkillEstimator and left alone here."""

    SAME_PLAYER_GAP_S = 3.0

    def __init__(self, scores: ScoreTimeline):
        self._scores = scores

    def apply(self, events: List[KillEvent]) -> None:
        events_by_killer = collections.defaultdict(list)
        for event in events:
            if event.killer_slot is not None and event.killer_slot >= 0 and not event.in_volley:
                events_by_killer[event.killer_slot].append(event)
        for killer_slot, killer_events in events_by_killer.items():
            killer_events.sort(key=lambda event: event.time_s)
            start = 0
            while start < len(killer_events):
                end = start
                while end + 1 < len(killer_events) and killer_events[end + 1].time_s - killer_events[end].time_s < self.SAME_PLAYER_GAP_S:
                    end += 1
                if end > start:
                    self._assign_steps(killer_slot, killer_events[start:end + 1])
                start = end + 1

    def _assign_steps(self, killer_slot: int, group: List[KillEvent]) -> None:
        scores_before = self._scores.scores_before(killer_slot, group[0].time_s - SCORE_WINDOW_BEFORE_S)
        scores_during = [score for _sent_s, score in
                         self._scores.timed_scores_between(killer_slot, group[0].time_s - SCORE_WINDOW_BEFORE_S, group[-1].time_s + SCORE_WINDOW_AFTER_S)]
        if not (scores_before and scores_during):
            return
        values = [scores_before[-1]] + scores_during
        steps = [after - before for before, after in zip(values, values[1:]) if after != before]
        strictly_ordered = all(later.time_s > earlier.time_s for earlier, later in zip(group, group[1:]))
        if len(steps) == len(group) and all(abs(step) == 1 for step in steps) and strictly_ordered:
            for event, step in zip(group, steps):
                event.score_change = step
                if event.team_verdict is None:
                    event.teamkill = 'yes' if step < 0 else ''


class TeamkillCrossChecker:
    """Marks a team verdict that the killer's own score change contradicts. Single kills only: a volley shares one change, and a second kill by
    the same player within a few seconds shares the score change too, so the check says nothing then."""

    CROWDED_WINDOW_S = 3.0

    def apply(self, events: List[KillEvent]) -> None:
        kill_times = collections.defaultdict(list)
        for event in events:
            if event.killer_slot is not None and event.killer_slot >= 0:
                kill_times[event.killer_slot].append(event.time_s)
        for event in events:
            crowded = (event.killer_slot is not None
                       and sum(1 for other_s in kill_times.get(event.killer_slot, ()) if abs(other_s - event.time_s) < self.CROWDED_WINDOW_S) > 1)
            event.score_contradicts_team = (event.team_verdict is not None and not event.in_volley and not crowded and event.score_change is not None
                                            and (event.score_change < 0) != event.team_verdict)
