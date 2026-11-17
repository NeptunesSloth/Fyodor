# Teach Fyodor

Fyodor plays most cards by itself. When a new set brings a mechanic it has never seen, or a card has one line it still leaves
to you, you can **teach** it — no programming, no files to edit. You snap pieces together, like the apps that teach children to
code, read back what Fyodor understood, try it at a test table, and keep it. Everything you teach is **data**, never code: it
lives in your `app.sqlite` beside your decks, goes into every backup, and can be shared with the pod as a small file.

Open it from the top bar: **Teach** (also linked from **Cards**).

## The page

```
┌──────────────────────────────────────────────────────────────┬───────────────────┐
│ ‹  TEACH FYODOR   [▶ Try it]  (?)             [Di] [Re] [+]  │                   │
├──────────────────────────────────────────────────────────────┤  COMMANDS         │
│ ( A keyword | One card's line )                              │  ■ When ▾         │
│ Keyword [Dive   ]  ☑ has a number N   Reminder text […]      │   Enters  Dies …  │
├──────────────────────────────────────────────────────────────┤  ■ If ▾           │
│ ABILITY 1                                                    │  ■ Cost ▾         │
│  ■ Enters                                                    │  ■ Do ▾           │
│     ■ mill [N] cards                                         │   Draw cards …    │
│     ■ You may …                                              │  ■ Always ▾       │
│        ■ put [a creature card] with mana value [N] or less … │  ■ Then ▾         │
│                                                         🗑    │  ■ Target ▾       │
├──────────────────────────────────────────────────────────────┤  ■ Values ▾       │
│ FYODOR READS IT AS                                           │   1 2 3 4 5 N     │
│ When this creature enters, mill N cards. You may put a …     │                   │
│ ✓ Fyodor understands this and will play it by itself.        │                   │
│ [Teach it]                                                   │                   │
└──────────────────────────────────────────────────────────────┴───────────────────┘
  TAUGHT SO FAR   Keyword Dive  (on) Edit Export Delete          [Export all] [Import a file…]
```

* **Left — the script.** Each ability is a stack of rows. The top row (green) is the **When**: what starts it. The rows under
  it say what happens. The small square on the left is the row's category colour; the white boxes are **chips** — tap one to
  change a number or a choice. Rows nest under "You may …", "If you do …" and "You may pay …".
* **Right — the Commands.** Every piece Fyodor knows, grouped by colour. **Drag** one onto the script (the places it may land
  light up, the one under your finger glows) or just **click** it to snap it into the first place it fits. **Target** chips drop
  on orange settings, **Values** chips on white numbers; **N** is the number written after a keyword ("Dive 2").
* **Under the script — the readback.** The sentence Fyodor will read, and its verdict from the real rules engine as you build.
  If something is out of place it says what ("put a Do piece inside You may"). The engine's own definition is there for the
  curious.
* **Top — ▶ Try it** opens a test table: the card in hand, lands to cast it, a library to mill, a target dummy, automation on.
  **?** is the help. The small tiles are the things you have taught; click one to edit it, **+** starts fresh.
* **Keyboard:** Enter on a command adds it; on a row, ↑ ↓ move it, Delete removes it, Enter edits its first chip; Escape closes
  a chip's menu. Nothing needs a drag.

Categories: **When** (triggers; also *Pay to use it* for activated abilities and *Always* for statics) · **If** (conditions) ·
**Cost** (what an activated ability costs, "Activate only…" limits, and *You may pay…* optional costs) · **Do** (effects) ·
**Always** (static abilities) · **Then** (*You may…*, *If you do…*, *Then*) · **Target** · **Values**.

## Worked example: "Dive N"

> This is an **invented** example. "Dive" was a leaked keyword from an upcoming set whose real text was unknown when this was
> written; the wording below is made up to show the steps. When the real card arrives, build whatever its reminder text says.

Suppose the card reads: *Dive 2 (When this creature enters, mill two cards, then you may return a creature card with mana
value 2 or less milled this way to your hand.)*

1. Open **Teach**, keep **A keyword**, type `Dive` as the keyword and tick **has a number N**. Paste the reminder text if you
   like (it is only shown back to you).
