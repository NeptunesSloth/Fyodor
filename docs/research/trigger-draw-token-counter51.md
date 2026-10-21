# Construct a Cosmic Cube: native draw/token/counter conjunction

Status: independently reviewed and admitted by the trigger agent after production 14 whole-card tests (including three genuine cold continuations), 78 related tests, scoped types, and Ruff passed. Count ownership: `/tmp/trigger50-admitted-manifest.json`. No coverage-only changes, custom primitives, or shared algorithms.

The full actual database canonical has two triggered abilities. The first trigger's conjunction joins token creation to a plan counter; the exact wrapper changes that conjunction into two sequential ordinary native effects. Second-card-per-turn tracking, 2/1 black Villain menace token creation, token/counter replacement effects, and the seventh-counter trigger all use existing native paths. The second printed ability remains unmodified: sacrifice, reflexive opponent target, and control that opponent during their next turn. No official rulings were returned by the card's Scryfall ruling endpoint.

Evidence files: `/tmp/counter50-cube-canonical.json`, `/tmp/counter50-cube-rulings.json`, `/tmp/counter51-cube-hooks-proposal.patch`, `/tmp/counter51-cube-review-manifest.json`.

Native tests pay the source's actual 2B cost and draw spells' costs. Cases cover second versus third draws, own second draw during another player's turn, other players' draws, Doubling Season, Solemnity, crossing seven counters (including six to eight), actual sacrifice/reflexive opponent targeting, opponent's next-turn native actions and expiry, inability to sacrifice after control change, and a new source incarnation receiving no counter from the old trigger. Three fresh-process continuations restore pending second-draw, seventh-counter, and next-turn-control states from serialized native saves and perform ordinary native actions without parser adapters or bootstrap hooks.

Related tests: `tests/test_rules_wave18h_player_control.py`, `tests/test_rules_wave5d_triggers.py` (78 cases). Exact final counts/log paths belong in the review manifest; final production counting belongs to the independently reviewing trigger agent.
