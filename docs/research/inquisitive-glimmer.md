# Inquisitive Glimmer

Unlocking a door is a special action, not casting a spell or activating an ability. Its generic reduction therefore has a distinct static marker and is read only by the Room unlock-cost calculation. The native static table supplies only currently functioning abilities; the reduction sums matching sources controlled by the payer. It removes up to that much generic mana and never changes colored symbols or produces a negative generic cost.

The calculated cost then passes through the existing Room payment and serializable terminal continuation unchanged. This preserves the original Room object identifier, native unlock/fully-unlocked designations, and triggers. The separate enchantment-spell reduction still applies when a Room half is cast. Enchantment-spell and activated-ability modifiers do not independently reduce unlock costs.

Canonical tests cover zero through three Glimmers, colored-mana floor, live source control and departure, Dress Down ability removal, nonleakage from Starfield Mystic/Training Grounds, actual reduced Room casting followed by a separately reduced unlock, and insufficient-payment atomicity. Two native continuation cases inject a structured draw rider below classification on an otherwise legal synthetic mana source; the paused reduced unlock resumes once after declining or accepting Abundance. The source is explicitly synthetic and does not assert an invalid draw-bearing Oracle mana ability.

Existing unlock special actions do not open an ask/cancel payment prompt merely because the internal payment preference is `ask`; this change preserves that existing behavior. Insufficient payment rolls back without paying mana or granting a designation.

Validation: 13 focused gameplay/save/replay cases and 28 existing Room and external-payment regressions passed together (41 unique tests). Ruff passed. Log: `/tmp/fyodor-glimmer-combined.log`.
