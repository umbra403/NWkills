"""The agent spawns of a capture."""
from typing import Dict, Iterable, List, NamedTuple, Tuple

AGENT_SPAWN_MESSAGE_TYPE = 5
MINIMUM_SPAWN_VALUES = 21
LOADOUT_FIRST_INDEX, LOADOUT_END_INDEX = 7, 18


class AgentSpawn(NamedTuple):
    time_s: float
    agent: int
    owner_slot: int
    troop_index: int
    item_indexes: Tuple[int, ...]


class SpawnExtractor:
    """Type-5 messages with the repeats of the same spawn removed: the server repeats a spawn message for a few ticks."""

    REPEAT_WINDOW_S = 8.0

    def extract(self, packet_records: Iterable[dict]) -> List[AgentSpawn]:
        spawns: List[AgentSpawn] = []
        last_seen_s: Dict[tuple, float] = {}
        for record in packet_records:
            time_s = record['t']
            for message_type, values, _widths in record['msgs']:
                if message_type != AGENT_SPAWN_MESSAGE_TYPE or len(values) < MINIMUM_SPAWN_VALUES or values[1] <= 0:
                    continue
                agent, owner, troop = values[1] - 1, values[2] - 1, values[3] - 1
                items = tuple(item - 1 for item in values[LOADOUT_FIRST_INDEX:LOADOUT_END_INDEX] if item)
                key = (agent, owner, troop, items)
                if key in last_seen_s and time_s - last_seen_s[key] < self.REPEAT_WINDOW_S:
                    last_seen_s[key] = time_s
                    continue
                last_seen_s[key] = time_s
                spawns.append(AgentSpawn(time_s, agent, owner, troop, items))
        return spawns
