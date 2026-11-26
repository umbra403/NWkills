"""All the kills of a capture: the death messages, combined with the owners of the agents, the teams and the scoreboard."""
import collections
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .admin_actions import AdminActionFinder
from .charge_kills import ChargeKillClaimer
from .evidence import EvidenceCollector, RawDeath
from .kill_builder import KillEventBuilder
from .kill_event import KillEvent
from .local_player import LocalPlayerTracker
from .mass_deaths import MapChangeDeathFilter
from .ownership import AgentOwnership
from .riders import HorseRiderSubstituter, RiderLinkHistory
from .score_steps import ScoreStepAssigner, TeamkillCrossChecker
from .score_timeline import ScoreTimeline
from .score_updates import ScoreUpdateFilter
from .teams import TeamHistory
from .volley_teamkills import VolleyTeamkillEstimator

Namer = Callable[[Optional[int], float], object]


class KillDecoder:
    """Reads the packet records (the dictionaries of PacketDecoder.to_legacy_record) and returns the kill events."""

    DYING_FLAG_WINDOW_S = 3.0           # a death message counts when the victim was flagged dying this close to it
    SAME_VICTIM_WINDOW_S = 6.0          # an agent cannot die twice within a few seconds

    def __init__(self, namer: Namer, item_names: Optional[List[str]] = None, score_filter: Optional[ScoreUpdateFilter] = None):
        self._namer = namer
        self._item_names = item_names
        self._score_filter = score_filter or ScoreUpdateFilter()

    def decode(self, packet_records: List[dict], local_slot: Optional[int] = None) -> Tuple[List[KillEvent], Optional[int]]:
        """-> (the kill events in time order, the slot of the local player: the one given, or the one found)."""
        admin_block_times = [action.time_s for action in AdminActionFinder().find(packet_records) if action.kind in ('slay_all', 'swap_all')]      # blocks announced by the server as an admin action are kept (and labelled in the kills file)
        mass_death_times = MapChangeDeathFilter().find_block_times(packet_records, admin_block_times)
        evidence = EvidenceCollector().collect(packet_records, mass_death_times)
        scores = ScoreTimeline(self._score_filter.keep_reliable(evidence.raw_score_updates))
        deaths = self._remove_repeated_deaths(self._keep_flagged_deaths(evidence))
        ownership = AgentOwnership(evidence.owner_sightings)
        tracker = LocalPlayerTracker(ownership, evidence.local_respawns)
        if local_slot is None:
            local_slot = tracker.detect_slot(deaths)
        tracker.add_respawn_ownership(deaths, local_slot)
        spawn_times = self._times_by_agent((spawn.agent, spawn.time_s) for spawn in evidence.spawn_messages)
        death_times = self._times_by_agent((death.victim_agent, death.time_s) for death in deaths)
        HorseRiderSubstituter(RiderLinkHistory(packet_records), spawn_times, death_times).substitute(deaths)
        builder = KillEventBuilder(ownership, scores, TeamHistory(evidence.team_spawns), evidence, spawn_times, death_times, self._namer, self._item_names)
        events = builder.build(deaths)
        VolleyTeamkillEstimator(scores).apply(events)
        ChargeKillClaimer(scores, self._namer).apply(events)
        ScoreStepAssigner(scores).apply(events)
        TeamkillCrossChecker().apply(events)
        return events, local_slot

    def _keep_flagged_deaths(self, evidence) -> List[RawDeath]:
        """A real death comes with the victim's agent flagged as dying (property 13) a moment around the message."""
        return [death for death in evidence.deaths
                if any(abs(flagged_s - death.time_s) < self.DYING_FLAG_WINDOW_S for flagged_s in evidence.dying_times.get(death.victim_agent, []))]

    def _remove_repeated_deaths(self, deaths: Iterable[RawDeath]) -> List[RawDeath]:
        """An agent cannot die twice within a few seconds: drop repeats of the same death message (no bucket edges)."""
        last_death_s: Dict[int, float] = {}
        kept = []
        for death in deaths:
            if death.victim_agent in last_death_s and death.time_s - last_death_s[death.victim_agent] < self.SAME_VICTIM_WINDOW_S:
                continue
            last_death_s[death.victim_agent] = death.time_s
            kept.append(death)
        return kept

    @staticmethod
    def _times_by_agent(agent_times) -> Dict[int, List[float]]:
        times = collections.defaultdict(list)
        for agent, time_s in agent_times:
            times[agent].append(time_s)
        return times
