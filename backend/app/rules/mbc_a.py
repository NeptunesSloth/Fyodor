"""-- Mystery Booster Commander (wave MBC-A) -- the last lines of a group of Mystery Booster Commander Edition cards (set MBC, oval
eternal-legal stamp: Commander-legal, Scryfall 2026-11) and one older card whose card data reads oddly. CR 2026-09-25.

* Rulebreaker (Seluma, Valko, Grizzlegom, Maular, Tolabow, Whtz, The Everforger, The Unluckiest Planeswalker): "Rulebreaker — A deck with this
  commander can have …" / "… has no maximum deck size." / "If ~ is your commander, the color identity of … cards in your deck can include …" —
  deck construction only (100.2a, 903.4-903.5; like "~ can be your commander.", 903.3a): it does nothing in a game. The deck check honours
  it (app/decks/rulebreaker.py); here it is a ``deckbuilding`` static, as "~ can be your commander." is.
* Named tokens (Greensleeves' Giant Badger, Worzel's Scryb Sprites, Thomil's Lord of the Pit, Arzakon's Black Lotus, Feroz's Feroz's Ban,
  Nivea's Akroma, Angel of Wrath): "Create a <card name> token." is a token with that card's copiable values, mana cost included (each card's
  reminder text spells them out; 111.3, 707.2) — read as the named tokens of wave 49D (scripts.NAMED_TOKENS) are, from the card's Oracle text.
* An ability word written with a hyphen ("Pack tactics - Whenever this creature attacks, …", Werewolf Pack Leader in the 2026-11 card data;
  Oracle prints an em dash): the same triggered ability (207.2c: an ability word has no rules meaning).
* Werewolf Pack Leader: "{3}{G}: Until end of turn, this creature has base power and toughness 5/3, gains trample, and is a Werewolf." — one
  effect until end of turn: base power and toughness 5/3 (613.4b), trample (613.1f), its creature type becomes Werewolf (205.1a: "is a
  Werewolf" without "in addition to its other types" replaces its creature types, 613.1d).
* The Everforger: "Whenever you cast an artifact creature or Equipment spell, you may copy that spell. Do this only once each turn." — the
  spell is an artifact creature, or an Equipment (the union the selectors read for "artifact creature or Vehicle"); the copy of a permanent
  spell becomes a token (707.10f, 608.3f).
* Whtz, the Bibliophile: "This ability costs {3} less to activate if you had 200 or more cards in your starting deck." — the starting deck
  (103.2b): the cards the player began the game with in their library and command zone (the commander counts; 702.139b), as the companion
  check reads it (casting.companion_problem); a token or test object is no card of it.
* The Unluckiest Planeswalker: "+1: Add one mana of any color. When you spend this mana to cast an Aura spell this turn, create a 1/1 red
  Gremlin creature token." — the mana carries a "when spent" rider (106.6, mana_units: as Domri, Chaos Bringer's riot); "this turn": the
  rider does nothing once the turn it was made in is over (mana kept past the turn by another effect). "−3: Discard your hand, then draw
  cards equal to twice the number of Auras you control. For each Aura attached to you, attach it to an opponent of your choice." — for each
  Aura attached to its controller (303.4: an Aura enchanting a player), that player chooses one of their opponents and the Aura is attached
  to them (701.3a); one that can't legally enchant that player doesn't move (701.3b).
* Tsagan's "Max speed — Tsagan has deathtouch and …" is app/rules/speed.py's rewrite (a name keeps its capital).
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Def = dict[str, Any]

# -- Rulebreaker -------------------------------------------------------------------------------------------------------------------------------
_RULEBREAKER = re.compile(r"^Rulebreaker — (?:A deck with this commander (?:can have [^.]+|has no maximum deck size)\."
                          r"|If .+? is your commander, the color identity of [^.]+ cards in your deck can include [^.]+\.)$")

# -- named tokens: name -> (mana cost, colors, power, toughness, type line, the card's Oracle text) ----------------------------------------------
NAMED_TOKENS = {
    "Giant Badger": ("{1}{G}{G}", ["G"], "2", "2", "Token Creature — Badger", "Whenever this creature blocks, it gets +2/+2 until end of turn."),
    "Scryb Sprites": ("{G}", ["G"], "1", "1", "Token Creature — Faerie", "Flying"),
    "Lord of the Pit": ("{4}{B}{B}{B}", ["B"], "7", "7", "Token Creature — Demon",
                        "Flying, trample\nAt the beginning of your upkeep, sacrifice a creature other than this creature. If you can't, this creature "
                        "deals 7 damage to you."),
    "Black Lotus": ("{0}", [], None, None, "Token Artifact", "{T}, Sacrifice this artifact: Add three mana of any one color."),
    "Feroz's Ban": ("{6}", [], None, None, "Token Artifact", "Creature spells cost {2} more to cast."),
    "Akroma, Angel of Wrath": ("{5}{W}{W}{W}", ["W"], "6", "6", "Legendary Token Creature — Angel",
                               "Flying, first strike, vigilance, trample, haste, protection from black and from red"),
}
_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_CREATE = re.compile(r"^Create (?P<n>" + "|".join(_NUMBERS) + r") (?P<name>" + "|".join(re.escape(n) for n in NAMED_TOKENS) + r") tokens?\.$")


def named_token(name: str) -> dict[str, Any]:
    cost, colors, p, t, type_line, text = NAMED_TOKENS[name]
    return {"name": name, "power": p, "toughness": t, "colors": list(colors), "type_line": type_line, "text": text, "mana_cost": cost}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """"Create a Black Lotus token." / "Create ten Scryb Sprites tokens." (a named token, module docstring)."""
    m = _CREATE.fullmatch(body.strip())
    if m is None:
        return None
    return [{"do": "create_token", "who": "you", "n": _NUMBERS[m["n"]], "token": named_token(m["name"])}], None, False


# -- definitions -------------------------------------------------------------------------------------------------------------------------------
_HYPHEN_WORD = re.compile(r"^(?P<word>[A-Za-z' ]+?) - (?P<rest>(?:When|Whenever|At) .+)$")
_WEREWOLF = re.compile(r"^(?P<cost>[^:]+): Until end of turn, ~ has base power and toughness (?P<p>\d+)/(?P<t>\d+), gains (?P<kw>[a-z ]+), "
                       r"and is an? (?P<type>[A-Z][a-z]+)\.$")
EVERFORGER = "Whenever you cast an artifact creature or Equipment spell, you may copy that spell. Do this only once each turn."
UNLUCKY_PLUS = "+1: Add one mana of any color. When you spend this mana to cast an Aura spell this turn, create a 1/1 red Gremlin creature token."
UNLUCKY_MINUS = ("−3: Discard your hand, then draw cards equal to twice the number of Auras you control. For each Aura attached to you, attach it "
                 "to an opponent of your choice.")


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    text = ability.text
    if ability.kind == "static" and _RULEBREAKER.fullmatch(text):
        return {"kind": "static", "static": "deckbuilding", "effects": []}  # (100.2a, 903.4-903.5: deck construction only)
    if ability.kind == "static" and (hm := _HYPHEN_WORD.fullmatch(text)) is not None and hm["word"].lower() in scripts.ABILITY_WORDS:
        return scripts.define(replace(ability, kind="triggered", text=f"{hm['word']} — {hm['rest']}"), ch)
    if ability.kind in ("loyalty", "activated") and ": " in text and _CREATE.fullmatch(text.split(": ", 1)[1]) is not None:
        # (read from the printed words: the token's name may hold the card's own short name, "Feroz's Ban" on Feroz, Ulgrotha's Warden)
        base = scripts.define(replace(ability, text=f"{text.split(': ', 1)[0]}: Create a Treasure token."), ch)
        if base is None or [e.get("do") for e in base["effects"]] != ["create_token"]:
            return None
        return {**base, "effects": parse(text.split(": ", 1)[1])[0]}  # type: ignore[index]
    own = scripts.self_text(text, ch.name or "")
    if ability.kind == "activated" and (wm := _WEREWOLF.fullmatch(own)) is not None:
        base = scripts.define(replace(ability, text=f"{wm['cost']}: Until end of turn, ~ has base power and toughness {wm['p']}/{wm['t']}."), ch)
        if base is None or [e.get("do") for e in base["effects"]] != ["become"]:
            return None
        become = {**base["effects"][0], "keywords": [wm["kw"]], "creature_types": [wm["type"]], "duration": "end_of_turn"}
        return {**base, "effects": [become]}
    if ability.kind == "triggered" and own == EVERFORGER:
        return _everforger(ability, ch)
    if ability.kind == "loyalty" and own == UNLUCKY_PLUS:
        import json

        from app.rules import mana_units

        base = scripts.define(replace(ability, text="+1: Add one mana of any color."), ch)
        rider = mana_units.rider("When you spend this mana to cast an Aura spell, create a 1/1 red Gremlin creature token.")
        if base is None or rider is None:
            return None
        return {**base, "effects": [*base["effects"], {"do": "turn_rider_mbca", "rider": json.loads(rider), "note": "Gremlin for an Aura spell this turn"}]}
    if ability.kind == "loyalty" and own == UNLUCKY_MINUS:
        base = scripts.define(replace(ability, text="−3: Discard your hand, then draw cards equal to twice the number of Auras you control."), ch)
        if base is None or [e.get("do") for e in base["effects"]] != ["discard", "draw"]:
            return None
        return {**base, "effects": [*base["effects"], {"do": "auras_to_opponents_mbca"}]}
    return None


def _everforger(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts, selectors

    base = scripts.define(replace(ability, text=EVERFORGER.replace("Equipment", "Vehicle")), ch)
    spell = ((base or {}).get("cond") or {}).get("spell")
    if base is None or spell is None or [e.get("do") for e in base["effects"]] != ["copy_spell"]:
        return None
    sel = selectors.from_key(spell)
    if sel.subtypes != ("Vehicle",) or not sel.union:
        return None
    return {**base, "cond": {**base["cond"], "spell": replace(sel, subtypes=("Equipment",)).key()}}


# -- Whtz: the starting deck ---------------------------------------------------------------------------------------------------------------------
_STARTING = re.compile(r"^you had (?P<n>\d+) or more cards in your starting deck$")


def condition(text: str) -> dict[str, Any] | None:
    """"you had 200 or more cards in your starting deck" (Whtz, the Bibliophile)."""
    m = _STARTING.fullmatch(text.strip())
    return {"mbca": "starting_deck", "n": int(m["n"])} if m else None


def starting_deck(state: Any, player: str) -> int:
    """103.2b: the cards ``player`` began the game with in their library and command zone (702.139b: the commander counts; every merged
    component is a card of it, a token or a test object is none) — the cards casting.companion_problem reads as the starting deck."""
    return sum(1 for shell in state.cards.values() if not shell.ability
               for part in (shell.merged if shell.merged else [shell])
               if part.owner == player and part.origin in ("library", "command") and not (part.is_token or part.test_object))


def holds(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    if cond.get("mbca") == "starting_deck":
        return starting_deck(plan.state, ctx["controller"]) >= int(cond["n"])
    return False


# -- The Unluckiest Planeswalker ------------------------------------------------------------------------------------------------------------------
def turn_rider(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The mana just added carries the rider (106.6), good for this turn only: its effects start with a check of the turn it was made in."""
    from app.rules import mana_units

    rider = dict(e["rider"])
    effects = list(rider.get("effects") or [])
    rider["effects"] = [{"do": "same_turn_mbca", "turn": plan.state.turn.number, "skip": len(effects)}, *effects]
    return mana_units.restrict(plan, ctx, {"only": None, "riders": [rider], "note": e.get("note", "")})


