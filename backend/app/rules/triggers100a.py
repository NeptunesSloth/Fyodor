"""-- trigger lines (wave 100A) -- triggered abilities read as an equivalent native wording plus, where needed, instructions of their own.

* Calculating Lich: "Whenever a creature attacks one of your opponents, that player loses 1 life." — the attack is declared against that opponent
  directly (508.3a; the "opponent" defender is a player, not a planeswalker), so "that player" is the attacking creature's defending player (508.5).
* Invasion of Ulgrotha: "When this Siege enters, it deals 3 damage to any other target …" — "it" is the Siege the trigger is about (608.2k) and
  "any other target" is any target but the Siege (115.4).
* Primordial Plasm: "… another target creature gets +2/+2 and loses all abilities until end of turn." — one effect: +2/+2 (613.4c) and losing all
  abilities (613.1f) from the same resolution, both until end of turn (514.2).
* Spreading Plague: "Whenever a creature enters, destroy all other creatures that share a color with it. They can't be regenerated." — "it" is the
  entering creature as it is as the ability resolves, or as it last existed (608.2h); a colorless one shares no color (105.2c); "other" is other than
  that object (a new object it became is another one, 400.7); all are destroyed at once (701.8a), without regeneration (701.19c).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

# text (after scripts.self_text) -> (the native wording it reads as, instructions, whether they replace the native effects or follow them)
_AS: dict[str, tuple[str, list[dict[str, Any]], bool]] = {
    "Whenever a creature attacks one of your opponents, that player loses 1 life.":
        ("Whenever a creature attacks one of your opponents, defending player loses 1 life.", [], False),
    "When ~ enters, it deals 3 damage to any other target and you gain 3 life.":
        ("When ~ enters, ~ deals 3 damage to any other target and you gain 3 life.", [], False),
    # Dinrova Horror: "that player" is the owner whose hand it went to (the one player named before)
    "When ~ enters, return target permanent to its owner's hand, then that player discards a card.":
        ("When ~ enters, return target permanent to its owner's hand. Its owner discards a card.", [], False),
    # Carrion Locust: "that player" is the opponent whose graveyard held it, the card's owner (404.2: a card goes to its owner's graveyard)
    "When ~ enters, exile target card from an opponent's graveyard. If it was a creature card, that player loses 1 life.":
        ("When ~ enters, exile target card from an opponent's graveyard. If it was a creature card, its owner loses 1 life.", [], False),
    "At the beginning of combat on your turn, another target creature gets +2/+2 and loses all abilities until end of turn.":
        ("At the beginning of combat on your turn, another target creature gets +2/+2 until end of turn.",
         [{"do": "become", "who": "target", "types": [], "lose_abilities": True, "duration": "end_of_turn"}], False),
    "Whenever a creature enters, destroy all other creatures that share a color with it. They can't be regenerated.":
        ("Whenever a creature enters, destroy it.", [{"do": "plague100a"}, {"do": "destroy", "who": "ref:plague100a"}, {"do": "no_regen"}], True),
    # Saltskitter: "this creature" after it was exiled is the card that left (400.7: the object the exile made), which "it" reads
    "Whenever another creature enters, exile ~. Return ~ to the battlefield under its owner's control at the beginning of the next end step.":
        ("Whenever another creature enters, exile ~. Return it to the battlefield under its owner's control at the beginning of the next end step.", [], False),
    # Ghastlord of Fugue: the revealed hand's owner exiles the card its controller chose (406.1: to exile; nothing here asks who did it)
    "Whenever ~ deals combat damage to a player, that player reveals their hand. You choose a card from it. That player exiles that card.":
        ("Whenever ~ deals combat damage to a player, that player reveals their hand. You choose a card from it. Exile that card.", [], False),
}

_MUTAVAULT: dict[str, Any] = {"name": "Mutavault", "power": None, "toughness": None, "colors": [], "type_line": "Token Land",
              "text": "{T}: Add {C}.\n{1}: This land becomes a 2/2 creature with all creature types until end of turn. It's still a land."}
_ANGEL: dict[str, Any] = {"name": "Angel", "power": "3", "toughness": "3", "colors": ["W"], "type_line": "Token Creature — Angel", "text": "Flying"}


def _nettling(d: dict[str, Any]) -> dict[str, Any] | None:
    """Nettling Nuisance: the token the damaged player created is goaded by you for the rest of the game (701.15a: by the ability's controller)."""
    effects = d["effects"]
    if len(effects) != 1 or effects[0].get("do") != "create_token":
        return None
    return {**d, "effects": [{**effects[0], "as": "nuisance100a"}, {"do": "permanent_copy_goad", "who": "ref:nuisance100a"}]}


def _kav(d: dict[str, Any]) -> dict[str, Any] | None:
    """Kav Landseeker: "the end step on your next turn" — an end step of yours in a later turn than this one (never this turn's)."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["create_token", "delayed", "deferred:sacrifice"]:
        return None
    return {**d, "effects": [effects[0], {**effects[1], "when": {**effects[1]["when"], "next_turn_only": True}}, effects[2]]}


def _mutavault(d: dict[str, Any]) -> dict[str, Any] | None:
    """Mutable Explorer: a token that's a copy of the card Mutavault (707.2, 111.4: the card's own characteristics — its name, types and rules text), tapped."""
    effects = d["effects"]
    if len(effects) != 1 or effects[0].get("do") != "create_token" or not effects[0].get("tapped"):
        return None
    return {**d, "effects": [{**effects[0], "token": dict(_MUTAVAULT)}]}


def _naturalist(d: dict[str, Any]) -> dict[str, Any] | None:
    """Patient Naturalist: the land card isn't optional ("Put …"); "If you can't" is that no land card was among the milled cards to put."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["mill", "pick_looked", "only_if", "create_token"]:
        return None
    return {**d, "effects": [effects[0], {**effects[1], "optional": False}, *effects[2:]]}


