"""What the decoded packets say about deaths, owners, spawns and scores, before anything is combined."""
import collections
from dataclasses import dataclass, field
from typing import DefaultDict, Dict, Iterable, List, NamedTuple, Optional, Set, Tuple

MAXIMUM_PLAYER_SLOT = 250
NO_OWNER_BEFORE_S = 30.0                 # owners listed in the first 30 s were known from the start of the capture: keep their order only
PREEXISTING_OWNER_TIME_FACTOR = 1e-6

DEATH_MESSAGE_TYPE = 13
PROJECTILE_MESSAGE_TYPE = 6
AGENT_SPAWN_MESSAGE_TYPE = 5
LOCAL_RESPAWN_MESSAGE_TYPE = 18
MINIMUM_DEATH_FIELDS = 5
HIT_FIELD_BIT_WIDTH = 9
MINIMUM_PROJECTILE_FIELDS = 6
AGENT_OWNER_PROPERTY, AGENT_DYING_PROPERTY = 27, 13
RIDER_PROPERTIES = (6, 7)
PLAYER_SCORE_PROPERTY = 0
SIGNED_SCORE_LIMIT, SCORE_WRAP = 4096, 8192
MAXIMUM_STATE_BLOCK_SLACK_BITS = 8


@dataclass
class RawDeath:
    """A death message. Agent numbers are the game's agent ids (the message holds id + 1)."""
    time_s: float
    victim_agent: int
    killer_agent: int
    weapon_class: int
    hit: Optional[int]
    mode: Optional[int]
    extra_field_count: int
    horse_agent: Optional[int] = None            # set when the killer was a horse and the rider was credited instead
    via_rider_link: bool = False
    horse_without_rider: bool = False


class OwnerSighting(NamedTuple):
    """An agent owned by a player slot, seen at a moment."""
    time_s: float
    agent: int
    slot: int


class AgentTime(NamedTuple):
    agent: int
    time_s: float


class ProjectileShot(NamedTuple):
    time_s: float
    shooter_agent: int
    item_index: int


@dataclass
class PacketEvidence:
    deaths: List[RawDeath] = field(default_factory=list)
    owner_sightings: List[OwnerSighting] = field(default_factory=list)
    spawn_messages: List[AgentTime] = field(default_factory=list)                 # spawns that carry an owner slot
    local_respawns: List[AgentTime] = field(default_factory=list)                 # message type 18: the agent the local player got
    projectile_shots: List[ProjectileShot] = field(default_factory=list)
    team_spawns: DefaultDict[int, List[Tuple[float, int]]] = field(default_factory=lambda: collections.defaultdict(list))   # agent -> [(time, team)]
    dying_times: DefaultDict[int, List[float]] = field(default_factory=lambda: collections.defaultdict(list))                # agent -> times it was flagged dying
    rider_property_times: DefaultDict[int, List[float]] = field(default_factory=lambda: collections.defaultdict(list))
    raw_score_updates: List[Tuple[float, int, int, bool]] = field(default_factory=list)


class EvidenceCollector:
    """Reads the kept messages and the state blocks of the packet records (the dictionaries of PacketDecoder.to_legacy_record)."""

    REPEATED_DEATH_WINDOW_S = 4.0

    def collect(self, packet_records: Iterable[dict], mass_death_times: Set[float]) -> PacketEvidence:
        evidence = PacketEvidence()
        previous_death_key, previous_death_time = None, None
        for record in packet_records:
            time_s = record['t']
            for message_type, values, widths in record['msgs']:
                fields, field_widths = values[1:], widths[1:]
                if message_type == DEATH_MESSAGE_TYPE and len(fields) >= MINIMUM_DEATH_FIELDS:
                    if fields[0] == fields[1] and time_s in mass_death_times:
                        continue
                    key = (fields[0] - 1, fields[1] - 1)
                    if previous_death_key == key and time_s - previous_death_time < self.REPEATED_DEATH_WINDOW_S:
                        previous_death_time = time_s              # the server repeats a death message until it is acknowledged
                        continue
                    previous_death_key, previous_death_time = key, time_s
                    evidence.deaths.append(RawDeath(time_s, key[0], key[1], fields[2], fields[-1] if field_widths[-1] == HIT_FIELD_BIT_WIDTH else None,
                                                    fields[3] if len(fields) > 3 else None, len(fields) - MINIMUM_DEATH_FIELDS))
                elif message_type == AGENT_SPAWN_MESSAGE_TYPE and len(fields) > 20 and fields[0] > 0:
                    evidence.team_spawns[fields[0] - 1].append((time_s, fields[3]))
                    if fields[1] - 1 <= MAXIMUM_PLAYER_SLOT:
                        evidence.owner_sightings.append(OwnerSighting(time_s, fields[0] - 1, fields[1] - 1))
                        evidence.spawn_messages.append(AgentTime(fields[0] - 1, time_s))
                elif message_type == LOCAL_RESPAWN_MESSAGE_TYPE and fields and fields[0] > 0:
                    evidence.local_respawns.append(AgentTime(fields[0] - 1, time_s))
                elif message_type == PROJECTILE_MESSAGE_TYPE and len(fields) >= MINIMUM_PROJECTILE_FIELDS:
                    evidence.projectile_shots.append(ProjectileShot(time_s, fields[4] - 1, fields[5] - 1))
            self._collect_state_block(evidence, record, time_s)
        return evidence

    @staticmethod
    def _collect_state_block(evidence: PacketEvidence, record: dict, time_s: float) -> None:
        state_block = record['tail']
        if not state_block:
            return
        read_cleanly = record['L'] - state_block['end'] < MAXIMUM_STATE_BLOCK_SLACK_BITS and not record['err']     # the property list of a packet that did not parse to the end can hold garbage
        for agent, property_number, value in state_block['agents']:
            if property_number == AGENT_OWNER_PROPERTY and 0 < value <= MAXIMUM_PLAYER_SLOT + 1 and read_cleanly:
                known_from_start = time_s < NO_OWNER_BEFORE_S
                evidence.owner_sightings.append(OwnerSighting(time_s * PREEXISTING_OWNER_TIME_FACTOR if known_from_start else time_s, agent, value - 1))
            if property_number == AGENT_DYING_PROPERTY and value == 1:
                evidence.dying_times[agent].append(time_s)
            if property_number in RIDER_PROPERTIES:           # rider agents carry these properties; horses do not
                evidence.rider_property_times[agent].append(time_s)
        for player, property_number, value in state_block['players']:
            if property_number == PLAYER_SCORE_PROPERTY:
                signed_score = value - SCORE_WRAP if value >= SIGNED_SCORE_LIMIT else value
                evidence.raw_score_updates.append((time_s, player, signed_score, read_cleanly))
