# -- tempting offers (wave 18C) --
"""Tempting offers: "Draw a card and create a 1/1 white Rabbit creature token. Then each opponent may draw a card and create a 1/1
white Rabbit creature token. For each opponent who does, you draw a card and you create a 1/1 white Rabbit creature token." (Tempt
with Bunnies, Glory, Immortality, Vengeance, Reflections, Discovery). Researched against CR 2026-09-25.

* 207.2c: "Tempting offer" is an ability word. The spell's controller does the action first.
* 101.4 / 608.2d: "each opponent may [do it]": the opponents choose in turn order (APNAP), each privately and each carrying the action
  out as they choose, before the next is asked. The action is the opponent's own: they are "you" for it (their library, their
  creatures, their graveyard, their tokens; a chosen target of the spell stays the spell's, 608.2b).
* "For each opponent who does, you [do it]": once more for each opponent who did, after all of them have chosen.
* Tempt with Discovery: "who searches a library this way" is the opponent who chose to search; "Then each player who searched a
  library this way shuffles" (701.19): you, and each opponent who searched, once.

The three sentences must be the same action (the opponents' and the offer's are compared word for word, third person made second),
so nothing is read into them; Tempt with Mayhem (copying the spell) stays manual.
"""

from __future__ import annotations

import copy
import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_MAY = re.compile(r"^(?:Then )?each opponent may (?P<x>.+)\.$", re.IGNORECASE)
_FOR = re.compile(r"^For each opponent who (?:does|searches a library this way), (?P<y>.+)\.$")
_SHUFFLE = "Then each player who searched a library this way shuffles."


def _norm(text: str) -> str:
    t = text.rstrip(".").lower()
    t = re.sub(r"\bthey control\b", "you control", t)
    t = re.sub(r"\btheir\b", "your", t)
    return re.sub(r"\s+", " ", re.sub(r"\byou\b\s*", "", t)).strip()


def bind(body: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """The effects of a tempting offer, or None if the body isn't one (or isn't read)."""
    if "each opponent may " not in body.lower():
        return None
    sentences = split_sentences(body.strip())
    at = next((i for i, s in enumerate(sentences) if i and _MAY.match(s)), None)
    if at is None or at + 1 >= len(sentences) or (m := _MAY.match(sentences[at])) is None or (f := _FOR.match(sentences[at + 1])) is None:
        return None
    tail = sentences[at + 2:]
    offer = sentences[:at]
    if tail not in ([], [_SHUFFLE]) or len(offer) not in (1, 2) or (len(offer) == 2 and not offer[0].startswith("Choose target ")):
        return None
    if not (_norm(m["x"]) == _norm(offer[-1]) == _norm(f["y"])) or (tail and "search" not in offer[-1].lower()):
        return None
    full = parse(" ".join(offer))
    if full is None or full[2] or not full[0]:
        return None
    effects, block = full[0], full[0]
    if len(offer) == 2:
        head = parse(offer[0])
        if head is None or head[2] or effects[:len(head[0])] != head[0]:
            return None
        block = effects[len(head[0]):]
    elif full[1]:
        return None  # (a target belongs to a "Choose target …" sentence of its own)
    if not block or any(e.get("bind") or e.get("as") or e.get("did") for e in block) or any(e["do"] == "choose_targets" for e in block):
        return None
    return [*effects, {"do": "tempt", "n": len(block), "shuffle": bool(tail), "text": m["x"][:120]}], full[1], False


def tempt(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Each opponent in turn order chooses and, if they do, does it; then you do it again for each who did."""
    me, n = ctx["controller"], int(e["n"])
    at = ctx["next"]
    template = ctx["effects"][at - 1 - n:at - 1]
    tag = f"t{at}_"
    opponents = [p for p in plan.apnap() if p != me]
    added: list[dict[str, Any]] = []
    for i, p in enumerate(opponents):
        added += [{"do": "tempt_ask", "player": p, "bind": f"{tag}{i}", "text": e["text"]},
                  {"do": "only_if", "cond": {"flag": f"{tag}{i}"}, "skip": n + 2}, {"do": "as_player", "player": p},
                  *copy.deepcopy(template), {"do": "as_player_end"}]
    for i, _ in enumerate(opponents):
        added += [{"do": "only_if", "cond": {"flag": f"{tag}{i}"}, "skip": n}, *copy.deepcopy(template)]
    if e.get("shuffle"):  # 701.19: you, and each opponent who searched
        added.append({"do": "shuffle_library", "who": "you", "zones": []})
        for i, p in enumerate(opponents):
            added += [{"do": "only_if", "cond": {"flag": f"{tag}{i}"}, "skip": 3}, {"do": "as_player", "player": p},
                      {"do": "shuffle_library", "who": "you", "zones": []}, {"do": "as_player_end"}]
    ctx["effects"][at:at] = added  # (in place: the loop in continue_effects reads this list)
    return True


def ask(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    p = e["player"]
    if p not in plan.live():
        from app.rules import context

        context.bind_flag(ctx, e["bind"], False)
        return True
    decide(plan, player=p, kind="confirm", prompt=f"{ctx.get('name') or 'Tempting offer'}: you may {e['text']}",
           options=[DecisionOption(id="yes", label="Yes"), DecisionOption(id="no", label="No")],
           resume={"step": "tempt_ask", "ctx": ctx, "bind": e["bind"]})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context
    from app.rules.effects import continue_effects

    ctx = d.resume["ctx"]
    context.bind_flag(ctx, d.resume["bind"], chosen[0] == "yes")
    plan.note(f"{plan.name(d.player)} {'accepted' if chosen[0] == 'yes' else 'declined'} the offer")
    continue_effects(plan, ctx)


def as_player(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The next instructions are done by this player (they are "you"), until ``as_player_end``."""
    ctx.setdefault("controllers", []).append(ctx["controller"])
    ctx["controller"] = e["player"]
    return True


def as_player_end(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    ctx["controller"] = ctx["controllers"].pop()
    return True


PRIMITIVES = {"tempt": tempt, "tempt_ask": ask, "as_player": as_player, "as_player_end": as_player_end}
RESUME = {"tempt_ask": resume}
