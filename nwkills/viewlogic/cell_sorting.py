"""How the cells of a result table are compared and aligned."""
import re
from typing import Iterable, List, Set, Tuple

_NUMBER = re.compile(r'^-?\d+(\.\d+)?$')
_MINUTES_SECONDS = re.compile(r'^\d+:\d\d$')

_NUMERIC_GROUP, _TEXT_GROUP, _EMPTY_GROUP = 0, 1, 2


def is_numeric(text: str) -> bool:
    """A number, or a time written as mm:ss."""
    stripped = text.strip()
    return bool(_NUMBER.match(stripped) or _MINUTES_SECONDS.match(stripped))


def cell_sort_key(text: str) -> Tuple[int, float, str]:
    """Numbers and mm:ss sort by value, text case-insensitively after them, and empty cells last."""
    stripped = text.strip()
    if _MINUTES_SECONDS.match(stripped):
        minutes, seconds = stripped.split(':')
        return (_NUMERIC_GROUP, int(minutes) * 60 + int(seconds), '')
    if _NUMBER.match(stripped):
        return (_NUMERIC_GROUP, float(stripped), '')
    if stripped == '':
        return (_EMPTY_GROUP, 0, '')
    return (_TEXT_GROUP, 0, stripped.lower())


def numeric_column_indexes(column_count: int, rows: Iterable[List[str]]) -> Set[int]:
    """The columns whose filled cells are all numbers: shown right-aligned."""
    rows = list(rows)
    numeric = set()
    for column in range(column_count):
        filled = [row[column] for row in rows if row[column].strip() != '']
        if filled and all(is_numeric(value) for value in filled):
            numeric.add(column)
    return numeric
