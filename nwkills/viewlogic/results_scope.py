"""What part of the Kills table is on screen, as the Players and Multikills tabs see it."""
from typing import List, NamedTuple

WARM_UP_HINT = ' (warm-up rounds left out; pick Warm-up to include them)'


class ResultsScope(NamedTuple):
    rows: List[List[str]]                    # the rows shown right now
    any_filter_active: bool                  # a chip or a column filter is set
    rounds_chosen: bool                      # the user picked rounds or kinds (chips, or a filter on round_kind)


def scope_note(measure: str, shown_count: int, total_count: int, rounds_chosen: bool) -> str:
    """The line under a derived table: 'totals from 12 of 40 kill rows (warm-up rounds left out; ...)'."""
    return '%s from %d of %d kill rows%s' % (measure, shown_count, total_count, '' if rounds_chosen else WARM_UP_HINT)
