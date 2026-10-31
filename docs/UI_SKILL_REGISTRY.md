# UI skill registry

These are the Claude Code skills used for Fyodor's UI and 3D work. They are kept under `.claude/skills/` (repo-local,
copied from upstream at a recorded commit; nothing is installed globally). `fyodor-ui-design` routes the work to them.
They are guidance, not architecture: **Fyodor stays on plain three.js**. Advice in any skill to use React Three Fiber,
Drei, GSAP, Rapier or `@react-three/postprocessing` is ignored, and so are paid asset-generator services. The one
physics library, `cannon-es`, was added at the user's request for thrown dice and flicked cards (`UI_REFERENCE_STUDY.md`
§26–27).

Last reviewed 2026-10-31. Each upstream repository was cloned and the installed copy diffed against it.

## Installed

| Skill | Source (commit) | Purpose | When to use |
|---|---|---|---|
| `fyodor-ui-design` | Fyodor | Product, privacy and renderer rules for any UI change; routes to the skills below | Before any frontend/table/HUD change |
| `fyodor-game-development`, `fyodor-card-playbook`, `mtg-rules-research` | Fyodor | Rules engine, card automation, Comprehensive Rules research | Server/rules work only (not visual) |
| `frontend-design` | anthropics/skills `8a1541c4` (identical to `ca45fc49`) | Creative direction and implementation of new/reshaped UI | Designing a screen or system |
| `impeccable` | pbakaus/impeccable `df3a4abe` (v4.8.0, engine 0.1.18), skill folder only | Critique, audit, polish, harden, typeset, layout … against PRODUCT.md / DESIGN.md | After each implemented stage; `critique` + `audit` on real screenshots |
| `threejs-game-ui-designer` | majidmanzarpour/threejs-game-skills `8286774b` | Game HUD, overlays, in-game menus, text fit, UI/world cohesion, "UI reads state, sends intents" | Plaques, dial, toasts, drawers, result screens |
| `accessibility` | addyosmani/web-quality-skills `afa8da94` (MIT) | WCAG 2.2 audit: 2.5.7 drag alternatives, 2.4.11 focus not obscured, 2.5.8 target size, contrast, keyboard | Every interaction change; before claiming a screen done |
| `animate`, `review-animations` | emilkowalski/skills `2d228630`, adapted for Fyodor | Build motion in the right order; review it against a high bar | Any motion: hover, card travel, banners, 3D tweens |
| `threejs-core`, `-geometry`, `-materials`, `-lighting`, `-camera`, `-animation`, `-loaders`, `-performance`, `-postprocessing`, `-shaders` | alton47/threejs-skills `7b8e2563` (identical to HEAD) | Plain three.js reference per topic | The matching part of `frontend/src/table3d` |
| `threejs-game-director`, `-gameplay-systems`, `-aaa-graphics-builder`, `-debug-profiler`, `-qa-release` | majidmanzarpour/threejs-game-skills `8286774b` (identical to HEAD) | Game workflow: graphics upgrade scorecard, profiling, QA/release, screenshots | Visual-quality passes, perf budgets (100/300/500+ objects), screenshot QA |
| `systematic-debugging` | obra/superpowers `2ce8aa15` | Root cause before fixes | Any bug or failing test |
| `test-driven-development`, `verification-before-completion` | obra/superpowers `8ca22dba` (identical to HEAD) | Tests first; evidence before "done" | All implementation |
| `ponytail`, `caveman` | `caveman`: JuliusBrussee/caveman `2fd153c6`; `ponytail`: no source recorded | Keep scope small / replies short | Scope control |

### Changed in this review
- **Added** `threejs-game-ui-designer`, which `threejs-game-director` already routed to but wasn't installed. Its
  `agents/openai.yaml` (a config for another tool) was left out.
- **Added** `accessibility`, because Fyodor's accessibility hard rule needed a WCAG 2.2 reference deeper than
  Impeccable's audit.
