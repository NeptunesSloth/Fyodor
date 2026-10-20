# Optional repeated die-and-copy blocks

Delina, Wild Mage's current Oracle text and official rulings were checked at
[Scryfall](https://api.scryfall.com/cards/e87459aa-af8f-4bd2-a310-151353083a2e) and
[official rulings](https://api.scryfall.com/cards/e87459aa-af8f-4bd2-a310-151353083a2e/rulings).

The high-result row explicitly says **may** roll again. This Oracle update is
confirmed by an official ruling. Every successful high result makes its token
before its controller chooses whether to repeat (CR 608.2c/d, 706.2b). The low
result still creates one token and finishes. The target is chosen when the
attack trigger goes on the stack and checked before any roll (CR 603.3d, 608.2b).

Each new roll must use the shared die primitive. Wyll, Blade of Frontiers,
Pixie Guide, and Barbarian Class replace every roll independently; ignored
results never happened (CR 706.6). A Pixie Guide token created by an earlier
iteration therefore adds another advantage die on a later iteration. Roll
results are recorded in table actions, so replay never rolls again.

The copy exception removes legendary and grants the token its own end-of-combat
exile ability; these are copiable exceptions (CR 707.9). It is not a delayed
exile attached only to the first token. Copies enter tapped and attacking, and
the controller chooses each defender independently of Delina's defender. They
were not declared attackers and do not trigger attack abilities (CR 508.4).
The two latter points are explicit official rulings.

The prepared helper uses ordinary roll and token-copy primitives, then an
optional relative rewind of that three-effect block. Existing token replacement,
entry/attack decisions and their saved continuations remain responsible for
their own choices. A relative rewind avoids expanding saved context on every
iteration and keeps the original target fixed throughout the resolving ability.

A shared event-batch correction seals the completed roll facts before the next
instruction. Without that boundary, a Wyll token created after a roll could
incorrectly observe the earlier roll. The normal rules-state bookkeeping closes
the batch; the compiled intent's final `rules_sync` records it without adding a
user-facing log or another full state snapshot. Tests check that an original
Wyll observes both rolls, its first copy observes only the later roll, and its
second copy observes neither earlier roll.
