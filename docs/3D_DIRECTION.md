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

## 0. Status (M19, 2026-09-29): the 3D table is built

`frontend/src/table3d/` renders the table with three.js, driven only by the per-viewer view:

- **Seats:** each player's mat faces its owner (south = you, then clockwise), 2–6 players.
  Library, graveyard, exile and command zone sit beside each mat; opponents' hands are fans of
  card backs (a count, nothing more); the stack hovers over the centre of the table.
- **Cards** ease to where the server says they are (tapped = turned 90°, attacking = lifted).
  Faces are the cached card images, or a readable text card offline; hidden cards arrive
  without identity and are drawn as backs. Card bodies are one instanced draw call.
- **Gestures** reuse the 2D table's actions: drag (with Alt as the manual override), double-click
  to tap, right-click for the card menu, click-to-target, pick mode, drag from the hand onto
  the 3D table (a drop resolver on the canvas). Rules intents behave exactly as on the 2D table.
- **Camera presets:** your seat, the whole table, or any opponent's side; wheel to zoom,
  middle-drag to turn.
- **Overlays stay DOM:** seat plates (portrait, name, life; click for the full player panel),
  the hand, the automation HUD, prompts, the stack panel and the card preview.
- **Fallback:** Settings → Table: AUTO (3D when WebGL works), 3D or 2D. Without WebGL the 2D
  table is used automatically; automated browsers default to 2D unless they opt in.
- **Tests:** `e2e/table3d.spec.ts` (drag from hand, right-click → Tap, camera presets) and a
  draw-call budget check on a four-seat board (about one call per card face plus a fixed
  environment). Frame rate is logged but not asserted: CI renders WebGL in software.

### Table themes: Magic planes

A theme is a plane (`frontend/src/theme/planes.ts`). One definition drives the UI accent
tokens, the sky, fog and lighting, the table surface, props around (never on) the play area,
drifting particles and a synthesised ambience. Everything is procedural: no downloaded art,
works offline, and every theme keeps cards, counters and prompts identical.

| Wave | Planes |
|---|---|
| 1 | **Dominaria** (default: oak, brass, candles, a Tolarian study), Ravnica (slate, lanterns, gothic spires), Innistrad (weathered wood, fog, a pale moon), Theros (marble, columns, Nyx starfield), Zendikar (stone, jade, floating hedrons) |
| 2 | Kamigawa (red lacquer, torii, neon), Amonkhet (sandstone, obelisks, pyramids), Ixalan (jungle, gold), New Phyrexia (oil-slick metal, spikes, pipes), Lorwyn (meadow, mushrooms, willows) |

The theme is a per-player preference (Settings → Table theme, or the arrows on the launcher);
ambience volume is Settings → Sound → Ambient.

### Dice

Every public roll or coin flip (the server's `roll` / `coin` actions, rolled on the host and logged) is thrown as real
dice, on the 3D table, over the 2D table and in the elimination hub's toy tray:

- **The dice** (`table3d/diceGeometry.ts`): d4, d6 (pips), d8, d10 (0–9), d12, d20, a d100 as a tens die (00–90) plus
  a d10, a d3, and a thick coin (struck relief, milled rim). Rounded edges (the solid shrunk by the bevel and grown
  back by a sphere); standard numbering (opposite faces sum to n + 1, a d10's evens round one apex, a d4 numbered at
  its points and read at the top); 6 and 9 underlined. Numbers and pips are engraved and inked: one normal-map + ink
  atlas per kind, drawn once (`diceArt.ts`).
- **The number is the server's**: the physics decides how a die tumbles and which face lands up; the die is drawn
  turned by the rotation of its own symmetry group that carries the face showing the server's number onto that face
  (`faceTurn`), so it tumbles exactly as simulated and lands right. Nothing is printed on whatever face comes up.
- **The throw** (`diceThrow.ts`, cannon-es): from the roller's hand over the near edge of their mat, an arc and a
  tumble onto its far half, knocking each other and glancing off the roller's piles; settles in about 1–2.5 s. A die
  that ends cocked, sunk or off the mat is thrown again with the next seed, or eased flat. The simulation runs in the
  roller's mat frame against an environment every screen builds alike, seeded by the log entry: every screen sees the
  same throw, and the 2D table lands that throw on its own mat.
- **Look** (`diceLook.ts`): the roller's seat colour, ivory or soot ink for contrast; Settings → Dice picks glossy
  resin (default, clearcoat), marble swirl (solid noise in the die's space), enamelled metal or gemstone (a dark glossy
  cut stone with an iridescent sheen; no refraction pass: dice stay out all turn, and refraction redraws the whole
  table every frame). Real shadows from the table's key light plus a contact shadow.
- **Readable**: at rest a chip over each die and a line by the roller ("Bob · 2d6: 3 + 6 = 9"), crisp DOM
  (`diceHud.ts`); a d20's natural 20 (gold) or 1 (ash red) gets a ring and a tag; dice the rules ignored (706.6,
  Barbarian Class) are greyed, their chips struck through, and left out of the total.
