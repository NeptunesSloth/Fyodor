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
from app.game.mana_cost_templates import GrantedManaCost
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
_EXILE_HAND = re.compile(r"^Exile (?P<n>a|an|one|two|three) (?P<what>(?:[\w\-]+ )*cards?(?: with mana value \d+ or (?:less|greater))?) from your hand$")
_PART_SPLIT = re.compile(r" and (?=(?:pay|exile|sacrifice|return|tap|discard) )")
_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3}


def _part(text: str, x_ok: bool = False) -> C.CostComponent | str | None:
    """One part of an alternative cost: a mana string ("{W}{U}{B}{R}{G}") or a cost component, or None. ``x_ok`` (-- cast keywords (wave 43D) --
    107.3a): the mana may have {X} (harmonize, overload, surge, warp, bestow, miracle: the X announced for the spell is the cost's too)."""
    from app.rules import opponent_gain_costs44

    if (gain_cost := opponent_gain_costs44.component(text)) is not None:
        return gain_cost
    part = text[:1].upper() + text[1:]
    m = re.fullmatch(r"Pay (?P<mana>(?:\{[^}]+\})+)", part)
    if m:
        mana = m["mana"]
        if not C._MANA_ONLY.match(mana) or ("X" in mana and not x_ok):
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


def parse_cost(text: str, x_ok: bool = False) -> AltCost | None:
    """"pay 1 life and exile a blue card from your hand" → the parts, or None when one isn't read."""
    from app.rules import shoal_nonmana_x

    if (nonmana_x := shoal_nonmana_x.parse(text)) is not None:
        return nonmana_x
    if text == "discard an Island card and another card":
        island, other = C._selector("Island card", zone="hand"), C._selector("card", zone="hand")
        if island is None or other is None:
            return None
        return AltCost("", C.AbilityCost(components=(
            C.CostComponent(C.DISCARD, selector=island, text="Discard an Island card"),
            C.CostComponent(C.DISCARD, selector=other, text="Discard another card"),
        )))
    if text == "discard a card that shares a color with that spell":
        from dataclasses import replace

        from app.rules import selectors
        selector = replace(selectors.Selector(card=True, zones=("hand",)), extras=("shares_color_source",))
        return AltCost("", C.AbilityCost(components=(C.CostComponent(C.DISCARD, selector=selector.key(), text=text),)))
    if re.search(r"\bx\b", text.replace("{X}", "") if x_ok else text, re.IGNORECASE) or "," in text:
        return None
    mana = ""
    parts: list[C.CostComponent] = []
    for piece in _PART_SPLIT.split(text.strip()):
        found = _part(piece.strip(), x_ok)
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


def define(t: str, x_ok: bool = False) -> dict[str, Any] | None:
    """The definition of an alternative-cost line (``t``: lowercased first letter, name as ~), or None."""
    from app.rules import opponent_gain_costs44

    if (gain_cost := opponent_gain_costs44.definition(t)) is not None:
        return gain_cost
    if t == "rather than pay the mana cost for a spell, its controller may discard a card that shares a color with that spell":
        return {"kind": "static", "static": "alt_cost", "cost": "discard a card that shares a color with that spell",
                "table": True, "any_controller": True, "once": False, "effects": []}
    # -- cost alt (wave 16F) -- 118.9: "If an opponent controls a Forest and you control a Swamp, you may cast this spell without paying
    # its mana cost." (the Legates) is an alternative cost of {0}, used under that condition
    t = re.sub(r"^(if [^,]+), you may cast (?:this spell|~) without paying its mana cost$", r"\1, you may pay {0} rather than pay "
               r"this spell's mana cost", t)
    # -- commander sweep (wave 49B) -- "As long as you've discarded a card this turn, you may pay {B/R} to cast this spell." (Asmoranomardicadaistinaculdacar): an alternative cost, used while the
    # condition holds (its ruling 2021-06-18: with no mana cost it can't be cast any other way)
    t = re.sub(r"^as long as ([^,]+), (you may pay [^,]+?) to cast (?:this spell|~)$", r"if \1, \2 rather than pay this spell's mana cost", t)
    m = SELF.fullmatch(t)
    if m:
        if m["c1"] and m["c2"]:
            return None
        found = parse_cost(m["cost"], x_ok)
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
FREERUN_COND = ("a player was dealt combat damage this turn by a creature that, at the time it dealt that damage, was an assassin creature or a commander "
                "under your control")  # -- cast keywords (wave 43D) -- 702.173a
