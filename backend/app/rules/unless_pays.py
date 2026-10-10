""""[Effect] unless [a player] pays [cost]" with a cost worked out as the ability resolves (wave 4C).

CR 118.12a: "[Do something] unless [a player does something else]" means "[A player may do something
else]. If [that player doesn't], [do something]." The payment itself is the optional payment of
app/rules/optional_payment.py (the payer alone decides, privately; PAY is offered only while the
whole cost is payable, 118.3; it's paid from that player's own resources, 601.2h). This module adds:

* sized costs (the amount is determined as the payment is made, 608.2h / 107.3): "{X}" (the X the
  spell was cast with, 107.3a), "{X}, where X is this creature's power", "{1} for each card in your
  graveyard", "{2} plus an additional {1} for each Faerie you control" — ``{"cost": base, "per":
  "{1}", "n": <value>}`` on the optional_payment effect, turned into a plain mana cost by
  :func:`concrete_cost`; values are app/rules/values.py expressions;
* "you may [effect] unless that player pays [cost]" (Rhystic Study, Mystic Remora): the payer
  decides first, then — if they didn't pay — the controller decides whether to do it (118.12a: "That
  player may pay {1}. If that player doesn't, you may draw a card."; 608.2c: in the order written).
  :func:`may_rest` is that "you may", asked as the resolution reaches it (not before it, 603.5);
* the counterspell riders: "If that spell is countered this way, exile it instead of putting it into
  its owner's graveyard." (608.2c: later text modifies the counter; the ``exile`` flag on the counter
  instruction) and "If they do, …" (118.12: whether the payer chose to pay — the payment's binding).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules import mana as M
from app.rules import values
from app.rules.plan import Plan, decide

Context = dict[str, Any]
_MANA = r"(?:\{[^}]+\})+"
_SIZED = re.compile(rf"^(?:(?P<base>{_MANA}) plus an additional )?(?P<per>{_MANA}) for each (?P<what>.+)$")
_X = re.compile(r"^\{X\}(?:,? where X is (?P<v>.+))?$")
_SELF_STAT = re.compile(r"^(?:this creature|this permanent|this artifact|this enchantment|~)'s (?P<stat>power|toughness|mana value)$")
_ITS_STAT = re.compile(r"^(?:its|that spell's) (?P<stat>power|toughness|mana value)$")
_STATS = {"power": "power", "toughness": "toughness", "mana value": "mana_value"}


# -- grammar (app/rules/scripts._unless_sentence) ----------------------------------------------------
def _value(phrase: str, its: str | None) -> Any:
    """A quantity phrase as a value, or None. ``its``: what "its" names (the target spell for a
    "counter target spell unless its controller pays …"), None when it can't be bound."""
    p = phrase.strip()
    m = _SELF_STAT.match(p)
    if m:
        return {_STATS[m["stat"]]: "self"}
    m = _ITS_STAT.match(p)
    if m:
        return {_STATS[m["stat"]]: its} if its is not None else None
    if re.search(r"\b(?:it|its|this way|they|them|that player)\b", p):
        return None  # ("card discarded this way", "cards revealed this way": what an earlier choice did — not read)
    return values.parse_count(p)


def sized_cost(phrase: str, its: str | None = None) -> dict[str, Any] | None:
    """"{X}" / "{X}, where X is …" / "{N} for each …" / "{A} plus an additional {B} for each …" →
    ``{"cost": base mana text ("" if none), "per": mana text, "n": value}``, or None."""
    m = _X.match(phrase.strip())
    if m:
        n = {"x": 1} if m["v"] is None else _value(m["v"], its)
        return {"cost": "", "per": "{1}", "n": n} if n is not None else None
    m = re.fullmatch(r"mana equal to (?P<v>.+)", phrase.strip())  # -- unless pays (wave 20E) -- "pays mana equal to the greatest power among creatures you control"
    if m:
        n = _value(m["v"], its)
        return {"cost": "", "per": "{1}", "n": n} if n is not None else None
    m = _SIZED.match(phrase.strip())
    if m is None:
        return None
    base, per = m["base"] or "", m["per"]
    for part in (base, per):
        if part and (M.parse_cost(part).unsupported or M.parse_cost(part).x or "{E}" in part.upper()):
            return None  # (mana only: an energy or X part isn't sized here)
    n = _value(m["what"], its)
    return {"cost": base, "per": per, "n": n} if n is not None else None


def countered_this_way(text: str) -> bool:
    """"If that spell is countered this way, exile it instead of putting it into its owner's
    graveyard." (608.2c: a later sentence modifying the counter before it)."""
    return re.fullmatch(r"if (?:that spell|it) is countered this way, exile it instead of putting it into its owner's graveyard",
                        text) is not None


