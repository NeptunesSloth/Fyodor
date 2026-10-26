---
target: 3D game screen
total_score: 39
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 0
target_identity: "file:/home/user/Fyodor/frontend/src/table3d/Table3D.tsx"
target_fingerprint: "sha256:a7465b88767887a02204152e935db1638c34cb6508c5d1377922a20f078f1329"
target_path: /home/user/Fyodor/frontend/src/table3d/Table3D.tsx
timestamp: 2026-10-26T23-17-06Z
slug: frontend-src-table3d-table3d-tsx
---
# Critique round 8: the whole 3D game screen

Provenance: the same isolated rater A. Rounds 6–8 re-scored commits 7c542bf1, a74b9940 and b0cbcdfb (37, 38, 39). 3D e2e: 8 passed, with a no-plaque-under-panel assertion.

## Score: 39/40
H1 4 · H2 4 · H3 4 · H4 4 · H5 4 · H6 4 · H7 4 · H8 3 · H9 4 · H10 4

## Remaining issues
1. [P2] On a sparse table a compact plaque can sit on its own pile: clearing the pile needs more than MAX_DRIFT (110px). Try sideways shifts first (Table3D.tsx place()).
2. [P3] The tip banner covers far-seat piles (table3d.css .t3d-coach); it shows once per tip.
3. [P3] The e2e overlap check covers panels only, not cards, piles or the banner.
