"""-- turn state (wave 100H) -- exact Oracle wordings of "this turn" history conditions and ability-word abilities, read as an equivalent native
wording or built from native parts (scripts.define / parse_effects) plus existing instructions. Researched against CR 2026-09-25; ability words
have no rules meaning (207.2c). Any other wording stays unsupported (refuse rather than guess).

* Akoum Hellkite: "If that land is a Mountain, ~ deals 2 damage instead." — the land the trigger is about (its event object, as it is or last
  existed: 608.2h), not the target; the condition is judged once, before the damage (608.2c).
* Moon-Circuit Hacker: the discard is skipped when ~ entered this turn (ninjutsu included: it entered, though it never attacked, 702.49c).
* Motivated Pony: "those creatures" are the attacking creatures it just pumped (608.2c), all as it resolves; a Food is any Food artifact (ruling).
* Wedding Announcement: the counter, then draw or Human by the creatures you attacked with this turn (508.1; ruling 2021-11-19), then transform.
* Composer of Spring: "If you control six or more enchantments, instead …" is checked as it resolves (608.2c), either put being optional.
* Kraul Harpooner: the target (up to one) is chosen as it goes on the stack, the fight only on resolution if you choose (rulings 2018-10-05).
* Oriss, Samite Guardian: both restrictions apply to the target player this turn (cast_limit, can't attack).
* Stalked Researcher: either eerie event (603.2c) lets it attack this turn as though it didn't have defender.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

_MOUNTAIN = 'sel:{"subtypes":["Mountain"]}'
Def = dict[str, Any]

# text (after scripts.self_text) -> the native wording it means
_AS: dict[str, str] = {
    "Whenever ~ deals combat damage to a player, if you have no cards in hand, that player discards cards equal to the damage.":
        "Whenever ~ deals combat damage to a player, if you have no cards in hand, that player discards that many cards.",  # (Jagged Poppet, 120.3)
    # Vengevine: only the second creature spell of the turn triggers it, from your graveyard (rulings 2020-08-07)
    "Whenever you cast a spell, if it's the second creature spell you cast this turn, you may return this card from your graveyard to the battlefield.":
        "Whenever you cast your second creature spell each turn, you may return this card from your graveyard to the battlefield.",
    # Sawblade Skinripper: "that much" is the number of permanents you sacrificed this turn (701.21a)
    "At the beginning of your end step, if you sacrificed one or more permanents this turn, ~ deals that much damage to any target.":
        "At the beginning of your end step, if you sacrificed one or more permanents this turn, ~ deals damage to any target equal to the number of "
        "permanents you sacrificed this turn.",
    # The Rollercrusher Ride: delirium judged as the damage would be dealt (614.1)
    "If a source you control would deal noncombat damage to a permanent or player while there are four or more card types among cards in your "
    "graveyard, it deals double that damage instead.":
        "As long as there are four or more card types among cards in your graveyard, if a source you control would deal noncombat damage to a "
        "permanent or player, it deals double that damage instead.",
    # Sage of the Skies: "this spell" is the spell the cast trigger is about (707.10, 707.10f: a copy of a permanent spell becomes a token)
    "When you cast this spell, if you've cast another spell this turn, copy this spell.":
        "When you cast this spell, if you've cast another spell this turn, copy it.",
    # The Lunar Whale: to play a card is to play it as a land or cast it as a spell (305.1, 601)
    "As long as ~ attacked this turn, you may play the top card of your library.":
        "As long as ~ attacked this turn, you may play lands and cast spells from the top of your library.",
}


# instruction bodies (scripts.parse_effects) -> the native wording they mean
SAME: dict[str, str] = {
    # Undercity Upheaval (undergrowth): a divided total is counted as the spell is cast (601.2d), as the card says
    "Distribute X +1/+1 counters among any number of target creatures you control, where X is the number of creature cards in your graveyard as you cast "
    "this spell. Creatures you control gain vigilance until end of turn.":
        "Distribute X +1/+1 counters among any number of target creatures you control, where X is the number of creature cards in your graveyard. "
        "Creatures you control gain vigilance until end of turn.",
}


def _dos(d: Def) -> list[Any]:
    return [e.get("do") for e in d["effects"]]


def _akoum(d: Def) -> Def | None:
    if _dos(d) != ["damage"]:
        return None
    hit = d["effects"][0]
    return {**d, "effects": [{"do": "only_if", "cond": {"not": {"object": "event", "is": _MOUNTAIN}}, "skip": 1, "bind": "cond0"}, hit,
                             {"do": "only_if", "cond": {"flag": "cond0", "negate": True}, "skip": 1}, {**hit, "n": 2}]}


def _hacker(d: Def) -> Def | None:
    if _dos(d) != ["draw", "only_if", "discard"]:
        return None
    draw, gate, discard = d["effects"]
    return {**d, "effects": [draw, {**gate, "skip": 2}, {"do": "only_if", "cond": {"not": {"history": "entered_self"}}, "skip": 1}, discard]}


def _pony(d: Def, food: Def) -> Def | None:
    if _dos(d) != ["pump"] or _dos(food) != ["only_if", "untap"]:
        return None
    pump = d["effects"][0]
    return {**d, "effects": [pump, {**food["effects"][0], "skip": 2}, food["effects"][1], {**pump, "p": 2, "t": 2}]}


def _wedding(d: Def, then: Def) -> Def | None:
    if _dos(d) != ["add_counters", "only_if", "draw", "only_if", "create_token"] or _dos(then) != ["add_counters", "only_if", "transform"]:
        return None
    return {**then, "effects": [then["effects"][0], *d["effects"][1:], *then["effects"][1:]]}


def _composer(land: Def, big: Def) -> Def | None:
    if _dos(land) != ["put_from_hand"] or _dos(big) != ["only_if", "put_from_hand"]:
        return None
    gate, put = big["effects"]
    return {**land, "effects": [{**gate, "bind": "cond0"}, put, {"do": "only_if", "cond": {"flag": "cond0", "negate": True}, "skip": 1}, *land["effects"]]}


def _harpooner(pump: Def, fight: Def) -> Def | None:
    if _dos(pump) != ["pump"] or _dos(fight) != ["fight"] or not fight.get("optional"):
        return None
    return {**fight, "optional": False, "effects": [*pump["effects"], {"do": "may_rest", "skip": 1, "label": "Fight that creature"}, *fight["effects"]]}


def _oriss(cast: Def, attack: Def) -> Def | None:
    if _dos(cast) != ["cast_limit"] or _dos(attack) != ["restrict"]:
        return None
    return {**cast, "effects": [*cast["effects"], *attack["effects"]]}


def _researcher(d: Def, alone: Def) -> Def | None:
    if _dos(d) != ["pump"] or _dos(alone) != ["restrict"] or d["cond"].get("event") != "either":
        return None
    return {**d, "effects": alone["effects"]}


def _soloist(d: Def) -> Def | None:
    """Sizzling Soloist: the second resolution this turn also makes the targeted creature attack in its controller's next combat (if able)."""
    if _dos(d) != ["restrict", "only_if", "draw"]:
        return None
    return {**d, "effects": [*d["effects"][:2], {"do": "attack_window", "who": "target", "window": "next_combat"}]}