- **Updated** `impeccable` from v4.5.0 (`e103efe7`) to v4.8.0. The installed copy had no local edits. Upstream now pins
  the engine binary's checksums in the repo (`scripts/engine-checksums.txt`), and its WCAG 2.5.8 rule is corrected.
  Only `plugin/skills/impeccable` was copied, **not** `plugin/hooks` (which would run the engine after every edit) or
  `plugin/agents`.
- **Updated** `systematic-debugging`. Upstream fixed an example that echoed a secret's value.

### Security notes
- **Impeccable's engine.** On first use it downloads a native binary from GitHub releases into `~/.impeccable`, checked
  against the pinned checksums. The engine also contacts `impeccable.style/api` (a "roll" request, an anonymous choice
  ping, an update check) and uses `OPENAI_API_KEY` for image generation if that key is set. Fyodor promises no
  telemetry, so run it with `IMPECCABLE_NO_TELEMETRY=1 IMPECCABLE_NO_UPDATE_CHECK=1` (or `DO_NOT_TRACK=1`).
- **`threejs-game-director/scripts/probe_asset_credentials.sh`** opens a login shell to report whether asset-generator
  API keys are set. Fyodor doesn't need it; don't run it.

## Rejected

| Candidate | Source | Why not |
|---|---|---|
| `webapp-testing` | anthropics/skills | Python Playwright with a `shell=True` helper. Fyodor already has a TypeScript `@playwright/test` suite plus `threejs-qa-release` |
| `theme-factory`, `canvas-design`, `algorithmic-art`, `web-artifacts-builder` | anthropics/skills | Slides, posters, p5 art, React+Tailwind+shadcn: unrelated |
| Playwright MCP plugin | anthropics/claude-plugins-official | An MCP server, not a skill, run as unpinned `npx @playwright/mcp@latest` |
| `web-design-guidelines` | vercel-labs/agent-skills | Fetches its rules from an unpinned remote URL on every run; Impeccable's audit already covers it |
| `react-best-practices`, `react-view-transitions`, `composition-patterns` | vercel-labs/agent-skills | Next.js/SWR focus; view transitions need canary React |
| `break-ui` | emilkowalski/skills | Overlaps Impeccable `harden`; examples are web-app data |
| `remove-animations`, `find-animation-opportunities`, `improve-animations` | emilkowalski/skills | `remove-animations` would strip the card motion GAME_UI_MOTION_RESEARCH.md keeps; the others duplicate `animate` / `review-animations` / Impeccable |
| `playwright-cli` | microsoft/playwright-cli | Needs a global alpha Playwright CLI; its page snapshot can't see inside the three.js canvas |
| `a11y-debugging`, `memory-leak-debugging` | ChromeDevTools/chrome-devtools-mcp | Need the DevTools MCP server, which sends usage statistics (and can send page URLs) to Google by default: wrong for a private LAN app |
| `accessibility-review` | anthropics/knowledge-work-plugins | WCAG 2.1, built around Figma/connectors; the installed `accessibility` is better |
| `playwright-skill` | lackeyjb/playwright-skill | Installs its own Playwright and Chromium; duplicates the e2e setup |
| `game-ui-design` | omer-metin/skills-for-antigravity | Generic, mass-generated, controller/console first |
| `threejs-3d-generator`, `-image-generator`, `-audio-generator` | majidmanzarpour/threejs-game-skills | Paid third-party APIs (Tripo, Gemini, ElevenLabs) and uploads |
| `threejs-react`, `-physics`, `-xr`, `-audio` | alton47/threejs-skills | Framework-coupled or out of scope |

## How they are used together

1. Design a change with `fyodor-ui-design`, then `frontend-design`. For HUD pieces add `threejs-game-ui-designer`; for
   the table itself add the matching `threejs-*` skill.
2. Build motion with `animate` and check it with `review-animations`.
3. Verify in the running app: screenshots at 1920×1080, 2560×1440 and a laptop size (`threejs-qa-release`), the
   Playwright e2e suite, and perf numbers (`threejs-debug-profiler`).
4. Critique with `impeccable critique` / `audit` and check against `accessibility`, then fix the concrete findings.
5. Use `systematic-debugging` for anything that breaks; never claim done without `verification-before-completion`.

Load only the skills a task needs. Don't put every skill into one agent's context.
