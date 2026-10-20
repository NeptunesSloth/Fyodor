# Mana-color restrictions on generic X

Scope: Crypt Rats, Consume Spirit, Crimson Hellkite, and Atalya, Samite Master. Drain Life and Soul Burn also have this wording, but their separate capped-life instructions remain outside this change; Soul Burn additionally requires attribution of actual black mana specifically to X.

## Rules and research

The pinned 2026-09-25 Comprehensive Rules retain announced X on the stack (107.3a), allow generic cost reductions to reduce generic components (118.7a), and determine the total cost before paying it (601.2f/h). “Spend only black mana on X” restricts spending; it does not turn X into black mana symbols. K'rrik therefore cannot replace that generic X with life. A genuine alternative/free cast without X must choose X=0 (107.3b).

Generic reductions can apply to X before other generic components. A historical MTG-L answer by Jeff Jordan, quoted at <https://www.mtgsalvation.com/forums/magic-fundamentals/magic-rulings/magic-rulings-archives/271113-consume-spirit-and-cost-reduction>, explicitly identifies the payer's choice among generic-origin components. The first four cards have no effect depending on which mana was assigned to X, so applying reductions to restricted X first accepts every payment available under the more restrictive allocations. Generic taxes remain unrestricted. Training Grounds' own minimum limits the actual reduction: for Crypt Rats X=1 or X=2, the final one mana is still part of X and must be black. A separate Trinisphere floor can add unrelated generic mana after X has been reduced away.

“As though” spending permissions can satisfy the restriction while actual mana provenance retains its real types (609.4b). The Mycosynth Lattice/Consume Spirit interaction is also discussed at <https://www.mtgsalvation.com/forums/magic-fundamentals/magic-rulings/magic-rulings-archives/295489-questions-on-mycosynth-lattice>. This differs from treating X as actual black symbols for K'rrik.

## Implementation

The declared ManaCost and PaymentRecord total-cost string stay generic. A serialized payment-purpose constraint records the allowed colors, the remaining restricted-X amount, and the original generic total. At the solver boundary, after actual black-symbol life substitution, restricted generic requirements receive native color alternatives plus the existing generic-helper pseudo-unit. Thus convoke, improvise, and delve can pay generic X without spending mana, while real mana must satisfy its restriction. Actual spent-mana provenance is unchanged. The pseudo-unit never appears in the player's payment display.

Spell reductions use the prepared-cost stage's actual gross generic reduction, not a net tax-minus-discount estimate. Offering's later generic reduction is included. Activated costs capture their native actual reduction after their own minimum. Selected modal text supplies Atalya's restriction, rather than unrelated abilities or only the modal header. Native paid-card-copy casting and its X-value menu use the same constraints.

Payment prompts serialize the constraint alongside the locked generic cost. A zero restriction remains an explicit saved value: sacrificing a cost reducer for mana while paying cannot reconstruct a restriction that was already reduced away. Cancellation leaves costs unpaid. Omitted mana-color choices consult the pending cost before the outer payment decision is cleared, so a U/B source can choose black when X requires it. Native payment stages retain their existing single terminal dispatch.

## Validation

27 canonical gameplay and edge cases passed, including a genuinely fresh Python-process resume of a saved restricted payment. Coverage includes both Atalya modes, announced X and stack mana value, ordinary generic mana, gross reductions plus taxes, Training Grounds' own minimum versus a separate Trinisphere floor, K'rrik, Mycosynth Lattice actual mana provenance, free X=0, generic convoke, actual paid copies from The Tale of Tamiyo, cancellation, color selection, and Krark-Clan Ironworks sacrificing Jet Medallion during a locked zero-restricted-X payment.

67 existing payment, cost-contribution, mana-floor, and cold-load regressions also passed (94 unique tests total). One old mana-floor assertion was updated to count the aggregate pool including source-tracked mana; its Sol Ring mana had correctly remained available. Logs: `/tmp/fyodor-colored-x-combined.log`, `/tmp/fyodor-colored-x-floor-regression.log`, `/tmp/fyodor-colored-x-cold.log`. Ruff passed.