# -- resolution ---------------------------------------------------------------------------------------
def concrete_cost(plan: Plan, ctx: Context, e: dict[str, Any]) -> str:
    """The cost text an optional payment asks for: its fixed ``cost``, plus ``per`` once for each of
    ``n`` (evaluated now, 608.2h) — a plain mana cost ("{3}", "{G}{G}"), "{0}" when nothing is owed."""
    if e.get("alt"):  # "If you control a Bird, … pays {4} instead" (checked now: 608.2c)
        from app.rules import conditions  # (conditions → effects → this module)

        return str(e["alt"]["cost"] if conditions.holds(plan, ctx, e["alt"]["cond"]) else e["cost"])
    if "per" not in e:
        return str(e["cost"])
    n = values.evaluate(plan, ctx, e["n"])
    base = M.parse_cost(e.get("cost") or "{0}")
    per = M.parse_cost(e["per"])
    total = M.ManaCost(generic=base.generic + per.generic * n, colored=base.colored + per.colored * n,
                       hybrid=base.hybrid + per.hybrid * n, phyrexian=base.phyrexian + per.phyrexian * n)
    return total.text() if not total.is_free else "{0}"


def may_key(ctx: Context) -> str:
    """The remembered-answer key of this "you may" (the same shape as effects.may_key: this source's
    own ability, never another card's)."""
    what = hashlib.sha1(json.dumps(ctx.get("effects"), sort_keys=True, default=str).encode()).hexdigest()[:12]
    return f"may:{(ctx.get('source_card') or ctx.get('name') or '')[:90]}:{what}"


def may_rest(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """``{"do": "may_rest"}``: "you may [the rest of the ability]", asked of the controller when the
    resolution reaches it (after the payment before it, 118.12a / 608.2c). "No" ends the resolution
    (the effects after this are the optional ones: scripts only builds it at the end of an ability)."""
    from app.rules import effects
    from app.rules.engine import remembered  # engine imports effects → this module

    pid = ctx["controller"]
    if ctx["next"] < len(ctx["effects"]) and effects.barred_search(plan, ctx, ctx["effects"][ctx["next"]]):  # -- prohibitions (wave 24D) -- can't choose to search: skip it
        ctx["next"] += e.get("skip") or len(ctx["effects"])
        return True
    skip = e.get("skip")  # -- optional first sentence (wave 24D) -- "You may X. Then Y.": only X's ``skip`` instructions are the "may"
    rest = ctx["effects"][ctx["next"]:ctx["next"] + skip if skip else None]
    key = may_key(ctx)
    answer = remembered(plan, pid, key, "")
    if answer == "no":
        plan.note(f"{plan.name(pid)} chose not to")
        ctx["next"] += skip or len(ctx["effects"])
        return True
    if answer == "yes":
        return True
    decide(plan, player=pid, kind="confirm", prompt=f"{ctx.get('name') or 'It'}: {effects.describe(rest)}?",
           options=[DecisionOption(id="yes", label="Yes"), DecisionOption(id="no", label="No")],
           resume={"step": "may", "ctx": ctx}, memory_key=key)
    return False


PRIMITIVES: dict[str, Any] = {"may_rest": may_rest}


# -- "Whenever an opponent casts their first noncreature spell each turn" (Esper Sentinel) ------------------
# 601.2i: the spell becomes cast; whether it is the player's first spell *of that kind* this turn counts every
# spell they cast this turn, also those cast before the watcher was on the battlefield. Each cast records, for
# its caster and this turn, which card types the spell had ("T:<type>") and lacked ("N:<type>") — in the per-turn
# marks (rules.once_per_turn: key → turn), so it survives saves and replays. A kind is read only when those marks
# answer it exactly: any of some card types ("instant or sorcery"), or the lack of one ("noncreature").
_CARD_TYPES = ("Artifact", "Battle", "Creature", "Enchantment", "Instant", "Kindred", "Land", "Planeswalker", "Sorcery")


def first_kind_ok(sel_key: str) -> bool:
    from app.rules import selectors

    sel = selectors.from_key(sel_key)
    plain = selectors.replace(sel, types=(), not_types=(), zones=sel.zones) == selectors.Selector(zones=sel.zones)
    one_kind = bool(sel.types) != bool(sel.not_types) and len(sel.not_types) <= 1
    return plain and one_kind and all(t in _CARD_TYPES for t in (*sel.types, *sel.not_types))


def mark_cast(plan: Plan, player: str, types: Any) -> list[str]:
    """Record a spell ``player`` just cast (its card types); returns the marks this turn had before it."""
    turn = plan.state.turn.number
    marks = plan.rules.once_per_turn
    prefix = f"cast_kind:{player}:"
    before = sorted(k[len(prefix):] for k, v in marks.items() if k.startswith(prefix) and v == turn)
    for t in _CARD_TYPES:
        marks[f"{prefix}{'T' if t in types else 'N'}:{t}"] = turn
    return before


def first_of_kind(sel_key: str, before: list[str]) -> bool:
    """Was no spell of this kind cast by that player earlier this turn (``before``: :func:`mark_cast`)?"""
    from app.rules import selectors

    sel = selectors.from_key(sel_key)
    if sel.not_types:
        return f"N:{sel.not_types[0]}" not in before
    return not any(f"T:{t}" in before for t in sel.types)
