"""What a table remembers about its columns when its contents are replaced by a table with other columns."""
from typing import Any, Collection, Dict, List, Mapping, Optional, Tuple


class ColumnMemory:
    """Filter texts, hidden columns and the sort order, kept by column NAME so they survive a table that gets different columns."""

    def __init__(self, headers: List[str], filter_texts: Mapping[int, str], hidden_columns: Collection[int], sort_column: int, sort_order: Any):
        self._filter_texts: Dict[str, str] = {headers[column]: text for column, text in filter_texts.items() if text and column < len(headers)}
        self._hidden_names = {headers[column] for column in range(len(headers)) if column in hidden_columns}
        self._sort: Optional[Tuple[str, Any]] = (headers[sort_column], sort_order) if 0 <= sort_column < len(headers) else None

    def filter_text(self, header: str) -> str:
        return self._filter_texts.get(header, '')

    def is_hidden(self, header: str) -> bool:
        return header in self._hidden_names

    def sort_for(self, new_headers: List[str], default_name: Optional[str], default_order: Any) -> Optional[Tuple[int, Any]]:
        """(column, order) to sort by in the new table: the remembered sort if its column still exists, else the default, else None."""
        if self._sort and self._sort[0] in new_headers:
            return new_headers.index(self._sort[0]), self._sort[1]
        if default_name in new_headers:
            return new_headers.index(default_name), default_order
        return None
