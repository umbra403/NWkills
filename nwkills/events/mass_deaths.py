"""Map changes and resets: the server kills every agent at once."""
from typing import Iterable, List, Set, Tuple


class MapChangeDeathFilter:
    """At a map change or reset the server kills every agent at once (killer == victim): hundreds of messages in a few seconds, often in queued
    packets. They are not kills. Self-deaths are treated as such a block when 8 or more different agents have one within 3 seconds, unless the
    server announced the block as an admin action."""

    DISTINCT_AGENT_THRESHOLD = 8
    HALF_WINDOW_S = 1.5
    ADMIN_BLOCK_BEFORE_S = 2.5
    ADMIN_BLOCK_AFTER_S = 1.5
    DEATH_MESSAGE_TYPE = 13
    MINIMUM_DEATH_VALUES = 6                 # peer field + 5 fields

    def find_block_times(self, packet_records: Iterable[dict], admin_block_times: Iterable[float]) -> Set[float]:
        """The times of the packets that hold self-deaths of such a block."""
        admin_block_times = list(admin_block_times)
        self_deaths = self._self_deaths(packet_records)
        block_times: Set[float] = set()
        window_start = 0
        for index, (time_s, _agent) in enumerate(self_deaths):
            while self_deaths[window_start][0] < time_s - self.HALF_WINDOW_S:
                window_start += 1
            window_end = index
            while window_end + 1 < len(self_deaths) and self_deaths[window_end + 1][0] <= time_s + self.HALF_WINDOW_S:
                window_end += 1
            distinct_agents = {agent for _t, agent in self_deaths[window_start:window_end + 1]}      # one death is sent again and again while the client is slow to acknowledge
            announced_by_admin = any(admin_s - self.ADMIN_BLOCK_BEFORE_S <= time_s <= admin_s + self.ADMIN_BLOCK_AFTER_S for admin_s in admin_block_times)
            if len(distinct_agents) >= self.DISTINCT_AGENT_THRESHOLD and not announced_by_admin:
                block_times.add(time_s)
        return block_times

    def _self_deaths(self, packet_records: Iterable[dict]) -> List[Tuple[float, int]]:
        return sorted((record['t'], values[1]) for record in packet_records for message_type, values, _widths in record['msgs']
                      if message_type == self.DEATH_MESSAGE_TYPE and len(values) >= self.MINIMUM_DEATH_VALUES and values[1] == values[2])
