"""-- choice grants and switches (wave 7E) -- researched against CR 2026-09-25.

* "This creature gains your choice of flying, deathtouch, or lifelink until end of turn." (Assassin Initiate, Shifting
  Ceratops), "… gets -1/-1 and gains your choice of flying, vigilance, deathtouch, or haste until end of turn." (Argivian
  Avenger, Jodah's Avenger), "This creature gets +1/-1 or -1/+1 until end of turn." (Brightling, Endling): the effect's
  controller chooses one of the listed options as it resolves (608.2d: "your choice"; nothing is chosen on activation,
  602.2b) and the choice is public. The chosen option is then the ordinary grant / pump (611.2a, 613.1f, 613.4c).
  Nothing is asked when the object is gone (611.2e: only a permanent on the battlefield gains an ability).
* "Switch this creature's power and toughness until end of turn." (Wandering Fumarole, 613.4d: layer 7d, applied after the
  other power and toughness effects, whatever their timestamps).
* "Regenerate target Insect, Rat, Spider, or Squirrel." / "Regenerate another target Elf." (701.19a): a regeneration
  shield for that permanent this turn; "another" is any object but the source.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]

_KW = r"(?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|reach|menace|indestructible|hexproof|shroud|shadow|fear|intimidate|skulk|wither|infect)"
_ITEM = rf"(?:{_KW}|protection from (?:white|blue|black|red|green))"
_LIST = rf"{_ITEM}(?:, {_ITEM})*,? or {_ITEM}"
_NUM = r"[+\-−]\d+"
_GAIN = re.compile(rf"^(?P<o>.+?)(?: gets (?P<p>{_NUM})/(?P<t>{_NUM}) and)? gains your choice of (?P<kws>{_LIST}) until end of turn$")
_PUMP = re.compile(rf"^(?P<o>.+?) gets (?P<p1>{_NUM})/(?P<t1>{_NUM}) or (?P<p2>{_NUM})/(?P<t2>{_NUM}) until end of turn$")
_SWITCH = re.compile(r"^switch (?P<o>target creature|this creature|~|each creature)'s power and toughness until end of turn$")  # (wave 34B: Mannichi, "each creature's")
# -- activated other (wave 34B) -- "Until end of turn, target creature has base power 1 or base toughness 1." (Vhati il-Dal): the controller chooses one of the two
# settings as it resolves (608.2d), each the layer 7b setting of "has base power 1" / "has base toughness 1" (613.4b)
_BASE_OR = re.compile(r"^(?:until end of turn, )?(?P<o>.+?) has base power (?P<p>\d+) or base toughness (?P<t>\d+)(?: until end of turn)?$")
_TRIGGERED = re.compile(r"^(?P<o>.+?) gains? (?P<kw>persist|undying|prowess|exalted|flanking|battle cry|dethrone|toxic \d+) until end of turn$")  # (wave 17B: flanking …)
_REGEN = re.compile(r"^regenerate (?!target creature(?: you control)?$)(?P<tgt>(?:another )?target .+)$")  # (not the older template's)


def _base_or(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language as L
    from app.rules.scripts import _NoMatch

    try:
        who, target = _subject(m["o"])
    except L._Fail:
        raise _NoMatch from None
    options = [{"label": f"Base {stat} {m[key]}", "effects": [{"do": "become", "who": who, "types": [], "duration": "end_of_turn", key: int(m[key])}]}
               for stat, key in (("power", "p"), ("toughness", "t"))]
    return [{"do": "choose_effect", "who": who, "options": options}], target


def _n(word: str) -> int:
    return int(word.replace("−", "-"))


def _subject(text: str, *, each: bool = False) -> tuple[str, Any]:
    from app.rules import language as L

    kind, key, group = L.ref(text)
    if kind not in ("target", "self") and not (each and kind == "each" and text == "each creature"):  # (wave 34B: a switch of every creature, Mannichi)
        raise L._Fail  # (a group or a pronoun: who chooses what isn't read here)
    return L._who(kind, key), L._one(group)


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language as L
    from app.rules.scripts import _NoMatch

    try:
        who, target = _subject(m["o"])
    except L._Fail:
        raise _NoMatch from None
    out: list[dict[str, Any]] = []
    if m.groupdict().get("kws"):
        if m["p"] is not None:
            out.append({"do": "pump", "who": who, "p": _n(m["p"]), "t": _n(m["t"])})
        options = []
        for k in re.split(r",? or |, ", m["kws"]):
            grant = {"keywords": [], "abilities": [k[0].upper() + k[1:]]} if k.startswith("protection") else {"keywords": [k]}
            options.append({"label": k[0].upper() + k[1:], "effects": [{"do": "grant", "who": who, **grant}]})
    else:
        options = [{"label": f"{_n(p):+d}/{_n(t):+d}", "effects": [{"do": "pump", "who": who, "p": _n(p), "t": _n(t)}]}
                   for p, t in ((m["p1"], m["t1"]), (m["p2"], m["t2"]))]
    out.append({"do": "choose_effect", "who": who, "options": options})
    return out, target


def _switch(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language as L
    from app.rules.scripts import _NoMatch

    try:
        who, target = _subject(m["o"], each=True)
    except L._Fail:
        raise _NoMatch from None
    return [{"do": "switch_pt", "who": who}], target


def _regen(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import selectors
    from app.rules.copying import _target_group
    from app.rules.scripts import _NoMatch

    g = _target_group(m["tgt"])
    if g is None or (g["min"], g["max"]) != (1, 1) or not g["what"].startswith(selectors.PREFIX):
        raise _NoMatch
    sel = selectors.from_key(g["what"])
    if sel.player is not None or sel.zones != ("battlefield",) or sel.card or sel.ability is not None:
        raise _NoMatch
    return [{"do": "regenerate", "who": "target"}], g


def _triggered(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    """"gains persist until end of turn": the keyword line itself is granted (613.1f), so its triggered ability (702.79a,
    702.93a, 702.108a, 702.83a) exists for as long as the grant does, like a printed one."""
    from app.rules import language as L
    from app.rules.scripts import _NoMatch

    try:
        kind, key, group = L.ref(m["o"])
        if kind not in ("target", "self", "each"):
            raise L._Fail
        who = L._who(kind, key)
    except L._Fail:
        raise _NoMatch from None
    return [{"do": "grant", "who": who, "keywords": [], "abilities": [m["kw"].capitalize() + "."]}], L._one(group)


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_GAIN, _build), (_PUMP, _build), (_SWITCH, _switch), (_REGEN, _regen),
                                                (_TRIGGERED, _triggered), (_BASE_OR, _base_or)]


def choose_effect(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.effects import _cards
    from app.rules.plan import decide

    if not [c for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]:
        return True  # (nothing left: 611.2e)
    src = plan.state.cards.get(ctx.get("source_card") or "")
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Effect'}: choose one",
           options=[DecisionOption(id=str(i), label=o["label"]) for i, o in enumerate(e["options"])],
           resume={"step": "choose_effect", "ctx": ctx, "e": e}, source=src)
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules.effects import PRIMITIVES, continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    if not chosen or chosen[0] not in {str(i) for i in range(len(e["options"]))}:
        raise ActionError("Choose one of the offered options")
    option = e["options"][int(chosen[0])]
    plan.note(f"{plan.name(d.player)} chooses {option['label'].lower()}", actor=d.player)
    for sub in option["effects"]:
        PRIMITIVES[sub["do"]](plan, ctx, sub)
    continue_effects(plan, ctx)


def switch_pt(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """613.4d: a layer 7d effect on the objects named now (611.2c), until end of turn."""
    from app.rules import layers
    from app.rules.effects import _cards, _mark, _remember

    cards = [c for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    _remember(plan, ctx, e, cards)
    if cards:
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer="7d", source=ctx.get("source_object"),
                          controller=ctx["controller"], label=f"power and toughness switched ({ctx.get('name', '')})")
        _mark(plan, cards, "P/T switched", text="until end of turn")
    return True


PRIMITIVES = {"choose_effect": choose_effect, "switch_pt": switch_pt}
RESUME = {"choose_effect": resume}