KEYWORD_CONDS = {"spectacle": "an opponent lost life this turn", "surge": "you've cast another spell this turn", "blitz": None, "warp": None, "bestow": None,
                 "prowl": PROWL_COND, "overload": None, "cleave": None, "emerge": None, "foretell": None, "mutate": None, "freerunning": FREERUN_COND,
                 "web-slinging": None, "sneak": None, "more than meets the eye": None}  # (wave 17C: prowl; wave 18D: mutate, 702.140a; wave 50C: 702.162a, converted)
# (-- casting extras (wave 18E) -- "Emerge {cost}" / "Emerge from artifact {cost}": 702.119a-b, the cost and a sacrifice)
_KEYWORD_LINE = re.compile(r"^(?P<kw>spectacle|surge|blitz|warp|bestow|prowl|overload|cleave|emerge|foretell|mutate|web-slinging|sneak|freerunning|more than meets the eye)(?: from (?P<q>[A-Za-z]+))? "
                           r"(?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
X_KEYWORDS = frozenset({"surge", "warp", "bestow", "overload", "cleave"})  # -- cast keywords (wave 43D) -- 107.3a: the cost may have {X} (the X announced for the spell is its too)
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


# -- Marvel keywords (wave 25A) -- "Each legendary spell you cast that's one or more colors has web-slinging {G}{W}{U}." (Peter Parker's back face)
GRANT_WEB = re.compile(r"^each (?P<sel>[A-Za-z][A-Za-z' -]*?) spell you cast(?: (?P<tail>that['’]s one or more colors))? has web-slinging "
                       r"(?P<cost>(?:\{[^}X]+\})+)$")
WEB_RETURN = " and return a tapped creature you control to its owner's hand"  # 702.188a
SNEAK_RETURN = " and return an unblocked creature you control to its owner's hand"  # -- keywords (wave 30I) -- 702.190a


def grant_web_slinging(t: str) -> dict[str, Any] | None:
    m = GRANT_WEB.fullmatch(t)
    if m is None or parse_cost(f"pay {m['cost']}{WEB_RETURN}") is None:
        return None
    from app.rules.permissions import spell_filter

    key = spell_filter(m["sel"], m["tail"])
    return {"kind": "static", "static": "alt_cost", "cost": f"pay {m['cost']}{WEB_RETURN}", "table": True, "filter": key, "once": False,
            "zone": None, "mv": None, "cond": None, "tag": "web-slinging", "effects": []} if key is not None else None


# -- keywords (wave 30E) -- 702.74a: "Evoke—Exile a white card from your hand." (Solitude, Fury, Grief, Endurance, Subtlety) is an alternative cost
# of non-mana parts ("You may cast this card by paying [cost] rather than its mana cost"); a mana "Evoke {cost}" is casting.EVOKE's
_EVOKE_COST = re.compile(r"^evoke—(?P<cost>[^{}]+)$", re.IGNORECASE)
_FREERUN_COST = re.compile(r"^freerunning—(?P<cost>[^{}]+)$", re.IGNORECASE)  # -- cast keywords (wave 43D) -- "Freerunning—Return a blue creature you control to its owner's hand."
# -- cast keywords (wave 43D) -- 702.176a: "Impending 4—{1}{U}{U}": the first of its four abilities is an alternative cost (tag "impending", ``n``: the time
# counters it enters with); the enters-with, the "isn't a creature" and the end step trigger are read from the cast record (engine, layers, scripts)
_IMPENDING = re.compile(r"^impending (?P<n>\d+)—(?P<cost>(?:\{[^}X]+\})+)$", re.IGNORECASE)


def impending_n(ch: Characteristics) -> int | None:
    """The time counters a permanent cast for its impending cost enters with (its one "Impending N—{cost}" line), or None."""
    found = [m for a in ch.abilities if a.kind == "keywords" and "impending" in a.keywords
             and (m := _IMPENDING.fullmatch(re.sub(r"\s*\(.*?\)", "", a.text).strip().rstrip("."))) is not None]
    return int(found[0]["n"]) if len(found) == 1 else None


def keyword_definition(line: str) -> dict[str, Any] | None:
    line = re.sub(r"\s*\(.*?\)", "", line).strip().rstrip(".")
    if (imp := _IMPENDING.fullmatch(line)) is not None and int(imp["n"]) > 0:
        found = define(f"you may pay {imp['cost']} rather than pay ~'s mana cost")
        return {**found, "tag": "impending", "n": int(imp["n"])} if found is not None else None
    if (ev := _EVOKE_COST.fullmatch(line)) is not None:
        found = define(f"you may {ev['cost'][:1].lower()}{ev['cost'][1:]} rather than pay ~'s mana cost")
        return {**found, "tag": "evoke"} if found is not None else None
    if (fr := _FREERUN_COST.fullmatch(line)) is not None:  # 702.173a: the other parts of an alternative cost, with its condition
        found = define(f"you may {fr['cost'][:1].lower()}{fr['cost'][1:]} rather than pay ~'s mana cost if {FREERUN_COND}")
        return {**found, "tag": "freerunning"} if found is not None else None
    m = _KEYWORD_LINE.fullmatch(line)
    if m is None:
        return None
    kw = m["kw"].lower()
    cond = KEYWORD_CONDS[kw]
    if m["q"] and kw != "emerge":
        return None  # ("from …" is emerge's)
    if "X" in m["cost"].upper() and kw not in X_KEYWORDS:
        return None
    pay = f"pay {m['cost']}"
    if kw == "emerge":  # 702.119a: "pay [cost] and sacrificing a creature" (702.119b: "a [quality] permanent")
        what = (m["q"] or "creature").lower()
        if what not in ("creature", "artifact", "enchantment", "land"):
            return None
        pay += f" and sacrifice {'an' if what[0] in 'aeiou' else 'a'} {what}"
    if kw == "web-slinging":  # -- Marvel keywords (wave 25A) -- 702.188a: "paying [cost] and returning a tapped creature you control to its owner's hand"
        pay += WEB_RETURN
    if kw == "sneak":  # -- keywords (wave 30I) -- 702.190a: "paying [cost] and returning an unblocked creature you control to its owner's hand"
        pay += SNEAK_RETURN
    found = define(f"you may {pay} rather than pay ~'s mana cost" + (f" if {cond}" if cond else ""), x_ok=kw in X_KEYWORDS)
    # ("tag": what the cast record says it was cast for; warp: only "from your hand", 702.185a)
    return {**found, "tag": kw, **({"hand_only": True} if kw == "warp" else {})} if found is not None else None  # (foretell 702.143a: only from the foretell zone, see offers())


@dataclass(frozen=True)
class Offer:
    key: str  # "<card id>:<ability index>"
    label: str
    alt: AltCost
    once_key: str | None = None
    escape: bool = False  # -- escape (wave 5I) -- 702.138a: a cast from the graveyard (app/rules/escape.py)
    tag: str | None = None  # -- keywords (wave 15E) -- "blitz": cast for its blitz cost (702.152a)
    flash: bool = False  # Timing permission belongs only to this actual alternative cost.
    producer_requirement: M.ProducerRequirement | None = None  # Frozen from the actual selected definition.
    minimum_mana_value: int | None = None  # Validated against the selected face and announced X.
    cost_template: GrantedManaCost | None = None
    template_mana_has_x: bool | None = None  # Actual original cost, unknown in old offers.


def sneak_timing(state: GameState, player: str) -> bool:
    """-- keywords (wave 30I) -- 702.190a: "Any time you could cast an instant during your declare blockers step" (priority is the caller's)."""
    return state.turn.phase == "declare_blockers" and state.turn.active_player == player


def _ctx(state: GameState, player: str, source: CardInstance) -> dict[str, Any]:
    r = state.rules
    return {"controller": player, "source_card": source.id, "source_object": r.object_id(source.id) if r is not None else None}


CONVERTED = "more than meets the eye"  # (the keyword: the definition's tag)
CONVERTED_TAG = "converted"  # (the offer's tag, what the cast record says it was cast for: at most 20 characters)


def converted_offers(state: GameState, player: str, card: CardInstance, info: CardInfo) -> list[Offer]:
    """-- commanders (wave 50C) -- 702.162a: "More Than Meets the Eye [cost]" means "You may cast this card converted by paying [cost] rather than its mana cost"
    (an alternative cost, 118.9; casting it converted is casting its back face, 701.28a / 712.8c: casting.cast_spell turns the intent to face 1). It works in
    any zone the card may be cast from; offered from the hand and the command zone (a commander). Read from the front face's line."""
    from app.rules import characteristics as chars
    from app.rules import scripts

    data = info.get(card.card_id) if card.card_id and card.token is None else None
    r = state.rules
    if data is None or data.get("layout") != "transform" or r is None or r.card_mode(card.id) == "manual" or card.owner != player \
            or card.zone not in (f"{player}:hand", f"{player}:command"):
        return []
    front = chars.printed_from_data(data, 0)
    out: list[Offer] = []
    for index, d in scripts.definitions(front).items():
        if d.get("static") == "alt_cost" and d.get("tag") == CONVERTED and (alt := parse_cost(d["cost"])) is not None:
            out.append(Offer(f"{card.id}:{index}", f"{front.name}: {d['cost']} (converted)", alt, tag=CONVERTED_TAG))
    return out


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
    out += converted_offers(state, player, card, info)  # -- commanders (wave 50C) -- 702.162a: More Than Meets the Eye (read from the front face, whichever face ``ch`` is)
    for index, d in scripts.definitions(ch).items():
        if d.get("static") != "alt_cost" or d.get("table") or d.get("tag") == CONVERTED:
            continue
        if d.get("hand_only") and card.zone != f"{player}:hand":
            continue
        if (d.get("tag") == "foretell") != (card.zone == f"{player}:foretell"):
            continue  # -- hidden exile (wave 18A) -- 702.143a: a foretold card is cast for its foretell cost only (and it only from there)
        if d.get("tag") == "foretell" and (card.owner != player or r.foretold.get(card.id, 0) >= state.turn.number):
            continue  # 702.143a/d: its owner, "after the current turn has ended" (a card put there by hand has no record: any turn)
        if d.get("cond") is not None and not conditions.holds(view, _ctx(state, player, card), d["cond"]):
            continue
        if d.get("tag") == "sneak" and not sneak_timing(state, player):
            continue  # -- keywords (wave 30I) -- 702.190a: only where you could cast an instant during your declare blockers step
        if d.get("tag") == "mutate":  # -- merged permanents (wave 18D) -- 702.140a: only with a creature to merge with
            from app.rules import merged

            if not merged.can_mutate(view, player, card, ch):
                continue
        alt = parse_cost(d["cost"], x_ok=d.get("tag") in X_KEYWORDS)
        if alt is not None:
            out.append(Offer(f"{card.id}:{index}", f"{ch.name}: {d['cost']}" + (f" ({d['tag']})" if d.get("tag") in ("mutate", "evoke") else ""), alt, tag=d.get("tag"),
                             producer_requirement=M.ProducerRequirement(d["producer_requirement"]) if d.get("producer_requirement") else None))
    given = r.foretell_costs.get(card.id)  # -- hidden exile (wave 18A) -- 702.143d: a foretell cost an effect gave it
    if given and card.zone == f"{player}:foretell" and card.owner == player and r.foretold.get(card.id, 0) < state.turn.number \
            and (alt := parse_cost(f"pay {given}")) is not None:
        out.append(Offer(f"{card.id}:foretell", f"{ch.name}: {given}", alt, tag="foretell"))
    receipt = r.foretell_templates.get(card.id)
    if receipt is not None and receipt.object_id == r.object_id(card.id) and card.zone == f"{player}:foretell" and card.owner == player and r.foretold.get(card.id, 0) < state.turn.number and ch.mana_cost:
        raw = M.parse_cost(ch.mana_cost)
        if not raw.unsupported:
            out.append(Offer(f"{card.id}:foretell-template", f"{ch.name}: foretell (its mana cost reduced by {{{receipt.template.generic_reduction}}})",
                             AltCost(raw.text(), C.AbilityCost()), tag="foretell", cost_template=receipt.template,
                             template_mana_has_x=bool(raw.x)))
    where = card.zone.rsplit(":", 1)[-1]
    for src, index, d in permissions._table_statics(state, info, {"alt_cost"}):
        if d.get("dynamic_keyword"):
            from app.rules import dynamic_keyword_costs55

            if where != "foretell" and src.controller == player and (granted := dynamic_keyword_costs55.offer(src, index, d, ch)) is not None:
                out.append(granted)
            continue
        if not d.get("table") or (src.controller != player and not d.get("any_controller")) or where == "foretell":
            continue
        key = f"{r.object_id(src.id)}:alt:{index}"  # (-- review 31 -- 400.7: a new As Foretold / Darksteel Monolith has a new use, as permissions' review 30c)
        if d["once"] and r.once_per_turn.get(key) == state.turn.number:
            continue
        if d.get("zone") and not (where == d["zone"] and (d["zone"] != "hand" or card.zone == f"{player}:hand")):
            continue
        if d.get("filter") and not permissions.spell_matches(state, player, card, ch, d["filter"], info):
            continue
        if d.get("filters") and not any(permissions.spell_matches(state, player, card, ch, k, info) for k in d["filters"]):
            continue  # (wave 42A: either kind of spell, "Artifact cards and red creature cards in your hand have warp", zone_grants)
        if d.get("mv") is not None:
            from app.rules import values

            if int(ch.mana_value) > values.evaluate(view, _ctx(state, player, src), d["mv"]):
                continue
        if d.get("cond") is not None and not conditions.holds(view, _ctx(state, player, card), d["cond"]):
            continue  # (wave 17C: prowl — read about the spell being cast)
        alt = parse_cost(d["cost"])
        if alt is not None:
            out.append(Offer(f"{src.id}:{index}", f"{src.name}: {d['cost']}", alt, once_key=key if d["once"] else None, tag=d.get("tag"), flash=bool(d.get("flash"))))
    # -- escape (wave 5I) -- printed and granted escape costs (702.138a), for a card in its owner's graveyard
    from app.rules import escape

    out += escape.offers(state, player, card, ch, info)
    return out


def bind_template(offer: Offer, *, x: int) -> Offer:
    from dataclasses import replace

    if offer.cost_template is None:
        return offer
    raw = offer.alt.mana_cost.with_x(x)
    bound = raw.plus_generic(-min(raw.generic, offer.cost_template.generic_reduction))
    return replace(offer, alt=replace(offer.alt, mana=bound.text()))


def announces_x(offer: Offer) -> bool:
    return bool(offer.alt.mana_cost.x or getattr(offer.alt, "nonmana_x", False) or offer.template_mana_has_x)


def chosen(plan: Plan, key: str, card: CardInstance, ch: Characteristics, *, x: int | None = None) -> Offer:
    """The alternative cost the intent names, checked now (601.2b), or an ActionError."""
    for offer in offers(plan.state, plan.actor, card, ch, plan.info):
        if offer.key == key:
            if offer.minimum_mana_value is not None and (x is not None or not offer.alt.mana_cost.x):
                from app.game.state import StackInfo
                from app.rules import stack_interaction

                probe = card.model_copy(update={"zone": "stack", "stack_info": StackInfo(x=x or 0)})
                if stack_interaction.mana_value(probe, ch) < offer.minimum_mana_value:
                    raise ActionError("That spell's announced mana value is too low for this alternative cost")
            return bind_template(offer, x=x or 0) if x is not None or not offer.alt.mana_cost.x else offer
    raise ActionError("That alternative cost can't be used to cast this spell now")


def merged(extra: C.AbilityCost | None, alt: C.AbilityCost) -> C.AbilityCost | None:
    """The spell's additional cost (118.8) and the alternative cost's non-mana parts, paid together (601.2h)."""
    parts = (extra.components if extra is not None else ()) + alt.components
    if not parts:
        return None
    return C.AbilityCost(components=parts, life=sum(c.amount for c in parts if c.kind == C.PAY_LIFE))
