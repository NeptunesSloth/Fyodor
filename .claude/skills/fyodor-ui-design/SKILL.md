---
name: fyodor-ui-design
description: Fyodor's UI and 3D tabletop design rules. Use before any change to Fyodor's frontend look, layout, table, cards, hand, overlays, menus, 3D renderer, game-start/end presentation, lobby or spectator UI. Routes the work to frontend-design (creation), impeccable (critique) and the vanilla threejs-* skills, within Fyodor's product, privacy and renderer constraints.
---

# Fyodor UI design

Fyodor is a private LAN/offline **Commander** tabletop: Tabletop Simulator freedom + MTG Arena-level rules
assistance + Master Duel-style priority clarity, on a dark physical Commander table. It must feel like a
**game client**, never a SaaS dashboard, admin panel, React template or AI-generated site. **The table is the
interface.**

## Read first (sources of truth — don't duplicate them, follow them)

- `PRODUCT.md` — users (one pod, each player on their own computer over LAN, mostly veterans, sometimes new
  players), purpose, constraints, principles.
- `docs/UI_REDESIGN_BRIEF.md` — the full redesign brief: visual direction, every system, phases A–E,
  screenshot checklist, success criteria, the "Don't" list.
- Feature plans it points to: `docs/3D_DIRECTION.md` (renderer, §7a end-of-game scenes and post-game flow),
  `docs/GAME_NIGHT_FLOW.md`, `docs/ELIMINATION_HUB.md`, `docs/TABLETOP_QOL_MILESTONE.md`,
  `docs/AUTOMATION_UX.md`.
- Code: `frontend/src/theme` (tokens, `theme.css`, `planes.ts`), `frontend/src/table3d` (three.js table),
  `frontend/src/game` (2D table, rules UI), `frontend/src/state` (zustand).

## Hard rules

1. **Server is authoritative.** UI renders per-viewer state and sends intents; it never decides rules
   outcomes. Rules behavior never depends on 2D vs 3D.
2. **Hidden information never reaches an unauthorized client** — not in props, store, DOM, logs, hints or
   WebSocket payloads. Private choices go in a private drawer; others see only "Waiting for Player N".
3. **Keep the plain three.js renderer.** Improve `frontend/src/table3d` in place. No React Three Fiber, Drei,
   Rapier or other 3D framework; no new runtime dependency without a concrete need the current stack can't
   meet. Skills are guidance, not architecture.
4. **2D table stays first-class** and fully usable. 3D is optional presentation.
5. **Manual tabletop freedom is never removed** (free positioning, any zone move, notes, tokens, undo).
6. **Accessibility:** reduced motion honored, readable contrast, keyboard actions, visible focus/selection,
   never color alone (seat colors need icon/text too).
7. **Performance:** measure first; boards of 100/300 visible and 500+ logical objects must stay smooth; token
   piles must reduce cost; no always-on animations, heavy postprocessing or shadows everywhere.
8. Don't update `docs/CURRENT_STATE.md` unless the user asks.

## Look

Dark wood, felt/leather surfaces, blackened metal, restrained brass/warm gold, soft directional light,
physical card depth, subtle seat-color accents. Avoid neon, glow, glassmorphism, big gradients, rounded SaaS
cards, sidebars, floating-panel clutter, fake HUDs. Table ≈ 85–90% of attention; chrome minimal and
contextual (hover, selection toolbars, radial menus, drawers, shortcuts). Plane-themed tables come later —
build the neutral table first.

## Workflow (per screen/system)

1. Inspect the current UI **running** (`/run` or the e2e server; screenshot at 1920×1080, 2560×1440,
   laptop). Never design from JSX alone.
2. **`frontend-design`** decides and implements the solution (primary creative skill).
3. **`impeccable`** critiques the implemented UI (`/impeccable critique|audit|polish <target>`); fix concrete
   findings that fit the tabletop direction. `PRODUCT.md` is its context; run `/impeccable document` to
   record `DESIGN.md` before large changes.
4. 3D work: consult `threejs-*` skills (core, geometry, materials, lighting, camera, animation, loaders,
   performance, postprocessing, shaders; `threejs-aaa-graphics-builder` for visual quality,
   `threejs-debug-profiler` for perf, `threejs-qa-release` for canvas/visual checks). Ignore their React,
   physics-engine, scaffold and asset-generation advice.
5. Verify in the real app (screenshots from the brief's checklist), run `cd frontend && npm run typecheck &&
   npm test`, Playwright for flows touched, and backend leak tests when views/hints change.
6. Ship in phase-sized, reviewed commits; never one giant unreviewed patch.
