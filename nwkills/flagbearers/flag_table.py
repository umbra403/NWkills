"""Which troops can carry a flag, and which items are flags. The tables come from the module files (troops.txt, item_kinds1.txt) of the game."""
import json
import os
from typing import Iterable, Optional

LOADOUT_FIRST_INDEX, LOADOUT_END_INDEX = 7, 18
MINIMUM_SPAWN_VALUES = 21
AGENT_SPAWN_MESSAGE_TYPE = 5
MAXIMUM_NW_ITEM_ID = 1023


class FlagTable:
    """troops: {troop index: {'name': ..., 'flags': [item index, ...]}}, items: {item index: name}, always: every spawn of such a troop counts."""

    def __init__(self, data: dict):
        self.troops = data['troops']
        self.items = data['items']
        self.every_spawn_counts = bool(data.get('always'))

    @classmethod
    def load(cls, data_directory: str, server_kind: str = 'nw') -> Optional['FlagTable']:
        """The table for 'nw' or 'nwe', or None when this build has none for that server type."""
        path = os.path.join(data_directory, 'flag_troops_%s.json' % server_kind)
        if not os.path.exists(path):
            return None
        with open(path) as table_file:
            return cls(json.load(table_file))


class ServerKindDetector:
    """'nw' when every loadout id fits 10 bits (the NW module), else 'nwe' (the NWE module has more than 1024 items)."""

    def detect(self, packet_records: Iterable[dict]) -> str:
        largest_item_id = 0
        for record in packet_records:
            for message_type, values, _widths in record['msgs']:
                if message_type == AGENT_SPAWN_MESSAGE_TYPE and len(values) >= MINIMUM_SPAWN_VALUES:
                    largest_item_id = max(largest_item_id, max(values[LOADOUT_FIRST_INDEX:LOADOUT_END_INDEX]))
        return 'nw' if largest_item_id <= MAXIMUM_NW_ITEM_ID else 'nwe'
