# Casting spells with mana from a particular object

Sources: [Brass's Tunnel-Grinder rulings](https://api.scryfall.com/cards/d61d8895-7f2e-4c77-951f-4f1a49e96f57/rulings), checked 2026-10-19; Comprehensive Rules 2026-09-25, 106.3 (mana's source), 106.4 (pool emptying), 201.5 (self-reference), 400.7 (new objects), 601.2h–i (payment and becoming cast), 707.2a/707.4 (copying characteristics), 718.3 (prototype).

The shared cast qualifier `using mana produced by ~` compares the watching permanent's exact rules object ID against sources of mana actually spent on the spell. It applies to Tecutlan, the Searing Rift; Barracks of the Thousand; and The Myriad Pools. The ordinary spell selector and casting player remain part of the condition.

All mana from a known source retains that source and its traits, including ordinary basic lands and Thespian's Stage. Restricting tracking to currently interesting printed abilities is unsound: Stage can make {C}, become a copy of Tecutlan without changing objects, and then trigger when its earlier mana is spent. Transformation likewise preserves identity; blinking produces a new object. Unknown-origin mana added by table tools and older saved plain pools remains unknown.

Only actually spent slots are recorded. Floating another source's mana, or leaving the relevant source's mana unspent, does not qualify. Mana paid for an activation does not create a cast event. Converted mana retains its source through Horizon Stone, and firebending retains its source until the mana empties at end of combat. Source tracking is hidden in normal player views: unrestricted remembered units are folded into the ordinary visible pool.

Tecutlan discovers using the spell's mana value, including chosen X on the stack and retained X if the spell was countered. Cost reductions do not reduce mana value. Its trigger resolves before the original spell.

The Myriad Pools copies the permanent spell's copiable values into the selected other permanent until end of turn. The source recipe is read from the stack or its last known information. Prototype values are copied. A face-down spell contributes only its public face-down characteristics; no hidden printing enters the resulting recipe. The copied permanent remains face up. Snapshot metadata retains face-down kind and specifications, including disguise's ward.

Validation includes actual Oracle fixtures, ordinary and manually floated payments, Stage's pre-copy mana, controller and object changes, a 1001-mana Marwyn activation followed by a 1000-mana payment, ordered source/target choices, face-down morph and disguise spells, prototype spells, and replay/save-load at pending choices. Existing Rain of Riches history and cascade checks retain their separate source-trait semantics.

The existing unit representation remains practical: a local benchmark measured 20 units at 1851 JSON bytes and 0.07 ms generic solving, 100 units at 9291 bytes and 0.21 ms, and 1000 units at 93891 bytes and 2.72 ms. Internal mana unit action capacities allow up to 100000 entries; compact quantity storage is not required for ordinary pools.


### Filter activation payments and public mana views

An automatically chosen filter is activated before the outer spell payment. Its mana input pays that activation, so its source IDs, Treasure/Snow tags and spell spend riders do not enter the spell payment. Native mana ability activation preserves life costs, tap/sacrifice costs and production riders. The filter's output then pays the spell normally, preserving unspent output units. Generic activation inputs are assigned actual colors during source selection: an Island can fund Sungrass Prairie while a Forest remains available for a double-green spell.

The existing automatic search bounds remain six candidate filters, pairs of at most two, and the mana solver's search budget. Aggregate filter feasibility can still overestimate a payment involving spell-only restricted input mana: native activation rechecks its own purpose and rejects the action atomically. Manually activating legal inputs remains available for those combinations. This change does not claim exhaustive filter-source search.

Player/spectator mana views fold unrestricted remembered units into the visible mana pool in one pass; restricted/rider units retain sequential visible IDs. Omniscient views retain exact source metadata.
