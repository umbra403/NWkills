"""What the 5-bit weapon class of a kill message means.

The classes are read from the game's jump table (function at 0x4bb310). Names marked (ico_...) are the engine's icon names; the module draws its
own art for them (for example ico_crossbow shows the musket)."""
WEAPON_NAMES = {
    0: 'headshot', 1: 'melee: couched lance (cavalry)', 2: 'fists (punch)', 3: 'cavalry: horse charge (rider hit)', 4: 'bow (ico_bow)',
    5: 'firearm: musket/rifle', 6: 'thrown axe (ico_axethrow)', 7: 'thrown knife (ico_knifethrow)', 8: 'javelin (ico_javelin)',
    9: 'thrown stone (ico_stonethrow)', 10: 'firearm: pistol', 11: 'firearm: musket (ico_musket)', 12: 'melee: sword/sabre',
    13: 'melee: two-handed sword (ico_swordtwo)', 14: 'melee: one-handed axe (ico_axeone)', 15: 'melee: two-handed axe (ico_axetwo)',
    16: 'melee: mace/club', 17: 'melee: bayonet/spear', 18: 'melee: morningstar (ico_morningstar)', 19: 'melee: hammer/mallet',
    20: 'artillery: cannonball', 21: 'artillery: shrapnel/canister', 22: 'artillery: explosion', 23: 'drowning',
    24: 'special: custom icon 5 (ico_custom_5)', 25: 'special: custom icon 6 (ico_custom_6)', 26: 'special: custom icon 7 (ico_custom_7)',
}
HEADSHOT_CLASS = 0
HORSE_CHARGE_CLASS = 3


def weapon_name(weapon_class: int) -> str:
    return WEAPON_NAMES.get(weapon_class, 'class %d' % weapon_class)
