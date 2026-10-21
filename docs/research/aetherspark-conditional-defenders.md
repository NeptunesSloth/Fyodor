# The Aetherspark: conditional attack prohibition and attached damage watcher

The canonical Oracle static sentence is now supported. Its loyalty activations
already parse: +1 attaches to up to one controlled target creature and adds a
+1/+1 counter; −5 draws two; −10 adds ten mana of one color.

The conditional sentence is a normal self static: while attached to a creature,
it cannot be attacked and gains an equipped-host combat-damage trigger during
its controller’s turn. Existing static conditions, quoted grants, attached damage
watchers, trigger turn qualifiers, and damage amounts supply its behavior.
The parser addition is the reusable rule phrase “can’t be attacked”.

Combat.attack_targets now derives potential planeswalker/battle defenders,
excludes cant_be_attacked, and validates a submitted declaration against current
legal defenders. Ordinary attack legality and attack requirements use the same
filtered defender set.
This changes declaration legality only: an existing attack continues when the
planeswalker becomes attached. The actual Scryfall ruling expressly confirms it.
Effects that put a creature onto the battlefield attacking do not declare it as
an attacker and must retain their separate legality rules (CR 508.4).

The attached-to-creature static condition currently uses a reconfigure shortcut:
a live battlefield host, rather than checking its creature type. Equipment SBA
normally makes this equivalent, but damage/animation inside a resolution must
be checked before broadening or changing that shared condition.

Seventeen passing canonical gameplay cases cover attached/unattached declaration options,
rejected forbidden defenders, attachment after an already legal declaration,
combat damage to creatures and players, double strike, zero damage/prevention,
noncombat exclusion, host death with pending loyalty trigger, source blink,
controller versus host ownership, and loyalty activations. Tests replay
history and JSON save-load. Fixtures preserve canonical metadata and faces.

Rulings source: https://api.scryfall.com/cards/05690d52-06c4-40b1-8360-380418a83250/rulings

## Implemented scope and timing limitation

The rule phrase and derived defender filter are implemented, including a fresh
check when submitting a previously offered declaration. A self-granted quoted
ability now resolves its own granter placeholder as self; ordinary grants to
another object retain their original granter binding.

Completed combat damage now collects event triggers before subsequent state-based
actions can detach equipment and remove a conditional source ability. This only
queues pending triggers: target choices, ordering, and placement still wait until
SBAs finish. The lethal-host canonical Aetherspark test demonstrated the prior
loss and now passes. All combat damage entry routes share this boundary.

This is a combat-boundary correction, not a global event-time snapshot system.
Noncombat damage and other resolving effects still normally collect after their
subsequent SBAs; an analogous conditional ability on a surviving object could
therefore disappear before collection. No new canonical noncombat example was
claimed fixed by this change. A broader event-time watcher/snapshot design is a
separate follow-up, especially for effects that continue after damage.
