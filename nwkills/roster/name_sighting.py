"""One sighting of a player name in a slot, and the rule that tells real names from coincidental byte patterns."""
from typing import NamedTuple


class NameSighting(NamedTuple):
    """The name seen in a player slot. `count` is the number of packets it was seen in (0 for the placeholder that marks a slot as unknown)."""
    first_seen_s: float
    last_seen_s: float
    name: str
    count: int


class PlayerNameHeuristics:
    """A name seen in only one packet is accepted only when it looks like a real player name. Random bytes that happen to match the
    join-record pattern give strings like m."_\\Dt, which once took over a slot (and all its kills) in one capture."""

    MINIMUM_LENGTH = 6
    MINIMUM_ALPHANUMERIC = 5
    MINIMUM_ALPHANUMERIC_SHARE = 0.6

    @classmethod
    def looks_like_player_name(cls, name: str) -> bool:
        if len(name) < cls.MINIMUM_LENGTH or '"' in name or '\\' in name:
            return False
        alphanumeric_count = sum(character.isalnum() for character in name)
        return alphanumeric_count >= cls.MINIMUM_ALPHANUMERIC and alphanumeric_count >= cls.MINIMUM_ALPHANUMERIC_SHARE * len(name)
