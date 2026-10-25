# -- friend or foe (wave 18C) --
"""Friend or foe (Battlebond): "For each player, choose friend or foe. Each friend returns a creature card from their graveyard to their
hand. Each foe sacrifices a creature of their choice." (Virtus's Maneuver, Pir's Whim, Regna's Sanction, Zndrsplt's Judgment, Khorvath's
Fury). Researched against CR 2026-09-25.

* The spell's controller chooses, for each player (themself included), whether that player is a friend or a foe (the choice is public:
  everyone at the table sees how the players were sorted). The choices are made in turn order (APNAP, 101.4) before anything else.
* "Each friend [does X]": each player who was chosen as a friend does X as the instruction is followed; "each foe [does Y]" likewise. A
  player does it themselves, in turn order, so their own cards, choices and "they control" are theirs (the same machinery as an
  opponent's tempting offer: ``as_player``). If nobody is in a group, nothing happens for it.

Read only when each sentence after the choice is "Each friend/foe [verb phrase]." whose third person becomes a plain second-person
instruction the effect grammar reads ("returns … their graveyard" → "Return … your graveyard"); anything else (Khorvath's Fury's
damage "to each foe equal to …", a sentence with its own subject) stays manual.
"""

from __future__ import annotations

import copy
import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_HEAD = "For each player, choose friend or foe."
_SIDE = re.compile(r"^Each (?P<side>friend|foe) (?P<rest>.+)\.$")
_VERBS = ("searches", "puts", "shuffles", "discards", "draws", "returns", "sacrifices", "creates", "chooses", "taps", "untaps", "gains",
          "loses", "exiles", "destroys", "reveals", "mills")


def _you(rest: str) -> str:
    """The third-person verb phrase as an imperative: "returns a creature card from their graveyard" → "Return … your …"."""
    t = re.sub(r"\b(" + "|".join(_VERBS) + r")\b", lambda m: m[1][:-2] if m[1].endswith("hes") else m[1][:-1], rest)
    t = t.replace(" of their choice", "")
    t = re.sub(r"\btheir\b", "your", t)
    t = re.sub(r"\bthey control\b", "you control", t)
    t = re.sub(r"\bthey\b|\bthemselves\b", "you", t)
    return t[:1].upper() + t[1:] + "."


def bind(body: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if not body.strip().startswith(_HEAD):
        return None
    sentences = split_sentences(body.strip())
    if sentences[0] != _HEAD or len(sentences) < 2:
        return None
    effects: list[dict[str, Any]] = [{"do": "friend_foe"}]
    seen = set()
    for sentence in sentences[1:]:
        m = _SIDE.match(sentence)
        if m is None or m["side"] in seen:
            return None
        seen.add(m["side"])
        # -- cards (wave 110I) -- a side whose instruction binds a choice of its own (Regna's Sanction, Zndrsplt's Judgment)
        from app.rules import wave110i_cards

        if (own := wave110i_cards.SIDES.get(m["rest"])) is not None:
            effects += [{"do": "side_does", "side": m["side"], "n": len(own)}, *copy.deepcopy(own)]
            continue
        found = parse(_you(m["rest"]))
        if found is None or found[1] or found[2] or not found[0]:
            return None
        block = found[0]
        if any(e.get("bind") or e.get("as") or e.get("did") for e in block):
            return None
        effects += [{"do": "side_does", "side": m["side"], "n": len(block)}, *block]
    return effects, None, False


def choose(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    ctx["sides"] = {"order": list(plan.apnap()), "chosen": {}}
    return _ask(plan, ctx)


def _ask(plan: Plan, ctx: Context) -> bool:
    from app.rules.plan import decide

    sides = ctx["sides"]
    for p in sides["order"]:
        if p in sides["chosen"]:
            continue
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"Is {plan.name(p)} a friend or a foe?",
               options=[DecisionOption(id="friend", label="Friend"), DecisionOption(id="foe", label="Foe")],
               resume={"step": "friend_foe", "ctx": ctx, "player": p})
        return False
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx = d.resume["ctx"]
    ctx["sides"]["chosen"][d.resume["player"]] = chosen[0]
    plan.note(f"{plan.name(d.resume['player'])} is a {chosen[0]}")
    if _ask(plan, ctx):
        continue_effects(plan, ctx)


def side_does(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The next ``n`` instructions once for each player of the side, each done by that player in turn order (none: skipped)."""
    at, n = ctx["next"], int(e["n"])
    block = ctx["effects"][at:at + n]
    members = [p for p in ctx["sides"]["order"] if ctx["sides"]["chosen"].get(p) == e["side"] and p in plan.live()]
    added: list[dict[str, Any]] = []
    for p in members:
        added += [{"do": "as_player", "player": p}, *copy.deepcopy(block), {"do": "as_player_end"}]
    ctx["effects"][at:at + n] = added
    return True


PRIMITIVES = {"friend_foe": choose, "side_does": side_does}
RESUME = {"friend_foe": resume}
