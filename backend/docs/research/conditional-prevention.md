# Conditional prevention (batch 38)

Fifteen canonical cards use native damage replacements and prevention records:
Ajani Steadfast, Shield of the Avatar, Plated Pegasus, Well-Laid Plans, Bronze
Horse, Callous Giant, Protective Sphere, Mourner's Shield, Guard Dogs, Circle of
Protection: Shadow, Orim's Touch, Elvish Healer, Pollen Remedy, Balduvian Hydra,
and Spore Cloud.

The shared leaf adds restricted source predicates and reads dynamic amounts in
the existing damage-replacement loop. The Avatar counts the Equipment's
controller's current creatures. Pegasus checks a spell rather than an ability.
Bronze Horse checks both the spell's exact object targets and another creature
controlled by the Horse's controller. Callous Giant checks the damage amount at
the replacement's application, preserving the affected player's replacement
ordering. Ajani's actual command-zone emblem remains active after its source
leaves.

Protective Sphere reads the activated ability's actual payment record, excluding
colorless mana and mana not spent on that activation. Mourner's Shield stores
the original linked-exile context, not a frozen list of colors: 609.7b checks the
chosen source's relational property when it would deal damage; 607.2a and 400.7
limit the linked card to the original object still in exile. If that object
leaves exile, the prevention no longer applies. A new incarnation of the Shield
cannot replace the old record's link. The initial choice is restricted by the
linked card's colors when the ability resolves. No card-specific official ruling
was available to override these general rules.

Guard Dogs instead follows its published ruling: whether the target creature
shares a color with the chosen permanent is checked when the ability resolves.
The resulting combat-prevention record does not recheck this comparison. The
Healer's green-creature bonus is similarly read on resolution. The Shadow
Circle's source qualification is checked again at damage time (609.7b), using
current or last-known full keywords. Orim's Touch and Pollen Remedy read actual
kicker receipts; copies retain kicked status. Remedy's three/six points are
allocated at announcement, allow explicit zero targets (107.1c), and do not
redistribute an illegal target's share. Hydra removes a real counter as a cost.
Spore Cloud snapshots attacking/blocking object identities on resolution and
uses the existing controller-relative next-untap records.

Fresh-process saved-state tests exercise the command emblem, the paid-color
source-choice prompt, a linked-exile record, and partially consumed divided
prevention. Actual gameplay tests cover each of the fifteen cards, replacement
order, copies, illegal targets, zero-target kicker casts, and source qualification.

## Explicit exclusions

Cover of Winter is not admitted: its official ruling requires the controller to
divide a source's prevention budget among that source's simultaneous recipients.
Applying the budget independently to each recipient would overprevent damage.
Prevention-trigger/reflexive rider cards also remain outside this scope until
all their replacement-triggered effects have real resumable continuations.
