"""-- villainous choice (wave 23A) -- "Each opponent faces a villainous choice — That player sacrifices a creature of their choice, or you
create a 3/3 black Dalek artifact creature token with menace." (The Dalek Emperor), "… that player faces a villainous choice — They
sacrifice a nontoken creature of their choice, or they lose 2 life and you draw two cards." (Damocles Base), "Then each opponent who lost
3 or more life this turn faces a villainous choice — You draw a card, or that player discards a card." (Davros).

CR 2026-09-25: 701.55a "[A player] faces a villainous choice — [option A], or [option B]" means that player chooses option A or option B,
then all actions in the chosen option are performed; 701.55b a player may choose an option that is illegal or impossible and performs as
much of it as is possible (an exception to 608.2d: the effects here already do what they can); 701.55d several players: the whole
process, one player at a time, in APNAP order (an exception to 608.2e), so the second player chooses after the first one's option was
carried out; 101.4b: the choice is that player's own and public (the options are written on the card, the choice is announced).

Each option is read as the clause "That player …" / "You …" with "that player" the one who faces the choice; an option that names
a target, a "may", a later "then", a "this way" or a "that" object is not read (the card stays manual). 701.55c ("an additional
time", The Valeyard) isn't modelled: that card stays manual."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.rules.plan import Plan

Context = dict[str, Any]
_HEAD = re.compile(r"^(?:then )?(?P<who>each opponent|that player|defending player)(?: who (?P<pred>[^—]+?))? faces a villainous choice — (?P<opts>.+)$")
_WHO = {"each opponent": "each_opponent", "that player": "event_player", "defending player": "defending_player"}
_BAD = re.compile(r'"target|\bthen\b|\bmay\b|\bthis way\b|\bthat (?:card|creature|permanent|spell)\b|\bchaos\b', re.I)


def _third(option: str) -> str:
    """"They lose 2 life and you draw two cards" → "That player loses 2 life and you draw two cards" (the one who faces the choice)."""
    out = re.sub(r"(?i)\bthat opponent\b", "that player", option)
    out = re.sub(r"(?i)\bthey (\w+)\b", lambda m: f"that player {m[1]}s", out)
    return out[:1].upper() + out[1:]


def sentence(text: str, effects: list[dict[str, Any]], read: Callable[[str], list[dict[str, Any]] | None]) -> list[dict[str, Any]] | None:
    """The instruction (and the players it names, for "each opponent who …") of a villainous-choice sentence, or None."""
    from app.rules import player_filter

    m = _HEAD.match(text.rstrip("."))
    if m is None or _BAD.search(m["opts"]):
        return None
    words = m["opts"].split(" ")
    out: list[dict[str, Any]] = []
    who = _WHO[m["who"]]
    if m["pred"]:
        pred = player_filter.parse_pred(m["pred"])
        if pred is None or m["who"] != "each opponent":
            return None
        name = f"pw{sum(1 for x in effects if x.get('do') == 'players_where')}"
        out.append({"do": "players_where", "as": name, "base": "opponent", "pred": pred})
        who = f"ref:{name}"
    for i in range(1, len(words)):  # "<option A>, or <option B>": the split both halves read
        if not words[i - 1].endswith(","):
            continue
        a, b = " ".join(words[:i]).rstrip(",").strip(), " ".join(words[i:])
        if not b.startswith("or "):
            continue
        a, b = _third(a), _third(b[3:])
        ea, eb = read(a + "."), read(b + ".")
        if not ea or not eb or '"target' in json.dumps([ea, eb]) or '"ref:' in json.dumps([ea, eb]):
            continue
        return [*out, {"do": "villain", "who": who, "a": ea, "b": eb, "labels": [a, b]}]
    return None


def _for(value: Any, pid: str) -> Any:
    from app.rules import each_may

    return each_may._for(value, pid)


def villain(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.55d: one player at a time, in APNAP order: that player chooses, the option is carried out, the next one chooses."""
    from app.rules import effects, wave110l_cards  # (wave 110L: 701.55c, an additional time, The Valeyard)
    from app.rules.plan import decide

    left = e.get("left")
    if left is None:
        who = effects._players(plan, ctx, e["who"])
        left = [p for p in plan.apnap() if p in who]
        left = [q for p in left for q in [p] * (1 + wave110l_cards.extra_faces(plan, p))]
    left = [p for p in left if p in plan.live()]
    if not left:
        return True
    pid = left[0]
    decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: you face a villainous choice",
           options=[DecisionOption(id="a", label=e["labels"][0]), DecisionOption(id="b", label=e["labels"][1])],
           resume={"step": "villain", "ctx": ctx, "e": e, "left": left})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e, left = d.resume["ctx"], d.resume["e"], d.resume["left"]
    pid, rest = left[0], left[1:]
    option = e["a"] if chosen == ["a"] else e["b"]
    plan.note(f"{plan.name(pid)} chooses: {e['labels'][0 if chosen == ['a'] else 1]}", actor=pid)  # 101.4b
    added = _for(option, pid)
    if rest:
        added = [*added, {**{k: v for k, v in e.items() if k != "left"}, "left": rest}]
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]
    continue_effects(plan, ctx)


PRIMITIVES = {"villain": villain}
RESUME = {"villain": resume}
