# Rootcoil Creeper and Seize the Storm collateral validation

Canonical current Oracle fixtures validate both complete cards. Rootcoil's unrestricted and graveyard-restricted mana abilities are separate: the latter cannot pay a hand spell but can pay the native flashback alternative. Its third activated ability exiles the source as a cost, accepts only an owned exiled card with flashback, and returns that card to its owner's hand. A fresh process resumes the native target announcement and pays only once.

Seize creates an Elemental with trample and a live power/toughness defining ability. Tests count only the current controller's instant/sorcery cards in their graveyard and flashback cards they own in exile; opponent-owned exile cards and non-flashback creatures do not count. The resolving Seize is counted after it reaches the graveyard. Recasting it with flashback temporarily removes that count: a sole 1/1 token dies to state-based actions while the spell is on the stack; the new token survives as 1/1 once the spell enters exile. Changing token control changes whose graveyard and owned exile cards the defining ability reads. Another fresh process proves the defining ability changes with a subsequent zone move.

No application changes were required for these two collateral promotions.
