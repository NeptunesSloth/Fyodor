# Automation UX

How much Fyodor does for the players, and how they stay in control. It borrows *UX* ideas from
MTG Arena (rules enforcement, payment help, highlights) and Yu-Gi-Oh! Master Duel (clear
response windows, a response toggle, compact prompts), on a physical tabletop. **Magic's
rules stay authoritative:** priority, the stack (called STACK, never "chain"), timing and APNAP
come from the Comprehensive Rules; nothing from Yu-Gi-Oh's rules is used.

Status legend: **built** = engine side done and tested (backend `tests/test_rules_*.py`);
**client** = the 2D/3D client still needs the UI (M18/M19).

## AUTOMATION: OFF / ASSISTED / FULL — built

| Level | What happens |
|---|---|
| OFF | Pure sandbox. The default for new games and for every game loaded from an older save. |
| ASSISTED | The engine understands and validates, prepares payments, attackers, blockers and state-based actions, and asks before important steps. |
| FULL | Arena-like: supported deterministic rules happen by themselves; you're asked only when Magic requires a choice. |

Each level is a preset of per-feature options (`settings.automation_options`):
`auto_mana_payment`, `auto_combat_damage`, `auto_sba`, `auto_priority_pass`, `auto_cleanup`,
`auto_token_creation`, `auto_counters`, `auto_trigger_stacking`, `auto_shuffle`, `highlights`
(OFF / SUBTLE / FULL). Changing any option shows the preset as **CUSTOM**.

What ASSISTED asks today:

- **State-based actions:** "State-based actions: Bear dies (lethal damage) [APPLY] [LEAVE FOR
  NOW]". A declined set isn't asked again until something changes.
- **Combat damage:** "Combat damage: Bear → Bob 3 [DEAL DAMAGE] [BY HAND]".
- **Payment:** you tap your own mana (see MANA).

The token/counter/trigger/shuffle options take effect with the M16 trigger and effect engine.

**Changing levels mid-game** (host): FULL→OFF keeps the rules state *dormant*, so nothing is
destroyed and the table simply continues as a sandbox. OFF→ASSISTED/FULL and RESUME after
PAUSE run **reconciliation** (below). Old saves are never switched to FULL silently: v5 games
that used rules automation become FULL, sandbox games stay OFF.

**PAUSE AUTOMATION** (host): intents are refused, the sandbox works, the stack and pending
decisions are kept. RESUME reconciles first.

## Reconciliation — built

When automation comes back after manual play, the engine:

1. **Takes in what the log shows:** a land moved from hand to the battlefield by hand counts
   as the land for the turn; a spell moved to the stack by hand counts as cast.
2. **Derives what the table shows:** the step and priority, combat bookkeeping, which
   permanents are where, whether a pending decision still matches the table (a decision about
   cards that are gone is cancelled and says so).
