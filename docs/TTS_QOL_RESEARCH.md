# Tabletop Simulator QoL research

What Magic players repeatedly find fiddly in Tabletop Simulator, and how Fyodor improves
on it. The guiding test for every feature:

> Would this take **fewer actions** than doing the same thing in Tabletop Simulator?

Status legend:
- ✅ done: implemented and tested.
- 🟡 partial: the core exists, with gaps noted.
- ⬜ planned.

Items in *italics* existed before this round of work.

## P0: core experience

| Feature | TTS behavior / problem | Fyodor improvement | Deps | Status |
|---|---|---|---|---|
| 3D card manipulation | Physics objects. Cards bounce, slide off the table, and merge into decks when colliders touch. | Kinematic cards: lift while dragging, eased settle, clamped to the table, recovery to the last safe position. Stacking is always explicit. | three.js scene | ⬜ |
| Archidekt import | Needs a third-party deck builder mod or manual image sheets | URL import (public JSON, exact Scryfall printing ids), paste/upload export, categories, finishes, preview with fallbacks, cache artwork | card DB | ✅ |
| Private deck search | Search spreads the deck face up in a private view; you scroll through 100 cards, drag one out, close, right-click, shuffle | Hover deck → `S` → type `sol` → click → choose destination → one-click **Shuffle**. Scryfall syntax (`t:`, `o:`, `c:`, `mv:`, `s:`), Archidekt category filter, *Search without shuffle*. Opponents only see "X is searching". | *engine search sessions* | 🟡 |
| Instant inspection | Alt-zoom shows only the image | Hold `Space` over any card: large image, Oracle text, counters, notes, controller/owner, attachments. Wheel resizes; `Tab` previews the other face without changing the table. Cached images appear instantly. | texture cache | 🟡 |
| Action-level undo | Rewind loads a snapshot from seconds ago, which is coarse and unpredictable | *Every change is one validated action. Undo/redo one action.* New: **History** panel (turn, time, who, what), **Restore to here**, undo policy (everyone / own actions / host). | *history* | 🟡 |
| Quick save / crash recovery | Manual save slots only | `Ctrl+S` quick save, *rotating autosaves every 10 actions*, and a **Recover game?** prompt on the lobby when the last session was interrupted | *saves* | 🟡 |
| Multi-object manipulation | Box select, but group actions are limited | Box select, `Shift`-click, group drag keeping offsets. Selection toolbar: Tap all / Untap all / Counter all / Move all / Graveyard / Exile / Stack / Arrange / Lock. | selection | 🟡 |
| Safe stacking and object safety | Accidental deletes and deck merges | Stacking only on intent. **Locked** (can't move) and **Protected** (can't be deleted, merged or stacked without confirming). Commanders are protected by default. | engine fields | ⬜ |

## P1: Magic quality of life

| Feature | TTS behavior / problem | Fyodor improvement | Deps | Status |
|---|---|---|---|---|
| Arbitrary counters | Spawn generic beads or dice | *Logical typed counters with any name.* Counter manager with `[-] n [+]` rows; readable badges. | *engine* | 🟡 |
| Token stacks | 27 Treasures means 27 objects | **Treasure ×27** as one logical stack: +1/−1/+5/−5, Split, Expand, Delete all. Identical tokens can be merged explicitly; non-identical cards never merge. | engine `quantity` | ⬜ |
| Quick card toolbar | Right-click menus nested several deep | A small floating toolbar on selection (Tap, Counter, Effects, Inspect, …). The full context menu adapts to the card: Transform for DFCs, loyalty for planeswalkers, Command Zone for commanders. | action registry | ⬜ |
| Double-faced cards | State hacks; "flip" shows the card back | *Transform (active face) is separate from Face down.* Inspector can preview the other face. | *engine* | 🟡 |
| Attachments | Physics joints, or nothing | `attached_to`: equipment and auras follow their host and sit tucked under it. Hold `Alt` while dragging to move only the parent. Detach. Persisted through undo, saves and sync. | engine | ⬜ |
| Camera and presets | Free camera, lots of navigation | WASD / middle-drag pan, right-drag orbit, wheel zoom. Presets `1`–`7` (my battlefield, full table, opponents, stack, command zones). `F` focuses the selection, `F`/`Esc` returns. Instant/Fast/Smooth transitions. | 3D | ⬜ |
| Screen-space hand | Hand is a 3D zone that's hard to read at angles | Optional overlay hand (**On / Off / Auto**, a persistent preference). Reorder, inspect, drag straight onto the 3D table. | 3D | ⬜ |
| Editable hotkeys | Fixed bindings | Central action registry with rebindable keys (saved per browser): `R` tap, `F` focus, `Space` inspect, `S` search, `G` group, `L` lock, `C` counters, `T` tokens, `M` move, `Del` delete. | registry | ⬜ |
| Commander tracking | Manual notes or a scripted mod | *Command zone, automatic adjustable tax, commander damage per commander, poison, monarch, initiative.* | — | ✅ |
| Magnetic alignment | Grid snap or nothing | Optional light snapping to nearby rows (Off / Light / Normal). Hold `Alt` to disable. | 3D | ⬜ |
| Arrange commands | Manual | Row / Column / Grid / Fan / Stack, plus **Arrange lands** and **Arrange creatures**, applied to the current selection | selection | ⬜ |
| Temporary piles (groups) | Custom scripting | `G` groups the selection and dragging one member moves all of them. `Shift+G` ungroups. | engine `group` | ⬜ |

