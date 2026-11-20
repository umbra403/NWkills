"""Turning a selection of cells into text to paste into a spreadsheet."""
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple


class TabSeparatedFormatter:
    """Tab separated text, which Excel, Sheets and LibreOffice paste into columns."""

    @staticmethod
    def clean(text: str) -> str:
        return re.sub(r'[\t\r\n]+', ' ', text)

    @classmethod
    def format(cls, headers: Sequence[str], grid: Sequence[Sequence[Optional[str]]], with_header: bool = False) -> str:
        """`grid` is a list of rows; None marks a cell that is not selected (it becomes empty)."""
        lines = []
        if with_header:
            lines.append('\t'.join(cls.clean(header) for header in headers))
        for row in grid:
            lines.append('\t'.join('' if value is None else cls.clean(value) for value in row))
        return '\n'.join(lines)


class SelectedCellGrid:
    """The rectangle that covers the selected cells, in the order the columns are shown."""

    @staticmethod
    def build(cells: Dict[Tuple[int, int], str], header_of_visual_column: Callable[[int], str]) -> Tuple[List[str], List[List[Optional[str]]]]:
        """`cells` maps (row, visual column) to the cell text. -> (headers of the columns used, rows with None where nothing is selected)."""
        if not cells:
            return [], []
        rows = sorted({row for row, _ in cells})
        columns = sorted({column for _, column in cells})
        headers = [header_of_visual_column(column) for column in columns]
        return headers, [[cells.get((row, column)) for column in columns] for row in rows]
