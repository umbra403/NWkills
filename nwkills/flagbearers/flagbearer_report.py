"""Who spawned carrying a flag, per round.

NWE has dedicated '*_flag_bearer' troops: every spawn of one counts (the flag item is filled in when the loadout shows it, else 'unknown').
In the NW module only some NCO troops (and two French 'colours' troops) can pick a flag; the flag is one of the items in that troop's
inventory. A spawn counts as a flagbearer when the troop can carry a flag AND the loadout contains one of that troop's flag items (troop index =
field - 1, item index = id - 1). Loadout ids are not reliable for items outside the troop's own inventory (the server's item table differs from
the module files for armour), which is why the troop is required as well."""
import collections
from typing import Callable, Iterable, List, NamedTuple, Optional

from ..rounds import RoundTimeline

from .flag_table import FlagTable
from .spawn_extractor import SpawnExtractor

UNKNOWN_FLAG = 'itm_unknown'


class FlagbearerRow(NamedTuple):
    round_number: int
    round_kind: str
    player: str
    owner_slot: int
    troop: str
    flag: str
    spawn_count: int
    first_spawn_s: float
    last_spawn_s: float
    review: str                 # 'name?' when the player's name is not known


class FlagbearerReport:
    def __init__(self, table: FlagTable, timeline: RoundTimeline, namer: Callable[[int, float], str], spawn_extractor: Optional[SpawnExtractor] = None):
        self._table = table
        self._timeline = timeline
        self._namer = namer
        self._spawn_extractor = spawn_extractor or SpawnExtractor()

    def build(self, packet_records: Iterable[dict]) -> List[FlagbearerRow]:
        """One row per round, player, troop and flag, sorted by round, name and first spawn."""
        totals = collections.OrderedDict()
        for spawn in self._spawn_extractor.extract(packet_records):
            troop = self._table.troops.get(str(spawn.troop_index))
            if not troop or spawn.owner_slot < 0:
                continue
            carried_flags = [item for item in spawn.item_indexes if item in troop['flags']]
            if not carried_flags and not self._table.every_spawn_counts:
                continue
            round_number = self._timeline.number_at(spawn.time_s)
            key = (round_number, spawn.owner_slot, troop['name'], self._table.items[str(carried_flags[0])] if carried_flags else UNKNOWN_FLAG)
            total = totals.setdefault(key, [0, spawn.time_s, spawn.time_s])
            total[0] += 1
            total[2] = spawn.time_s
        rows = []
        for (round_number, owner_slot, troop_name, flag), (spawn_count, first_s, last_s) in totals.items():
            name = self._namer(owner_slot, first_s)
            rows.append(FlagbearerRow(round_number, self._timeline.kind_at(first_s), name, owner_slot, troop_name.replace('trp_', ''),
                                      flag.replace('itm_', ''), spawn_count, round(first_s, 1), round(last_s, 1),
                                      'name?' if name.startswith(('?', 'player#')) else ''))
        rows.sort(key=lambda row: (row.round_number, row.player.lower(), row.first_spawn_s))
        return rows