## P2: power features

| Feature | TTS behavior / problem | Fyodor improvement | Deps | Status |
|---|---|---|---|---|
| Card macros / effects | Lua scripting per mod | Declarative macros made of validated primitives. Oracle-text suggestions (e.g. `{T}: Add {C}{C}`, loyalty abilities, token makers). Each macro run is **one** undo step. | engine `macro` | ⬜ |
| Custom card actions | Lua | Right-click → **Add custom action**. Save it to this instance, every copy of the card, or the personal library. | macros | ⬜ |
| Visual targeting | — | Target mode: candidates highlight, click, and a temporary arrow is drawn and logged. `Esc` cancels. Legality isn't enforced. | 3D picking | ⬜ |
| Combat helpers | Manual | *Attack/block markers and blocker arrows.* In 3D, attackers slide forward. | — | 🟡 |
| Reminders | Sticky notes | Add a reminder for the next upkeep / draw / combat / end step / next turn. It's shown when that step is reached and never auto-executes. | engine | ⬜ |
| Card notes | Object descriptions | *Per-instance notes with a note icon* | — | ✅ |
| Pings | Pointer arrow | `Alt`+click pings a spot or card for everyone for 3 seconds. Nobody's camera moves. | WS event | ⬜ |
| Picture-in-picture | — | Pinnable live mini-views of another area (opponent battlefield, stack) | camera | ⬜ planned (the camera module has hooks for secondary views) |
| Command palette | — | `Ctrl+K`: fuzzy search over every registered action (core, tokens, macros, camera, game) | registry | ⬜ |
| Archidekt categories in search | — | Category filter in private library search, never shown to opponents | Archidekt | 🟡 categories reach the game privately; search filter UI pending |
| Deck version diff | — | **Check source**: added/removed/printing/category changes, then Apply / Ignore | Archidekt | ✅ |

## P3: multiplayer and polish

| Feature | Status |
|---|---|
| LAN sync, private-information filtering, spectators | *✅ existed*. New fields are covered by the leak tests. |
| Undo permissions | ⬜ (`undo_policy`) |
| Host permissions for spawn/delete/modify others | ⬜ planned. The architecture has a permission check point in `api/games.py` `authorize()`. |
| Play mode / edit mode | 🟡 Play mode is the default and hides table editing. The table editor is future work. |
| Table presets | 🟡 Presets are data in `table3d/layout.ts` (2–6 seats). Saving custom presets is planned. |
| Solo / goldfish mode | 🟡 One-player games and *Open table* exist. **Restart with same deck** is planned. |
| Opening hand tool | ⬜ Draw 7 / Mulligan / Keep bar at game start |
| Performance architecture | ⬜ render-on-demand, shared geometry, texture LRU, logical stacks. See the benchmarks in `docs/PERFORMANCE.md`. |

## P4: accessibility and polish

| Feature | Status |
|---|---|
| Settings (UI scale, hover size, camera/drag sensitivity, rotation step, animation speed, screen-hand, snap) | ⬜ Settings panel (searchable) |
| Contextual first-use hints (dismissible, never repeat) | ⬜ |
| Controller-ready input abstraction | ⬜ Semantic intents in `input/`. There are no gamepad bindings yet. |
