# Block-only evasion exceptions

Canonical cards covered: Aether Web, Aetherflame Wall, Wall of Diffusion, Heartwood Dryad, Street Savvy, Staff of the Ages, and Dragon Hunter.

The pinned Comprehensive Rules (2026-09-25), 609.4, says that an “as though” permission treats the stated condition as true only for its stated purpose. Rule 609.4a allows compatible permissions to work together. These cards do not actually add shadow or reach to their blockers or remove landwalk from an attacker. Shadow's two blocking restrictions remain governed by 702.28b; other evasion restrictions remain cumulative under 509.1b.

Native static definitions carry three narrow blocker permissions and one global landwalk exception. The existing central block-legality function reads those rules together with current keywords and creature types. A blocker allowed to block shadow creatures can still make an ordinary block. If that blocker actually gains shadow, it retains ordinary permission to block a shadow attacker, and still cannot block a nonshadow attacker. Dragon Hunter's exception applies to current Dragons only. It grants no reach keyword.

Street Savvy modifies its attached creature's blocking permission. Staff of the Ages modifies blocking of current landwalk creatures for all players. Both cover the same native landwalk conditions as ordinary blocking, including basic, nonbasic, legendary, artifact, snow landwalk, and snow-specific basic landwalk. These permissions do not bypass flying, shadow, menace, protection, tapping restrictions, or other restrictions.

The native post-layer rule pass preserves the distinction between a printed self permission and an external direct rule. Lignify removes a printed exception from its creature source. It does not remove an Aura's direct blocking permission from the enchanted creature. An animated Staff whose abilities are removed stops supplying its global exception; removing that ability-loss effect restores it. Attached permissions follow the current attached object and its controller, rather than the Aura controller.

The canonical gameplay tests cover all seven cards, ordinary and shadow blocks, actual gained shadow, flying plus shadow, eleven landwalk variants, conditional reach and acquired Dragon type, source departure, host control changes, actual Lignify/Ensoul interactions, menace declarations, saved-game replay, and fresh-process declarations. No new serialized callback or client action was introduced.

Source rules: `data/rules/comprehensive_rules/2026-09-25/comprehensive_rules.txt`, CR 609.4, 609.4a, 702.9, 702.14, 702.28, and 509.1b. Canonical card metadata comes from the imported Oracle database snapshot dated 2026-10-18.