_RESOLVED = {"history": "resolution"}


def _treasurer(treasure: Def, pay: Def) -> Def | None:
    """Rose Room Treasurer: a Treasure on the first and second resolution this turn; otherwise the optional {X} and its reflexive damage (603.12)."""
    if _dos(treasure) != ["only_if", "create_token"] or _dos(pay) != ["optional_payment", "reflexive"]:
        return None
    first = {"do": "only_if", "cond": {"any": [{**_RESOLVED, "n": 1}, {**_RESOLVED, "n": 2}]}, "skip": 1, "bind": "cond0"}
    return {**pay, "effects": [first, treasure["effects"][1], {"do": "only_if", "cond": {"flag": "cond0", "negate": True}, "skip": 2}, *pay["effects"]]}


def _ashling(counter: Def, blast: Def) -> Def | None:
    """Ashling the Pilgrim: on the third resolution this turn exactly (history.resolution_holds), all its +1/+1 counters come off and it deals that
    many damage to each creature and each player at once (120.2)."""
    if _dos(counter) != ["add_counters"] or _dos(blast) != ["remove_counters", "damage", "damage"]:
        return None
    remove, *hits = blast["effects"]
    remove = {**remove, "n": {"counters": "+1/+1", "on": "self"}, "bind": "removed_counters"}  # ("that much": the counters removed, as Give // Take reads)
    hits = [{**h, "n": {"ref_amount": "removed_counters"}} for h in hits]
    return {**counter, "effects": [*counter["effects"], {"do": "only_if", "cond": {**_RESOLVED, "n": 3}, "skip": 3}, remove, *hits]}


