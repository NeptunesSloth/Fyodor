---
target: in-game table, card-attached selection toolbar, pings, hand sorting, turn alert (2D and 3D)
total_score: 26
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 1
target_identity: "file:/home/user/Fyodor/frontend/src/game/Hud.tsx"
target_fingerprint: "sha256:cbe317981255790c2c40efcdb02296fdd5cda8ef9dfe9d6fb4d2a449d2520bfc"
target_path: /home/user/Fyodor/frontend/src/game/Hud.tsx
timestamp: 2026-10-31T02-08-10Z
slug: frontend-src-game-hud-tsx
---
# Critique: the new table pieces (round 1)

Method: dual-agent (A: isolated design review of source and six screenshots · B: detector plus a read-only browser
pass). Scored before the fixes below. Earlier 3D-screen rounds (39/40) covered the whole 3D screen with a different
rater; this round scores the new pieces and the 2D table too, so the numbers don't compare directly.

## Score: 26/40 (Acceptable)
H1 3 · H2 3 · H3 3 · H4 2 · H5 2 · H6 2 · H7 3 · H8 3 · H9 3 · H10 2

## Detector
Exit 0, 0 findings (regex-only TSX scan; the element rules need a URL scan, not run).

Browser pass (Play, Settings):
- 4 unnamed form controls on Play
- ✕ and ⇩ buttons named by glyph
- `.btn.small` 23 px tall
- autobackup `code` at 4.15:1

## Priority issues and what happened
- [P1] Toolbar actions ignored card type and were ambiguous (+1/+1 vs a temporary pump) → **fixed**: creatures get
  Tap / +1/+1 counter (right-click removes) / Damage…; other permanents get Counter…; Turn over for double-faced
  cards; shortcut keys in titles; at most 4 plus More….
- [P2] 3D selection used priority ice (DESIGN.md reserves ice for "you may act now") → **fixed**: brass edge glow and
  a brass name tag; the tag under the toolbar's own card is hidden.
- [P2] Toolbar and pings ignored fixed controls and off-screen cards → **fixed**: the toolbar steps to the card's
  other side when the dial, response bar or stack would cover it, and hides when its card is off-screen; off-screen
  pings pin to the edge with a dashed ring, and screen readers hear "pinged Sol Ring".
- [P2] Turn alert missed an unfocused window (second monitor) → **fixed**: hasFocus() plus a focus listener.
- [P2] A sorted hand refuses manual reordering → **open** (the toast explains; a "My order" mode is the follow-up).
- Detector/browser findings → **fixed**: aria-labels, `.btn.small` min-height 24 px, code contrast.

## Open
- The 2D table reads as a grid of stat panels (players' panels in columns).
- Pings and sorting aren't discoverable on the table.
- Counters go up one click at a time.
