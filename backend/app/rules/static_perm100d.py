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
    if body == 'Create a white Avatar creature token. It has "This token\'s power and toughness are each equal to your life total."':
        # (Ajani Goldmane: the token's own characteristic-defining ability, 604.3; "this token" is "this creature", the same object)
        from app.rules import scripts

        base = _native(ability, ch, f"{cost}: You gain 2 life.")  # (the quoted text read as written: no "~" for Ajani in it)
        made = scripts.parse_effects('Create a white Avatar creature token with "This creature\'s power and toughness are each equal to your life total."')
        return None if base is None or made is None or made[1] is not None else {**base, "effects": made[0]}
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
    if (single := _single(ability, ch, text)) is not None:
        return single
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
    if text in _LIFE_LINES:
        return {"kind": "static", "static": LIFE_ENTRY, "cap": _LIFE_LINES[text], "effects": []}
    if text in _AS_ENTERS:
        return {"kind": "static", "static": AS_ENTERS, "do": _AS_ENTERS[text], "effects": []}
    if text == "~ can be attached only to a legendary creature." and "Equipment" in ch.subtypes:  # -- wave 110A -- Konda's Banner (301.5c, 704.5n)
        return {"kind": "static", "static": ATTACH_ONLY, "stat": "legendary", "min": 0, "effects": []}
    if (m := _ATTACH_ONLY.fullmatch(text)) is not None and "Equipment" in ch.subtypes:
        return {"kind": "static", "static": ATTACH_ONLY, "stat": m["stat"], "min": int(m["n"]), "effects": []}
    if (rule := _rule_static(text, ch)) is not None:
        return rule
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
    "~'s power and toughness are each equal to the life paid as it entered.": "life_paid",
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
    if kind == "life_paid":  # (the amount recorded as it entered; none outside the battlefield)
        card = plan.state.cards.get(ctx.get("source_card") or "")
        return int((card.choices.get("Life paid") or 0) if card is not None and card.zone.endswith(":battlefield") else 0)
    if kind == "life_paid_lki":  # -- multi (wave 100M) -- Phyrexian Processor's ability: its source as it is, or as it last existed (608.2h)
        card, oid = plan.state.cards.get(ctx.get("source_card") or ""), ctx.get("source_object") or ""
        here = card is not None and plan.oid(card) == oid and card.zone.endswith(":battlefield")
        return int(((card.choices if here and card is not None else snap.choices if (snap := plan.rules.lki.get(oid)) else {}).get("Life paid")) or 0)
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
# "As ~ enters, pay any amount of life." (Minion of the Wastes; Nameless Race: no more than the white nontoken permanents your opponents control
# plus the white cards in their graveyards): 119.4, 614.12a — the amount is chosen before it enters (0 up to your life total; 0 if you can't
# lose life, 119.8), paid as it enters (rulings 2011-01-25, 2004-10-04), and kept on the permanent as "Life paid" for its CDA (604.3).
LIFE_ENTRY, LIFE_KEY = "life_entry100d", "amount of life to pay"
_LIFE_LINES = {"As ~ enters, pay any amount of life.": None,
               "As ~ enters, pay any amount of life. The amount you pay can't be more than the total number of white nontoken permanents your opponents "
               "control plus the total number of white cards in their graveyards.": "white"}


def life_cap(plan: Plan, ctx: dict[str, Any]) -> int:
    from app.rules import life_lock, scripts, values

    you, card = ctx["controller"], plan.state.cards.get(ctx.get("source_card") or "")
    cap = plan.state.players[you].life if you in plan.state.players else 0
    if cap <= 0 or life_lock.pay_problem(plan.state, plan.info, you, 1) is not None:
        return 0
    defs = scripts.definitions(plan.ch(card)).values() if card is not None else ()
    if any(d.get("static") == LIFE_ENTRY and d.get("cap") == "white" for d in defs):
        counts = [values.parse_count(t) for t in ("the number of white nontoken permanents your opponents control",
                                                  "the number of white cards in your opponents' graveyards")]
        cap = min(cap, sum(values.evaluate(plan, ctx, c) for c in counts if c is not None))
    return cap


_AS_ENTERS = {"As ~ enters, discard your hand.": "discard_hand", "As ~ enters, sacrifice all lands you control.": "sacrifice_lands",
              "As ~ enters, mill three cards for each time it was kicked.": "mill_per_kick",  # (Urborg Lhurgoyf: 702.33d, rulings 2022-09-09)
              "As ~ enters, if it was kicked, mill four cards.": "kicked_mill4"}  # (-- activated (wave 100I) -- Monstrous War-Leech: 702.33d, 701.17a)


