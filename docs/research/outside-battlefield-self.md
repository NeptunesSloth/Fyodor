# Grist, the Hunger Tide

Current Oracle text retrieved from Scryfall on 2026-10-19. CR 113.6c makes
an ability that states where it does not function work everywhere else,
including before the game. This makes Grist a creature card for commander
eligibility (903.3), creature-card searches and reanimation, and a creature
spell on the stack. It remains a planeswalker too. As it enters the battlefield
its ability stops applying; creature-entry replacements should evaluate that
future battlefield state, and it enters with ordinary planeswalker loyalty.

This is not a characteristic-defining ability: it sets values conditionally
(604.3a). Its type addition belongs in layer 4 and its 1/1 setting in 7b.
Neither is a copiable value, but the copied rules ability works on a copy
outside the battlefield. Face-down objects lack the ability. It must not
grant creature characteristics to an ability object whose source was Grist.

The implementation uses an exact self-ability parser shared with commander
eligibility; layer-4 and layer-7b hooks over layer-1 copiable rules text for
nonbattlefield objects stop on battlefield entry probes. Prospective casting
characteristics include its creature type for restrictions and restricted
mana payment. Searches now use current characteristics, including self-type
additions and dependent group effects such as Maskwood Nexus. Printed/copiable
values remain separate. Derived face-down exile characteristics are empty
under 406.3a; prospective casting reads the face-up spell separately.

Canonical fixtures are in outside_battlefield_self_cards.json. Gameplay checks
cover each nonbattlefield zone, normal cast versus battlefield values,
Essence Scatter countering its creature spell, Reanimate and Green Sun's
Zenith finding it, loyalty entry, face-down suppression, copied card behavior,
actual commander casting, Castle Garenbrig's restricted mana, Maskwood Nexus,
and Containment Priest/Hallowed Moonlight entry qualification. Replay and
save/load are checked throughout.

Syr Konrad tests also exposed a shared missing event: a graveyard-to-battlefield
move returned from the entry branch before recording that it left the
graveyard. Collecting the leave event first preserves normal entry events and
existing look-back source intervals. A reanimated Konrad does not see its own
departure, while an existing Konrad sees Grist enter and leave the graveyard
as a creature card. Nonbattlefield intrinsic types also feed discarded-card
and historical graveyard-card queries.
