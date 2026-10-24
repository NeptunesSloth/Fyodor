# Checkpoint65 verified — continuing

Thirty card implementations pass native validation; **26 add Commander-legal FULL classifications**. Latest catalog: **29,914 FULL / 2,154 PARTIAL** among32,068 Commander-legal cards. Exact expected promotions, no prior FULL regressions or unexpected/missing names; metadata/name sets match. **452 of1,500 additional completions verified;1,048 remain.** FULL is coverage classification.

Patient Zero, Uthgardt Fury, Victory of the Pyrohammer and Case of the Market Melee have canonical commander_legal=not_legal. Their native implementations are tested but excluded from Commander promotion/target counts. The initial30-name expected catalog assertion caught this scope mistake; no source change or rerun was needed. The original implementation expected list and explicit corrected26-name catalog list/exclusions remain adjacent.

The same frozen912-module source passes143 native tests in295.32s,150 related regressions in47.70s,54 core checks, full mypy912 and configured Ruff. [Coverage](checkpoint65-coverage.json), [hashes](checkpoint65-source-hashes.json), [logs](checkpoint65-validation). No whole-suite claim.

Groups cover graveyard shuffle/mill with original departure snapshots; temporary creature types; bounded unless-pay decisions; attached destruction/current-host outcomes; attacked-player discounts; recipient/global count values; damage retention at cleanup; non-target control exchange cohorts and current type/controller choices. Functional shared hooks are included. Later17 candidates are separately frozen and uncounted.
