# Second Chance and Elder Spawn: native upkeep compounds

Status: independently reviewed and admitted by the trigger agent; production 15 whole-card (two genuine cold) plus 62 related tests and scoped types/Ruff passed. Count ownership: trigger manifest. No shared algorithms or custom primitives.

Full actual canonicals and all official rulings were reviewed: `/tmp/counter53-compound-canonical.json`, `/tmp/counter53-compound-rulings.json` (Second Chance four; Elder Spawn none). Guardian of the Ages is included in those research artifacts but excluded from this leaf and count.

Second Chance splits the exact conjunction into sequential native sacrifice and extra-turn effects. Native upkeep/intervening-if life checks remain at trigger time and resolution. The extra turn is independent of whether the source can still be sacrificed, as official rulings require.

Elder Spawn uses the existing native optional Island-sacrifice payment. Its native failed-payment gate skips two follow-up instructions when paid: sacrifice the source, then deal six damage to its ability controller. The damage remains independent of whether the source can actually be sacrificed. The source's red-creature blocking restriction is already native and receives an actual attack/block negative proof.

Whole-card native tests pay actual mana costs, exercise trigger and resolution life thresholds, source departure and control change, Island payment and declining, sacrifice/damage ordering, native extra-turn scheduling and actual extra-turn phase advancement, red blocking, and two fresh-process pending-upkeep continuations. Related tests are `test_rules_wave8a_extra_turns.py` and `test_rules_optional_payment.py` (62 cases).

Hook proposal `/tmp/counter53-upkeep-hooks-proposal.patch`; final review manifest `/tmp/counter53-upkeep-review-manifest.json`.