def _ronin(counters: Def, grant: Def) -> Def | None:
    """The Last Ronin III: the delayed "attacks alone this turn" ability (506.5) puts the counters, then grants the keywords until end of turn."""
    if _dos(counters) != ["delayed", "deferred:add_counters"] or _dos(grant) != ["delayed", "deferred:grant"]:
        return None
    watch, add = counters["effects"]
    return {**counters, "effects": [{**watch, "n": 2}, add, grant["effects"][1]]}


def _guardian(d: Def) -> Def | None:
    """Council Guardian: protection from each color with the most votes or tied for most (701.38), for the rest of the game (611.2a)."""
    return {**d, "effects": [d["effects"][0], {"do": "council100h"}]} if _dos(d) == ["vote", "grant"] else None


def _taigam(d: Def) -> Def | None:
    """Taigam, Ojutai Master: the instant or sorcery spell cast from your hand gains rebound (702.88a), if Taigam attacked this turn (603.4)."""
    from app.rules import selectors

    if _dos(d) != ["draw"] or d.get("trigger") != "cast_you":
        return None
    attacked = {"history": "self_attacked", "object": "self"}  # (508.1: declared as an attacker this turn)
    spell = selectors.Selector(zones=("stack",), types=("Instant", "Sorcery")).key()
    return {**{k: v for k, v in d.items() if k != "filter"}, "trigger": "event", "if": attacked,
            "cond": {"event": "cast", "subject": "player", "player": "you", "spell": spell, "from": "hand", "from_owner": "you"},
            "effects": [{"do": "only_if", "cond": attacked, "skip": 1}, {"do": "spell_rider", "who": "event_spell", "keyword": "rebound"}]}


def _frodo(d: Def) -> Def | None:
    """Frodo, Adventurous Hobbit: after the temptation, a draw if Frodo is your Ring-bearer and the Ring tempted you twice or more (701.54)."""
    if _dos(d) != ["only_if", "ring_tempts"]:
        return None
    return {**d, "effects": [*d["effects"], {"do": "only_if", "cond": {"frodo100h": True}, "skip": 1}, {"do": "draw", "who": "you", "n": 1}]}


def _churn(d: Def) -> Def | None:
    """Riverchurn Monument: each target player mills as many cards as are in their own graveyard, every count read before any card moves (608.2h)."""
    from app.rules import sized_damage

    n = sized_damage.per_player("the number of cards in their graveyard")
    return {**d, "effects": [{**d["effects"][0], "n": n}]} if _dos(d) == ["mill"] and n is not None else None


def _destiny(d: Def) -> Def | None:
    """Angel of Destiny: each player it was declared attacking this turn (508.1; not a planeswalker's controller) loses the game (104.3e)."""
    return {**d, "effects": [d["effects"][0], {"do": "destiny100h"}]} if _dos(d) == ["only_if", "win_game"] else None


def _retriever(d: Def) -> Def | None:
    """Glissa's Retriever (corrupted): the reflexive ability's "up to X" is counted as it is put on the stack, with its targets (603.12, 601.2c;
    ruling 2023-02-04): the opponents with three or more poison counters then."""
    from app.rules import scripts

    count = scripts.parse_effects("Draw X cards, where X is the number of opponents who have three or more poison counters.")
    if _dos(d) != ["exile", "reflexive"] or count is None or len(d["effects"][1]["ability"].get("targets") or []) != 1:
        return None
    ability = d["effects"][1]["ability"]
    return {**d, "effects": [d["effects"][0], {**d["effects"][1], "ability": {**ability, "targets": [{**ability["targets"][0], "x_value": count[0][0]["n"]}]}}]}


def _jays(d: Def) -> Def | None:
    """Messenger Jays (council's dilemma): one discard for each card the quill votes actually drew (121.2a: a replaced draw draws none)."""
    if _dos(d) != ["vote", "vote_repeat", "add_counters", "vote_repeat", "draw"]:
        return None
    return {**d, "effects": [*d["effects"][:4], {**d["effects"][4], "as": "jays100h"},
                             {"do": "discard", "who": "you", "n": {"this_way": "drawn", "of": None, "ref_count": "jays100h"}}]}


