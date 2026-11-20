import unittest
import support
from nwkills.packets import message_layouts
from nwkills.packets.server_profile import NW_PROFILE, NWE_PROFILE, ServerProfile


class ServerProfileTest(unittest.TestCase):
    def test_the_presets_hold_the_known_widths(self):
        self.assertEqual((NWE_PROFILE.troop_id_bits, NWE_PROFILE.type7_id_bits, NWE_PROFILE.scene_prop_bits,
                          NWE_PROFILE.item_id_bits, NWE_PROFILE.loadout_item_bits, NWE_PROFILE.agent_spawn_extra_bits), (11, 11, 10, 12, 12, 9))
        self.assertEqual((NW_PROFILE.troop_id_bits, NW_PROFILE.type7_id_bits, NW_PROFILE.scene_prop_bits,
                          NW_PROFILE.item_id_bits, NW_PROFILE.loadout_item_bits, NW_PROFILE.agent_spawn_extra_bits), (10, 11, 9, 10, 9, 11))

    def test_with_values_replaces_only_the_named_widths(self):
        changed = NWE_PROFILE.with_values(troop_id_bits=7)
        self.assertEqual(changed.troop_id_bits, 7)
        self.assertEqual(changed.item_id_bits, NWE_PROFILE.item_id_bits)
        self.assertEqual(NWE_PROFILE.troop_id_bits, 11)

    def test_with_values_rejects_an_unknown_name(self):
        with self.assertRaises(ValueError):
            NWE_PROFILE.with_values(nonsense=1)

    def test_a_profile_cannot_be_changed_in_place(self):
        with self.assertRaises(Exception):
            NWE_PROFILE.troop_id_bits = 3


class MessageLayoutsTest(unittest.TestCase):
    def test_resolve_width_passes_numbers_through(self):
        self.assertEqual(message_layouts.resolve_width(17, NWE_PROFILE), 17)

    def test_resolve_width_looks_names_up_in_the_profile(self):
        self.assertEqual(message_layouts.resolve_width(message_layouts.TROOP, NW_PROFILE), 10)

    def test_every_type_is_known_once(self):
        self.assertFalse(set(message_layouts.FIXED_LAYOUTS) & set(message_layouts.DATA_DEPENDENT_TYPES))
        self.assertEqual(message_layouts.KNOWN_MESSAGE_TYPES, set(message_layouts.FIXED_LAYOUTS) | set(message_layouts.DATA_DEPENDENT_TYPES))

    def test_every_named_width_is_a_profile_field(self):
        names = {width for layout in message_layouts.FIXED_LAYOUTS.values() for width in layout if isinstance(width, str)}
        self.assertTrue(names <= set(ServerProfile.PROFILE_FIELD_NAMES), names)


if __name__ == '__main__':
    unittest.main()
