"""Who rides a horse: the client credits a horse's kill to its rider."""
import collections
from typing import DefaultDict, Dict, Iterable, List, Tuple

from .evidence import RawDeath
from .weapon_names import HORSE_CHARGE_CLASS

AGENT_SPAWN_MESSAGE_TYPE = 5
MINIMUM_SPAWN_VALUES = 22
FIRST_RELIABLE_SPAWN_ORDER_S = 30.0


class RiderLinkHistory:
    """horse agent -> [(time, rider agent or -1)], sorted by time. Sources: message type 30 (the server keeps the rider field of a horse current
    with it) and the order of spawn messages: a rider is spawned together with its horse, so the rider's spawn message (it has an owner) is
    followed directly by the horse's (no owner, team 0)."""

    def __init__(self, packet_records: Iterable[dict]):
        self._links: DefaultDict[int, List[Tuple[float, int]]] = collections.defaultdict(list)
        for record in packet_records:
            for horse, rider in record.get('links') or ():
                self._links[horse].append((record['t'], rider))
            spawns = [values for message_type, values, _widths in record['msgs']
                      if message_type == AGENT_SPAWN_MESSAGE_TYPE and len(values) >= MINIMUM_SPAWN_VALUES and values[1] > 0]
            for rider_spawn, horse_spawn in zip(spawns, spawns[1:]):
                owner_of_rider, owner_of_horse, team_of_horse = rider_spawn[2], horse_spawn[2], horse_spawn[4]
                if owner_of_rider > 0 and owner_of_horse == 0 and team_of_horse == 0 and record['t'] >= FIRST_RELIABLE_SPAWN_ORDER_S:       # the first 30 s list the agents already on the map in no useful order
                    self._links[horse_spawn[1] - 1].append((record['t'], rider_spawn[1] - 1))
        for links in self._links.values():
            links.sort()

    def knows_horse(self, agent: int) -> bool:
        return agent in self._links

    def links_of(self, horse_agent: int) -> List[Tuple[float, int]]:
        return self._links[horse_agent]


class HorseRiderSubstituter:
    """The client shows the RIDER as the killer when the killer agent is a horse that has a rider (killfeed routine 0x4bb310: agent kind 1 -> the
    agent in its rider field, which the server keeps current with message type 30). This does the same: the latest link of that horse since
    its latest spawn message."""

    LINK_TOLERANCE_S = 0.05
    DEATH_TOLERANCE_S = 0.3
    RESPAWN_AFTER_LINK_S = 0.5
    NO_SPAWN_S = -1e9

    def __init__(self, links: RiderLinkHistory, spawn_times_by_agent: Dict[int, List[float]], death_times_by_agent: Dict[int, List[float]]):
        self._links = links
        self._spawn_times = spawn_times_by_agent
        self._death_times = death_times_by_agent

    def substitute(self, deaths: Iterable[RawDeath]) -> None:
        """For a horse charge by a horse with a rider, the killer becomes the rider (`via_rider_link`). A horse whose rider is gone is marked
        `horse_without_rider`: the scoreboard may still credit the last rider, so the score decides first."""
        for death in deaths:
            if death.weapon_class != HORSE_CHARGE_CLASS or not self._links.knows_horse(death.killer_agent):
                continue
            latest_spawn_s = max([spawn_s for spawn_s in self._spawn_times.get(death.killer_agent, ()) if spawn_s <= death.time_s + self.DEATH_TOLERANCE_S],
                                 default=self.NO_SPAWN_S)
            links = [link for link in self._links.links_of(death.killer_agent)
                     if latest_spawn_s - self.LINK_TOLERANCE_S <= link[0] <= death.time_s + self.DEATH_TOLERANCE_S]
            if not links:
                continue
            link_s, rider = links[-1]
            if self._rider_is_gone(rider, link_s, death.time_s):
                death.horse_without_rider = True
            else:
                death.horse_agent, death.killer_agent, death.via_rider_link = death.killer_agent, rider, True

    def _rider_is_gone(self, rider: int, link_s: float, death_s: float) -> bool:
        """The client only substitutes a rider that is an active agent: one that has died (or been re-spawned) since the link is gone."""
        return (rider < 0
                or any(link_s + self.LINK_TOLERANCE_S < died_s < death_s + self.DEATH_TOLERANCE_S for died_s in self._death_times.get(rider, ()))
                or any(link_s + self.RESPAWN_AFTER_LINK_S < spawned_s <= death_s + self.DEATH_TOLERANCE_S for spawned_s in self._spawn_times.get(rider, ())))
