---
target: 3D game screen
total_score: 28
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
target_identity: "file:/home/user/Fyodor/frontend/src/table3d/Table3D.tsx"
target_fingerprint: "sha256:af0e56fe95c44823c470678d052fc07dab3061ddc2e3214480fae7070e33d5e2"
target_path: /home/user/Fyodor/frontend/src/table3d/Table3D.tsx
timestamp: 2026-10-26T19-06-35Z
slug: frontend-src-table3d-table3d-tsx
---
# Critique round 2: the whole 3D game screen (after W1–W6)

Provenance: isolated sub-agents A (design review) and B (detector + browser with bypassCSP overlay).

## Score: 28/40
H1 3 · H2 3 · H3 3 · H4 2 · H5 2 · H6 2 · H7 4 · H8 3 · H9 3 · H10 3

## Priority issues (status after commits 27c41556, 1268a1a5, f58b7bc1)
1. [P1] Laptop overlays covering permanents — stack panels reduced to the top row at <=1440px; coach tips end after turn 1. FIXED
2. [P1] Beams through the standing stack cards, which hide Casey's row — beams route around the stack; stack beams leave from the facing edge; stack moved nearer my side. FIXED
3. [P2] Manual dial ignored the stack — its primary becomes Resolve top. FIXED
4. [P2] Hovered hand card cut off — it grows from its bottom edge. FIXED
5. [P2] Badges unreadable — about 1.6x larger. IMPROVED
6. [P3] Cinzel caps on buttons — Inter. FIXED
Detector: step labels at 10–10.5px (now 11px); seat focus looked the same as the active seat (distinct ring now); mixed focus styles (unified); thin border with a wide shadow (fixed); margin transition (fixed).
