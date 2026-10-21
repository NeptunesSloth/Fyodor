# Regeneration shield provenance

Matopi Golem, Skeleton Scavengers, Soldevi Sentry, and Debt of Loyalty need individual shield identity (CR 614.8, 616.1). Aggregate `regen_shields` counts remain compatible with old saves; typed `RegenerationShield` records identify only shields carrying additional effects. Anonymous shields retain their existing count-only representation. Cleanup clears both representations.

When a rider-bearing shield competes with another replacement, the permanent's controller selects the actual shield before the destruction batch mutates anything. Unused shields remain available for subsequent destruction. Exact object references prevent blinking or reanimating a permanent from inheriting its previous shields or pending counter effects.

Debt of Loyalty has an immediate replacement rider: regeneration taps/removes combat/damage, then its caster gains control permanently. It creates no control effect when initially cast. The official Scryfall rulings dated 2008-04-01 explicitly distinguish the Debt shield from unrelated shields and confirm this timing. The other three cards explicitly say 'When it regenerates this way'; they queue ordinary delayed triggered abilities, whose controllers, source identities, protected objects and chosen opponent are captured when their shield is created. Counter placement and optional draw resolution use existing native effects and replacement/payment continuations.

Skeleton Scavengers' printed generic cost is represented internally as a defined X equal to its current +1/+1 counters, reusing the native announcement/locked-payment path and cost reductions. It is not a freely chosen X.

Verification: 27 canonical gameplay cases plus 125 existing automatic-regeneration, finite-regeneration, Nimbus, variable-counter-cost, and replacement-choke-point cases passed. New cases include both fresh-process destruction-effect and lethal-SBA decisions, save/replay compatibility, multiple simultaneous objects, selected versus anonymous shields, delayed stack timing, source departure/blink, borrowing, shield expiry, indestructibility, inability to regenerate, armor choice, and counter replacement. Spiny Starfish's historical regeneration count is a separate remaining card rule and is not claimed here.

The variable-counter-cost regression module had three assertions reading only the legacy scalar mana dictionary. Five mana reads now use the established aggregate `mana_pool` helper; their expected quantities are unchanged. All 30 cases then passed.
