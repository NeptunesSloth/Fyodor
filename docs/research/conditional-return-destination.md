# Emeria Shepherd: optional conditional return destination

Oracle: “Landfall — Whenever a land you control enters, you may return target nonland permanent card from your graveyard to your hand. If that land is a Plains, you may return that nonland permanent card to the battlefield instead.”

Official rulings: https://api.scryfall.com/cards/08ef3822-592f-456f-823d-a4d5cc85ddf9/rulings

The target must be a nonland permanent card in the trigger controller's graveyard when the ability goes on the stack. Optional return does not make target choice optional. An illegal sole target at resolution causes the ordinary whole-ability fizzle (608.2b). Battle cards qualify under current permanent-card rules despite the old 2015 ruling's pre-Battle enumeration.

The condition describes the triggering land, not the targeted graveyard card. At resolution use its current characteristics if it remains the same battlefield object, otherwise its battlefield last-known information (608.2h). A land that is a Plains when entering but loses the type before resolution does not qualify; a non-Plains that gains it does. A Plains leaving and returning as a different object must not substitute its new characteristics for the old one.

The bounded typed primitive: offer hand / battlefield (only when event-land condition holds) / decline to the trigger controller, then delegate the selected destination to native return_card. Battlefield return is under your control; ordinary Aura entry choices/legality, counter replacements, Priest/Moonlight, and Grafdigger's Cage are reused. The generic “instead” parser deliberately refuses an optional alternative and also guards ambiguous event-object-versus-target binding. This exact reusable body parser should bypass those ambiguities without weakening the generic grammar.

Tests to prepare: Plains and Forest each with accepted/declined destinations; choosing hand despite Plains; illegal graveyard target fizzle; no legal target; current type changes and LKI/old-OID distinction; Aura return attached without targeting hexproof host and Aura without legal host remains graveyard; entry replacement; source leaves/control changes; target legality plus private decision views; JSON save/load/replay across destination and subsequent Aura-choice prompts.


Implementation: `app/rules/conditional_return_destination.py` emits a typed destination-choice effect with an explicit event-object Plains selector and native return template/target selector. It returns false for whole-ability optionality because hand, battlefield and decline are one decision at resolution. The resume handler delegates to native return_card, including a subsequent Aura-entry choice, so the ordinary continuation persists through both decisions.

Seventeen focused gameplay cases pass, with canonical metadata for all fixture cards. Real Phantasmal Terrain and Spreading Seas change the event land's current types while the trigger is pending; actual Alchemist's Refuge activation permits casting these Auras in response. Boomerang then removes a formerly Forest/now Plains land, verifying battlefield LKI rather than the card's new hand characteristics. The generic native permanent-card selector includes a Battle target. Original trigger controller survives source departure or control changes. Private destination and Aura choices replay and save/load correctly.

Nylea's Presence was deliberately not used as an automated fixture: its separate “enchanted land is every basic land type” static remains unsupported and needs a later family extension. No generic grammar or land-type engine guard was weakened to make the Emeria tests pass.
