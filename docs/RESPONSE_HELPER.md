# Response helper

A lightweight "anything in response?" check for LAN tables. It **asks; it never enforces**,
and it never locks the table.

Modes (table setting `priority_helper`, chosen in the lobby):

* **Off** — nothing is asked (default for hot-seat tables, where one person runs everything).
* **Simple** — described below (default for LAN lobbies).
* *Structured* (per-step priority passing) is reserved; not built.

## Simple mode

| Trigger | What happens |
|---|---|
| Something goes on the stack (cast from any zone, or *Put ability on stack*) | Everyone else sees **RESPOND / PASS / AUTO-PASS**. When all have passed: “Everyone passed.” |
| **Resolve top** with the stack non-empty | Asks first, then resolves automatically once everyone passes — unless everyone *just* passed on that stack item, in which case it resolves at once. |
| **Next step** / **Next turn** | Asks first (“Alice wants to move to combat”), then moves on automatically once everyone passes. |

* **RESPOND** puts a pending step/resolve on hold and tells the table who is responding; the
  responder's own spell or ability then opens a new check.
* **AUTO-PASS** passes every check until the end of the current turn (toggle again to stop).
* The player who asked can always **Go ahead anyway** (or send the request with `force`), and the
  host can **Force** any check closed. Every other action keeps working while a check is open.
* Going back a step (`Previous step`) never asks.

Keys (from the central hotkey table, `frontend/src/game/hotkeys.ts`): **P** pass, **R**
respond, **Shift+P** auto-pass. A unit test guarantees no key is bound twice.

## Under the hood

The check is public game state (`GameState.response`): who asked, what for, who is still
waiting, who passed, and — server-side only — the resolved action (“intent”) to carry out.
Clients can't open checks themselves: the server turns a `phase` / `next_turn` /
`resolve_top` request into a `response_open` in its resolve step, and applying the final
`response_pass` applies the stored intent. Everything is in the action history, so undo and
redo replay it exactly.
