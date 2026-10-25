# Stack extension103 — seven native definitions

Depends on closed stack-events102 packet (including retained Aura source_entry102 foundation). Incremental review.patch contains all five source changes; no registration-only patch. Stage /workspace/scratch/triggers103/backend.

Exact baseline PARTIAL promotions: Precursor Golem; Ink-Treader Nephilim; Bill Potts; Flamehold Grappler; Ancestral Communion; Social Snub; Banish into Fable.

22 unique native tests pass: native19.log includes all seven FULL gates and two genuine fresh-process cold proofs, extra2.log adds initial commander absence and artifact-enchantment double copy; origin-fixed1.log adds actual Yawgmoth’s Will casting Banish from graveyard without its hand-only trigger; final2-rerun.log rechecks original-controller eligibility and Precursor after final controller refinements. Every gameplay test roundtrips saved state and event history. Scoped mypy5/Ruff6 pass. Related activated_copy_family33 + wave6d_trigger_bodies74 + spell_copy_replacements23: 130 PASS.

Initial cast conditions are checked once before adding self-cast triggers, never installed as resolution conditions. Commander/creature removal via an actual responding Murder does not cancel already triggered copies. Grappler installs native delayed once/this-turn cast watch. Bill joins actual cast and activation branches under one native once-each-turn limit. Precursor copies are controlled by original casting player; Nephilim eligibility uses original spell controller, while copies belong to ability controller and may consequently have illegal targets. Native copy ordering, additional-copy replacement, saved LKI, target legality, ward, and spell resolution are reused. Empty destination sets do not produce replacement copies.

Banish tests current resolution artifact/enchantment conditions separately. One permanent of both types produces two copies. Its cast origin uses PaymentRecord.cast_from_player. Found and fixed baseline receipt provenance bug: ordinary casts previously derived this field from display label "the hand" and recorded None. _PostCast.origin_player103 now captures physical owner before moving to stack and persists through payment continuation. Old continuations without captured owner remain unknown; no guessed own-hand permission.

No blanket/classifier support changes. Uncopyable Room, mutate, and face-down cases retain native explicit manual boundaries inherited from copying kernel. Official ruling and canonical data files included.
