# 3D direction: Tabletop Simulator interaction on an Arena-like rules engine

Goal: **Tabletop Simulator-style 3D interaction + MTG Arena-like rules automation + a manual
sandbox override.**

- **Physical:** cards are physical objects you pick up, drag, stack, tap, flip and arrange
  anywhere.
- **Automated:** for the cards and mechanics the rules engine supports, those gestures mean
  something. Dragging a land plays it, dragging a creature forward attacks, and costs,
  triggers, combat damage and state-based actions happen automatically, as in Arena.
- **Manual:** anything unsupported or unusual is done by hand with the same table.

Guiding rule: **the gesture is the player's intent, the server decides the outcome, and a
manual override is always one modifier away.**

**Sequencing.** The 3D renderer is built *after* the rules engine boundary and core
primitives (`IMPLEMENTATION_PLAN.md`, M14–M18). It is integrated with the rules intent API
from the start, so it never learns how to mutate game state directly.

## 1. What exists (inspected 2026-09-28)

| Layer | State | Verdict |
|---|---|---|
| Card DB (`backend/app/cards`) | Scryfall bulk importer, FTS5 search, image cache, printings | **Keep**. It's engine-agnostic. |
| Decks (`backend/app/decks`) | Tolerant parser, repository, validation, editor UI | **Keep and extend** for Archidekt (see `ARCHIDEKT_COMPATIBILITY.md`). |
| Table engine (`backend/app/game`) | Server-authoritative state, ~100 validated sandbox actions, deterministic resolve/apply, per-viewer views and visibility, snapshot+replay history, saves | **Keep**. It knows nothing about pixels, so a 3D client can drive it unchanged. |
| Rules engine (`backend/app/rules`) | Planned (M14–M17): intents, priority, stack, costs, combat, SBAs, card scripts, coverage | **Build before 3D.** The renderer talks to it through intents. |
| Multiplayer (`backend/app/multiplayer`, `api/games.py`) | Rooms, seats, tokens, WS broadcast of sanitized views | **Keep**. |
| Frontend (`frontend/src`) | React + zustand, 2D DOM battlefield (`game/Battlefield.tsx`, `TableCard.tsx`, ...), overlays, dialogs, context menus | **Keep overlays and state layer; add a 3D play surface** beside the 2D board. Both use the same gesture → intent module. The 2D board stays as a lightweight fallback view. |

The important finding is that the hard parts are already rendering-independent:
- hidden information,
- undo,
- deterministic randomness,
- saves,
- LAN sync.

Moving to 3D is a **client** change. The rules engine is a separate server-side layer that
both the 2D and 3D clients use through the same intents. Neither is a rewrite.

### Is the current undo "reload the table from 10 seconds ago"?

No. Undo is already **command-based**. Every meaningful change is exactly one validated
action (`move`, `tap`, `create_token`, `shuffle`, …) and undo removes exactly one action.
Internally the previous state is rebuilt from the nearest snapshot (every 20 actions)
plus at most 19 replayed actions. That takes microseconds to milliseconds and is
invisible to the user.
- The client doesn't reload the scene. It receives the new view and the 3D renderer
  diffs it, so only the objects that changed animate back.
- Randomness is stored in the action, so undoing a shuffle restores the exact previous
  order.

Explicit inverse operations per action would add a second, bug-prone code path for
every action type without improving what the user sees. They're rejected on purpose;
see §6.

## 1a. Gestures send intents, not state changes

The renderer turns a gesture into exactly one input and sends it. It never edits the
authoritative state, and it holds no rules logic.

| Gesture | Automation on (rules intent) | Automation off, or override modifier held (sandbox action) |
|---|---|---|
| Drag a land from hand to your battlefield | `play_land(card)` | `move(card → battlefield, x, y)` |
| Drag a spell from hand onto the table or stack | `cast_spell(card)`, then prompts for targets, modes, X and payment | `move(card → stack or battlefield)` |
| Drag a creature forward during declare attackers | `declare_attackers([(card, player/planeswalker)])` | `attack` marker |
| Drag a blocker onto an attacker | `declare_blockers([(blocker, attacker)])` | `block` marker |
| Click an ability on a card (card toolbar / radial) | `activate_ability(card, ability_id)` | context-menu tools |
| Click a highlighted target during a prompt | `choose(decision, answer)` | — |
| Space / Pass button | `pass_priority` | `phase` (next step) |
| Drag anywhere else (rearrange, stack, fan out, tidy) | a sandbox `set_position` / `group` / `attach` (never a rules event) | same |

Rules for the renderer:

