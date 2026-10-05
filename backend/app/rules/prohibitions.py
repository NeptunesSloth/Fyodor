"""-- prohibitions (wave 22B) -- static "can't" lines checked where the event would happen. Researched against CR 2026-09-25.

* 614.17: an effect that says something can't happen isn't a replacement effect but follows similar rules; 614.17a: it must exist before
  the event; 614.17c: an event that can't happen can only be replaced by a self-replacement effect (614.15), so nothing replaces it and
  nothing triggers on it (603.2g). The line is read while its source is on the battlefield (611.3a), from the table as it is at that
  moment (the same scan as the cast limits: ``cast_limits._statics``).
* "Creature cards in graveyards and libraries can't enter the battlefield." (Grafdigger's Cage, Weathered Runestone, Soulless Jailer,
  Kunoros): checked for each card an effect puts onto the battlefield (``attachments.enter``, the one entry choke point): it stays where it
  is, as an Aura with nothing to enchant does (303.4g). A card in a hidden zone stays silently (a note would show that a card was found).
  Not read: "Lands can't enter the battlefield" (Worms of the Earth: whether a land play is then possible isn't settled).
* "Counters can't be put on artifacts, creatures, enchantments, or lands." (Solemnity), "This creature can't have counters put on it."
  (Tatterkite, Melira's Keepers): checked at the one counter choke point (``replace.plan_counters``) before any replacement is applied,
  for permanents on the battlefield and for one entering with counters (122.6: they are put as it enters; persist and undying returns
  too). A card that isn't a permanent (a suspended card in exile) is not "an artifact, creature, enchantment, or land" on the battlefield.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.state import zone_key
from app.rules import selectors

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo
    from app.rules.plan import Plan

Definition = dict[str, Any]
KINDS = ("cant_enter", "cant_counters", "cant_pay")

_ENTER = re.compile(r"^(?P<what>(?:nonland )?(?:permanent|creature) cards) in (?P<zones>graveyards|libraries|graveyards and libraries) "
                    r"can't enter the battlefield$")
_ZONES = {"graveyards": ("graveyard",), "libraries": ("library",), "graveyards and libraries": ("graveyard", "library")}
_COUNTERS = re.compile(r"^counters can't be put on (?P<sel>[a-z, ]+)$")
_SELF_COUNTERS = "~ can't have counters put on it"
# "Players can't pay life or sacrifice creatures to cast spells or activate abilities." (Angel of Jubilation, Yasharn), "Players can't pay life to
# cast spells or to activate abilities that aren't mana abilities." (Karn's Sylex)
_PAY = re.compile(r"^players can't pay life(?: or sacrifice (?P<sac>[a-z ]+))? to cast spells(?P<act> or activate abilities"
                  r"| or to activate abilities that aren't mana abilities)$")


def static_definition(text: str) -> Definition | None:
    t = text.strip().rstrip(".")
    t = t[:1].lower() + t[1:] if t[:1].isupper() and not t.startswith("~") else t
    m = _ENTER.fullmatch(t)
    if m is not None:
        sel = selectors.parse(m["what"])
        if sel is None or sel.player is not None:
            return None
        return {"kind": "static", "static": "cant_enter", "sel": sel.key(), "zones": list(_ZONES[m["zones"]]), "effects": []}
    m = _COUNTERS.fullmatch(t)
    if m is not None:
        sel = selectors.parse(re.sub(r",? and ", ", or " if "," in m["sel"] else " or ", m["sel"]))
        if sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",) or sel.extras or sel.other:
            return None
        return {"kind": "static", "static": "cant_counters", "sel": sel.key(), "effects": []}
    m = _PAY.fullmatch(t)
    if m is not None:
        sel = selectors.parse(m["sac"]) if m["sac"] else None
        if m["sac"] and (sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",) or sel.extras):
            return None
        return {"kind": "static", "static": "cant_pay", "sac": sel.key() if sel else None,
                "mana": m["act"] == " or activate abilities", "effects": []}
    if t == _SELF_COUNTERS:
        return {"kind": "static", "static": "cant_counters", "sel": None, "effects": []}
    if t == "players can't get counters":  # (122.1: a player gets counters; poison, energy, experience, rad)
        return {"kind": "static", "static": "cant_counters", "sel": None, "players": True, "effects": []}
    return None


def _statics(plan: Plan, kind: str) -> list[tuple[CardInstance, Definition]]:
    from app.rules import cast_limits

    return cast_limits._statics(plan.state, plan.info, kind)


def _label(src: CardInstance) -> str:
    return src.name or "a permanent"


def cant_enter(plan: Plan, card: CardInstance, controller: str) -> tuple[str, bool] | None:
    """(the permanent saying so, whether the card is in a public zone) if ``card`` can't enter the battlefield now (614.17)."""
    found = _statics(plan, "cant_enter")
    if not found:
        return None
    ch = plan.ch(card)
    for src, d in found:
        if not any(card.zone.endswith(f":{z}") for z in d["zones"]):
            continue
        sel = selectors.from_key(d["sel"])
        if sel.types and not set(sel.types) & ch.types or set(sel.not_types) & ch.types:
            continue
        return _label(src), not card.zone.endswith((":library", ":hand"))
    return None


