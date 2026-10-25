"""-- enters (wave 110D) -- "enters with" counter statics beyond the battlefield-only, one-kind, no-type shape (CR 2026-09-25).

* 614.1c / 122.6: "each Human creature you control enters with an additional +1/+1 counter" is replace_grammar's counters static;
  113.6 / 113.6b: "As long as this creature is in your graveyard, …" lets it work from the graveyard (flag ``gy110d``, replace.static_candidates).
* 614.1e: "… and as a Mutant in addition to its other types" (Master Biomancer): the same replacement gives the entering permanent a subtype
  (op ``add_subtype110d``; ``entered`` adds it as the permanent enters, a permanent layer-4 effect, 205.1b).
* 614.1a / 611.2a / 609.7a: "Until your next turn, if that creature would deal combat damage to one of your opponents, it deals triple that damage to that
  player instead" (Jeska, Thrice Reborn): a record naming the chosen creature as the source (``oids``), players only, until your next turn.
* 122.6 / 614.12: "For each kind of counter on Blue, Loyal Raptor, each other Dinosaur you control enters with a counter of that kind on it":
  one +1 static per kind of counter on the source now (op ``kinds110d``; ``kinds``).
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

_GY = re.compile(r"As long as ~ is in your graveyard, (each .+ enters with .+)")
_MUTANT = " and as a Mutant in addition to its other types."
_BIO = "Each other creature you control enters with a number of additional +1/+1 counters on it equal to ~'s power"
_JESKA = ("0: Choose target creature. Until your next turn, if that creature would deal combat damage to one of your opponents, "
          "it deals triple that damage to that player instead.")
_BLUE = "For each kind of counter on ~, each other Dinosaur you control enters with a counter of that kind on it."


def in_graveyard(card: Any, ch: Any) -> bool:
    return any(a.text.startswith("As long as this creature is in your graveyard, each ") for a in ch.abilities)


def kinds(card: Any, d: dict[str, Any]) -> list[str | None]:
    """The counter kinds a static is applied for: [None] = the one it names."""
    if not d["op"].get("kinds110d"):
        return [None]
    return sorted(k for k, n in card.counters.items() if n > 0)


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)

    def base(native: str) -> dict[str, Any] | None:
        d = scripts.define(replace(ability, text=native), ch)
        ok = d and d.get("kind") == "static" and d.get("static") == "replace" and d.get("event") == "counters"
        return d if ok else None

    if (m := _GY.fullmatch(text)) is not None and (d := base(m[1][:1].upper() + m[1][1:])) is not None:
        return {**d, "gy110d": True}
    if text == _BIO + _MUTANT and (d := base(_BIO + ".")) is not None:
        return {**d, "op": {**d["op"], "add_subtype110d": "Mutant"}}
    if text == _BLUE and (d := base("Each other Dinosaur you control enters with an additional +1/+1 counter on it.")) is not None:
        return {**d, "match": {k: v for k, v in d["match"].items() if k != "counter"}, "op": {**d["op"], "kinds110d": True}}
    if text.replace("Jeska", "~") == _JESKA.replace("Jeska", "~") or text == _JESKA:
        d = scripts.define(replace(ability, text="0: Target creature gains flying until end of turn."), ch)
        return {**d, "effects": [{"do": "triple_damage110d"}]} if d and d.get("loyalty") else None
    return None


def triple(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects
    from app.rules import replace as repl

    chosen = effects._cards(plan, ctx, "target")
    if chosen:
        mine = ctx["controller"]
        repl.add_record(plan, event="damage", match={"combat": True, "source": {"oids": [plan.oid(chosen[0])]},
                                                     "to": {"pids": [p for p in plan.live() if p != mine]}},
                        op={"do": "mul", "n": 3}, controller=mine, source=ctx.get("source_object"), source_card=ctx.get("source_card"),
                        label=ctx.get("name") or "an effect", until="next_turn", until_player=mine)
    return True


PRIMITIVES = {"triple_damage110d": triple}


def entered(plan: Any, card: Any, controller: str, newcomers: Any) -> None:
    """The subtype an "enters … as a Mutant" static gives a permanent as it enters (614.12: judged as it would exist, not by newcomers)."""
    from app.rules import layers
    from app.rules import replace as repl

    for c in repl.candidates(plan, "counters"):
        sub = c.op.get("add_subtype110d")
        if not sub:
            continue
        ev = {"kind": "counters", "card": card.id, "oid": None, "counter": c.match["counter"], "n": 0, "by": controller, "effect": True,
              "applied": [], "controller": controller, "entering": True, **({"newcomers": sorted(newcomers)} if newcomers else {})}
        if repl._counters_applies(plan, c, ev, None):  # type: ignore[arg-type]
            layers.add_effect(plan, affected=[plan.oid(card)], layer="4", source=None, controller=controller, add_subtypes=(sub,),
                              duration="permanent", label=f"Enters as a {sub}")
