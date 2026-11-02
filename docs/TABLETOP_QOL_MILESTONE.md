# Milestone plan: tabletop quality of life (15 of 17 built)

Requested 2026-10-03. **Build it after the core rules engine and the primary 3D table are stable.**
Status (2026-11-01): 15 of the 17 aids are built; the quick undo request (#7, approval) and the public choice wheel (#12) are not. `IMPLEMENTATION_PLAN.md` lists each. Don't redesign the app: the goal is to make a real Commander game faster,
clearer and less annoying to operate.

**Preserve:** the authoritative server state, privacy, manual tabletop freedom, rules automation, the
2D fallback and performance.

**One system, not seventeen widgets:** contextual overlays, compact status badges, hover/focus behavior,
subtle seat colors and a minimal permanent HUD. No new giant sidebar: the table stays the interface.

**Before building, check what exists.** `TTS_QOL_RESEARCH.md` tracks related features (undo/history and
undo policy, card notes, the Space inspector, attachments, groups, `F` focus and camera presets,
commander tracking). Some of its statuses predate later work; read the code, extend what exists, and
don't build a second version of anything.

## Build order and PRs

Build in roughly this order, as coherent PRs over shared primitives (never one giant unreviewed
commit):

| # | Feature | Group |
|---|---|---|
| 1 | Private choice drawer | High game-night value |
| 2 | Pending decision indicator | High game-night value |
| 3 | Token pile collapse | High game-night value |
| 4 | Color-coded ownership / control | High game-night value |
| 5 | X / mode / choice visual memory | High game-night value |
| 6 | Commander damage hover | High game-night value |
| 7 | Quick undo request | High game-night value |
| 8 | Attachment lines | Table readability |
| 9 | Combat lane view | Table readability |
| 10 | Focus hotkey | Table readability |
| 11 | Auto-center important events | Table readability |
| 12 | Public choice wheel | Social / flow |
| 13 | Nudge current player | Social / flow |
| 14 | Spectator reactions / emotes | Social / flow |
| 15 | Start-game countdown | Social / flow |
| 16 | Temporary card notes | Social / flow |
| 17 | Session recap | Social / flow |

## The features

### Private choice drawer

Every private decision appears in a dedicated private drawer/overlay: choose a card from hand, library
search, look at the top N, discard selection, choose a hidden card, private cost payment. The drawer
says clearly what is required ("SEARCH YOUR LIBRARY — Find a creature card", the cards, CONFIRM), shows
only authorized information, keeps the table visible and supports confirm/cancel where legal. Other
players see only "Waiting on Player 2": no hidden options, no card metadata, no identities sent to
unauthorized clients.

### Pending decision indicator

Make it obvious who the game waits for: "WAITING FOR PLAYER 3 — Choose blockers", "WAITING FOR
PLAYER 1 — Resolve trigger ordering". Compact but very visible; nobody should wonder whether the game
froze. The deciding player sees **YOUR DECISION**, clearly highlighted.

### Token pile collapse

Large token armies render as logical piles (Treasure ×36, Zombie ×14) instead of 40 cards, without
losing any rules object's identity. A pile keeps what rules need: tapped/untapped groups, counters,
summoning sickness, attacking/blocking, distinct modifications. Piles split automatically when objects
stop being identical (Treasure ×20, tap 5 → Treasure ×15 + Tapped Treasure ×5); a token that gets
counters, equipment etc. leaves the pile. **Expand / Collapse.** Collapsed piles must improve
performance, not hurt it.

### Color-coded ownership / control

Owner and controller are visually distinct, especially for stolen permanents: a subtle owner seat pip
(e.g. bottom-left) and a controller border/accent. When owner equals controller, show only the normal
seat indicator; when they differ, make it obvious without recoloring the card. Hover shows "Owned by
Player 1 / Controlled by Player 3". Color is never the only signal: add icons, text and tooltips.

### X / mode / choice visual memory

Cards and stack objects remember important choices so players don't have to: X = 7, KICKED ×2, the
chosen modes, chosen color, chosen creature type, COMMANDER CAST #3. Small badges/chips on stack
objects, relevant permanents and the card inspector. Show only what is still rules-relevant; don't
clutter every card. The badges survive save/load (the engine already records most of these: cast
records, enters choices, kicker, X).

### Commander damage hover

Hover/focus a player: commander damage dealt to them per commander ("Player 1 / Atraxa: 8"). Hover a
commander: the damage it dealt to each opponent. The normal HUD stays compact; a full matrix only when
explicitly opened.

### Quick undo request

A lightweight **Undo last action** for the acting player. If the existing rules/history policy allows
a direct undo, it happens normally. If approval is needed, the others see "Player 2 requests: Undo Cast
Sol Ring [APPROVE] [DECLINE]", quick and non-intrusive. Never undo automatically: hidden-information
reveals, random outcomes players already saw, actions after substantial new public information, or
anything the history system marks unsafe. **The server decides** whether an undo is legal; clients
never rewrite authoritative history.

*Built* (`backend/app/game/undo_requests.py`, `frontend/src/game/UndoRequestBar.tsx`): at a LAN table, an undo the host's
undo setting refuses becomes **Ask to undo**, and so does, under every setting, an undo of an action that showed hidden
information or a random outcome (a draw, a look, a reveal, a search, a shuffle, a roll, a flip, a random pick: recorded on
the action as the server applies it, from what the table can see happened, never from which cards a private choice offers).
Like an agreed ending, every other seated player still in the game approves and one decline ends it; the server then
undoes it for the requester ("undid: … (with the table's approval)"). The requester can withdraw it; any change to the
table cancels it. Hot-seat tables undo directly, as before.

### Attachment lines

Subtle lines/arrows between an Aura / Equipment / Fortification and what it's attached to. Default:
visible while hovering or selecting either object, with an optional always-visible setting and reduced
opacity when not focused. Multiple attachments stay clean; no spaghetti. Visualization only: the
relationship stays server-side.

### Combat lane view

An optional, temporary combat presentation: attacker over its blocker(s), or clear horizontal lanes.
Useful with many attackers, multiple blockers, menace, planeswalker/battle targets and several
defending players. **Combat view on/off.** It never moves the players' layouts permanently; after combat
the cards return to their previous positions.

### Focus hotkey

Hover/select, then press **F**: the camera centers and zooms appropriately on a card, player, the
stack, a combat group or a token pile. **F** again or **Esc** returns to the previous view. Camera only,
never game state.

### Auto-center important events

Optional: gently focus the camera on significant public events (a large spell on the stack, a board
wipe, a commander cast, an elimination, big combats, a game-winning action), never routine draws, land
plays or minor actions. A small nudge only; any user input cancels it. Setting: Off / Important only /
On. Reduced motion disables movement.

### Public choice wheel

A fast wheel/radial/menu for **public** non-target choices with a reasonable option count: a color, a
creature type, a player, a number, heads/tails, one of several public options. Never for private
decisions. The choice remains a server-authoritative Decision.

### Nudge current player

A soft social reminder: "Player 2's turn [NUDGE]" → "Player 3 nudged you — waiting on your action."
With a cooldown, no spam, no loud or repeated sounds, a setting to disable it, and nothing usable for
harassment. Also a simple automatic idle hint after a configurable time ("Your turn."). No timer is
enforced unless the pod enables one separately.

### Spectator reactions / emotes

Eliminated spectators can react without disrupting the game: 👍 😂 😮 🔥 💀 👏, shown briefly near their
spectator/player indicator. Rate limited, muteable, no giant screen effects, no hidden information, and
spectators still can't interact with game objects.

### Start-game countdown

When the pod is ready and the host starts: 3, 2, 1, then the pre-game commander intro / turn-order
reveal (`GAME_NIGHT_FLOW.md`). Short, skippable where appropriate, presentation only, and it never delays
game initialization.

### Temporary card notes

Manual notes/markers on cards: "Stolen from Player 2", "Don't untap", "Until EOT", "Copied by Sakashima",
"Goaded", "Remember trigger", or custom text, with add / edit / remove and an optional small icon. Notes
are **table aids**: they change no rules unless attached to an existing rules-managed state. Keep them
visually distinct from engine-derived status. (Per-instance card notes already exist,
`TTS_QOL_RESEARCH.md`; extend them.)

### Session recap

At the end of a pod session, a lightweight recap: the session name, games played, total time, wins per
player, commanders and how many games each played. Optional: shortest and longest game, elimination
order, average turns, game-end reasons. Actions: **View games**, **Pod stats**, **Back to lobby**. A
casual recap only: no ranked matchmaking or MMR. It builds on the pod session / game split of
`GAME_NIGHT_FLOW.md`.

## Renderers

Core functionality works in both renderers where practical, and rules behavior never depends on the
renderer.

- **2D:** attachment arrows, pile labels, focus behavior, the private drawer.
- **3D:** physical piles, spatial lines, camera focus, combat lanes.

## Performance

Token piles, attachment lines, combat lanes and notes must work on large Commander boards. Test with
roughly 100 visible objects, 300 visible objects and 500+ logical objects.

## Privacy

Pay special attention to the private choice drawer, undo after hidden information, spectator mode and
pending decisions. Unauthorized clients must never receive private card identities or options.

## Tests

- an unsafe undo after a hidden reveal is rejected;
- a safe undo succeeds;
- X / mode badges persist through save/load;
- temporary notes don't affect rules;
- attachment visualization follows the attachment state;
- a token pile splits when one token changes;
- the combat lane view restores the original positions;
- commander damage hover values are correct;
- a public choice is visible to everyone where appropriate;
- a private choice is hidden from other clients;
- the focus hotkey changes only the camera;
- the pending decision names the correct player;
- the nudge cooldown;
- spectator reaction rate limit and privacy;
- skipping the countdown;
- a session recap over several games;
- ownership/control display after control changes.
