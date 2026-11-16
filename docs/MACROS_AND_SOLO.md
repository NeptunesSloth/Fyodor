# Custom actions (macros) and solo tools

## Custom actions

Some cards and house mechanics are fiddly to do by hand every time. A custom action (a
*macro*) is a short list of steps you run from the card's menu. **Custom actions ▸** lists
the macros saved for that card (every printing, matched by Oracle id) plus your library.
Use **New custom action…** to build one.

Macros are **data, never code**. Each step is one of these whitelisted primitives:

| Step | Fields |
| --- | --- |
| `CREATE_TOKEN` | a token card id, or name / type line / power / toughness; count; for me / each opponent / each player |
| `ADD_COUNTER`, `REMOVE_COUNTER` | this card or the selected cards; counter kind; amount |
| `CHANGE_LIFE` | me / each opponent / each player; ± delta |
| `ADD_MANA` | a W/U/B/R/G/C amount map |
| `MOVE_CARD` | this or selected → hand, graveyard, exile, library, battlefield, command |
| `ROLL_DIE`, `FLIP_COIN` | sides, count |
| `CREATE_MARKER` | a temporary effect marker (e.g. "Hexproof") |
| `SET_NOTE`, `SET_CHOICE` | note text; a named choice ("Chosen type: Dragon") |
| `CREATE_ARROW` | point at the selected objects or each opponent |
| `CHANGE_CONTROLLER` | this or selected → me |
| `DISPLAY_TEXT` | a line in the log |

- **Validation:** every definition is validated by a strict schema. Unknown ops, unknown
  fields, more than 20 steps or out-of-range numbers are rejected.
- **Execution:** the server expands the steps into ordinary table actions and resolves them
  in order. They go through the same permission and hidden-information checks as clicking.
  The whole macro is **one history entry**: a single Undo takes all of it back.
- **Randomness:** the server rolls dice and coins once and records the results, so Redo
  replays the same result.
- **Storage:** macros live in the app database (`/api/macros`). The host machine can edit
  them, and so can a seated player's browser (with a seat token). Deleting is local only.
- **What macros never do:** they don't trigger themselves, watch for events or enforce
  rules. You run them.

## Solo tools (⋯ → Solo tools)

- **Spawn a card…**: put any card from the local card database onto your battlefield as a
  **test object**.
  - A "TEST" mark shows it to everyone.
  - It is never part of a deck, and Reset removes it.
  - Test objects are off at LAN tables until the host turns them on (**Allow test cards**).
    They are on by default in local/hot-seat games.
- **Reset my deck…**: gathers your cards back into your library (commanders go to the
  command zone). It also removes your tokens, copies and test objects, clears counters,
  markers and life changes, then shuffles and draws 7. This is undoable.
- **New opening hand**: a free redraw.
- **Add a target dummy** (host; also a checkbox when you start a Sandbox test on the Play page): seats a
  **Target Dummy** opponent with no deck, the table's starting life, poison and commander damage, so "each
  opponent", targeted damage and drain effects have someone to hit. Needs test cards allowed (as Spawn a card).
  - It **never takes a turn**: ending your turn comes straight back to you (with the rules on too), so it never
    draws. A draw an effect makes it take from its empty library doesn't lose it the game (704.5b is waived for
    it); everything else does (0 life, 10 poison, 21 commander damage): that is the lethal you are testing.
  - With rules automation on, the server answers for it at once: it passes priority, declares no attackers and
    no blockers, and takes the first (or "none") answer to any other choice. Its answers are recorded actions,
    so they replay the same; **one Undo takes back your action together with the dummy's answers to it**, and
    Redo puts both back. The response helper never waits for it. A choice it can't answer is left to you (pause
    automation), with a log line saying so.
  - **Spawn a card** can put a test card on the dummy's battlefield (a blocker to test against with the rules
    off, or a removal target); *Give control* works too.
  - **Reset dummy…** (host): life back to the start, poison, other counters and commander damage cleared, its
    test cards and tokens removed and any card it was given returned to its owner. If it lost, it comes back
    into the game (**Restore dummy…**) and play goes on. Undoable like any table action.
  - A table with a dummy records no pod result: when the rules end the game, the table shows it, and Reset
    dummy (or Undo) carries on. Nobody can join in the dummy's seat.
- **Restart game…** (host): resets every deck, back to turn 1.