def same_turn(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    if plan.state.turn.number != int(e["turn"]):
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
    return True


def auras_to_opponents(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """For each Aura attached to its controller, attach it to an opponent of their choice (701.3a; 701.3b: one it can't enchant stays)."""
    me = ctx["controller"]
    auras = [c.id for c in plan.state.cards.values()
             if c.zone.endswith(":battlefield") and c.attached_player == me and "Aura" in plan.ch(c).subtypes]
    return _next_aura(plan, ctx, auras)


def _next_aura(plan: Plan, ctx: dict[str, Any], pending: list[str]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import attachments, effects
    from app.rules.plan import decide

    me = ctx["controller"]
    while pending:
        aura = pending.pop(0)
        card = plan.state.cards.get(aura)
        if card is None or card.attached_player != me or not card.zone.endswith(":battlefield"):
            continue
        opponents = effects._players(plan, {"controller": me}, "each_opponent")
        if not opponents:
            continue
        if len(opponents) == 1:
            attachments.attach(plan, aura, opponents[0], me)
            continue
        decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name') or 'Attach'}: attach {card.name or 'the Aura'} to which opponent?",
               options=[DecisionOption(id=p, label=plan.name(p)) for p in opponents],
               resume={"step": "auras_to_opponents_mbca", "ctx": ctx, "aura": aura, "pending": pending}, source=card)
        return False
    return True


def resume_aura(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import attachments
    from app.rules.effects import continue_effects

    ctx = d.resume["ctx"]
    if chosen:
        attachments.attach(plan, d.resume["aura"], chosen[0], d.player)
    if _next_aura(plan, ctx, list(d.resume["pending"])):
        continue_effects(plan, ctx)


PRIMITIVES: dict[str, Any] = {"turn_rider_mbca": turn_rider, "same_turn_mbca": same_turn, "auras_to_opponents_mbca": auras_to_opponents}
RESUME: dict[str, Any] = {"auras_to_opponents_mbca": resume_aura}
