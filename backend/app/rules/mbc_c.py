"""-- Mystery Booster Commander (wave MBC-C) -- lines of Mystery Booster Commander Edition cards (oval-stamped: Commander-legal), each read in its
exact Oracle wording: a native rewrite whose definition is checked, then spliced; a small dedicated primitive where no native one exists. Reminder
text has no rules meaning (207.2a). CR 2026-09-25.

* Ashaya's Enduring Bond: "Ashaya's Enduring Bond can be your commander." — a deck-construction line (903.3a, read by app/rules/commander.py); in
  the game it does nothing (the sorcery's spell ability is its discover line).
* Zagorka, Mother of Sanctum: "each player may create a tapped land token named Sanctum with "{T}: Add one mana of any color." Each opponent who
  does can't attack you during their next turn." — the native "each player may … Each player who does can't attack you during their next turn"
  (City Hall, Willie Lumpkin); the token is a land with no subtype, its own name (111.4) and the quoted mana ability; it is colorless (111.3). "Each
  opponent who does": you can't attack yourself (506.2), so the restriction binds only opponents either way.
* Tresserhorn's Lord: "sacrifice him unless you sacrifice three creatures, pay 3 life, and have target opponent draw three cards" (118.12).
* Kuroki: the target opponent's "may draw four cards" (608.2d), then a private look at that hand and a free cast from it (608.2g).
* Dragon's Smile: the table alternative cost "{0} … for a spell you cast from exile", once each turn, only during your turns; the combat-damage
  impulse ("that player exiles that many cards …. You may play those cards this turn").
* The Weaver King: mill, then one creature card per opponent put into their graveyard from their library this turn (the turn's log, 400.7).
* The Madcap Jester: a "to_exile" batch from an opponent's library caused by a spell or ability you control (``Event.cause110g``; triggers.py
  ``cause_you_mbc``); "those cards" may be played until the end of your next turn with mana of any type (``spend`` "type").
* Itazura: group_choice's secret numbers, the highest opponent (a tie: you choose), damage, that opponent's free cast from the exiled cards
  (permissions.free_cast ``caster`` "ref:…"), then a card still in exile into your hand.
* Yume: the "first spell during each of your turns has assist" static (a ``spell_keyword`` part, read by casting through cast_limits) and its
  linked cast trigger; the helper's payment is recorded by assist.py on the spell's card for the turn.
* Glava: X of the cast permanent spell / activated ability on the stack becomes 5 (``double_event_x``'s way), optional, once each turn.

-- (wave MBC-D) -- Miss Highwater and Chira, All In, once left by hand here, are automated in app/rules/mbc_d.py (a player leaving the game as an
event with what they controlled, app/rules/left_game.py; every random choice of the engine as one event, app/rules/randomness.py).
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any, TypeGuard

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

Def = dict[str, Any]

ASHAYA = "~ can be your commander."
TRESSERHORN = "When ~ enters, sacrifice ~ unless you sacrifice three creatures, pay 3 life, and have target opponent draw three cards."
KUROKI = ("At the beginning of your end step, target opponent may draw four cards. If they do, look at that player's hand and you may cast a spell "
          "from their hand without paying its mana cost. If they don't, put two +1/+1 counters on ~.")
SMILE_ALT = "Once during each of your turns, you may pay {0} rather than pay the mana cost for a spell you cast from exile."
SMILE_HIT = ("Whenever ~ deals combat damage to a player, that player exiles that many cards from the top of their library. You may play those "
             "cards this turn.")
WEAVER = ("Whenever ~ deals combat damage to a player, they mill that many cards. Then for each opponent, put a creature card from that player's "
          "graveyard that was put there from their library this turn onto the battlefield under your control.")
JESTER = ("Whenever a spell or ability you control causes one or more cards to be exiled from an opponent's library, you may play those cards until "
          "the end of your next turn. Mana of any type can be spent to cast spells this way.")
ITAZURA = ("At the beginning of your upkeep, exile the top three cards of your library. Each opponent secretly chooses a number 0 or greater. Then "
           "those numbers are revealed. Choose an opponent with the highest number. ~ deals that much damage to them, then they may cast a spell from "
           "among those cards without paying its mana cost. You put a card from among them that wasn't cast this way into your hand.")
YUME = ("The first spell you cast during each of your turns has assist. When you cast that spell, if another player spent mana to cast it, you and "
        "that player each draw a card.")
GLAVA = ("Whenever you cast a permanent spell with {X} in its mana cost or activate an ability with {X} in its activation cost that isn't a mana ability, "
         "you may have the value of X become 5. Do this only once each turn.")
ZAGORKA = ('At the beginning of your end step, each player may create a tapped land token named Sanctum with "{T}: Add one mana of any color." '
           "Each opponent who does can't attack you during their next turn.")


def _native(ability: AbilityText, ch: Characteristics, text: str, kind: str | None = None) -> Def | None:
    from app.rules import scripts

    d = scripts.define(replace(ability, text=text, kind=kind or ability.kind), ch)  # type: ignore[arg-type]
    return copy.deepcopy(d) if d is not None else None


def _does(d: Def | None, *names: str) -> TypeGuard[Def]:
    return d is not None and [e.get("do") for e in d.get("effects") or []] == list(names)


def _self_text(ability: AbilityText, ch: Characteristics) -> str:
    from app.rules import scripts

    return scripts.self_text(ability.text.strip(), ch.name)


def definition(ability: AbilityText, ch: Characteristics) -> Def | None:
    """One of the lines of the module docstring, in its exact wording; else None."""
    if ability.index >= 100:
        return None
    text = _self_text(ability, ch)
    if text == ASHAYA and ability.kind == "spell" and ch.is_instant_or_sorcery:
        # 903.3a: deck construction only — a line of the sorcery that instructs nothing as the spell resolves (the whole spell is its discover line)
        return {"kind": "spell", "effects": [], "target": None, "deckbuilding": True}
    if text == ZAGORKA and ability.kind == "triggered":
        return _zagorka(ability, ch)
    if text == TRESSERHORN and ability.kind == "triggered":
        return _tresserhorn(ability, ch)
    if text == KUROKI and ability.kind == "triggered":
        return _kuroki(ability, ch)
    if text == SMILE_ALT and ability.kind == "static":
        d = _native(ability, ch, "Once each turn, you may pay {0} rather than pay the mana cost for a spell you cast from exile.")
        if d is None or d.get("static") != "alt_cost" or not d.get("once") or d.get("zone") != "exile" or d.get("cond") is not None:
            return None
        return {**d, "cond": {"turn": "yours"}}  # ("during each of your turns": offered only in its controller's turn, once each turn)
    if text == SMILE_HIT and ability.kind == "triggered":
        d = _native(ability, ch, "Whenever ~ deals combat damage to a player, exile that many cards from the top of that player's library. You may play "
                                 "those cards this turn.")
        return d if _does(d, "exile_top", "grant_play") and d["effects"][0].get("player") == "event_player" else None
    if text == WEAVER and ability.kind == "triggered":
        d = _native(ability, ch, "Whenever ~ deals combat damage to a player, that player mills that many cards.")
        if not _does(d, "mill") or d["effects"][0].get("who") != "event_player":
            return None
        return {**d, "effects": [*d["effects"], {"do": "weaver_mbc"}]}
    if text == JESTER and ability.kind == "triggered":
        return _jester(ability, ch)
    if text == ITAZURA and ability.kind == "triggered":
        return _itazura(ability, ch)
    if text == YUME and ability.kind == "static":
        return _yume(ability, ch)
    if text == GLAVA and ability.kind == "triggered":
        return _glava(ability, ch)
    return None


def _glava(ability: AbilityText, ch: Characteristics) -> Def | None:
    """One trigger, two events (603.2): a permanent spell you cast with {X} in its mana cost, or a nonmana ability you activate with {X} in its
    activation cost (``activation_cost.has_x``, the activation's own frozen cost facts). "You may have the value of X become 5": the spell's or
    ability's current X on the stack (107.3: the costs already paid stay paid; Unbound Flourishing's ``double_event_x`` way), as the trigger
    resolves while that object is still on the stack. "Do this only once each turn" (603.2h: ``do_once``, counted only when it was done)."""
    from app.rules import activated_copy_effects

    spell = _native(ability, ch, "Whenever you cast a permanent spell with {X} in its mana cost, draw a card.")
    if not _does(spell, "draw") or (spell.get("cond") or {}).get("event") != "cast" or "x_cost" not in str(spell["cond"].get("spell")):
        return None
    act = {**activated_copy_effects.activation_cond(), "activation_cost": {"has_x": True}}
    return {**spell, "optional": True, "limit": "do_once", "cond": {"event": "either", "subject": "player", "conds": [spell["cond"], act]},
            "effects": [{"do": "glava_x_mbc", "n": 5}]}


def glava(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """The X of the spell or ability the trigger is about becomes ``n``, if it is still that object on the stack (400.7)."""
    from app.rules import context
    from app.rules.copying import _copy_sources

    event = ctx.get("event") or {}
    who = "event_ability" if event.get("kind") == "activate" else "event_spell"
    found = [sid for sid, _ in _copy_sources(plan, ctx, who)] if who == "event_ability" else         [c for c in context.objects(plan, ctx, context.EVENT) if plan.state.cards[c].zone == "stack"]
    value = int(e.get("n", 5))
    for cid in [c for c in found if c in plan.state.cards and plan.state.cards[c].zone == "stack"]:
        entry = plan.rules.stack.get(cid)
        if entry is not None:
            entry.x = value
        plan.do({"type": "set_stack_info", "card_id": cid, "x": value})
        plan.note(f"{plan.state.cards[cid].name or 'Its'} X becomes {value}", [cid])
    return True


def _yume(ability: AbilityText, ch: Characteristics) -> Def | None:
    """Two abilities in one paragraph (604.1): the static — the first spell you cast during each of your turns has assist (702.132a) as it is cast
    (a ``spell_keyword`` static read by casting through cast_limits.granted_instances: "first" turn, during your turn) — and its linked trigger
    "When you cast that spell, if another player spent mana to cast it, you and that player each draw a card" (603.4: an intervening "if", checked
    as it triggers and as it resolves): the helper's assist payment is recorded on the spell (app/rules/assist.py)."""
    d = _native(ability, ch, "Whenever you cast your first spell during each of your turns, draw a card.", kind="triggered")
    cond = (d or {}).get("cond") or {}
    if not _does(d, "draw") or cond.get("event") != "cast" or cond.get("nth") != 1 or cond.get("during") != "you":
        return None
    assisted = {"mbcc": "assisted"}
    keyword = {"kind": "static", "static": "spell_keyword", "keyword": "assist", "count": 1, "filter": None, "from": None, "first": "turn",
               "during110c": "your_turn", "effects": []}
    return {**d, "if": assisted, "effects": [{"do": "only_if", "cond": assisted, "skip": 1}, {"do": "yume_mbc"}], "also": [keyword]}


