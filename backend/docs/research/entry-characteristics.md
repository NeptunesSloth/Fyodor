# Characteristics supplied as a permanent enters

CR 611.2e distinguishes a resolving effect saying a returned nontoken permanent
**is/has** a characteristic from an effect saying it **becomes/gains** one. The
former applies simultaneously with entry. The latter applies afterward. Entry
replacements inspect the prospective permanent under CR 614.12; enter triggers
see its actual characteristics. These continuous changes are not copiable values
(CR 707.2).

`EntryCharacteristics` is a typed, saved, noncopiable form on the permanent. Native
layers compose it in layers 4, 5, 6 and 7b with a frozen effect timestamp and the
actual object's entry timestamp. It survives phasing and control changes, clears
on a real zone change, and is excluded from copy recipes. Native replacement
planning receives the form on its prospective battlefield probe. The final Move
carries a per-card form map, assigned only to successful battlefield entries
before tracking and enter-trigger collection. Redirecting an entry to exile
therefore does not leave the form on the exiled card.

The native return and looked-card entry continuations carry the JSON descriptor,
so replacement questions, saved games and replay retain the same instructions.
Existing exact `is` riders and Enduring `enters_as` instructions are hoisted before
the return; ordinary `becomes`/`gains` instructions remain after it. Legacy saved
post-entry `enters_as` instructions retain their compatibility handler.

The bounded canonical family is Dance of the Manse, Grave Betrayal, Grimoire of
the Dead, Drana, the Last Bloodchief, Ghouls' Night Out, Excava, the Risen Past,
The War in Heaven, Arbiter of the Ideal, Abuelo's Awakening, Relive the Past,
Tom, Bert, and William, and Otherworldly Escort. Existing Rise from the Grave,
Liliana, Death's Majesty, and the Enduring cycle use the same entry foundation.
Ghouls' Night Out uses native choices for every graveyard before one simultaneous
return; its explicitly gained decayed keyword remains a post-entry effect.
Drana's defending player chooses from the original ability controller's graveyard.
Arbiter's manifestation counter is only a reminder: removing it does not remove
the added Enchantment type.

Canonical Oracle metadata and official rulings were retrieved from the repository
card database and Scryfall's official-rulings records. Focused tests exercise actual
spells and abilities, replacement predicates, simultaneous groups, exact objects,
noncopiable values, counters, save/load and replay. Cards with other unsupported
abilities and Aura return forms are excluded from this bounded implementation.
