# Teach Fyodor

Fyodor plays most cards by itself. When a new set brings a mechanic it has never seen, or a card has one line it still leaves
to you, you can **teach** it — no programming, no files to edit. You snap pieces together, like the apps that teach children to
code, read back what Fyodor understood, try it at a test table, and keep it. Everything you teach is **data**, never code: it
lives in your `app.sqlite` beside your decks, goes into every backup, and can be shared with the pod as a small file.

Open it from the top bar: **Teach** (also linked from **Cards**).

## The page

```
┌──────────────────────────────────────────────────────────────┬───────────────────┐
│ ‹  TEACH FYODOR   [▶ Try it]  (?)             [di] [Re] [+]  │                   │
├──────────────────────────────────────────────────────────────┤  COMMANDS         │
│ ( A keyword | An action | One card's line )                  │  ■ Cost ▾         │
│ Action (the verb) [dive  ]  ☐ has a number N   Reminder […]  │  ■ Do ▾           │
│ Cards say it dives, target creature dives; the Do pieces     │   Draw cards …    │
│ below are what happens to that creature ("it").              │   Can't be        │
├──────────────────────────────────────────────────────────────┤    blocked until …│
│ WHAT HAPPENS                                                 │  ■ Then ▾         │
│  ■ The action                                                │  ■ Target ▾       │
│     ■ [this creature] can't be blocked [until it deals       │  ■ Values ▾       │
│        combat damage while attacking]                   🗑    │   1 2 3 4 5       │
├──────────────────────────────────────────────────────────────┤                   │
│ FYODOR READS IT AS                                           │                   │
│ It can't be blocked until it deals combat damage while       │                   │
│ attacking.                                                   │                   │
│ On a card: When this creature enters, it dives. Fyodor reads │                   │
│ it as "When this creature enters, it can't be blocked until  │                   │
│ it deals combat damage while attacking."                     │                   │
│ ✓ Fyodor understands this and will play it by itself.        │                   │
│ [Teach it]                                                   │                   │
└──────────────────────────────────────────────────────────────┴───────────────────┘
  TAUGHT SO FAR   Action dive  (on) Edit Export Delete           [Export all] [Import a file…]
```

* **Left — the script.** Each ability is a stack of rows. The top row (green) is the **When**: what starts it. The rows under
  it say what happens. The small square on the left is the row's category colour; the white boxes are **chips** — tap one to
  change a number or a choice. Rows nest under "You may …", "If you do …" and "You may pay …". An **action** has one stack whose
  top row is fixed (*The action*): its Do pieces are what happens to the creature a card names.
* **Right — the Commands.** Every piece Fyodor knows, grouped by colour. **Drag** one onto the script (the places it may land
  light up, the one under your finger glows) or just **click** it to snap it into the first place it fits. **Target** chips drop
  on orange settings, **Values** chips on white numbers; **N** is the number written after a keyword or an action ("Plunge 2").
* **Under the script — the readback.** The sentence Fyodor will read, and its verdict from the real rules engine as you build.
  If something is out of place it says what ("put a Do piece inside You may"). For an action, also the line a card would carry
  and what Fyodor reads instead. The engine's own definition is there for the curious.
* **Top — ▶ Try it** opens a test table: the card in hand, lands to cast it, a library to mill, a target dummy, automation on.
  **?** is the help. The small tiles are the things you have taught; click one to edit it, **+** starts fresh.
* **Keyboard:** Enter on a command adds it; on a row, ↑ ↓ move it, Delete removes it, Enter edits its first chip; Escape closes
  a chip's menu. Nothing needs a drag.

Three things can be taught:

* **A keyword** — a word on its own line of a card, maybe with a number ("Plunge 2"): the abilities it stands for, each with a When
  piece. Every card whose text has the keyword gets them.
* **An action** — a verb cards use *inside* a sentence ("it dives", "target creature dives", "that creature dives"; with a number,
  "plunge 2" like "bolster 2"): what happens to the creature the sentence names. The card's own words say *when*; the pieces say
  *what*. Every card that says the verb reads it as your pieces.
* **One card's line** — one ability of one card Fyodor plays by hand, taught for that card only.

Categories: **When** (triggers; also *Pay to use it* for activated abilities and *Always* for statics) · **If** (conditions) ·
**Cost** (what an activated ability costs, "Activate only…" limits, and *You may pay…* optional costs) · **Do** (effects) ·
**Always** (static abilities) · **Then** (*You may…*, *If you do…*, *Then*) · **Target** · **Values**. An action offers Cost, Do,
Then, Target and Values only.

## Worked example: dive, the real card

The first card with dive reads:

> *Devour 3 (As this creature enters, you may sacrifice any number of creatures. This creature enters with three +1/+1 counters on
> it for each creature sacrificed this way.)*
> *When this creature enters, if it devoured a creature, it dives. (It can't be blocked until it deals combat damage while
> attacking.)*

