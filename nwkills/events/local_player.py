"""Finding out which player slot is the person who made the capture."""
import collections
from typing import List, Optional

from .evidence import AgentTime, OwnerSighting, RawDeath
from .ownership import AgentOwnership


class LocalPlayerTracker:
    """The local player gets a message of type 18 with the agent they respawn as. A death of a player-owned agent that is followed within 10 s by
    such a message, for an agent nobody else owns, is a death of the local player."""

    RESPAWN_WINDOW_S = 10.0
    OWNER_MATCH_TOLERANCE_S = 4.0
    CAPTURE_START_S = 1e-4

    def __init__(self, ownership: AgentOwnership, local_respawns: List[AgentTime]):
        self._ownership = ownership
        self._local_respawns = local_respawns

    def detect_slot(self, deaths: List[RawDeath]) -> Optional[int]:
        votes = collections.Counter()
        for death in deaths:
            owners_before = [sighting for sighting in self._ownership.sightings_of(death.victim_agent) if sighting.time_s < death.time_s - 0.3]
            if owners_before and self._respawn_follows_unowned(death) and owners_before[-1].slot >= 0:
                votes[owners_before[-1].slot] += 1
        return votes.most_common(1)[0][0] if votes else None

    def _respawn_follows_unowned(self, death: RawDeath) -> bool:
        return any(death.time_s < respawn.time_s < death.time_s + self.RESPAWN_WINDOW_S
                   and not self._ownership.has_sighting_near(respawn.agent, respawn.time_s, self.OWNER_MATCH_TOLERANCE_S)
                   for respawn in self._local_respawns)

    def add_respawn_ownership(self, deaths: List[RawDeath], local_slot: Optional[int]) -> None:
        """Every time the local player's agent dies, their next respawn agent is theirs. (Needs the agent they had at the start of the capture.)"""
        starting_agents = [sighting.agent for sighting in self._ownership.sightings
                           if sighting.time_s < self.CAPTURE_START_S and sighting.slot == local_slot]
        current_agent = starting_agents[0] if starting_agents else None
        new_sightings = []
        for death in deaths:
            if current_agent is not None and death.victim_agent == current_agent:
                respawns = [respawn for respawn in self._local_respawns if death.time_s < respawn.time_s < death.time_s + self.RESPAWN_WINDOW_S]
                if respawns:
                    new_sightings.append(OwnerSighting(respawns[0].time_s, respawns[0].agent, local_slot))
                    current_agent = respawns[0].agent
        self._ownership.add_sightings(new_sightings)
