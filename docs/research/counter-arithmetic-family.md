# Counter arithmetic

Canonical Oracle fixtures cover Sarulf, Realm Eater; Lightning Coils; Lily
Bowen, Raging Grandma; Sage of Hours; and Nuclear Fallout.

These clauses compose existing native counter removal, replacement-aware token
creation, life gain, exile, and extra-turn effects. Removal results use actual
removed counts. Lily's branch freezes its initial power comparison; Nuclear
Fallout negates twice X rather than multiplying a clamped negative value.
Sarulf rechecks its intervening condition and cannot remove counters from a
departed source. Lightning Coils binds its delayed exile to the tokens actually
created, including replacement-generated tokens.

Sage's variable counter cost captures the paid quantity before resolution.
Complete groups of five determine extra turns, including zero groups. The
activation continuation stores this server-computed quantity separately from
the UI-bounded input intent, so removing 1,005 counters creates 201 turns
without widening input limits or rereading a departed source. Large removals
reuse the existing native removal helper.

Gameplay verification includes real payment and spell/ability copies, borrowed
abilities, source departure, replacements, intervening-condition failure,
response-time power changes, replay, and fresh-process saved resolution.
