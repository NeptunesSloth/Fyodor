---
target: Play page and launcher
total_score: 31
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
target_identity: "file:/tmp/gx/ui4/frontend/src/pages/PlayPage.tsx"
target_fingerprint: "sha256:449c2bb2c3c84140d4fb15a38a1caa5ce6d12c6b935fcac0f38b318f7ca827c7"
target_path: /tmp/gx/ui4/frontend/src/pages/PlayPage.tsx
timestamp: 2026-11-02T23-33-01Z
slug: frontend-src-pages-playpage-tsx
---
⚠️ DEGRADED: single-context (no sub-agent tool exposed to this agent; Assessment A was completed before the detector ran)

## Design Health Score
| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | "Setting up…", database status line; Continue's loading state is quiet |
| 2 | Match System / Real World | 4 | seats, empty chairs, felt table, front rail |
| 3 | User Control and Freedom | 3 | deck picker didn't return focus on close |
| 4 | Consistency and Standards | 3 | a brass Open/Load on every shelf tile broke "one brass thing per region" |
| 5 | Error Prevention | 3 | Join disabled until a code; deletes confirm |
| 6 | Recognition Rather Than Recall | 3 | decks by commander art; bare "LAN" button was cryptic |
| 7 | Flexibility and Efficiency | 3 | Continue, recent decks to a new game |
| 8 | Aesthetic and Minimalist Design | 3 | brass noise on the shelf; mode copy wrapped unevenly |
| 9 | Error Recovery | 3 | shared toasts |
| 10 | Help and Documentation | 3 | automation/LAN hints, setup guide |
| **Total** | | **31/40** | **Good** |

## Design Specificity Verdict
Authored for this product: felt table, commander plinths, empty chairs, commander mosaics. Detector (TSX) clean; in-page overlay: 12–22 hits, mostly world lighting (--scene), cards-on-a-mat as "nested cards", poker-chip gradients and proxy-card internals (false positives here). Real: placeholder contrast (2.2–4.3:1), gradient text on the top bar's brand, a brown fallback chip at 1.9:1, missing autocomplete hints.

## Priority Issues
- [P1] Brass Open/Load on every shelf tile → metal buttons, brass kept for Start game and Join.
- [P1] Placeholder contrast (room code 2.2:1, password hints 3.8–4.3:1) → plain hint ≥4.5:1.
- [P2] Small Cinzel on launcher deck tiles (12.5px) → Inter 13px.
- [P2] Deck picker focus not entering (≤5 decks) / not returning to the seat.
- [P2] Mode copy wraps unevenly; "LAN" button cryptic → shorter copy, "Load as LAN".

## Minor Observations
Title pen icon drifted (width overrode field-sizing); brand gradient text; fallback chip colour; autocomplete on passwords; launcher text selection unthemed.
