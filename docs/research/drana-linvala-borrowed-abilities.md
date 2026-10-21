# Borrowing activated abilities and spending permissions

Drana and Linvala’s combined static now grants the actual activated abilities of
creatures its controller’s opponents control, with an ability-specific permission
to spend mana as though it were any color. The restriction against opponents’
creature activations was already implemented and includes mana abilities.

The shared borrowing engine now derives full lender characteristics, including
static and resolved grants and ability loss. It constructs a read-only layer-six
grant graph, resolves dependencies before dependents, and applies effects within
dependency cycles once in timestamp order (CR 613.8). Traversal is iterative;
there is no recursion-depth limit or thirty-two-ability truncation. Canonical
granting paths distinguish recursive abilities. Existing direct ability indices
are retained where safe; other indices occupy a separate JavaScript-safe integer
range, with deterministic collision resolution. No read-only request mutates a
saved identity registry.

Spending permission belongs to the particular borrowing static, not every ability
on the borrower. A separately granted Dragon Mantle ability retains its colored
cost, and another creature borrowing Drana’s activated abilities does not inherit
the separate spending permission. Colored mana-ability activation costs use the
same provenance check. A pre-existing Phyrexian-cost restriction was corrected:
any-color/type permissions preserve the choice between any mana and two life,
including mana payment when life payments are prohibited. Actual colorless and
monocolored-hybrid costs retain their restrictions.

Gameplay tests cover Cudgel Troll self-reference, Llanowar Elves activation
restriction, Paradise Mantle grants and departure, Darksteel Mutation ability
loss, recursive Experiment Kraj grants and cycles, borrowed Devoted Druid counter
costs, source departure while an activation is on the stack, ownership/controller
changes, thirty-four borrowed abilities, forced index collisions, and facedown
creatures lending only their visible granted abilities. Moltensteel Dragon tests
exercise Phyrexian mana/life payments, life bans, cancellation, and replay/save.
Borrowing/inheritance regressions passed 95 tests; the subsequent Phyrexian/cost
regression run passed 82, with focused final refinements verified separately.

## Supported modal and linked inherited abilities

The continuation removes the blanket modal, named-token, and within-ability
choice refusals. A virtual modal header/mode view reuses the native grammar;
mode memory uses the borrower object and inherited ability identity. Cankerbloom,
Kargan Intimidator, and Breya execute their native modes with the borrower paying
the costs. Separate instances retain separate mode memory, and recursive lending
preserves the modal frame. Sliversmith creates its named token normally, and Oona
chooses its color during the borrowed activation’s resolution.

Linked exile records use a separate provenance namespace rather than changing
source_object. Abilities acquired together from the same original linked pair
share a newly initialized record; unrelated borrowed pairs, a donor’s previous
exiles, and the borrower’s unrelated native imprint remain isolated. Elite
Arcanist therefore has no linked card and a defined X of zero when only its
activation is inherited. Sisters of Stone Death’s two inherited activations can
exile and return a creature through their own new record. Defined activation X,
resolution-time values, targeted link selectors, and linked mana production use
the appropriate namespace. Native nonborrowed exile links are unchanged.

Canonical gameplay tests cover donor/borrower departure while an activation is
on the stack, new object identities after either blinks, a borrower retaining an
unrelated native imprint, and scoped target selection. The combined continuation
regression run passed 180 tests across native modal, inherited, Drana, and defined
activation-X mechanics. Native unsupported modal forms and unresolved prior
choices/noted values still retain explicit manual handling; this change does not
synthesize missing native card implementations or copy a donor’s prior choices.