- **Optimistic motion, authoritative result.** A dragged card moves locally while you drag.
  On release the client sends the intent and waits for the next view.
  - If accepted, the card settles where the server put it.
  - If rejected, it glides back and the reason is shown, with *Do it manually* offered.
- **Hints come from the server.** The view says which of *your* cards are playable, which
  creatures can attack or block, and what the pending prompt accepts. The renderer only
  highlights; it never computes legality. Hints about hidden cards go only to their owner.
- **Visual physics ≠ authoritative state.** Tweens, lifting, bounce, dice tumbling or a
  "flip the table" effect are cosmetic. Only the server's view decides where things are.
- **One gesture module.** `frontend/src/input/intents.ts` maps gestures to intents or sandbox
  actions for both the 2D board and the 3D scene, so behaviour is identical in both views.

## 2. Engine choice

| Option | Pros | Cons |
|---|---|---|
| **Godot 4** (native client) | Real 3D engine, physics, good tooling | A second client stack (GDScript/C#) that duplicates networking, views, overlays and tests. LAN guests must install a native app per device. Web export is ~40 MB WASM, awkward with DOM overlays, and has no shared React UI. Not available in this environment to build or test. |
| **Godot web export embedded** | Keeps a browser join flow | Heavy download, poor text/overlay integration, two UI systems |
| **Babylon.js** | Full engine in the browser | Larger API surface than we need; its GUI would compete with React overlays |
| **three.js inside the existing React client** ✅ | Same app, same LAN "open a URL" flow, reuses the WS protocol, sanitized views, card cache, image route, overlays and tests. Small bundled dependency (works offline), handles hundreds to thousands of meshes, instancing when needed. | We build our own interaction layer (drag/lift/snap/select). That's exactly the part we want to design Magic-specifically anyway. |

**Decision: three.js, driven imperatively from a `TableScene` class inside the React app.**
- React-three-fiber was considered and rejected for the scene itself. A reconciler per
  card adds overhead at 500+ objects, and we want full control of the render loop
  (render on demand).
- React still owns all 2D UI:
  - toolbars, menus, inspector, search, history, palette;
  - the screen-space hand, which is projected over the canvas.

### Physics: controlled, not simulated

Physics is purely presentation. The server stays authoritative, and rules outcomes never
depend on the simulation.


Magic doesn't benefit from rigid-body chaos, so cards are **kinematic**:
- They lift while dragged, glide to their target with an eased tween, and settle flat.
- Stacking is explicit (drop-on-card intent or `Create stack`). Touching colliders never
  merge objects.
- A card can't fall through or off the table. Positions are clamped to table bounds,
  and an object outside them snaps back to its last valid position.
- A cosmetic physics mode (e.g. "flip table") could be added later with Rapier as a
  purely visual effect. It must never mutate authoritative state.

## 3. Coordinate model

- **World**: centimetre-like units. A card is 6.3 × 8.8 and the table is sized by seat
  count.
- **Seats**: each seat has a transform (position and yaw) around the table. Seat-local
  frame: +x to the player's right, +y away from the player.
- **Battlefield positions stay seat-local** (the engine's existing virtual 1000 × 600
  frame). The renderer maps them onto the seat's battlefield rectangle.
  - Values outside 0–1000 / 0–600 are legal, so a card can sit anywhere on the table,
    including the shared middle, without changing control.
  - Dropping a card inside *another* player's battlefield rectangle gives them control
    (the existing semantics).
- Piles (library, graveyard, exile), the command zone and the hand area have fixed
  seat-local anchors defined by the **table preset**. Presets are data (§5), not code.
- `rotation` (free, degrees) is separate from `tapped` (+90°). `flipped` means rotated
  180° (Kamigawa). `face_down` means card back up. `face` is the active printed face
  (transform/MDFC). These are four distinct concepts.

## 4. Client architecture

```
frontend/src/
  table3d/
    TableScene.ts      scene, renderer, render-on-demand loop, resize
    layout.ts          presets: seat transforms, zone anchors, seat-local ↔ world
    CardObject.ts      one card: mesh, textures, face/back, tap/flip/rotation tweens
    PileObject.ts      library/graveyard/exile piles (height ∝ count), stack badges
    textures.ts        texture cache (LRU), lazy image loading, canvas text-card fallback
    camera.ts          orbit/pan/zoom, WASD, presets 1–7, focus (F), transition speeds
    picking.ts         raycasting, box select, drop-zone resolution
    interaction.ts     drag with lift, group drag, snap (off/light/normal); emits gestures only
    sync.ts            diff incoming views → create/update/remove objects
  input/
    intents.ts         gesture → rules intent or sandbox action (shared by 2D and 3D)
    actions.ts         central action registry (id, label, handler, availability)
    bindings.ts        editable key bindings (persisted), controller-ready intents
  game/…               existing overlays reused (menus, dialogs, panels, log)
  overlays/            card toolbar, inspector, search overlay, history, palette, screen hand
```

Principles:
- **One action registry** feeds hotkeys, the command palette, context menus, the card
  toolbar and card macros. Nothing checks raw keys or mouse buttons outside `input/`.
  That keeps controller / Steam Deck support possible later.
- **Render on demand.** The scene renders only while something animates, the camera
  moves or a drag is active. An idle table costs ~0 CPU/GPU.
- **Performance levers**:
  - shared geometry and materials; texture LRU with lazy loading;
  - logical token stacks (one object for "Treasure ×27");
  - instanced card backs for libraries and hands;
  - UI virtualization in search.

## 5. Engine / data-model changes

✅ **Built** (milestones 12–13), all as optional fields with save migrations. The rules
engine adds its own `GameState.rules` separately (see `ARCHITECTURE.md`).

| Field / action | Purpose |
|---|---|
| `CardInstance.rotation` + `rotate` | Free rotation independent of tapping |
| `locked`, `protected` + `set_lock`, `set_protect` | Locked cards can't move. Protected cards can't be deleted, stacked or merged without an explicit `force`. Commanders default to protected. |
| `attached_to` + `attach` / `detach` | Equipment, auras, cards exiled under another permanent. Moving the parent moves its attachments; detach keeps the position. Persisted, so it survives undo, saves and sync. |
| `group` + `group` / `ungroup` | Temporary piles: dragging one member moves all of them |
| `quantity` + `stack_adjust`, `split_stack`, `expand_stack`, `merge_tokens` | Logical token stacks ("Treasure ×17") |
| `PlayerState.mana` + `add_mana`, `clear_mana` | Temporary mana pool (optionally emptied on step change) |
| `macro` action | Runs a validated list of primitive steps as **one** undoable history entry |
| Macro library | Macros saved per card (by Oracle id, so every printing shares them) or in a personal library, in `app.sqlite` |
| `GameSettings.undo_policy` | everyone / own actions / host only |
| `GameSettings.clear_mana_on_step` | Convenience, default off |

View changes: views gain the new fields. Hidden cards still expose only public
geometry: position, rotation, tapped, attachments, counters.

## 6. Undo and history ✅ built

With automation on, one rules intent (cast + costs + triggers + SBAs) is one history entry,
so Undo takes back the whole play.

- The history panel lists every applied action with turn, time, actor and a
  human-readable summary (rendered per viewer, so hidden cards stay hidden).
- **Restore to here** moves the cursor back to any earlier action. It's one history
  operation, redo-able, and logged with who initiated it.
- `undo_policy` is checked server-side:
  - `everyone`;
  - `own` (you can only undo while the action being undone is yours);
  - `host` (in LAN games only the host seat token can undo).

## 7. Migration plan

0. **Prerequisite: the rules engine** (M14–M18 in `IMPLEMENTATION_PLAN.md`): intent protocol,
   core primitives, coverage, pod cards, and a rules-aware 2D client. The shared
   `input/intents.ts` module is proven on the 2D board first.
1. **Model**: ✅ done (the engine fields and actions in §5).
2. **3D surface**: `TableScene` renders the same views as the 2D board. A view toggle
   (3D / 2D) lets both run against the same server, so 3D can land incrementally
   without breaking play.
3. **Interaction**: drag with lift, drop zones, tap/flip/rotate, box select, group drag,
   camera presets. Every drop goes through `input/intents.ts`. Rules highlights and prompts
   are shown in 3D (targets glow, attackers slide forward, blockers snap to attackers).
4. **Overlays**: card toolbar, inspector (hold Space), private search overlay,
   screen-space hand (on/off/auto preference), history, command palette.
5. **Stacks and attachments** in 3D, then macros, targeting, pings,
   picture-in-picture.
6. When the 3D table covers every 2D feature, make it the default. The 2D view remains
   as a low-spec fallback.
7. **Tabletop toys** (dice objects, tray, token bags, a hidden draw bag with the same
   per-viewer privacy as libraries). Their results are resolved on the server and recorded,
   and the visual physics is cosmetic.

## 8. Status

- **Rules engine:** see `IMPLEMENTATION_PLAN.md` (M14–M18). It is next.
- **3D renderer and toys:** not started. They begin after the rules-aware 2D client (M19).
- **Per-feature table QoL status:** `docs/TTS_QOL_RESEARCH.md`.