def plan_entry(plan: Plan, card: CardInstance, controller: str, out: dict[str, Any], answers: dict[str, str] | None = None) -> None:
    """replacements.entry_plan's part: the instructions to carry out as ``card`` enters under ``controller`` (read from the permanent as it
    would exist on the battlefield, 614.12); "pay any amount of life" asks the amount first (614.12a, an entering choice)."""
    from app.game.state import zone_key
    from app.rules import scripts

    if out.get("divert") or out.get("divert_zone") or plan.manual(card):
        return
    probe = card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller})
    defs = [d for d in scripts.definitions(plan.ch(probe)).values() if d.get("kind") == "static" and d.get("static") in (AS_ENTERS, LIFE_ENTRY)]
    found = [d["do"] for d in defs if d["static"] == AS_ENTERS]
    if any(d["static"] == LIFE_ENTRY for d in defs):
        value = (answers or {}).get(LIFE_KEY)
        if value is None:
            out.setdefault("choice", {"what": LIFE_KEY})
        else:
            out.setdefault("choices", {})[LIFE_KEY] = value
            out[LIFE_ENTRY] = int(value or 0)
            found.append("pay_life")
    if found:
        out[AS_ENTERS] = found


def as_enters(plan: Plan, card_id: str, ep: dict[str, Any], controller: str) -> None:
    """Carry out what ``plan_entry`` found, in printed order (608.2c), before the permanent is moved."""
    from app.game.state import zone_key
    from app.rules import effects, values

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
        elif what == "pay_life" and (n := min(int(ep.get(LIFE_ENTRY) or 0), plan.state.players[controller].life)) > 0:  # 119.4
            from app.rules import replace

            plan.note(f"As {name} enters, {plan.name(controller)} pays {n} life", [card_id])
            replace.lose_life(plan, [(controller, n)])
        elif what == "mill_per_kick" and (n := 3 * values.kicked_count(plan, ctx)):  # 701.17a (not cast: never kicked)
            plan.note(f"As {name} enters, {plan.name(controller)} mills {n} cards", [card_id])
            effects.PRIMITIVES["mill"](plan, ctx, {"do": "mill", "who": "you", "n": n})
        elif what == "kicked_mill4":  # (the spell's own payment record, 601.2h: "if it was kicked")
            from app.rules import conditions

            if conditions.holds(plan, ctx, {"object": "self", "cast": {"kicked": True}}):
                effects.PRIMITIVES["mill"](plan, ctx, {"do": "mill", "who": "you", "n": 4})


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
        if d["stat"] == "legendary":  # (-- wave 110A -- "can be attached only to a legendary creature")
            if "Legendary" not in hch.supertypes:
                return "it can be attached only to a legendary creature"
            continue
        value = sba.power(host, hch) if d["stat"] == "power" else sba.toughness(host, hch)
        if value is not None and value < int(d["min"]):  # (a value the engine can't read: never moved off on a guess)
            return f"it can be attached only to a creature with {d['stat']} {d['min']} or greater"
    return None


# -- rule-modifying statics (wave 100D) ---------------------------------------------------------------------------------------
# * "During your turn, you and ~ have hexproof." (Gruul Spellbreaker): 702.11b/c, a player's hexproof and the creature's, both only while it
#   is its controller's turn (611.3a; player_shields._shields reads the grant's condition).
# * "You can't play lands or cast spells from your hand." (Experimental Frenzy): 601.3, 305.1; other actions with those cards stay possible
#   (cycling, bloodrush: ruling 2018-10-05). Lands from hand: engine.land_play_problem reads ``lands_from_hand``.
# * "Players can cast spells and activate abilities only during their own turns." (City of Solitude): 601.3, 602.5 — mana abilities too (605.1a;
#   ruling 2009-10-01), and abilities of cards that aren't on the battlefield (ruling 2004-10-04); triggered abilities are never activated.
# * "All lands are no longer snow." (Melting): 205.4, 613.1d, a supertype removed in layer 4.
# * "You can't choose an untapped permanent / creature as this spell's target as you cast it." (Dream Leash, Enthralling Hold): 601.2c, only the
#   target chosen as the Aura spell is cast (``cast_aura``); on resolution, or when its target changes, the enchant ability alone counts, and an
#   Aura put onto the battlefield without being cast is attached to any legal object (rulings 2005-10-01, 2020-06-23).
TAPPED_TARGET = "tapped_target100d"


