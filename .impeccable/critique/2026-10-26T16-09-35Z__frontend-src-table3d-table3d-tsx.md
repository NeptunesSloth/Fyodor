---
target: 3D table overlays
total_score: 25
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
target_identity: "file:/home/user/Fyodor/frontend/src/table3d/Table3D.tsx"
target_fingerprint: "sha256:453f8839e053a5860b95d7d4c6506822d5b1bc93b20d92f0d61568659175d4ba"
target_path: /home/user/Fyodor/frontend/src/table3d/Table3D.tsx
timestamp: 2026-10-26T16-09-35Z
slug: frontend-src-table3d-table3d-tsx
---
# Critique: 3D table overlays (hand fan, seat plaques, camera strip, stack panel)

Provenance: Assessment A (design review) and Assessment B (detector + browser) ran as two isolated sub-agents. B injected the detector overlay with Playwright bypassCSP, because the app's CSP blocks inline scripts.

## Design health: 25/40 (Acceptable)
| # | Heuristic | Score |
|---|---|---|
| 1 | Visibility of status | 2 |
| 2 | Match to real world | 3 |
| 3 | User control | 3 |
| 4 | Consistency | 2 |
| 5 | Error prevention | 2 |
| 6 | Recognition over recall | 2 |
| 7 | Flexibility | 3 |
| 8 | Minimalist design | 3 |
| 9 | Error recovery | 2 |
| 10 | Help | 2 |

## Specificity verdict
Mostly specific to Fyodor: the plaques, the fanned hand and the brass Turn tab belong to this product. The stack panel and the camera strip are generic: a grey web panel and a bright primary button.

## Priority issues
1. [P1] The AUTO pill covers the stack's Resolve top button (hit test at 1859,65 returns the auto-pill). FIXED in 22ed76e9: the stack widget always sits below the HUD.
2. [P1] The plaques leave out commander damage, poison and opponents' hand counts. FIXED: these show when non-zero, and lethal values say "lethal" in words.
3. [P1] Hand cards can't be reached by keyboard; camera buttons are named by a single letter. FIXED: hand cards have tabIndex, role=button, an aria-label and Enter/Space to select; camera buttons have aria-labels.
4. [P2] The hand fan covers your own command zone, graveyard and library in the seat view. OPEN (the camera phase will keep the bottom band clear).
5. [P2] The stack panel is styled as generic grey web UI, with no "resolves next" weight and no target text. OPEN.

## Detector evidence
- CLI scan: clean.
- Overlay: 41 findings. Undersized card-face text in the hand (8.7–10.3px; 5–7px at 1366), 3.6:1 contrast for accent-ink on the accent gradient (FIXED on the Turn tab and the camera strip; the app-wide buttons are still open), cramped padding, and a dark glow.
- Plaque contrast: 6.9:1 for the name and 12.5:1 for the life total.

## Persona red flags
- Jordan (newcomer): the "B C J" camera letters, and two previews on hover.
- Sam (accessibility): hand keyboard access (fixed).
- Alex (veteran): Resolve top was covered (fixed); opening three plaques to check lethal commander damage (fixed).

## Minor
The monarch glyph can be cut off by the name ellipsis; the hand's type line is truncated at 1080p; the empty hand gives no cue in 3D.
