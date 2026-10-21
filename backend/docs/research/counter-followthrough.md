# Counter follow-through

Five canonical single-gap cards compose native counter result bindings, source
thresholds, captured payment quantities, and optional counter costs: Dawn of a
New Age, Decree of Silence, Lost Isle Calling, Blademane Baku, and Magmatic
Sprinter. No new runtime primitive, callback, or saved schema is required.

Dawn's actual removed count gates only its draw. Its later zero-counter check
runs independently, including when no counter could be removed. Native draw
replacement continuations retain the sacrifice and life-gain tail.

Decree places its depletion counter whether or not the opponent's spell can be
countered. Lost Isle's threshold and draw quantity use its original source's
counter snapshot after its exile cost; the threshold does not count cards
actually drawn. Blademane uses twice the counter quantity captured by its
single variable counter cost, including copies and borrowed abilities, rather
than reading counters remaining on the source. Unknown or ambiguous multiple
counter-removal costs remain unread. Magmatic Sprinter uses a native optional
full two-counter payment; one counter cannot partially pay it.

Canonical gameplay tests cover real entry/end-step/cast/scry/activation paths,
zero and threshold boundaries, uncounterable spells, replacements and draw
limits, source incarnation changes, true ability copies, native replay, and
fresh-process saved source snapshots and draw-replacement continuation.
