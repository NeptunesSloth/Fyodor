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
    if ability.kind == "activated" and text == "{1}: ~ becomes the creature type of your choice in addition to its other types until end of turn.":
        base = _native(ability, ch, "{1}: ~ becomes the creature type of your choice until end of turn.")  # (Mistform Sliver's grant: 205.1b, added
        if base is None or [e.get("pick") for e in base["effects"]] != ["creature type"]:  # not set; ruling 2004-10-04)
            return None
        return {**base, "effects": [{**base["effects"][0], "pick_added": True}]}
    if ability.kind == "triggered" and text == "When ~ enters, you may fateseal 1.":
        # 701.29a: look at the top card of an opponent's library (the fatesealing player picks which: no target), then you may put it on the
        # bottom of that library (Mesmeric Sliver's grant). Only that player sees the card (701.29a "look").
        base = _native(ability, ch, "When ~ enters, choose an opponent. Look at the top card of that player's library. You may put that card on the "
                                    "bottom of that library.")
        return None if base is None else {**base, "optional": True}
    if ability.kind == "activated" and text == "Sacrifice ~: Regenerate all Werewolf creatures you control.":
        # (Full Moon's Rise: a shield on each of them as it resolves, 701.19a, 608.2c)
        from app.rules import selectors

        base, wolves = _native(ability, ch, "Sacrifice ~: Regenerate each creature you control."), selectors.parse("Werewolf creatures you control")
        return {**base, "effects": [{"do": "regenerate", "who": wolves.key()}]} if base is not None and wolves is not None else None
    if ability.kind != "static":
        return None
    if (solve := re.fullmatch(r"To solve — (?P<c>.+?)\.(?: \(If unsolved, solve at the beginning of your end step\.\))?", text)) is not None \
            and solve["c"] in _SOLVE and "Case" in ch.subtypes:
        return case_solve(_SOLVE[solve["c"]])
    if text == "~ is a 4/4 Gorgon creature with deathtouch and lifelink in addition to its other types." and "Case" in ch.subtypes:
        # (Case of the Gorgon's Kiss, "Solved —": characteristics.of keeps the line only while it is solved, 719.3c; layer 4 and 7b, 613.1d)
        native = statics.parse("Enchanted land is a Gorgon creature with base power and toughness 4/4 in addition to its other types and has deathtouch and lifelink.")
        return None if native is None else {**native, "who": "self", "attached_kind": None, "add_subtypes": []}
    if text == "Other Sliver creatures you control have outlast {2}.":
        # 702.107a: "Outlast [cost]" means "[Cost], {T}: Put a +1/+1 counter on this permanent. Activate only as a sorcery." (granted as that
        # ability, the way oracle.py reads a printed outlast line; Enduring Sliver)
        return statics.parse('Other Sliver creatures you control have "{2}, {T}: Put a +1/+1 counter on this creature. Activate only as a sorcery."')
    if text in _CDAS:  # 604.3, 613.4a: characteristic-defining, in every zone (layers._cda)
        return {"kind": "static", "static": "cda", "effects": [], "p": {"perm100d": _CDAS[text]}, "t": {"perm100d": _CDAS[text]}}
    if text == "~ gets +1/+1 for each card in your hand and each foretold card you own in exile.":
        pump = statics.parse("~ gets +1/+1 for each card in your hand.")  # (Alrund: layer 7c, on the battlefield only, ruling 2021-02-05)
        if pump is None or not pump.get("each"):
            return None
        return {**pump, "each": {**pump["each"], "value": {"perm100d": "hand_and_foretold"}}}
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


# -- characteristic-defining power and toughness (604.3, 613.4a) and counted bonuses -------------------------------------------
# values.evaluate hands ``{"perm100d": kind}`` here. A CDA that sets power and toughness may set them below 0 (107.1b: an effect that sets
# power and toughness to a value is the exception; Scourge of the Skyclaves ruling 2020-09-25: its toughness can be less than 0).
_CDAS = {
    "~'s power and toughness are each equal to 20 minus the highest life total among players.": "twenty_minus_highest",
    "~'s power and toughness are each equal to your life total minus the life total of an opponent with the most life.": "life_minus_top_opponent",
    "During your turn, ~'s power and toughness are each equal to 2 plus the number of Swamps your opponents control. During turns other "
    "than yours, ~'s power and toughness are each 2.": "angry_mob",
}


