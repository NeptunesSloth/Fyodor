"""-- if you do / instead (wave 111B) -- Star Trek one-off wordings, each read as the native wording that means the same.

* "When U.S.S. Enterprise-C enters or dies, you may discard your hand. If you do, draw a card for each card discarded this way."
  (U.S.S. Enterprise-C, Time-Tossed): the optional discard is the payment of 118.12 ("Discard your hand" can be paid with an
  empty hand: the Bomat Courier ruling, costs.py); the cards discarded this way are the ones the payment discarded
  (optional_payment records them: "draw that many cards", 608.2c / 701.9a).
* "Sacrifice another creature: Gowron gains trample until end of turn. If you sacrificed a Klingon this way, you draw a card and
  lose 1 life." (Gowron, Eager for Battle): only the ability's controller pays its cost (602.2b, 601.2h), so "you sacrificed a
  Klingon this way" is "a Klingon was sacrificed this way" (conditions ``cost_sacrifice_is``: the creature as it last existed on
  the battlefield, 608.2h / 112.7a; a changeling is a Klingon, 702.73a).
* Built from native parts (each explained where it is defined below): Salt Vampire, Support Mission, The Promise of Kahless (``parse``),
  Peace in Our Time, Sarek, Guinan (counter receipts, ``counted_111b``), Dominion Saboteur (copying.entry_counters), Cmdr. Troi
  (permissions.free_cast caster "target111b", copying._stack_objects "free_cast111b"), Dr. McCoy (regeneration_choices: ``healers`` / ``heal``).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

# The ability's own text (the card's name written ~) → the native wording it is read as.
_AS: dict[str, str] = {
    "When ~ enters or dies, you may discard your hand. If you do, draw a card for each card discarded this way.":
        "When ~ enters or dies, you may discard your hand. If you do, draw that many cards.",
    "Sacrifice another creature: ~ gains trample until end of turn. If you sacrificed a Klingon this way, you draw a card and lose 1 life.":
        "Sacrifice another creature: ~ gains trample until end of turn. If a Klingon was sacrificed this way, you draw a card and lose 1 life.",
    # Salt Vampire: the opponent exiles the card you chose (the same card from the same hand, to its owner's exile, 406.1), then draws (608.2c)
    "When ~ enters, look at target opponent's hand. You may choose a nonland card from it. If you do, that player exiles that card, then draws a card.":
        "When ~ enters, look at target opponent's hand. You may choose a nonland card from it. If you do, exile that card, then that player draws a card.",
}

# Dominion Saboteur: the copy (707.5, 614.1c, the choice as it enters: 614.12a) and, only when it is used, the copied permanent's counters, each kind and
# number, as additional counters it enters with (707.9e: an effect of the replacement; 122.6: counters put as it enters, so counter replacements apply)
_SABOTEUR = ("You may have ~ enter as a copy of any artifact or creature on the battlefield, except it isn't legendary. If you do, it enters with additional "
             "counters on it equal to the same number and kinds of counters the copied permanent has on it.")
_SABOTEUR_COPY = "You may have ~ enter as a copy of any artifact or creature on the battlefield, except it isn't legendary."
# Peace in Our Time: "that player may draw a card. If they do, they can't attack this turn and you put a peace counter on this enchantment." — the
# player whose turn it is chooses (the draw is theirs, 118.12); then none of the creatures they control can be declared as attackers this turn, those
# that come under their control later too (a rule for the player's creatures, not locked in: 611.2c, 508.1c), and the enchantment's controller puts
# the counter (122.6a).
_PEACE = "At the beginning of combat on each player's turn, that player may draw a card. If they do, they can't attack this turn and you put a peace counter on ~."
_PEACE_PARTS = ("At the beginning of combat on each player's turn, that player may draw a card.", "Creatures that player controls can't attack this turn.",
                "Put a peace counter on ~.")
# Sarek, Federation Ambassador: "for every five creature types" is the number of creature types among them divided by five, rounded down (107.1a);
# a changeling has every creature type (702.73a). "If you draw three or more cards this way": the cards actually drawn (ifyoudo100b's reading).
_SAREK = ("At the beginning of combat on your turn, draw a card for every five creature types among non-Borg creatures you control. If you draw three "
          "or more cards this way, put two +1/+1 counters on each creature you control.")
_SAREK_PARTS = ("At the beginning of combat on your turn, draw a card for each creature type among non-Borg creatures you control.",
                "Put two +1/+1 counters on each creature you control.")


# Two sentences read apart, their effects joined in order (608.2c): "that creature" is the creature the trigger is about, never the
# enchantment the sentence before put a counter on.
_JOINED: dict[str, tuple[str, str]] = {
    # Support Mission: the quest counter first, then "instead" judged with it there (608.2c; the counters as the instruction is carried out)
    "Whenever a creature you control enters, put a quest counter on ~. Put a +1/+1 counter on that creature. If ~ has five or more quest counters on it, "
    "instead put two +1/+1 counters on that creature.":
        ("Whenever a creature you control enters, put a quest counter on ~.",
         "Whenever a creature you control enters, put a +1/+1 counter on that creature. If ~ has five or more quest counters on it, instead put two +1/+1 "
         "counters on that creature."),
}


_KAHLESS = "You may sacrifice a Klingon or Warrior. If you do, return all other Klingon and Warrior creature cards from your graveyard to the battlefield."


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Effect bodies. The Promise of Kahless: "Klingon and Warrior creature cards" are the creature cards that are Klingons and those that are Warriors
    (as "Klingons and Warriors you control"); "all other" leaves out the card just sacrificed, now in the graveyard (400.7j; effects.return_card
    ``exclude``). A sacrificed token is no card to leave out (111.7)."""
    if body.strip() != _KAHLESS:
        return None
    from app.rules import scripts

    got = scripts.parse_effects("You may sacrifice a Klingon or Warrior. If you do, return all Klingon or Warrior creature cards from your graveyard to the battlefield.")
    if got is None or got[1] is not None or [e["do"] for e in got[0]] != ["optional_payment", "only_if", "return_card"] or not got[0][0].get("bind"):
        return None
    effects = [dict(e) for e in got[0]]
    effects[2]["exclude"] = effects[0]["bind"]
    return effects, None, got[2]


