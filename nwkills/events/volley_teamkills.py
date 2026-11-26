"""Teamkills in a volley: several kills by one player within a few seconds."""
import collections
from typing import List

from .kill_builder import TEAM_KILL_MODE, SCORE_WINDOW_AFTER_S, SCORE_WINDOW_BEFORE_S
from .kill_event import KillEvent
from .score_timeline import ScoreTimeline


class VolleyTeamkillEstimator:
    """Artillery and canister kills of one player within a few seconds share one scoreboard change, so the per-kill test gives them all the same
    verdict. This uses the whole change instead: n kills with a net change D contain (n - D) / 2 teamkills. Which of them are teamkills is a
    guess (victims with the killer's regiment prefix first) and is flagged as a burst guess."""

    VOLLEY_GAP_S = 2.5

    def __init__(self, scores: ScoreTimeline):
        self._scores = scores

    def apply(self, events: List[KillEvent]) -> None:
        events_by_killer = collections.defaultdict(list)
        for event in events:
            if event.mode == TEAM_KILL_MODE and event.killer_slot is not None and event.killer_slot >= 0 and event.killer_slot != event.victim_slot:
                events_by_killer[event.killer_slot].append(event)
        for killer_slot, killer_events in events_by_killer.items():
            killer_events.sort(key=lambda event: event.time_s)
            for volley in self._split_into_volleys(killer_events):
                self._resolve_volley(killer_slot, volley)

    def _split_into_volleys(self, sorted_events: List[KillEvent]) -> List[List[KillEvent]]:
        volleys, start = [], 0
        while start < len(sorted_events):
            end = start
            while end + 1 < len(sorted_events) and sorted_events[end + 1].time_s - sorted_events[end].time_s <= self.VOLLEY_GAP_S:
                end += 1
            if end > start:
                volleys.append(sorted_events[start:end + 1])
            start = end + 1
        return volleys

    def _resolve_volley(self, killer_slot: int, volley: List[KillEvent]) -> None:
        for event in volley:
            event.in_volley = True
        if all(event.team_verdict is not None for event in volley):
            return                          # every verdict in the volley comes from the teams: nothing to guess
        first_s, last_s = volley[0].time_s, volley[-1].time_s
        kill_count = len(volley)
        scores_after = self._scores.scores_between(killer_slot, first_s - SCORE_WINDOW_BEFORE_S, last_s + SCORE_WINDOW_AFTER_S)
        scores_before = self._scores.scores_before(killer_slot, first_s - SCORE_WINDOW_BEFORE_S)
        if not scores_after:
            if not scores_before or kill_count % 2:
                return
            scores_after = [scores_before[-1]]        # the server only sends a score when it changes: no update after n kills means a net change of 0
        baseline = scores_before[-1] if scores_before else (0 if -3 <= scores_after[0] <= 3 else None)
        if baseline is None:
            return
        if abs(scores_after[0] - baseline) > kill_count and abs(scores_after[0]) <= kill_count:
            baseline = 0                    # reset to 0 that we did not see (the last score before is last round's value)
        net_change = self._net_change(scores_after, baseline, kill_count) - baseline
        if (kill_count - net_change) % 2 or not 0 <= (kill_count - net_change) // 2 <= kill_count:
            return
        teamkill_count = (kill_count - net_change) // 2
        unknown = [index for index in range(kill_count) if volley[index].team_verdict is None]      # kills whose teams are known keep their verdict
        remaining = teamkill_count - sum(1 for event in volley if event.team_verdict)
        if not unknown or not 0 <= remaining <= len(unknown):
            return
        likely_teamkills = sorted(unknown, key=lambda index: (0 if self._prefix(volley[index].victim) == self._prefix(volley[index].killer) else 1, index))
        flagged = set(likely_teamkills[:remaining])
        for index in unknown:
            volley[index].teamkill = 'yes' if index in flagged else ''
            volley[index].burst_guess = 0 < remaining < len(unknown)

    @staticmethod
    def _net_change(scores_after: List[int], baseline: int, kill_count: int) -> int:
        """Follows the changes while they can come from these kills; stops at a later reset to 0 (the first change after the kills is theirs:
        3 -> 1 after two kills is two teamkills)."""
        current = baseline
        for step, score in enumerate(scores_after):
            if step and abs(score - current) >= 2 and abs(current) >= 2 and -1 <= score <= 1:
                break
            if abs(score - baseline) > kill_count:
                break
            current = score
        return current

    @staticmethod
    def _prefix(name) -> str:
        """The regiment tag in front of the first underscore."""
        return str(name).split('_')[0].lower() if isinstance(name, str) else ''
