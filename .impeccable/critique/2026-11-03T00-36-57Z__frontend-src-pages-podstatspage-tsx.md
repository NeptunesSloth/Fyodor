---
target: Settings, Pod stats, Assets, Cards (round 5)
total_score: 32
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 0
target_identity: "file:/tmp/gx/ui5b/frontend/src/pages/PodStatsPage.tsx"
target_fingerprint: "sha256:02b4f068f8d7765d900b8f8342dd7bc1d8099921356805199e10736ba98d0487"
target_path: /tmp/gx/ui5b/frontend/src/pages/PodStatsPage.tsx
timestamp: 2026-11-03T00-36-57Z
slug: frontend-src-pages-podstatspage-tsx
---
⚠️ DEGRADED: single-context (running as a sub-agent with no sub-agent tool exposed)

Scope: Settings (#/settings and the in-game modal), Pod stats (#/stats, with GameRecap), Assets (#/assets), Cards (#/cards), after the round-5 redesign. Shots: /tmp/gx/ui5b-shots/after (1440, 1920, 390).

| # | Heuristic | Score | Key issue |
|---|-----------|-------|-----------|
| 1 | Visibility of system status | 3 | Settings save silently (a note in the index says so); backups/card data show live state |
| 2 | Match system / real world | 4 | Game nights, seats, "Won", felt table, keycaps: the pod's own vocabulary |
| 3 | User control and freedom | 3 | Destructive actions confirmed; a player's sheet closes; no undo for a deleted result (pre-existing) |
| 4 | Consistency and standards | 3 | Same steel placards, brass buttons, felt as Play/lobby; the index rail is the one new pattern |
| 5 | Error prevention | 3 | Delete is quiet and confirmed; profile delete hidden with one profile |
| 6 | Recognition rather than recall | 4 | Search syntax as clickable examples; keycaps; hints under every setting |
| 7 | Flexibility and efficiency | 3 | Section index, drop-to-upload; no in-page filter for settings |
| 8 | Aesthetic and minimalist design | 3 | Settings is long (11 sections) but indexed; pod stats art-forward with one spotlight |
| 9 | Error recovery | 3 | Card search error and no-match states say what to try |
| 10 | Help and documentation | 3 | One-line explanation per setting and section |
| **Total** | | **32/40** | Good |

Design specificity: authored for this product — the pod ledger sits on the Play page's felt with walnut rim, each player shown with their most-played commander; the last game gets the winner's art in a spotlight; history reads by game night with every seat's commander and the winner framed in brass. Settings rows are blackened-steel placards with brass switches; keys are keycaps.

Detector: CLI scan clean (0). In-page detector: low-contrast on `div.app` (false positive: sampled backgrounds are #0e0c0b–#20170f, text-dim 7.9–9:1, text-faint 5–5.7:1); purple gradient = the plane previews' own colours (data); proxy-card internals (undersized text, tc-head padding, stripes) belong to the card face; nested card (auto-backup box inside the backup placard) — fixed by making it a row; text-faint elimination detail 4.4:1 on steel — fixed (text-dim); straggler words — fixed with text-wrap: pretty.

Priority issues (after fixes):
- [P2] Settings is long on a phone (theme tiles alone are tall) — tiles drop their blurb under 620 px; consider collapsing waves.
- [P2] Pod stats picks art by commander name (one card search per unique commander, cached) — fine for a pod, watch it with 100+ distinct commanders.
- [P3] Asset kinds that the table does not use yet (counter art, dice skins…) still get tabs; their note says so plainly.

Persona red flags: Jordan (first-timer) — fine: every setting has a plain hint. Alex (power user) — the index and keycap rebinding are quick; no search box in Settings.