def cant_get_counters(plan: Plan) -> str | None:
    """The permanent saying players can't get counters (614.17), or None."""
    return next((_label(src) for src, d in _statics(plan, "cant_counters") if d.get("players")), None)


def cant_counters(plan: Plan, card_id: str, entering_for: str | None) -> str | None:
    """The permanent saying counters can't be put on this card (614.17), or None. ``entering_for``: the controller it is entering
    under (it isn't on the battlefield yet: only other permanents' lines are read)."""
    found = _statics(plan, "cant_counters")
    card = plan.state.cards.get(card_id)
    if not found or card is None:
        return None
    if entering_for is None and not card.zone.endswith(":battlefield"):
        return None  # (a card in exile with time counters is no permanent)
    probe = card.model_copy(update={"zone": zone_key(entering_for, "battlefield"), "controller": entering_for}) if entering_for else card
    ch = plan.ch(probe)
    for src, d in found:
        if d.get("players"):
            continue
        if d["sel"] is None:
            if src.id == card_id and entering_for is None:
                return _label(src)
        elif selectors.matches(plan, selectors.from_key(d["sel"]), probe, ch, src.controller, src.id):
            return _label(src)
    return None


# -- cost payment (601.2h, 602.2b, 119.4) -- a cost that includes paying life or sacrificing something the line forbids can't be paid, so the
# spell or ability can't be begun (nothing is paid: 601.2h). Read from the table as it is (cast_limits._statics): ``mana_ability`` costs are
# only stopped by the lines that say "activate abilities" (Sylex: "that aren't mana abilities").
def life_banned(state: GameState, info: CardInfo | None, *, mana_ability: bool = False) -> str | None:
    from app.rules import cast_limits

    return next((_label(src) for src, d in cast_limits._statics(state, info, "cant_pay") if d["mana"] or not mana_ability), None)


def sacrifice_banned(state: GameState, info: CardInfo | None, card: CardInstance, *, mana_ability: bool = False) -> str | None:
    """The permanent saying ``card`` can't be sacrificed to pay a cost (a creature for Angel of Jubilation)."""
    from app.rules import cast_limits
    from app.rules.plan import Plan

    found = [(src, d) for src, d in cast_limits._statics(state, info, "cant_pay") if d["sac"] is not None and (d["mana"] or not mana_ability)]
    if not found or info is None:
        return None
    plan = Plan.view(state, card.controller, info)
    ch = plan.ch(card)
    return next((_label(src) for src, d in found if selectors.matches(plan, selectors.from_key(d["sac"]), card, ch, card.controller, src.id)), None)