# Guinan, Ancient Advisor: "If you put two or more +1/+1 counters on creatures this way" counts the counters the instruction put, as the modified
# event put them (614.6: a doubling replacement's counters are the ones put), read from the placements the counter choke point records (counter_receipts).
_GUINAN = "{1}, {T}: Put a +1/+1 counter on each creature you control that entered this turn. If you put two or more +1/+1 counters on creatures this way, draw a card."
_GUINAN_PUT = "{1}, {T}: Put a +1/+1 counter on each creature you control that entered this turn."
_RECEIPT = "put111b"


def counted(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """``counted_111b``: binds ``bind`` (a flag, 608.2c) to whether the instruction recorded under ``receipt`` put at least ``n`` counters of ``kind``."""
    from app.rules import context, counter_receipts

    put = sum(p.amount for p in counter_receipts.placements(ctx, e["receipt"]) if p.kind == e["kind"] and p.amount > 0)
    context.bind_flag(ctx, e["bind"], put >= int(e["n"]))
    return True


PRIMITIVES = {"counted_111b": counted}


# Cmdr. Troi, Outgoing Empath: the target is the active player, if an opponent (targets "opponent_active110n", 500.1); that player may cast a spell from
# their own hand during the resolution without paying its mana cost (608.2g, 118.9; permissions.free_cast with caster "target111b": the question is
# theirs, asked whenever their hand holds a card, so the table never learns whether one was castable). "If they do, you copy that spell": the copy is
# yours (707.10, 707.10c: new targets may be chosen), put on the stack above it; "If they don't": nothing was cast (declined or abandoned), you draw.
_TROI = ("{T}: Target opponent whose turn it is may cast a spell from their hand without paying its mana cost. If they do, you copy that spell. You may "
         "choose new targets for the copy. If they don't, you draw a card.")
_TROI_NATIVE = "{T}: You may cast a spell from your hand without paying its mana cost."


def caster(plan: Any, ctx: dict[str, Any]) -> str:
    """The targeted opponent (Troi's one target); the ability's controller if there is none (never reached: with an illegal target the ability doesn't
    resolve, 608.2b)."""
    from app.rules import effects

    found = effects._players(plan, ctx, "target")
    return str(found[0]) if found else str(ctx["controller"])


# Dr. McCoy, Surly Surgeon: a destruction replacement (614.1a) offered with regeneration, shield counters and umbra armor (regeneration_choices: the
# affected creature's controller picks one when several apply, 616.1), for destruction by an effect (701.8) and by lethal or deathtouch damage
# (704.5g-h). Not a regeneration ("can't be regenerated" doesn't stop it). With its +1/+1 counters gone the creature may still die of 0 toughness
# (704.5f: not a destruction).
_MCCOY = ("If another creature you control with a +1/+1 counter on it would be destroyed, instead remove all +1/+1 counters from it and all damage "
          "already dealt to it is healed.")
HEAL = "heal111b:"


def healers(plan: Any, card: Any) -> list[Any]:
    """The Dr. McCoys whose replacement would apply to ``card`` being destroyed now: another creature its controller controls, with a +1/+1 counter."""
    from app.rules import scripts

    if card.counters.get("+1/+1", 0) <= 0 or not card.zone.endswith(":battlefield") or not plan.ch(card).is_creature:
        return []
    return [doc for doc in plan.state.cards.values()
            if doc.id != card.id and doc.controller == card.controller and doc.zone.endswith(":battlefield") and not plan.manual(doc)
            and any(d.get("static") == "heal_instead111b" for d in scripts.definitions(plan.ch(doc)).values())]


def heal(plan: Any, card: Any, actor: str | None) -> None:
    """Instead of being destroyed: all its +1/+1 counters removed and the damage marked on it removed (a deathtouch hit with it, 704.5h)."""
    from app.rules import counter_removal_results

    plan.note(f"{card.name}: Dr. McCoy's replacement is used instead of the destruction", [card.id], actor=actor)
    counter_removal_results.remove(plan, card.id, "+1/+1", card.counters.get("+1/+1", 0), by=card.controller)
    card = plan.state.cards[card.id]
    if card.damage:
        plan.do({"type": "set_damage", "card_ids": [card.id], "value": 0}, actor=actor)
    plan.rules.deathtouched = [c for c in plan.rules.deathtouched if c != card.id]


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    text = text.removeprefix("Federation — ")  # (an ability word, 207.2c: no rules meaning)
    if text == _TROI and ability.kind == "activated":
        native = scripts.define(replace(ability, text=_TROI_NATIVE), ch)
        if native is None or native.get("target") or [e["do"] for e in native["effects"]] != ["free_cast"] or native["effects"][0].get("zone") != "hand":
            return None
        cast = {**native["effects"][0], "caster": "target111b", "did": "troi0"}
        return {**native, "target": {"what": "opponent_active110n"},
                "effects": [cast, {"do": "only_if", "cond": {"succeeded": "troi0"}, "skip": 2}, {"do": "copy_spell", "who": "free_cast111b"},
                            {"do": "copy_new_targets", "optional": True}, {"do": "only_if", "cond": {"succeeded": "troi0", "negate": True}, "skip": 1},
                            {"do": "draw", "who": "you", "n": 1}]}
    if text == _MCCOY and ability.kind == "static":
        return {"kind": "static", "static": "heal_instead111b", "effects": []}  # (regeneration_choices reads it: healers / heal)
    if text == _SABOTEUR:
        native = scripts.define(replace(ability, text=_SABOTEUR_COPY), ch)
        if native is None or native.get("replacement") != "enter_as_copy" or native.get("enter_counters") or native.get("mimeo110c"):
            return None
        return {**native, "counters_of_copied111b": True}  # (copying.entry_counters)
    if text == _PEACE:
        native = scripts.define(replace(ability, text=_PEACE_PARTS[0]), ch)
        cant = scripts.parse_effects(_PEACE_PARTS[1], event_player=True)
        counter = scripts.parse_effects(_PEACE_PARTS[2])
        if native is None or cant is None or counter is None or cant[1] is not None or counter[1] is not None or cant[2] or counter[2]:
            return None
        pay, gate, draw = native["effects"] if len(native["effects"]) == 3 else (None, None, None)
        if pay is None or gate is None or draw is None or pay.get("do") != "optional_payment" or gate.get("skip") != 1 or draw.get("who") != "event_player":
            return None
        more = [*cant[0], *counter[0]]
        return {**native, "effects": [pay, {**gate, "skip": 1 + len(more)}, draw, *more]}
    if text == _SAREK:
        native = scripts.define(replace(ability, text=_SAREK_PARTS[0]), ch)
        counters = scripts.parse_effects(_SAREK_PARTS[1])
        if native is None or counters is None or counters[1] is not None or counters[2] or [e["do"] for e in native["effects"]] != ["draw"]:
            return None
        draw = native["effects"][0]
        name = "e0"
        return {**native, "effects": [{**draw, "n": {"every111b": [5, draw["n"]]}, "as": name},
                                      {"do": "only_if", "cond": {"value": {"this_way": "drawn", "of": None, "players": "you", "ref_count": name}, "op": ">=", "n": 3},
                                       "skip": len(counters[0])}, *counters[0]]}
    if text == _GUINAN:
        native = scripts.define(replace(ability, text=_GUINAN_PUT), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["add_counters"] or native["effects"][0].get("kind") != "+1/+1":
            return None
        return {**native, "effects": [{**native["effects"][0], "receipt": _RECEIPT},
                                      {"do": "counted_111b", "receipt": _RECEIPT, "kind": "+1/+1", "n": 2, "bind": "cond0"},
                                      {"do": "only_if", "cond": {"flag": "cond0"}, "skip": 1}, {"do": "draw", "who": "you", "n": 1}]}
    as_text = _AS.get(text)
    if as_text is not None:
        return scripts.define(replace(ability, text=as_text), ch)  # (the cost, when there is one, is unchanged)
    if (pair := _JOINED.get(text)) is not None:
        first, rest = (scripts.define(replace(ability, text=t), ch) for t in pair)
        if first is None or rest is None or {k: v for k, v in first.items() if k != "effects"} != {k: v for k, v in rest.items() if k != "effects"}:
            return None
        if any("as" in e or "bind" in e for e in first["effects"]):
            return None  # (nothing of the first sentence is named by the second)
        return {**rest, "effects": [*first["effects"], *rest["effects"]]}
    return None
