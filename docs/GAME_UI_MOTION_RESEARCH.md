# Game UI & motion research — how Fyodor avoids "AI slop"

Research wave, 2026-10-26. Purpose: give any session building Fyodor's UI a concrete, sourced bar for game-client
look and motion. Read with `fyodor-ui-design` (hard rules win), `docs/UI_REDESIGN_BRIEF.md` and `PRODUCT.md`.
Numbers marked **[synth]** are starting points derived from the cited ranges — tune by eye, they are not published
figures.

## 1. Skill stack (what to load, in order)

| Step | Skill | Use it for |
| --- | --- | --- |
| 1 | `fyodor-ui-design` | Product/privacy/renderer constraints, look, workflow. Always first. |
| 2 | `frontend-design` | Deciding and building a screen/system. |
| 3 | **`animate`** (new, vendored) | Building any motion: should it animate → purpose → tool → properties → curve/duration/spring → interruption → reduced motion. |
| 4 | `threejs-*` | 3D table work; `threejs-gameplay-systems/references/game-feel.md` for juice (hitstop, shake, layered feedback). |
| 5 | **`review-animations`** (new, vendored) | Strict motion review of the diff: Before/After/Why table + Block/Approve. |
| 6 | `impeccable critique/audit/polish` | Whole-UI critique against its craft-floor ban list. |

