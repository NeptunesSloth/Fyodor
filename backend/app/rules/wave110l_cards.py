"""-- wave 110L -- exact Oracle wordings of single cards, built from parts the grammar already reads, plus a few small primitives.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

Def = dict[str, Any]
Context = dict[str, Any]

# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def _swap_hands(d: Def) -> Def:
    """Rakdos Augermage: each hand is revealed in turn and the *other* player picks the discard (701.9a, 701.20a: a revealed hand is public)."""
    return {**d, "effects": [{"do": "pick_discard110l", "owner": "you", "chooser": "target"},
                             {"do": "pick_discard110l", "owner": "target", "chooser": "you"}]}


_BUILD["{T}: Reveal your hand and discard a card of target opponent's choice. Then that player reveals their hand and discards a card of your choice. Activate only as a sorcery."] = (
    "{T}: Target opponent loses 1 life. Activate only as a sorcery.", _swap_hands)


def _chime(d: Def) -> Def:
    """Apocalypse Chime: only the permanents with a name first printed in Homelands (wave110l_homelands) are destroyed."""
    from dataclasses import replace as rep

    from app.rules import selectors

    out = []
    for e in d["effects"]:
        if e.get("do") == "destroy":
            sel = selectors.from_key(e["who"])
            e = {**e, "who": rep(sel, extras=(*sel.extras, "first_hml110l")).key()}
        out.append(e)
    return {**d, "effects": out}


_BUILD["{2}, {T}, Sacrifice this artifact: Destroy all nontoken permanents with a name originally printed in the Homelands expansion. They can't be regenerated."] = (
    "{2}, {T}, Sacrifice this artifact: Destroy all nontoken permanents. They can't be regenerated.", _chime)


def _bookworm(d: Def) -> Def:
    """Oblivious Bookworm: the discard of "if you do, discard a card" is also skipped when a permanent entered face down under your control or you turned
    one face up this turn (708.2, 702.37e; facts of history.note_events / rules_state.emit)."""
    gate = [e for e in d["effects"] if e.get("do") == "only_if" and e["cond"].get("succeeded")]
    if len(gate) != 1:
        return d
    skip = {"any": [{"history": "facts", "kind": k, "who": "you", "n": 1} for k in ("enter_fd110l", "turned_up110l")]}
    return {**d, "effects": [{**e, "cond": {"all": [e["cond"], {"not": skip}]}} if e is gate[0] else e for e in d["effects"]]}


_BUILD["At the beginning of your end step, you may draw a card. If you do, discard a card unless a permanent entered the battlefield face down under your control "
       "this turn or you turned a permanent face up this turn."] = (
    "At the beginning of your end step, you may draw a card. If you do, discard a card.", _bookworm)


def _descent(d: Def) -> Def:
    """Descent into Madness: each player exiles X permanents they control and/or cards from their hand (X the despair counters, the one just put on included)."""
    sac = [e for e in d["effects"] if e.get("do") == "sacrifice_choice"]
    if len(sac) != 1:
        return d
    return {**d, "effects": [{"do": "exile_mixed110l", "n": e["n"]} if e is sac[0] else e for e in d["effects"]]}


_BUILD["At the beginning of your upkeep, put a despair counter on this enchantment, then each player exiles X permanents they control and/or cards from their hand, "
       "where X is the number of despair counters on this enchantment."] = (
    "At the beginning of your upkeep, put a despair counter on this enchantment, then each player sacrifices X permanents, "
    "where X is the number of despair counters on this enchantment.", _descent)


def exile_mixed(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Each player, in APNAP order (101.4), chooses X from their own permanents and hand cards (fewer if they have fewer); all are exiled at once.
    The hand is private: only the chooser sees the options until the cards are exiled (exile is face up, 406.3)."""
    from app.rules.effects import _amount

    return _exile_next(plan, ctx, _amount(plan, ctx, e["n"]), list(plan.apnap()), [])


