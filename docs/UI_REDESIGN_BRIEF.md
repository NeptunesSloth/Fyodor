# Brief: full UI / 3D tabletop redesign (done in rounds)

Requested 2026-10-03 as the brief for the redesign, which was built in PR #35's rounds (`UI_REFERENCE_STUDY.md` §20–31). When the
redesign starts, this file is the instruction set; the related plans it pulls together are:

- end-of-game scenes and the post-game flow: `3D_DIRECTION.md` §7a;
- the game-night / match flow (persistent pod, d20 turn order, rematch vote, recap): `GAME_NIGHT_FLOW.md`;
- the elimination activity hub: `ELIMINATION_HUB.md`;
- the 17 tabletop quality-of-life features: `TABLETOP_QOL_MILESTONE.md`.

## Skills and workflow

Use **both** skills, with different jobs:

- **`frontend-design`** is the **primary** design/implementation skill: visual direction, layout,
  hierarchy, component design, tabletop composition, responsive behavior, interaction design, 3D
  presentation, visual identity.
- **`impeccable`** (installed in `.claude/skills/impeccable/`) is the **critique / refinement** layer.
  After each meaningful UI pass, use it to review hierarchy, spacing, typography, visual balance,
  density, consistency, accessibility, motion, interaction clarity, responsive behavior, visual polish,
  and generic-AI/SaaS-looking elements.

Both are repo-local skills: `.claude/skills/frontend-design/` (from `anthropics/skills`) and
`.claude/skills/impeccable/` (from `pbakaus/impeccable`). Product context for Impeccable is in
`PRODUCT.md` at the repository root (written by `/impeccable init`).

**3D renderer rule.** Fyodor already has a plain three.js renderer (`frontend/src/table3d`). Preserve it and
improve it in place, reusing its infrastructure wherever sound. Don't introduce React Three Fiber, Drei,
Rapier or any other 3D framework because a skill demonstrates it: skills are guidance, not architecture.
Any new runtime dependency needs a concrete need the current stack can't reasonably meet. The vanilla
three.js skills in `.claude/skills/threejs-*` (core, geometry, materials, lighting, camera, animation,
postprocessing, loaders, performance, shaders) are reference material for that work; ignore their
React/R3F sections.

Never let both skills independently redesign the same screen from scratch. The loop is:

```
CURRENT UI → frontend-design direction → implementation → impeccable critique/audit
          → targeted fixes → verify in the actual running application
```

Per major screen/system:

1. **Frontend design:** decide and implement the visual/interaction solution.
2. **Impeccable:** critique/audit the *implemented* UI: generic AI UI, weak hierarchy, excessive
   containers, spacing inconsistency, typography problems, bad density, inaccessible contrast, bad
   interaction states, visually disconnected controls, excessive decoration, poor responsive behavior,
   motion problems.
3. **Fix** the concrete findings. Don't apply suggestions that conflict with the game-client/tabletop
   direction.
4. **Real app:** inspect the actual running UI; never judge from JSX/CSS alone.

Use `frontend-design` aggressively for creation and `impeccable` aggressively for critique. Don't only
describe what should change: implement it, run it, inspect it, critique it, refine it, verify it.

## The product

Fyodor is a private LAN/offline Commander simulator. Target experience:

- **Tabletop Simulator** physical freedom
- **MTG Arena**-level rules assistance
- **Master Duel**-style response/priority clarity
- a **dark physical Commander table** aesthetic

It should feel like a **game client**, not a SaaS dashboard, an admin panel, a generic React template,
a crypto dashboard, a Discord clone, an AI-generated website, or a card database with a battlefield
bolted on. **The tabletop is the primary interface.**

## Before changing anything

Inspect the existing application first: frontend architecture, current components, the 2D tabletop,
the 3D table (`frontend/src/table3d`), state management, the WebSocket/game-state architecture,
interaction handlers, design tokens/theme (`frontend/src/theme`), screenshots/assets, and current
responsive behavior. **Run the UI** and look at it at realistic desktop resolutions. Don't redesign from
assumptions; preserve what works.

Write a short design assessment: (1) what works visually, (2) what feels generic or unfinished,
(3) what should remain, (4) what should be redesigned, (5) what 2D and 3D can share, (6) major
interaction risks. **Then implement** — don't stop at the document.

