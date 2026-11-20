"""The bit widths that differ from one server to the next.

Several message fields are ids into the server's module tables (troops, items, scene props ...). The game stores each as many bits as the
table needs, so every module has its own widths. They cannot be read from a packet directly; profile_calibrator finds them by trying
candidates until the packets of the capture parse to their end."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ServerProfile:
    troop_id_bits: int              # troop id (+1) in an agent spawn (type 5) and the state field of type 15 and of the player join record
    type7_id_bits: int              # id field read by message type 7
    scene_prop_bits: int            # first id field of types 20, 21 and 52
    item_id_bits: int               # item id in a projectile (type 6)
    loadout_item_bits: int          # each of the 11 loadout item ids in an agent spawn (type 5)
    agent_spawn_extra_bits: int     # extra bits at the end of an agent spawn (0 = none)

    PROFILE_FIELD_NAMES = ('troop_id_bits', 'type7_id_bits', 'scene_prop_bits', 'item_id_bits', 'loadout_item_bits', 'agent_spawn_extra_bits')

    def with_values(self, **changes) -> 'ServerProfile':
        """A copy with the given widths replaced."""
        values = {name: getattr(self, name) for name in self.PROFILE_FIELD_NAMES}
        unknown_names = set(changes) - set(values)
        if unknown_names:
            raise ValueError('unknown profile field(s): %s' % ', '.join(sorted(unknown_names)))
        values.update(changes)
        return ServerProfile(**values)


NWE_PROFILE = ServerProfile(troop_id_bits=11, type7_id_bits=11, scene_prop_bits=10, item_id_bits=12, loadout_item_bits=12, agent_spawn_extra_bits=9)
NW_PROFILE = ServerProfile(troop_id_bits=10, type7_id_bits=11, scene_prop_bits=9, item_id_bits=10, loadout_item_bits=9, agent_spawn_extra_bits=11)
