# Entry putter receipts (76; staged, not admitted)

Thelon's Chant and Tourach's Chant trigger for the player putting the matching land onto the battlefield. The Thelon ruling explicitly distinguishes that player from the resulting permanent's controller. Current entry moves batch all cards under the first actor, which loses mixed-player putter identities.

The isolated proposal adds an optional typed per-card Move.entry_putters map and Event.entry_putter receipt. It preserves the existing Event.actor used for discard causation, and supplies no receipt for manual table moves or legacy events. Existing entering-controller triggers are unchanged. A separate native put_battlefield fact freezes the actual receipt player for the Chants' optional full counter cost and damage.

Explicit each-player/owner instructions retain that authority through existing grammar rewrites. Native land plays, token creation, return instructions, simultaneous entry commits and discard-to-battlefield replacements carry the actual putter independently of destination controller. The Chants reuse native optional_payment PUT_COUNTER and damage effects, including zero-counter replacement versus prohibited placement.

Automatic linked-exile returns are deliberately held unknown: CR 610.3c establishes return under the owner's control, but neither that sentence nor the existing implementation establishes that the owner is instructed to perform the return. The proposal leaves their legacy actor/control unchanged and supplies no putter receipt. This authority question remains a review gate; no completion is claimed from the staged patch.

Canonical sources: /tmp/counter76-chants-canonical.json. Thelon ruling: /tmp/counter75-rulings-ff4ccf8d-7d3d-4a44-a9ab-6bc88e90d6a7.json. Tourach has no published rulings in the fetched response. Producer support canonical and every associated ruling response were read in /tmp/counter76-putter-support-canonical.json and /tmp/counter76-support-rulings-*.json.

The exact owned proposal is proposals/entry_putter_receipts76.patch. It was rebased onto current sibling work in /tmp/counter76-rebased-stage, preserving attachment snapshots, first-event history, kicked outcomes and targeting hooks. No production source has been installed.

## UNINSTALLED closeout

Root requested stopping new work for PR #19. No 76 production code or admissions were installed. Native tests and fixture were moved out of automatic test collection to proposals/entry_putter_receipts76_native_tests.py and proposals/entry_putter_receipts76_cards.json. Evidence summary: proposals/entry_putter_receipts76_UNINSTALLED.json. Closed isolated gates: 24 whole/coverage checks including 2 genuine cold processes, mypy 19 source files, Ruff 3 files; related 135 passed with 9 explicit scheduler-model fixture-order failures, and that model suite passes all 11 when isolated. The extra pending mixed-return cold test did not pass its initial stack-zone fixture assertion and is not claimed. The actual-putter authority question for automatic linked returns remains unresolved.