_EGG = ('Defender\nWhen this creature dies, create a 2/2 red Dragon creature token with flying and "{R}: This creature gets +1/+0 until end of '
        'turn."')


def _nesting(d: Def) -> Def | None:
    """Nesting Dragon: the Egg's own dies trigger makes the Dragon with its firebreathing (the inner quote is that token's ability, 111.4)."""
    if _dos(d) != ["create_token"] or d["effects"][0]["token"].get("name") != "Dragon Egg":
        return None
    return {**d, "effects": [{**d["effects"][0], "token": {**d["effects"][0]["token"], "text": _EGG}}]}


_GRAVEYARD_PLAY = {"any": [{"history": "cast", "who": "you", "sel": 'sel:{"zones":["stack"]}', "n": 1, "op": ">=", "from": "graveyard"},
                           {"history": "facts", "kind": "gy_ability", "who": "you", "n": 1}]}


def _drudge(d: Def) -> Def | None:
    """Laboratory Drudge: "draw a card if …" is checked only as it resolves (no intervening "if", 603.4): a spell you cast from any graveyard (601.2i)
    or an ability you activated of a card in a graveyard this turn (602.2; casting.py records the source's zone before its cost moved it)."""
    return {**d, "effects": [{"do": "only_if", "cond": _GRAVEYARD_PLAY, "skip": 1}, *d["effects"]]} if _dos(d) == ["draw"] else None


_CREATURE_CARDS = 'sel:{"card":true,"types":["Creature"],"zone_owner":"you","zones":["graveyard"]}'


def _spider(d: Def) -> Def | None:
    """Hatchery Spider (undergrowth): X is the creature cards in your graveyard as the cast trigger resolves, for the reveal and the mana value cap
    (the reveal moves nothing: one count)."""
    from app.rules import selectors

    if _dos(d) != ["look_top", "pick_looked", "rest_looked"]:
        return None
    look, pick, rest = d["effects"]
    sel = selectors.from_key(pick["sel"])
    if sel.compare != (("mv", "<=", 3),):
        return None
    capped = replace(sel, compare=(("mv", "<=", selectors.COUNT_STAT + _CREATURE_CARDS),)).key()
    return {**d, "effects": [{**look, "n": {"count": _CREATURE_CARDS}}, {**pick, "sel": capped}, rest]}


def _shade(d: Def) -> Def | None:
    """Skyclave Shade: from your graveyard, on your turn, the card (that object, 400.7) may be cast from there this turn (normal timing and costs,
    kicker included: rulings 2020-09-25)."""
    if _dos(d) != ["only_if", "return_card"] or d["effects"][1].get("who") != "self_gy":
        return None
    return {**d, "gy_watch": True, "effects": [d["effects"][0], {"do": "shade100h", "who": "self_gy"}]}


def _basri(d: Def) -> Def | None:
    """Basri Ket −2: the turn-long delayed ability (603.7c) triggers once for each declaration with nontoken attackers (one or more: 603.2c), and
    makes that many Soldiers attacking (508.4: they were never declared, so they don't trigger it)."""
    if _dos(d) != ["delayed", "deferred:create_attacking"]:
        return None
    watch, make = d["effects"]
    cond = {"event": "attack", "subject": "sel", "sel": 'sel:{"token":false,"types":["Creature"]}', "aggregate": True}
    return {**d, "effects": [{**watch, "when": {**watch["when"], "cond": cond, "text": "one or more nontoken creatures attack"}},
                             {**make, "n": {"event_amount": 1}}]}


def _goliath(d: Def) -> Def | None:
    """Goliath Hatchery (corrupted): the cards drawn are the chosen creature's total toxic value as it resolves (702.164b)."""
    if _dos(d) != ["only_if", "player_chooses", "draw"]:
        return None
    return {**d, "effects": [*d["effects"][:2], {"do": "toxic_draw100h", "who": "ref:" + d["effects"][1]["as"]}]}


def _resolve(d: Def) -> Def | None:
    """Warrior's Resolve: a creature you control with a +1/+1 counter on it now that was declared as an attacker this turn (508.1, 400.7)."""
    from app.rules import selectors

    if _dos(d) != ["only_if", "draw"] or not d.get("if"):
        return None
    sel = selectors.from_key(d["if"]["value"]["count"])
    cond = {**d["if"], "value": {"count": replace(sel, extras=(*sel.extras, "attacked_this_turn")).key()}}
    return {**d, "if": cond, "effects": [{**d["effects"][0], "cond": cond}, d["effects"][1]]}


