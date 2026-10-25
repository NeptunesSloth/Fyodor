# Jandor’s Ring exact last-drawn-object cost

Depends on costs106 source base. Two native files: exact discard-cost grammar uses an own-hand selector; selector reads the last private ordered actual draw object already recorded in TurnLog.drawn. Never scans backward for a surviving card, never accepts a card returned under a new object ID, never infers absent legacy history. No new schema or public projection changes.

Canonical PR21 PARTIAL now FULL. Clean native-first7.log7 PASS: actual two-card draw then Ring activation discards only last, taps/pays2 and draws replacement; previous draw invalid; latest leaving hand disallows fallback and returned incarnation; true cold activation; true cold old-save missing draw history fails closed. Two genuine fresh-process checks. Scoped mypy2 and configured Ruff3 PASS. Minimal native fixture decks avoid unnecessary large-state replay. No whole-suite claim.
