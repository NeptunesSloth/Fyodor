# Earthbender Ascension

Oracle text and supporting canonical cards are recorded in `backend/tests/fixtures/reflexive_counter_threshold_cards.json`. Scryfall's rulings were checked during implementation, including that earthbend targets an existing land before the later search puts another land onto the battlefield.

CR 603.12 creates a separate reflexive triggered ability after counters are actually put on the enchantment. CR 603.4 checks the threshold both when that ability would trigger and when it resolves. A prevented counter does not create the reflexive ability. Counter multiplication uses the existing native reflexive counter accounting.

The parser extension is bounded to a preceding instruction putting counters on the source and a leading condition about that source's counters. The new reflexive ability has its own targets and an intervening condition. Its resolution gate skips the entire ability if the condition fails, including the second sentence granting trample. The source antecedent is distinct from the land that caused landfall. Native last-known information preserves the original source's counters after it leaves or returns as a new object.

Tests exercise actual land play, low and sufficient thresholds, Solemnity, Doubling Season, a real Vampire Hexmage response, source departure and return, the original earthbend/search entry ability, replay, and save/load.