## Visual direction

A premium physical Commander table: dark wood, dark felt / leather-like surfaces, blackened metal,
restrained brass / warm gold, subtle texture, physical depth, soft directional lighting, tasteful
shadows, realistic card elevation, subtle seat-color accents. Brass/gold is restrained emphasis, not a
glow everywhere.

Avoid: neon cyberpunk, excessive glow, glassmorphism everywhere, giant gradients, oversized rounded
SaaS cards, unnecessary sidebars, excessive floating panels, fake futuristic HUD clutter.

## Systems

**The table dominates.** During play the tabletop takes roughly 85–90%+ of the visual attention.
Minimal permanent chrome; prefer hover, contextual and radial menus, compact toolbars, temporary
drawers, card-adjacent controls, keyboard shortcuts and selection-based controls over permanent side
panels, multiple fixed toolbars or giant HUD containers.

**Player areas.** Compact, integrated into the table, subtle seat colors. At a glance: name, life,
commander, commander-damage access, poison when relevant, active player, priority, connection state,
eliminated state. No large rectangular dashboards.

**Ownership vs control.** Distinguish owner and current controller (especially stolen permanents): a
small owner seat-color marker, a subtle controller accent/border, tooltip text on hover. Never recolor
the whole card; never rely on color alone.

**Cards.** Physical but readable: hover lift, selected elevation, drag depth, tilt, tap animation, flip,
face-down state, DFC behavior, stack overlap, grouping, fan behavior, clean snapping. Usability beats
exaggerated physics.

**Hand.** A slight fan, cards large enough to recognize, hover lift, the selected card comes forward,
smooth horizontal navigation, doesn't hide the battlefield needlessly, can collapse/minimize. Private
hand information stays private.

**Card inspector.** Contextual, not permanently huge: hover = light preview, select = stronger preview,
pin = persistent inspector, easy to close/collapse; comparing two cards later if the architecture allows.
The table stays visible.

**Contextual card actions.** A compact tabletop-like control for the selection (Tap/Untap, Flip, Counter,
Move, Exile, Sacrifice, Attach, Copy, Note, Inspect): a dark metal / leather toolbar or a small radial
menu, never giant buttons around every card.