def _assist_helper(plan: Plan, ctx: dict[str, Any]) -> str | None:
    """The other player who spent mana to cast the spell the trigger is about (assist), if any, still in the game."""
    objects = (ctx.get("event") or {}).get("objects") or []
    card = objects[0].get("card") if objects else None
    helper, _, turn = (plan.rules.chosen_players.get(f"{card}:assist") or "").partition(":") if card else ("", "", "")
    # (recorded as "<player>:<turn>" when the helper paid: only this turn's — the trigger is about the first spell cast this turn, 400.7)
    if not helper or turn != str(plan.state.turn.number) or helper == ctx["controller"] or helper not in plan.live():
        return None
    return helper


def holds(plan: Plan, ctx: dict[str, Any], cond: Def) -> bool:
    if cond.get("mbcc") == "assisted":
        return _assist_helper(plan, ctx) is not None
    return False


def yume(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """"you and that player each draw a card" (121.2c: in APNAP order)."""
    from app.rules.effects import PRIMITIVES as EFFECTS

    helper = _assist_helper(plan, ctx)
    if helper is None:
        return True
    for pid in [p for p in plan.apnap() if p in (ctx["controller"], helper)]:
        EFFECTS["draw"](plan, ctx, {"do": "draw", "who": f"player:{pid}", "n": 1})
    return True


def _itazura(ability: AbilityText, ch: Characteristics) -> Def | None:
    """The secret numbers are group_choice's (Wheel of Misfortune's): each opponent's decision goes to them alone and nothing is shown until all
    are in, then all are revealed at once (``gc_choose`` secret, ``gc_extremes``). "Choose an opponent with the highest number": with a tie,
    Itazura's controller chooses among them (608.2d); "that much": the highest number. "they may cast a spell from among those cards": the cards
    exiled this way still in exile, cast by that opponent during the resolution (608.2g; ``free_cast`` with the binding's player as caster).
    "You put a card from among them that wasn't cast this way into your hand": a card still in exile, your choice (none if none is left)."""
    d = _native(ability, ch, "At the beginning of your upkeep, exile the top three cards of your library. You may cast a spell from among cards "
                             "exiled this way without paying its mana cost.")
    if not _does(d, "exile_top", "free_cast") or d["effects"][0].get("as") != "e0" or d["effects"][1].get("who") != "ref:e0":
        return None
    exile, cast = d["effects"]
    return {**d, "effects": [
        exile,
        {"do": "gc_choose", "who": "each_opponent", "what": "number", "min": 0, "secret": True, "as": "gc", "say": "a number"},
        {"do": "gc_extremes", "as": "gc"},
        {"do": "itazura_mbc", "step": "pick"},
        {"do": "damage", "who": "ref:itazura_mbc", "n": {"ref_amount": "gc_hi"}},
        {**cast, "caster": "ref:itazura_mbc"},
        {"do": "itazura_mbc", "step": "keep", "ref": "e0"}]}


def _tresserhorn(ability: AbilityText, ch: Characteristics) -> Def | None:
    """The "unless" is one choice (118.12): sacrifice three creatures, pay 3 life and have the target opponent draw three cards — all of it, only
    if all of it can be done (the costs payable, 118.3); otherwise (declined, or it can't) Tresserhorn's Lord is sacrificed."""
    d = _native(ability, ch, "When ~ enters, sacrifice ~ unless you sacrifice three creatures and pay 3 life.")
    draw = _native(ability, ch, "When ~ enters, target opponent draws three cards.")
    if not _does(d, "optional_payment", "only_if", "sacrifice") or not _does(draw, "draw") or draw.get("target") != {"what": "opponent"}:
        return None
    pay, unless, sac = d["effects"]
    name = pay.get("bind") or "pay0"
    return {**d, "target": draw["target"], "effects": [pay, {"do": "only_if", "cond": {"succeeded": name}, "skip": 1}, draw["effects"][0], unless, sac]}


def _kuroki(ability: AbilityText, ch: Characteristics) -> Def | None:
    """The target opponent chooses as it resolves (608.2d); "If they do": the cards are drawn, then you look at that player's hand (private, 701.20e)
    and may cast a spell from among those cards without paying its mana cost (608.2g, Silent-Blade Oni's native look and cast); "If they don't":
    two +1/+1 counters on Kuroki."""
    look = _native(ability, ch, "At the beginning of your end step, look at target opponent's hand. You may cast a spell from among those cards without "
                                "paying its mana cost.")
    grow = _native(ability, ch, "At the beginning of your end step, put two +1/+1 counters on ~.")
    if not _does(look, "reveal_hand", "free_cast") or not _does(grow, "add_counters") or look.get("target") != {"what": "opponent"}:
        return None
    return {**look, "effects": [
        {"do": "optional_payment", "who": "target", "ask": "Draw four cards (if you don't, Kuroki gets two +1/+1 counters)", "bind": "kuroki_mbc"},
        {"do": "only_if", "cond": {"succeeded": "kuroki_mbc"}, "skip": 3},
        {"do": "draw", "who": "target", "n": 4}, *look["effects"],
        {"do": "only_if", "cond": {"succeeded": "kuroki_mbc", "negate": True}, "skip": 1}, *grow["effects"]]}


def _jester(ability: AbilityText, ch: Characteristics) -> Def | None:
    """A batch of cards put into exile from an opponent's library (a card goes to its owner's exile, so "an opponent's library" is the library of the
    card's owner) by a spell or ability you control: the zone change carries the controller of the resolving spell or ability that moved it
    (``Event.cause110g``; a cost, an SBA or a rule moves none this way). "Those cards": the batch's cards in exile (603.2c, 400.7: the new objects)."""
    grant = _native(ability, ch, "Whenever ~ attacks, exile the top card of each opponent's library. Until the end of your next turn, you may play "
                                 "those cards, and mana of any type can be spent to cast those spells.")
    if not _does(grant, "exile_top", "grant_play") or grant["effects"][1].get("spend") != "type" or grant["effects"][1].get("until") != "end_of_next_turn":
        return None
    shell = _native(ability, ch, "Whenever one or more cards are put into exile from your library and/or your graveyard, you gain 1 life.")
    if shell is None or (shell.get("cond") or {}).get("event") != "to_exile":
        return None
    cond = {**shell["cond"], "froms": ["library"], "from_owner": "opponent", "cause_you_mbc": True, "aggregate": True}
    return {**shell, "cond": cond, "effects": [{**grant["effects"][1], "who": "ref:event"}]}


def _zagorka(ability: AbilityText, ch: Characteristics) -> Def | None:
    d = _native(ability, ch, "At the beginning of your end step, each player may create a tapped Treasure token. Each player who does can't attack "
                             "you during their next turn.")
    land = _native(ability, ch, 'At the beginning of your end step, create a tapped Planet land token named Sanctum with "{T}: Add one mana of any '
                                'color."')
    if d is None or land is None or not _does(d, "each_may") or not _does(land, "create_token") or not d["effects"][0].get("then"):
        return None
    act = d["effects"][0].get("act") or []
    if [e.get("do") for e in act] != ["create_token"]:
        return None
    token = {**land["effects"][0]["token"], "type_line": "Token Land"}  # (no subtype: "a land token named Sanctum")
    d["effects"][0]["act"] = [{**act[0], "token": token, "tapped": True}]
    d["effects"][0]["text"] = 'create a tapped land token named Sanctum with "{T}: Add one mana of any color."'
    return d


# -- helpers ---------------------------------------------------------------------------------------------------------------------------
def _insert(ctx: dict[str, Any], added: list[Def]) -> None:
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]


