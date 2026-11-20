"""Kill events from the decoded packets of a capture."""
from typing import List, Optional

from .admin_actions import AdminAction, AdminActionFinder
from .evidence import MAXIMUM_PLAYER_SLOT
from .kill_decoder import KillDecoder
from .kill_event import KillEvent
from .weapon_names import WEAPON_NAMES

WCODE = WEAPON_NAMES


def admin_lines(packet_records):
    """Admin actions the server announces as text lines -> [AdminAction(time_s, kind, admin, target)]."""
    return AdminActionFinder().find(packet_records)


def decode(packet_records, roster=None, local_slot=None, items=None, namer=None):
    """-> (kill dictionaries in time order, the local player's slot). `namer(slot, time)` gives the name shown for a slot."""
    roster = roster or {}
    if namer is None:
        namer = lambda slot, time_s: roster.get(slot, slot)
    events, local_slot = KillDecoder(namer, items).decode(packet_records, local_slot)
    return [event.to_legacy_dict() for event in events], local_slot
