"""Which player slot owned which agent, over time."""
import collections
from typing import Dict, Iterable, List, Optional

from .evidence import OwnerSighting


class AgentOwnership:
    """The owner sightings, sorted by time. Agent ids are reused by the game, so an owner is always asked for at a moment."""

    SIGHTING_DELAY_S = 0.3              # a sighting counts for events from this long after it
    LATE_WINDOW_S = 120.0
    SPAWN_MATCH_TOLERANCE_S = 0.5

    def __init__(self, sightings: Iterable[OwnerSighting]):
        self._set_sightings(sightings)

    def _set_sightings(self, sightings: Iterable[OwnerSighting]) -> None:
        self._sightings: List[OwnerSighting] = sorted(set(sightings))
        self._by_agent: Dict[int, List[OwnerSighting]] = collections.defaultdict(list)
        for sighting in self._sightings:
            self._by_agent[sighting.agent].append(sighting)

    @property
    def sightings(self) -> List[OwnerSighting]:
        return self._sightings

    def sightings_of(self, agent: int) -> List[OwnerSighting]:
        return self._by_agent.get(agent, [])

    def add_sightings(self, sightings: Iterable[OwnerSighting]) -> None:
        self._set_sightings(self._sightings + list(sightings))

    def owner_at(self, agent: int, time_s: float) -> Optional[int]:
        """The slot of the latest sighting of the agent from before the moment, or None when there is none."""
        earlier = [sighting for sighting in self.sightings_of(agent) if sighting.time_s < time_s - self.SIGHTING_DELAY_S]
        return earlier[-1].slot if earlier else None

    def owner_learned_later(self, agent: int, time_s: float, death_times: List[float], spawn_times: List[float]) -> Optional[int]:
        """The owner of an agent learned from data that arrives AFTER the event (agents already present when the capture started are only listed
        later). Used only when nothing earlier is known. Sightings are ignored if they come with a spawn message of that agent id (the id was
        re-created, so it is another agent) or after the agent's next death; accepted only if all remaining sightings within the window agree
        on one player."""
        next_death_s = min([death_s for death_s in death_times if death_s > time_s + self.SIGHTING_DELAY_S], default=1e18)
        candidates = [sighting for sighting in self.sightings_of(agent)
                      if time_s - self.SIGHTING_DELAY_S <= sighting.time_s <= time_s + self.LATE_WINDOW_S and sighting.time_s < next_death_s
                      and not any(abs(sighting.time_s - spawn_s) < self.SPAWN_MATCH_TOLERANCE_S for spawn_s in spawn_times)]
        slots = {sighting.slot for sighting in candidates}
        return slots.pop() if len(slots) == 1 else None

    def has_sighting_near(self, agent: int, time_s: float, tolerance_s: float) -> bool:
        return any(abs(sighting.time_s - time_s) < tolerance_s for sighting in self.sightings_of(agent))


class RespawnIndex:
    """When a player's agent next appears. Only owner sightings that come with a spawn message count: owner records from property lists also
    describe agents that were already there."""

    LATER_THAN_DEATH_S = 0.5
    LONGEST_RESPAWN_S = 120.0

    def __init__(self, ownership: AgentOwnership, spawn_messages):
        spawn_keys = {(round(spawn.time_s, 2), spawn.agent) for spawn in spawn_messages}
        self._spawn_sightings_by_slot = collections.defaultdict(list)
        for sighting in ownership.sightings:
            if (round(sighting.time_s, 2), sighting.agent) in spawn_keys:
                self._spawn_sightings_by_slot[sighting.slot].append(sighting)

    def delay_after_death(self, slot: int, dead_agent: int, death_s: float) -> Optional[float]:
        """Seconds until the slot owns another agent after `death_s`, or None when that takes more than two minutes or is not in the capture."""
        delays = [sighting.time_s - death_s for sighting in self._spawn_sightings_by_slot.get(slot, [])
                  if sighting.time_s > death_s + self.LATER_THAN_DEATH_S and sighting.agent != dead_agent]
        if delays and min(delays) <= self.LONGEST_RESPAWN_S:
            return round(min(delays), 1)
        return None