So "dive" is a **keyword action** — a verb in a sentence ("it dives"), like "it explores" — not a keyword with a number. The
reminder text says everything: a creature that dives can't be blocked until the first time it deals combat damage as an attacker;
that lasts across turns, and a creature that leaves the battlefield and comes back is a new creature that never dived.

**Fyodor knows dive natively** now (`backend/app/rules/dive.py`: the duration "until it deals combat damage while attacking", the
rewrite of "X dives", and the condition "if it devoured a creature"), so the card plays by itself without teaching. Here is how you
would have taught it the day the card leaked, in about a minute — and how you teach the next verb like it:

1. Open **Teach** and pick **An action**. Type `dive` as the verb (lowercase: cards say "it dives"). Paste the reminder text if you
   like (it is only shown back to you). Leave **has a number** unticked.
2. The stack already starts with *The action*. From **Do**, click **Can't be blocked until …**. It snaps under the top row:
   *this creature can't be blocked [this turn]*.
3. Tap the duration chip and choose **until it deals combat damage while attacking**. (The other durations: *this turn*, *until
   your next turn*, *until it deals combat damage* — any combat damage, blocking included.)
4. Read it back: *It can't be blocked until it deals combat damage while attacking.* Under it: *On a card: When this creature
   enters, it dives.* → *When this creature enters, it can't be blocked until it deals combat damage while attacking.* The verdict
   turns green: *Fyodor understands this and will play it by itself.*
5. **▶ Try it.** No printed card says "dives" yet, so a plain creature stands in for one that dives as it enters. Cast it; on your
   next turn attack with it: the table shows *Can't be blocked — until it deals combat damage while attacking* on it, nobody may
   block it, and once it connects the marker goes and it can be blocked again.
6. **Teach it.** From now on every card whose text says `it dives`, `target creature dives`, `that creature dives` … reads those
   words as your pieces in new games — including cards that arrive with the next card-database update, because Fyodor reads the
   text when a game starts. The card's own "if it devoured a creature" stays the card's: the action only says what diving does.

