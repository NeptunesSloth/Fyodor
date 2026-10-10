"""-- draw bodies (wave 28B) -- "If you would draw a card, instead <effects>" (CR 121.6, 614.11).

The replacement effect of a draw can do whatever its text says (Underrealm Lich looks at three cards, Eruth exiles two, Blood
Scrivener draws two and loses life, Enduring Renewal reveals the top card). Such a body is the effect grammar's own instructions
(``scripts.parse_effects``), kept in the static's op (``{"do": "body", "effects": [...]}``) and run as a small resolution of its own
(a context with no stack object, ``body_done`` saying how it ends) by ``replace.do_draws``:

* 121.6b / 614.11a: the body is completed before the sequence of draws goes on. The draws after it are planned only once it is
  done (``replace.draw_cards`` cuts the plan at a body and the continuation ``draw_rest`` plans the rest), so a body that moves
  cards (a mill, a look) is what the next draw's replacements see, and a body's own choices (which of three cards) are its player's.
* 614.5: a draw inside the body (Blood Scrivener's "you draw two cards", Enduring Renewal's "Otherwise, draw a card") is a new
  event the same effect doesn't replace again; any other draw replacement may apply to it (``repl_applied`` in the context).
* 614.6 / 121.5: the replaced draw never happens: nothing triggers on it, and cards the body puts into a hand aren't drawn.

Only a fixed set of instructions is allowed in a body (those whose resolution doesn't depend on a stack object or a target), for
the player who controls the effect ("you"); anything else stays manual.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

BODY_OK = frozenset({"look_top", "pick_looked", "rest_looked", "exile_top", "grant_play", "return_choice", "only_if", "draw",
                     "lose_life", "gain_life", "mill", "scry", "surveil", "add_counters", "create_token", "discard"})
_WHO_OK = ("you", "ref:", "self", "each_opponent")


def parse(text: str) -> list[dict[str, Any]] | None:
    """The body's instructions, or None when the grammar doesn't read them all, one needs a target or says something else."""
    from app.rules import scripts

    text = text if text.endswith(".") else text + "."
    if text.endswith(" If you can't, you lose the game."):  # (Forbidden Crypt, Out of the Tombs: 104.3e; checked by the previous instruction)
        got = parse(text[: -len(" If you can't, you lose the game.")])
        return None if got is None or got[-1]["do"] != "return_choice" else [*got[:-1], {**got[-1], "lose_if_none": True}]
    found = scripts.parse_effects(text)
    if found is None:
        return None
    effects, targets, optional = found
    if targets is not None or optional or not effects:
        return None
    for e in effects:
        who, player = e.get("who", "you"), e.get("player", "you")  # (look_top / exile_top / mill name the library's owner: "you")
        if e["do"] not in BODY_OK or not isinstance(who, str) or not who.startswith(_WHO_OK) or player != "you":
            return None
    return effects


def supported(effects: list[dict[str, Any]]) -> bool:
    return all(e.get("do") in BODY_OK for e in effects)


def run(plan: Plan, ev: dict[str, Any], then: dict[str, Any]) -> None:
    """Carry out a body event as a resolution of its own: ``then`` (a continuation, replace.run_then) runs when it ends."""
    import copy

    from app.rules import effects

    ctx: dict[str, Any] = {"controller": ev["controller"], "source_card": ev.get("source_card"), "source_object": ev.get("source_oid"),
                           "name": ev.get("label") or "A replacement effect", "targets": [], "stack_id": None, "kind": "replacement",
                           "effects": copy.deepcopy(ev["effects"]), "next": 0, "x": 0, "event": None,
                           "repl_applied": list(ev.get("applied") or []), "body_done": then}
    effects.continue_effects(plan, ctx)
