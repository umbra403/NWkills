"""The team of an agent, from the spawn messages."""
import bisect
from typing import Dict, List, Optional, Tuple


class TeamHistory:
    """The client's own teamkill test compares the teams of two agents, taken from their latest spawn message."""

    LOOKAHEAD_S = 0.05

    def __init__(self, team_spawns: Dict[int, List[Tuple[float, int]]]):
        self._spawns = {agent: sorted(spawns) for agent, spawns in team_spawns.items()}

    def team_at(self, agent: int, time_s: float) -> Optional[int]:
        """The team from the agent's latest spawn message at or before the moment, or None when its spawn is not in the capture."""
        spawns = self._spawns.get(agent)
        if not spawns:
            return None
        index = bisect.bisect_right(spawns, (time_s + self.LOOKAHEAD_S, 99)) - 1
        return spawns[index][1] if index >= 0 else None