The real card's **If** piece is also there for the next card like it: **It devoured a creature** (and *It devoured N or more
creatures*), beside *It was kicked* and *You cast it*. These go right under a When piece on a keyword or a card line ("When this
creature enters, if it devoured a creature, …").

### A keyword with a number

Keywords work the same way with a When piece on top. Suppose a card read: *Plunge 2 (When this creature enters, mill two cards,
then you may return a creature card with mana value 2 or less milled this way to your hand.)*

1. Pick **A keyword**, type `Plunge`, tick **has a number N**.
2. From **When**, click **Enters**: *When this creature enters*. From **Do**, click **Mill cards** and set its number chip to **N**.
3. From **Then**, click **You may …**; from **Do**, click **Keep one of the milled cards** (it snaps inside) and set its number to **N**.
4. Read it back: *When this creature enters, mill N cards. You may put a creature card with mana value N or less from among the cards
   milled this way into your hand.* — *On a card: Plunge 2 (… mill two cards … mana value 2 or less …)*. **Teach it**: every card
   saying `Plunge 3`, `Plunge 1`, … plays by itself.

## One card's line

Pick **One card's line**, find the card, and its text appears line by line with a dot: green — Fyodor plays it; red — Fyodor
leaves it to you; brass — you taught it. Click **Teach this line** on a red one and build what it does. If the red line looks
like a keyword ("Plunge 2"), the page offers **Teach "Plunge" as a keyword** instead, which covers every card with it; if it says
"it plunges", **Teach "plunge" as an action**. A taught line applies to that card only (every printing of it).

## What happens underneath (for the curious)

A taught entry is a small piece of data: pieces, their settings, a name. When a game starts, Fyodor writes each taught keyword,
action or line out as the Oracle sentence it stands for and reads it with the same parser it uses for every printed card — so the
taught ability is automated, replayed, saved and kept private exactly like any other. Only pieces from Fyodor's own vocabulary are
accepted, every value is checked against its allowed range, and a card is only "taught" if the engine confirms it can read the
result (the same check behind the FULL/PARTIAL/MANUAL coverage levels). An action's phrase is replaced inside the card's own
sentence, its reminder text dropped, the subject the card used kept ("target creature dives" → "target creature can't be blocked
until …").

* **New games** start with the enabled entries. **Games in progress** (and saved games) keep the entries they started with, so
  editing or deleting an entry later never changes a game under way or breaks a replay.
* **LAN:** the host's taught entries apply to every table the host runs. Other players can look at the page; only the host
  computer can change the library or open a Try it table.
* **Off switch:** each entry has an on/off toggle in *Taught so far*; off means new games ignore it without forgetting it.
* **Backups:** the library is in `app.sqlite`, which every backup (automatic or by hand) includes. A restore brings it back.
* **Coverage reports:** `python -m tools.commander_coverage` applies the host's library and reports how many cards it reaches
  ("taught N"); `--no-taught` shows the engine alone.

## Sharing with the pod

*Taught so far* → **Export all** (or **Export** on one row) saves a small JSON file (`dive.fyodor-teach.json`). Send it however
you like; the other host opens **Teach** → **Import a file…**. A file is checked as strictly as a new entry: an unknown field,
piece or value refuses the whole file, and it can never contain code. Importing something already taught replaces it.

The file looks like this — it is only names, piece ids and choices:

```json
{"format": "fyodor-teach", "version": 1, "entries": [{"kind": "action", "name": "dive", "param": false,
  "reminder": "It can't be blocked until it deals combat damage while attacking.",
  "abilities": [{"hat": {"id": "action"}, "body": [{"id": "unblockable_for",
  "values": {"who": "t_self", "dur": "rdur_combat_attacking"}}]}]}]}
```

## Limits

* The pieces cover common shapes: triggers (enters, dies, attacks, blocks, combat damage to a player, becomes a target,
  landfall, another creature enters/dies, you/an opponent casts a spell, gain life, upkeep/combat/end step), activated
  abilities with mana / tap / sacrifice / discard / life / counter / exile-from-graveyard costs and "only as a sorcery" / "once
  each turn" limits, optional costs, conditions (including *it devoured a creature*, *it was kicked*, *you cast it*), effects
  (draw, discard, damage, life, tokens, counters, destroy, exile, bounce, tap/untap, mill, scry, surveil, search, return from
  graveyard, sacrifice, copy, counter, gain control, pump and keyword grants *until end of turn* or *until your next turn*,
  evasion *this turn / until your next turn / until it deals combat damage (while attacking)*, add mana, investigate,
  proliferate) and statics (keywords, +X/+X, anthems, evasion, cost reduction, enters with counters / tapped). A mechanic that
  needs something outside this set (a new zone, a new kind of counter, a new timing rule) still needs a code change.
* The expressiveness sweep added: triggers when it *becomes blocked*, *blocks or becomes blocked*, *is dealt damage*, *a creature
  of yours attacks alone*, *you attack*, *any creature dies*; conditions for what happened this turn (raid, morbid, revolt …),
  what is true now (lieutenant, ferocious, hellbent, delirium …) and *it had no +1/+1 (−1/−1) counters*; costs *discard this
  card* (cycling-like) and *exile this card from your graveyard*, and a boast-like limit; effects *sacrifice it [unless you pay
  …]* (echo-like), *return it* after it died (undying, persist), *counter that spell or ability unless its controller pays …*
  (ward-like, only under *Becomes a target*), exalted- and battle-cry-like pumps; statics for combat rules (defender, "attacks
  each combat if able" …), evasion *except by* flying/reach, two or more creatures (menace), artifact and/or black creatures
  (fear), *by* creatures with greater power (skulk), landwalk, *if it would die, exile it instead*, damage prevention, *can't be
  countered*, *this spell costs {N} less …* (affinity, undaunted), extra and alternative costs (spectacle-, surge-like),
  casting a permanent card from the graveyard (escape-like, retrace) and the **Kicker** and **Flashback** pieces (the engine's
  own wording for an optional additional cost and for a spell exiled as it leaves the stack: a mechanic built on them is still
  your own, e.g. "Rekindle 2" = Flashback {2}). Some pieces only read under certain When pieces; the page only lets them snap
  there. What every keyword, keyword action and ability word of the rules can and can't be taught as:
  [TEACH_FYODOR_COVERAGE.md](TEACH_FYODOR_COVERAGE.md).
* A keyword's name must be one Fyodor doesn't already know (you can't redefine *Flying*); an action's verb must not be a keyword
  action of the rules (you can't redefine *explore*). An action is one word and one stack of Do pieces; "each creature you
  control dives" is left to the players (a group can't stop being unblockable one creature at a time).
* Up to 4 abilities per entry, 12 pieces per ability, 500 entries.

For developers: the vocabulary is `backend/app/rules/taught_vocab.py` (pieces are Oracle templates), the checker and applier
`backend/app/rules/taught.py`, storage `backend/app/storage/taught.py` (migration 12), API `backend/app/api/teach.py`, the page
`frontend/src/pages/TeachPage.tsx` with `frontend/src/teach/`. `python -m tests.teach_matrix` regenerates the fixtures that keep
the page's readback and the backend's sentences identical; `tests/test_teach.py` and `tests/test_teach_matrix.py` cover it.
`python -m tests.teach_coverage` regenerates TEACH_FYODOR_COVERAGE.md from `tests/teach_coverage.py` (`tests/test_teach_coverage.py`
checks every row with the engine; `tests/test_teach_playtests.py` plays the representative ones against their native keyword). The
native dive is `backend/app/rules/dive.py` with `tests/test_rules_dive.py`.
