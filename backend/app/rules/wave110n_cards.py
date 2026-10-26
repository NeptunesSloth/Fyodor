"""-- wave 110N -- exact Oracle wordings of single cards, built from parts of wordings the grammar already reads.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]

_NATIVE_HEA = ("At the beginning of your upkeep, if there are five colors among permanents you control and your life total is greater than or "
               "equal to your starting life total, you win the game.")
_SIX_TYPES: Def = {"value": {"union_types110n": "you"}, "op": ">=", "n": 6}


def _hea(d: Def) -> Def:
    """Happily Ever After: the middle clause joins the native condition, in the trigger's intervening "if" (603.4) and as it resolves."""
    both = {"all": [*d["if"]["all"][:1], _SIX_TYPES, *d["if"]["all"][1:]]}
    return {**d, "if": both, "effects": [{**e, "cond": both} if e.get("do") == "only_if" else e for e in d["effects"]]}


# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    "At the beginning of your upkeep, if there are five colors among permanents you control, there are six or more card types among permanents you "
    "control and/or cards in your graveyard, and your life total is greater than or equal to your starting life total, you win the game.":
        (_NATIVE_HEA, _hea),
}


ROCK_CAST, ROCK_LANDS = "rock_cast110n", "rock_lands110n"
_FLAGS = {"You can't cast Rock Jockey if you've played a land this turn.": ROCK_CAST,
          "You can't play lands if this creature was cast this turn.": ROCK_LANDS}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if (flag := _FLAGS.get(ability.text.strip())) is not None:
        return {"kind": "static", "static": flag, "effects": []}
    if ability.text.strip() == _BANE:
        return _bane(ability, ch)
    if ability.text.strip() == _FLAYER:
        return _flayer(ability, ch)
    if ability.text.strip() == _LASH:
        return _lash(ability, ch)
    if ability.text.strip() == _SPIRIT:
        return _spirit(ability, ch)
    if ability.text.strip() == _SWARM:
        return _swarm(ability, ch)
    if ability.text.strip() == _ERIETTE:
        return _eriette(ability, ch)
    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def union_types(plan: Any, ctx: Any, v: Def) -> int:
    """205.2a: the card types shared out among the player's permanents and the cards in their graveyard (a card type, not a subtype)."""
    from app.rules.values import CARD_TYPES

    me = ctx["controller"]
    found: set[str] = set()
    for c in plan.state.cards.values():
        if (c.zone == f"{me}:battlefield" and plan.in_game(c)) or c.zone == f"{me}:graveyard":
            found |= {"Kindred" if t == "Tribal" else t for t in plan.ch(c).types if t in CARD_TYPES}
    return len(found)


_DECREE = ("Counter target spell. If a permanent spell is countered this way, exile it instead of putting it into its owner's graveyard. "
           "You may cast that card without paying its mana cost for as long as it remains exiled.")


_SWORD = ("Reveal the top three cards of your library. For each of those cards, put that card into your hand unless any opponent pays 3 life. "
          "Then exile the rest.")


_HEW = ("Sacrifice any number of lands. Reveal the top X cards of your library, where X is the number of lands sacrificed this way. Choose any number of artifact and/or "
        "land cards revealed this way. Put all nonland cards chosen this way onto the battlefield, then put all land cards chosen this way onto the battlefield tapped, "
        "then put the rest on the bottom of your library in a random order.")


def _hew() -> Any:
    """Hew the Entwood: the revealed cards are public, so choosing the nonland artifacts and then the lands (each any number, 700.2) is the one choice made in two
    asks; they enter in that order (the artifacts, then the lands tapped) and the rest go to the bottom in a random order (401.4)."""
    from app.rules import scripts, selectors

    parsed = scripts.parse_effects("Sacrifice any number of lands. Reveal the top X cards of your library, where X is the number of lands sacrificed this way.")
    arts, lands = selectors.parse("nonland artifact card"), selectors.parse("land card")
    if parsed is None or arts is None or lands is None or [e["do"] for e in parsed[0]] != ["sacrifice_choice", "look_top"]:
        return None
    return [*parsed[0], {"do": "pick_looked", "n": 99, "optional": True, "sel": arts.key(), "to": "battlefield", "reveal": False},
            {"do": "pick_looked", "n": 99, "optional": True, "sel": lands.key(), "to": "battlefield_tapped", "reveal": False},
            {"do": "rest_looked", "to": "bottom_random"}], None, False


_VISION = ("Choose a land type and a basic land type. Each land of the first chosen type becomes the second chosen type until end of turn.")


