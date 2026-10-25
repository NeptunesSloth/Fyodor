"""-- counters (wave 100J) -- counter lines the grammar didn't read, as an equivalent native wording plus, where needed, a patch.

* Decimator Web: "loses 2 life, gets a poison counter, then mills six cards" — one player, three instructions in order (608.2c).
* Necrogen Rotpriest: "an additional poison counter" — one poison counter of the trigger's own, besides toxic's (702.164c).
* Trygon Prime: "it" is ~ (608.2k); "That creature" is only the other target (the ruling).
* Ultimate Spider-Man: "each Spider and legendary creature you control" — each creature you control that is a Spider or legendary, once (701.10e).
* Vexing Radgull: whether that player has a rad counter is read once, as it resolves (608.2c): two rad counters, or else proliferate (701.34a).
* Bounty Board: "its controller's opponents" — the other players (102.2) than the dying creature's controller as it last existed (608.2h), a
  bounty counter from anywhere (the ruling).
* Lightshield Array: every creature declared as an attacker this turn (508.1), anyone's.
* Erithizon: the defending player (508.5) chooses the target as the ability is put on the stack (the ruling).
* Ley Line: the upkeep's player chooses the target (as Erithizon's) and, as it resolves, whether to put the counter, which they put (608.2d).
* The Ghoul, Gunslinger: "If that player is you" — the target player is the ability's controller (608.2c).
* Obscura Ascendancy: an intervening "if" (603.4): the spell's mana value (as it is, or last existed on the stack: 608.2h) is 1 plus the
  number of soul counters on ~, at the trigger and again as it resolves (the ruling).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from app.rules import selectors

_CREATURE = selectors.Selector(types=("Creature",))
_ADAPT = ("haste", "flying", "first strike", "double strike", "deathtouch", "indestructible", "lifelink", "menace", "reach", "trample", "vigilance")
_SPIDERS = "union:" + "+".join(s.key() for s in (replace(_CREATURE, controller="you", subtypes=("Spider",)), replace(_CREATURE, controller="you", supertypes=("Legendary",))))


def _who(who: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Every instruction of the native reading made about ``who`` instead."""
    return lambda d: {**d, "effects": [{**e, "who": who} for e in d["effects"]]}


def _radgull(d: dict[str, Any]) -> dict[str, Any] | None:
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["player_counter"]:
        return None
    none = {"as": "event", "cond": {"value": {"player_counters": "rad"}, "op": "==", "n": 0}}
    return {**d, "effects": [{"do": "only_if", "cond": none, "bind": "rad100j", "skip": 1}, effects[0],
                             {"do": "only_if", "cond": {"flag": "rad100j", "negate": True}, "skip": 1}, {"do": "proliferate", "who": "you"}]}


def _intervening(d: dict[str, Any], cond: dict[str, Any]) -> dict[str, Any]:
    """603.4: checked as it triggers ("if") and again as it resolves (the first instruction), as the grammar reads one."""
    return {**d, "if": cond, "effects": [{"do": "only_if", "cond": cond, "skip": len(d["effects"])}, *d["effects"]]}


