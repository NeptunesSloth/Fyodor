"""-- wave 110B -- exact Oracle wordings of single cards, read as a wording the grammar already reads (``_AS``) or built from parts of it.

Each entry matches one whole ability's Oracle text exactly (plural names and "and/or" included) and nothing else; any other wording stays
unsupported. Researched against the Comprehensive Rules of 2026-09-25.
"""
from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]


def firebending(line: str) -> int | None:
    """702.189a: N of the one "firebending N" piece of a keyword line ("Trample, firebending 4, haste"), else None."""
    pieces = [p.strip() for p in re.split(r"[,;]\s*", re.sub(r"\s*\([^()]*\)", "", line).strip().rstrip("."))]
    found = [re.fullmatch(r"firebending (\d+)", p.lower()) for p in pieces if p.lower().startswith("firebending")]
    return int(found[0][1]) if len(found) == 1 and found[0] else None


# whole ability text -> the wording the grammar reads for it
_AS: dict[str, str] = {
    # Clive, Ifrit's Dominant (back face Ifrit, Warden of Inferno): the Saga is "Ifrit"; exiled and returned it comes back front face up (712.14, 712.2)
    "II, III — Brimstone — Add {R}{R}{R}{R}. If Ifrit has three or more lore counters on it, exile it, then return it to the battlefield.":
        "II, III — Brimstone — Add {R}{R}{R}{R}. If this Saga has three or more lore counters on it, exile this Saga, then return it to the battlefield.",
    "Exile Stunning Reversal.": "Exile ~.",
    # Desert Warfare: "that many" is the number of Deserts you control (the "five or more" test, 603.4, counts them); "They gain haste" is the tokens' own
    "At the beginning of combat on your turn, if you control five or more Deserts, create that many 1/1 red, green, and white Sand Warrior creature tokens. "
    "They gain haste.":
        "At the beginning of combat on your turn, if you control five or more Deserts, create a 1/1 red, green, and white Sand Warrior creature token with "
        "haste for each Desert you control.",
    # Kitsune Ace: an attacking Vehicle is a creature (301.7), so "that Vehicle" is "that creature"
    "Whenever a Vehicle you control attacks, That Vehicle gains first strike until end of turn.":
        "Whenever a Vehicle you control attacks, that creature gains first strike until end of turn.",
    # Campsite Cuisine: the enchantment itself is no creature, so "a legendary creature you control" is another one; X Foods are "any number of Foods" and
    # X targets are "that many" (the number sacrificed, set as the reflexive trigger is put on the stack, 603.12)
    "Whenever this enchantment or a legendary creature you control enters, create a Food token.":
        "Whenever this enchantment or another legendary creature you control enters, create a Food token.",
    "Whenever you attack, you may sacrifice X Foods. When you do, up to X target attacking creatures each get +3/+3 and gain trample and indestructible "
    "until end of turn.":
        "Whenever you attack, you may sacrifice any number of Foods. When you do, up to that many target attacking creatures each get +3/+3 and gain "
        "trample and indestructible until end of turn.",
    # Plague Reaver: "each other creature you control" is "all other creatures you control" (701.21a)
    "At the beginning of your end step, sacrifice each other creature you control.":
        "At the beginning of your end step, sacrifice all other creatures you control.",
    # Ran and Shaw: one object with a plural name (201.5); "Dragon and/or Lesson" is a card with either subtype
    "When Ran and Shaw enter, if you cast them and there are three or more Dragon and/or Lesson cards in your graveyard, create a token that's a copy "
    "of Ran and Shaw, except it's not legendary.":
        "When this creature enters, if you cast it and there are three or more Dragon or Lesson cards in your graveyard, create a token that's a copy "
        "of this creature, except it's not legendary.",
    # Longhorn Sharpshooter: "it" is the plotted card itself (a source of damage in exile, 120.1)
    "When this card becomes plotted, it deals 2 damage to any target.": "When this card becomes plotted, this creature deals 2 damage to any target.",
    # Prince of Thralls: "that opponent" is the opponent whose permanent went to the graveyard, as "that player"
    "Whenever a permanent an opponent controls is put into a graveyard, put that card onto the battlefield under your control unless that opponent pays 3 life.":
        "Whenever a permanent an opponent controls is put into a graveyard, put that card onto the battlefield under your control unless that player pays 3 life.",
}


def _swap_value(d: Def, old: Def, new: Def) -> Def:
    """The native definition with the one condition value ``old`` read as ``new``."""
    hit = [c for c in d["conditions"] if c.get("value") == old]
    assert len(hit) == 1
    return {**d, "conditions": [{**c, "value": new} if c is hit[0] else c for c in d["conditions"]]}


def _gated(n: int) -> Callable[[Def], Def]:
    """The one kicked gate (a promised gift is a kicked spell, 702.174k) covers the ``n`` instructions after it."""
    return lambda d: {**d, "effects": [{**e, "n": n} if e["do"] == "kicked_gate" else e for e in d["effects"]]}


def _reaver(d: Def) -> Def:
    return {**d, "effects": [{"do": "reaver110b"}]}


def _quake(d: Def) -> Def:
    """Quakebringer (113.6b-style zones): works on the battlefield, or from the graveyard while its controller controls a Giant (603.4 as it triggers)."""
    here = {"object": "self", "test": "on_battlefield"}
    cond = {"any": [here, d["if"]]}
    return {**d, "if": cond, "gy_watch": True, "gy_bf110b": True, "effects": [{**e, "cond": cond} if e["do"] == "only_if" else e for e in d["effects"]]}


def _skyguard(d: Def) -> Def:
    return {**d, "if": {"skyguard110b": True},
            "effects": [{**e, "duration": "end_of_combat"} if e["do"] == "prevent_all" else e for e in d["effects"]]}


