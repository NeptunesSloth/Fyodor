# Mana values of spells cast this turn

Call Forth the Tempest's Oracle text and official rulings were checked at
[Scryfall](https://api.scryfall.com/cards/81d6b979-251a-4736-86f0-35a6c8b492c9) and
[official rulings](https://api.scryfall.com/cards/81d6b979-251a-4736-86f0-35a6c8b492c9/rulings).

The damage counts all other spells its controller cast before the effect
resolves, including spells cast using either cascade ability. It counts spells
that were countered or remain on the stack. Copies put directly onto the stack
were not cast and do not contribute. These points are explicit official rulings.

The existing cast history stores a snapshot of each spell as it became cast
(CR 601.2i, 608.2i). Its recorded mana value includes the announced X on the
stack (CR 202.3e), rather than the card's later mana value in another zone. The
amount of mana paid, including a free cast or a reduced cost, is irrelevant.

The typed aggregate filters the caster and optional spell characteristics,
then sums recorded mana values. "Other" excludes only the source object, not
every earlier cast of the same physical card. An uncast copy of Tempest is a
different object and therefore includes the original cast Tempest in its total.
No new history schema or payment tracking is needed.
