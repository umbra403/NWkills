"""Where the files of one run go."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OutputPaths:
    kills: str
    players: str
    rounds: str
    flagbearers: str

    @classmethod
    def for_kills_file(cls, kills_path: str) -> 'OutputPaths':
        """The other files sit next to the kills file: <name>_rounds.csv, <name>_flagbearers.csv, <name>_players.csv."""
        stem = os.path.splitext(kills_path)[0]
        shared_stem = stem.replace('_kills', '')
        return cls(kills=kills_path, players=stem + '_players.csv', rounds=shared_stem + '_rounds.csv', flagbearers=shared_stem + '_flagbearers.csv')

    @classmethod
    def for_capture(cls, capture_path: str, kills_path: str = None) -> 'OutputPaths':
        return cls.for_kills_file(kills_path or os.path.splitext(capture_path)[0] + '_kills.csv')