3. **Asks what it can't know**, in one concise list addressed to the player who knows:

   > Did Llanowar Elves come under your control this turn? [This turn] [Before this turn]
   > [Leave it manual]
   > Has Alice played a land this turn? [Yes] [Not yet]

   "Leave it manual" takes that card out of automation. Questions are only asked when the fact
   matters now (e.g. summoning sickness of the active player's creatures). The list is public;
   the answers are the chooser's.

It never invents hidden history.

## Per-card automation — built

Right-click → Automation → AUTO / MANUAL (ASSISTED is stored for scripted effects in M16).
A MANUAL card resolves by hand ("Resolve Sol Ring by hand, then press Done") and its timing
restrictions (summoning sickness) aren't enforced. Only its controller can change it. Opponents
only learn about cards they can see.

## RESPONSE: OFF / AUTO / ON — built

Per player; the HUD shows `RESP: AUTO`, a click cycles OFF → AUTO → ON (the hotkey is a
client setting).

| RESPONSE | Stack not empty | Stack empty |
|---|---|---|
| OFF | pass | stop only in your own first main phase, and only if you have something to do |
| AUTO (default) | stop if you have a real response (instant, flash, activated ability) | stop at your configured stops; always in your first main phase |
| ON | stop | stop (bluffing) |

**Stops** per player: `stops_my_turn` (default main 1 and main 2) and `stops_their_turn`
(default none), over the real turn structure. Nobody gets priority in the untap step.

**Decisions always reach you** (targets, blockers, discard…), whatever is set.

**Temporary overrides** — built:

- **HOLD PRIORITY:** keep priority after casting or activating.
- **FULL CONTROL:** no smart passing at all.
- **FORCE STOP:** your next priority is a stop, whatever else is set. It can be pressed any
  time (even mid-animation, without priority) and is registered immediately; it is used up
  once it stops you.
- **PASS UNTIL …:** next action (another player acts), stack changes, stack empty, next step,
  next turn, my turn, combat.
- Stack fast controls: **RESOLVE ONE** = pass until the stack changes; **RESOLVE ALL UNTIL
  DECISION** = pass until the stack is empty; **HOLD AFTER THIS RESOLVES** = stop once a
  chosen stack object has left the stack; **PASS UNTIL STACK CHANGES**. A forced stop is never
  skipped.

**Information-leak safety:** auto-passes look exactly like passes, and nothing ever says
"Jonathan has no playable responses". **BLUFF STOPS** (optional) also stop you on public
conditions only (cards in hand and an untapped permanent), so stopping doesn't reveal a real
response.

## Remembered answers (auto-yield) — built

A prompt that allows it is flagged `rememberable`. Answering with ALWAYS YES THIS TURN / ALWAYS
NO THIS TURN / ALWAYS YIELD stores the answer with the prompt's key **and its context**; the
same prompt in a different situation (e.g. a commander going to exile instead of the
graveyard) is asked again. "This turn" answers expire with the turn. Cancel one or all at any
time (`set_prefs cancel_yield / cancel_all_yields`). YIELD UNTIL END OF TURN is PASS UNTIL next
turn.

## MANA: you tap your own mana — built

Pod rule: **the engine never taps anyone's lands or mana sources.** Players tap their own mana
(double-click / T / right-click Tap on a land or mana source taps it *for mana* when automation
is on), and every cost is paid from the mana pool.

- Mana already in your pool that covers the cost: the spell or ability goes on at once.
- Not enough in your pool: a **Pay {1}{G} — tap your mana** prompt opens. Your untapped mana
  sources are highlighted; click them on the table (or in the prompt) to tap them. Only mana
  abilities can be used while it's open. The spell goes on the moment your pool covers the cost;
  CANCEL leaves the table untouched (mana you tapped stays in your pool).
- The same goes for echo / "sacrifice unless you pay", morph costs and filter lands' activation
  costs: tap first, then pay.
- If a mana ability can add different colors, the one that helps the pending payment is added.

Convoke creatures and spend-restricted mana still need a hand in some cases (tap them with the
table tools). The older AUTO / ASK / MANUAL payers remain inside the engine for its own tests
only; clients can't select them.

## Smart prompting and optional effects — built for templated effects

- A single deterministic result is performed without asking.
- Real choices are asked (target, mode, private filtered search, color).
- Optional "may" effects get a compact YES/NO; declining is recorded, never nagged.
- Mandatory vs optional is part of the effect model: mandatory deterministic → automatic;
  mandatory with a choice → ask the choice; optional → ask whether.
- Triggered abilities go on the stack automatically (FULL) or after one confirmation listing
  them (ASSISTED: "Triggered: Alpha, Beta [PUT ON THE STACK] [BY HAND]"). Several of your own
  triggers at once: a private ORDER choice, skipped when they are identical and AUTO ORDER
  IDENTICAL TRIGGERS is on. APNAP order across players is decided by the engine.
- AUTO RESOLVE OWN TRIGGERS: OFF / SAFE ONLY / ON is stored per player; today your own triggers
  already resolve without a stop unless you have a response (RESPONSE AUTO).

## Repeat a combo — built

**REPEAT LAST VALIDATED SEQUENCE:** after doing a sequence once this turn, repeat your last N
intents N times or until a condition (mana, tokens, a player's life, a counter). Every
iteration goes through the rules engine; the repeat stops as soon as an iteration is illegal,
needs a choice or is random, and the table is left after the last complete iteration. The
whole repeat is one undo entry and its log folds under "Alice repeated the sequence ×30".
Fyodor never decides by itself that a board "is" an infinite loop.

## When automation goes wrong — built

- Every intent is transactional: it is compiled on a scratch copy and applied as one history
  entry, or not at all.
- An unexpected engine error becomes **AUTOMATION ERROR** ("Fyodor couldn't carry out pass
  priority. Nothing changed. Resolve it manually with the table tools, pause automation, or
  export a rules scenario."), and the table carries on.
- **EXPORT RULES SCENARIO** (developer tool: `FYODOR_DEV_TOOLS=1`, host computer only,
  `GET /api/games/{id}/rules/scenario`): the table just before the intent(s), hidden zones
  redacted unless referenced, the recorded intents and decisions (with shuffle/dice results),
  the failure, card Oracle ids and hashes, script versions, and build/engine/CR versions.
  `app.rules.scenario.replay()` re-runs it with the current engine for a regression test.

## Animations are not rules timing

The server applies input the moment it arrives; nothing in the rules state waits for a client
animation. RESPOND / STOP / HOLD PRIORITY are preferences (`set_prefs`) that are accepted at any
time, even without priority. Renderers animate afterwards to catch up with the authoritative
state.

## Client (M18) — built on the 2D table

- **HUD** (top right): `AUTO: FULL · RESP: AUTO · MANA: ASK`. RESP and MANA cycle on click; the
  host's AUTO menu switches OFF / ASSISTED / FULL and PAUSE / RESUME.
- **Creating a table / LAN lobby:** an Automation selector (default OFF). The old response
  helper is only offered with automation OFF.
- **Priority bar:** whose priority, PASS / NEXT, RESOLVE ONE, RESOLVE ALL, END TURN, cancel a
  pass-until, and the HOLD / FULL CONTROL / STOP overrides.
- **STACK — N** helper with targets and HOLD AFTER THIS RESOLVES (⏸).
- **Prompts** for every decision kind: choose one / confirm with remembered answers, order,
  choose cards (private search, discard, scry), grouped reconciliation, declare attackers and
  blockers.
- **Gestures → intents:** dragging a land from your hand onto your battlefield plays it; dragging
  a spell onto the table or the stack casts it. **Alt-drop** is the manual override (the card just
  moves, logged as done by hand).
- **Card menu:** Play land / Cast / Activate: <ability> (disabled unless the server lists it as
  legal now), Automation AUTO / MANUAL, Mana source PREFER / NORMAL / SAVE, Hold after this
  resolves.
- **Highlights** come only from `rules.hints` (the viewer's own legal actions): subtle outlines,
  never a glow on everything.
- **AUTOMATION ERROR** panel: resolve manually, pause automation, or export the rules scenario.

Still to come: resolution speed NORMAL / FAST / INSTANT with batched presentation
("Treasure ×30"), ability buttons on permanents, player plates as click targets, and the 3D
client (M19).