- **They stay** until the roller rolls again, someone clicks them (or their line) away on their own screen, or the
  turn ends: a roll usually decides something for the rest of the turn, and no longer, so dice don't pile up on cards.
- **Sound** (`game/diceSound.ts`): each recorded impact plays a synthesised clack as the throw reaches it, by how hard
  it hit (felt thud, resin knock, leather rail, deck, coin ring), on Settings → Sound → Dice; silent when muted.
- **2D table** (`game/DiceLayer.tsx`): the same 3D dice in a transparent overlay (`table3d/diceOverlay.ts`, loaded
  with the first roll, drawing only while dice move); without WebGL or on low graphics, drawn dice
  (`game/DieGlyph.tsx`) tumble in and rest with their numbers up.
- **Rolling** (`game/DicePanel.tsx`): the tool tray's Dice button or Shift+R opens a compact panel: d4–d20, d100, a
  coin and a count, quick picks (1d20, 2d6, a coin), any XdY, and the table's last rolls with Again.
- **Cost**: one draw call per die (plus its shadow and contact shadow), ~1–1.5k triangles each; geometry, atlases and
  materials cached and freed with the last tray; a typical throw simulates in 5–20 ms, 12d20 in ~90 ms; reduced
  motion shows the dice at rest, animation speed scales the throw. Tests and screenshots freeze a throw at a set time
  (`window.__fyodorDice.freeze`): headless software WebGL draws about a frame a second.

Still to come: cannon / Bag of Extras as physical objects, token piles as stacks,
card flip and shuffle animations, hands in TABLETOP mode.

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
- **Animations never gate input.** RESPOND / STOP / HOLD PRIORITY are sent the moment they are
  pressed (`set_prefs`, accepted at any time, with or without priority); the server registers
  them immediately and the scene animates afterwards to catch up. Rules timing never waits for
  an animation to finish.
- **Renderer per player.** The 2D table stays a first-class renderer; players in the same
  authoritative game may use 3D or 2D (weak hardware, no WebGL, preference).
- **Automation HUD and prompts** come from `view.rules` (status, prefs, decision, hints,
  reconcile list, failure); see `AUTOMATION_UX.md`.

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
7. **Tabletop toys** (dice objects — done, see "Dice" above —, tray, token bags, a hidden draw bag with the same
   per-viewer privacy as libraries). Their results are resolved on the server and recorded,
   and the visual physics is cosmetic.

> The full redesign brief that pulls these plans together is `UI_REDESIGN_BRIEF.md`.

## 7a. Planned: end-of-game scenes (late-stage, not started)

Requested 2026-10-03 for the 3D redesign. It is late-stage presentation work, like the other polish
items: build it after the rules work, as part of the 3D redesign. The feel to reference is Teamfight
Tactics' victory/defeat presentation, made much simpler, faster and cheaper to render. **It is not a
cinematic.**

Flow: **game ends → table reacts → result appears → player chooses what to do next.**

**Core presentation.** Use the existing tabletop as the scene, never a separate full-screen
environment. When the result happens:

1. briefly disable unnecessary table interaction;
2. subtly dim or tint the tabletop;
3. make a small camera ease toward the center of the board;
4. play a short visual pulse / particle effect;
5. reveal the result text;
6. reveal a small result panel;
7. let the player inspect the final table afterward.

The whole dramatic sequence takes roughly 1–3 seconds.

