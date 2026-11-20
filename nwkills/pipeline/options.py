import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class PipelineOptions:
    capture_path: str
    kills_path: Optional[str] = None                 # default: <capture>_kills.csv
    server_port: Optional[int] = None                # default: find the game server in the capture
    own_name_part: Optional[str] = None              # part of the player's own name, to know which slot is the local player
    process_count: int = max(1, os.cpu_count() or 2)
    cache_path: Optional[str] = None                 # a pickle of the decoded packets: re-run the kill logic without decoding again
    packet_limit: Optional[int] = None               # only decode the first N packets (for tests)
