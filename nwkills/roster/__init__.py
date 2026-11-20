"""Who sat in which player slot, and when: the names the server announces in clear, merged and corrected into a PlayerRoster."""
from .name_sighting import NameSighting, PlayerNameHeuristics
from .join_record_scanner import JoinRecordScanner
from .player_roster import PlayerRoster, SlotNamer
from .roster_filler import RosterFiller
from .unnamed_slots import UnnamedSlotFinder