def _ask(plan: Plan, ctx: dict[str, Any], player: str, prompt: str, cards: list[str], resume: dict[str, Any], *, lo: int, hi: int) -> None:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=player, kind="choose_cards", prompt=f"{ctx.get('name') or 'Choose'}: {prompt}",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in cards],
           min_choices=lo, max_choices=hi, resume={"ctx": ctx, **resume}, source=plan.state.cards.get(ctx.get("source_card") or ""))


# -- The Weaver King: for each opponent, a creature card milled into their graveyard this turn ------------------------------------------------
def _milled_creatures(plan: Plan, pid: str) -> list[str]:
    """The creature cards in ``pid``'s graveyard that were put there from their library this turn: the object each is now is the one that
    arrived from the library (400.7: one that left the graveyard and came back is a new object, put there from elsewhere)."""
    log = plan.rules.turn_log
    if log.turn != plan.state.turn.number:
        return []
    arrived = {a.object_id for a in log.entered_graveyard if a.owner == pid and a.from_zone == "library" and a.object_id}
    gy = plan.state.zones.get(f"{pid}:graveyard", [])
    return [c for c in gy if plan.oid(c) in arrived and plan.ch(plan.state.cards[c]).is_creature]


def weaver(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """"Then for each opponent, put a creature card from that player's graveyard that was put there from their library this turn onto the
    battlefield under your control": you choose one such card in each opponent's graveyard (APNAP order of the opponents; none where there is
    none), then they all enter at once (one instruction, 603.6a)."""
    me = ctx["controller"]
    return _weave(plan, ctx, [p for p in plan.apnap() if p != me], [])


def _weave(plan: Plan, ctx: dict[str, Any], who: list[str], picks: list[str]) -> bool:
    from app.rules import context

    me = ctx["controller"]
    while who:
        pid, who = who[0], who[1:]
        cards = _milled_creatures(plan, pid)
        if len(cards) == 1:
            picks = [*picks, cards[0]]
        elif cards:
            _ask(plan, ctx, me, f"put a creature card from {plan.name(pid)}'s graveyard onto the battlefield", cards,
                 {"step": "weaver_mbc", "who": who, "picks": picks}, lo=1, hi=1)
            return False
    if picks:
        context.bind_objects(plan, ctx, "weaver_mbc", picks)
        _insert(ctx, [{"do": "return_card", "who": "ref:weaver_mbc", "to": "battlefield", "tapped": False, "under": "you"}])
    return True


def _resume_weaver(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    r = d.resume
    if len(chosen) != 1:
        raise ActionError("Choose one card")
    if _weave(plan, r["ctx"], r["who"], [*r["picks"], chosen[0]]):
        effects.continue_effects(plan, r["ctx"])


# -- Itazura: the opponent with the highest number; the card you keep ---------------------------------------------------------------------
def itazura(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    from app.rules import context, effects

    me = ctx["controller"]
    if e["step"] == "pick":
        tied = [p for p in effects._players(plan, ctx, "ref:gc:hi") if p != me]
        if len(tied) <= 1:
            context.refs(ctx)["itazura_mbc"] = {"kind": "players", "players": tied}
            return True
        from app.game.rules_state import DecisionOption
        from app.rules.plan import decide

        decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name') or 'Itazura'}: choose an opponent with the highest number",
               options=[DecisionOption(id=p, label=plan.name(p)) for p in tied], resume={"step": "itazura_mbc", "ctx": ctx},
               source=plan.state.cards.get(ctx.get("source_card") or ""))
        return False
    left = [c for c in context.objects(plan, ctx, e["ref"]) if c in plan.state.cards and plan.state.cards[c].zone.endswith(":exile")]
    if len(left) == 1:
        plan.do({"type": "move", "card_ids": left, "to": {"player": plan.state.cards[left[0]].owner, "zone": "hand"}}, actor=me)
    elif left:
        _ask(plan, ctx, me, "put a card from among them into your hand", left, {"step": "itazura_keep_mbc"}, lo=1, hi=1)
        return False
    return True


def _resume_itazura(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in plan.state.players:
        raise ActionError("Choose one opponent")
    context.refs(ctx)["itazura_mbc"] = {"kind": "players", "players": chosen}
    plan.note(f"{plan.name(d.player)} chooses {plan.name(chosen[0])}", actor=d.player)
    effects.continue_effects(plan, ctx)


def _resume_keep(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1:
        raise ActionError("Choose one card")
    plan.do({"type": "move", "card_ids": chosen, "to": {"player": plan.state.cards[chosen[0]].owner, "zone": "hand"}}, actor=d.player)
    effects.continue_effects(plan, ctx)


PRIMITIVES: dict[str, Any] = {"weaver_mbc": weaver, "itazura_mbc": itazura, "yume_mbc": yume, "glava_x_mbc": glava}
RESUME: dict[str, Any] = {"weaver_mbc": _resume_weaver, "itazura_mbc": _resume_itazura, "itazura_keep_mbc": _resume_keep}
