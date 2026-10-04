"""Alternative costs written on cards (wave 4I): "You may pay 1 life and exile a blue card from your hand rather than
pay this spell's mana cost." (Force of Will) and the table's "You may pay {W}{U}{B}{R}{G} rather than pay the mana
cost for spells you cast." (Jodah, Archmage Eternal).

Rules (stored Comprehensive Rules, 2026-09-25):

* 118.9 — an alternative cost is paid rather than the spell's mana cost; 118.9a: only one per spell (not with
  flashback, evoke, dash, a face-down cast or "without paying its mana cost"), announced as it's cast (601.2b);
  118.9b: optional; 118.9c: the spell's mana cost doesn't change (its mana value stays what's printed);
  118.9d: additional costs, increases and reductions apply to it (601.2f: the total cost).
* 107.3b — a spell with {X} in its mana cost cast for an alternative cost without X: X is 0.
* 601.2h — the total cost is paid all at once, with no partial payments (118.3): every part of the alternative cost
  is chosen and checked before anything moves (app/rules/cost_payment.py).
* A condition the line states ("If you control a Swamp, …", "If it's not your turn, …", "… if there are …") is
  checked as the spell is cast (601.2b, the announcement): it's a condition on using the cost.

Hidden information: the cards a "exile a blue card from your hand" part can take are offered only to the payer (a
private decision); the card exiled to pay is public from then on, as any card put into exile face up (406.3).

``action.alt_cost`` names the cost: "<card id>:<ability index>" — the spell's own line or a permanent's static.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.rules import conditions
from app.rules import costs as C
from app.rules import mana as M

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.plan import Plan

EXILE_FROM_HAND = "EXILE_FROM_HAND"  # a cost part: exile cards from your own hand (Force of Will)

# "You may pay 1 life and exile a blue card from your hand rather than pay this spell's mana cost." / "If you control a
# Swamp, you may pay 4 life rather than pay this spell's mana cost." / "You may pay {B} rather than pay this spell's mana
# cost if there are …"
SELF = re.compile(r"^(?:if (?P<c1>[^,]+), )?you may (?P<cost>.+?) rather than pay (?:this spell's|~'s) mana cost"
                  r"(?: if (?P<c2>.+))?$")
# "You may pay {W}{U}{B}{R}{G} rather than pay the mana cost for spells you cast." / "Once each turn, you may pay {0}
# rather than pay the mana cost for a colorless spell you cast from your hand." / "You may pay eight {E} rather than pay
# the mana cost for permanent spells you cast." / "Once each turn, you may pay {0} rather than pay the mana cost for a
# spell you cast with mana value X or less, where X is the number of time counters on this enchantment."
TABLE = re.compile(r"^(?P<once>once each turn, )?you may pay (?P<pay>(?:\{[^}]+\})+|\w+ \{E\}) rather than pay the mana cost "
                   r"for (?:(?:a|an) )?(?:(?P<sel>[A-Za-z][A-Za-z' -]*?) )?spells? you cast"
                   r"(?P<zone> from your hand| from exile)?(?: with mana value X or less, where X is (?P<mv>.+))?$")
_EXILE_HAND = re.compile(r"^Exile (?P<n>a|an|one|two|three) (?P<what>(?:[\w\-]+ )*cards?) from your hand$")
_PART_SPLIT = re.compile(r" and (?=(?:pay|exile|sacrifice|return|tap|discard) )")
_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3}


def _part(text: str) -> C.CostComponent | str | None:
    """One part of an alternative cost: a mana string ("{W}{U}{B}{R}{G}") or a cost component, or None."""
    part = text[:1].upper() + text[1:]
    m = re.fullmatch(r"Pay (?P<mana>(?:\{[^}]+\})+)", part)
    if m:
        mana = m["mana"]
        if not C._MANA_ONLY.match(mana) or "X" in mana:
            return None
        return mana
    m = _EXILE_HAND.fullmatch(part)
    if m:
        key = C._selector(m["what"], zone="hand")
        return C.CostComponent(EXILE_FROM_HAND, amount=_WORDS[m["n"]], selector=key, text=text) if key else None
    # "tap four untapped creatures you control with flying" (Sephara): the selector grammar reads "… with flying you control"
    part = re.sub(r"^(Tap \w+ untapped \w+) you control (with [a-z ]+)$", r"\1 \2 you control", part)
    found = C._component(part, "")
    if found is None or found.kind not in (C.PAY_LIFE, C.PAY_ENERGY, C.SACRIFICE, C.RETURN_PERMANENT, C.TAP_OTHER, C.DISCARD,
                                           C.EXILE_FROM_GRAVEYARD):
        return None
    if found.kind not in (C.PAY_LIFE, C.PAY_ENERGY) and (found.selector is None or found.random):
        return None  # (never the spell itself; a random discard isn't printed on an alternative cost)
    if found.kind == C.PAY_ENERGY and found.x:
        return None
    return found


@dataclass(frozen=True)
class AltCost:
    mana: str  # "" for none
    cost: C.AbilityCost  # the other parts (components)

    @property
    def mana_cost(self) -> M.ManaCost:
        return M.parse_cost(self.mana or "{0}")


def parse_cost(text: str) -> AltCost | None:
    """"pay 1 life and exile a blue card from your hand" → the parts, or None when one isn't read."""
    if re.search(r"\bx\b", text, re.IGNORECASE) or "," in text:
        return None
    mana = ""
    parts: list[C.CostComponent] = []
    for piece in _PART_SPLIT.split(text.strip()):
        found = _part(piece.strip())
        if found is None:
            return None
        if isinstance(found, str):
            if mana:
                return None
            mana = found
        else:
            parts.append(found)
    return AltCost(mana, C.AbilityCost(components=tuple(parts), life=sum(c.amount for c in parts if c.kind == C.PAY_LIFE)))