def _chooser(who: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    return lambda d: {**d, "target_choice": who}


def _ley(d: dict[str, Any]) -> dict[str, Any] | None:
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["add_counters"]:
        return None
    return {**d, "target_choice": "event_player",
            "effects": [{"do": "optional_payment", "who": "event_player", "ask": "put a +1/+1 counter on the target", "bind": "pay0"},
                        {"do": "only_if", "cond": {"succeeded": "pay0"}, "skip": 1}, {**effects[0], "by": "event_player"}]}


def _ghoul(d: dict[str, Any]) -> dict[str, Any] | None:
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["player_counter", "create_token"]:
        return None
    return {**d, "effects": [effects[0], {"do": "only_if", "cond": {"target_you100j": True}, "skip": 1}, effects[1]]}


def _shape(*dos: str) -> Callable[[Callable[[list[dict[str, Any]]], list[dict[str, Any]]]], Callable[[dict[str, Any]], dict[str, Any] | None]]:
    """A patch of the native instructions, applied only when they are exactly ``dos``."""
    def wrap(f: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
        return lambda d: {**d, "effects": f(d["effects"])} if [e.get("do") for e in d["effects"]] == list(dos) else None
    return wrap


@_shape("add_counters", "optional_payment", "only_if", "lose_life")
def _torment(es: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Torment of Venom: "another nonland permanent" — other than the target creature (the spell is no permanent); the player may also
    choose neither and lose 3 life (the ruling)."""
    pay = {k: v for k, v in es[1].items() if k != "cost"}
    return [es[0], {"do": "exclude100j", "who": "ref:" + es[0]["as"]}, {**pay, "alts": ["Sacrifice another nonland permanent", "Discard a card"]},
            *es[2:]]


@_shape("return_choice")
def _finality(es: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**es[0], "counter": "finality"}]  # (122.1h: it enters with it, 122.6)


@_shape("return_choice", "grant", "delayed", "deferred:sacrifice")
def _emperor(es: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**es[0], "counter": "finality"}, *es[1:]]


@_shape("until", "restrict")
def _edifice(es: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [es[0], {**es[1], "rules": [*es[1]["rules"], "cant_activate"]}]  # (602.5: mana abilities too)


@_shape("add_counters", "delayed", "deferred:draw", "deferred:create_token")
def _xira(es: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Xira: the delayed ability's "if it has an egg counter on it" — the creature as it last existed (603.10a, 608.2h)."""
    return [es[0], {**es[1], "n": 3}, {"do": "deferred:only_if", "cond": {"egg100j": "egg"}, "skip": 2}, *es[2:]]


@_shape("exile", "return_card")
def _respite(es: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hallowed Respite: the returned permanent (400.7: a new object) — under your control, a counter; otherwise tapped (608.2c)."""
    back = "ref:back100j"
    return [es[0], {**es[1], "as": "back100j"}, {"do": "only_if", "cond": {"you_control100j": back}, "bind": "mine100j", "skip": 1},
            {"do": "add_counters", "who": back, "kind": "+1/+1", "n": 1}, {"do": "only_if", "cond": {"flag": "mine100j", "negate": True}, "skip": 1},
            {"do": "tap", "who": back}]


# text (after scripts.self_text) -> (the native wording it reads as, how its definition is completed)
_AS: dict[str, tuple[str, Callable[[dict[str, Any]], dict[str, Any] | None] | None]] = {
    "{4}, {T}: Target opponent loses 2 life, gets a poison counter, then mills six cards.":
        ("{4}, {T}: Target opponent loses 2 life and gets a poison counter. That player mills six cards.", None),
    "Whenever a creature you control with toxic deals combat damage to a player, that player gets an additional poison counter.":
        ("Whenever a creature you control with toxic deals combat damage to a player, that player gets a poison counter.", None),
    "Whenever ~ attacks, put a +1/+1 counter on it and a +1/+1 counter on up to one other target attacking creature. That creature can't be blocked this turn.":
        ("Whenever ~ attacks, put a +1/+1 counter on ~. Put a +1/+1 counter on up to one other target attacking creature. That creature can't be "
         "blocked this turn.", None),
    "Whenever you attack, double the number of each kind of counter on each Spider and legendary creature you control.":
        ("Whenever you attack, double the number of each kind of counter on each creature you control.", _who(_SPIDERS)),
    "Whenever ~ deals combat damage to a player, that player gets two rad counters if they don't have any rad counters. Otherwise, proliferate.":
        ("Whenever ~ deals combat damage to a player, that player gets two rad counters.", _radgull),
    "Whenever a creature with a bounty counter on it dies, each of its controller's opponents draws a card and gains 2 life.":
        ("Whenever a creature with a bounty counter on it dies, each opponent draws a card and gains 2 life.", _who("others100c:ref:event.controller")),
    "At the beginning of your end step, put a +1/+1 counter on each creature that attacked this turn.":
        ("At the beginning of your end step, put a +1/+1 counter on each creature you control.",
         _who(replace(_CREATURE, extras=("attacked_this_turn",)).key())),
    "Whenever ~ attacks, put a +1/+1 counter on target creature of defending player's choice.":
        ("Whenever ~ attacks, put a +1/+1 counter on target creature.", _chooser("defending100j")),
    "At the beginning of each player's upkeep, that player may put a +1/+1 counter on target creature of their choice.":
        ("At the beginning of each player's upkeep, put a +1/+1 counter on target creature.", _ley),
    "Whenever ~ or another nontoken Zombie or Mutant you control dies, target player gets two rad counters. If that player is you, create a Treasure token.":
        ("Whenever ~ or another nontoken Zombie or Mutant you control dies, target player gets two rad counters. Create a Treasure token.", _ghoul),
    "Whenever you cast a spell, if its mana value is equal to 1 plus the number of soul counters on ~, put a soul counter on ~, then create a 2/2 "
    "white Spirit creature token with flying.":
        ("Whenever you cast a spell with mana value 1, put a soul counter on ~, then create a 2/2 white Spirit creature token with flying.",
         lambda d: _intervening({**d, "cond": {**d["cond"], "spell": selectors.Selector(zones=("stack",)).key()}}, {"ascend100j": "soul"})),
    # Withengar Unbound: as Blood Tyrant's five (life_game_history: the loss event, 104.3, 603.10a)
    "Whenever a player loses the game, put thirteen +1/+1 counters on ~.":
        ("Whenever a player loses the game, put five +1/+1 counters on ~.", lambda d: {**d, "effects": [{**d["effects"][0], "n": 13}]}),
    # Gideon, Champion of Justice: P/T set as it resolves, not updated later (the ruling; 608.2h)
    "0: Until end of turn, ~ becomes a Human Soldier creature with power and toughness each equal to the number of loyalty counters on ~ and gains "
    "indestructible. He's still a planeswalker. Prevent all damage that would be dealt to ~ this turn.":
        ("0: Until end of turn, ~ becomes a Human Soldier creature with power and toughness each equal to the number of loyalty counters on it and "
         "gains indestructible. It's still a planeswalker. Prevent all damage that would be dealt to ~ this turn.",
         _shape("become", "grant", "still_a", "prevent_all")(lambda es: [{**es[0], "p": {"counters": "loyalty", "on": "self"},
                                                                            "t": {"counters": "loyalty", "on": "self"}}, *es[1:]])),
    # Celestial Convergence: 104.2b (the others lose), or 104.4c (a draw for every player: no limited range of influence in Commander)
    "At the beginning of your upkeep, remove an omen counter from ~. If there are no omen counters on ~, the player with the highest life total wins "
    "the game. If two or more players are tied for highest life total, the game is a draw.":
        ("At the beginning of your upkeep, remove an omen counter from ~. If there are no omen counters on ~, you win the game.",
         _shape("remove_counters", "only_if", "win_game")(lambda es: [*es[:2], {"do": "convergence100j"}])),
    "Put three -1/-1 counters on target creature. Its controller loses 3 life unless they sacrifice another nonland permanent of their choice or "
    "discard a card.": ("Put three -1/-1 counters on target creature. Its controller loses 3 life unless they discard a card.", _torment),
    # Biogenic Upgrade: "those creatures" — the targets still legal (608.2b); doubling puts as many as each has (701.10e, the ruling)
    "Distribute three +1/+1 counters among one, two, or three target creatures, then double the number of +1/+1 counters on each of those creatures.":
        ("Distribute three +1/+1 counters among one, two, or three target creatures.",
         _shape("add_counters")(lambda es: [*es, {"do": "double_counters", "who": "target:0", "kind": "+1/+1"}])),
    "When ~ enters, exile an instant or sorcery card from your graveyard. Put a number of +1/+1 counters on ~ equal to half that card's mana value, "
    "rounded up.": ("When ~ enters, exile an instant or sorcery card from your graveyard. Put a number of +1/+1 counters on ~ equal to that card's "
                    "mana value.", _shape("return_choice", "add_counters")(lambda es: [es[0], {**es[1], "n": {"half": es[1]["n"], "round": "up"}}])),
    # Floodpits Drowner: an illegal target and nothing happens, ~ isn't shuffled either (the ruling: one target, 608.2b)
    "{1}{U}, {T}: Shuffle ~ and target creature with a stun counter on it into their owners' libraries.":
        ("{1}{U}, {T}: Shuffle ~ into its owner's library. Shuffle target creature with a stun counter on it into its owner's library.", None),
    "At the beginning of your upkeep, you may put a creature card exiled with ~ onto the battlefield under your control with a finality counter on it.":
        ("At the beginning of your upkeep, you may put a creature card exiled with ~ onto the battlefield under your control.", _finality),
    "Whenever one or more +1/+1 counters are put on ~, put a creature card exiled with ~ onto the battlefield under your control with a finality "
    "counter on it. It gains haste. Sacrifice it at the beginning of the next end step.":
        ("Whenever one or more +1/+1 counters are put on ~, put a creature card exiled with ~ onto the battlefield under your control. It gains haste. "
         "Sacrifice it at the beginning of the next end step.", _emperor),
    "{1}, {T}: Until your next turn, target creature can't attack or block and its activated abilities can't be activated. Activate only if there "
    "are three or more brick counters on ~.": ("{1}, {T}: Until your next turn, target creature can't attack or block. Activate only if there are "
                                                 "three or more brick counters on ~.", _edifice),
    # Norn's Decree: "poisoned" — one or more poison counters (the ruling); a player a creature is attacking (not a planeswalker's controller)
    "Whenever a player attacks, if one or more players being attacked are poisoned, the attacking player draws a card.":
        ("Whenever a player attacks, the attacking player draws a card.", lambda d: _intervening(d, {"poisoned100j": True})),
    # Arcus Acolyte: 702.107a outlast, granted as that ability (as oracle.py reads a printed outlast line; Enduring Sliver, wave 100D)
    "Each other creature you control without a +1/+1 counter on it has outlast {G/W}.":
        ('Each other creature you control without a +1/+1 counter on it has "{G/W}, {T}: Put a +1/+1 counter on this creature. Activate only as '
         'a sorcery."', None),
    # Awakening of Vitu-Ghazi: its name is just Vitu-Ghazi, for good (the rulings; a layer 3 name, as rules_state's set_name)
    "Put nine +1/+1 counters on target land you control. It becomes a legendary 0/0 Elemental creature with haste named Vitu-Ghazi. It's still a land.":
        ("Put nine +1/+1 counters on target land you control. It becomes a legendary 0/0 Elemental creature with haste. It's still a land.",
         _shape("add_counters", "become", "still_a")(lambda es: [*es, {"do": "name100j", "who": "target", "name": "Vitu-Ghazi"}])),
    "Whenever ~ attacks, put an egg counter on another target creature without an egg counter on it. When that creature dies, if it has an egg "
    "counter on it, draw a card and create a 1/1 black Insect creature token with flying.":
        ("Whenever ~ attacks, put an egg counter on another target creature without an egg counter on it. When that creature dies, draw a card and "
         "create a 1/1 black Insect creature token with flying.", _xira),
    "Exile target nonlegendary creature, then return it to the battlefield under its owner's control. If it entered under your control, put a "
    "+1/+1 counter on it. Otherwise, tap it.":
        ("Exile target nonlegendary creature, then return it to the battlefield under its owner's control.", _respite),
    # Wicked Slumber: each counter on a target still legal, the same one or not (the rulings)
    "Tap up to two target creatures. Put a stun counter on either of them. Then put a stun counter on either of them.":
        ("Tap up to two target creatures.", _shape("tap")(lambda es: [*es, {"do": "stun100j"}, {"do": "stun100j"}])),
    # Amzu: "those cards" — the batch that left at once, one trigger for it (the ruling; 603.2c), each as it last existed there (608.2h)
    "Whenever one or more cards leave your graveyard, you may create a 1/1 black and green Insect creature token, then put a number of +1/+1 "
    "counters on it equal to the greatest mana value among those cards. Do this only once each turn.":
        ("Whenever one or more cards leave your graveyard, you may create a 1/1 black and green Insect creature token, then put a number of +1/+1 "
         "counters on it equal to the greatest mana value among them. Do this only once each turn.", None),
    # Portent Tracker: who protects it (310.8) is read as it resolves (608.2c)
    "{T}: Choose target battle. If an opponent protects it, remove a defense counter from it. Otherwise, put a defense counter on it. Activate "
    "only as a sorcery.": ("{T}: Put a defense counter on target battle. Activate only as a sorcery.", _shape("add_counters")(lambda es: [
        {"do": "only_if", "cond": {"protected_opp100j": True}, "bind": "opp100j", "skip": 1}, {"do": "remove_counters", "who": "target", "kind": "defense", "n": 1},
        {"do": "only_if", "cond": {"flag": "opp100j", "negate": True}, "skip": 1}, *es])),
    # Sphere of Annihilation: the void counters as it resolves, before anything is exiled; all at once (608.2h; X is 0 off the stack: the ruling)
    "At the beginning of your upkeep, exile ~, all creatures and planeswalkers with mana value less than or equal to the number of void counters on "
    "it, and all creature and planeswalker cards in graveyards with mana value less than or equal to the number of void counters on it.":
        ("At the beginning of your upkeep, exile ~.", _shape("exile")(lambda es: [{"do": "sphere100j"}])),
    # The Book of Exalted Deeds: the Angel keeps the ability, counter or not, Angel or not (the rulings; game_result reads it, 104.3, 104.2b)
    "{W}{W}{W}, {T}, Exile ~: Put an enlightened counter on target Angel. It gains \"You can't lose the game and your opponents can't win the game.\" "
    "Activate only as a sorcery.": ("{W}{W}{W}, {T}, Exile ~: Put an enlightened counter on target Angel. It gains flying. Activate only as a sorcery.",
                                    _shape("add_counters", "grant")(lambda es: [es[0], {**es[1], "keywords": [], "abilities": [
                                        "You can't lose the game and your opponents can't win the game."]}])),
    # Super-Adaptoid: each keyword checked in turn as it resolves, against the target and ~ as they are then (608.2c); keyword counters (122.1b)
    "Whenever ~ enters or attacks, choose another target creature. If that creature has haste and ~ doesn't, put a haste counter on ~. Do the same "
    "for flying, first strike, double strike, deathtouch, indestructible, lifelink, menace, reach, trample, and vigilance.":
        ("Whenever ~ enters or attacks, choose another target creature. If that creature has flying, put a flying counter on ~.",
         _shape("choose_targets", "only_if", "add_counters")(lambda es: [es[0], *(x for kw in _ADAPT for x in (
             {"do": "only_if", "cond": {"adapt100j": kw}, "skip": 1}, {**es[2], "kind": kw}))])),
    # Desecration Demon: each opponent in turn order may sacrifice, even after another did; one counter at most (the rulings; 101.4, 118.12)
    "At the beginning of each combat, any opponent may sacrifice a creature of their choice. If a player does, tap ~ and put a +1/+1 counter on it.":
        ("At the beginning of each combat, tap ~ and put a +1/+1 counter on it.", _shape("tap", "add_counters")(lambda es: [{"do": "demon100j"}, *es])),
    # Lavabrink Floodgates: the upkeep's player puts one, removes one or does nothing (the ruling); sacrificed only by this resolution (the ruling)
    "At the beginning of each player's upkeep, that player may put a doom counter on ~ or remove a doom counter from it. Then if it has three or "
    "more doom counters on it, sacrifice ~. When you do, it deals 6 damage to each creature.":
        ("At the beginning of each player's upkeep, put a doom counter on ~. Then if ~ has three or more doom counters on it, sacrifice ~. When you "
         "do, ~ deals 6 damage to each creature.", _shape("add_counters", "only_if", "sacrifice", "reflexive")(lambda es: [{"do": "floodgates100j"}, *es[1:]])),
    # Terrapact Intimidator: the target opponent chooses as it resolves (118.12-style "may have"); "If they don't": the counters instead
    "When ~ enters, target opponent may have you create two Lander tokens. If they don't, put two +1/+1 counters on ~.":
        ("When ~ enters, target opponent loses 1 life. Create two Lander tokens. Put two +1/+1 counters on ~.",
         _shape("lose_life", "create_token", "add_counters")(lambda es: [
             {"do": "optional_payment", "who": "target", "ask": "have its controller create two Lander tokens (if not, it gets two +1/+1 counters)", "bind": "pay0"},
             {"do": "only_if", "cond": {"succeeded": "pay0"}, "skip": 1}, es[1], {"do": "only_if", "cond": {"succeeded": "pay0", "negate": True}, "skip": 1}, es[2]])),
    # Dimension X Pizzasaur: every counter of every kind on permanents you control, read when the target is chosen and again as it resolves (608.2b)
    "When ~ enters, put two +1/+1 counters on target creature. When you do, destroy up to one target creature with mana value less than or equal to "
    "the number of counters among permanents you control.":
        ("When ~ enters, put two +1/+1 counters on target creature. When you do, destroy up to one target creature with mana value less than or equal "
         "to the number of creatures you control.", _shape("add_counters", "reflexive")(lambda es: [es[0], {**es[1], "ability": {**es[1]["ability"], "targets": [
             {**es[1]["ability"]["targets"][0], "what": replace(_CREATURE, compare=(("mv", "<=", "counters100j"),)).key()}]}}])),
    # Dismantle: how many counters it had, of any kind; the kind and the artifact chosen as it resolves; also when it wasn't destroyed (the rulings)
    "Destroy target artifact. If that artifact had counters on it, put that many +1/+1 counters or charge counters on an artifact you control.":
        ("Destroy target artifact.", _shape("destroy")(lambda es: [{"do": "dismantle100j"}, *es])),
    # Xathrid Gorgon: for good, whatever happens to the counter (the ruling); defender (613.1f), artifact and colorless (613.1d-e), no activations (602.5)
    "{2}{B}, {T}: Put a petrification counter on target creature. It gains defender and becomes a colorless artifact in addition to its other types. "
    "Its activated abilities can't be activated.": ("{2}{B}, {T}: Put a petrification counter on target creature. It becomes a colorless artifact in "
                                                    "addition to its other types.", _shape("add_counters", "become")(lambda es: [
                                                        *es, {"do": "grant", "who": "target", "keywords": ["defender"], "duration": "permanent"},
                                                        {"do": "restrict", "who": "target", "rules": ["cant_activate"], "duration": "permanent"}])),
    # Valor's Reach Tag Team's Warriors: "~ and at least one other creature token attack" — another token among the attackers declared (508.1)
    "Whenever ~ and at least one other creature token attack, put a +1/+1 counter on ~.":
        ("Whenever ~ and at least one other creature attack, put a +1/+1 counter on ~.",
         lambda d: {**d, "cond": {**d["cond"], "min_attackers": 1, "sel": replace(_CREATURE, token=True).key(), "others_only": True}}),
    # Quarantine Field: as many targets as isolation counters on it as the ability is put on the stack, then locked (the ruling; 601.2c)
    "When ~ enters, for each isolation counter on it, exile up to one target nonland permanent an opponent controls until ~ leaves the battlefield.":
        ("When ~ enters, exile up to X target nonland permanents an opponent controls until ~ leaves the battlefield.",
         lambda d: {**d, "targets": [{**d["targets"][0], "x_value": {"counters": "isolation", "on": "self"}}]} if len(d.get("targets") or []) == 1 else None),
    "When ~ enters, put two level counters on each creature you control with level up.":
        ("When ~ enters, put two level counters on each creature you control.", _who(replace(_CREATURE, controller="you", extras=("level_up100j",)).key())),
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    found = _AS.get(scripts.self_text(ability.text, ch.name))
    if found is None:
        return None
    native = scripts.define(replace(ability, text=found[0]), ch)
    return native if native is None or found[1] is None else found[1](native)


def holds(plan: Any, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    from app.rules import context, effects

    if cond.get("target_you100j"):
        return effects._players(plan, ctx, "target") == [ctx["controller"]]
    if (kind := cond.get("ascend100j")) is not None:
        spell = context.info(plan, ctx, context.EVENT)
        return spell is not None and int(spell[1].mana_value) == 1 + _self_counters(plan, ctx, kind)
    if cond.get("poisoned100j"):
        attacked = {c.attacking.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.attacking is not None and c.attacking.kind == "player"}
        return any(plan.state.players[p].resources.get("poison", 0) > 0 for p in plan.live() if p in attacked)
    if (ref := cond.get("you_control100j")) is not None:
        cards = effects._cards(plan, ctx, ref)
        return bool(cards) and all(plan.state.cards[c].controller == ctx["controller"] for c in cards)
    if (kind := cond.get("egg100j")) is not None:
        got = context.info(plan, ctx, context.EVENT)
        return got is not None and got[0].counters.get(kind, 0) > 0
    if cond.get("protected_opp100j"):
        from app.rules import battles

        found = effects._cards(plan, ctx, "target")
        return bool(found) and battles.protector(plan.state, plan.state.cards[found[0]]) in [p for p in plan.live() if p != ctx["controller"]]
    if (kw := cond.get("adapt100j")) is not None:
        found, src = effects._cards(plan, ctx, "target"), effects._cards(plan, ctx, "self")
        return bool(found and src) and kw in plan.ch(plan.state.cards[found[0]]).keywords and kw not in plan.ch(plan.state.cards[src[0]]).keywords
    if (binds := cond.get("any_paid100j")) is not None:
        from app.rules import conditions

        return any(conditions.holds(plan, ctx, {"succeeded": b}) for b in binds)
    return False


def _self_counters(plan: Any, ctx: dict[str, Any], kind: str) -> int:
    """The source's counters of a kind, as it is or as it last existed (608.2h)."""
    src = plan.state.cards.get(ctx.get("source_card") or "")
    if src is not None and plan.oid(src) == ctx.get("source_object") and src.zone.endswith(":battlefield"):
        return int(src.counters.get(kind, 0))
    snap = plan.rules.lki.get(ctx.get("source_object") or "")
    return int(snap.counters.get(kind, 0)) if snap is not None else 0


def sphere(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    n = _self_counters(plan, ctx, "void")
    kinds = ("Creature", "Planeswalker")
    groups = [selectors.Selector(types=kinds, compare=(("mv", "<=", n),)), selectors.Selector(card=True, types=kinds, zones=("graveyard",), compare=(("mv", "<=", n),))]
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "exile", "who": "union:" + "+".join(["self", *(g.key() for g in groups)])}]
    return True


def convergence(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import win_game

    live = plan.live()
    top = max(plan.state.players[p].life for p in live)
    leaders = [p for p in live if plan.state.players[p].life == top]
    if len(leaders) == 1:
        return win_game.win_game(plan, {**ctx, "controller": leaders[0]}, e)
    plan.rules.draw_reason = "Two or more players are tied for the highest life total (104.4c)"
    plan.rules.priority = None
    plan.rules.decision = None
    plan.note("The game is a draw: two or more players are tied for the highest life total (104.4c)")
    return False


def exclude(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The binding's object can't pay the cost its controller is offered next (optional_payment._taken)."""
    from app.rules import effects

    if payer := effects._players(plan, ctx, e["who"] + ".controller"):
        ctx.setdefault("resolution_cost_exclusions", []).append({"payer": payer[0], "who": e["who"]})
    return True


def name(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, layers

    if cards := effects._cards(plan, ctx, e["who"]):
        layers.add_effect(plan, affected=[plan.oid(plan.state.cards[c]) for c in cards], layer="3", source=ctx.get("source_object"),
                          controller=ctx["controller"], duration="permanent", label=f"named {e['name']}", set_name=e["name"])
    return True


def _put(plan: Any, ctx: dict[str, Any], cid: str, kind: str, n: int = 1, **extra: Any) -> None:
    """Next, put ``n`` counters of ``kind`` on that permanent (through add_counters: 122.6, 614.16)."""
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "add_counters", "who": f"object:{plan.oid(plan.state.cards[cid])}", "kind": kind, "n": n, **extra}]


def _ask(plan: Any, ctx: dict[str, Any], player: str, step: str, prompt: str, options: Sequence[tuple[str, str, str | None]], **extra: Any) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=player, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: {prompt}",
           options=[DecisionOption(id=i, label=label, card_id=card) for i, label, card in options], resume={"step": step, "ctx": ctx, **extra})
    return False


def stun(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    legal = effects._cards(plan, ctx, "target:0")
    if len(legal) == 1:
        _put(plan, ctx, legal[0], "stun")
    if len(legal) < 2:
        return True
    return _ask(plan, ctx, ctx["controller"], "stun100j", "put a stun counter on which?", [(c, plan.state.cards[c].name or "Creature", c) for c in legal])


def demon(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Desecration Demon: one optional sacrifice for each opponent, in turn order (101.4); then the tap and the counter if any was made."""
    opponents = [p for p in plan.apnap() if p != ctx["controller"] and p in plan.live()]
    binds = [f"demon100j_{p}" for p in opponents]
    pays = [{"do": "optional_payment", "who": f"player:{p}", "cost": "Sacrifice a creature", "bind": b} for p, b in zip(opponents, binds, strict=True)]
    ctx["effects"][ctx["next"]:ctx["next"]] = [*pays, {"do": "only_if", "cond": {"any_paid100j": binds}, "skip": 2}]
    return True


def floodgates(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    src = plan.state.cards.get(ctx.get("source_card") or "")
    who = effects._players(plan, ctx, "event_player")
    if src is None or plan.oid(src) != ctx.get("source_object") or not src.zone.endswith(":battlefield") or not who:
        return True
    options = [("put", "Put a doom counter on it", None), *([("remove", "Remove a doom counter from it", None)] if src.counters.get("doom") else []),
               ("neither", "Do neither", None)]
    return _ask(plan, ctx, who[0], "floodgates100j", "put a doom counter on it, remove one, or neither?", options)


def dismantle(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Dismantle: its counters before it's destroyed (608.2h), put after the destruction (the next instruction)."""
    from app.rules import effects

    n = sum(sum(plan.state.cards[c].counters.values()) for c in effects._cards(plan, ctx, "target"))
    if n > 0:
        ctx["effects"][ctx["next"] + 1:ctx["next"] + 1] = [{"do": "dismantle_put100j", "n": n}]
    return True


def dismantle_put(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    arts = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == ctx["controller"] and plan.in_game(c)
            and "Artifact" in plan.ch(c).types]
    if not arts:
        return True
    return _ask(plan, ctx, ctx["controller"], "dismantle100j", f"put {e['n']} counters on which artifact, of which kind?",
                [(f"{c}|{k}", f"{plan.state.cards[c].name}: {k}", c) for c in arts for k in ("+1/+1", "charge")], n=e["n"])


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose one of the offered options")
    ctx, step, pick = d.resume["ctx"], d.resume["step"], chosen[0]
    if step == "stun100j":
        _put(plan, ctx, pick, "stun")
    elif step == "dismantle100j":
        cid, _, kind = pick.partition("|")
        _put(plan, ctx, cid, kind, int(d.resume["n"]))
    elif pick == "put":
        _put(plan, ctx, ctx["source_card"], "doom", by="event_player")
    elif pick == "remove":
        ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "remove_counters", "who": "self", "kind": "doom", "n": 1}]
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"convergence100j": convergence, "exclude100j": exclude, "name100j": name, "stun100j": stun, "sphere100j": sphere, "demon100j": demon,
              "floodgates100j": floodgates, "dismantle100j": dismantle, "dismantle_put100j": dismantle_put}
RESUME = {"stun100j": resume, "floodgates100j": resume, "dismantle100j": resume}
