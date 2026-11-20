"""Admin actions the server announces as text lines."""
import re
from typing import Iterable, List, NamedTuple, Optional


class AdminAction(NamedTuple):
    time_s: float
    kind: str                       # 'slay', 'slay_all' or 'swap_all'
    admin: str
    target: Optional[str]           # the slain player, for 'slay'


class AdminActionFinder:
    """Finds "X Slayed Player Y.", "X Slayed Everyone." and "X Swapped Everyone to Spectators." in the server text lines. Each line arrives in two
    copies; the second copy within a second is dropped."""

    PATTERNS = ((re.compile(r'^(.+?) Slayed Player (.+)\.$'), 'slay'),
                (re.compile(r'^(.+?) Slayed Everyone\.?$'), 'slay_all'),
                (re.compile(r'^(.+?) Swapped Everyone to Spectators\.?$'), 'swap_all'))
    DUPLICATE_WINDOW_S = 1.0

    def find(self, packet_records: Iterable[dict]) -> List[AdminAction]:
        actions: List[AdminAction] = []
        for record in packet_records:
            for line in record['txt']:
                for pattern, kind in self.PATTERNS:
                    match = pattern.match(line.strip())
                    if match:
                        target = match.group(2) if kind == 'slay' else None
                        if not any(action.kind == kind and action.target == target and abs(action.time_s - record['t']) < self.DUPLICATE_WINDOW_S
                                   for action in actions):
                            actions.append(AdminAction(record['t'], kind, match.group(1), target))
                        break
        return actions