New skills come from [emilkowalski/skills](https://github.com/emilkowalski/skills) (MIT, @`2d228630`), adapted:
no Motion/Framer/GSAP, springs are hand-rolled and stepped from the three.js loop, Fyodor rules added.

Surveyed and **not adopted** (reasons): `greensock/gsap-skills` (needs GSAP; GSAP is free since Apr 2025 but
proprietary "Standard No Charge" licence, not MIT, ~23 KB core), `ui-ux-pro-max-skill` (its "Gaming" profile
recommends "Vibrant + neon" — the opposite of our goal), `awesome-gamedev-agent-skills` (Godot/Unity-centric;
duplicates local game-feel.md), `skills-for-antigravity/game-ui-design` (console/TV-safe-zone focus),
`taste-skill` (landing-page genre; its tells list is folded into §5). Adapted as rules below:
[raphaelsalaja/userinterface-wiki](https://github.com/raphaelsalaja/userinterface-wiki) (audio, typography, staging),
[lottiefiles/motion-design-skill](https://github.com/lottiefiles/motion-design-skill) (choreography, material easing),
[dannyjpwilliams/ui-sound-design-skill](https://github.com/dannyjpwilliams/ui-sound-design-skill) (later, for sound
recipes; vanilla Web Audio path only). No public card-game/tabletop UI taste skill exists — this doc fills that gap.

## 2. Principles the best card games share

- **Effects do their job and get out of the way.** Arena's Chris Clay: making Magic "snappy" is the hard UI
  problem ([PCGamesN](https://www.pcgamesn.com/magic-the-gathering-arena/mtg-arena-snappiness-flow)).
- **Never lock input behind animation.** Legends of Runeterra 0.9.1 "removed effect buffers" and "decreased action
  lock-out windows" ([Inven](https://labs.invenglobal.com/articles/10550/patch-091-speeds-up-animations-introduces-jinx-and-garen-themed-boards-to-legends-of-runeterra)).
  Fyodor rule: **game state commits immediately; visuals catch up; click/Space jumps choreography to its end.**
- **Speed settings are standard.** Slay the Spire Fast Mode, Master Duel "show summon animation once per duel".
  Fyodor: one global time multiplier (1×, 1.5×, 2×, instant) applied to every CSS/WAAPI duration and three.js tween.
- **Reduced motion removes juice, not feedback.** Balatro's Reduced Motion drops "swirly background, gyrating card
  motion, much of the juice" ([mp1st](https://mp1st.com/news/balatro-update-1-07-shuffles-out-this-may-16)).
  Keep fades/colour; drop sway, shake, tilt, overshoot, parallax; shorten (don't delete) 3D flights.
- **Frequency decides whether something animates.** 100+/day or keyboard-initiated → no animation
  ([Emil Kowalski](https://emilkowal.ski/ui/great-animations)). Priority passes, hotkeys, tapping lands: instant.
- **Things come from somewhere.** Spatial origin; momentum preserved on release; light objects (cards) bounce
  little ([Rauno Freiberg](https://rauno.me/craft/interaction-design)).
- **Physical table.** Hearthstone aimed for a board game that "could actually be played in a fantasy world"
  ([Game Developer](https://gamedeveloper.com/design/video-blizzard-s-art-design-principles-for-i-hearthstone-i-)).

## 3. Motion tokens (one source, CSS + three.js)

```css
--ease-out:    cubic-bezier(0.23, 1, 0.32, 1);    /* default: enter/exit, card travel */
--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);   /* on-screen moves/morphs */
--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);    /* drawers, private-choice panel */
--dur-press: 120ms; --dur-hover: 140ms; --dur-popover: 180ms; --dur-panel: 240ms;
--dur-card-travel: 240ms; --dur-banner: 700ms;    /* banner = rare, click-through */
```

Never `ease-in` on UI, never `transition: all`, never `scale(0)` (start 0.95 + opacity 0), transform/opacity only.

Springs (hand-rolled, velocity-preserving, ~50 lines, stepped with clamped `dt` inside
`renderer.setAnimationLoop`; DOM overlays written via refs, never React state per frame) **[synth]**:

| Preset | stiffness | damping | mass | ζ ≈ | Use |
| --- | --- | --- | --- | --- | --- |
| `snappy` | 500 | 40 | 1 | 0.89 | hover lift, selection |
| `settle` | 350 | 28 | 1 | 0.75 | drag follow, card landing |
| `heavy`  | 200 | 28 | 1 | 1.0 | camera, big permanents, board reflow |

ζ = damping / (2·√(stiffness·mass)); ζ = 1 never overshoots ([Android SpringForce](https://developer.android.com/reference/android/support/animation/SpringForce)).
CSS-side springs: bake the same presets into `linear()` easing strings (Chrome 113 / Firefox 112 / Safari 17.2,
[web.dev](https://developer.chrome.com/docs/css-ui/css-linear-easing-function)) — fixed-duration, fine for non-gesture UI.

Tool ladder: CSS transition (interruptible, hover/press/state) → `@starting-style` (mount) → WAAPI (imperative
sequences, cancellable) → same-document View Transitions for DOM-overlay phase/screen changes only (Baseline Oct 2025;
doesn't capture the WebGL canvas; wrap React updates in `flushSync`) → hand-rolled spring. No new dependency; if
WAAPI orchestration ever gets tedious, Motion's ~2.5 KB `animate` mini is the only acceptable add, and only with
a stated need.

## 4. Card choreography table **[synth unless cited]**

Reference values from Mix and Jam's open-source Balatro-feel recreation
([CardVisual.cs](https://raw.githubusercontent.com/mixandjam/balatro-feel/main/Assets/Scripts/CardVisual.cs),
[80.lv](https://80.lv/articles/balatro-s-card-movements-shaders-recreated-in-unity)): split each card into a
**logical slot that snaps instantly** and a **visual that chases it** — `pos = lerp(pos, target, 1 - exp(-30*dt))`;
drag tilt from velocity `rot = lerp(rot, delta*20, 20*dt)` (they clamp ±60°; Fyodor ±12–15°); hover 1.15×,
selected 1.25× over 150 ms with slight overshoot; hand arc only from 5+ cards, Y/rotation from curves over
normalized index.

| Moment | Fyodor spec |
| --- | --- |
| Hand hover | Lift 8–15% of card height, scale 1.08–1.12, `--ease-out` 120–150 ms (CSS transition, interruptible). Big preview after 80–120 ms dwell; closes instantly. Neighbours part slightly. |
| Drag | `settle` spring + velocity tilt; release keeps velocity; pointer capture; invalid drop springs back to its slot. |
| Play / cast | Anticipation dip 2–4% over 60–80 ms → travel 200–280 ms `--ease-out` from the hand/source → land with 1.03 overshoot settling 80–120 ms, shadow tightens, sound on contact frame. Total ≤ 450 ms, non-blocking. |
| Stack | Physical offset pile (~6–10% per item); new item enters from its source (caster's hand or permanent); resolve flies to destination; 40–60 ms stagger. Top of stack always legible. |
| Targeting | Curved bezier arrow from source, drawn at 0 ms; snaps to a valid target; invalid targets dim (plus icon/text — never colour alone). |
| Tap / untap | 90° rotation, `--ease-out` ≤ 180 ms; mass untap on untap step staggered 20–30 ms, total ≤ 300 ms. |
| Life / damage | Number rolls 300–600 ms scaled to delta; scale punch 1.15→1; red/green flash plus +N/−N text. Shake only for lethal/commander damage, few px, fast decay. |
| Turn / phase | Full banner only at **your** turn start, ≤ 700 ms, click-through. Phase/priority changes: a subtle stepper tick, no banner. |
| Group entrance | 30–50 ms per item, total stagger ≤ 300 ms, never blocks interaction. |
| Game start / end | The one place for a 600–1200 ms orchestrated "dramatic reveal" (lottiefiles band); still skippable. |

Choreography (lottiefiles): one **primary** motion at a time, secondary motion supports it, ambient motion
≈ none (Fyodor bans always-on animation). Duration scales with distance; exits 30–50% shorter than entrances.
Material: cards are paper — small overshoot (≤ 3–5%); tokens/counters rigid — none; board/camera heavy — none.

## 5. Ban list — tells of AI-generated UI (reject on sight)

Visual: purple/indigo/blue gradients; gradient text; glassmorphism / `backdrop-filter` decoration; zero-offset
coloured glow shadows; neon; same-radius rounded-xl cards everywhere; nested cards; row-of-three icon+heading
cards; coloured `border-left` stripes; eyebrow/kicker labels and "01/02/03" numbering; hero-metric tiles,
sparklines, progress rings, "Live" badges; emoji or random Lucide soup as icons; Inter/system font on the table
layer; untouched scrollbars, selection colour and focus rings; shadows that ignore the single top-left key light.
Sources: [Anthropic](https://claude.com/blog/improving-frontend-design-through-skills), impeccable
`reference/craft-floor.md`, [taste-skill tells](https://github.com/Leonxlnx/taste-skill).

Motion: same fade-in-up on everything; uniform 300 ms `ease-in-out`; reflexive bounce/elastic; staggers on
non-lists; scattered micro-interactions with no authored moment; long feedback that reads as latency; animating
width/height/top/left; constant idle wobble; screen shake on routine events; VFX hiding board state; unskippable
banners; input locked during animation; tooltip delays that stack.

## 6. Material, type and sound (adapted rules)

- **Light:** one key light top-left; shadow offset and blur grow with lift height — the strongest "physical" cue.
  No pure-black shadows; layered shadows.
- **Cards:** real thickness edge in 3D, corner radius matched to 63×88 mm cards (~2.5 mm).
- **Brass/wood/felt:** brass has a specular band, not a flat tint; textures low-contrast.
- **Type:** Cinzel (serif display) for banners, names, life totals; small caps for phases; `font-variant-numeric:
  tabular-nums` on every counter/life/timer; no font synthesis; uppercase gets letter-spacing; `text-wrap: balance`
  on headings. Text over art needs a 1 px light/dark offset pair or a backing plate — not a glow.
  Inter stays for dense menus/logs only.
- **Sound** (userinterface-wiki): sound for confirmations, errors and impacts only — not hover or keyboard
  navigation; every sound has a visual equivalent; master toggle + volume (default gain ≈ 0.3); sound weight
  matches action weight; one shared `AudioContext`; exponential envelopes to 0.001; ±3–5% pitch variation against
  machine-gun repeats; fire on the **impact frame**, not animation start; scale with the speed multiplier and drop
  at "instant". Fyodor already has `frontend/src/game/sound.ts` and `table3d/ambience.ts` — extend those.

## 7. Enforcement (skills alone won't hold the line)

1. Tokens first (`frontend/src/theme`), agent reads them before writing motion; drift is a finding.
2. Build with `animate`; review with `review-animations` (Block/Approve) and `impeccable critique`.
3. Screenshot-critique loop at 1920×1080, 2560×1440 and laptop, plus a 2–5× slow-motion check of each new
   animation; give specific feedback ("lift 12% not 20%"), never "looks off".
4. Playwright `toHaveScreenshot` baselines for touched screens (`threejs-qa-release`).
5. Every PR touching motion states: frequency tier, purpose, tool, curve/duration or spring preset, reduced-motion
   behaviour, speed-multiplier/skip behaviour.

## Unverified

Hearthstone/Arena/Marvel Snap internal timings (not published; GDC Vault was down during research); Balatro's exact
speed options; star counts of surveyed repos.