def _rule_static(text: str, ch: Any) -> dict[str, Any] | None:
    from app.rules import statics

    if text == "During your turn, you and ~ have hexproof.":
        own = statics.parse("During your turn, ~ has hexproof.")
        ok = own is not None and own.get("static") == "grant" and own.get("conditions") == [{"static": "your_turn"}]
        return {**own, "player_shield": "hexproof"} if ok and own is not None else None
    if text == "You can't play lands or cast spells from your hand.":
        return {"kind": "static", "static": "cast_limit", "who": "you", "when": None, "filter": None, "from": ["hand"], "act": None, "max": None,
                "lands_from_hand": True, "effects": []}
    if text == "Players can cast spells and activate abilities only during their own turns.":
        return {"kind": "static", "static": "cast_limit", "who": "each", "when": "not_own_turn", "filter": None, "from": None, "act": "all", "max": None,
                "effects": []}
    if text == "All lands are no longer snow.":
        from app.rules import type_statics

        return type_statics._definition("lands", {"remove_supertypes": ["Snow"]})
    m = re.fullmatch(r"If (?:this card|~) is in a graveyard, effects from spells named (?P<n>[^.]+) count it as a card named (?P=n)\.", text)
    if m is not None:
        return {"kind": "static", "static": COUNTS_AS, "name": m["n"], "effects": []}
    if text == "Other creatures you control that are enchanted by Auras you control have base power and toughness 4/4 and have flying.":
        # (Archon of the Wild Rose: enchanted by at least one Aura you control; 613.4b in timestamp order, rulings 2023-09-01)
        return statics.parse("Other creatures you control that are enchanted by an Aura you control have base power and toughness 4/4 and have flying.")
    if text == "You may activate the loyalty abilities of ~ twice each turn rather than only once.":  # (Urza, Planeswalker: 606.3, its own)
        return {"kind": "static", "static": "loyalty_rule", "who": "self", "twice": True, "effects": []}
    if text == ('Each creature your opponents control is an Illusion in addition to its other types and has "When ~ becomes the target '
                'of a spell or ability, sacrifice it."'):  # (Dismiss into Dream: one group, layers 4 and 6, as type_statics' _GRANT_AND_TYPE reads)
        from app.rules import type_statics

        grant = statics.parse('Creatures your opponents control have "When this creature becomes the target of a spell or ability, sacrifice it."')
        typed = type_statics.parse("Creatures your opponents control are Illusions in addition to their other types.")
        if grant is None or typed is None or grant["who"] != typed["who"] or not typed.get("layer4"):
            return None
        return {**grant, "layered": True, "layer4": typed["layer4"]}
    if text in _FLAGS:
        return {"kind": "static", "static": _FLAGS[text], "effects": []}
    if text == "Recover—Pay half your life, rounded up.":
        return _recover_half()
    m = re.fullmatch(r"You can't choose an untapped (?P<n>permanent|creature) as this spell's target as you cast it\.", text)
    if m is not None and "Aura" in ch.subtypes:
        return {"kind": "static", "static": TAPPED_TARGET, "noun": m["n"], "effects": []}
    return None


def cast_aura(ch: Any, aura: str | None) -> str | None:
    """The selector the Aura spell ``ch`` targets with as it is cast (601.2c): its enchant selector, tapped ones only under TAPPED_TARGET."""
    from app.rules import scripts, selectors

    if aura is None or not any(d.get("static") == TAPPED_TARGET and d["noun"] == aura for d in scripts.definitions(ch).values()):
        return aura
    sel = selectors.parse(f"tapped {aura}")
    return aura if sel is None else sel.key()


# -- "effects from spells named N count it as a card named N" (Pardic Firecat, Diligent Farmhand) --------------------------------
# 201.2, 404.1: while the card is in a graveyard, a count by a spell named N of "cards named N" (Flame Burst, Muscle Burst: the selector
# extra ``named_self``, selectors.matches) includes it; for any other source it keeps its own name.
COUNTS_AS = "counts_as100d"


def counted_as(plan: Plan, source: str | None, card: CardInstance, ch: Any) -> bool:
    from app.rules import scripts

    src = plan.state.cards.get(source or "")
    if src is None or src.zone != "stack" or src.ability is not None or not card.zone.endswith(":graveyard"):
        return False
    name = plan.ch(src).name
    return any(d.get("static") == COUNTS_AS and d["name"] == name for d in scripts.definitions(ch).values())


