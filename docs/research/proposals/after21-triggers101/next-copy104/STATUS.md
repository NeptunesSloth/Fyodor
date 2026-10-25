# Next-copy104 — three native delayed copy watches

Depends on stack-events102 and stack-extension103. Incremental review.patch has all three source files. Stage /workspace/scratch/triggers104/backend.

Exact baseline PARTIAL promotions: Tzaangor Shaman; Sea Gate Stormcaller; Repeated Reverberation.

10 unique native tests pass (native10-initial.log: nine passed, one Shaman attack fixture failed; shaman-fixed1.log: corrected legal next-own-turn combat passes). Two genuine fresh-process cold proofs exercise Repeated either-watch and kicked Sea Gate watch with an actually countered original. Actual Shaman combat damage installs watch; actual Jace loyalty activation produces two copies while paying loyalty once. Kicked and nonkicked Sea Gate ignore a nonmatching mana-value-three spell and copy a subsequent legal spell twice/once. All native gameplay proofs roundtrip state and event history. Mypy3/Ruff4 pass. Related gate shared with103: activated_copy_family33 + wave6d_trigger_bodies74 + spell_copy_replacements23, 130 PASS.

Native delayed.wrap_when uses once/this-turn persistence, event-condition matching including cast/loyalty union, mana value selectors with stack X, retained payment kicked provenance and native copy_event_stack with n copies and optional independent new targets. Copy effects are constructed only at native watch creation so deferred references retain their correct event scope; no classifier weakening.

Official canonical records and all current official rulings included. Source unchanged after native gates; only Shaman fixture changed to obey summoning sickness.
