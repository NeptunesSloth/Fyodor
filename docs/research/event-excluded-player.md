# A player target other than the player in the triggering event

The Lord of Pain: “Whenever a player casts their first spell each turn, choose another target player. The Lord of Pain deals damage equal to that spell's mana value to the chosen player.” Another excludes the caster named by the triggering event. If an opponent cast the spell, the Lord's controller may target themself. If the Lord's controller cast it, they cannot target themself.

Existing cast-event grammar already supports each player's first spell per turn. It counts earlier spells even before the Lord entered. A spell copy is not cast. Existing `mana_value(event)` uses the cast spell while it remains on the stack, or its last-known characteristics if it left. Stack snapshots retain X and reconstruct StackInfo, so X contributes correctly under CR 202.3e. No new mana-value or cast-count history field is needed.

Implemented target representation: `Selector(player='any', player_exclude='that_player')`. `triggers.bind_that_player` binds the exclusion alongside existing controller/zone-owner bindings to `player:<caster id>` before target announcement. `matches_player` rejects the bound player and fails closed for an unresolved exclusion; the ordinary player-targeting path still checks player hexproof/protection. The bound exclusion remains on the stack entry for resolution and copied-ability target changes.

The grammar for choosing another target player and subsequently damaging the chosen player lowers to the ordinary target damage effect with this selector. This avoids interpreting “another” as “opponent of the ability's controller.” No separate runtime damage effect is needed.

Canonical fixtures: `event_excluded_player_cards.json`, including the Lord, Blaze (X), Ornithopter (mana value zero), Leyline of Sanctity (player shields), Counterspell and Stifle.

Verified gameplay cases: opponent caster may target the Lord controller but not caster; self caster excludes self; each player gets their own first spell each turn and later spells do not trigger; spells cast before Lord entered count; next turn resets; zero-mana-value spell; X on stack and after Counterspell/LKI; source leaves/changes controller; player shields apply on resolution; copied triggers keep the original caster exclusion when choosing new targets; the existing life prohibition affects opponents only; save/replay during target choice and resolution.

All 195 selected Lord/selector/player-relative/history/spell-copy tests passed. Ruff and scoped diff checks passed.
