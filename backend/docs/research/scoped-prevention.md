# Timed prevention scopes

Eighteen canonical cards use the native damage replacement planner: Kiora, the Crashing
Wave; Dovin, Hand of Control; Energy Arc; Terrifying Presence; Moonmist; Inspire Awe;
Feint; Sewers of Estark; Wellgabber Apothecary; Blinding Powder; Cautery Sliver;
Decorated Griffin; Barbed Wire; Healing Grace; Dazzling Reflection; Ajani's Aid;
Shieldmage Elder; and Forcefield.

Object-specific shields bind original object identities. Kiora and Dovin protect damage
both to and by the selected permanent until the original controller's next turn starts,
using the shared modern/legacy replacement lifetime helper. The shield survives its
planeswalker source leaving. Energy Arc uses the same native both-side scope for legal
surviving targets, including an untapped creature or zero targets.

Rules-modifying class restrictions remain dynamic (CR611.2c). Moonmist checks Werewolf
and Wolf types when damage would be dealt, and Inspire Awe checks current enchantment
and enchanted status then. Their official WotC rulings expressly include later entrants
and changed characteristics. Their separate transform and scry instructions run during
resolution. Feint and Sewers retain their original target identity while checking its
current blocking relationships; their tap instruction is independent of this scope.

Scoped next-N budgets use the existing prevention store, replacement simulation, shield
commit and cleanup, with source/recipient/combat matching before subtraction. A budget
counts damage, not events or recipients, and cannot be duplicated across simultaneous
recipients. The affected recipient chooses which simultaneous eligible source's damage
to prevent (CR615.7), using the native saved ShieldAsk decision. Different affected
recipients retain native APNAP handling (CR616.1); no new global source-controller choice
is introduced. Barbed Wire's printed upkeep trigger has one recipient, and its actual
activation/upkeep case proves that behavior. A separate native-planner unit verifies the
generic source-only budget is shared across a multi-recipient batch. Unpreventable damage
does not spend a budget. Forcefield reuses native prevent_all_but and never shields a
blocked trampler.

Creature-of-choice instructions choose creature permanents without targeting (CR109.2).
Healing Grace instead uses the existing full source-choice set (CR609.7), then gains life
immediately. Shieldmage Elder's target spell retains the existing permanent-spell source
alias when that spell becomes a permanent. Powder's granted ability pays the actual native
UNATTACH granter cost; recognizing that leading cost verb is the only Oracle classifier
extension. Cautery's target union allows players, planeswalkers and Sliver creatures,
without permitting unrelated creatures.

Canonical tests cover actual casts, loyalty and granted activation costs, combat and
noncombat damage, replacement choices, source/recipient identity, dynamic exceptions,
source departure, source-spell entry mapping, shared and partially spent budgets, and
fresh-process saved decisions and lifetime records. Telekinesis remains outside this
family because its next-two-untap-steps instruction requires a separate foundation.
