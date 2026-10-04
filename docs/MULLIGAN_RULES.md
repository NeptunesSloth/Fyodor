# Mulligan rules

Fyodor deals opening hands and walks each player through keep / mulligan / bottom at the
same time. Every rule is a **`MulliganPolicy`**: plain data, never code. The table's policy is
chosen in the lobby (or in *New game* for hot-seat) and stored in the save.

## Presets

| Rule | What it does | Source |
|---|---|---|
| **Commander London** (default for Commander) | Draw 7. Each mulligan: shuffle the hand into the library, draw 7. When you keep, put 1 card on the bottom per mulligan **after the first** (the first mulligan is free). | CR 103.5 + 103.5c (multiplayer free mulligan), as used by Commander |
| **London** (default otherwise) | Same, but every mulligan counts: keep 7, bottom N after N mulligans. | CR 103.5 |
| **Boston (Custom Pod)** | A named slot for our pod's house rule. **It has no mechanics until the host defines them.** | Our pod — *not* an official rule |
| **Custom** | Any combination of the fields below, for one-off experiments. | — |
| **None (by hand)** | No opening-hand phase; draw and mulligan manually (the old sandbox behaviour). | — |

## Policy fields

| Field | Meaning |
|---|---|
| `display_name` | Shown in the lobby, the overlay and the log. |
| `starting_hand_size` | Cards in the first hand. |
| `draw_count` | Cards drawn for each new hand after a mulligan. |
| `free_mulligans` | Mulligans that don't count toward cards put on the bottom. |
| `cards_to_bottom` | Cards put on the bottom **per counted mulligan**, chosen after keeping. |
| `shuffle_between_mulligans` | Shuffle the library each time a hand is sent back (otherwise the rejected cards go to the bottom unshuffled). |
| `partial_hand_selection` | The player picks *which* cards to send back and draws that many, instead of the whole hand. |
| `set_aside_rejected_hands` | Rejected cards go to a private, face-down **set-aside** zone instead of the library. |
| `final_shuffle` | When the player keeps, set-aside cards are shuffled into the library. |
| `minimum_hand_size` | No mulligan may leave a smaller kept hand. |
| `max_mulligans` | Upper limit on mulligans (empty = no limit). |
| `needs_definition` | Set on the Boston slot until the host fills it in. |

Cards to bottom after *m* mulligans = `max(0, m − free_mulligans) × cards_to_bottom`.

## How a game uses it

1. When the game starts, everyone gets `starting_hand_size` cards and the **Opening hand**
   overlay opens. Decisions are simultaneous and independent.
2. **Mulligan** (`mulligan_take`) → **Keep** (`mulligan_keep`). If cards must go to the bottom,
   the player selects exactly N cards (“Selected 1 / 2”; *Put 2 on the bottom* stays disabled
   until the count is exact), in order — the last one picked goes to the very bottom
   (`mulligan_bottom`).
3. The game proper starts when every player has kept. The host can press **Start now**
   (`mulligan_finish`, host-only on LAN); anyone still deciding keeps the hand they hold.
4. The overlay never locks the table: **Hide** peeks at the board, and manual actions keep
   working.

**What others see:** mulligan counts, “Choosing 2 for the bottom”, and the log line
“Bob kept 7 and put 2 cards on the bottom.” They never see which cards. Bottomed cards become
anonymous library cards (not even their owner keeps a record of them), and set-aside cards are
owner-only placeholders. Randomness is resolved on the server and recorded, so undo/redo
replays exactly the same hands.

## Defining “Boston (Custom Pod)”

“Boston mulligan” is our pod's name, not an official rule, so Fyodor doesn't guess what it
means. A table with the undefined slot can deal hands and keep 7, but **Mulligan** is
disabled, and the lobby lists *“The Boston (Custom Pod) mulligan isn't defined yet”* as a start
blocker (the host may still *Start anyway*).

To define it, the host opens **Table settings → Mulligan → Boston (Custom Pod)** (or picks it
in *New game*) and answers these questions with the editor's fields:

1. How many cards is the opening hand? → `starting_hand_size`
2. After a mulligan, how many cards do you draw? → `draw_count`
3. Does the whole hand go back, or do you choose some cards? → `partial_hand_selection`
4. Do rejected cards go back into the library, or aside? If aside, do they come back after you
   keep? → `set_aside_rejected_hands`, `final_shuffle`
5. Is the library shuffled between hands? → `shuffle_between_mulligans`
6. How many mulligans are free, and how many cards go to the bottom per counted mulligan?
   → `free_mulligans`, `cards_to_bottom`
7. Is there a minimum hand size or a limit on mulligans? → `minimum_hand_size`, `max_mulligans`

The definition is remembered in the host's browser for the next table. If the pod's rule needs
a step these fields can't express (for example "reveal the rejected hand" or "opponents
choose"), that is a new field to add here, not a behaviour to invent.

## Opening-hand actions (CR 103.6; wave 18C)

With rules automation on and a guided mulligan, the table asks one more thing after the last player has kept (the same
`mulligan_keep` / `mulligan_bottom` / `mulligan_finish` action that ends the mulligans carries the compiled first decision, so
replays and undo are exact): **each player, the starting player first and then in turn order, chooses which cards of their
opening hand to use** (`app/rules/opening_hand.py`).

* "If this card is in your opening hand, you may begin the game with it on the battlefield." (the Leylines, Leyline Axe,
  Quicksilver): the card enters like any permanent (103.6a). Gemstone Caverns is offered only to a player who is not the starting
  player; it enters with a luck counter and its player then exiles a card from their hand.
* "You may reveal this card from your opening hand. If you do, at the beginning of the first upkeep / your first upkeep / your first
  main phase of the game, …" (the Chancellors, Sphinx of Foresight): the card is revealed to the table (103.6b) and its delayed
  trigger is created for the revealer; the card is hidden again once the last player has acted.
* **Privacy**: every player gets the same prompt whether or not their hand holds such a card, so neither the decision nor its timing
  says anything about a hand. The options are visible to the chooser only; the others see "is making a choice".
* Not read (manual): Chancellor of the Annex (a per-opponent delayed cast trigger), Leyline of Transformation (a choice as it
  enters), Serum Powder's "any time you could mulligan" action.
