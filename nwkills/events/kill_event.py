"""One kill (one row of the kills file)."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class KillEvent:
    time_s: float
    killer: object                          # a name, or '?', '(AI)', '(world)'
    victim: object
    weapon: str
    teamkill: str                           # 'yes' or ''
    team_verdict: Optional[bool]            # the two agents' teams said teamkill (True) or not (False); None when a spawn was not in the capture
    killer_slot: Optional[int]
    victim_slot: Optional[int]
    killer_agent: int
    victim_agent: int
    hit: Optional[int]
    score_change: Optional[int]             # the killer's scoreboard change that goes with this kill
    score_baseline_s: Optional[float]       # when the score before the change was sent
    mode: Optional[int]
    respawn_delay_s: Optional[float]
    weapon_class: int
    extra_field_count: int
    late_sources: List[str] = field(default_factory=list)       # which names came from data that arrives after the kill
    horse: bool = False                     # the death of a player's horse
    via_rider_link: bool = False
    horse_without_rider: bool = False
    in_volley: Optional[bool] = None        # one of several kills by one player within a few seconds
    burst_guess: Optional[bool] = None      # the number of teamkills in the volley is exact, which of them is a guess
    runaway_horse: Optional[bool] = None
    score_contradicts_team: Optional[bool] = None
    admin_label: Optional[str] = None       # set when a server admin action caused this death ('admin slay', 'admin: slayed everyone', ...)