def _cond(text: str | None) -> Any:
    if text is None:
        return None
    cond = conditions.parse(text)
    if cond is None or "succeeded" in cond:
        raise ValueError(text)
    return cond


def define(t: str) -> dict[str, Any] | None:
    """The definition of an alternative-cost line (``t``: lowercased first letter, name as ~), or None."""
    # -- cost alt (wave 16F) -- 118.9: "If an opponent controls a Forest and you control a Swamp, you may cast this spell without paying
    # its mana cost." (the Legates) is an alternative cost of {0}, used under that condition
    t = re.sub(r"^(if [^,]+), you may cast (?:this spell|~) without paying its mana cost$", r"\1, you may pay {0} rather than pay "
               r"this spell's mana cost", t)
    m = SELF.fullmatch(t)
    if m:
        if m["c1"] and m["c2"]:
            return None
        found = parse_cost(m["cost"])
        if found is None:
            return None
        try:
            cond = _cond(m["c1"] or m["c2"])
        except ValueError:
            return None
        return {"kind": "static", "static": "alt_cost", "cost": m["cost"], "cond": cond, "effects": []}
    m = TABLE.fullmatch(t)
    if m:
        pay = m["pay"]
        energy = re.fullmatch(r"(\w+) \{E\}", pay)
        if energy:
            n = C._ENERGY_WORDS.get(energy[1].lower())
            if not n:
                return None
            cost_text = f"pay {energy[1]} {{E}}"
        else:
            if not C._MANA_ONLY.match(pay) or "X" in pay:
                return None
            cost_text = f"pay {pay}"
        if parse_cost(cost_text) is None:
            return None
        from app.rules.permissions import spell_filter

        key = spell_filter(m["sel"]) if m["sel"] else None
        if m["sel"] and key is None:
            return None
        mv = None
        if m["mv"]:
            from app.rules import values

            mv = values.parse_count(m["mv"], it="self")
            if mv is None:
                return None
        return {"kind": "static", "static": "alt_cost", "cost": cost_text, "table": True, "filter": key,
                "once": bool(m["once"]), "zone": (m["zone"] or "").replace(" from your ", "").replace(" from ", "") or None,
                "mv": mv, "effects": []}
    return None


# -- keywords (wave 15E) -- alternative-cost keywords that are only a cost with a condition on casting (118.9): spectacle
# (702.137a: "You may cast this spell by paying [cost] rather than its mana cost if an opponent lost life this turn."), surge
# (702.117a: "if you or a teammate has cast another spell this turn" — no teammates in Commander), freerunning
# (702.173a is not read). Read as the "You may pay … rather than pay this spell's mana cost if …" line they stand for.
PROWL_COND = "a player was dealt combat damage this turn by a source you controlled that shared a creature type with this spell"  # 702.76a
KEYWORD_CONDS = {"spectacle": "an opponent lost life this turn", "surge": "you've cast another spell this turn", "blitz": None, "warp": None, "bestow": None,
                 "prowl": PROWL_COND, "mutate": None}  # (wave 17C: prowl; wave 18D: mutate, 702.140a)
_KEYWORD_LINE = re.compile(r"^(?P<kw>spectacle|surge|blitz|warp|bestow|prowl|mutate) (?P<cost>(?:\{[^}X]+\})+)$", re.IGNORECASE)
# -- static_other sweep (wave 17C) -- "Dinosaur spells you cast have prowl {2}{R}." (Hunting Velociraptor): a table alternative cost, offered
# when the prowl condition holds for that spell
GRANT_PROWL = re.compile(r"^(?:(?P<sel>[A-Za-z][A-Za-z' -]*?) )?spells you cast have prowl (?P<cost>(?:\{[^}X]+\})+)$")