def parse(body: str) -> Any:
    """Exact spell bodies: the parts the grammar reads, joined with the card's own step."""
    from app.rules import scripts

    if body.strip() == _DECREE:
        parsed = scripts.parse_effects("Counter target spell. If that spell is countered this way, exile it instead of putting it into its owner's graveyard. "
                                       "You may cast that card without paying its mana cost for as long as it remains exiled.")
        if parsed is not None and len(parsed[0]) == 2 and parsed[0][0].get("do") == "counter":
            effects, target, optional = parsed
            return [{**effects[0], "do": "decree110n"}, effects[1]], target, optional
    if body.strip() == _VISION:
        return [{"do": "vision110n"}], None, False
    if body.strip() == _HEW:
        return _hew()
    if body.strip() == _SWORD:
        return [{"do": "look_top", "n": 3, "player": "you", "reveal": True, "as": "e0"}, {"do": "sword110n", "who": "ref:e0"}], None, False
    return None


def decree(plan: Any, ctx: Any, e: Def) -> bool:
    """Thranduil's Decree: a permanent spell is exiled instead of going to the graveyard (608.2c, 701.6a); only a card that is in exile because of it may then
    be cast (a nonpermanent spell, or one that can't be countered, leaves "that card" nothing to be cast)."""
    from app.rules import context, effects
    from app.rules.values import PERMANENT_TYPES

    sids = effects._stack_targets(plan, ctx, e)
    perm = bool(sids) and bool(plan.ch(plan.state.cards[sids[0]]).types & PERMANENT_TYPES)
    effects.counter(plan, ctx, {**e, "do": "counter", "to": "exile" if perm else None})
    if not (perm and plan.state.cards[sids[0]].zone.endswith(":exile")):
        context.bind_objects(plan, ctx, e["as"], [])  # nothing was exiled by this: no card to cast
    return True


def sword(plan: Any, ctx: Any, e: Def) -> bool:
    """Sword-Point Diplomacy: for each revealed card in turn, the opponents are offered 3 life in turn order (101.4, 118.12) until one pays; if none does the
    card goes to its controller's hand (still where it was revealed, 400.7), and the rest are exiled at the end. A later opponent is asked only while no
    earlier one has paid: the card is then already kept out of the hand."""
    from app.rules import context

    me = ctx["controller"]
    opponents = [p for p in plan.apnap() if p != me and p in plan.live()]
    steps: list[Def] = []
    cards = [c for c in context.objects(plan, ctx, e["who"][len(context.PREFIX):]) if plan.state.cards[c].zone == f"{me}:library"]
    for i, cid in enumerate(cards):
        binds = [f"sword110n_{i}_{p}" for p in opponents]
        steps.append({"do": "sword_note110n", "card": cid})
        for j, (p, b) in enumerate(zip(opponents, binds, strict=True)):
            if j:
                steps.append({"do": "only_if", "cond": {"not": {"any_paid100j": binds[:j]}}, "skip": 1})
            steps.append({"do": "optional_payment", "who": f"player:{p}", "cost": "Pay 3 life", "bind": b})
        steps += [{"do": "only_if", "cond": {"not": {"any_paid100j": binds}}, "skip": 1}, {"do": "sword_hand110n", "card": cid, "oid": plan.oid(cid)}]
    steps.append({"do": "sword_rest110n", "cards": [[c, plan.oid(c)] for c in cards]})
    ctx["effects"][ctx["next"]:ctx["next"]] = steps
    return True


def sword_note(plan: Any, ctx: Any, e: Def) -> bool:
    plan.note(f"{ctx.get('name') or 'It'}: any opponent may pay 3 life so that {plan.state.cards[e['card']].name} isn't put into hand")
    return True


def sword_hand(plan: Any, ctx: Any, e: Def) -> bool:
    card = plan.state.cards[e["card"]]
    if card.zone == f"{ctx['controller']}:library" and plan.oid(card) == e["oid"]:
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": ctx["controller"], "zone": "hand"}}, actor=ctx["controller"])
    return True


def sword_rest(plan: Any, ctx: Any, e: Def) -> bool:
    left = [c for c, oid in e["cards"] if plan.state.cards[c].zone == f"{ctx['controller']}:library" and plan.oid(c) == oid]
    if left:
        plan.do({"type": "move", "card_ids": left, "to": {"player": ctx["controller"], "zone": "exile"}}, actor=ctx["controller"])
    return True


