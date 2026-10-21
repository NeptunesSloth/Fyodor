# Ordinary banding

Authority: Comprehensive Rules effective 2026-09-25, CR 702.22a/c-k, 508.1,
509.1, 510.1c/d, 702.19b (trample), and 400.7 (new objects).

Ordinary banding now supports declaring attacking bands with one or more creatures
with banding and at most one without it, all attacking the same defender. Creatures
remain separate permanents with their own abilities. Blocking one member blocks the
others, including when a ground member exposes a flying or menace member. An effect
making one member blocked makes the entire band blocked.

Bands persist when banding is lost. Leaving combat removes a member; a returned card
is a new object and does not rejoin. At damage assignment, current banding among the
opposing creatures determines who divides the source's combat damage. First strike,
trample's lethal requirement, multiple blockers, and attack costs remain independent
for each creature.

## Implementation and interface

`banding.py` validates declarations, records object IDs, expands shared blocks, and
selects the damage chooser. Existing block/damage primitives apply the results.
`DeclareAttackers.bands` is optional and defaults empty. The new
`RulesState.attacking_bands` field also defaults empty for old saves, records object IDs,
and is pruned during reconciliation and cleared at combat boundaries. Public views
expose only the current battlefield card IDs.

The attackers panel provides band selection, validates each group, and disables invalid
declarations. The HUD lists declared bands and restores them on reconnect. Ordinary
keyword, temporary/static/Aura grant, and token-creation paths accept banding.

## Validation and catalog

62 focused tests and 286 plus 279 selected regression tests pass (overlap). Gameplay
tests check replay/save-load, both sides' assignment choices, multiple blockers and
bands, flying and menace, first strike, trample, attack taxes, lost and newly granted
banding, leaving/returning objects, effect-created blocked status, invalid declarations,
and temporary/static/Aura/token grants. Browser E2E passes for declaring bands,
invalid-group prevention, public display, and reload. All 81 frontend unit tests,
TypeScript/build, Ruff, mypy (350 files), and whitespace checks pass. Two real-card
browser fixtures were added; the importer fixture count was updated accordingly.

Inventory compared with the base-stat checkpoint promotes exactly 30 cards and loses
no FULL support: 20 intrinsic banding creatures plus Baton of Morale, Helm of Chatzuk,
Soraya the Falconer, Fortified Area, Cooperation, Formation, Icatian Infantry, Errand
of Duty, Dire Wolves, and Beast Walkers. The result is 27,702 FULL / 4,366 PARTIAL of
32,068 Commander-legal cards; commanders are 2,947 FULL / 3,501.

“Bands with other” and effects specifically referring to bandmates remain separate
unfinished families. Cards containing those unsupported abilities remain PARTIAL.
No complete backend suite, commit, push, or deployment was performed.
