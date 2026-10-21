# Spell mana floors: Trinisphere

Research date: 2026-10-19. Rules source: the stored Comprehensive Rules dated
2026-09-25, `data/rules/comprehensive_rules/2026-09-25/comprehensive_rules.txt`.

## Oracle text and official rulings

Trinisphere:

> As long as this artifact is untapped, each spell that would cost less than
> three mana to cast costs three mana to cast. (Additional mana in the cost may
> be paid with any color of mana or colorless mana. For example, a spell that
> would cost {1}{B} to cast costs {2}{B} to cast instead.)

The actual default printing's [Scryfall rulings endpoint](https://api.scryfall.com/cards/316caa4e-a53a-460b-978c-5f0fba7bc549/rulings)
was fetched with `curl`; the response is retained during this task at
`/tmp/fyodor-trinisphere-rulings.json`. It contains these two official rulings,
both dated 2020-08-07:

> To determine the total cost of a spell, start with the mana cost or alternative
> cost you're paying, add any cost increases, then apply any cost reductions.
> Finally, apply Trinisphere's effect if the mana component of the spell's cost
> is less than three mana. The mana value of the spell remains unchanged, no
> matter what the total cost to cast it was.

> If Trinisphere leaves the battlefield or becomes tapped or untapped as a cost
> to cast a spell, this cost is paid after you've locked in the total cost.

## Rules and ordering

CR 601.2b requires a player to announce the nonhybrid equivalent of hybrid mana
symbols and the choice of mana or two life for each Phyrexian symbol. These
choices precede cost determination. CR 107.4e-f defines the alternatives;
`{2/B}` can represent two generic mana or one black mana, and life paid for a
Phyrexian symbol does not contribute mana to Trinisphere's minimum.

CR 601.2f first combines the mana cost or alternative cost, additional costs,
increases, and reductions. Effects directly affecting the total cost apply
afterward, then the result becomes locked. Trinisphere is such a final effect.
Offering reductions (CR 702.48c), and optional reductions limited to particular
colored mana, therefore precede the floor. A spending permission does not erase
colored symbols before these reductions: CR 609.4b changes how mana can pay the
cost, not the cost itself.

CR 118.9d applies additional costs, increases, and reductions to alternative
costs too. Casting without paying a spell's mana cost can therefore still
require three generic mana. A resolving free cast follows the same ordering
as an ordinary cast.

After reductions, the floor adds generic mana until the mana component reaches
three; it preserves colored and specifically colorless requirements. For
example, Gitaxian Probe costs either `{2}{U}` or `{3}` plus two life. Dismember
can cost `{1}{B}{B}`, `{2}{B}` plus two life, or `{3}` plus four life.

CR 601.2g-h governs mana abilities and payment after the cost is locked.
Convoke (702.51a), delve (702.66a), and improvise (702.126a) pay components of
the total cost rather than reducing that cost. They may pay mana added by the
floor, and the floor is not applied again to the unpaid remainder. Assist
(702.132a) similarly lets another player pay the generic component of the
already determined total; the floor does not apply separately to the caster's
share. K'rrik's permission to pay two life rather than black mana is a payment
substitution, distinct from announcing a printed Phyrexian symbol: the black
mana requirement still counts when applying the floor.

Whether a relevant Trinisphere is untapped is checked when the total is
determined. Tapping or sacrificing it while activating a mana ability during
payment cannot lower the locked cost. Multiple untapped copies impose the same
minimum rather than adding separate surcharges. Phasing and loss of its static
ability affect whether its floor is active. Activated abilities are outside
this effect's scope.

## Implementation and verification

`spell_cost_stages.PreparedCost` preserves the cost before reductions and
resolves concrete symbol announcements before evaluating reductions.
`spell_symbol_choices` stores a private, cancellable announcement in the cast
intent. `spell_mana_floor` reads active static abilities and applies the final
minimum. Normal casts, resolving free casts, and castability hints use these
stages. Existing locked-payment continuations preserve the determined cost.

The focused gameplay tests cover the examples above, explicit and saved symbol
choices, cancellation and replay/save-load, low and exactly sufficient life,
free casting through Omniscience and Electrodominance, flashback reduction and
life costs, offering, assist, convoke, improvise, delve, K'rrik, a colored-only
reduction with Oath of Nissa's spending permission, ability exclusion, and
sacrificing Trinisphere to Krark-Clan Ironworks while paying. Additional edge
tests cover multiple copies, actual phasing, and loss/restoration of the static
ability.