def _emancipation(d: dict[str, Any]) -> dict[str, Any] | None:
    """Soul of Emancipation: one Angel for each target still legal as it resolves, created by that permanent's controller as the destruction
    found it (608.2b: an illegal target gets none; the official ruling: one that wasn't destroyed — a shield counter — still gets one)."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["destroy"] or effects[0].get("who") != "target:0":
        return None
    return {**d, "effects": [{"do": "emancipate100a"}, *effects]}


def _dream(d: dict[str, Any]) -> dict[str, Any] | None:
    """Dream Eater: after the surveil, a reflexive ability (603.12) whose target is chosen then; it triggers even when fewer than four
    cards were surveilled (the official ruling)."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["surveil"]:
        return None
    back = {"kind": "triggered", "trigger": "reflexive", "effects": [{"do": "bounce", "who": "target"}], "optional": True,
            "target": {"what": "nonland_permanent_opp"}}
    return {**d, "effects": [*effects, {"do": "reflexive", "cond": {"always100a": True}, "ability": back}]}


def _antelope(d: dict[str, Any]) -> dict[str, Any] | None:
    """Graceful Antelope: "you may have target land become a Plains until ~ leaves the battlefield" — optional (decided on resolution, 603.5),
    the land's types replaced (305.7) for as long as the source remains on the battlefield (611.2b; nothing if it has already left)."""
    return {**d, "optional": True} if [e.get("do") for e in d["effects"]] == ["until", "become"] else None


def _boars(d: dict[str, Any]) -> dict[str, Any] | None:
    """Crashing Boars: the defending player (508.5) chooses as it resolves; the chosen creature must block ~ this turn if able (509.1c) —
    not if it's tapped by then (the official ruling), nothing when there's no untapped creature to choose."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["player_chooses", "tap"] or not effects[0].get("as"):
        return None
    return {**d, "effects": [effects[0], {"do": "restrict", "who": "ref:" + effects[0]["as"], "rules": ["must_block_obj:@src"]}]}


def _gravestorm(d: dict[str, Any]) -> dict[str, Any] | None:
    """Gravestorm: when the target opponent doesn't exile a card (or can't: an empty graveyard), you may draw."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["optional_payment", "only_if", "draw"] or effects[1].get("skip") != 1:
        return None
    return {**d, "effects": [effects[0], {**effects[1], "skip": 2}, {"do": "may_rest"}, effects[2]]}


def _upkeep_cost(name: str) -> Any:
    """Egon / Anurid Scavenger / Chisei: an upkeep instruction carried out by its primitive, then the rest unless it was done."""
    def build(d: dict[str, Any]) -> dict[str, Any] | None:
        effects = d["effects"]
        if not effects or effects[0].get("do") != "sacrifice" or effects[0].get("who") != "self":
            return None
        return {**d, "effects": [{"do": name}, {"do": "only_if", "cond": {"flag": name, "negate": True}, "skip": len(effects)}, *effects]}
    return build


_GABRIEL = ["flying", "first strike", "trample", "rampage 3"]


