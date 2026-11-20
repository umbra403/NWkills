"""The field layouts of the server's message types.

A layout is the list of bit widths of the fields that follow the message type and the peer field. A width given as text is the name of a
ServerProfile field. Message types whose body depends on the data (strings, flags, lists) have no fixed layout; message_reader reads
those with code."""
from .server_profile import ServerProfile

TROOP = 'troop_id_bits'
TYPE7_ID = 'type7_id_bits'
SCENE_PROP = 'scene_prop_bits'
ITEM_ID = 'item_id_bits'
LOADOUT_ITEM = 'loadout_item_bits'
AGENT_SPAWN_EXTRA = 'agent_spawn_extra_bits'

POSITION = (17, 17, 17)                     # x, y, z of a position
ROTATION_AND_SPEED = (12, 12, 12, 12)

# message type -> field widths (after the peer field)
FIXED_LAYOUTS = {
    1: (1, 2, 3),
    2: (3, 5, 13, 13, 13, 13),          # the second field is the faction-count width: 5 on NW and NWE (confirmed on 107 queued packets)
    4: (8, 13, 13),
    5: (10, 8, TROOP, 3, 8, 32) + (LOADOUT_ITEM,) * 11 + (10, 10, 51, 10, 7, 7, 7, 1, AGENT_SPAWN_EXTRA),     # agent spawn
    6: (10, 51, 27, 12, 10, ITEM_ID, 32, ITEM_ID, 32),                                                     # projectile
    8: (10, 17, 17, 17, 12, 12, 12, 12),
    9: (10, 10, 6, 10, 10, 10, 12, 12, 12, 12),
    10: (10, 14, 13, 13, 13, 12, 12, 12, 12),
    11: (10,) * 5 + (12,) * 4,
    12: (10,), 14: (8, 3), 15: (8, TROOP), 16: (8,), 17: (14,), 18: (10,), 19: (10,),
    21: (10, SCENE_PROP, 12, 15, 15, 15, 5),
    22: (12, 12, 12), 23: (10,), 24: (10, 10),
    25: (10, 1), 26: (10, 1), 27: (10, 1),
    28: (10,) * 8 + (8, 8, 1, 12, 2),
    29: (10, 10, 7, 7, 7),
    30: (10, 10),                                  # horse agent + 1, rider agent + 1
    31: (17,),
    34: (7,),
    35: (7, 32), 36: (7, 32, 32), 37: (7, 32, 32, 32), 38: (7, 32, 32, 32, 32),      # script events (the 7 is the 107 wrapper)
    41: (), 42: (14,),
    45: (14,), 46: (14,) + POSITION + ROTATION_AND_SPEED,
    47: (14,) + POSITION + ROTATION_AND_SPEED + (17,),
    48: (14, 10) + POSITION + ROTATION_AND_SPEED + (14, 1),
    49: (),
    50: (8, 10),
    51: (10, 2, 10),
    52: (10, SCENE_PROP, 12, 15, 15, 15, 5),
    54: (8,), 55: (),
    57: (7, 10), 58: (10,), 59: (8,), 60: (10, 1),
    61: (),
}

# message types whose body length depends on the data
DATA_DEPENDENT_TYPES = (0, 3, 7, 13, 20, 32, 33, 39, 40, 43, 44, 53, 56, 62, 63)
KNOWN_MESSAGE_TYPES = frozenset(FIXED_LAYOUTS) | frozenset(DATA_DEPENDENT_TYPES)

# message types that carry text
PLAYER_JOIN_TYPE = 3
CHAT_TYPES = (32, 33, 39)
SERVER_TEXT_TYPE = 39


def resolve_width(width, profile: ServerProfile) -> int:
    """A field width: the number itself, or the profile's value for a field name."""
    return getattr(profile, width) if isinstance(width, str) else width
