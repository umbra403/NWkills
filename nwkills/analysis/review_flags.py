"""The notes in the review column of the kills file: what a person should look at twice."""
from typing import List

from ..events.kill_event import KillEvent
from ..rounds import RoundTimeline


class KillReviewFlagger:
    SYNC_TIME_S = 90                # before this the server may not have told the client who owns what

    def __init__(self, timeline: RoundTimeline):
        self._timeline = timeline

    def flags_for(self, event: KillEvent) -> List[str]:
        flags: List[str] = []
        for role, name in (('killer', event.killer), ('victim', event.victim)):
            if name == '?' and event.time_s < self.SYNC_TIME_S:
                flags.append('before-sync')
            elif not isinstance(name, str) or name.startswith(('?', 'player#')):
                flags.append(role + '?')
        if event.score_contradicts_team and not self._score_baseline_is_from_an_earlier_round(event):
            flags.append('teamkill?(score disagrees)')              # the teams say one thing, the killer's score change the other
        if event.runaway_horse:
            flags.append('runaway-horse')                            # the horse had no rider (link message), no kill credit
        if event.burst_guess:
            flags.append('teamkill?(burst)')                         # several kills at once: the number of teamkills is exact, which of them is a guess
        if event.late_sources:
            flags.append('name-from-later-data(%s)' % '+'.join(event.late_sources))
        if event.weapon.startswith('class ') or '(ico_' in event.weapon:
            flags.append('weapon?')                                  # not yet seen on video (label from the exe's icon table only)
        if event.killer == event.victim and event.killer not in ('?', '(AI)', '(world)') and not event.admin_label:
            flags.append('self')
        return flags

    def _score_baseline_is_from_an_earlier_round(self, event: KillEvent) -> bool:
        """A score read against a baseline from an earlier round proves nothing: the scoreboard starts the round at 0, and that reset is not sent."""
        round_ = self._timeline.round_at(event.time_s)
        return event.score_baseline_s is not None and round_ is not None and event.score_baseline_s < round_.start_s
