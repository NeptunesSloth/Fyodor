# Tap actors 62 — independently admitted

Solitary Sanctuary (`4c0a8eed-f2e2-4821-8011-6e6ad2081936`) and Icewrought Sentry (`0828d891-f7c3-4e51-b42e-6ce88d48ac8b`) were independently reviewed and registered by the trigger agent. Production 26 native cases plus 41 related cases, scoped mypy and Ruff passed. Both promotions belong only to the trigger stream manifest (admission 68).

`backend/app/rules/trigger_tap_actors62.py` exactly guards their printed singular tap triggers. It composes the existing plural instructed-tap grammar, including its event actor filter, then changes only aggregation to per creature. No event, activation, casting, or effect algorithm changes are proposed.

Isolated verification passed 26 native cases: a complete 25-case run including two genuine subprocess reloads, plus the additional paid Sanctuary ETB ruling test where an already tapped target receives a stun counter without triggering the counter follow-on. Other proofs cover actual paid Frost Lynx and Frost Breath, individual creatures in one simultaneous batch, repeat tapping, current controller versus owner, paid Icy Manipulator control changes, own-creature exclusion, opponent mana activations, attack declaration, Sentry source blink, Sanctuary's full paid ETB, and Sentry's paid cast, vigilance attack, optional payment, and reflexive tap.

Both native Rhystic Deluge cases passed: while your ability resolves, an opponent activates Llanowar Elves to pay its native optional mana cost. Their creature taps, the target stays untapped, and your watcher does not trigger. This tests an actual supported instructed-payer context; it is not an implementation of Tangle Wire. Tangle Wire remains PARTIAL, and its exact instructed-player tap body is unproved end to end here.

Related verification passed 41 cases: wave45c tapped 9, crew 3, and keywords3f 29. Scoped mypy (one source) and Ruff passed. The attempted stage-only mana-activation-watchers regression file used a hardcoded repository-relative database path unavailable in the staging layout; it was excluded from these 41, with no semantic claim based on that failed harness run.

Full actual database canonicals and all official rulings (2/1): `/tmp/counter62-tappers-canonical.json`, `/tmp/counter62-tappers-rulings.json`. Frozen file hashes, exact names, proposed four-line hook, and logs: `/tmp/counter62-staged-manifest.json`. Leaf SHA256: `a3c3cff6a1bc17c2e881a00a7e0780444e6df8b6ab1018b335a51ec8d2afa88c`.

Tests and full canonical fixture: `backend/tests/test_rules_trigger_tap_actors62.py`, `backend/tests/fixtures/trigger_tap_actors62_cards.json`. No shared event, casting, activation, or regeneration code was edited.