_MODIFIED_DIED = {"history": "departed", "sel": 'sel:{"types":["Creature"]}', "n": 1, "op": ">=", "died": True, "who": "you", "modified100h": True}


def _chirography(d: Def) -> Def | None:
    """Intermediate Chirography: the creature that died under your control this turn was modified as it last existed (700.9, 603.10a)."""
    if _dos(d) != ["only_if", "create_token"] or not d.get("if"):
        return None
    return {**d, "if": _MODIFIED_DIED, "effects": [{**d["effects"][0], "cond": _MODIFIED_DIED}, d["effects"][1]]}


_HACK = "Whenever ~ deals combat damage to a player, you may draw a card. If you do, discard a card"
_PONY = "Whenever ~ attacks, attacking creatures get +1/+1 until end of turn."
_WED = "At the beginning of your end step, put an invitation counter on ~."
_ENCH = "Whenever an enchantment you control enters, "
_PUT = "put a {} card from your hand onto the battlefield tapped."
_KRAUL = "When ~ enters, "
_ORISS = "Discard another card named Oriss, Samite Guardian: "
_EERIE = "Whenever an enchantment you control enters and whenever you fully unlock a Room, "
_DEFENDER = "~ can attack this turn as though it didn't have defender."
_SOLO = "Whenever another creature you control enters, "
# text (after scripts.self_text) -> (the native wordings read, how the definition is built from their definitions)
_BUILD: dict[str, tuple[tuple[str, ...], Callable[..., Def | None]]] = {
    "Whenever a land you control enters, ~ deals 1 damage to any target. If that land is a Mountain, ~ deals 2 damage instead.":
        (("Whenever a land you control enters, ~ deals 1 damage to any target.",), _akoum),
    f"{_HACK} unless ~ entered this turn.": ((f"{_HACK}.",), _hacker),
    f"{_PONY} If a Food entered the battlefield under your control this turn, untap those creatures and they get an additional +2/+2 until end of turn.":
        ((_PONY, "Whenever ~ attacks, if a Food entered the battlefield under your control this turn, untap all attacking creatures."), _pony),
    f"{_WED} If you attacked with two or more creatures this turn, draw a card. Otherwise, create a 1/1 white Human creature token. Then if ~ has three "
    "or more invitation counters on it, transform it.":
        ((f"{_WED} If you attacked with two or more creatures this turn, draw a card. Otherwise, create a 1/1 white Human creature token.",
          f"{_WED} Then if ~ has three or more invitation counters on it, transform it."), _wedding),
    f"{_ENCH}you may {_PUT.format('land')} If you control six or more enchantments, instead you may {_PUT.format('creature or land')}":
        ((f"{_ENCH}you may {_PUT.format('land')}", f"{_ENCH}if you control six or more enchantments, you may {_PUT.format('creature or land')}"), _composer),
    f"{_KRAUL}choose up to one target creature you don't control with flying. ~ gets +X/+0 until end of turn, where X is the number of creature cards in "
    "your graveyard, then you may have ~ fight that creature.":
        ((f"{_KRAUL}~ gets +X/+0 until end of turn, where X is the number of creature cards in your graveyard.",
          f"{_KRAUL}you may have ~ fight up to one target creature with flying you don't control."), _harpooner),
    f"{_ORISS}Target player can't cast spells this turn, and creatures that player controls can't attack this turn.":
        ((f"{_ORISS}Target player can't cast spells this turn.", f"{_ORISS}Creatures target player controls can't attack this turn."), _oriss),
    f"{_EERIE}{_DEFENDER}": ((f"{_EERIE}~ gets +1/+0 until end of turn.", f"Whenever you fully unlock a Room, {_DEFENDER}"), _researcher),
    f"{_SOLO}target creature an opponent controls can't block this turn. If this is the second time this ability has resolved this turn, that creature "
    "attacks during its controller's next combat phase if able.":
        ((f"{_SOLO}target creature an opponent controls can't block this turn. If this is the second time this ability has resolved this turn, draw a card.",),
         _soloist),
    f"{_SOLO}create a Treasure token if this is the first or second time this ability has resolved this turn. Otherwise, you may pay {{X}}. When you do, "
    "~ deals X damage to any target.":
        ((f"{_SOLO}if this is the second time this ability has resolved this turn, create a Treasure token.",
          f"{_SOLO}you may pay {{X}}. When you do, ~ deals X damage to any target."), _treasurer),
    "{1}{R}: Put a +1/+1 counter on ~. If this is the third time this ability has resolved this turn, remove all +1/+1 counters from ~, and it deals that "
    "much damage to each creature and each player.":
        (("{1}{R}: Put a +1/+1 counter on ~.", "{1}{R}: Remove all +1/+1 counters from ~. ~ deals that much damage to each creature and each player."),
         _ashling),
    "III — Whenever a creature you control attacks alone this turn, put three +1/+1 counters on it. It gains trample, lifelink, and indestructible until "
    "end of turn.":
        (("III — Whenever a creature you control attacks alone this turn, put three +1/+1 counters on it.",
          "III — Whenever a creature you control attacks this turn, it gains trample, lifelink, and indestructible until end of turn."), _ronin),
    # Linessa, Zephyr Mage (grandeur): "repeats this process" — the same player chooses and returns one of each kind, in that order (608.2c)
    "Discard another card named Linessa, Zephyr Mage: Target player returns a creature they control to its owner's hand, then repeats this process for "
    "an artifact, an enchantment, and a land.":
        (("Discard another card named Linessa, Zephyr Mage: Target player returns a creature they control to its owner's hand. "
          + " ".join(f"Then that player returns {k} they control to its owner's hand." for k in ("an artifact", "an enchantment", "a land")),),
         lambda d: d if _dos(d) == ["player_chooses", "bounce"] * 4 else None),
    "When ~ enters, starting with you, each player votes for blue, black, red, or green. ~ gains protection from each color with the most votes or tied "
    "for most votes.":
        (("When ~ enters, starting with you, each player votes for blue, black, red, or green. ~ gains protection from blue until end of turn.",), _guardian),
    "Whenever you cast an instant or sorcery spell from your hand, if ~ attacked this turn, that spell gains rebound.":
        (("Whenever you cast an instant or sorcery spell, draw a card.",), _taigam),
    "Whenever ~ attacks, if you gained 3 or more life this turn, the Ring tempts you. Then if ~ is your Ring-bearer and the Ring has tempted you two or "
    "more times this game, draw a card.": (("Whenever ~ attacks, if you gained 3 or more life this turn, the Ring tempts you.",), _frodo),
    "{2}{U}{U}, {T}: Any number of target players each mill cards equal to the number of cards in their graveyard.":
        (("Exhaust — {2}{U}{U}, {T}: Any number of target players each mill two cards.",), _churn),
    "When ~ enters, starting with you, each player votes for feather or quill. Put a +1/+1 counter on ~ for each feather vote and draw a card for each "
    "quill vote. For each card drawn this way, discard a card.":
        (("When ~ enters, starting with you, each player votes for feather or quill. Put a +1/+1 counter on ~ for each feather vote and draw a card "
          "for each quill vote.",), _jays),
    "Whenever a land you control enters, create a 0/2 red Dragon Egg creature token with defender and \"When this token dies, create a 2/2 red Dragon "
    "creature token with flying and '{R}: This token gets +1/+0 until end of turn.'\"":
        (("Whenever a land you control enters, create a 0/2 red Dragon Egg creature token with defender and \"When this token dies, create a 2/2 red "
          "Dragon creature token with flying.\"",), _nesting),
    "When you cast this spell, reveal the top X cards of your library, where X is the number of creature cards in your graveyard. You may put a green "
    "permanent card with mana value X or less from among them onto the battlefield. Put the rest on the bottom of your library in a random order.":
        (("When you cast this spell, reveal the top five cards of your library. You may put a green permanent card with mana value 3 or less from among "
          "them onto the battlefield. Put the rest on the bottom of your library in a random order.",), _spider),
    "Whenever a land you control enters, if this card is in your graveyard and it's your turn, you may cast it from your graveyard this turn.":
        (("Whenever a land you control enters, if this card is in your graveyard and it's your turn, return this card from your graveyard to your "
          "hand.",), _shade),
    "−2: Whenever one or more nontoken creatures attack this turn, create that many 1/1 white Soldier creature tokens that are tapped and attacking.":
        (("−2: Whenever you attack this turn, create a 1/1 white Soldier creature token that's tapped and attacking.",), _basri),
    "If you attacked this turn, you may have ~ enter as a copy of any creature on the battlefield.":
        (("You may have ~ enter as a copy of any creature on the battlefield.",),
         lambda d: {**d, "raid100h": True} if d.get("replacement") == "enter_as_copy" else None),  # (Protean Raider: copying.entering reads it)
    "At the beginning of your upkeep, if an opponent has three or more poison counters, choose a creature you control, then draw cards equal to its "
    "total toxic value.":
        (("At the beginning of your upkeep, if an opponent has three or more poison counters, choose a creature you control, then draw cards equal to "
          "its power.",), _goliath),
    "At the beginning of your end step, if you control a creature with a +1/+1 counter on it that attacked this turn, draw a card.":
        (("At the beginning of your end step, if you control a creature with a +1/+1 counter on it, draw a card.",), _resolve),
    "At the beginning of each end step, draw a card if you've cast a spell from a graveyard or activated an ability of a card in a graveyard this turn.":
        (("At the beginning of each end step, draw a card.",), _drudge),
    "At the beginning of each end step, if a modified creature died under your control this turn, create a 2/1 white and black Inkling creature "
    "token with flying.":
        (("At the beginning of each end step, if a creature died under your control this turn, create a 2/1 white and black Inkling creature token "
          "with flying.",), _chirography),
    "When ~ dies, exile it. When you do, return up to X target cards from your graveyard to your hand, where X is the number of opponents who have "
    "three or more poison counters.":
        (("When ~ dies, exile it. When you do, return up to two target cards from your graveyard to your hand.",), _retriever),
    "At the beginning of your end step, if you have at least 15 life more than your starting life total, each player ~ attacked this turn loses the game.":
        (("At the beginning of your end step, if you have at least 15 life more than your starting life total, you win the game.",), _destiny),
}


