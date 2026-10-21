# Three Way loyalty-grant collateral promotions

Canonical cards: Way of the Deathbringer, Way of the Warlord, and Way of the Wildspeaker. Each is a Legendary Enchantment, not an Aura. Each enters with an empower Jace trigger and grants a quoted loyalty ability to planeswalkers its controller controls. They do not grant loyalty abilities to ordinary nonplaneswalker creatures.

Actual paid casts produce the canonical blue Jace planeswalker token and add five, five, or seven loyalty counters. Existing printed Jace loyalty abilities remain, plus the appropriate granted ability. A control change removes the grant from a planeswalker no longer controlled by the Way's controller; an ordinary Grizzly Bears receives none.

The tests exercise Deathbringer's separate optional payment and creature sacrifice, both pay and decline branches, and its 4/4 green Beast with trample. Warlord deals 2 damage to the required player and optionally a creature/planeswalker. Wildspeaker creates its 4/4 Beast directly. Loyalty costs are paid natively and granted/printed abilities share the normal once-per-turn rule. Activation requires the controller's own main phase and an empty stack. Counterspell counters an actual Disenchant to preserve the Way while independently testing the turn restriction.

Removing the Way in response removes its ongoing grant but does not erase an ability already on the stack. Destroying the Jace host in response does not erase Warlord's damage source; native last known information handles it. An actual Sarkhan the Masterless +1 changes Jace into a Dragon creature without the planeswalker type, which removes the Way grant. Setting its loyalty to zero and advancing state-based actions does not kill that creature. This verifies type eligibility and the distinction between loyalty abilities and the planeswalker zero-loyalty state-based action.

Eight-card fixtures copy complete Oracle metadata from the local canonical database. Every scenario checks replay and JSON save/load, including optional sacrifice decisions. This is tests-only validation of existing shared runtime changes; it adds no engine changes.

Verification: all twelve focused cases and all 74 combined collateral, empower, and granted-loyalty regression cases pass, exit 0. The final off-turn rerun explicitly establishes the activating player's priority on the opponent's turn. Scoped Ruff and diff checks pass. No runtime gap was found in these three collateral promotions.
