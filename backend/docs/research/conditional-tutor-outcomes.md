# Conditional tutor requests and exact outcomes

Eighteen canonical cards compile to native searches plus explicit result-bound continuations: Aang's Journey; Analyze the Pollen; Nissa's Triumph; Tithe; The Five Doctors; Hunting Wilds; Caravan Vigil; Path to the Festival; Vision Quest; Courier of Comestibles; Unlucky Cabbage Merchant; Trench Gorger; Zirilan of the Claw; Nissa, Worldwaker; Slimefoot's Survey; Ruin in Their Wake; Dina's Guidance; Treasure Chest. Anchor to Reality belongs to the separate sacrificed-cost family and is not implemented here.

The complete metadata fixture is `tests/fixtures/conditional_tutor_outcome_cards.json`. Tests in `tests/test_rules_conditional_tutor_outcomes.py` exercise a successful found-card effect for every card before checking alternate branches and failures. The production leaf is `app/rules/conditional_tutor_outcomes.py`; searching, search authority, card movement, simultaneous entry, counters and delayed triggers still belong to existing native primitives.

## Queries, costs, destinations

The request adapter chooses a native selector/count/slot/destination when the corresponding condition is read. Kicker decisions use native `values.kicked_holds`, which includes an actual copied spell's inherited kicker. Analyze the Pollen reads the optional evidence payment decision from the EXACT source stack object's PaymentRecord; it deliberately does not use the actual-cast predicate, since CR707.10 copies additional-cost decisions but a copied spell was not cast. There is no global weakening of `conditions._cast_holds`. Actual Twincast gameplay proves both inherited evidence and kicker query/animation behavior.

Nissa's Triumph checks a controlled planeswalker with subtype Nissa; neither the card's name nor its owner is sufficient. Tithe counts lands at resolution and retains its mandatory opponent target. CR701.23h combines its requested additional Plains with the original library search. The Five Doctors uses the native selected subset of library/graveyard, proper Doctor creature subtype, and inherited kicker destination, shuffling only if the library was searched.

Ruin in Their Wake and Caravan Vigil reuse the native optional conditional battlefield destination, retaining the hand choice and respecting entry prohibitions/replacements. Dina's Guidance and Treasure Chest use an opt-in native found-card destination choice, after a card is revealed and before moving/shuffling. Agent-diverted cards cannot enter these menus. Treasure Chest keeps a native recorded die roll and all four actual result rows; the tests force the randomizer's result through the existing dice harness, never a fake Oracle card.

## Exact results, not a rescan

Every producer/consumer reference uses standard `ref:` namespacing, including the already-namespaced binding used when the adapter constructs a native request during resolution. Native `_finish_search` opt-in `outcome` captures exact selected references EXCLUDING Opposition Agent's replaced findings. After movement, `context.bind_moved` preserves their old information and exact new public objects. Hand outcomes use native `this_way: your_hand`; Trench Gorger counts exact resulting exile objects once with native `live_ref_count`, then creates a fixed base-PT effect. It never becomes a live CDA tied to whether those cards remain exiled later.

Haste, animation and untap riders receive a separate binding containing ONLY still-current battlefield arrivals. A Priest-redirected card in exile cannot receive a haste marker or an effect that later applies if it is recast. Vision Quest evaluates X into integer entry-counter metadata before the permanent enters; an additional count of zero is omitted rather than falling through a legacy `or 1` default. Native doubling, Solemnity, Priest and Cage are tested, along with a genuine Adaptive Automaton entry-choice pause and saved/replayed resolution.

Hunting Wilds untaps and permanently makes its actual found lands green 3/3 creatures with haste; its haste is not merely until end of turn (official ruling). Nissa's ultimate permanently makes actual found lands 4/4 Elementals with trample while retaining Land. Zirilan grants haste until end of turn and schedules native next-end exile tied to the exact entered object; leaving/reentering prevents that delayed trigger from moving the new object, and Zirilan leaving does not stop it.

Courier's Food fallback depends on whether a card was actually put into hand, including decline, fail-to-find, forbidden search and Agent diversion. Unlucky Cabbage Merchant uses the separate fact that a search was actually performed: finding zero still bottoms the exact original source before the final shuffle, while declining or a prohibited optional search does not. The original trigger's controller remains the player searching even if control of the source changes. Source-object checks remain native; a departed/reentered source is not guessed from its name.

## Domain and private looks

Path to the Festival checks the current land types AFTER the searched land enters. Slimefoot's Survey uses current derived library selectors for land cards with any basic land type, then checks current post-entry domain to size the native private look. The optional top card and random bottom remainder use existing look/pick/rest primitives and recorded randomness.

## CR701.23h repair to the preceding search family

The stored Comprehensive Rules (2026-09-25), 701.23h, say that multiple library-search instructions before a shuffle are the same as one search for all those cards. Firemind's Foresight and Verdant Crescendo now opt into a shared search frame. It records the original searched library portion as exact object references, the native Agent decider and whether the ONE search event was emitted. Subsequent requests reuse that same portion: removing the first card cannot make Aven Mindcensor's originally fifth card searchable. Frames are JSON-native and scoped to the resolution, source clause, searcher and library owner.

Textual movement order is preserved: Verdant's first land enters before the subsequent library/graveyard instruction (entry costs can change the graveyard); Firemind's repeated process moves each selected card to hand before the next qualifier. This is one continuing library search, not fresh searches of a changed top four. Native Agent exile and permission code is reused. Actual Archivist of Oghma, Mindcensor, Agent and new cold-session tests independently prove both cards' one event, same original portion and chooser across finds.

## Rules sources and checks

Rules: CR118.12b (choosing to search versus taking additional actions), 201.2/205.3 (names/subtypes), 608.2c/h (instruction order and current/LKI information), 614.6 (replaced original event does not happen), 701.23b/h (qualified fail-to-find and one library search), 707.10 (copied cost decisions). Official rulings were fetched from Scryfall's canonical card rulings endpoint; raw research is `/tmp/conditional-search-outcomes33-rulings.json` and `/tmp/search-name-packets32-canonical.json` for the earlier family.

Important official rulings: Caravan's battlefield choice remains optional even with morbid; Tithe counts lands at resolution; The Five Doctors cares about the Doctor subtype and copies inherit kicker; Hunting Wilds' creatures keep haste permanently; Trench Gorger may search if it has left, is 6/6 when search is declined, and its fixed PT does not change if exiled cards later leave exile.

Elfhame Sanctuary's this-turn-only skip expiry and Prishe's Wanderings' search-occurrence reflexive trigger remain explicitly outside this family. They are not promoted by pretending unsupported foundations exist. Full-catalog/type/core verification is centralized by the parent agent; this agent did not run a full inventory or mypy.