def grant_prowl(t: str) -> dict[str, Any] | None:
    m = GRANT_PROWL.fullmatch(t)
    if m is None or parse_cost(f"pay {m['cost']}") is None:
        return None
    from app.rules.permissions import spell_filter

    key = spell_filter(m["sel"]) if m["sel"] else None
    if m["sel"] and key is None:
        return None
    return {"kind": "static", "static": "alt_cost", "cost": f"pay {m['cost']}", "table": True, "filter": key, "once": False, "zone": None,
            "mv": None, "cond": _cond(PROWL_COND), "tag": "prowl", "effects": []}


def keyword_definition(line: str) -> dict[str, Any] | None:
    m = _KEYWORD_LINE.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip("."))
    if m is None:
        return None
    kw = m["kw"].lower()
    cond = KEYWORD_CONDS[kw]
    found = define(f"you may pay {m['cost']} rather than pay ~'s mana cost" + (f" if {cond}" if cond else ""))
    # ("tag": what the cast record says it was cast for; warp: only "from your hand", 702.185a)
    return {**found, "tag": kw, **({"hand_only": True} if kw == "warp" else {})} if found is not None else None


@dataclass(frozen=True)
class Offer:
    key: str  # "<card id>:<ability index>"
    label: str
    alt: AltCost
    once_key: str | None = None
    escape: bool = False  # -- escape (wave 5I) -- 702.138a: a cast from the graveyard (app/rules/escape.py)
    tag: str | None = None  # -- keywords (wave 15E) -- "blitz": cast for its blitz cost (702.152a)


def _ctx(state: GameState, player: str, source: CardInstance) -> dict[str, Any]:
    r = state.rules
    return {"controller": player, "source_card": source.id, "source_object": r.object_id(source.id) if r is not None else None}


def offers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[Offer]:
    """The alternative costs ``player`` could use to cast this card now (conditions and "once each turn" included;
    whether the cast is allowed at all and the cost can be paid are the caller's)."""
    from app.rules import permissions, scripts
    from app.rules.plan import Plan

    r = state.rules
    if r is None or r.card_mode(card.id) == "manual":
        return []
    view = Plan.view(state, player, info)
    out: list[Offer] = []
    for index, d in scripts.definitions(ch).items():
        if d.get("static") != "alt_cost" or d.get("table"):
            continue
        if d.get("hand_only") and card.zone != f"{player}:hand":
            continue
        if d.get("cond") is not None and not conditions.holds(view, _ctx(state, player, card), d["cond"]):
            continue
        if d.get("tag") == "mutate":  # -- merged permanents (wave 18D) -- 702.140a: only with a creature to merge with
            from app.rules import merged

            if not merged.can_mutate(view, player, card, ch):
                continue
        alt = parse_cost(d["cost"])
        if alt is not None:
            out.append(Offer(f"{card.id}:{index}", f"{ch.name}: {d['cost']}", alt, tag=d.get("tag")))
    where = card.zone.rsplit(":", 1)[-1]
    for src, index, d in permissions._table_statics(state, info, {"alt_cost"}):
        if not d.get("table") or src.controller != player:
            continue
        key = f"{src.id}:alt:{index}"
        if d["once"] and r.once_per_turn.get(key) == state.turn.number:
            continue
        if d.get("zone") and not (where == d["zone"] and (d["zone"] != "hand" or card.zone == f"{player}:hand")):
            continue
        if d.get("filter") and not permissions.spell_matches(state, player, card, ch, d["filter"], info):
            continue
        if d.get("mv") is not None:
            from app.rules import values

            if int(ch.mana_value) > values.evaluate(view, _ctx(state, player, src), d["mv"]):
                continue
        if d.get("cond") is not None and not conditions.holds(view, _ctx(state, player, card), d["cond"]):
            continue  # (wave 17C: prowl — read about the spell being cast)
        alt = parse_cost(d["cost"])
        if alt is not None:
            out.append(Offer(f"{src.id}:{index}", f"{src.name}: {d['cost']}", alt, once_key=key if d["once"] else None, tag=d.get("tag")))
    # -- escape (wave 5I) -- printed and granted escape costs (702.138a), for a card in its owner's graveyard
    from app.rules import escape

    out += escape.offers(state, player, card, ch, info)
    return out


def chosen(plan: Plan, key: str, card: CardInstance, ch: Characteristics) -> Offer:
    """The alternative cost the intent names, checked now (601.2b), or an ActionError."""
    for offer in offers(plan.state, plan.actor, card, ch, plan.info):
        if offer.key == key:
            return offer
    raise ActionError("That alternative cost can't be used to cast this spell now")


def merged(extra: C.AbilityCost | None, alt: C.AbilityCost) -> C.AbilityCost | None:
    """The spell's additional cost (118.8) and the alternative cost's non-mana parts, paid together (601.2h)."""
    parts = (extra.components if extra is not None else ()) + alt.components
    if not parts:
        return None
    return C.AbilityCost(components=parts, life=sum(c.amount for c in parts if c.kind == C.PAY_LIFE))