def _thief(d: Def) -> Def:
    """Thief of Existence: the spell gains the leaves-the-battlefield trigger only if the exile happened, and keeps it as the permanent it becomes (400.7a)."""
    from app.rules import scripts

    grant = scripts.parse_effects('Exile up to one target permanent. If you do, ~ gains "When this creature leaves the battlefield, target opponent draws a card."')
    gains = [e for e in d["effects"] if e.get("do") == "gain_life"]
    if grant is None or len(gains) != 1:
        return d
    return {**d, "effects": [{**grant[0][2], "who": "self_stack"} if e is gains[0] else e for e in d["effects"]]}  # the spell, still on the stack


_BUILD["When you cast this spell, exile up to one target noncreature, nonland permanent an opponent controls with mana value 4 or less. If you do, "
       "Thief of Existence gains \"When this creature leaves the battlefield, target opponent draws a card.\""] = (
    "When you cast this spell, exile up to one target noncreature, nonland permanent an opponent controls with mana value 4 or less. If you do, you gain 1 life.", _thief)


_BANE = ("Whenever another nontoken creature you control dies, target opponent may have you draw a card. If they don't, you may put a creature card "
         "with equal or lesser toughness from your hand onto the battlefield.")


def _bane(ability: Any, ch: Any) -> Def | None:
    """Bane, Lord of Darkness: the targeted opponent answers first (608.2d); "if they don't" the controller may put a creature card from hand whose toughness
    is at most the dead creature's as it last existed (603.10a); "if they do" the controller draws instead."""
    from app.rules import scripts

    head = scripts.define(replace(ability, text="Whenever another nontoken creature you control dies, target opponent loses 1 life."), ch)
    put = scripts.define(replace(ability, text="Whenever another nontoken creature you control dies, you may put a creature card with mana value less than or "
                                 "equal to that creature's mana value from your hand onto the battlefield."), ch)
    if head is None or put is None or put["effects"][0].get("do") != "put_from_hand":
        return None
    card = {k: v for k, v in put["effects"][0].items() if k != "mv"}
    return {**head, "effects": [
        {"do": "optional_payment", "who": "target", "ask": "Have its controller draw a card", "bind": "bane110n"},
        {"do": "only_if", "cond": {"not": {"succeeded": "bane110n"}}, "skip": 1},
        {**card, "tough110n": {"toughness": "event"}},
        {"do": "only_if", "cond": {"succeeded": "bane110n"}, "skip": 1},
        {"do": "draw", "who": "you", "n": 1}]}


_ERIETTE = ("Whenever an Aura you control becomes attached to a nonland permanent an opponent controls with mana value less than or equal to that Aura's "
            "mana value, gain control of that permanent for as long as that Aura is attached to it.")


def _eriette(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    native = scripts.define(replace(ability, text="Whenever an Aura you control becomes attached to a nonland permanent an opponent controls, tap that permanent."), ch)
    if native is None or native.get("cond", {}).get("event") != "attached":
        return None
    return {**native, "effects": [{"do": "eriette110n"}], "cond": {**native["cond"], "host_mv_le_aura110n": True}}


def eriette(plan: Any, ctx: Any, e: Def) -> bool:
    """611.2b: control of the permanent lasts while that very Aura stays attached to it; if the Aura is already gone or elsewhere the duration has ended and
    nothing happens (the permanent is the object the event named, 400.7)."""
    from app.rules import context, effects, layers

    aura = context.info(plan, ctx, context.EVENT_OTHER)
    host = context.info(plan, ctx, context.EVENT)
    if aura is None or host is None:
        return True
    a, h = aura[0], host[0]
    if not (a.zone.endswith(":battlefield") and a.attached_to == h.id and h.zone.endswith(":battlefield") and plan.in_game(h)):
        return True
    effects._control_effect(plan, ctx, [h.id], ctx["controller"], "attached110n")
    plan.rules.effects[-1].until_object = plan.oid(a)
    layers.control_sync(plan)
    return True


def still_attached(plan: Any, e: Any) -> bool:
    aura = next((c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) == e.until_object), None)
    host = plan.state.cards.get(aura.attached_to or "") if aura is not None else None
    return host is not None and host.zone.endswith(":battlefield") and plan.oid(host) in e.affected


_SWARM = ("When this creature dies, distribute three -1/-1 counters among one, two, or three target creatures. For each -1/-1 counter you put on a creature "
          "this way, remove a -1/-1 counter from that creature at the beginning of the next end step.")


