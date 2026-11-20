"""Reading and writing the result tables as CSV files."""
import csv
from typing import List, NamedTuple, Sequence


class CsvTable(NamedTuple):
    headers: List[str]
    rows: List[List[str]]                    # every cell is a string


class CsvTableFile:
    """A CSV file with a header row, in the encoding Excel opens correctly (utf-8 with a byte order mark)."""

    ENCODING = 'utf-8-sig'

    @classmethod
    def read(cls, path: str) -> CsvTable:
        """Short rows are padded with empty cells to the width of the header; empty lines are skipped."""
        with open(path, newline='', encoding=cls.ENCODING) as csv_file:
            reader = csv.reader(csv_file)
            headers = next(reader, [])
            rows = [row + [''] * (len(headers) - len(row)) for row in reader if row]
        return CsvTable(headers, rows)

    @classmethod
    def write(cls, path: str, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        with open(path, 'w', newline='', encoding=cls.ENCODING) as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(headers)
            writer.writerows(rows)