**Choice memory, notes, attachments, token piles, combat lanes, private drawer, public choices,
commander damage, focus hotkey, auto-center:** as specified in `TABLETOP_QOL_MILESTONE.md` (compact
chips for X / KICKED / MODE / CHOSEN COLOR / CHOSEN TYPE / COMMANDER CAST #; manual notes visually distinct
from engine status; subtle attachment lines shown on hover/selection with an optional always-show;
identical tokens as logical piles that split when state diverges; a temporary combat lane view that
restores positions; the private choice drawer with "WAITING FOR PLAYER 2" for everyone else; radial or
compact pickers for public choices; commander damage on hover with the 21 threshold obvious; **F** to
focus and **F**/**Esc** to return; auto-center Off / Important only / On, subtle, cancelled by input,
respecting reduced motion).

**Battlefield organization.** Both physical freedom and optional organization: free positioning,
snapping to sensible areas, row, grid, fan, stack, spread, multi-select, group. No rigid Arena-style
battlefield; help without taking control away.

**Stack / priority.** Always answer *who has priority?* and *what is the game waiting for?* with compact
indicators ("YOUR PRIORITY", "WAITING FOR PLAYER 3", "PLAYER 2 CHOOSING BLOCKERS"). The stack shows
order, source, controller, targets, modes, X, copies and pending responses, and collapses many similar
triggers compactly.

**Camera / 3D.** Pan, zoom, orbit, focus, smooth reset, whole-table, seat/player, stack and combat views.
Camera bookmarks if the architecture fits (1 My board, 2 Opponent left, 3 Opponent across, 4 Opponent
right, 5 Whole table).

**Game start, game end, spectators, post-game, persistent pod, recap:** as specified in
`GAME_NIGHT_FLOW.md`, `3D_DIRECTION.md` §7a and `ELIMINATION_HUB.md`: a 3-2-1 countdown, a short
commander intro (player, commander, art), the turn-order reveal (game 1: visible authoritative d20 rolls,
ties resolved; later games: the previous winner goes last; a reroll after a draw), then mulligans — all
short. End scenes of 1–3 seconds that keep the battlefield visible (Victory: slight dim, restrained
brass/gold emphasis, the winner highlighted, tiny particles at most; Defeat: restrained darker/red; Draw:
neutral/silver; Eliminated: a quick dark pulse, "Game continues", then Spectate / Practice table / Deck
lab). Spectators always have Return to live game and restrained, rate-limited reactions with no hidden
information. Post-game: Rematch — same decks / Return to lobby / View final board, with a rematch vote;
deck changes only in the lobby. The pod persists across games (players, seats, cosmetics, lobby
configuration, selected decks, pod identity), never match state. A casual, tasteful session recap — not
esports statistics.

**3D table.** Physical but controlled. Priorities in order: card readability, interaction reliability,
performance, spatial clarity, visual beauty. No chaotic full physics; controlled movement; rules state
stays authoritative.

**Materials and lighting.** A substantial table: dark walnut, aged wood, felt play areas, leather trim,
dark steel, brass details. Warm overhead/environment light, soft card shadows, subtle contact shadows,
enough contrast for card art.

**Background.** The game space is an environment, never an empty gray app background. **Not** the
plane-themed tables yet: build a strong neutral default table first.

## Responsive, performance, 2D, accessibility

- **Responsive:** desktop game night first. Don't destroy table space at 1080p. Test at least
  1920×1080, 2560×1440, ultrawide if practical, and a laptop viewport; controls collapse intelligently.
- **Performance:** test realistic boards (100 visible, 300 visible, 500+ logical objects). Token piles
  must reduce render cost. Avoid needless React rerenders, hundreds of always-on animations, heavy
  postprocessing, shadows everywhere, needless DOM overlays and needless Three.js object creation.
  Measure before adding expensive effects.
- **2D fallback:** never removed or broken; important interactions stay available. Rules behavior never
  depends on the renderer; 3D is presentation and the server stays authoritative.
- **Accessibility:** reduced motion, readable contrast, keyboard actions, clear selected/focused states,
  non-color indicators, scalable text where reasonable. Seat colors are never the only indicator.

## Visual testing

Capture screenshots of the **real running app** during development and use them for critique: (1) empty
battlefield, (2) normal four-player game, (3) large Commander battlefield, (4) card selected, (5) hand
expanded, (6) stack with several objects, (7) combat, (8) private choice, (9) token pile, (10) stolen
permanent, (11) eliminated spectator, (12) victory/result screen, (13) lobby between games. Never present
mockups as the application.

## Phases

Never one huge unreviewed patch.

- **A — Design system + table shell:** colors, typography, spacing, table materials, player areas,
  overlays, the contextual control language, shared UI primitives.
- **B — Core tabletop:** cards, hand, selection, dragging, snapping, grouping, token piles, attachments,
  ownership/control.
- **C — Rules UX:** stack, priority, choices, X/modes, private drawer, pending decisions, combat lane view,
  commander damage.
- **D — 3D / camera:** physical card presentation, camera, focus, interaction depth, auto-centering,
  performance.
- **E — Game flow:** countdown, commander intro, d20 order, elimination, spectator experience, winner
  spotlight, rematch, persistent lobby, recap.

After every phase: targeted tests, a frontend-design review as needed, an Impeccable critique/polish,
real screenshots, regression fixes.

## Don't

Rewrite working rules systems unnecessarily; change the server authority model; expose hidden
information; turn the app into a dashboard; add giant sidebars; add neon everywhere; make everything
glassmorphic; add unnecessary dependencies; replace working functionality for looks alone; make 3D
mandatory; silently remove manual tabletop freedom; let animations block gameplay; trade performance for
particles/postprocessing; update `CURRENT_STATE.md` unless the user says so.

## Success criteria

It immediately looks like a polished tabletop/card-game client; the table dominates; cards feel
physical; large Commander boards stay readable; priority and decisions are obvious; private decisions
stay private; 3D makes interaction easier, not harder; repeated games flow naturally; the visual design is
consistent; nothing resembles a generic AI-generated SaaS dashboard; the rules engine stays
authoritative; the 2D fallback works; performance holds up in real four-player Commander games.
