# Ruthless Technomancer — implemented native minimum X

Current Oracle text retrieved from Scryfall on 2026-10-19. Its activated cost
already parses into native MANA and X-sized SACRIFICE components, and its
reanimation body already produces an ordinary targeted return with a power
comparison against announced X. The remaining blocker is scripts.define's
trailing "X can't be 0" support: it accepts only a mana cost containing {X},
despite native AbilityCost.x_chosen supporting announced nonmana X.

Planned bounded change: accept a native announced X component when extracting
the minimum-X constraint, preserving native activation and cost selection.
The minimum is checked before costs are paid. Any applicable target must be
announced before paying and remain legal at resolution.

Canonical fixture nonmana_activation_x_min_cards.json prepared. Planned cases:
X=0 rejection without mana/sacrifices; exact one/two artifacts paid including
tokens; creature target power/ownership; target leaving before resolution;
cost-prompt cancellation; source leaving after activation; copy retaining X;
history/save-load through the sacrifice choice. No imported edits during the
eighth-checkpoint freeze.

Implemented: scripts minimum-X extraction now accepts native AbilityCost.x_chosen,
as well as literal mana {X}. Nine canonical cases pass, including explicit zero
rejection against a legal zero-power target, exact two-artifact payment, atomic
rejection of insufficient sacrifice selections, saved native cost prompts, source
removal, and stale target resolution. Broader variable-X regressions are running.