def _recover_half() -> dict[str, Any] | None:
    """702.59a: "Recover—Pay half your life, rounded up." (Garza's Assassin) is recover's trigger with that cost (119.4: half a life total,
    rounded up, can always be paid; 0 at 0 life)."""
    import json

    from app.rules import keyword_triggers

    found = keyword_triggers._definition("recover {2}")
    d = json.loads(found)[0] if found else None
    if d is None or d["effects"][0].get("cost") != "{2}":
        return None
    return {**d, "effects": [{**d["effects"][0], "cost": "Pay half your life, rounded up"}, *d["effects"][1:]]}


def _single(ability: Any, ch: Any, text: str) -> dict[str, Any] | None:
    """Single triggered and activated wordings read onto a native neighbour:
    * Dragon Turtle: "tap it and up to one target creature …. They don't untap during their controllers' next untap steps." — each stays tapped
      through its own controller's next untap step (502.3); an illegal target: the whole ability does nothing (608.2b, rulings 2021-07-23).
    * Blue Dragon: a third target group, "other" than both earlier ones (115.3; ruling 2021-07-23), with the same "until your next turn".
    * Legate Lanius: "a tenth of the creatures they control …, rounded up" — each opponent's own count (ruling 2024-03-08).
    * Elsewhere Flask: "Choose a basic land type. Each land you control becomes that type until end of turn." — chosen as it resolves, the lands
      you control then (611.2c) have only that land type (305.7; rulings 2008-05-01)."""
    from app.rules import selectors

    if text == "When ~ enters, tap it and up to one target creature an opponent controls. They don't untap during their controllers' next untap steps.":
        base = _native(ability, ch, "When ~ enters, tap ~ and up to one target creature an opponent controls.")
        if base is None or [e.get("do") for e in base["effects"]] != ["tap", "tap"]:
            return None
        return {**base, "effects": [*base["effects"], *({"do": "stay_tapped", "who": w, "during": "controller"} for w in ("self", "target:0"))]}
    if text == ("When ~ enters, until your next turn, target creature an opponent controls gets -3/-0, up to one other target creature gets -2/-0, "
                "and up to one other target creature gets -1/-0."):
        base = _native(ability, ch, "When ~ enters, until your next turn, target creature an opponent controls gets -3/-0 and up to one other target creature gets -2/-0.")
        groups = (base or {}).get("targets")
        if base is None or not isinstance(groups, list) or len(groups) != 2 or base["effects"][0] != {"do": "until", "duration": "next_turn", "n": 2}:
            return None
        return {**base, "targets": [*groups, {**groups[1], "distinct_from": [0, 1]}],
                "effects": [{**base["effects"][0], "n": 3}, *base["effects"][1:], {"do": "pump", "who": "target:2", "p": -1, "t": 0}]}
    if text == "When ~ enters, each opponent sacrifices a tenth of the creatures they control of their choice, rounded up.":
        base = _native(ability, ch, "When ~ enters, each opponent sacrifices half the creatures they control of their choice, rounded up.")
        if base is None or [e.get("n") for e in base["effects"]] != [{"half_own": "up"}]:
            return None
        return {**base, "effects": [{**base["effects"][0], "n": {"half_own": "up", "div": 10}}]}
    if text == "Sacrifice ~: Choose a basic land type. Each land you control becomes that type until end of turn.":
        base = _native(ability, ch, "Sacrifice ~: Target land becomes the basic land type of your choice until end of turn.")
        lands = selectors.parse("lands you control")
        if base is None or lands is None or [e.get("do") for e in base["effects"]] != ["become"]:
            return None
        return {**base, "target": None, "effects": [{**base["effects"][0], "who": lands.key()}]}
    return None