def _swarm(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    native = scripts.define(replace(ability, text="When this creature dies, distribute three -1/-1 counters among one, two, or three target creatures."), ch)
    if native is None or [e.get("do") for e in native["effects"]] != ["add_counters"]:
        return None
    return {**native, "effects": [{"do": "swarm_pre110n"}, *native["effects"], {"do": "swarm_post110n"}]}


def swarm_pre(plan: Any, ctx: Any, e: Def) -> bool:
    from app.rules import effects

    ctx["swarm110n"] = {c: plan.state.cards[c].counters.get("-1/-1", 0) for c in effects._cards(plan, ctx, "target:0")}
    return True


def swarm_post(plan: Any, ctx: Any, e: Def) -> bool:
    """Each creature the counters really went on (a replacement may have changed the number, 122.6) loses that many at the next end step (603.7a), if it is
    still that permanent then (400.7)."""
    from app.rules import context, delayed

    for cid, was in ctx.pop("swarm110n", {}).items():
        card = plan.state.cards[cid]
        put = card.counters.get("-1/-1", 0) - was
        if put > 0 and card.zone.endswith(":battlefield"):
            context.bind_objects(plan, ctx, "swarm110n", [cid])
            delayed.create(plan, {**ctx, "next": 0, "effects": [{"do": "remove_counters", "who": "ref:swarm110n", "kind": "-1/-1", "n": put}]},
                           {"do": "delayed", "when": {"kind": "step", "step": "end", "whose": "next"}, "n": 1})
    return True


_SPIRIT = ("At the beginning of your end step, choose target permanent card in your graveyard. You may sacrifice a permanent that shares a card type with the "
           "chosen card. If you do, return the chosen card from your graveyard to the battlefield and it gains \"If this permanent would leave the battlefield, "
           "exile it instead of putting it anywhere else.\"")
_SPIRIT_NATIVE = ("At the beginning of your end step, you may sacrifice a creature. If you do, return target permanent card from your graveyard to the battlefield. "
                  "It gains \"If this permanent would leave the battlefield, exile it instead of putting it anywhere else.\"")


def _spirit(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    native = scripts.define(replace(ability, text=_SPIRIT_NATIVE), ch)
    if native is None or native["effects"][0].get("do") != "optional_payment":
        return None
    return {**native, "effects": [{"do": "spirit110n", "bind": native["effects"][0]["bind"]}, *native["effects"][1:]]}


def _spirit_options(plan: Any, ctx: Any) -> list[str]:
    """The permanents the controller may sacrifice: they share a card type (205.2a) with the chosen card, as it is in the graveyard."""
    from app.rules import effects
    from app.rules.values import CARD_TYPES

    chosen = effects._cards(plan, ctx, "target")
    if len(chosen) != 1 or not plan.state.cards[chosen[0]].zone.endswith(":graveyard"):
        return []
    kinds = {"Kindred" if t == "Tribal" else t for t in plan.ch(plan.state.cards[chosen[0]]).types if t in CARD_TYPES}
    return [c.id for c in plan.state.cards.values() if c.zone == f"{ctx['controller']}:battlefield" and plan.in_game(c)
            and kinds & {"Kindred" if t == "Tribal" else t for t in plan.ch(c).types if t in CARD_TYPES}]


def spirit(plan: Any, ctx: Any, e: Def) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    options = _spirit_options(plan, ctx)
    if not options:
        context.bind_payment(ctx, e["bind"], False)  # 608.2c: no permanent to sacrifice, so "if you do" is not met
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: you may sacrifice a permanent that shares a card type with the chosen card",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Permanent", card_id=c) for c in options], min_choices=0, max_choices=1,
           resume={"step": "spirit110n", "ctx": ctx, "e": e})
    return False


