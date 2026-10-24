"""-- static permanents (wave 100D) -- exact rule-modifying statics and loyalty abilities of permanents, read onto
existing machinery. Researched against CR 2026-09-25 (rule numbers in each block).

Attachment legality (301.5c, 701.3b, 704.5n; host_problem in app/rules/attachments.py reads these):
* "This Equipment can be attached only to a creature with power 3 or greater." (O-Naginata), "... toughness 4 or greater." (Gate Smasher):
  the equip ability still targets any creature you control, but the Equipment doesn't move onto a creature with less (701.3b; rulings
  2020-08-07 / 2015-02-25), and it becomes unattached as a state-based action once the equipped creature's power / toughness drops below,
  its own bonus included (704.5n; O-Naginata ruling 2020-08-07).
* "This creature can't be equipped." (Goblin Brawler): an equip ability may target it, but the Equipment fails to move (ruling 2004-12-01).
* "You control enchanted artifact creature." (Domineer): the "control" static of Control Magic (613.1b); "Enchant artifact creature" keeps it
  on an artifact creature only (303.4d, 704.5m: ruling 2004-12-01).
* "Enchanted Mountain is a 7/7 red Giant creature with haste. It's still a land." (Awaken the Ancient): the Zendikon static on the enchanted
  land (205.1b, 305.7: it keeps its types, ruling 2013-07-01); "Enchant Mountain" puts the Aura into the graveyard once it stops being a
  Mountain (704.5m).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

ATTACH_ONLY = "attach_only100d"
CANT_BE_EQUIPPED = "cant_be_equipped100d"
_ATTACH_ONLY = re.compile(r"(?:~|This Equipment) can be attached only to a creature with (?P<stat>power|toughness) (?P<n>\d+) or greater\.")
_LAND_TYPES = ("Plains", "Island", "Swamp", "Mountain", "Forest")


def _native(ability: Any, ch: Any, text: str) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    return scripts.define(replace(ability, text=text), ch)


def loyalty(ability: Any, ch: Any, text: str) -> dict[str, Any] | None:
    """Loyalty abilities (606) read as one native instruction list:
    * "Exile ~ and each creature your opponents control." (Gideon, the Oathsworn): one exile of both, at once (608.2c; 610.3: a Gideon that
      already left is simply not among them, ruling 2019-05-03).
    * "Tap all permanents target opponent controls. That player skips their next untap step." (Dovin, Architect of Law): "that player" is the
      target opponent (115.1, 614.10).
    * "~ deals 4 damage to each creature except for tokens you control." (Ajani Unrelenting): one damage event (120.2) to every nontoken
      creature and every creature token an opponent controls.
    * "That player or that planeswalker's controller discards seven cards, then sacrifices seven permanents of their choice." (Nicol Bolas,
      Planeswalker): the two instructions in order (608.2c); the damage being prevented doesn't change them (ruling 2012-07-01).
    * "Destroy up to two target creatures. Put up to two creature cards from graveyards onto the battlefield under your control." (Liliana,
      the Necromancer): the cards are chosen as the ability resolves, after the destruction, from any graveyard, the destroyed ones included
      (608.2c, 608.2d; rulings 2018-07-13)."""
    cost, _, body = text.partition(": ")
    if body == "Exile ~ and each creature your opponents control.":
        base = _native(ability, ch, f"{cost}: Exile each creature your opponents control.")
        if base is None or [e.get("do") for e in base["effects"]] != ["exile"]:
            return None
        return {**base, "effects": [{**base["effects"][0], "who": "union:self+" + base["effects"][0]["who"]}]}
    if body == "Tap all permanents target opponent controls. That player skips their next untap step.":
        base = _native(ability, ch, f"{cost}: Tap all permanents target opponent controls.")
        if base is None or (base.get("target") or {}).get("what") != "opponent":
            return None
        return {**base, "effects": [*base["effects"], {"do": "skip_next", "who": "target", "what": "untap", "n": 1}]}
    if body == "~ deals 4 damage to each creature except for tokens you control.":
        from app.rules import selectors

        base = _native(ability, ch, f"{cost}: ~ deals 4 damage to each nontoken creature.")
        theirs = selectors.parse("creature tokens your opponents control")
        if base is None or theirs is None or [e.get("do") for e in base["effects"]] != ["damage"]:
            return None
        return {**base, "effects": [{**base["effects"][0], "who": f"union:{base['effects'][0]['who']}+{theirs.key()}"}]}
    tail = "That player or that planeswalker's controller discards seven cards, then sacrifices seven permanents of their choice."
    if body == f"~ deals 7 damage to target player or planeswalker. {tail}":
        return _native(ability, ch, f"{cost}: ~ deals 7 damage to target player or planeswalker. That player or that planeswalker's controller "
                                    "discards seven cards. That player or that planeswalker's controller sacrifices seven permanents of their choice.")
    if body == "Destroy up to two target creatures. Put up to two creature cards from graveyards onto the battlefield under your control.":
        from app.rules import scripts

        base = _native(ability, ch, f"{cost}: Destroy up to two target creatures.")
        put = scripts.parse_effects("Put a creature card from a graveyard onto the battlefield under your control.")
        if base is None or put is None or len(put[0]) != 1 or put[0][0].get("do") != "return_choice":
            return None
        return {**base, "effects": [*base["effects"], {**put[0][0], "n": 2, "upto": True, "label": "creature cards"}]}
    return None


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, statics

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == "loyalty":
        return loyalty(ability, ch, text)
    if ability.kind == "activated" and text == "Sacrifice ~: Regenerate all Werewolf creatures you control.":
        # (Full Moon's Rise: a shield on each of them as it resolves, 701.19a, 608.2c)
        from app.rules import selectors

        base, wolves = _native(ability, ch, "Sacrifice ~: Regenerate each creature you control."), selectors.parse("Werewolf creatures you control")
        return {**base, "effects": [{"do": "regenerate", "who": wolves.key()}]} if base is not None and wolves is not None else None
    if ability.kind != "static":
        return None
    if text in _AS_ENTERS:
        return {"kind": "static", "static": AS_ENTERS, "do": _AS_ENTERS[text], "effects": []}
    if (m := _ATTACH_ONLY.fullmatch(text)) is not None and "Equipment" in ch.subtypes:
        return {"kind": "static", "static": ATTACH_ONLY, "stat": m["stat"], "min": int(m["n"]), "effects": []}
    if text in ("~ can't be equipped.", "This creature can't be equipped.") and ch.is_creature:
        return {"kind": "static", "static": CANT_BE_EQUIPPED, "effects": []}
    if text == "You control enchanted artifact creature.":
        return {"kind": "static", "static": "control", "who": "host", "effects": []}
    m = re.fullmatch(rf"Enchanted (?P<t>{'|'.join(_LAND_TYPES)}) (?P<rest>is an? \d+/\d+ .+\. It's still a land\.)", text)
    if m is not None and f"enchant {m['t'].lower()}" in (ch.oracle_text or "").lower().split("\n"):
        return statics.parse(f"Enchanted land {m['rest']}")  # (the Aura's own enchant line: the host is that land type, 303.4a)
    return None


# -- "As ~ enters, <instruction>." (614.1c, 614.12) ------------------------------------------------------------------------
# A replacement effect of the entering permanent (not a trigger, 603.6d): the instruction is carried out immediately before it enters,
# however it enters, by the player it enters under ("you"), as part of the entering event; nobody gets priority in between (rulings:
# Overlaid Terrain 2004-10-04 "right before this enchantment enters"; Wood Elemental 2004-10-04 "no matter how this card enters").
# The permanent being put onto the battlefield is no card of that player's hand or lands any more (it is the object entering).
AS_ENTERS = "as_enters100d"
_AS_ENTERS = {"As ~ enters, discard your hand.": "discard_hand", "As ~ enters, sacrifice all lands you control.": "sacrifice_lands"}


def plan_entry(plan: Plan, card: CardInstance, controller: str, out: dict[str, Any]) -> None:
    """replacements.entry_plan's part: the instructions to carry out as ``card`` enters under ``controller`` (read from the permanent as it
    would exist on the battlefield, 614.12)."""
    from app.game.state import zone_key
    from app.rules import scripts

    if out.get("divert") or out.get("divert_zone") or plan.manual(card):
        return
    probe = card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller})
    found = [d["do"] for d in scripts.definitions(plan.ch(probe)).values() if d.get("kind") == "static" and d.get("static") == AS_ENTERS]
    if found:
        out[AS_ENTERS] = found


def as_enters(plan: Plan, card_id: str, ep: dict[str, Any], controller: str) -> None:
    """Carry out what ``plan_entry`` found, in printed order (608.2c), before the permanent is moved."""
    from app.game.state import zone_key
    from app.rules import effects

    for what in ep.get(AS_ENTERS) or ():
        name = plan.state.cards[card_id].name if card_id in plan.state.cards else "It"
        ctx: dict[str, Any] = {"controller": controller, "source_card": card_id, "source_object": plan.oid(card_id), "effects": [], "next": 0}
        if what == "discard_hand":  # 701.9a: the whole hand, no choice
            hand = [c for c in plan.state.zones.get(zone_key(controller, "hand"), []) if c != card_id]
            plan.note(f"As {name} enters, {plan.name(controller)} discards their hand", [card_id])
            effects._discard_next(plan, ctx, 0, [], hand)
        elif what == "sacrifice_lands":  # 701.21a: all at once
            lands = [c for c in plan.state.zones.get(zone_key(controller, "battlefield"), [])
                     if c != card_id and plan.in_game(plan.state.cards[c]) and plan.ch(plan.state.cards[c]).is_land]
            plan.note(f"As {name} enters, {plan.name(controller)} sacrifices all lands they control", [card_id])
            effects._sacrifice_cards(plan, lands, controller, ctx)


def _statics(plan: Plan, card: CardInstance, kind: str) -> list[dict[str, Any]]:
    from app.rules import scripts

    if plan.manual(card):
        return []
    return [d for d in scripts.definitions(plan.ch(card)).values() if d.get("kind") == "static" and d.get("static") == kind]


def equip_problem(plan: Plan, source: CardInstance, host: CardInstance) -> str | None:
    """Why the Equipment ``source`` can't be attached to the creature ``host`` by its own or the host's rules (301.5c, 701.3b), or None."""
    from app.rules import sba

    if _statics(plan, host, CANT_BE_EQUIPPED):
        return f"{host.name or 'that creature'} can't be equipped"
    for d in _statics(plan, source, ATTACH_ONLY):
        hch = plan.ch(host)
        value = sba.power(host, hch) if d["stat"] == "power" else sba.toughness(host, hch)
        if value is not None and value < int(d["min"]):  # (a value the engine can't read: never moved off on a guess)
            return f"it can be attached only to a creature with {d['stat']} {d['min']} or greater"
    return None