2. From **When**, click **Enters**. It becomes the green top row: *When this creature enters*.
3. From **Do**, click **Mill cards**. Tap its number chip and choose **N** (or drag the **N** value onto it): *mill N cards*.
4. From **Then**, click **You may …**. From **Do**, click **Keep one of the milled cards** — it snaps inside the "You may". Set
   its number chip to **N**; leave *a creature card*.
5. Read it back: *When this creature enters, mill N cards. You may put a creature card with mana value N or less from among the
   cards milled this way into your hand.* The verdict turns green: *Fyodor understands this and will play it by itself.* Under
   it: *On a card: Dive 2 (… mill two cards … mana value 2 or less …)* — the number is filled in per card.
6. **▶ Try it.** No real card has Dive yet, so a plain creature stands in for one with "Dive 2". Cast it: the trigger goes on
   the stack, two cards are milled, and Fyodor asks which creature card (if any) to keep.
7. **Teach it.** From now on every card whose text says `Dive 3`, `Dive 1`, … plays by itself in new games — including cards
   that arrive with the next card-database update, because Fyodor reads the keyword from the card text when a game starts.

## One card's line

Pick **One card's line**, find the card, and its text appears line by line with a dot: green — Fyodor plays it; red — Fyodor
leaves it to you; brass — you taught it. Click **Teach this line** on a red one and build what it does. If the red line looks
like a keyword ("Dive 2"), the page offers **Teach "Dive" as a keyword** instead, which covers every card with it. A taught line
applies to that card only (every printing of it).

## What happens underneath (for the curious)

A taught entry is a small piece of data: pieces, their settings, a name. When a game starts, Fyodor writes each taught keyword or
line out as the Oracle sentence it stands for and reads it with the same parser it uses for every printed card — so the taught
ability is automated, replayed, saved and kept private exactly like any other. Only pieces from Fyodor's own vocabulary are
accepted, every value is checked against its allowed range, and a card is only "taught" if the engine confirms it can read the
result (the same check behind the FULL/PARTIAL/MANUAL coverage levels).

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

The file looks like this — it is only names, piece ids and numbers:

```json
{"format": "fyodor-teach", "version": 1, "entries": [{"kind": "keyword", "name": "Dive", "param": true,
  "reminder": "…", "abilities": [{"hat": {"id": "etb"}, "body": [{"id": "mill", "values": {"n": "N"}},
  {"id": "may", "body": [{"id": "from_milled", "values": {"card": "card_creature", "n": "N"}}]}]}]}]}
```

## Limits

* The pieces cover common shapes: triggers (enters, dies, attacks, blocks, combat damage to a player, becomes a target,
  landfall, another creature enters/dies, you/an opponent casts a spell, gain life, upkeep/combat/end step), activated
  abilities with mana / tap / sacrifice / discard / life / counter / exile-from-graveyard costs and "only as a sorcery" / "once
  each turn" limits, optional costs, conditions, effects (draw, discard, damage, life, tokens, counters, destroy, exile, bounce,
  tap/untap, mill, scry, surveil, search, return from graveyard, sacrifice, copy, counter, gain control, pump, keyword until end
  of turn, add mana, investigate, proliferate) and statics (keywords, +X/+X, anthems, evasion, cost reduction, enters with
  counters / tapped). A mechanic that needs something outside this set (a new zone, a new kind of counter, a new timing rule)
  still needs a code change.
* A keyword's name must be one Fyodor doesn't already know (you can't redefine *Flying*).
* Up to 4 abilities per entry, 12 pieces per ability, 500 entries.

For developers: the vocabulary is `backend/app/rules/taught_vocab.py` (pieces are Oracle templates), the checker and applier
`backend/app/rules/taught.py`, storage `backend/app/storage/taught.py` (migration 12), API `backend/app/api/teach.py`, the page
`frontend/src/pages/TeachPage.tsx` with `frontend/src/teach/`. `python -m tests.teach_matrix` regenerates the fixtures that keep
the page's readback and the backend's sentences identical; `tests/test_teach.py` and `tests/test_teach_matrix.py` cover it.
