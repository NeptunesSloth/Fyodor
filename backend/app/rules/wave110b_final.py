"""-- wave 110B final pass -- exact Oracle wordings of single cards, read as a wording the grammar already reads plus the smallest change to its definition.

* Lukka, Coppercoat Outcast: +1 gives each exiled creature card a permission to be cast for as long as it remains exiled and you control a Lukka planeswalker
  (611.2b, 113.6m; the 2020-04-17 rulings: any Lukka planeswalker counts); -2 reveals until a creature card with greater mana value than the exiled creature's, as it last
  existed (608.2h; X is 0 in a card in a library or on the battlefield: 107.3g).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

Def = dict[str, Any]

_LUKKA_PLUS = ('+1: Exile the top three cards of your library. Creature cards exiled this way gain "You may cast this card from exile as long as you control a Lukka planeswalker."')
_LUKKA_MINUS = ("−2: Exile target creature you control, then reveal cards from the top of your library until you reveal a creature card with greater mana value. "
                "Put that card onto the battlefield and the rest on the bottom of your library in a random order.")


def _lukka_plus(d: Def) -> Def:
    from app.rules import conditions, permissions

    cond = conditions.parse("you control a Lukka planeswalker")
    assert cond is not None
    return {**d, "effects": [{**e, "filter": permissions.spell_filter("creature"), "when": cond} if e.get("do") == "grant_play" else e for e in d["effects"]]}


def _lukka_minus(d: Def) -> Def:
    out: list[Def] = []
    for e in d["effects"]:
        if e.get("do") == "exile":
            e = {**e, "as": "gone110b"}
        elif e.get("do") == "look_top":
            e = {"do": "greater_dig110b", "gone": "ref:gone110b", "dig": e}
        out.append(e)
    return {**d, "effects": out}


_BUILD: dict[str, tuple[str, Any]] = {
    _LUKKA_PLUS: ('+1: Exile the top three cards of your library. For as long as they remain exiled, you may cast those cards.', _lukka_plus),
    _LUKKA_MINUS: ("−2: Exile target creature you control. Reveal cards from the top of your library until you reveal a creature card. "
                   "Put that card onto the battlefield and the rest on the bottom of your library in a random order.", _lukka_minus),
}


_SANAR = ("Vivid \u2014 At the beginning of your first main phase, reveal cards from the top of your library until you reveal X nonland cards, where X is the number of colors among "
          "permanents you control. For each of those colors, you may exile a card of that color from among the revealed cards. Then shuffle. You may cast the exiled cards this turn.")
_COLORS = (("W", "white"), ("U", "blue"), ("B", "black"), ("R", "red"), ("G", "green"))


def _sanar(d: Def) -> Def:
    """For each color among your permanents (read as the picks are made: nothing changes in between), one optional pick of a revealed card of that color (a card of two colors may
    be taken for either, not both: it leaves the revealed cards, 608.2d); the cards exiled may be cast this turn."""
    from app.rules import conditions, selectors

    dig, pick, shuffle, grant = d["effects"]
    out: list[Def] = [dig]
    for i, (_letter, word) in enumerate(_COLORS):
        cond = conditions.parse(f"you control a {word} permanent")
        sel = selectors.parse(f"{word} card")
        assert cond is not None and sel is not None
        out += [{"do": "only_if", "cond": cond, "skip": 1}, {**pick, "sel": sel.key(), "as": f"vivid{i}", "prompt": f"Vivid: exile a {word} card from among the revealed cards?"}]
    out.append(shuffle)
    out += [{**grant, "who": f"ref:vivid{i}"} for i in range(len(_COLORS))]
    return {**d, "effects": out}


_BUILD[_SANAR] = ("At the beginning of your first main phase, reveal cards from the top of your library until you reveal X nonland cards, where X is the number of colors among permanents you "
                  "control. You may exile one of them. Then shuffle. You may cast the exiled card this turn.", _sanar)

_KAMI = ("I, II \u2014 You gain 2 life. Look at the top three cards of your library. Exile one of them face down with a hatching counter on it, then put the rest on the bottom of your "
         "library in any order.")
_BUILD[_KAMI] = ("I, II \u2014 You gain 2 life. Look at the top three cards of your library. Exile one of them face down, then put the rest on the bottom of your library in any order. "
                 "Put a hatching counter on the exiled card.", lambda d: d)  # (the counter goes on the card as it is exiled, 122.1: the same exiled object, still face down)
_EGG = ("Whenever this creature or a Dragon you control dies, you may cast a creature spell from among cards you own in exile with hatching counters on them without paying its mana cost.")


def _egg(d: Def) -> Def:
    """"this creature or a Dragon you control" (the Egg is no Dragon): itself or any Dragon of yours, the Egg's own death counted once (603.10a: its last known information)."""
    from dataclasses import replace as _replace

    from app.rules import selectors

    sel = selectors.from_key(d["cond"]["sel"])
    return {**d, "cond": {**d["cond"], "sel": _replace(sel, other=False).key()}}


