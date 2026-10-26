---
target: 3D game screen
total_score: 30
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 1
target_identity: "file:/home/user/Fyodor/file:/home/user/Fyodor/frontend/src/table3d/Table3D.tsx"
timestamp: 2026-10-26T20-57-54Z
slug: r-fyodor-frontend-src-table3d-table3d-tsx-84a20c4c
---
# Critique round 4: the whole 3D game screen

Provenance: the same isolated rater A as round 3, re-scored against its own round-3 baseline. Reviewer B's round-3 detector fixes are applied: tab order, .td-group contrast, cam-chip size, portrait ring. Full e2e: 24 passed.

## Score: 30/40 (+2)
H1 3 · H2 3 · H3 3 · H4 3 · H5 3 · H6 3 (+1) · H7 3 · H8 3 · H9 3 (+1) · H10 3

## Priority issues
1. [P1] Seat plaques cover battlefield cards on laptop. The avoidance list only covers fixed chrome (table3d/Table3D.tsx:77).
2. [P2] The coach tip overlaps the command-zone card at 1366 wide (table3d/table3d.css:78).
3. [P2] The attack beam ends under the Turn tab (TableScene.ts syncArrows).
4. [P2] There is no hotkey for the dial's primary action in manual play (game/hotkeys.ts:35-55).
5. [P3] At 1080p a plaque reaches the right viewport edge (Table3D.tsx:84-92).
6. [P3] On-card badges are below 11px on screen (table3d/textures.ts:322,337).

## Next anchors (what moves each heuristic from 3 to 4)
- H1: no state hidden under plaques; confirm every manual move.
- H2: "Cmdr dmg 0 / 21"; "Less detail" says what it hides.
- H3: an undo list that is still reachable after the toast is gone.
- H4: one rule for plaque stats; Hand shown for every player; one chain-number style.
- H5: confirm multi-card or commander Delete; disable illegal dial actions.
- H6: card names readable on the table.
- H7: box-select and acting on several permanents on the 3D table.
- H8: issues 1–3; fade empty zone outlines.
- H9: a hint for every common server error; mark the error on the card involved.
- H10: contextual hints at the first combat, the first priority stop and the first target choice; a link from errors to Help.
