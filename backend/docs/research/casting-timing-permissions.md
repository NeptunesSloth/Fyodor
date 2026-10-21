# Conditional and next-spell timing permissions

Canonical Oracle fixtures and current official rulings are staged in the casting-timing37 research files. This batch implements fifteen cards through native casting permissions and cost payment rather than bypassing the announcement pipeline.

Next matching spell permissions retain their resolution-time cast-count boundary. Matching spells consume every applicable permission even at ordinary main-phase timing; nonmatching spells and uncast stack copies do not. Independently granted zone access remains necessary. Suspend uses the same legal-cast timing test; land play remains a separate action.

Conditional timing checks use an immutable prospective view for graveyard casting, excluding the announced card from that graveyard. The timing decision is captured before mana activation/payment, so sacrificing the qualifying Ferocious creature while paying does not invalidate the locked announcement.

Savage Summoning binds each matching entry-counter effect to the exact actual cast object's incarnation. Native stack-to-battlefield effect remapping carries the effect to its permanent; ordinary copied spells do not inherit these noncopiable counter effects. Arlinn instead creates a dynamic, original-controller, until-next-turn entry rule that includes creature tokens and checks the actual entering characteristics. Native entry counter replacement/prevention applies afterward. Hatchling grants the exact actual cast Dinosaur a native triggered ability and retains the independent turn-long timing permission.

Primal Prayers uses an ordinary selected alternative cost with native energy payment. The alternative grants timing only when actually selected, grants no access to unauthorized zones, fixes announced X to zero, and leaves mandatory additional costs payable. Optional Behold, tap-three-flyers, and teamwork timing permissions use native selected additional-cost receipts and native cost feasibility/payment. Merely having a payable cost available does not authorize an unselected off-time announcement.

All new model fields have backward-compatible defaults. Cold-process tests construct native views before resuming, then verify actual effects, save/load equality, and replay equality.

The decisive conditional timing regression uses actual Skirk Prospector mana activation: Dragon Grip is legally announced while a Giant Growth makes the Prospector 4/4, then that creature is sacrificed during the native self-payment window. The existing payment resume now carries a server-only original object identifier, restored only transiently in `_rerun`; the original announcement retains its general timing authorization while all ordinary zone, priority, prohibition and explicit casting-restriction checks remain intact. A new action or new incarnation cannot inherit the authorization. Cancellation retains no lock, and legacy resumes with no field keep their existing behavior.

Verification: 43 distinct canonical/gameplay/edge cases passed across the focused run and corrected exact reruns. Five tests resume in fresh processes, including the live mana-payment boundary. Additional native timing, optional-cost, self-payment and flash-Aura regressions are recorded separately in the batch verification log.