def _gabriel(d: dict[str, Any]) -> dict[str, Any] | None:
    """Gabriel Angelfire: the choice is made as it resolves (608.2d), the ability lasts until your next upkeep (delayed.DURATIONS)."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["until", "grant"]:
        return None
    options = [{"label": kw[0].upper() + kw[1:], "effects": [effects[0], {**effects[1], "keywords": [], "abilities": ["Rampage 3"]} if kw == "rampage 3"
                                                              else {**effects[1], "keywords": [kw]}]} for kw in _GABRIEL]
    return {**d, "effects": [{"do": "choose_effect", "who": "self", "options": options}]}


_PIRATE = 'that player creates a 4/2 red Pirate creature token with "This token can\'t block."'
# text (after scripts.self_text) -> (the native wording, how its definition is completed)
_BUILD: dict[str, tuple[str, Any]] = {
    f"Whenever one or more Faeries you control deal combat damage to a player, {_PIRATE} The token is goaded for the rest of the game.":
        (f"Whenever one or more Faeries you control deal combat damage to a player, {_PIRATE}", _nettling),
    "When ~ enters, create a Lander token. At the beginning of the end step on your next turn, sacrifice that token.":
        ("When ~ enters, create a Lander token. At the beginning of your next end step, sacrifice that token.", _kav),
    "When ~ enters, create a tapped Mutavault token.": ("When ~ enters, create a tapped Treasure token.", _mutavault),
    "When ~ enters, mill three cards. Put a land card from among the milled cards into your hand. If you can't, create a Treasure token.":
        ("When ~ enters, mill three cards. You may put a land card from among the milled cards into your hand. If you don't, create a Treasure token.",
         _naturalist),
    "When ~ enters, destroy up to three other target nonland permanents. For each of those permanents, its controller creates a 3/3 white Angel "
    "creature token with flying.": ("When ~ enters, destroy up to three other target nonland permanents.", _emancipation),
    "When ~ enters, surveil 4. When you do, you may return target nonland permanent an opponent controls to its owner's hand.":
        ("When ~ enters, surveil 4.", _dream),
    "Whenever ~ deals combat damage to a player, you may have target land become a Plains until ~ leaves the battlefield.":
        ("Whenever ~ deals combat damage to a player, target land becomes a Plains for as long as ~ remains on the battlefield.", _antelope),
    "Whenever ~ attacks, defending player chooses an untapped creature they control. That creature blocks ~ this turn if able.":
        ("Whenever ~ attacks, defending player chooses an untapped creature they control. Tap that creature.", _boars),
    "At the beginning of your upkeep, target opponent may exile a card from their graveyard. If that player doesn't, you may draw a card.":
        ("At the beginning of your upkeep, target opponent may exile a card from their graveyard. If they don't, you draw a card.", _gravestorm),
    "At the beginning of your upkeep, exile two cards from your graveyard. If you can't, sacrifice ~ and draw a card.":
        ("At the beginning of your upkeep, sacrifice ~ and draw a card.", _upkeep_cost("egon100a")),
    "At the beginning of your upkeep, sacrifice ~ unless you put a card from your graveyard on the bottom of your library.":
        ("At the beginning of your upkeep, sacrifice ~.", _upkeep_cost("scavenger100a")),
    "At the beginning of your upkeep, sacrifice ~ unless you remove a counter from a permanent you control.":
        ("At the beginning of your upkeep, sacrifice ~.", _upkeep_cost("chisei100a")),
    "At the beginning of your upkeep, choose flying, first strike, trample, or rampage 3. ~ gains that ability until your next upkeep.":
        ("At the beginning of your upkeep, ~ gains flying until your next upkeep.", _gabriel),
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != "triggered":
        return None
    text = scripts.self_text(ability.text, ch.name)
    if (built := _BUILD.get(text)) is not None:
        native = scripts.define(replace(ability, text=built[0]), ch)
        return built[1](native) if native is not None else None
    found = _AS.get(text)
    if found is None:
        return None
    native = scripts.define(replace(ability, text=found[0]), ch)
    if native is None:
        return None
    if found[2]:
        return {**native, "effects": list(found[1])}
    return {**native, "effects": [*native["effects"], *found[1]]} if found[1] else native


def plague(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Spreading Plague: bind every other creature on the battlefield sharing a color with the entering creature (as it is, or last existed)."""
    from app.rules import context

    got = context.info(plan, ctx, context.EVENT)
    refs = context._object_refs(ctx, context.EVENT)
    colors = set(got[1].colors) if got is not None else set()
    oid = refs[0].object_id if refs else None
    victims = [c.id for c in plan.state.cards.values() if colors and c.zone.endswith(":battlefield") and plan.in_game(c)
               and plan.oid(c) != oid and (o := plan.ch(c)).is_creature and o.colors & colors]
    context.bind_objects(plan, ctx, "plague100a", victims)
    return True


