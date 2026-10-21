# Professor Onyx: seven simultaneous discard rounds

The official 2021-04-16 ruling defines each iteration: opponents choose cards privately in turn order, all chosen cards are revealed and discarded simultaneously, and opponents who did not discard lose 3 life. The whole operation happens seven times. It is not seven choices by the first player followed by seven by the next player.

The parser uses the existing `each_may` whole-round mechanism. Discard-only deferred optional payments now use a prepared group: validate and bind payments, capture exact objects and replacement candidates, finish affected players' replacement choices, then commit one simultaneous move with individual destinations. Opponent-caused battlefield replacements and madness retain their actual cause and event timing; replacement-displaced discards still pay the cost. Battlefield entry choices/counters use the existing simultaneous entry machinery. Madness creates its usual delayed trigger after the one exile move. Discard triggers wait until the entire loyalty ability finishes.

One native grouped life-loss call applies each round's nonpayer losses. State-based elimination happens after the complete resolving ability, so a player at zero life partway through still makes subsequent choices. Source loyalty is paid once and the source may already be gone when the ability resolves.

Seventeen canonical gameplay cases passed, including all seven pay/decline rounds, empty hands, APNAP rotation after control change, private choices, simultaneous ordinary and Baloth discard routes, Rest in Peace competing with Baloth or madness, deferred Megrim/ETB/madness triggers, zero-life boundaries, save/replay and fresh-process private-choice and replacement-choice resumes. No frontend change or new game-lifecycle outcome is needed.

Related verification closed with 283 unique passing cases across each-player optional payments, discard causes, repeated costs and replacement guards (300 unique including the 17 new cases). Three existing scalar-mana assertions were updated to the established aggregate mana-pool helper without changing expected quantities.