def uncounter_by(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Autumn's Veil: until the turn ends, spells ``ctx["controller"]`` controls can't be countered by spells of these colors."""
    r, turn = plan.rules, plan.state.turn.number
    r.results = [x for x in r.results if x["turn"] == turn]
    r.results.append({"player": ctx["controller"], "what": "uncounterable_by", "turn": turn, "colors": e["colors"]})
    return True


def shielded(plan: Any, card: Any, source: str) -> bool:
    """Is ``card`` (on the stack) protected from being countered by ``source``, a spell of a listed color (Autumn's Veil)?"""
    src = plan.state.cards.get(source)
    if src is None or src.zone != "stack" or src.ability is not None:
        return False
    turn, colors = plan.state.turn.number, set(plan.ch(src).colors)
    return any(x.get("what") == "uncounterable_by" and x["turn"] == turn and x["player"] == card.controller and colors & set(x["colors"])
               for x in plan.rules.results)


def stolen_holds(plan: Any, ctx: dict[str, Any]) -> bool:
    """Bronze Bombshell: its controller is not its owner (603.8, 108.3)."""
    c = plan.state.cards[ctx["source_card"]]
    return c.controller != c.owner


_WORLD = ("After the second main phase this turn, there's an additional combat phase followed by an additional main phase. "
          "At the beginning of that combat, untap all creatures that attacked this turn.")
_WORLD_NATIVE = ("After this main phase, there is an additional combat phase followed by an additional main phase. "
                 "At the beginning of that combat, untap all creatures that attacked this turn.")


def second_main(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """World at War: 500.8, the additional phases come after the postcombat main phase of this turn. In it they are added now; before it (precombat main, combat,
    or an upkeep when rebounded) a delayed trigger adds them as that phase begins (603.7); after it nothing is left to add them to."""
    from app.rules import delayed, effects

    if plan.state.turn.phase == "main2":
        return all(effects.PRIMITIVES[x["do"]](plan, ctx, x) is not False for x in e["effects"])
    if plan.state.turn.phase in ("upkeep", "draw", "main1", "begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat"):
        return delayed.create(plan, {**ctx, "effects": e["effects"], "next": 0},
                              {"n": 1, "when": {"kind": "step", "step": "main2", "whose": "next"}})
    return True


def nelly_draw(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Nelly Borca: you and the controller of the creatures that dealt the damage (as they last existed, 608.2h) each draw a card."""
    from app.rules import context, effects

    mine = ctx["controller"]
    others = [c.controller for c, _ in context.infos(plan, ctx, context.EVENT) if c.controller != mine]
    for pid in dict.fromkeys([mine, *others]):
        if pid in plan.live():
            effects.PRIMITIVES["draw"](plan, ctx, {"do": "draw", "who": f"player:{pid}", "n": 1})
    return True


def adapt_free(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Biomancer's Familiar: the next time the target creature adapts this turn it adapts as though it had no +1/+1 counters (701.46a)."""
    from app.game.rules_state import turn_log_now
    from app.rules import effects

    log = turn_log_now(plan.state)
    if log is not None:
        log.adapt_free110b += [plan.oid(c) for c in effects._cards(plan, ctx, e["who"])]
    return True


def adapt_free_used(plan: Any, ctx: dict[str, Any]) -> bool:
    """The creature adapting (the source of the adapt ability) has the effect waiting: it is used up (614.5)."""
    from app.game.rules_state import turn_log_now

    log = turn_log_now(plan.state)
    oid = ctx.get("source_object")
    if log is None or oid not in log.adapt_free110b:
        return False
    log.adapt_free110b.remove(oid)
    return True


def lolth_lost(plan: Any, ctx: dict[str, Any]) -> int:
    """Life the damaged player (the event's player) has lost this turn, combat damage just dealt included (119.3)."""
    from app.rules import history

    return sum(history.log_for(plan).lost.get(p, 0) for p in ctx["event"]["players"])


def lolth_loss(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Lolth's emblem: that player loses life equal to the difference between 8 and the life they have lost this turn (checked again as it resolves, 603.4)."""
    from app.rules import effects

    n = 8 - lolth_lost(plan, ctx)
    return n <= 0 or effects.PRIMITIVES["lose_life"](plan, ctx, {"do": "lose_life", "who": "event_player", "n": n})


def skyguard_holds(plan: Any, ctx: dict[str, Any]) -> bool:
    """Suppressor Skyguard: the attacking player (the active player, 508.1) has an opponent other than the Skyguard's controller who is not being
    attacked (508.3d: a player is attacked by a creature attacking them or a planeswalker or battle they control)."""
    me, atk = ctx["controller"], plan.active
    attacked = set()
    for c in plan.state.cards.values():
        if c.attacking is not None and c.controller == atk:
            attacked.add(c.attacking.id if c.attacking.kind == "player" else plan.state.cards[c.attacking.id].controller)
    return any(p != atk and p != me and not plan.state.players[p].left and p not in attacked for p in plan.state.players)


def _still_here(d: Def) -> Def:
    """The delayed trigger has an intervening "if" this creature is still on the battlefield (603.4, 603.7)."""
    hit = [e for e in d["effects"] if e["do"] == "delayed"]
    assert len(hit) == 1
    hit[0]["when"] = {**hit[0]["when"], "if": {"object": "self", "test": "on_battlefield"}}
    return d


def _lich(d: Def) -> Def:
    """Lich's Mastery: one exile per life lost (608.2c), of a permanent, a card in hand or a card in the graveyard."""
    return {**d, "effects": [{"do": "repeat", "n": {"event_amount": 1}, "span": 1}, {"do": "exile_own110b"}]}


# whole ability text -> (the wording the grammar reads, what to change in its definition)
def _electro(d: Def) -> Def:
    return {**d, "effects": [d["effects"][0], {**d["effects"][1], "n": {"turn_history": "excess_obj110b", "object": "event"}}]}


def _warriors(d: Def) -> Def:
    """Dalkovan Encampment: the tokens the turn-long trigger makes are sacrificed at the next end step (603.7: that delayed trigger is made when each fires)."""
    watch, make = d["effects"]
    return {**d, "effects": [{**watch, "n": 3}, {**make, "as": "tok110b"}, {"do": "deferred:delayed", "when": {"kind": "step", "step": "end", "whose": "next"}, "n": 1},
                             {"do": "deferred:deferred:sacrifice", "who": "ref:tok110b"}]}


def _inheritance(d: Def) -> Def:
    """Expedited Inheritance: the damaged creature's controller (not the enchantment's) chooses, exiles from their own library and plays those cards (a card's owner, 400.3)."""
    exile, grant = d["effects"]
    ask = {"do": "optional_payment", "who": "ref:event.controller", "ask": "exile that many cards from the top of your library", "cost": "", "bind": "pay110b"}
    return {**d, "optional": False, "effects": [ask, {"do": "only_if", "cond": {"succeeded": "pay110b"}, "skip": 2},
                                                {**exile, "player": "ref:event.controller"}, {**grant, "owner": True, "optional": True}]}


def _battleshaper(d: Def) -> Def:
    """Boros Battleshaper: two "up to one" targets; 508.1d / 509.1c the first must attack or block if able, 508.1c the second can't attack or block, both this combat only."""
    force, = d["effects"]
    return {**d, "effects": [{**force, "rules": ["must_attack", "must_block"]}, {**force, "who": "target:1", "rules": ["cant_attack_or_block"]}],
            "targets": [d["targets"][0], dict(d["targets"][0])]}


def _mirror(d: Def) -> Def:
    """Mirror of Life Trapping (607.2a linked exile): returning the cards exiled with it first is the same as returning "all other" ones after the exile."""
    from app.rules import selectors

    sel = selectors.parse("permanent card")
    assert sel is not None
    key = sel.key()
    back = {"do": "return_card", "who": f"exiled_with:{key}", "to": "battlefield", "tapped": False, "under": "owner"}
    gate, exile = d["effects"]
    return {**d, "effects": [{**gate, "skip": 2}, back, {**exile, "link": True}], "accumulating_link": True}


def _sponsor(d: Def) -> Def:
    """Scholarship Sponsor: the search of "each player who controls fewer lands than you" (a native reading) is sized per player by ``gap_search110b``."""
    where, search = d["effects"]
    assert where["do"] == "players_where" and search["do"] == "search"
    return {**d, "effects": [{"do": "gap_search110b", "search": {k: v for k, v in search.items() if k not in ("who", "max")}}]}


def gap_search(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Scholarship Sponsor: each player (in turn order, 101.4) who controls fewer lands than the player who controls the most searches for up to as many
    basic lands as the difference (701.23), put onto the battlefield tapped; counted once, before any search (608.2c)."""
    lands = {p: sum(1 for c in plan.state.cards.values() if c.controller == p and c.zone.endswith(":battlefield") and "Land" in plan.ch(c).types)
             for p in plan.apnap() if not plan.state.players[p].left}
    most = max(lands.values(), default=0)
    at = ctx["next"]
    ctx["effects"][at:at] = [{**e["search"], "who": f"player:{p}", "max": most - lands[p]} for p in plan.apnap() if p in lands and lands[p] < most]
    return True


def _intervention(d: Def) -> Def:
    """Cosmic Intervention: 614.1a the replacement covers every permanent you control (a "die" replacement is the creature case of it)."""
    from app.rules import selectors

    gone, = d["effects"]
    sel = selectors.parse("permanent you control")
    assert gone["do"] == "exile_if_dies" and sel is not None
    return {**d, "effects": [{**gone, "each": sel.key(), "return110b": True}]}


def return_next_end(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Cosmic Intervention (603.7, 400.7): the card the replacement exiled returns under its owner's control at the beginning of the next end step; a token
    ceased to exist in exile (111.7), and a card that has moved again is another object."""
    from app.game.rules_state import ObjectRef
    from app.rules import delayed

    card = plan.state.cards.get(e["card"])
    if card is None or card.is_token or not card.zone.endswith(":exile"):
        return True
    ref = ObjectRef(card=card.id, object_id=plan.oid(card), zone=card.zone).model_dump(mode="json")
    delayed.create_plain(plan, ctx["controller"], ctx.get("source_card") or "", ctx.get("source_object") or "", ctx.get("name") or "",
                         {"kind": "step", "step": "end", "whose": "next"},
                         [{"do": "bind_refs", "refs": {"ret110b": {"kind": "objects", "objects": [ref]}}},
                          {"do": "return_card", "who": "ref:ret110b", "to": "battlefield", "tapped": False, "under": "owner"}])
    return True


def _towershell(d: Def) -> Def:
    """603.7, 508.4: the delayed return waits for the declare attackers step of its controller's next turn, and the creature enters attacking."""
    out = []
    for e in d["effects"]:
        if e["do"] == "delayed":
            e = {**e, "when": {**e["when"], "step": "declare_attackers"}}
        elif e["do"] == "deferred:return_card":
            e = {**e, "attacking": True}
        out.append(e)
    return {**d, "effects": out}


def _tombspawn(d: Def) -> Def:
    """Tombstone Stairwell: each player's own count of creature cards in their graveyard (608.2h, all counted before any token is made); the tokens are remembered."""
    make = {**d["effects"][0], "as": "tombspawn110b", "n": {"per_player": {"count": 'sel:{"card":true,"types":["Creature"],"zone_owner":"you","zones":["graveyard"]}'}}}
    return {**d, "if": {"object": "self", "test": "on_battlefield"},
            "effects": [make, {"do": "name_relation", "kind": "record_created_tokens", "who": "ref:tombspawn110b"}]}


def destroy_created(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Destroy every token still on the battlefield that this source's earlier ability made (the "can't be regenerated" sentence follows, 701.8c)."""
    from app.rules import context, exiled_with

    saved = plan.rules.created_with.get(exiled_with.link_key(ctx), [])
    ids = [oid.rsplit(".", 1)[0] for oid in saved if (card := plan.state.cards.get(oid.rsplit(".", 1)[0])) is not None
           and card.zone.endswith(":battlefield") and plan.oid(card) == oid]
    context.bind_objects(plan, ctx, "tombspawn_tokens", ids)
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], {"do": "destroy", "who": "ref:tombspawn_tokens"}, *ctx["effects"][at:]]
    return True


def _had_to(d: Def) -> Def:
    def swap(c: Any) -> Any:
        return {**c, "what": "had_to_attack110b"} if isinstance(c, dict) and c.get("what") == "attacked" else c

    return {**d, "if": swap(d["if"]), "effects": [{**e, "cond": swap(e["cond"])} if "cond" in e else e for e in d["effects"]]}


def _slicer(d: Def) -> Def:
    from app.rules import scripts

    more = scripts.parse_effects("Untap this creature. Goad it.")
    bar = scripts.parse_effects('This creature gains "This creature can\'t be sacrificed" until end of turn.')
    back = scripts.parse_effects("Transform this creature.")
    assert more and bar and back
    return {**d, "optional": False, "effects": [{"do": "slicer110b", "yes": [*d["effects"], *more[0], *bar[0]], "no": back[0]}]}


def slicer(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Slicer: "you may have that player gain control of Slicer ... If you don't, convert it" - 603.5 the choice is made as it resolves; both branches are fixed effects."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=ctx["controller"], kind="confirm", prompt=f"Have that player gain control of {ctx.get('name') or 'it'} until end of turn? (If not, convert it.)",
           options=[DecisionOption(id="yes", label="Yes, they gain control"), DecisionOption(id="no", label="No, convert it")], resume={"step": "slicer110b", "ctx": ctx, "e": e})
    return False


def resume_slicer(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects
    from app.rules.exile_packet_continuations import insert

    ctx, e = d.resume["ctx"], d.resume["e"]
    insert(ctx, list(e["yes"] if chosen == ["yes"] else e["no"]))
    effects.continue_effects(plan, ctx)


def _niv(d: Def) -> Def:
    """Niv-Mizzet Reborn: one pick per color pair, a card of exactly those two colors (105.2) among the revealed cards; no card of a pair, no pick (608.2d)."""
    from itertools import combinations

    from app.rules import selectors

    two = selectors.parse("card that's exactly two colors")
    assert two is not None
    pick = next(e for e in d["effects"] if e.get("do") == "pick_looked")
    picks = [{**pick, "sel": selectors.replace(two, not_colors=tuple(c for c in "WUBRG" if c not in pair)).key()}
             for pair in combinations("WUBRG", 2)]
    return {**d, "effects": [x for e in d["effects"] for x in (picks if e is pick else [e])]}


def _anchor(d: Def) -> Def:
    return {**d, "cond": {**d["cond"], "event": "scry_bottom110b"}, "effects": [{"do": "exile_bottom110b", "n": {"event_amount": 1}}]}


def note_scry_bottom(plan: Any, pid: str, chosen: list[str]) -> None:
    """701.22a: the cards a scry put on the bottom of its library (those that got there), as one event."""
    from app.game.rules_state import emit

    n = sum(1 for c in chosen if plan.state.cards[c].zone == f"{pid}:library")
    if n:
        emit(plan.state, "designation", counter="scry_bottom110b", player=pid, amount=n)


def exile_bottom(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The Temporal Anchor: exile that many cards from the bottom of your library (400.1), linked to the source for "cards exiled with" (607.2a)."""
    from app.rules import effects, exiled_with

    pid = ctx["controller"]
    n = max(0, int(effects._amount(plan, ctx, e["n"])))
    cards = list(plan.state.zones.get(f"{pid}:library", []))[::-1][:n] if n else []
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"player": pid, "zone": "exile"}}, actor=pid)
        exiled_with.record(plan, ctx, [c for c in cards if plan.state.cards[c].zone.endswith(":exile")])
    return True


_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    # Braided Net: 611.2b the lock lasts for as long as that permanent remains tapped (delayed.expire, duration "object_tapped110m"; the restriction is on that object, 400.7)
    "{T}, Remove a net counter from this artifact: Tap another target nonland permanent. Its activated abilities can't be activated for as long as it remains tapped.":
        ("{T}, Remove a net counter from this artifact: Tap another target nonland permanent. Its activated abilities can't be activated this turn.",
         lambda d: {**d, "effects": [{**e, "duration": "object_tapped110m"} if e.get("do") == "restrict" else e for e in d["effects"]]}),
    # Fractured Powerstone: 901.3 the planar die is Planechase game material and 706.7 only a Planechase game rolls it; ruling 2012-06-01: in other games the
    # roll "will have no effect" (no die is rolled, so no roll trigger, no Night Shift payment: ruling 2022-10-07 speaks only of a Planechase game)
    "{T}: Roll the planar die. Activate only as a sorcery.":
        ("{T}: Draw a card. Activate only as a sorcery.", lambda d: {**d, "effects": [{"do": "planechase_only"}]}),
    "Whenever you choose to put one or more cards on the bottom of your library while scrying, exile that many cards from the bottom of your library.":
        ("Whenever you scry, draw a card.", _anchor),
    "When Niv-Mizzet enters, reveal the top ten cards of your library. For each color pair, choose a card that's exactly those colors from among them. Put the chosen cards into your hand and the rest on the bottom of your library in a random order.":
        ("When Niv-Mizzet enters, reveal the top ten cards of your library. Put a creature card from among them into your hand and the rest on the bottom of your library in a random order.", _niv),
    # Slicer, Hired Muscle: 613.1b/e control until end of turn, 701.39 goad, 701.21 sacrifice barred, 701.28 convert (a transform); the "may" is asked first, then one of two branches
    "At the beginning of each opponent's upkeep, you may have that player gain control of Slicer until end of turn. If you do, untap Slicer, goad it, and it can't be sacrificed this turn. If you don't, convert it.":
        ("At the beginning of each opponent's upkeep, that player gains control of this creature until end of turn.", lambda d: _slicer(d)),
    # Summon: Brynhildr chapter I: the exiled card is playable in turns you put a lore counter on this Saga (the permission's "when", read at play time as Robber of the Rich's)
    "I \u2014 Chain \u2014 Exile the top card of your library. During any turn you put a lore counter on this Saga, you may play that card.":
        ("I \u2014 Exile the top card of your library. You may play that card for as long as it remains exiled.",
         lambda d: {**d, "effects": [{**e, "when": {"history": "lore_put110b"}} if e.get("do") == "grant_play" else e for e in d["effects"]]}),
    # Bladegriff Prototype: the damaged player picks the target (the trigger's controller still controls the ability, 115.1, 603.3d: "target_choice")
    "Whenever this creature deals combat damage to a player, destroy target nonland permanent of that player's choice that one of your opponents controls.":
        ("Whenever this creature deals combat damage to a player, destroy target nonland permanent an opponent controls.",
         lambda d: {**d, "target_choice": "event_player"}),
    "Whenever a creature deals combat damage to one of your opponents, if that creature had to attack this combat, you put a +1/+1 counter on Firkraag and you draw a card.":
        ("Whenever a creature deals combat damage to one of your opponents, if that creature attacked this turn, you put a +1/+1 counter on Firkraag and you draw a card.", _had_to),
    "At the beginning of each upkeep, if this enchantment is on the battlefield, each player creates a 2/2 black Zombie creature token with haste named Tombspawn for each "
    "creature card in their graveyard.":
        ("At the beginning of each upkeep, each player creates a 2/2 black Zombie creature token with haste named Tombspawn.", _tombspawn),
    # 603.2 one ability, two events (the end step half is the last, as at_step_generic reads a "multi:" trigger)
    "At the beginning of each end step and when this enchantment leaves the battlefield, destroy all tokens created with this enchantment. They can't be regenerated.":
        ("When this enchantment leaves the battlefield, destroy all tokens. They can't be regenerated.",
         lambda d: {**d, "trigger": "multi:ltb_self+step:end:each", "effects": [{"do": "destroy_created110b"}, {"do": "no_regen"}]}),
    # Marchesa, Resolute Monarch: 603.4 intervening "if" over Rules.hit110b (kept across turns: other players' turns come between)
    "At the beginning of your upkeep, if you haven't been dealt combat damage since your last turn, you draw a card and you lose 1 life.":
        ("At the beginning of your upkeep, you draw a card and you lose 1 life.", lambda d: {**d, "if": {"history": "unhit110b"}}),
    # Behemoth of Vault 0: 118.12 the energy paid is the target's mana value; the destruction follows the payment (the target is the dies trigger's own)
    "When this creature dies, you may pay an amount of {E} equal to target nonland permanent's mana value. When you do, destroy that permanent.":
        ("When this creature dies, you may pay {E}. If you do, destroy target nonland permanent.",
         lambda d: {**d, "effects": [{**d["effects"][0], "cost": "", "energy_n": {"mana_value": "target"}}, *d["effects"][1:]]}),
    "{T}: The next time target creature adapts this turn, it adapts as though it had no +1/+1 counters on it.":
        ("{T}: Target creature gains haste until end of turn.", lambda d: {**d, "effects": [{"do": "adapt_free110b", "who": "target"}]}),
    "Whenever one or more creatures an opponent controls deal combat damage to one or more of your opponents, you and the controller of those creatures each draw a card.":
        ("Whenever one or more creatures an opponent controls deal combat damage to one or more of your opponents, you draw a card.",
         lambda d: {**d, "effects": [{"do": "nelly_draw110b"}]}),
    # Lolth's emblem (-8): 603.4 intervening "if" (conditions "lolth110b"), the loss is the difference to 8 (119.3: life lost counts all of this turn's)
    "Whenever an opponent is dealt combat damage by one or more creatures you control, if that player lost less than 8 life this turn, they lose life equal to the difference.":
        ("Whenever one or more creatures you control deal combat damage to an opponent, that player loses 1 life.",
         lambda d: {**d, "if": {"lolth110b": True}, "effects": [{"do": "lolth_loss110b"}]}),
    # Ramses: 603.4 the intervening "if" is judged with the player who lost as the event player (history._attacked_by, 508.1); 104.3a / 800.4: you win
    "Whenever a player loses the game, if they were attacked this turn by an Assassin you controlled, you win the game.":
        ("Whenever a player loses the game, put five +1/+1 counters on ~.",
         lambda d: {**d, "if": {"history": "attacked_by110b", "sel": 'sel:{"subtypes":["Assassin"]}'}, "effects": [{"do": "win_game", "who": "you"}]}),
    # Saproling Infestation: 702.33d a player "kicks" a spell as they cast it kicked; a spell kicked several times (multikicker, two kicker costs)
    # is that many kicks, so it triggers once per kick (603.2c)
    "Whenever a player kicks a spell, you create a 1/1 green Saproling creature token.":
        ("Whenever a player casts a kicked spell, you create a 1/1 green Saproling creature token.",
         lambda d: {**d, "cond": {**d["cond"], "per_kicker": True}}),
    # Alania: the intervening "if" is a fact about the turn's casts (triggers.alania_first), judged as the spell is cast (603.4); the rest reads natively
    "Whenever you cast a spell, if it's the first instant spell, the first sorcery spell, or the first Otter spell other than Alania you've cast this turn, "
    "you may have target opponent draw a card. If you do, copy that spell. You may choose new targets for the copy.":
        ("Whenever you cast a spell, you may have target opponent draw a card. If you do, copy that spell and you may choose new targets for the copy.",
         lambda d: {**d, "cond": {**d["cond"], "alania110b": True}}),
    # Mana Web: "a land an opponent controls is tapped for mana" is an opponent tapping a land for mana (605.1a: only its controller activates it)
    "Whenever a land an opponent controls is tapped for mana, tap all lands that player controls that could produce any type of mana that land could produce.":
        ("Whenever an opponent taps a land for mana, tap all lands that player controls.", lambda d: {**d, "effects": [{"do": "mana_web110b"}]}),
    # Senu: works only from exile (113.6k); "put it onto the battlefield attacking" (508.4: its controller chooses whom it attacks), untapped
    "When a legendary creature you control attacks and isn't blocked, if this card is exiled, put it onto the battlefield attacking.":
        ("When a legendary creature you control attacks and isn't blocked, you gain 1 life.",
         lambda d: {**d, "ex110b": True, "if": {"object": "self", "test": "in_exile110b"},
                    "effects": [{"do": "return_card", "who": "self_exile", "to": "battlefield", "attacking": True}]}),
    # Lathiel: "up to that many" = life gained this turn (the value is read as the trigger goes on the stack, 601.2d/608.2d); any number of targets (115.6) may be none
    "At the beginning of each end step, if you gained life this turn, distribute up to that many +1/+1 counters among any number of other target creatures.":
        ("At the beginning of each end step, if you gained life this turn, distribute X +1/+1 counters among any number of other target creatures, where X is the "
         "amount of life you gained this turn.",
         lambda d: {**d, "targets": [{**d["targets"][0], "min": 0, "divide": {**d["targets"][0]["divide"], "upto110b": True, "allow_zero_targets": True}}]}),
    "At the beginning of your end step, choose an opponent. At the beginning of that player's next end step, you draw a card if they didn't attack you that turn. "
    "Otherwise, create three 1/1 white Human Soldier creature tokens.":
        ("At the beginning of your end step, choose an opponent.",
         lambda d: {**d, "effects": [{**d["effects"][0], "as": "faramir_opp"}, {"do": "faramir_set110b", "who": "ref:faramir_opp"}]}),
    # Overencumbered: the enchanted opponent (702.5d) creates the tokens; 508.1d / 509.1a restrict: "creatures can't attack this combat", unless that player pays {1}
    # for each artifact they control (601.2h-like optional payment, counted when the trigger resolves)
    "When this Aura enters, enchanted opponent creates a Clue token, a Food token, and a Junk token.":
        ("When this Aura enters, you create a Clue token, a Food token, and a Junk token.",
         lambda d: {**d, "effects": [{**e, "who": "enchanted_player"} if e["do"] == "create_token" else e for e in d["effects"]]}),
    "At the beginning of combat on enchanted opponent's turn, that player may pay {1} for each artifact they control. If they don't, creatures can't attack "
    "this combat.":
        ("At the beginning of enchanted player's upkeep, that player may pay {1}. If they don't, you draw a card.",
         lambda d: {**d, "trigger": "step:begin_combat:enchanted_player", "effects": [
             {**d["effects"][0], "cost": "", "per": "{1}", "n": {"for_player": "event", "of": {"count": 'sel:{"controller":"you","types":["Artifact"]}'}}},
             d["effects"][1], {"do": "restrict", "who": 'sel:{"types":["Creature"]}', "rules": ["cant_attack"], "duration": "end_of_combat"}]}),
    "Whenever one or more creatures you control deal combat damage to a player, you may return one of them to its owner's hand. If you do, you may activate "
    "loyalty abilities of Kaito twice this turn rather than only once.":
        ("Whenever one or more creatures you control deal combat damage to a player, you draw a card.",
         lambda d: {**d, "effects": [{"do": "kaito110b"}]}),
    # Curator of Sun's Creation: 701.57 the new discover uses the triggering discover's N (event amount)
    "Whenever you discover, discover again for the same value. This ability triggers only once each turn.":
        ("Whenever you discover, discover 3. This ability triggers only once each turn.",
         lambda d: {**d, "effects": [{**e, "n": {"event_amount": 1}} if e["do"] == "discover" else e for e in d["effects"]]}),
    # Weeping Angel: 205.1b the Angel loses the creature type until end of turn (it stays a permanent with its other types)
    "Whenever an opponent casts a creature spell, this creature isn't a creature until end of turn.":
        ("Whenever an opponent casts a creature spell, this creature becomes an artifact until end of turn.",
         lambda d: {**d, "effects": [{"do": "become", "who": "self", "remove_types": ["Creature"], "duration": "end_of_turn"}]}),
    # Linvala, Shield of Sea Gate: 611.2a, 113.3: restricted until her controller's next turn, both rules on the one target
    "At the beginning of combat on your turn, if you have a full party, choose target nonland permanent an opponent controls. Until your next turn, it can't "
    "attack or block, and its activated abilities can't be activated.":
        ("At the beginning of combat on your turn, if you have a full party, until your next turn, target nonland permanent an opponent controls can't attack or block.",
         lambda d: {**d, "effects": [{**e, "n": 2} if e["do"] == "until" else e for e in d["effects"]] + [{"do": "restrict", "who": "target", "rules": ["cant_activate"]}]}),
    # Nissa of Shadowed Boughs: "you may have it become" asks before the become + "still a land" pair (unless_pays.may_rest skip 2), 205.1b
    "+1: Untap target land you control. You may have it become a 3/3 Elemental creature with haste and menace until end of turn. It's still a land.":
        ("+1: Untap target land you control. It becomes a 3/3 Elemental creature with haste and menace until end of turn. It's still a land.",
         lambda d: {**d, "effects": [d["effects"][0], {"do": "may_rest", "skip": 2, "label": "Make it a 3/3 Elemental creature"}, *d["effects"][1:]]}),
    "\u22125: You may put a creature card with mana value less than or equal to the number of lands you control onto the battlefield from your hand or "
    "graveyard with two +1/+1 counters on it.":
        ("-5: Put a creature card with mana value less than or equal to the number of lands you control from your hand or graveyard onto the battlefield "
         "with two +1/+1 counters on it.", lambda d: {**d, "effects": [{"do": "may_rest"}, *d["effects"]]}),
    # Meandering Towershell
    "Whenever this creature attacks, exile it. Return it to the battlefield under your control tapped and attacking at the beginning of the declare "
    "attackers step on your next turn.":
        ("Whenever this creature attacks, exile it. Return it to the battlefield under your control tapped at the beginning of your next end step.", _towershell),
    # Autumn's Veil: 101.2, 701.6 its controller's spells can't be countered by blue or black spells this turn (shielded), plus the targeting half
    "Spells you control can't be countered by blue or black spells this turn, and creatures you control can't be the targets of blue or black spells this turn.":
        ("Creatures you control can't be the targets of blue or black spells this turn.",
         lambda d: {**d, "effects": [{"do": "uncounter_by110b", "colors": "UB"}, *d["effects"]]}),
    # Bronze Bombshell: 603.8 state trigger "controlled by a player other than its owner" (stolen_holds); the thief is the trigger's controller
    "When a player other than this creature's owner controls it, that player sacrifices it. If the player does, this creature deals 7 damage to the player.":
        ("When you control no Islands, sacrifice this creature. If you do, ~ deals 7 damage to you.", lambda d: {**d, "state": {"stolen110b": True}}),
    # Rendmaw: 701.15a each token is goaded by Rendmaw's controller, "for the rest of the game" (token_copy_sources.permanent_goad, as Nettling Nuisance)
    "When Rendmaw enters and whenever you play a card with two or more card types, each player creates a tapped 2/2 black Bird creature token with flying. "
    "The tokens are goaded for the rest of the game.":
        ("When ~ enters and whenever you play a card with two or more card types, each player creates a tapped 2/2 black Bird creature token with flying.",
         lambda d: {**d, "effects": [{**d["effects"][0], "as": "bird110b"}, {"do": "permanent_copy_goad", "who": "ref:bird110b"}]}),
    # Stunning Reversal: 614.1a the next loss of the game this turn is replaced (wave110c_lose reads the shield)
    "The next time you would lose the game this turn, instead draw seven cards and your life total becomes 1.":
        ("Draw a card.", lambda d: {**d, "effects": [{"do": "lose_shield110b"}]}),
    "If a permanent you control would be put into a graveyard from the battlefield this turn, exile it instead. Return it to the battlefield under its "
    "owner's control at the beginning of the next end step.":
        ("If a creature you control would die this turn, exile it instead.", _intervention),
    "When this creature enters, each player who controls fewer lands than the player who controls the most lands searches their library for a number of "
    "basic land cards less than or equal to the difference, puts those cards onto the battlefield tapped, then shuffles.":
        ("When this creature enters, each player who controls fewer lands than you searches their library for up to two basic land cards, puts them onto "
         "the battlefield tapped, then shuffles.", _sponsor),
    "Whenever a creature enters, if it was cast, exile it, then return all other permanent cards exiled with this artifact to the battlefield under "
    "their owners' control.": ("Whenever a creature enters, if it was cast, exile it.", _mirror),
    "At the beginning of each combat, up to one target creature attacks or blocks this combat if able and up to one target creature can't attack or block this combat.":
        ("At the beginning of each combat, up to one target creature attacks this combat if able.", _battleshaper),
    "At the beginning of combat on your turn, investigate for each goaded creature you control. Then each creature you control is no longer goaded.":
        ("At the beginning of combat on your turn, investigate for each goaded creature you control.", lambda d: {**d, "effects": [*d["effects"], {"do": "ungoad110b"}]}),
    "Whenever a creature is dealt damage, its controller may exile that many cards from the top of their library. They may play those cards until the end of their next turn.":
        ("Whenever a creature is dealt damage, you may exile that many cards from the top of your library. You may play those cards until the end of your next turn.", _inheritance),
    # Dalkovan Encampment (the sacrifice rides on each trigger's tokens)
    "{2}{W}, {T}: Whenever you attack this turn, create two 1/1 red Warrior creature tokens that are tapped and attacking. Sacrifice them at the beginning of the next end step.":
        ("{2}{W}, {T}: Whenever you attack this turn, create two 1/1 red Warrior creature tokens that are tapped and attacking.", _warriors),
    # Taii Wakeen: 120.3, "equal to that creature's toughness" is the amount of this one damage event; "plus X" is the X paid (107.3k)
    "Whenever a source you control deals noncombat damage to a creature equal to that creature's toughness, draw a card.":
        ("Whenever a source you control deals noncombat damage to a creature, draw a card.", lambda d: {**d, "cond": {**d["cond"], "eq_toughness110b": True}}),
    "{X}, {T}: If a source you control would deal noncombat damage to a permanent or player this turn, it deals that much damage plus X instead.":
        ("{X}, {T}: Until end of turn, if a source you control would deal noncombat damage to a permanent or player, it deals that much damage plus 1 instead.",
         lambda d: {**d, "effects": [{**e, "op": {**e["op"], "n": 0, "x110b": True}} if e.get("do") == "replace_record" else e for e in d["effects"]]}),
    # Way of the Mind Sculptor: the activation event carries the loyalty counters its cost removed (606.4, 603.4)
    "Whenever you activate a loyalty ability, if you removed two or more loyalty counters to activate it, draw a card.":
        ("Whenever you activate a loyalty ability, draw a card.", lambda d: {**d, "cond": {**d["cond"], "loyalty_removed110b": 2}}),
    # The Chain Veil: each planeswalker you control may be activated one more time this turn (606.3 as though none were activated)
    "{4}, {T}: For each planeswalker you control, you may activate one of its loyalty abilities once this turn as though none of its loyalty abilities "
    "have been activated this turn.":
        ("{4}, {T}: Draw a card.", lambda d: {**d, "effects": [{"do": "veil110b"}]}),
    # Perch Protection: all three instructions are conditional on the promised gift (608.2c: one sentence)
    "Create four 2/2 blue Bird creature tokens with flying. If the gift was promised, all permanents you control phase out, and until your next turn, "
    "your life total can't change and you gain protection from everything.":
        ("Create four 2/2 blue Bird creature tokens with flying. If the gift was promised, all permanents you control phase out. Until your next turn, "
         "your life total can't change. You gain protection from everything until your next turn.", _gated(3)),
    # Marvo: the clash he won (701.30d), as Entangling Trap's "if you won" reads it
    "Whenever you win a clash, draw a card. Then you may cast a spell from your hand with mana value 8 or less without paying its mana cost.":
        ("Whenever you clash, draw a card. Then you may cast a spell from your hand with mana value 8 or less without paying its mana cost.",
         lambda d: {**d, "if": {"clash_won100a": True}}),
    # Oath of Lim-Dul: one sacrifice-unless-discard for each 1 life lost (the event's amount), each time its own choice (608.2c)
    "Whenever you lose life, for each 1 life you lost, sacrifice a permanent other than this enchantment unless you discard a card.":
        ("Whenever you lose life, sacrifice a permanent other than this enchantment unless you discard a card.",
         lambda d: {**d, "effects": [{"do": "repeat", "n": {"event_amount": 1}, "span": len(d["effects"])}, *d["effects"]]}),
    # Plague Reaver: the chosen opponent's next upkeep returns the sacrificed card under that player's control (603.7, 110.2a)
    "Discard two cards, Sacrifice this creature: Choose target opponent. Return this creature to the battlefield under that player's control at the "
    "beginning of their next upkeep.":
        ("Discard two cards, Sacrifice this creature: Target opponent gains 1 life.", _reaver),
    # Quakebringer: the trigger works from the battlefield, or from the graveyard with a Giant under your control
    "At the beginning of your upkeep, Quakebringer deals 2 damage to each opponent. This ability triggers only if Quakebringer is on the battlefield or "
    "if Quakebringer is in your graveyard and you control a Giant.":
        ("At the beginning of your upkeep, if this card is in your graveyard and you control a Giant, this creature deals 2 damage to each opponent.",
         _quake),
    # Suppressor Skyguard: prevention lasts through this combat only (500.5); the attacker needs another opponent nobody attacks
    "Whenever a player attacks you, if that player has another opponent who isn't being attacked, prevent all combat damage that would be dealt to you "
    "this combat.":
        ("Whenever a player attacks you, prevent all combat damage that would be dealt to you this turn.", _skyguard),
    # Shirei: the delayed return happens only if Shirei is still on the battlefield when the next end step begins
    "Whenever a creature with power 1 or less is put into your graveyard from the battlefield, you may return that card to the battlefield at the "
    "beginning of the next end step if Shirei is still on the battlefield.":
        ("Whenever a creature with power 1 or less is put into your graveyard from the battlefield, you may return that card to the battlefield at the "
         "beginning of the next end step.", _still_here),
    # Lich's Mastery: for each 1 life you lost, exile a permanent you control or a card from your hand or graveyard
    "Whenever you lose life, for each 1 life you lost, exile a permanent you control or a card from your hand or graveyard.":
        ("Whenever you lose life, exile a permanent you control.", _lich),
    # Divine Intervention: the effect states that the game is a draw (104.4c)
    "When you remove the last intervention counter from this enchantment, the game is a draw.":
        ("When the last intervention counter is removed from this enchantment, draw a card.",
         lambda d: {**d, "effects": [{"do": "draw_game110b"}]}),
    # Overclocked Electromancer: X is all the excess damage that creature was dealt this turn (120.10), summed from the turn log
    "Whenever this creature deals combat damage to a creature, if that creature was dealt excess damage this turn, you get X {E}, where X is that excess "
    "damage.":
        ("Whenever this creature deals combat damage to a creature, if that creature was dealt excess damage this turn, you get {E}{E}.", _electro),
    # Firemane Angel: works from the graveyard (as Quakebringer) or on the battlefield (603.4 intervening "if")
    "At the beginning of your upkeep, if Firemane Angel is in your graveyard or on the battlefield, you may gain 1 life.":
        ("At the beginning of your upkeep, if this creature is in your graveyard, you may gain 1 life.", _quake),
    # Goblin Plate Mail: the Army chosen by amassing, whether or not it got counters (701.47c), is what the Equipment attaches to (701.3a)
    "When this Equipment enters, amass Goblins 1, then attach this Equipment to the amassed Army.":
        ("When this Equipment enters, amass Goblins 1.",
         lambda d: {**d, "effects": [{**d["effects"][0], "as": "army110b"}, {"do": "attach_to", "who": "ref:army110b"}]}),
    # Wall of Dust: the blocked creature can't attack in its controller's next turn (a window rule that starts with that turn, as attack_destinations)
    "Whenever this creature blocks a creature, that creature can't attack during its controller's next turn.":
        ("Whenever this creature blocks a creature, that creature doesn't untap during its controller's next untap step.",
         lambda d: {**d, "effects": [{"do": "no_attack_next110b", "who": "event"}]}),
    # Ozai: the mana a player would lose stays in the pool as red mana (614.1a, 500.4)
    "If you would lose unspent mana, that mana becomes red instead.":
        ("If you would lose unspent mana, that mana becomes colorless instead.", lambda d: {**d, "to": "R"}),
    # Ozai: unspent mana of any type, in the pool and in units with restrictions (106.4)
    "Ozai has flying and indestructible as long as you have six or more unspent mana.":
        ("Ozai has flying and indestructible as long as you have six or more cards in your hand.",
         lambda d: _swap_value(d, {"hand": "you"}, {"unspent": ""})),
}


_LINVALA = "Sacrifice Linvala: Choose hexproof or indestructible. Creatures you control gain that ability until end of turn."


def _linvala(ability: Any, ch: Any) -> Def | None:
    """700.2: "Choose hexproof or indestructible" is a choice of one of two modes, read as the modal ability it equals (header and two bullets in a scratch card)."""
    from app.rules import modal_abilities

    rows = [replace(ability, index=ability.index + i, kind="static", text=f"• Creatures you control gain {k} until end of turn.") for i, k in ((1, "hexproof"), (2, "indestructible"))]
    head = replace(ability, text="Sacrifice Linvala: Choose one \u2014")
    return modal_abilities.definitions(head, replace(ch, abilities=(head, *rows))).get(ability.index)


_ANGEL = "If this creature would deal combat damage to a creature, prevent that damage and that creature's owner shuffles it into their library."


def _angel() -> Def:
    """Weeping Angel: 615.1, 615.5 the combat damage it would deal to a creature is prevented, and the prevented-from creature's owner shuffles it in (the rider)."""
    from app.rules import selectors

    return {"kind": "static", "static": "replace", "event": "damage",
            "match": {"combat": True, "source": {"self": True}, "to": {"objects": {"sel": selectors.Selector(types=("Creature",)).key()}}},
            "op": {"do": "prevent_all", "prevention": True, "rider": {"aggregation": "batch", "effects": [{"do": "to_library", "who": "ref:to", "place": "shuffle"}]}},
            "effects": []}


def note_required(plan: Any, attackers: Any) -> None:
    """508.1d: remember the declared attackers a requirement (goad, "attacks each combat if able", ...) was on, for this combat (Firkraag: "had to attack this combat")."""
    from app.game.rules_state import turn_log_now
    from app.rules import attack_requirements, combat_rules
    from app.rules.keyword_actions import goaded_by

    log = turn_log_now(plan.state)
    for x in attackers if log is not None else ():
        ch = plan.ch(plan.state.cards[x.card_id])
        if attack_requirements.counts(ch) or goaded_by(ch) or combat_rules.other_than(ch) or combat_rules.attack_players(ch):
            log.required110b.append(f"{plan.oid(plan.state.cards[x.card_id])}|{plan.rules.combats}")  # type: ignore[union-attr]


def note_hits(plan: Any) -> None:
    """Turn end: players dealt combat damage this turn join the list; the player whose turn ends starts over (Marchesa: "since your last turn")."""
    log = plan.rules.turn_log
    hit = plan.rules.hit110b
    hit.extend(p for p in dict.fromkeys(f.player for f in (log.facts if log is not None else ()) if f.kind == "damage" and f.combat and f.amount > 0) if p not in hit)
    if plan.active in hit:
        hit.remove(plan.active)


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    text = ability.text.strip()
    if text == _ANGEL:
        return _angel()
    if text == _LINVALA:
        return _linvala(ability, ch)
    from app.rules import wave110b_tahngarth  # -- Tahngarth (wave 110B) --

    if (tahngarth := wave110b_tahngarth.definition(ability, ch)) is not None:
        return tahngarth
    if text == "Exile a creature card from your graveyard and pay its mana cost: Create a token that's a copy of that card. Activate only as a sorcery.":
        from app.rules import selectors

        # Back from the Brink: the choosable cards are the creature cards in the graveyard, each with that ability (zone_grants.apply, keyword "brink110b")
        return {"kind": "static", "static": "zone_grant", "filter": selectors.parse("creature card in your graveyard").key(), "keyword": "brink110b", "cost": None, "reduce": 0, "effects": []}
    if text == "Clandestine Chameleon has all abilities of ability stickers on other permanents you own and cards in your graveyard.":
        return {"kind": "static", "static": "sticker_abilities110b", "effects": []}  # the abilities come from stickers101.continuous (613.1f)
    if (same := _AS.get(text)) is not None:
        return scripts.define(replace(ability, text=same), ch)
    if (built := _BUILD.get(text)) is not None:
        native = scripts.define(replace(ability, text=built[0]), ch)
        return None if native is None else built[1](native)
    return None


_VINCENT = ('Until end of turn, target creature you control gains "When this creature dies, return it to the battlefield tapped under its owner\'s '
            'control" and has the chosen base power and toughness.')
_TIER = re.compile(r"• (?P<label>[^—{}]+) — (?P<cost>(?:\{[^}]+\})+) — (?P<p>\d+)/(?P<t>\d+)\.")


def tiered(ch: Any, lines: list[Any]) -> Def | None:
    """Vincent's Limit Break (702.183a): the line above the tiers is the spell, each tier gives the base power and toughness it names (613.4b)."""
    from app.rules import scripts

    found = [_TIER.fullmatch(ab.text) for ab in lines[1:]]
    if len(lines) != 4 or lines[0].text != _VINCENT or None in found:
        return None
    modes = []
    for m in found:
        assert m is not None
        parts = [scripts.define(replace(lines[0], text=t), ch) for t in (
            'Until end of turn, target creature you control gains "When this creature dies, return it to the battlefield tapped under its owner\'s control."',
            f"Until end of turn, target creature you control has base power and toughness {m['p']}/{m['t']}.")]
        if None in parts or [d["target"] for d in parts if d] != [parts[0]["target"]] * 2:  # type: ignore[index]
            return None
        assert parts[0] is not None and parts[1] is not None
        modes.append({"text": f"{m['label']} — {m['cost']} — {m['p']}/{m['t']}.", "effects": [*parts[0]["effects"], *parts[1]["effects"]],
                      "target": parts[0]["target"], "cost": m["cost"]})
    return {"kind": "spell", "effects": [], "target": None, "modes": modes, "modal": {"min": 1, "max": 1, "repeat": False, "condition": None}}


def veil(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The Chain Veil: every planeswalker its controller controls gets one more loyalty activation this turn (the "twice" allowance, cast_limits.loyalty_rule)."""
    for c in plan.state.cards.values():
        if c.controller == ctx["controller"] and c.zone.endswith(":battlefield") and "Planeswalker" in plan.ch(c).types:
            plan.rules.once_per_turn[f"loyalty_veil110b:{c.id}"] = plan.state.turn.number
    return True


_HEROIC = ("Choose target creature you control. Until end of turn, all damage that would be dealt to you and creatures you control is dealt to the chosen creature instead. "
           "When that creature dies this turn, put its counters on up to one target creature you control and draw a card.")


_AVACYN = {"Turn the exiled card face up. If it's a creature card, you lose life equal to its mana value.": "avacyn_up110b",
           "You may put the exiled card onto the battlefield if it's a creature card. If you don't put it onto the battlefield, put it into its owner's hand.": "avacyn_out110b"}


def parse(body: str) -> Any:
    """Heroic Sacrifice: the chosen creature gets the death trigger until end of turn (611.2a, 603.7: the same as "when that creature dies this turn"); the damage
    to you and your creatures is redirected to it (614.9) while it is on the battlefield."""
    from app.rules import scripts, wave110b_mirror

    if body.strip() == _WORLD:  # World at War
        got = scripts.parse_effects(_WORLD_NATIVE)
        return None if got is None else ([{"do": "second_main110b", "effects": got[0]}], got[1], got[2])
    if (mirror := wave110b_mirror.parse(body)) is not None:  # Mystic Reflection
        return mirror
    if body.strip() in _AVACYN:  # The Creation of Avacyn, chapters II and III
        return [{"do": _AVACYN[body.strip()]}], None, False
    if body.strip() != _HEROIC:
        return None
    got = scripts.parse_effects('Target creature you control gains "When this creature dies, put its counters on up to one target creature you control and draw a card" until end of turn.')
    if got is None:
        return None
    effects, target, optional = got
    return [{"do": "redirect110b"}, *effects], target, optional


def redirect(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Until end of turn, damage that would be dealt to you and to creatures you control is dealt to the target creature instead (614.9)."""
    from app.rules import damage_redirection_effects as dre
    from app.rules import source_shields

    dest = source_shields._destination(plan, ctx, "target")
    if dest is not None:
        dre.record(plan, ctx, {"to": {"players": "you"}}, dest)
        dre.record(plan, ctx, {"to": {"objects": {"sel": dre.key("creatures you control")}}}, dest)
    return True


def faramir_set(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Faramir, Prince of Ithilien: the chosen opponent's next end step (603.7) gets the delayed trigger, naming that player (603.7c)."""
    from app.rules import delayed, effects

    chosen = effects._players(plan, ctx, e["who"])
    if len(chosen) != 1:
        return True
    return delayed.create(plan, {**ctx, "effects": [{"do": "deferred:faramir_end110b", "player": chosen[0]}], "next": 0},
                          {"n": 1, "when": {"kind": "step", "step": "end", "whose": "payer", "player": chosen[0]}})


def faramir_end(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """You draw a card if that player didn't attack you this turn (508.1: a creature they control was declared as attacking you); otherwise three Soldiers."""
    from app.rules import effects, history, scripts

    log = history.log_for(plan)
    attacked = any(ctx["controller"] in log.attacked_who.get(a, []) for a in log.attackers.get(e["player"], []))
    body = scripts.parse_effects("Create three 1/1 white Human Soldier creature tokens." if attacked else "You draw a card.")
    assert body is not None
    for x in body[0]:
        effects.PRIMITIVES[x["do"]](plan, ctx, x)
    return True


def kaito(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Kaito, Dancing Shadow: you may return one of the creatures (that dealt the batch's combat damage) to its owner's hand; if you do, Kaito's loyalty
    abilities may be activated twice this turn (606.3, 400.7)."""
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    pool = [c for c in dict.fromkeys(context.objects(plan, ctx, context.EVENT)) if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")
            and plan.state.cards[c].controller == ctx["controller"] and plan.ch(plan.state.cards[c]).is_creature]
    if not pool:
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt="Return one of them to its owner's hand?",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in pool],
           min_choices=0, max_choices=1, resume={"step": "kaito110b", "ctx": ctx, "pool": pool})
    return False


def resume_kaito(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    chosen = [c for c in chosen[:1] if c in d.resume["pool"]]
    if chosen:
        plan.do({"type": "move", "card_ids": chosen, "to": {"player": plan.state.cards[chosen[0]].owner, "zone": "hand"}}, actor=ctx["controller"])
        if plan.state.cards[chosen[0]].zone.endswith(":hand"):  # (not when a replacement kept it: no "if you do")
            plan.rules.once_per_turn[f"loyalty_veil110b:{ctx['source_card']}"] = plan.state.turn.number
    effects.continue_effects(plan, ctx)


def ungoad(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Serene Sleuth: "each creature you control is no longer goaded" - 701.15b goaded is a designation lasting until the goader's next turn; it leaves them now."""
    from app.rules import delayed, keyword_actions

    mine = {plan.oid(c) for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == ctx["controller"]}
    for effect in [x for x in plan.rules.effects if any(i.startswith(keyword_actions.GOADED) for i in x.imposes)]:
        if mine & set(effect.affected):
            delayed._drop(plan, effect, [o for o in effect.affected if o not in mine])
    return True


def draw_game(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """104.4c: "the game is a draw" (a Commander game does not use the limited range of influence option, 104.4e)."""
    plan.rules.draw_reason = "An effect states that the game is a draw (104.4c)"
    plan.rules.priority = None
    plan.rules.decision = None
    plan.note("The game is a draw (104.4c)")
    return False


def reaver(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Plague Reaver: delayed trigger (603.7a) at the chosen opponent's next upkeep returns the sacrificed card (still the same object, 603.7c) to the
    battlefield under that opponent's control (110.2a)."""
    from app.game.rules_state import DelayedTrigger
    from app.rules import context
    from app.rules.effects import _players

    who = _players(plan, ctx, "target")
    card = ctx.get("source_card")
    if len(who) != 1 or card is None or plan.state.cards[card].zone.endswith(":battlefield"):
        return True
    refs: dict[str, Any] = {}
    context.bind_objects(plan, {"refs": refs}, "reaver", [card])
    context.bind_players({"refs": refs}, "opp", who)
    plan.rules.delayed.append(DelayedTrigger(
        id=secrets.token_hex(4), controller=ctx["controller"], source_card=card, source_object=ctx.get("source_object"), name=ctx.get("name") or "",
        when={"kind": "step", "step": "upkeep", "whose": "payer", "player": who[0]},
        effects=[{"do": "return_card", "who": "ref:reaver", "to": "battlefield", "tapped": False, "under": "ref:opp"}], refs=refs,
        turn=plan.state.turn.number, step=plan.state.turn.phase, created_step=plan.rules.step_serial))
    plan.note(f"{ctx.get('name')} will return at {who[0]}'s next upkeep")
    return True


def exile_own(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Exile a permanent you control or a card from your hand or graveyard": the controller picks one as it resolves (608.2d); none: nothing."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    me = ctx["controller"]
    mine = [c for c in plan.state.cards.values() if (c.zone == f"{me}:hand" or c.zone == f"{me}:graveyard" and c.owner == me)
            or (c.zone.endswith(":battlefield") and c.controller == me)]
    if not mine:
        return True
    decide(plan, player=me, kind="choose_cards", prompt=f"{ctx.get('name') or 'Exile'}: exile a permanent you control or a card from your hand or graveyard",
           options=[DecisionOption(id=c.id, label=c.name or "Card", card_id=c.id) for c in mine], min_choices=1, max_choices=1,
           resume={"step": "exile_own110b", "ctx": ctx})
    return False


def resume_exile_own(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx = d.resume["ctx"]
    ok = {o.id for o in d.options}
    if len(chosen) != 1 or chosen[0] not in ok:
        raise ActionError("Choose one of the cards offered")
    plan.note(f"{plan.name(d.player)} exiles {plan.state.cards[chosen[0]].name}", actor=d.player)
    effects.exile_cards(plan, ctx, {}, chosen)
    effects.continue_effects(plan, ctx)


def rebound_or_hand(plan: Any, card_id: str, controller: str) -> bool:
    """614.1a, 616.1: a rebound spell that also goes to its owner's hand as it resolves (buyback, Soulfire Grand Master): two replacements of the same
    event, so its controller picks one. True: the question is open (engine.leave_stack waits for it)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    if plan.oid(card_id) not in plan.rules.buyback or plan.oid(card_id) in plan.rules.flashback:
        return False
    decide(plan, player=controller, kind="choose_one", prompt="Rebound (exile it) or return it to your hand as it resolves?",
           options=[DecisionOption(id="rebound", label="Exile it with rebound"), DecisionOption(id="hand", label="Put it into your hand")],
           resume={"step": "rebound_hand110b", "card": card_id, "oid": plan.oid(card_id), "controller": controller})
    return True


def resume_rebound_hand(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import engine

    r = d.resume
    card = plan.state.cards.get(r["card"])
    if card is None or card.zone != "stack" or plan.oid(card) != r["oid"]:
        return
    plan.rules.buyback = [o for o in plan.rules.buyback if o != r["oid"]]
    if chosen[0] == "hand":
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "hand"}}, actor=r["controller"])
    else:
        engine.leave_stack(plan, card.id, r["controller"])


def no_attack_next(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Wall of Dust: 508.1c-style restriction "can't attack" (a continuous effect, 611.2) from the start of the creature's controller's next turn
    (declaration window "next_turn", engine.begin_window) to its end."""
    from app.rules import effects, layers

    for cid in effects._cards(plan, ctx, e["who"]):
        card = plan.state.cards[cid]
        layers.add_effect(plan, affected=[plan.oid(cid)], layer="6", source=ctx.get("source_object"), controller=ctx["controller"], duration="permanent",
                          imposes=("cant_attack",), declaration_window="next_turn", declaration_player=card.controller)
    return True


def lose_shield(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import turn_log_now

    log = turn_log_now(plan.state)
    if log is not None:
        log.lose_shield110b.append(f"{ctx['controller']}|{ctx['source_card']}")
    return True


RESUME: dict[str, Any] = {"slicer110b": resume_slicer, "kaito110b": resume_kaito, "exile_own110b": resume_exile_own, "rebound_hand110b": resume_rebound_hand}
def gift_given(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """702.174c: the gift was given (its instant or sorcery resolved, or its permanent's gift trigger resolved): "Whenever you give a gift"."""
    from app.game.rules_state import emit

    emit(plan.state, "designation", counter="gift_given110b", player=ctx["controller"])
    return True


def mana_web(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Mana Web: tap all lands that player controls that could produce any type of mana the tapped land could produce (106.7; the land as it was tapped)."""
    from app.rules import context
    from app.rules import mana as M
    from app.rules.wave110a_grants import could_produce

    lands = context.objects(plan, ctx, context.EVENT)
    if not lands:
        return True
    tapped = plan.state.cards[lands[0]]
    types = [m for m in M.ALL_MANA if could_produce(plan, tapped, plan.ch(tapped), m)]
    hit = []
    for cid in plan.state.zones.get(f"{tapped.controller}:battlefield", []):
        c = plan.state.cards[cid]
        if not c.tapped and plan.ch(c).is_land and any(could_produce(plan, c, plan.ch(c), m) for m in types):
            hit.append(cid)
    if hit:
        plan.do({"type": "tap", "card_ids": hit, "tapped": True}, actor=ctx["controller"])
    return True


def _linked(plan: Any, ctx: dict[str, Any]) -> Any:
    from app.rules import effects

    return next((plan.state.cards[c] for c in effects._cards(plan, ctx, "exiled_with") if plan.state.cards[c].zone.endswith(":exile")), None)


def avacyn_up(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The Creation of Avacyn II: the card exiled face down is turned face up (it is public in exile, 406.3); a creature card costs its controller life equal to its
    mana value (119.3, 608.2h)."""
    card = _linked(plan, ctx)
    if card is None:
        return True
    if card.face_down:
        plan.do({"type": "face_down", "card_ids": [card.id], "face_down": False}, actor=ctx["controller"])
    c = plan.state.cards[card.id]
    if "Creature" in plan.ch(c).types:
        ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "lose_life", "who": "you", "n": int(plan.ch(c).mana_value)}]
    return True


def avacyn_out(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The Creation of Avacyn III: a creature card may be put onto the battlefield; what isn't put there (any other card, or a creature card they decline) goes to its
    owner's hand."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    card = _linked(plan, ctx)
    if card is None:
        return True
    if "Creature" not in plan.ch(card).types:
        return effects.PRIMITIVES["return_card"](plan, ctx, {"do": "return_card", "who": "exiled_with", "to": "hand"})
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'The Creation of Avacyn'}: put {card.name} onto the battlefield?",
           options=[DecisionOption(id="battlefield", label="Put it onto the battlefield"), DecisionOption(id="hand", label="Put it into its owner's hand")],
           resume={"step": "avacyn_out110b", "ctx": ctx})
    return False


def resume_avacyn_out(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    step = {"do": "return_card", "who": "exiled_with", "to": chosen[0], **({"tapped": False, "under": "you"} if chosen[0] == "battlefield" else {})}
    effects.PRIMITIVES["return_card"](plan, ctx, step)
    effects.continue_effects(plan, ctx)


RESUME["avacyn_out110b"] = resume_avacyn_out


PRIMITIVES: dict[str, Any] = {"exile_bottom110b": exile_bottom, "slicer110b": slicer, "avacyn_up110b": avacyn_up, "avacyn_out110b": avacyn_out, "destroy_created110b": destroy_created, "adapt_free110b": adapt_free, "second_main110b": second_main, "nelly_draw110b": nelly_draw, "lolth_loss110b": lolth_loss, "mana_web110b": mana_web, "faramir_set110b": faramir_set, "faramir_end110b": faramir_end, "redirect110b": redirect, "kaito110b": kaito, "return_next_end110b": return_next_end, "gap_search110b": gap_search, "gift_given110b": gift_given, "ungoad110b": ungoad, "no_attack_next110b": no_attack_next, "draw_game110b": draw_game, "reaver110b": reaver, "veil110b": veil, "uncounter_by110b": uncounter_by, "exile_own110b": exile_own, "lose_shield110b": lose_shield}