# -- Cases (719.3a): "To solve — [condition]" is "At the beginning of your end step, if [condition] and this Case is not solved, it becomes
# solved." (checked as it would trigger and again on resolution: rulings 2024-02-02). The conditions read this turn's history (608.2i):
# * "You control no suspected Skeletons." — the Skeletons you control that are suspected now (701.60);
# * "Three or more creatures attacked this turn." — the creatures declared as attackers this turn, each once (508.1; one put onto the
#   battlefield attacking never attacked, 508.4);
# * "Three or more creature cards were put into graveyards from anywhere this turn." — cards (no tokens) with the creature type as they are
#   in the graveyard (ruling 2024-02-02), whoever owns them, each arrival once;
# * "Three or more sources you controlled dealt damage this turn." — distinct source objects under your control as they dealt damage (a
#   source dealing damage twice is one source; one that changed zones is a new one: rulings 2024-02-02).
_SOLVE = {
    "You control no suspected Skeletons": {"value": {"perm100d": "suspected_skeletons"}, "op": "==", "n": 0},
    "Three or more creatures attacked this turn": {"value": {"turn_history": "attackers"}, "op": ">=", "n": 3},
    "Three or more creature cards were put into graveyards from anywhere this turn": {"value": {"perm100d": "creature_cards_to_graveyards"}, "op": ">=", "n": 3},
    "Three or more sources you controlled dealt damage this turn": {"value": {"perm100d": "damage_sources"}, "op": ">=", "n": 3},
}


def case_solve(cond: dict[str, Any]) -> dict[str, Any]:
    unsolved = {"all": [cond, {"object": "self", "test": "solved", "negate": True}]}  # (the same trigger scripts builds for "To solve —")
    return {"kind": "triggered", "trigger": "end_step_you", "if": unsolved, "optional": False, "target": None,
            "effects": [{"do": "only_if", "cond": unsolved, "skip": 1}, {"do": "become_solved"}]}


def amount(plan: Plan, ctx: dict[str, Any], v: dict[str, Any]) -> int:
    from app.game.state import zone_key
    from app.rules import values

    you = ctx["controller"]
    kind = v["perm100d"]
    lives = {p: plan.state.players[p].life for p in plan.live()}  # (players still in the game, 800.4a)
    if kind == "twenty_minus_highest":
        return 20 - max(lives.values(), default=0)
    if kind == "life_minus_top_opponent":  # (the opponent with the most life; ties give the same number)
        return lives.get(you, plan.state.players[you].life if you in plan.state.players else 0) - max((n for p, n in lives.items() if p != you), default=0)
    if kind == "angry_mob":  # "your turn": its controller's (outside the battlefield and the stack, its owner's: 108.4a)
        if plan.state.turn.active_player != you:
            return 2
        swamps = values.parse_count("the number of Swamps your opponents control")
        return 2 + (values.evaluate(plan, ctx, swamps) if swamps is not None else 0)
    if kind == "hand_and_foretold":  # 702.143a: a foretold card is exiled face down, in its owner's foretell area of exile
        return len(plan.state.zones.get(zone_key(you, "hand"), [])) + sum(
            1 for c in plan.state.zones.get(zone_key(you, "foretell"), []) if plan.state.cards[c].owner == you)
    if kind == "suspected_skeletons":
        return sum(1 for c in plan.state.zones.get(zone_key(you, "battlefield"), []) if plan.in_game(plan.state.cards[c])
                   and plan.oid(c) in plan.rules.suspected and "Skeleton" in plan.ch(plan.state.cards[c]).subtypes)
    from app.rules import characteristics as chars
    from app.rules import history

    log = history.log_for(plan)
    if kind == "creature_cards_to_graveyards":
        return sum(1 for a in log.entered_graveyard if (card := plan.state.cards.get(a.card)) is not None and card.card_id is not None
                   and not card.is_token and card.ability is None and "Creature" in chars.of(card, plan.info).types)
    if kind == "damage_sources":  # (the history keeps each source by its object and its controller then, wave 42B)
        return len({src for f in log.facts if f.amount > 0 and f.source_controller == you
                    and (src := f.object_id if f.kind == "damage" else f.source if f.kind == "damaged" else None) is not None})
    raise ValueError(f"unknown wave 100D value {v!r}")


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
