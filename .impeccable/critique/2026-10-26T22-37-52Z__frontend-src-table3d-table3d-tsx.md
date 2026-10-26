---
target: 3D game screen
total_score: 36
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 1
target_identity: "file:/home/user/Fyodor/frontend/src/table3d/Table3D.tsx"
target_fingerprint: "sha256:f77849f444a3df87e2be78fdabfdb9c70ea098e6fbc88b43cbbfd6ca344b414f"
target_path: /home/user/Fyodor/frontend/src/table3d/Table3D.tsx
timestamp: 2026-10-26T22-37-52Z
slug: frontend-src-table3d-table3d-tsx
---
# Critique round 5: the whole 3D game screen

Provenance: the same isolated rater A, re-scored against its round-4 baseline (30). Source checked at a82db180, 5991dd36 and 03d5aa74. 3D e2e: 8 passed.

## Score: 36/40 (+6)
H1 3 · H2 3 · H3 4 (+1) · H4 4 (+1) · H5 3 · H6 4 (+1) · H7 4 (+1) · H8 3 · H9 4 (+1) · H10 4 (+1)

## Priority issues
1. [P1] On a dense table (300 permanents) plaques still cover cards: the viewport clamp can push a plaque back onto them (Table3D.tsx follow loop).
2. [P2] The coach tip is fixed at left 14px / top 220px and covers battlefield cards (table3d.css:79).
3. [P2] The dial's disabled reason is in the tooltip only (RulesHud.tsx:216, :247).
4. [P3] The Undo ▾ caret reads as a separate control (TopBar.tsx:41).
5. [P3] Name tags are aria-hidden (Table3D.tsx:191).
6. [P3] "End game" sits next to Undo (TopBar.tsx).

## What blocks a 4
- H1: show the disabled reason visibly; plaques must never hide cards at any density.
- H2: "‹ Back" should say "‹ Previous step"; "Hide panel extras" should name what it hides.
- H5: show legal drop zones while dragging; move "End game" away from Undo.
- H8: issues 1, 2 and 4; compact plaques by default, expanding on hover.
