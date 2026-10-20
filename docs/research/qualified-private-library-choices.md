# Qualified private library choices

Batch 36 adds native choices for Conjurer's Mantle, Overgrown Pest, Radagast the Brown, and Follow the Lumarets. Companion leaves implement the other nine cards listed in `/tmp/fyodor-qualified-look36-cards.json`.

`qualified_look_outcomes` queues existing exact-object look, optional selected-card reveal/hand placement, and random-bottom continuations. Unselected cards stay private. Mantle accepts any card with a shared creature type, including a noncreature Kindred card, using the attacking creature's current or last battlefield characteristics. Radagast counts the entering creature's mana value and excludes the union of creature types currently controlled. Its trigger includes a token copy of itself while ignoring other token creatures. Lumarets reads life gained this turn, allowing two cards even when damage has cancelled the life total increase.

Pest's new selector checks physical double-faced layouts, including meld, rather than image availability. Transform and modal cards remain eligible when imported without downloaded images; split and Adventure cards remain ineligible. The outer library zone is explicit for the native OR selector.

Validation: 16 actual gameplay cases in `backend/tests/test_rules_qualified_look_outcomes.py`, including four fresh-process resumes, actual equipped attacks and Murder before the Mantle trigger resolves, Kindred selection, all three physical double-faced kinds, token Radagast, optional decline, and gained-life versus net-life history. Each completed game checks replay or saved-state equivalence. Related selector and reveal regressions run separately.
