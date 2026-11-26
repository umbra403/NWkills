"""The regular expression typed under a column label."""
import re
from typing import Callable, Dict, List, Mapping, Optional, Pattern

RowPredicate = Callable[[List[str]], bool]


class ColumnFilters:
    """One compiled regular expression per column. A row passes when every column's expression finds a match in that cell."""

    def __init__(self, patterns: Mapping[int, Pattern], invalid_columns: Optional[List[int]] = None):
        self.patterns: Dict[int, Pattern] = dict(patterns)
        self.invalid_columns: List[int] = list(invalid_columns or [])

    @classmethod
    def compile(cls, texts: Mapping[int, str], ignore_case: bool = True) -> 'ColumnFilters':
        """`texts` maps a column to what was typed there. Empty texts are skipped; a text that is not a valid expression is reported in
        `invalid_columns` and ignored."""
        patterns, invalid_columns = {}, []
        for column, text in texts.items():
            if not text:
                continue
            try:
                patterns[column] = re.compile(text, re.IGNORECASE if ignore_case else 0)
            except re.error:
                invalid_columns.append(column)
        return cls(patterns, invalid_columns)

    def accepts(self, row: List[str]) -> bool:
        return all(pattern.search(row[column]) for column, pattern in self.patterns.items())

    @property
    def is_active(self) -> bool:
        return bool(self.patterns)
