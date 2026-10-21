# Actual object names and name-equivalence instructions

Batch34 covers Detention Sphere, Legion's End, Hour of Glory, Deicide, Invasive Surgery, Pick the Brain, Reap Intellect, Moratorium Stone, Bloodbond March, Locket of Yesterdays, Cylian Sunsinger, Chrome Replicator, Winnow, Eye of Singularity, Bazaar of Wonders, Mimeofacture, Dichotomancy, Reflector Mage, Academic Probation and Cornered Market. Twinning Glass is deliberately outside this implementation; a historical cast-name snapshot deserves its own schema change.

CR201.2a/709.4a comparisons use actual current characteristic name sets, including a split card's multiple names, rather than the physical printing display name. A real canonical Pack Hunt test initially failed to find a Bonecrusher Giant card when targeting the battlefield Bonecrusher Giant: its physical printing name included `// Stomp`. Native named search now compares characteristic names, and the test passes. Existing target/event references read exact-object LKI when necessary (608.2h/400.7).

The new sequence leaf freezes reference facts at the proper instruction and inserts standard typed native effects. It does not directly mutate damage, counters, destruction, entry, or search destinations. Native target legality, regeneration/replacement continuations, linked exile, cost locking, search packets, private choices and APNAP trigger placement remain authoritative. Produced binding names which cross the compiler are explicit `as` fields; consumers carry standard `who: ref:` metadata so compiled line namespaces cannot separate producers from consumers.

Important individual distinctions follow canonical Oracle and official Scryfall rulings:

* Detention Sphere has one target and includes untargeted same-name lands. Its literal excluded name remains Detention Sphere even when an ability is copied. Standard linked exile handles original-source departure and exact incarnations.
* Hour of Glory checks whether the old battlefield creature was a God, and uses its old controller. Deicide checks the actual card in exile; a copied God which reverts to its printed non-God card does not qualify. The frozen old controller is the player searched.
* Reap Intellect uses the names of actual exiled hand cards, allows selecting zero, does not search if none were exiled, and still performs its independent final shuffle. Optional qualified searches may leave matching cards untouched.
* Locket changes generic payment only, counts each matching graveyard card once, and excludes the spell being cast from that graveyard. Native payment owns locking and colored-symbol requirements.
* Chrome requires two distinct nonland nontoken permanents controlled by its controller, with its intervening condition checked at trigger creation and resolution.
* Winnow draws even if no duplicate exists or destruction is prevented; sole-illegal-target resolution still follows the native fizzle gate.
* Eye excludes basic lands, uses a simultaneous destruction group with regeneration prohibited, and excludes only the original exact entering object from its later-entry destruction.
* Dichotomancy freezes separate name slots for each tapped nonland permanent, selects distinct physical cards in one native search and enters all found cards together, under the resolving controller, then shuffles the library owner.
* Reflector Mage binds the old creature's owner and old name until the resolving controller's next turn; its owner can cast a card whose hand name differs from that old name. Academic Probation binds the chosen name and only opponents. Cornered Market reads current nontoken permanents and separately prohibits nonbasic land plays.

Canonical fixtures retain colors, mana values, keywords, layouts and face metadata. Own tests prove every actual positive effect, opposite branches, controller distinctions, last-known source names, native name bans at legal casting times, intervening conditions, privacy-bearing native choice lifetimes, replay and JSON roundtrips. Three fresh Python processes load and resume hand choice/search, foreign-library named tutor and typed-name restriction after constructing a cold view.