def _descent(d: Def) -> Def | None:
    """Squirming Emergence (fathomless descent): the mana value is compared with the permanent cards in your graveyard, counted as the target is
    chosen and again as it resolves (608.2b) — the card itself is on the stack then."""
    from app.rules import selectors

    if _dos(d) != ["return_card"] or not str((d.get("target") or {}).get("what", "")).startswith(selectors.PREFIX):
        return None
    sel = selectors.from_key(d["target"]["what"])
    counted = replace(sel, not_types=())
    return {**d, "target": {**d["target"], "what": replace(sel, compare=(("mv", "<=", selectors.COUNT_STAT + counted.key()),)).key()}}


def _beck(d: Def) -> Def | None:
    """Beck: the turn-long delayed ability (603.7c) triggers on any creature entering, whoever controls it (ruling 2013-04-15); the draw is optional."""
    if _dos(d) != ["delayed", "deferred:draw"]:
        return None
    watch, draw = d["effects"]
    return {**d, "effects": [{**watch, "n": 2}, {"do": "deferred:may_rest", "skip": 1, "label": "Draw a card"}, draw]}


def _split(d: Def) -> Def | None:
    """Split Decision (will of the council): the target spell is chosen as it is cast; the vote happens as it resolves (rulings 2014-05-29), then
    the spell is countered (denial wins) or copied, new targets allowed (707.10c)."""
    from app.rules import scripts

    vote = scripts.parse_effects("Starting with you, each player votes for denial or duplication. If denial gets more votes, draw a card. If "
                                 "duplication gets more votes or the vote is tied, draw two cards.")
    if _dos(d) != ["copy_spell", "copy_new_targets"] or vote is None or [e.get("do") for e in vote[0]] != ["vote", "only_if", "draw", "only_if", "draw"]:
        return None
    ballot, denial, _, duplication, _ = vote[0]
    return {**d, "effects": [ballot, denial, {"do": "counter", "who": "target"}, {**duplication, "skip": 2}, *d["effects"]]}