def emancipate(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Soul of Emancipation: before the destruction, each legal target's controller; the Angels follow it (one creation per player)."""
    from app.rules import effects

    counts: dict[str, int] = {}
    for t in effects.target_refs(ctx, "target:0"):
        card = plan.state.cards.get(t["id"])
        if card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == t.get("object_id"):
            counts[card.controller] = counts.get(card.controller, 0) + 1
    angels = [{"do": "create_token", "who": f"player:{pid}", "n": n, "token": dict(_ANGEL)} for pid, n in counts.items()]
    at = ctx["next"] + 1  # after the destroy instruction that follows this one
    ctx["effects"][at:at] = angels
    return True


def holds(plan: Any, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    return bool(cond.get("always100a"))  # Dream Eater: the surveil always happened (603.12)


def _graveyard(plan: Any, pid: str) -> list[str]:
    return list(plan.state.zones.get(f"{pid}:graveyard", []))


def _ask(plan: Any, ctx: dict[str, Any], step: str, prompt: str, options: list[Any], least: int, most: int) -> bool:
    from app.rules.plan import decide

    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: {prompt}", options=options,
           min_choices=least, max_choices=most, resume={"step": step, "ctx": ctx})
    return False


def _card_options(plan: Any, cards: list[str]) -> list[Any]:
    from app.game.rules_state import DecisionOption

    return [DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in cards]


def egon(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Egon, God of Death: "Exile two cards from your graveyard. If you can't, …" — with two or more cards two must be exiled (no choice to
    decline); with one, none is (the official rulings: you can't exile two, so the rest happens)."""
    from app.rules import context

    gy = _graveyard(plan, ctx["controller"])
    if len(gy) < 2:
        context.bind_flag(ctx, "egon100a", False)
        return True
    if len(gy) == 2:
        _exile_now(plan, ctx, gy)
        return True
    return _ask(plan, ctx, "egon100a", "exile two cards from your graveyard", _card_options(plan, gy), 2, 2)


def _exile_now(plan: Any, ctx: dict[str, Any], cards: list[str]) -> None:
    from app.rules import context

    context.bind_objects(plan, ctx, "egon_cards100a", cards)
    context.bind_flag(ctx, "egon100a", True)
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "exile", "who": "ref:egon_cards100a"}]


def scavenger(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Anurid Scavenger: "… unless you put a card from your graveyard on the bottom of your library" — the controller may (118.12a: none, an
    empty graveyard, is not doing it); the card goes to the bottom of its owner's library (the controller's own graveyard)."""
    from app.rules import context

    gy = _graveyard(plan, ctx["controller"])
    if not gy:
        context.bind_flag(ctx, "scavenger100a", False)
        return True
    return _ask(plan, ctx, "scavenger100a", "put a card from your graveyard on the bottom of your library (none: sacrifice it)",
                _card_options(plan, gy), 0, 1)


def _counter_options(plan: Any, pid: str) -> dict[str, tuple[str, str]]:
    from app.rules import cost_payment

    mine = [c.id for c in plan.state.cards.values() if c.zone == f"{pid}:battlefield" and plan.in_game(c) and any(n > 0 for n in c.counters.values())]
    return cost_payment.counter_tokens(plan, mine)


def chisei(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Chisei, Heart of Oceans: "… unless you remove a counter from a permanent you control" — any one counter of any kind on any one of
    them (122.8), or none (then it's sacrificed)."""
    from app.game.rules_state import DecisionOption
    from app.rules import context

    tokens = _counter_options(plan, ctx["controller"])
    if not tokens:
        context.bind_flag(ctx, "chisei100a", False)
        return True
    seen: dict[tuple[str, str], str] = {}
    for t, key in tokens.items():
        seen.setdefault(key, t)  # one choice per permanent and kind of counter
    options = [DecisionOption(id=t, label=f"{kind} counter on {plan.state.cards[cid].name or 'it'}", card_id=cid) for (cid, kind), t in seen.items()]
    return _ask(plan, ctx, "chisei100a", "remove a counter from a permanent you control (none: sacrifice it)", options, 0, 1)


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, counter_removal_results, effects

    ctx, step = d.resume["ctx"], d.resume["step"]
    valid = {o.id for o in d.options}
    if not set(chosen) <= valid or not d.min_choices <= len(chosen) <= d.max_choices or len(set(chosen)) != len(chosen):
        raise ActionError("Choose from the offered options")
    pid = ctx["controller"]
    if step == "egon100a":
        _exile_now(plan, ctx, [c for c in chosen if c in _graveyard(plan, pid)])
    elif step == "scavenger100a":
        cards = [c for c in chosen if c in _graveyard(plan, pid)]
        for cid in cards:
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "library"}, "position": "bottom"}, actor=pid)
        context.bind_flag(ctx, "scavenger100a", bool(cards))
    else:
        tokens = _counter_options(plan, pid)
        picked = [tokens[t] for t in chosen if t in tokens]
        for cid, kind in picked:
            counter_removal_results.remove(plan, cid, kind, 1, by=pid)
        context.bind_flag(ctx, "chisei100a", bool(picked))
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"plague100a": plague, "emancipate100a": emancipate, "egon100a": egon, "scavenger100a": scavenger, "chisei100a": chisei}
RESUME = {"egon100a": resume, "scavenger100a": resume, "chisei100a": resume}
