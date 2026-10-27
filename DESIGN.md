---
name: Fyodor
description: A private Commander card room — walnut table, petrol baize playmats, blackened steel and restrained brass.
colors:
  room-black: "#0b0c0d"
  room-black-2: "#121416"
  plaque-top: "#181a1c"
  plaque-bottom: "#0a0b0d"
  line: "#2a2d31"
  line-2: "#3e4247"
  walnut: "#3b2117"
  walnut-deep: "#1d0f0a"
  baize: "#152c33"
  baize-nap: "#21434c"
  brass-frame: "#8a6a3f"
  brass-hi: "#d7ae63"
  brass: "#d0a45a"
  brass-light: "#f0c97d"
  brass-ink: "#231605"
  parchment: "#eee5d3"
  parchment-dim: "#b5ad9e"
  parchment-faint: "#8f887c"
  priority-ice: "#7fb6ff"
  danger: "#e0645c"
  ok: "#7cc48f"
  attack-beam: "#ff5a2a"
  block-beam: "#5fa8ff"
typography:
  display:
    fontFamily: "Cinzel, Trajan Pro, Georgia, serif"
    fontWeight: 700
    letterSpacing: "0.02em"
  numeral:
    fontFamily: "Cinzel, Georgia, serif"
    fontSize: "28px"
    fontWeight: 700
  body:
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
rounded:
  chamfer: "8px"
  sm: "3px"
  md: "6px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "14px"
  lg: "24px"
components:
  plaque:
    backgroundColor: "{colors.plaque-bottom}"
    textColor: "{colors.parchment}"
    rounded: "{rounded.chamfer}"
    padding: "6px 14px"
  button-brass:
    backgroundColor: "{colors.brass}"
    textColor: "{colors.brass-ink}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  button-metal:
    backgroundColor: "{colors.room-black-2}"
    textColor: "{colors.parchment}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  tab-turn:
    backgroundColor: "{colors.brass}"
    textColor: "{colors.brass-ink}"
    padding: "3px 8px"
  tab-priority:
    backgroundColor: "{colors.priority-ice}"
    textColor: "#0b1a2b"
    padding: "3px 8px"
---

## Overview
A game client for one private Commander pod: Tabletop Simulator freedom, MTG Arena-level rules help and
Master Duel priority clarity. The table is the interface — about 85–90% of attention — and every overlay
is an object lying on or beside it, not an app panel. Materials come from a real card room: a dark walnut
table, a petrol-blue baize playmat per seat stitched in the seat colour, blackened steel, a little brass. Colour values above are the Dominaria (default) plane; every
plane maps the same roles (`theme/planes.ts` → `cssTokens()`), so roles, not hex values, are normative.

## Colors
- **Baize** is the play surface (3D mats, the 2D table); **walnut** is everything around it.
- **Blackened steel** (room black / plaque, `--steel-hi`/`--steel-lo`/`--hud-surface`) carries every overlay. Never brown panels.
- **Brass** is emphasis only: the primary action, the active turn, the selected card's edge. One brass
  thing per region. Brass buttons use a gradient whose darkest stop is computed per plane to keep
  `brass-ink` at ≥ 4.5:1 (`accentLow()`); faint text is lifted to ≥ 4.5:1 (`textFaint()`), both tested.
- **Priority ice** means "you may act now" and nothing else.
- **Beams:** attack orange-red, block blue, targets ice, other arrows brass — thin cords, never glowing.
- Never signal with colour alone: turn, priority, lethal, modified P/T all also say it in words or glyphs.

## Typography
Cinzel only where engraving makes sense: life totals, the phase name, card-room titles. Inter in
sentence case for everything else; no tracked-out all-caps labels. Minimum 11px for any text the player
must read; card text on the table relies on the inspector, not on tiny type.

## Layout
- The hand: a fanned arc rising from the bottom edge; the hovered card lifts clear.
- Seat plaques sit at each mat's edge, glued to the 3D table.
- The turn & priority dial sits bottom-right (Arena/Moxgate); the top bar is a thin strip.
- The stack is cards at the table centre plus a chain list beside them.
- Nothing covers another control; overlays clear the hand band.

## Elevation & Depth
Physical depth, not glow: cards have edges and soft contact shadows that spread as they lift; plaques
drop a single soft shadow (`.plaque-wrap`). No glows on buttons; the only emissive light on the table is
the arrows' beams and the target crystals.

## Shapes
Plaques are chamfered rectangles (8px cut) with a 1px brass edge that follows the chamfer (`.plaque`).
Buttons are 3px-rounded. Cards keep their real rounded corners. Circles are reserved for portraits and
keyword badges.

## Components
- `.plaque` / `.plaque-wrap` — the overlay surface (theme/theme.css).
- `.btn.primary` — brass; `.btn` — metal; `.btn.danger` — oxblood text.
- Seat plaque (`table3d/Table3D.tsx`): portrait, name, life numeral, Turn/Priority tabs, Cmdr/Poison/Hand.
- Card badges (`table3d/textures.ts cardOverlayCanvas`): P/T plate with ▲/▼, keyword glyph badges, counters.
- Beam arrows (`table3d/arrows.ts`).

## Do's and Don'ts
- Do say what a button will do ("Resolve top", "To combat"), and keep that name through the flow.
- Do keep every overlay off the hand band and off other controls.
- Don't add neon, glassmorphism, gradient washes or glows; don't use grey web panels.
- Don't rely on colour alone; don't use all-caps labels.
- Don't let animation delay an action; honour reduced motion.