_SPELL_BUILD: dict[str, tuple[str, Callable[[Def], Def | None]]] = {
    "Choose target instant or sorcery spell. Starting with you, each player votes for denial or duplication. If denial gets more votes, counter the "
    "spell. If duplication gets more votes or the vote is tied, copy the spell. You may choose new targets for the copy.":
        ("Copy target instant or sorcery spell. You may choose new targets for the copy.", _split),
    "Whenever a creature enters this turn, you may draw a card.": ("Whenever a creature enters this turn, draw a card.", _beck),
    "Return to the battlefield target nonland permanent card in your graveyard with mana value less than or equal to the number of permanent cards in your "
    "graveyard.": ("Return target nonland permanent card from your graveyard to the battlefield.", _descent),
}


_HELLBENT = "If you have no cards in hand, this spell can't be countered and the damage can't be prevented."
_EMPTY_HAND = {"value": {"hand": "you"}, "op": "==", "n": 0}


def _demonfire(d: Def) -> Def | None:
    """Demonfire (hellbent): with no cards in your hand as it resolves (608.2c), its damage can't be prevented (615.12)."""
    if _dos(d) != ["damage", "exile_if_dies"]:
        return None
    hit, exile = d["effects"]
    return {**d, "effects": [{"do": "only_if", "cond": _EMPTY_HAND, "skip": 1, "bind": "cond0"}, {**hit, "unpreventable": True},
                             {"do": "only_if", "cond": {"flag": "cond0", "negate": True}, "skip": 1}, hit, exile]}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == "static" and text == "As long as ~ entered this turn, you may activate her loyalty abilities any time you could cast an instant.":
        # The Wandering Emperor: 606.3's sorcery timing lifted (still once each turn) while the object entered this turn (cast_limits.loyalty_rule)
        return {"kind": "static", "static": "loyalty_rule", "who": "self", "instant": True, "entered100h": True, "effects": []}
    if ability.kind == "spell" and text == _HELLBENT:  # (its "can't be countered" part: a static of the spell, judged when something would counter it)
        return {"kind": "static", "static": "self_uncounterable", "cond": _EMPTY_HAND, "effects": []}
    others = tuple(a for a in ch.abilities if scripts.self_text(a.text, ch.name) != _HELLBENT)
    if ability.kind == "spell" and len(others) < len(ch.abilities) and \
            text == "~ deals X damage to any target. If a creature dealt damage this way would die this turn, exile it instead.":
        native = scripts.define(ability, replace(ch, abilities=others))
        return None if native is None else _demonfire(native)
    if ability.kind == "spell" and (spell := _SPELL_BUILD.get(text)) is not None:
        native = scripts.define(replace(ability, text=spell[0]), ch)
        return None if native is None else spell[1](native)
    if (same := _AS.get(text)) is not None:
        return scripts.define(replace(ability, text=same), ch)
    built = _BUILD.get(text)
    if built is None:
        return None
    natives = [scripts.define(replace(ability, text=t), ch) for t in built[0]]
    return None if any(n is None for n in natives) else built[1](*natives)


