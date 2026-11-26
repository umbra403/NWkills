"""The kind of a death."""
from ..events.kill_event import KillEvent

BLOW_MODE = 2


class DeathClassifier:
    """Provisional classification (there is no ground truth yet for the non-blow kinds). Test capture with chat markers: fall = self + class 0,
    suicide = self + class 2, team swap = killer-less + class 0 (a player leaving the server looks the same)."""

    KILL = 'kill'
    AI_OR_HORSE_DEATH = 'AI/horse death'
    WORLD_DEATH = 'world (team swap / left server)'
    HORSE_DEATH = 'horse death (player-owned mount)'
    NO_BLOW_KNOWN_KILLER = 'no-blow death (mount?, not counted)'
    NO_BLOW_UNKNOWN_KILLER = 'non-blow death (leave/class change?)'

    def classify(self, event: KillEvent) -> str:
        if event.victim_slot is not None and event.victim_slot < 0:
            return self.AI_OR_HORSE_DEATH
        if event.killer_agent is not None and event.killer_agent < 0:
            return self.WORLD_DEATH
        if event.killer_slot is not None and event.killer_slot == event.victim_slot:
            return self._self_inflicted(event)
        if event.horse:
            return self.HORSE_DEATH              # the victim agent is the player's horse (no rider properties); not a player death, no score
        if event.mode != BLOW_MODE:
            if event.killer_slot is not None and event.killer_slot >= 0:
                return self.NO_BLOW_KNOWN_KILLER              # known killer, no blow data and no killfeed line (seen on video: horse deaths); not counted
            return self.NO_BLOW_UNKNOWN_KILLER
        return self.KILL

    @staticmethod
    def _self_inflicted(event: KillEvent) -> str:
        if event.weapon.startswith('headshot'):
            return 'self-inflicted: fall'                                      # confirmed by chat markers in a test capture
        if event.weapon.startswith('fists'):
            return 'self-inflicted: suicide (no admin line)'                  # slay and suicide share the packets and the killfeed icon
        if event.weapon == 'drowning':
            return 'self-inflicted: drowning'                                 # confirmed on video (own drowning, capture 2026-11-11)
        return 'self-inflicted (other)'

    @staticmethod
    def is_self_inflicted(death_type: str) -> bool:
        return death_type.startswith('self')

    @staticmethod
    def is_uncounted_mount_death(death_type: str) -> bool:
        return death_type.startswith(('horse death', 'no-blow death'))
