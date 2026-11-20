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

    def to_legacy_dict(self) -> dict:
        """The dictionary form the later stages still use (removed when they move to this class)."""
        legacy = dict(time=self.time_s, killer=self.killer, victim=self.victim, weapon=self.weapon, teamkill=self.teamkill,
                      tk_team=self.team_verdict, killer_slot=self.killer_slot, victim_slot=self.victim_slot, killer_agent=self.killer_agent,
                      victim_agent=self.victim_agent, hit=self.hit, dl=self.score_change, dl_base_t=self.score_baseline_s, mode=self.mode,
                      respawn=self.respawn_delay_s, wcode=self.weapon_class, nextra=self.extra_field_count, late=self.late_sources,
                      horse=self.horse, via_link=self.via_rider_link, link_none=self.horse_without_rider)
        for key, value in (('in_group', self.in_volley), ('burst', self.burst_guess), ('runaway', self.runaway_horse), ('tk_check', self.score_contradicts_team)):
            if value is not None:
                legacy[key] = value
        return legacy
