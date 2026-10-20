# Qualified banding: “bands with other”

Authority: Comprehensive Rules effective 2026-09-25, CR 702.22b/c/e/j/k/m,
613.1f and 613.7 (ability grants/loss in timestamp order), 201.2 (names), and
400.7 (new objects).

A qualified band can contain any number of matching creatures when at least one
matching creature has the corresponding “bands with other” ability. For damage
assignment, a holder and another matching creature must be blocking or blocked by
the same creature. One holder alongside a nonmatching creature does not change the
chooser. Ordinary banding remains an independent way to form a band.

The Oracle reader preserves each qualified form as its own keyword key. Existing
selectors match legendary creatures or creatures with a literal name. Band validation,
shared blocking, and assignment control use those qualities. Static and resolved
ability grants participate in layer 6 at their own timestamps. Removing ordinary
banding also removes all qualified forms; removing qualified forms alone keeps
ordinary banding. A later grant restores only the form it grants.

The browser receives eligible holders and matching members for each quality, so its
controls validate qualified groups alongside ordinary bands. Public bands continue
to use existing band state. No further GameState fields were added.

23 focused tests and 433 selected regression tests pass (overlap), with gameplay
replay/save-load checks. Coverage includes all five land colors, controller filtering,
three-member legendary bands, nonmatching rejection, the second-matching-creature
assignment rule, real named Wolf tokens, loss without breaking the band, Tolaria's
upkeep restriction, later ordinary versus qualified grants, and removing two qualified
forms then restoring only one. Both ordinary and qualified browser E2Es pass, as do all
81 frontend unit tests, TypeScript/build, Ruff, mypy (350 files), and whitespace checks.
The Cathedral browser fixture increases the importer count to 175 and the expected
nonbasic-land search set includes it.

Inventory comparison promotes exactly Tolaria, Cathedral of Serra, Adventurers'
Guildhouse, Mountain Stronghold, Unholy Citadel, Seafarer's Quay, Master of the Hunt,
and Shelkin Brownie, with no lost FULL support: 27,710 FULL / 4,358 PARTIAL of 32,068
Commander-legal cards; commanders remain 2,947 FULL / 3,501. Effects explicitly referring
to bandmates remain unfinished. No complete backend suite, commit, push, or deployment.
