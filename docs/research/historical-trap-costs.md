# Historical Trap alternative costs

Whiplash Trap and Lavaball Trap require one opponent to have had two qualifying
permanents enter under their control this turn. Baloth Cage Trap needs one artifact
entry. Runeflare Trap needs one opponent to have drawn three cards, and Needlebite
Trap needs an opponent to have gained life. Their effects and native alternative
cost payment already use existing rules machinery.

The new exact entry-history grammar carries a `one_opponent` marker. Its check
counts each live opponent separately, using the existing arrival-controller and
as-entered type snapshots. Two opponents with one entry each cannot collectively
meet a threshold of two. A later control change does not rewrite who controlled
the entry; leaving the battlefield does not erase the entry. Existing conditions
that aggregate opponents' entries retain their previous meaning. The original
caster context is preserved when matching the selector.

Draws and life gain already have per-player ledgers. The draw parser now accepts
the Oracle past tense “drew”; the gained-life condition can inspect opponents as
existing draw and lost-life conditions do. No new saved-state fields, callbacks,
or casting paths are introduced.

Canonical gameplay tests exercise all five paid costs and real effects, split
versus single-recipient thresholds, turn reset, native artifact casting,
Divination, Healing Salve, creature departure, Act of Treason, land play and
Rampant Growth, atomic rejection, replay, cold resume, and countering a paid
spell.

Permafrost Trap additionally records the entering permanent's derived colors
alongside its type snapshot. Later recoloring, control changes, and departure do
not rewrite that fact. An older saved entry with no color snapshot cannot prove
a colored-entry condition; current color is never substituted for missing
history. Uncolored historical conditions remain usable for those older entries.
Canonical Permafrost tests verify the actual discounted spell and skipped untap,
both directions of recoloring, departure, native control transfer, JSON reload,
and the conservative legacy behavior.