_BUILD[_EGG] = ("Whenever this creature or another Dragon you control dies, you may cast a creature spell from among cards you own in exile with hatching counters on them without paying its "
                "mana cost.", _egg)

_INVASION = ("When this Siege enters, exile cards from the top of your library until you exile two nonland cards with mana value 4 or less. You may cast one of those two cards "
             "without paying its mana cost. Put one of them into your hand. Then put the other cards exiled this way on the bottom of your library in a random order.")
_BUILD[_INVASION] = ("When this Siege enters, draw a card.", lambda d: {**d, "effects": [
    {"do": "siege_exile110b"},
    {"do": "free_cast", "zone": "that", "who": "ref:siege_keep110b", "filter": None, "optional": True, "mv": None, "n": 1},
    {"do": "siege_hand110b"}, {"do": "siege_rest110b"}]})
_ALL_COLORS = "Awaken the Maelstrom is all colors."
_AWAKEN = ("Target player draws two cards. You may put an artifact card from your hand onto the battlefield. Create a token that's a copy of a permanent you control. "
           "Distribute three +1/+1 counters among one, two, or three creatures you control. Destroy target permanent an opponent controls.")


def spell(ch: Any, lines: list[Any]) -> Def | None:
    """Awaken the Maelstrom as one definition (its "is all colors" line is a characteristic, characteristics.all_colors; whole110k: both lines read as this one)."""
    from app.rules import scripts

    if (guardian := guardian_spell(ch, lines)) is not None:
        return guardian
    if [x.text for x in lines] != [_ALL_COLORS, _AWAKEN]:
        return None
    parsed = scripts.parse_effects("Target player draws two cards. You may put an artifact card from your hand onto the battlefield. Destroy target permanent an opponent controls.")
    assert parsed is not None
    effects, targets, _ = parsed
    effects = [effects[0], effects[1], {"do": "copy_choice110b"}, {"do": "distribute110b", "n": 3}, effects[2]]
    return {"kind": "spell", "whole110k": True, "effects": effects, **scripts.target_fields(targets)}