| Result | Sequence | Camera | Particles |
|---|---|---|---|
| **Victory** (satisfying, warm, premium, restrained) | table darkens slightly → warm gold/brass light pulse across the battlefield → very few gold particles/sparks → "VICTORY" appears prominently → result panel fades in. Optional: a tiny commander/card emblem behind the text, a short victory sound sting. | slow 2–4% push toward the table center (optionally a subtle upward move) | small gold dust/sparks |
| **Defeat** (understated; the final battlefield stays visible, no destruction animation) | table dims → restrained dark/red pulse → "DEFEAT" → result panel | very slight 2–4% pull-back | a few dark/red embers |
| **Draw** (calmer than victory or defeat) | brief neutral desaturation / silver pulse → "DRAW" → short explanation if known → result panel | almost stationary | a few neutral/silver particles |
| **Eliminated** (Commander-specific: the local player lost but the game continues; shorter and less dramatic than Defeat) | brief dark pulse → "ELIMINATED" → "Game continues" → immediately offer **Spectate** / **Leave game** | small pull-back | little or none |

Elimination must **not** end the match UI for the other players: only the eliminated player sees it. After the scene, the
eliminated player gets the activity hub planned in `ELIMINATION_HUB.md` (Spectate, Practice Table, Opening Hand
Simulator, Deck Lab).

**Result panel** (compact, never a dashboard), for example:

```
VICTORY
Player 1
Atraxa, Praetors' Voice
Turn 11
[REMATCH — SAME DECKS]  [RETURN TO LOBBY]  [VIEW FINAL BOARD]
```

Optional smaller actions: game log, pod stats.

**Post-game flow (requested 2026-10-03; the game-night milestone in `GAME_NIGHT_FLOW.md` turns Rematch into a pod vote).** Deck changes happen **only in the existing lobby**. There is no
separate "Change decks" screen after the match, and the result panel never duplicates lobby functions.

```
Lobby → Game → Result → Rematch — same decks
Lobby → Game → Result → Return to lobby → change decks / ready up → Start next game
```

- **Rematch — same decks** starts a completely fresh Commander game with the same players, seats,
  decks, commanders, lobby configuration, mulligan policy and the appropriate automation/player
  settings. All match state is reset, and it gets a new game/result record.
- **Return to lobby** takes the whole pod back to the existing lobby, with everyone still connected to
  the room (nobody leaves and rejoins). Each player's previous deck is selected by default, for example
  "Player 1 — Atraxa — not ready". Players who keep their deck do nothing. Others use the normal lobby
  controls: keep the deck, choose another saved deck, import/paste a deck, choose another commander,
  change deck privacy, ready/unready, and any pre-game setting the lobby allows. When everyone is
  ready: **Start next game**.
- **View final board** keeps the finished table inspectable.
- Eliminated players who are in another activity when the game ends get the same three choices
  (`ELIMINATION_HUB.md`); they change decks after returning to the lobby.

**Visual style.** Match Fyodor: dark tabletop, warm brass/gold, blackened metal, dark wood/felt,
restrained typography, a physical card-room feeling. Avoid neon UI, rainbow gradients, giant glowing
buttons, generic SaaS modal styling, confetti covering the screen, giant explosions, excessive
particles, and anything that looks like a mobile-game reward screen.

**Rules for the implementation.**

- Camera motion is extremely small and **presentation only: it must never affect game state.** Reduced-motion
  settings disable it (and the pulses).
- Particle counts are very low; effects finish quickly and clean themselves up. Don't add an
  expensive particle engine: use the CSS/WebGL primitives already available, simple overlays and
  transforms.
- It must also work in the 2D fallback renderer.
- Sound: prepare hooks for short victory / defeat / draw / eliminated sounds. Audio is optional and
  nothing may depend on it. (The request was cut off at "Do not require audio for"; confirm the rest
  of that sentence before building.)
- The result comes from the server's game state (game over / player lost), never from the client
  guessing, and it shows no hidden information.

## 8. Status

- **Rules engine:** see `IMPLEMENTATION_PLAN.md` (M14–M18). It is next.
- **3D renderer and toys:** not started. They begin after the rules-aware 2D client (M19).
- **Per-feature table QoL status:** `docs/TTS_QOL_RESEARCH.md`.
