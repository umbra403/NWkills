"""Turning the raw deaths into kill events: who killed whom, with what, and whether it was a teamkill."""
from typing import Callable, Dict, Iterable, List, Optional

from .evidence import PacketEvidence, ProjectileShot, RawDeath
from .kill_event import KillEvent
from .ownership import AgentOwnership, RespawnIndex
from .score_timeline import ScoreTimeline
from .teams import TeamHistory
from .weapon_names import HEADSHOT_CLASS, weapon_name

TEAM_KILL_MODE = 2                  # the death message's mode field: 2 = a blow (anything else is a death without one)
SCORE_WINDOW_BEFORE_S = 0.3
SCORE_WINDOW_AFTER_S = 2.5
SHOT_MATCH_WINDOW_S = 1.0
HORSE_RIDER_LOOKBACK_S = 20.0


class KillEventBuilder:
    """Combines the raw deaths with the owners, the teams and the scoreboard."""

    def __init__(self, ownership: AgentOwnership, scores: ScoreTimeline, teams: TeamHistory, evidence: PacketEvidence,
                 spawn_times_by_agent: Dict[int, List[float]], death_times_by_agent: Dict[int, List[float]],
                 namer: Callable[[Optional[int], float], object], item_names: Optional[List[str]] = None):
        self._ownership = ownership
        self._scores = scores
        self._teams = teams
        self._evidence = evidence
        self._spawn_times = spawn_times_by_agent
        self._death_times = death_times_by_agent
        self._namer = namer
        self._item_names = item_names
        self._respawns = RespawnIndex(ownership, evidence.spawn_messages)

    def build(self, deaths: Iterable[RawDeath]) -> List[KillEvent]:
        return [self._build_one(death) for death in deaths]

    def _build_one(self, death: RawDeath) -> KillEvent:
        time_s = death.time_s
        killer_slot = self._ownership.owner_at(death.killer_agent, time_s)
        victim_slot = self._ownership.owner_at(death.victim_agent, time_s)
        late_sources = []
        if killer_slot is None:
            killer_slot = self._ownership.owner_learned_later(death.killer_agent, time_s, self._death_times.get(death.killer_agent, []),
                                                              self._spawn_times.get(death.killer_agent, []))
            if killer_slot is not None:
                late_sources.append('killer')       # a victim whose owner is not known by the time of death stays unknown: its next life depends on where the capture started
        score_change, score_baseline_s = self._score_change(killer_slot, time_s)
        team_verdict = self._team_verdict(death, killer_slot, victim_slot)
        is_teamkill = team_verdict if team_verdict is not None else (score_change is not None and score_change < 0)
        return KillEvent(
            time_s=round(time_s, 2), killer=self._namer(killer_slot, time_s), victim=self._namer(victim_slot, time_s),
            weapon=self._weapon_label(death), teamkill='yes' if is_teamkill else '', team_verdict=team_verdict, killer_slot=killer_slot,
            victim_slot=victim_slot, killer_agent=death.killer_agent, victim_agent=death.victim_agent, hit=death.hit, score_change=score_change,
            score_baseline_s=score_baseline_s, mode=death.mode, respawn_delay_s=self._respawn_delay(victim_slot, death), weapon_class=death.weapon_class,
            extra_field_count=death.extra_field_count, late_sources=late_sources, horse=self._is_horse_death(death, killer_slot, victim_slot),
            via_rider_link=death.via_rider_link, horse_without_rider=death.horse_without_rider)

    def _score_change(self, killer_slot: Optional[int], time_s: float):
        """-> (the killer's scoreboard change that goes with this kill, when the score before it was sent)."""
        if killer_slot is None:
            return None, None
        scores_after = self._scores.scores_between(killer_slot, time_s - SCORE_WINDOW_BEFORE_S, time_s + SCORE_WINDOW_AFTER_S)
        if not scores_after:
            return None, None
        times_before = self._scores.times_before(killer_slot, time_s - SCORE_WINDOW_BEFORE_S)
        scores_before = self._scores.scores_before(killer_slot, time_s - SCORE_WINDOW_BEFORE_S)
        if scores_before:
            change = scores_after[0] - scores_before[-1]
            if abs(change) >= 2 and -1 <= scores_after[0] <= 1:
                change = scores_after[0]              # a jump no single kill makes: the scoreboard was reset to 0 without us seeing it
            return (change if change != 0 else None), times_before[-1]
        if -3 <= scores_after[0] < 0:
            return scores_after[0], None              # first score ever sent for this player: the server omits a score of 0, so the baseline was 0
        return None, None

    def _respawn_delay(self, victim_slot: Optional[int], death: RawDeath) -> Optional[float]:
        if victim_slot is None or victim_slot < 0:
            return None
        return self._respawns.delay_after_death(victim_slot, death.victim_agent, death.time_s)

    def _is_horse_death(self, death: RawDeath, killer_slot: Optional[int], victim_slot: Optional[int]) -> bool:
        """A death without a blow of a player-owned agent that has never shown rider properties is the player's horse."""
        rider_times = self._evidence.rider_property_times
        if (death.mode != TEAM_KILL_MODE and victim_slot is not None and victim_slot >= 0 and killer_slot is not None and killer_slot >= 0
                and killer_slot != victim_slot and rider_times):
            return not any(death.time_s - HORSE_RIDER_LOOKBACK_S <= seen_s <= death.time_s + 0.5 for seen_s in rider_times.get(death.victim_agent, []))
        return False

    def _weapon_label(self, death: RawDeath) -> str:
        if death.weapon_class == HEADSHOT_CLASS and death.mode != TEAM_KILL_MODE:
            return 'no blow (mode %s)' % death.mode
        label = weapon_name(death.weapon_class)
        if death.weapon_class == HEADSHOT_CLASS:
            shots = [shot.item_index for shot in self._evidence.projectile_shots
                     if shot.shooter_agent == death.killer_agent and -SHOT_MATCH_WINDOW_S < death.time_s - shot.time_s < SHOT_MATCH_WINDOW_S]
            if shots and self._item_names and 0 <= shots[0] < len(self._item_names):
                label += ' (' + self._item_names[shots[0]][4:] + ')'
        return label

    def _team_verdict(self, death: RawDeath, killer_slot: Optional[int], victim_slot: Optional[int]) -> Optional[bool]:
        """The client decides a teamkill from the two agents' teams (a friendly relation between them), not from the score. Used when both players'
        agents have a spawn message in the capture; otherwise the killer's score change decides (older behaviour)."""
        if (death.mode == TEAM_KILL_MODE and killer_slot is not None and killer_slot >= 0 and victim_slot is not None and victim_slot >= 0
                and death.killer_agent != death.victim_agent):
            killer_team = self._teams.team_at(death.killer_agent, death.time_s)
            victim_team = self._teams.team_at(death.victim_agent, death.time_s)
            if killer_team is not None and victim_team is not None:
                return killer_team == victim_team
        return None
