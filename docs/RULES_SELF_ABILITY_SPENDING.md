# Spending permissions for one permanent's abilities

Manascape Refractor and Sharkey, Tyrant of the Shire use a source-specific `spend_as`
static. It applies to that permanent's own activated abilities, including abilities borrowed
from lands. It grants no permission to pay other permanents' activation costs or spell costs.

The shared mana-cost machinery preserves the distinction in CR 609.4b: “any color” can
pay colored symbols with other mana but cannot replace a {C} requirement; “any type” can
also pay {C} with colored mana. Costs such as tapping remain necessary. The permission
does not give Sharkey mana abilities that its borrowing text excludes.

Nine focused tests (included in 73 selected passing regressions) cover colored land
ability costs, {C} requirements, unrelated spells and abilities, borrowed mana ability tap
costs, and replay/save-load. Ruff and mypy passed.