# -- flags read where the rule acts ---------------------------------------------------------------------------------------------
# * "You can't cast ~ during your first, second, or third turns of the game." (Serra Avenger): 601.3, on the caster's own turns only, counted
#   as the turns they have taken (extra turns too: ruling 2012-07-01; another player's turn: ruling 2006-09-25) — cast_limits.cast_problem.
# * "Permanents your opponents control can't be turned face up during your turn." (Karlov Watchdog): 702.37e, 701.40b, 701.58b — neither the
#   special action (ruling 2024-02-02) nor an effect turns one up (casting.turn_face_up, facedown._turn_up).
# * "All damage is dealt as though its source had wither." (Everlasting Torment): 702.80a, 120.3d — damage to a creature is -1/-1 counters
#   (replace.py, wherever the source is: ruling 2008-05-01).
# * "You may look at an additional two cards each time you surveil." (Enhanced Surveillance): 701.25a, part of what you surveil, two more for
#   each one you control (rulings 2018-10-05) — effects._look.
# * "Foretelling cards from your hand costs {1} less and can be done on any player's turn." (Cosmos Charger): 702.143a, the special action's {2}
#   less {1} for each one you control, any time you have priority (rulings 2021-02-05) — casting.foretell.
# * "Planeswalkers' loyalty abilities you activate cost an additional [+1] to activate." (Carth the Lion): 606.4, 118.8 — one total loyalty cost
#   ([-3] removes two counters at once; [0] becomes [+1]), +1 for each one you control (rulings 2021-06-18) — casting.ability_problem / pay.
FIRST_TURNS, NO_FACE_UP, ALL_WITHER, MORE_SURVEIL, FORETELL = "first_turns100d", "no_face_up100d", "all_wither100d", "more_surveil100d", "foretell100d"
# * "Planeswalkers you control aren't put into their owners' graveyards for having 0 loyalty." (Sanctum Lurker): the 704.5i exception (ruling
#   2026-08-21) — sba.py.
# * "You can't spend mana to cast this spell." (Hogaak): 601.2h, the total cost is paid by convoke and delve only — casting.pay_spell.
# * "Instant and sorcery spells you control have rebound." (Cast Through Time): 702.88a, read as the spell finishes resolving (on the battlefield
#   then, ruling 2010-06-15) — engine's rebound check; cast from your hand only, copies never (rulings 2010-06-15).
LOYALTY_PLUS, ZERO_LOYALTY, NO_MANA, REBOUND = "loyalty_plus100d", "zero_loyalty100d", "no_mana100d", "rebound100d"
_FLAGS = {"Instant and sorcery spells you control have rebound.": REBOUND,
"Planeswalkers you control aren't put into their owners' graveyards for having 0 loyalty.": ZERO_LOYALTY,
          "You can't spend mana to cast this spell.": NO_MANA,
"Planeswalkers' loyalty abilities you activate cost an additional [+1] to activate.": LOYALTY_PLUS,
"You may look at an additional two cards each time you surveil.": MORE_SURVEIL,
          "Foretelling cards from your hand costs {1} less and can be done on any player's turn.": FORETELL,
          "You can't cast ~ during your first, second, or third turns of the game.": FIRST_TURNS,
          "Permanents your opponents control can't be turned face up during your turn.": NO_FACE_UP,
          "All damage is dealt as though its source had wither.": ALL_WITHER}


def _sources(plan: Plan, kind: str) -> list[CardInstance]:
    return [c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and not c.face_down and plan.in_game(c) and _statics(plan, c, kind)]


def yours(plan: Plan, kind: str, player: str) -> int:
    return sum(1 for c in _sources(plan, kind) if c.controller == player)


def loyalty_plus(state: Any, info: Any, player: str) -> int:
    from app.rules.plan import Plan

    return yours(Plan.view(state, player, info), LOYALTY_PLUS, player) if info is not None else 0


def any_static(plan: Plan, kind: str) -> bool:
    return bool(_sources(plan, kind))


def face_up_barred(plan: Plan, card: CardInstance) -> str | None:
    you = plan.state.turn.active_player
    src = next((c for c in _sources(plan, NO_FACE_UP) if c.controller == you != card.controller), None)
    return None if src is None else f"{src.name or 'A permanent'}: permanents its controller's opponents control can't be turned face up during their turn"


def cast_problem(state: Any, player: str, ch: Any) -> str | None:
    from app.rules import scripts

    if state.turn.active_player != player or not any(d.get("static") == FIRST_TURNS for d in scripts.definitions(ch).values()):
        return None
    tt = state.rules.turns_taken
    return None if (tt.get(player, 0) if tt else 1) > 3 else f"{ch.name or 'It'} can't be cast during your first, second, or third turns of the game"


def parse(body: str) -> Any:
    """scripts.parse_effects' part: "Switch the power and toughness of each of up to two target creatures until end of turn." (Invert: each
    target's own power and toughness switched, 613.4d, ruling 2018-10-05)."""
    if body.strip() != "Switch the power and toughness of each of up to two target creatures until end of turn.":
        return None
    from app.rules import selectors

    creature = selectors.parse("creature")
    return None if creature is None else ([{"do": "switch_pt", "who": "target:0"}], [{"what": creature.key(), "min": 0, "max": 2}], False)


def no_mana(ch: Any) -> bool:
    from app.rules import scripts

    return any(d.get("static") == NO_MANA for d in scripts.definitions(ch).values())
