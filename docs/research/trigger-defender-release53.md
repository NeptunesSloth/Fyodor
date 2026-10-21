# Guardian of the Ages: permanent native defender exchange

Status: independently reviewed and admitted by the trigger agent; production 11 whole-card (two genuine cold) plus 47 related tests and scoped types/Ruff passed. Count ownership: trigger manifest. No shared algorithms or custom primitives.

Actual canonical and two official rulings were reviewed in `/tmp/counter53-compound-canonical.json` and `/tmp/counter53-compound-rulings.json`. Those research artifacts also contain Second Chance and Elder Spawn, owned by the independently admitting trigger agent; this leaf admits only Guardian of the Ages.

The exact wrapper retains the existing native creature-attack event, player-or-controlled-planeswalker defender filter, source defender predicate at trigger time, and native only-if recheck at resolution. It changes the ordinary keyword grant into a permanent trample grant that removes defender from that exact source object. Multiple attacking creatures each trigger; losing defender on the first resolution stops the later defender checks. Departed source incarnations cannot grant the successor trample. The official rulings explicitly confirm that the change lasts indefinitely and that reacquiring defender can allow another trigger.

Native tests pay seven mana, prove defender blocks an actual later-turn attack, own-player/own-planeswalker/opponent attack scope, permanent persistence across cleanup, multiple attackers with one successful defender exchange, source blink identity, Turn to Frog resolution recheck, actual released-Guardian attack and trample over a blocker, and two fresh-process continuations (pending trigger and permanent effect after cleanup). Related native conditions/duration tests: 47 cases.

Hook proposal `/tmp/counter53-defender-hooks-proposal.patch`; final manifest `/tmp/counter53-defender-review-manifest.json`.