def siege_exile(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """Exile from the top until two nonland cards with mana value 4 or less are exiled (or the library runs out); all are bound, and the two (the ones the cast and the hand are about) too."""
    from app.rules import context

    pid = ctx["controller"]
    taken: list[str] = []
    keep: list[str] = []
    for cid in list(plan.state.zones.get(f"{pid}:library", [])):
        taken.append(cid)
        c = plan.state.cards[cid]
        if "Land" not in plan.ch(c).types and plan.ch(c).mana_value <= 4:
            keep.append(cid)
            if len(keep) == 2:
                break
    if taken:
        plan.do({"type": "move", "card_ids": taken, "to": {"player": pid, "zone": "exile"}}, actor=pid)
    context.bind_objects(plan, ctx, "siege_all110b", [c for c in taken if plan.state.cards[c].zone.endswith(":exile")])
    context.bind_objects(plan, ctx, "siege_keep110b", [c for c in keep if plan.state.cards[c].zone.endswith(":exile")])
    return True


def siege_hand(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """"Put one of them into your hand": one of the two still in exile (the one not cast); with both left (none cast) the controller chooses which."""
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    pid = ctx["controller"]
    left = [c for c in context.objects(plan, ctx, "siege_keep110b") if plan.state.cards[c].zone.endswith(":exile")]
    if not left:
        return True
    if len(left) == 1:
        plan.do({"type": "move", "card_ids": left, "to": {"player": pid, "zone": "hand"}}, actor=pid)
        return True
    decide(plan, player=pid, kind="choose_cards", prompt="Put one of them into your hand", options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in left],
           min_choices=1, max_choices=1, resume={"step": "siege_hand110b", "ctx": ctx})
    return False


def resume_siege_hand(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose one of the cards offered")
    plan.do({"type": "move", "card_ids": chosen, "to": {"player": d.player, "zone": "hand"}}, actor=d.player)
    effects.continue_effects(plan, d.resume["ctx"])


def siege_rest(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """The other cards exiled this way (not the two) go to the bottom in a random order; the card of the two that stayed in exile stays there (the 2023-04-14 ruling)."""
    from app.rules import context, effects

    keep = {r.card for r in context._object_refs(ctx, "siege_keep110b")}
    rest = [c for c in context.objects(plan, ctx, "siege_all110b") if c not in keep and plan.state.cards[c].zone.endswith(":exile")]
    if rest:
        effects.bottom_at_random(plan, ctx["controller"], rest)
    return True


def copy_choice(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """"Create a token that's a copy of a permanent you control": chosen as it resolves (the 2023-04-14 ruling: the artifact just put onto the battlefield is a legal choice)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    pid = ctx["controller"]
    mine = [c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == pid and plan.in_game(c)]
    if not mine:
        return True
    decide(plan, player=pid, kind="choose_cards", prompt=f"{ctx.get('name') or 'Create a token'}: choose a permanent you control to copy",
           options=[DecisionOption(id=c.id, label=c.name or "Permanent", card_id=c.id) for c in mine], min_choices=1, max_choices=1,
           resume={"step": "copy_choice110b", "ctx": ctx})
    return False


def resume_copy_choice(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose one of the permanents offered")
    context.bind_objects(plan, ctx, "copy_choice110b", chosen)
    if effects.PRIMITIVES["token_copy"](plan, ctx, {"do": "token_copy", "n": 1, "who": "ref:copy_choice110b"}):
        effects.continue_effects(plan, ctx)


def distribute(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """"Distribute three +1/+1 counters among one, two, or three creatures you control", chosen as it resolves: each counter goes to a creature of yours (so one to three
    creatures get at least one, 601.2d's limit for the count); they are put at the same time (122.1)."""
    return _distribute_ask(plan, ctx, e, [])


def _distribute_ask(plan: Any, ctx: dict[str, Any], e: Def, given: list[str]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import replace
    from app.rules.plan import decide

    pid = ctx["controller"]
    mine = [c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == pid and plan.ch(c).is_creature and plan.in_game(c)]
    if not mine:
        return True
    if len(given) < int(e["n"]):
        decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name') or 'Distribute'}: put +1/+1 counter {len(given) + 1} of {e['n']} on which creature?",
               options=[DecisionOption(id=c.id, label=c.name or "Creature", card_id=c.id) for c in mine],
               resume={"step": "distribute110b", "ctx": ctx, "e": e, "given": given})
        return False
    tally: dict[str, int] = {}
    for c in given:
        tally[c] = tally.get(c, 0) + 1
    replace.put_counters(plan, [(c, "+1/+1", n) for c, n in tally.items()], by=pid, effect=True)
    return True


def resume_distribute(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose one of the creatures offered")
    ctx, e = d.resume["ctx"], d.resume["e"]
    if _distribute_ask(plan, ctx, e, [*d.resume["given"], chosen[0]]):
        effects.continue_effects(plan, ctx)


_LICH_DAMAGE = "If damage would be dealt to you, exile that many cards from your graveyard instead. If you can't, you lose the game."


def lich_graveyard(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """Nefarious Lich (614.1a, 614.6, 609.3): the damage is never dealt; its controller exiles that many cards from their graveyard (their choice); if they have fewer, they exile
    what they have ("as much as possible") and lose the game."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    pid = ctx["controller"]
    n = max(0, int(effects._amount(plan, ctx, e["n"])))
    yard = [c for c in plan.state.zones.get(f"{pid}:graveyard", [])]
    if n == 0:
        return True
    if len(yard) <= n:
        effects.exile_cards(plan, ctx, {}, yard)
        if len(yard) < n:
            return effects.PRIMITIVES["lose_game"](plan, ctx, {"do": "lose_game", "who": "you"})
        return True
    decide(plan, player=pid, kind="choose_cards", prompt=f"{ctx.get('name') or 'Exile'}: exile {n} cards from your graveyard instead of the damage",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in yard], min_choices=n, max_choices=n,
           resume={"step": "lich_gy110b", "ctx": ctx})
    return False


def resume_lich_graveyard(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ok = {o.id for o in d.options}
    if len(set(chosen)) != d.max_choices or any(c not in ok for c in chosen):
        raise ActionError(f"Choose {d.max_choices} of the cards offered")
    effects.exile_cards(plan, d.resume["ctx"], {}, list(chosen))
    effects.continue_effects(plan, d.resume["ctx"])


_GUARDIAN = ("Prevent the next X damage that would be dealt to any target this turn. Until end of turn, you may pay {1} any time you could cast an instant. If you do, prevent the "
             "next 1 damage that would be dealt to that permanent or player this turn.")
GUARDIAN_PAY = "{1}: Prevent the next 1 damage that would be dealt to that permanent or player this turn."  # the special action's marker line (never a stack ability)


def guardian_spell(ch: Any, lines: list[Any]) -> Def | None:
    from app.rules import scripts

    if [x.text for x in lines] != [_GUARDIAN]:
        return None
    parsed = scripts.parse_effects("Prevent the next X damage that would be dealt to any target this turn.")
    assert parsed is not None
    effects, targets, _ = parsed
    return {"kind": "spell", "whole110k": True, "effects": [*effects, {"do": "guardian110b"}], **scripts.target_fields(targets)}


def guardian_note(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """The permission to pay {1}, for this turn: its card, controller and the target it names (the permanent as that object, 400.7, or the player)."""
    t = (ctx.get("targets") or [{}])[0].get("id")
    if t is None or ctx.get("source_card") is None:
        return True
    card = plan.state.cards.get(t)
    plan.rules.guardian110b.append({"card": ctx["source_card"], "player": ctx["controller"], "turn": plan.state.turn.number, "target": t,
                                    "oid": plan.oid(card) if card is not None else None})
    return True


def _guardian_open(state: Any, card: Any, player: str) -> dict[str, Any] | None:
    r = state.rules
    if r is None or card.zone != f"{player}:graveyard" or card.owner != player:
        return None
    return next((g for g in r.guardian110b if g["card"] == card.id and g["player"] == player and g["turn"] == state.turn.number), None)


def guardian_overlay(state: Any, card: Any, ch: Any) -> Any:
    """113.6m-like: while this turn's permission lasts, the Angel in its owner's graveyard offers the payment ("{1}: Prevent the next 1 damage …") as a special action."""
    from dataclasses import replace as _replace

    from app.rules.oracle import AbilityText

    if card.name != "Guardian Angel" or _guardian_open(state, card, card.owner) is None:
        return ch
    return _replace(ch, abilities=ch.abilities + (AbilityText(index=193, text=GUARDIAN_PAY, kind="activated", cost="{1}"),))


def guardian_action(plan: Any, card: Any, ch: Any, a: Any) -> None:
    """The special action (it uses no stack and can't be responded to): pay {1}; then the next 1 damage to the target this turn is prevented (615.7). 118.1: paid like any cost."""
    from app.game.errors import ActionError
    from app.rules import casting, special_payment_tails
    from app.rules import mana as M

    g = _guardian_open(plan.state, card, plan.actor)
    if g is None:
        raise ActionError("That payment is no longer open this turn")
    target = plan.state.cards.get(g["target"])
    if target is None and g["target"] not in plan.live() or target is not None and (not target.zone.endswith(":battlefield") or plan.oid(target) != g["oid"]):
        raise ActionError("The permanent or player it names is gone")
    cost = M.parse_cost("{1}")
    purpose = casting.Purpose()
    if casting.payment_step(plan, a, cost, f"paying {{1}} for {ch.name}", purpose=purpose):
        return
    special_payment_tails.pay(plan, "guardian110b", card, ch, cost, f"paid {{1}} for {ch.name}", sources=a.sources, purpose=purpose, effects=[{"target": g["target"], "oid": g["oid"]}])


def guardian_paid(plan: Any, card: Any, effects: list[Def]) -> None:
    """Paid: the shield (prevent the next 1 damage that would be dealt to that permanent or player this turn); more payments make more shields."""
    import secrets

    from app.rules import replace

    spec = effects[0]
    target = plan.state.cards.get(spec["target"])
    if target is not None and (not target.zone.endswith(":battlefield") or plan.oid(target) != spec["oid"]):
        return  # (it left while the payment was made: nothing to protect)
    key = "scoped:" + secrets.token_hex(8)
    plan.rules.prevention[key] = 1
    replace.add_record(plan, event="damage", match={"source": {}, "to": {"objects": {"oids": [spec["oid"]]}} if target is not None else {"pids": [spec["target"]]}},
                       op={"do": "scoped_shield", "key": key, "prevention": True}, controller=plan.actor, source=None, source_card=card.id, label=card.name or "Guardian Angel")
    plan.note(f"{plan.name(plan.actor)}: the next 1 damage that would be dealt to {target.name if target is not None else plan.name(spec['target'])} this turn is prevented", actor=plan.actor)
    plan.rules.passed = []


_MAIRSIL_ETB = "When Mairsil enters, you may exile an artifact or creature card from your hand or graveyard and put a cage counter on it."
_MAIRSIL_STATIC = ("Mairsil has all activated abilities of all cards you own in exile with cage counters on them. You may activate each of those abilities only once each turn.")


def _mairsil_static(d: Def) -> Def:
    """The lending of abilities_of.py (113.10, 613.1f), each lent ability "Activate only once each turn" (602.5b: ``once``)."""
    return {**d, "abilities_of": {**d["abilities_of"], "once": True}}


_BUILD[_MAIRSIL_STATIC] = ("This creature has all activated abilities of all cards you own in exile with cage counters on them.", _mairsil_static)
_BUILD[_MAIRSIL_ETB] = ("When this creature enters, draw a card.", lambda d: {**d, "effects": [{"do": "mairsil_cage110b"}]})


def mairsil_cage(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """"You may exile an artifact or creature card from your hand or graveyard and put a cage counter on it" (608.2d: chosen as it resolves)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    pid = ctx["controller"]
    pool = [c.id for c in plan.state.cards.values() if (c.zone == f"{pid}:hand" or c.zone == f"{pid}:graveyard" and c.owner == pid)
            and {"Artifact", "Creature"} & set(plan.ch(c).types)]
    if not pool:
        return True
    decide(plan, player=pid, kind="choose_cards", prompt=f"{ctx.get('name') or 'Mairsil'}: you may exile an artifact or creature card from your hand or graveyard and put a cage counter on it",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool], min_choices=0, max_choices=1, resume={"step": "mairsil_cage110b", "ctx": ctx})
    return False


def resume_mairsil_cage(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if len(chosen) > 1 or any(c not in {o.id for o in d.options} for c in chosen):
        raise ActionError("Choose one of the cards offered, or none")
    ctx = d.resume["ctx"]
    if chosen:
        plan.do({"type": "move", "card_ids": chosen, "to": {"player": plan.state.cards[chosen[0]].owner, "zone": "exile"}}, actor=d.player)
        if plan.state.cards[chosen[0]].zone.endswith(":exile"):
            from app.rules import replace

            replace.put_counters(plan, [(chosen[0], "cage", 1)], by=d.player, effect=True)  # (122.6: through the counter choke point)
    effects.continue_effects(plan, ctx)


_RIVER_DRAW = "Meet in Reverse \u2014 You draw cards from the bottom of your library rather than the top."
_RIVER_SPOILERS = ("Spoilers \u2014 Whenever an opponent scries, surveils, or searches their library, put a +1/+1 counter on River Song. "
                   "Then River Song deals damage to that player equal to its power.")


def draws_from_bottom(plan: Any, pid: str) -> bool:
    """River Song (121.1, 614.1): while its controller controls it, they draw from the bottom of their library; several such effects change nothing more."""
    return any(c.zone.endswith(":battlefield") and c.controller == pid and any(a.text.strip() == _RIVER_DRAW for a in plan.ch(c).abilities)
               for c in plan.state.cards.values() if c.name == "River Song")


def _river_spoilers(d: Def) -> Def:
    one = {"subject": "player", "player": "opponent"}
    return {**d, "cond": {"event": "either", **one, "conds": [{"event": k, **one} for k in ("scry", "surveil", "search_library")]}}


_BUILD[_RIVER_SPOILERS] = ("Whenever an opponent searches their library, put a +1/+1 counter on this creature. Then this creature deals damage to that player equal to its power.", _river_spoilers)

_THIEF = ("As this creature enters, remove all counters from all permanents. This creature enters with a +1/+1 counter on it for each counter removed this way.")


def _has_thief(ch: Any) -> bool:
    return any(a.text.strip() == _THIEF for a in ch.abilities)


def _rival(plan: Any, card: Any, newcomers: list[str] | None) -> bool:
    """Another Thief of Blood entering at the same time: the 2015-11-04 ruling lets its controller apply any one of them (616.1) and only that one gets the counters.
    ponytail: that choice is not built; neither Thief acts and the players do it by hand (the note says so)."""
    other = [c for i in newcomers or () if i != card.id and (c := plan.state.cards.get(i)) is not None and c.name == card.name]
    if other:
        plan.note(f"{card.name} entered with another {card.name}: apply only one of them (it removes the counters and enters with them), by hand (614.12, 616.1)", [card.id])
    return bool(other)


def thief_total(plan: Any, card: Any, ch: Any, newcomers: list[str] | None = None) -> int:
    """Thief of Blood (614.12, 122.6): the counters on all permanents now (the look-ahead of what it enters with; nothing is removed here)."""
    if not _has_thief(ch) or _rival(plan, card, newcomers):
        return 0
    return sum(sum(c.counters.values()) for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.id != card.id)


def thief_remove(plan: Any, card: Any, ch: Any, controller: str, newcomers: list[str] | None = None) -> None:
    """The removal itself, as the Thief really enters (the 2015-11-04 rulings: loyalty counters are removed from planeswalkers, players' experience counters are not)."""
    if not _has_thief(ch) or any(i != card.id and i in plan.state.cards and plan.state.cards[i].name == card.name for i in newcomers or ()):
        return  # (the rival's note was made by thief_total)
    for c in list(plan.state.cards.values()):
        if c.zone.endswith(":battlefield") and c.id != card.id:
            for kind, n in list(c.counters.items()):
                if n > 0:
                    plan.do({"type": "counter", "card_ids": [c.id], "kind": kind, "delta": -n}, actor=controller)


_TORRENT_STATIC = ('As long as Torrent of Lava is on the stack, each creature has "{T}: Prevent the next 1 damage that would be dealt to this creature by Torrent of Lava this turn."')
_TORRENT_GRANT = "{T}: Prevent the next 1 damage that would be dealt to this creature by Torrent of Lava this turn."


def stack_grants(state: Any, card: Any, ch: Any) -> Any:
    """Torrent of Lava (113.6, 604.1, 611.3): while it is on the stack every creature has the shield ability (a static ability of the spell works on the stack, 113.6b).
    ponytail: keyed by the name, like Pin Collection; a second card of this kind needs the text read from its static instead."""
    from dataclasses import replace as _replace

    from app.rules.oracle import parse_abilities

    if not ch.is_creature or not any(c.name == "Torrent of Lava" and c.ability is None and c.zone == "stack" for c in state.cards.values()):
        return ch
    ab = parse_abilities(_TORRENT_GRANT)
    return _replace(ch, abilities=ch.abilities + (_replace(ab[0], index=190),)) if len(ab) == 1 else ch


def torrent_prevent(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """The granted ability's effect: the next 1 damage the Torrent (the spell on the stack, as that object) would deal to this creature this turn is prevented (615.7)."""
    from app.rules import source_shields

    spell = next((c for c in plan.state.cards.values() if c.name == "Torrent of Lava" and c.ability is None and c.zone == "stack"), None)
    if spell is None:
        plan.note("Torrent of Lava is no longer on the stack: nothing is prevented", actor=ctx["controller"])
        return True
    source_shields._record(plan, ctx, {"to": "self", "budget": 1, "props": {}}, [plan.oid(spell)], "Torrent of Lava")
    return True


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if ability.text.strip() == _LICH_DAMAGE:  # the damage body of replace_grammar (damage bodies, wave 35C) with this instruction
        return {"kind": "static", "static": "replace", "event": "damage", "match": {"source": {}, "to": {"players": "you"}},
                "op": {"do": "body", "rider": {"effects": [{"do": "lich_gy110b", "n": {"ref_amount": "that_damage"}}], "if": False}}, "effects": []}
    if ability.text.strip() == _TORRENT_STATIC:
        return {"kind": "static", "static": "stack_grant110b", "effects": []}
    if ability.text.strip() == _TORRENT_GRANT:
        native = scripts.define(replace(ability, text="{T}: You gain 1 life."), ch)
        return None if native is None else {**native, "effects": [{"do": "torrent_prevent110b"}]}

    if ability.text.strip() == _RIVER_DRAW:
        return {"kind": "static", "static": "draw_bottom110b", "effects": []}  # carried out where draws happen (replace.do_draws: draws_from_bottom)
    if ability.text.strip() == _THIEF:
        return {"kind": "static", "static": "thief110b", "effects": []}  # carried out where permanents enter (replacements.entered: thief_remove)
    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def greater_dig(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """The reveal-until instruction with its card required to have greater mana value than the creature the binding names (as it last existed)."""
    from app.rules import context, selectors

    gone = context.info(plan, ctx, e["gone"].removeprefix("ref:"))
    if gone is None:
        return True  # (nothing was exiled: no creature, nothing to compare with: 608.2b)
    dig = e["dig"]
    until = selectors.replace(selectors.from_key(dig["until"]), compare=(("mv", ">", int(gone[1].mana_value)),))
    ctx["effects"][ctx["next"]:ctx["next"]] = [{**dig, "until": until.key()}]
    return True


_SOUND = ("Whenever one or more creature tokens you control deal combat damage to a player, exile target instant or sorcery card with mana value equal to the damage dealt from their "
          "graveyard. Copy it. You may cast the copy without paying its mana cost. If you do, convert Soundwave.")


def _soundwave(d: Def) -> Def:
    """The target's mana value is the damage the batch dealt that player, read as the trigger goes on the stack (triggers.bind_event_stat: ``evt:damage110b``)."""
    from dataclasses import replace as _replace

    from app.rules import selectors

    t = d["target"]
    sel = _replace(selectors.from_key(t["what"]), compare=(("mv", "==", selectors.EVENT_STAT + "damage110b"),))
    return {**d, "target": {**t, "what": sel.key()}}


# 701.28 / the 2022-10-14 ruling: converting a permanent is transforming it, so "transform this creature" is the same action
_BUILD[_SOUND] = ("Whenever one or more creature tokens you control deal combat damage to a player, exile target instant or sorcery card from that player's graveyard. Copy it. "
                  "You may cast the copy without paying its mana cost. If you do, transform this creature.", _soundwave)

_GRIM = ("Whenever The Grim Captain attacks, each opponent sacrifices a nonland permanent of their choice. Then you may put an exiled creature card used to craft The Grim Captain "
         "onto the battlefield under your control tapped and attacking.")
_BUILD[_GRIM] = ("Whenever this creature attacks, each opponent sacrifices a nonland permanent of their choice.", lambda d: {**d, "effects": [*d["effects"], {"do": "crafted_put110b"}]})


def crafted_put(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """The Grim Captain (702.167c, 508.4): you may put one of the exiled creature cards used to craft it (still those objects, still in exile) onto the battlefield under your
    control tapped and attacking; what it attacks is chosen as it enters (the 2023-11-10 ruling), and it was never declared as an attacker."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    refs = plan.rules.crafted_materials.get(ctx.get("source_object") or "", [])
    pool = [c for r in refs if (c := plan.state.cards.get(r.card)) is not None and plan.oid(c) == r.object_id and c.zone.endswith(":exile") and plan.ch(c).is_creature]
    if not pool:
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'The Grim Captain'}: put an exiled creature card used to craft it onto the battlefield tapped and attacking?",
           options=[DecisionOption(id=c.id, label=c.name or "Card", card_id=c.id) for c in pool], min_choices=0, max_choices=1, resume={"step": "crafted_put110b", "ctx": ctx})
    return False


def resume_crafted_put(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    ctx = d.resume["ctx"]
    if len(chosen) > 1 or any(c not in {o.id for o in d.options} for c in chosen):
        raise ActionError("Choose one of the cards offered, or none")
    if chosen:
        context.bind_objects(plan, ctx, "crafted_put110b", chosen)
        if not effects.PRIMITIVES["return_card"](plan, ctx, {"do": "return_card", "who": "ref:crafted_put110b", "to": "battlefield", "tapped": True, "under": "you", "attacking": True}):
            return  # (asked whom it attacks: that answer carries on)
    effects.continue_effects(plan, ctx)


PRIMITIVES: dict[str, Any] = {"mairsil_cage110b": mairsil_cage, "guardian110b": guardian_note, "lich_gy110b": lich_graveyard, "siege_exile110b": siege_exile, "siege_hand110b": siege_hand, "siege_rest110b": siege_rest, "copy_choice110b": copy_choice,
                              "distribute110b": distribute, "torrent_prevent110b": torrent_prevent, "greater_dig110b": greater_dig, "crafted_put110b": crafted_put}
RESUME: dict[str, Any] = {"mairsil_cage110b": resume_mairsil_cage, "lich_gy110b": resume_lich_graveyard, "crafted_put110b": resume_crafted_put, "siege_hand110b": resume_siege_hand, "copy_choice110b": resume_copy_choice, "distribute110b": resume_distribute}