def resume_spirit(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    if chosen and chosen[0] not in _spirit_options(plan, ctx):
        raise ActionError("Choose a permanent that shares a card type with the chosen card")
    done = False
    if chosen:
        effects._sacrifice_cards(plan, chosen[:1], ctx["controller"], ctx)
        done = not plan.state.cards[chosen[0]].zone.endswith(":battlefield")
    context.bind_payment(ctx, e["bind"], done)
    effects.continue_effects(plan, ctx)


UNPAID_CU = "unpaid_cu110n"
_LASH = "When a player doesn't pay this enchantment's cumulative upkeep, that player exiles all cards from their library."


def _lash(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    native = scripts.define(replace(ability, text="At the beginning of your upkeep, exile all cards from your library."), ch)
    if native is None or native.get("trigger") != "upkeep_you":
        return None
    return {**native, "trigger": UNPAID_CU}


def cu_exile(plan: Any, ctx: Any, e: Def) -> bool:
    """Cumulative upkeep—Exile the top card of your library (702.24a): the cost once for each age counter, all of it or none (118.3). Not paying sacrifices the
    enchantment, and Thought Lash's own "doesn't pay" trigger is put on the stack first (603.2: the event is the choice not to pay)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    src = plan.state.cards.get(ctx.get("source_card", ""))
    if src is None or not src.zone.endswith(":battlefield") or plan.oid(src) != ctx.get("source_object"):
        return True
    n = src.counters.get("age", 0)
    if len(plan.state.zones.get(f"{src.controller}:library", [])) < n:
        plan.note(f"{plan.name(src.controller)} can't exile {n} cards from the top of their library")
        _unpaid(plan, ctx, src)
        return True
    decide(plan, player=src.controller, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: exile the top {n} card{'s' if n != 1 else ''} of your library or sacrifice it?",
           options=[DecisionOption(id="pay", label=f"Exile the top {n} card{'s' if n != 1 else ''} of your library"), DecisionOption(id="decline", label=f"Sacrifice {src.name}")],
           resume={"step": "cu_exile110n", "ctx": ctx}, source=src)
    return False


def _unpaid(plan: Any, ctx: Any, src: Any) -> None:
    from app.rules import effects, triggers

    for card, ch, i, d in triggers._watchers(plan, UNPAID_CU):
        if card.id == src.id:
            triggers._add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=i, definition=d)
    effects._sacrifice_cards(plan, [src.id], src.controller, ctx)


def resume_cu_exile(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    src = plan.state.cards.get(ctx.get("source_card", ""))
    if src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
        n = src.counters.get("age", 0)
        library = plan.state.zones.get(f"{src.controller}:library", [])
        if chosen[0] == "pay" and len(library) >= n:
            plan.do({"type": "move", "card_ids": list(library[:n]), "to": {"player": src.controller, "zone": "exile"}}, actor=src.controller)
            plan.note(f"{plan.name(src.controller)} exiles the top {n} card{'s' if n != 1 else ''} of their library to pay for {src.name}")
        else:
            _unpaid(plan, ctx, src)
    effects.continue_effects(plan, ctx)


_FLAYER = ("If a creature card with flying was exiled with this creature's delve ability, this creature has flying. The same is true for first strike, double strike, "
           "deathtouch, haste, hexproof, indestructible, lifelink, reach, trample, and vigilance.")
_FLAYER_KEYWORDS = ["flying", "first strike", "double strike", "deathtouch", "haste", "hexproof", "indestructible", "lifelink", "reach", "trample", "vigilance"]


def _flayer(ability: Any, ch: Any) -> Def | None:
    """Soulflayer: one conditional grant per keyword, each judged on the cards the delve exiled (611.3a), read from the spell's payment record."""
    from app.rules import scripts

    base = scripts.define(replace(ability, text="As long as this creature was cast, this creature has flying."), ch)
    if base is None or base.get("keywords") != ["flying"] or base.get("conditions") != [{"static": "was_cast"}]:
        return None
    parts = [{**base, "keywords": [k], "conditions": [{"static": "delve_kw110n", "kw": k}]} for k in _FLAYER_KEYWORDS]
    return {**parts[0], "also": parts[1:]}


def vision(plan: Any, ctx: Any, e: Def) -> bool:
    """Vision Charm, mode 2: the controller names a land type (205.3i) and a basic land type; every land of the first type on the battlefield as this resolves
    (611.2c: the set is fixed now) is set to the second type until end of turn (305.7: it loses its old land types and what its rules text gave it)."""
    from app.game.rules_state import DecisionOption
    from app.rules.effects import CHOICE_OPTIONS
    from app.rules.plan import decide

    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a land type",
           options=[DecisionOption(id=t, label=t) for t in CHOICE_OPTIONS["land type"]], resume={"step": "vision110n", "ctx": ctx, "stage": 1})
    return False


def resume_vision(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.rules_state import DecisionOption
    from app.rules import context, effects
    from app.rules.effects import CHOICE_OPTIONS
    from app.rules.plan import decide

    ctx = d.resume["ctx"]
    if d.resume["stage"] == 1:
        if chosen[0] not in CHOICE_OPTIONS["land type"]:
            raise ValueError("not an offered land type")
        ctx["vision110n"] = chosen[0]
        plan.note(f"{plan.name(d.player)} chooses {chosen[0]} (land type)", actor=d.player)
        decide(plan, player=d.player, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a basic land type",
               options=[DecisionOption(id=t, label=t) for t in CHOICE_OPTIONS["basic land type"]], resume={"step": "vision110n", "ctx": ctx, "stage": 2})
        return
    if chosen[0] not in CHOICE_OPTIONS["basic land type"]:
        raise ValueError("not an offered basic land type")
    plan.note(f"{plan.name(d.player)} chooses {chosen[0]} (basic land type)", actor=d.player)
    lands = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.in_game(c) and ctx["vision110n"] in plan.ch(c).subtypes
             and plan.ch(c).is_land]
    context.bind_objects(plan, ctx, "vision110n", lands)
    if effects.become(plan, ctx, {"do": "become", "who": "ref:vision110n", "types": [], "land_types": [chosen[0]], "duration": "end_of_turn"}):
        effects.continue_effects(plan, ctx)


def _willow(d: Def) -> Def:
    return {**d, "effects": [{"do": "willow110n", "who": "target"}]}


_BUILD["{G}: Until end of turn, Autumn Willow can be the target of spells and abilities controlled by target player as though it didn't have shroud."] = (
    "{G}: Target player gains 1 life.", _willow)


def willow(plan: Any, ctx: Any, e: Def) -> bool:
    """609.4: for the turn, the chosen player's spells and abilities may target this object although it has shroud (702.18a); the permission is theirs
    and about this object only (400.7), so it ends with the turn or when the Willow leaves."""
    from app.rules import effects

    src = plan.state.cards.get(ctx.get("source_card", ""))
    if src is None or not src.zone.endswith(":battlefield") or plan.oid(src) != ctx.get("source_object"):
        return True
    for pid in effects._players(plan, ctx, e["who"]):
        plan.rules.cast_limits.append({"shroud_ignore110n": {"card": src.id, "oid": plan.oid(src), "player": pid}, "controller": ctx["controller"],
                                       "until": "turn", "turn": plan.state.turn.number, "spells": False, "label": ctx.get("name") or "Targeting permission"})
        plan.note(f"{plan.name(pid)} may target {src.name} as though it didn't have shroud this turn", actor=ctx["controller"])
    return True


def ignores_shroud(plan: Any, chooser: str, card: Any) -> bool:
    from app.rules import cast_limits

    return any(d["player"] == chooser and d["card"] == card.id and d["oid"] == plan.oid(card)
               for x in plan.rules.cast_limits if (d := x.get("shroud_ignore110n")) and cast_limits._record_live(plan.state, x))


def cast_problem(state: Any, player: str, ch: Any) -> str | None:
    """Rock Jockey: 601.3, the spell can't be cast once its caster has played a land this turn (305.1: played, not put onto the battlefield)."""
    from app.rules import scripts

    r = state.rules
    if r is None or not any(d.get("static") == ROCK_CAST for d in scripts.definitions(ch).values()):
        return None
    return f"{ch.name or 'It'} can't be cast if you've played a land this turn" if r.lands_this_turn(player, state.turn.number) else None


def land_problem(state: Any, player: str, info: Any) -> str | None:
    """Rock Jockey: 305.1, no land may be played by its controller while it is on the battlefield and was cast this turn (its spell left a cast
    record that names the permanent it became, 400.7)."""
    from app.rules import static_perm100d
    from app.rules.plan import Plan

    r = state.rules
    log = r.turn_log if r is not None else None
    if info is None or log is None or log.turn != state.turn.number:
        return None
    plan = Plan.view(state, player, info)
    for c in state.cards.values():
        if c.zone == f"{player}:battlefield" and c.controller == player and plan.in_game(c) and static_perm100d._statics(plan, c, ROCK_LANDS) \
                and any(n.became == plan.oid(c) for n in log.casts):
            return f"{c.name}: you can't play lands, it was cast this turn"
    return None


PRIMITIVES: dict[str, Any] = {"decree110n": decree, "willow110n": willow, "vision110n": vision, "cu_exile110n": cu_exile, "spirit110n": spirit, "swarm_pre110n": swarm_pre, "swarm_post110n": swarm_post, "eriette110n": eriette, "sword110n": sword, "sword_note110n": sword_note,
                              "sword_hand110n": sword_hand, "sword_rest110n": sword_rest}
RESUME: dict[str, Any] = {"vision110n": resume_vision, "spirit110n": resume_spirit, "cu_exile110n": resume_cu_exile}