def _exile_next(plan: Plan, ctx: Context, want: int, players: list[str], picked: list[str]) -> bool:
    from app.rules.effects import decide, exile_cards, zone_key

    for i, pid in enumerate(players):
        pool = [c for c in plan.state.zones.get(zone_key(pid, "battlefield"), []) if plan.state.cards[c].controller == pid]
        pool += plan.state.zones.get(zone_key(pid, "hand"), [])
        n = min(want, len(pool))
        if n == 0:
            continue
        if n == len(pool):
            picked = [*picked, *pool]
            continue
        decide(plan, player=pid, kind="choose_cards", prompt=f"Exile {n} permanent{'s' if n != 1 else ''} you control and/or card{'s' if n != 1 else ''} from your hand",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool],
               min_choices=n, max_choices=n, resume={"step": "exile_mixed110l", "ctx": ctx, "want": want, "rest": players[i + 1:], "picked": picked})
        return False
    return exile_cards(plan, ctx, {}, picked)


def resume_exile_mixed(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    r = d.resume
    if _exile_next(plan, r["ctx"], r["want"], r["rest"], [*r["picked"], *chosen]):
        continue_effects(plan, r["ctx"])


def _tyrannic(d: Def) -> Def:
    """The First Tyrannic War chapter I: the put creature enters with counters when its mana cost contains {X} (put_from_hand reads "xlands110l")."""
    puts = [e for e in d["effects"] if e.get("do") == "put_from_hand"]
    return {**d, "effects": [{**e, "xlands110l": True} if e in puts else e for e in d["effects"]]} if len(puts) == 1 else d


_BUILD["I — You may put a creature card from your hand onto the battlefield. If its mana cost contains {X}, it enters with a number of +1/+1 counters on it equal to the number of lands you control."] = (
    "I — You may put a creature card from your hand onto the battlefield.", _tyrannic)


def x_counters(plan: Plan, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each entering card whose printed mana cost has {X} (107.3) gets a +1/+1 counter per land its controller controls as it enters."""
    from app.rules.effects import zone_key

    out = []
    for entry in entries:
        card = plan.state.cards[entry["card"]]
        if "{X}" in plan.ch(card).mana_cost:  # (counter_n 0 would read as one counter: with no land there are none to put)
            lands = sum(1 for c in plan.state.zones.get(zone_key(entry["player"], "battlefield"), [])
                        if "Land" in plan.ch(plan.state.cards[c]).types and plan.state.cards[c].controller == entry["player"])
            entry = {**entry, "counter": "+1/+1", "counter_n": lands} if lands else entry
        out.append(entry)
    return out


def _slith(d: Def) -> Def:
    """Etched Slith: the reflexive trigger's "another target permanent" also takes an opponent (115.1: counters on a player, 122.1)."""
    out = []
    for e in d["effects"]:
        sub = e.get("ability")
        if e.get("do") == "reflexive" and sub and sub.get("target", {}).get("what") == 'sel:{"other":true}':
            e = {**e, "ability": {**sub, "target": {**sub["target"], "what": "opponent_or_other_permanent110l"}}}
        out.append(e)
    return {**d, "effects": out} if out != d["effects"] else d


_BUILD["Whenever this creature deals combat damage to a player, put a +1/+1 counter on it. When you do, you may remove a counter from another target permanent or opponent."] = (
    "Whenever this creature deals combat damage to a player, put a +1/+1 counter on it. When you do, you may remove a counter from another target permanent.", _slith)


_NAMES = "Chosen card names"


def _day_of_the_moon(d: Def) -> Def:
    """Day of the Moon: every chapter chooses one more name; all creatures with any name chosen for this Saga are goaded (701.15a)."""
    effs = d["effects"]
    if [e.get("do") for e in effs] != ["choose_value", "goad"]:
        return d
    return {**d, "effects": [{**effs[0], "as": "named110l"}, {"do": "goad_names110l"}]}


_BUILD["I, II, III — Choose a creature card name, then goad all creatures with a name chosen for this enchantment."] = (
    "I, II, III — Choose a creature card name, then goad all creatures with the chosen name.", _day_of_the_moon)


def goad_names(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The Saga's public record of its chosen names grows by this chapter's (614.12a style, 400.7: a new object has none); if the Saga has left, its
    last-known record is read (603.10a)."""
    from app.cards.names import normalize_name
    from app.rules import card_names, context, keyword_actions

    new = context.refs(ctx).get("named110l", {}).get("value")
    src = plan.state.cards.get(ctx.get("source_card") or "")
    live = src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object")
    snap = plan.rules.lki.get(ctx.get("source_object") or "")
    prior = (src.choices if live and src is not None else snap.choices if snap is not None else {}).get(_NAMES, "")
    names = [n for n in prior.split("\n") if n]
    if new:
        names.append(str(new))
    if live and src is not None and new:
        plan.do({"type": "set_choice", "card_id": src.id, "key": _NAMES, "value": "\n".join(names)}, actor=ctx["controller"])
    want = {normalize_name(n) for n in names}
    hit = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.in_game(c) and plan.ch(c).is_creature
           and want & {normalize_name(n) for n in card_names.names_of(plan.ch(c))}]
    context.bind_objects(plan, ctx, "_day110l", hit)
    return keyword_actions.goad(plan, ctx, {"who": "ref:_day110l"})


def pick_discard(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The owner reveals their hand; the chooser picks one card of it, which is discarded (an empty hand reveals nothing and discards nothing)."""
    from app.rules.effects import _players, decide, zone_key

    owner, chooser = _players(plan, ctx, e["owner"])[:1], _players(plan, ctx, e["chooser"])[:1]
    if not owner or not chooser:
        return True
    hand = list(plan.state.zones.get(zone_key(owner[0], "hand"), []))
    if not hand:
        plan.note(f"{plan.name(owner[0])} reveals an empty hand", actor=owner[0])
        return True
    plan.do({"type": "reveal", "card_ids": hand}, actor=owner[0])
    if len(hand) > 1:
        decide(plan, player=chooser[0], kind="choose_cards", prompt=f"Choose a card from {plan.name(owner[0])}'s hand to be discarded",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand],
               min_choices=1, max_choices=1, resume={"step": "pick_discard110l", "ctx": ctx, "hand": hand, "owner": owner[0]})
        return False
    _finish(plan, ctx, owner[0], hand, hand)
    return True


def _finish(plan: Plan, ctx: Context, owner: str, hand: list[str], chosen: list[str]) -> None:
    from app.rules import prohibitions

    take = [c for c in chosen if c in plan.state.cards and plan.state.cards[c].zone == f"{owner}:hand"]
    if take and (why := prohibitions.cant_cause_discard(plan, owner, ctx["controller"])) is not None:
        plan.note(f"{why}: {plan.name(owner)} can't be made to discard cards")
        take = []
    rest = [c for c in hand if c not in take and c in plan.state.cards and plan.state.cards[c].zone == f"{owner}:hand"]
    if take:
        plan.do({"type": "move", "card_ids": take, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
    if rest:  # 701.20a: the rest is no longer revealed
        plan.do({"type": "hide", "card_ids": rest}, actor=ctx["controller"])


def resume_pick_discard(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    _finish(plan, d.resume["ctx"], d.resume["owner"], d.resume["hand"], chosen)
    continue_effects(plan, d.resume["ctx"])


_P0 = {"goad_names110l": goad_names, "pick_discard110l": pick_discard, "exile_mixed110l": exile_mixed}
_R0 = {"pick_discard110l": resume_pick_discard, "exile_mixed110l": resume_exile_mixed}


# -- spell bodies read whole (their parse hook is scripts.parse_effects) --
_RITUAL = ("Sacrifice a nontoken permanent. If you do, target opponent loses 2 life unless that player sacrifices a permanent of their choice or discards a card. "
           "You may repeat this process any number of times.")
_STRUGGLE = ("Target opponent reveals their hand. That player exiles a card from it, then you exile a card from it. Repeat this process until all cards in that hand "
             "have been exiled. That player returns the cards they exiled this way to their hand and puts the rest into their graveyard.")
_BODIES: dict[str, tuple[list[Def], str]] = {
    _RITUAL: ([{"do": "ritual110l", "who": "target"}], "opponent"),
    _STRUGGLE: ([{"do": "struggle110l", "who": "target"}], "opponent"),
}


def parse(body: str) -> Any:
    found = _BODIES.get(body.strip())
    return None if found is None else ([dict(e) for e in found[0]], found[1], False)


def _opponent(plan: Plan, ctx: Context, e: dict[str, Any]) -> str | None:
    from app.rules.effects import _players

    who = _players(plan, ctx, e["who"])
    return who[0] if who and who[0] in plan.live() else None


def _ask(plan: Plan, player: str, kind: str, prompt: str, options: list[DecisionOption], step: str, state: dict[str, Any], low: int = 1) -> bool:
    from app.rules.effects import decide

    decide(plan, player=player, kind=kind, prompt=prompt, options=options, min_choices=low, max_choices=1, resume={"step": step, **state})
    return False


def _cards_options(plan: Plan, cards: list[str]) -> list[DecisionOption]:
    return [DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in cards]


def ritual(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Forbidden Ritual: each pass sacrifices one nontoken permanent of the controller's (701.21a); only if one was, the target opponent loses 2 life unless
    they sacrifice a permanent or discard a card (their choice, 608.2d); then the controller may go again (the copy of the process, any number of times)."""
    return _ritual_sacrifice(plan, ctx, e)


def _ritual_sacrifice(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import prohibitions

    mine = [c for c in plan.state.zones.get(f"{ctx['controller']}:battlefield", []) if plan.state.cards[c].controller == ctx["controller"]
            and not plan.state.cards[c].is_token and not prohibitions.sacrifice_forbidden(plan, plan.state.cards[c])]
    if not mine or prohibitions.cant_cause_sacrifice(plan, ctx["controller"], ctx["controller"]):
        return True
    return _ask(plan, ctx["controller"], "choose_cards", "Sacrifice a nontoken permanent", _cards_options(plan, mine), "ritual110l",
                {"ctx": ctx, "e": e, "stage": "sacrifice"})


def _ritual_opponent(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    opp = _opponent(plan, ctx, e)
    if opp is None:
        return _ritual_again(plan, ctx, e)
    options = [DecisionOption(id="life", label="Lose 2 life")]
    if any(plan.state.cards[c].controller == opp for c in plan.state.zones.get(f"{opp}:battlefield", [])):
        options.append(DecisionOption(id="sacrifice", label="Sacrifice a permanent"))
    if plan.state.zones.get(f"{opp}:hand"):
        options.append(DecisionOption(id="discard", label="Discard a card"))
    return _ask(plan, opp, "choose_one", "Forbidden Ritual: lose 2 life unless you sacrifice a permanent or discard a card", options, "ritual110l",
                {"ctx": ctx, "e": e, "stage": "opponent", "opp": opp})


def _ritual_again(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    return _ask(plan, ctx["controller"], "choose_one", "Repeat this process?", [DecisionOption(id="yes", label="Repeat"), DecisionOption(id="no", label="Stop")],
                "ritual110l", {"ctx": ctx, "e": e, "stage": "again"})


def ritual_again(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    return _ritual_again(plan, ctx, e["ritual"])


def resume_ritual(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects, prohibitions

    r = d.resume
    ctx, e, stage = r["ctx"], r["e"], r["stage"]
    pick = chosen[0] if chosen else ""
    if stage == "sacrifice":
        effects._sacrifice_cards(plan, [pick], ctx["controller"], ctx)
        done = pick in plan.state.cards and not plan.state.cards[pick].zone.endswith(":battlefield")
        go = _ritual_opponent(plan, ctx, e) if done else _ritual_again(plan, ctx, e)
    elif stage == "opponent":
        opp = r["opp"]
        if pick == "life":  # the loss may itself wait on a replacement choice (616.1): the repeat question is the next instruction, asked after it
            ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "ritual_again110l", "ritual": e}]
            go = effects.PRIMITIVES["lose_life"](plan, ctx, {"who": e["who"], "n": 2})
        else:
            pool = [c for c in plan.state.zones.get(f"{opp}:{'battlefield' if pick == 'sacrifice' else 'hand'}", []) if plan.state.cards[c].controller == opp]
            go = _ask(plan, opp, "choose_cards", "Sacrifice a permanent" if pick == "sacrifice" else "Discard a card", _cards_options(plan, pool), "ritual110l",
                      {"ctx": ctx, "e": e, "stage": "pay_" + pick, "opp": opp})
    elif stage in ("pay_sacrifice", "pay_discard"):
        if stage == "pay_sacrifice":
            effects._sacrifice_cards(plan, [pick], r["opp"], ctx)
        elif prohibitions.cant_cause_discard(plan, r["opp"], ctx["controller"]) is None:
            plan.do({"type": "move", "card_ids": [pick], "to": {"zone": "graveyard"}}, actor=ctx["controller"])
        go = _ritual_again(plan, ctx, e)
    else:  # "again"
        go = _ritual_sacrifice(plan, ctx, e) if pick == "yes" else True
    if go:
        effects.continue_effects(plan, ctx)


def struggle(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Struggle for Sanity: the hand is revealed (701.20a: public, so every pick is a public choice); the opponent exiles a card, then the controller does,
    until the hand is empty; the opponent's exiled cards go back to the hand, the controller's to the graveyard (400.7: each card is followed by its
    id and the object it became in exile)."""
    opp = _opponent(plan, ctx, e)
    if opp is None:
        return True
    hand = list(plan.state.zones.get(f"{opp}:hand", []))
    if hand:
        plan.do({"type": "reveal", "card_ids": hand}, actor=opp)
    return _struggle_next(plan, ctx, e, opp, "opp", [], [])


def _struggle_next(plan: Plan, ctx: Context, e: dict[str, Any], opp: str, turn: str, theirs: list[tuple[str, str]], mine: list[tuple[str, str]]) -> bool:
    while True:
        hand = list(plan.state.zones.get(f"{opp}:hand", []))
        if not hand:
            break
        chooser = opp if turn == "opp" else ctx["controller"]
        if len(hand) > 1:
            return _ask(plan, chooser, "choose_cards", "Exile a card from the revealed hand", _cards_options(plan, hand), "struggle110l",
                        {"ctx": ctx, "e": e, "opp": opp, "turn": turn, "theirs": theirs, "mine": mine})
        theirs, mine = _struggle_exile(plan, ctx, hand[0], turn, theirs, mine)
        turn = "me" if turn == "opp" else "opp"
    back = [c for c, oid in theirs if c in plan.state.cards and plan.oid(plan.state.cards[c]) == oid and plan.state.cards[c].zone == f"{opp}:exile"]
    away = [c for c, oid in mine if c in plan.state.cards and plan.oid(plan.state.cards[c]) == oid and plan.state.cards[c].zone == f"{opp}:exile"]
    if back:
        plan.do({"type": "move", "card_ids": back, "to": {"zone": "hand"}}, actor=ctx["controller"])
    if away:
        plan.do({"type": "move", "card_ids": away, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
    return True


def _struggle_exile(plan: Plan, ctx: Context, cid: str, turn: str, theirs: list[tuple[str, str]], mine: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    plan.do({"type": "move", "card_ids": [cid], "to": {"zone": "exile"}}, actor=ctx["controller"])
    card = plan.state.cards[cid]
    entry = (cid, plan.oid(card))
    return ([*theirs, entry], mine) if turn == "opp" else (theirs, [*mine, entry])


def resume_struggle(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    r = d.resume
    ctx, opp, turn = r["ctx"], r["opp"], r["turn"]
    theirs, mine = [tuple(x) for x in r["theirs"]], [tuple(x) for x in r["mine"]]
    theirs, mine = _struggle_exile(plan, ctx, chosen[0], turn, theirs, mine)  # type: ignore[arg-type]
    if _struggle_next(plan, ctx, r["e"], opp, "me" if turn == "opp" else "opp", theirs, mine):  # type: ignore[arg-type]
        continue_effects(plan, ctx)


PRIMITIVES = {**_P0, "ritual110l": ritual, "ritual_again110l": ritual_again, "struggle110l": struggle}
RESUME = {**_R0, "ritual110l": resume_ritual, "struggle110l": resume_struggle}