def holds(plan: Any, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    """Frodo: the source is its controller's Ring-bearer (701.54a) and the Ring has tempted them two or more times (701.54c)."""
    from app.rules import designations

    card = plan.state.cards.get(ctx.get("source_card") or "")
    return bool(card is not None and plan.oid(card) == ctx.get("source_object") and designations.ring_bearer_of(plan.state, card)
                and designations.ring_level(plan, ctx["controller"]) >= 2)


def council(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    tally = (ctx.get("vote") or {}).get("tally") or {}
    top = max(tally.values(), default=0)
    colors = [w for w, n in tally.items() if top and n == top]
    return effects.grant(plan, ctx, {"do": "grant", "who": "self", "keywords": [], "abilities": [f"Protection from {c}" for c in colors],
                                     "duration": "permanent"})


def destiny(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import history, win_game

    for pid in [p for p in history.log_for(plan).attacked_who.get(ctx.get("source_object") or "", []) if p in plan.live()]:
        win_game.lose_game(plan, ctx, {"who": f"player:{pid}"})
    return True


def toxic_draw(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import combat, effects

    n = sum(combat._toxic(plan.ch(plan.state.cards[c])) for c in effects._cards(plan, ctx, e["who"]))
    return effects.draw(plan, ctx, {"do": "draw", "who": "you", "n": n}) if n else True


def shade(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, permissions

    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is None or card.zone != f"{ctx['controller']}:graveyard" or plan.oid(card) != ctx.get("source_object"):
        return True  # (it left the graveyard, or is a new object there: no permission)
    context.bind_objects(plan, ctx, "shade100h", [card.id])
    return permissions.grant_play(plan, ctx, {"do": "grant_play", "who": context.PREFIX + "shade100h", "play": False, "cast": True, "until": "end_of_turn"})


PRIMITIVES = {"council100h": council, "destiny100h": destiny, "toxic_draw100h": toxic_draw, "shade100h": shade}
