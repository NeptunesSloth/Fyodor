# Rites of Refusal collateral validation

The actual Oracle spell costs {1}{U}: "Discard any number of cards. Counter target spell unless its controller pays {3} for each card discarded this way."

The shared unless-payment quantity grammar now reads its native prior-discard binding. Discarding happens during resolution, after target legality is checked; it is not an additional casting cost. CR 608.2c/h: the tax counts the cards actually discarded by that instruction. CR 118.12a: the target spell's controller may pay the whole cost, including zero if no cards were discarded. Explicitly declining a zero payment still permits the counter instruction. CR 701.9: a replacement that sends discarded cards to exile changes their destination without making them cease to be discarded, so Rest in Peace must preserve the count.

Canonical fixtures include full metadata for Rites and Rest in Peace, with the existing reveal-family fixture supplying canonical support cards. Tests exercise 0/1/2 discards, payment/decline/unavailable costs, private chooser options, actual JSON-reloaded continuations and history replay, replaced discard destinations, and a target leaving before resolution. This is validation only; no production changes were needed.
