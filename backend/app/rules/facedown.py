"""Face-down permanents put onto the battlefield by keyword actions (wave 3F): manifest (701.40),
manifest dread (701.62) and cloak (701.58).

A manifested or cloaked card is turned face down before it enters (708.3), as a 2/2 creature with no
text, no name, no subtypes and no mana cost (cloak: with ward {2}; app/rules/characteristics.py
``face_down_characteristics``), so its own "enters" abilities neither trigger nor apply; other
permanents' "enters" replacement effects see the face-down creature (614.1d, 614.12). Only its
controller may look at it (708.5: app/game/visibility.py); everyone sees how it got face down
(``face_down_kind``). Turning it face up is the special action in app/rules/casting.py
(``turn_face_up``: its mana cost if it's a creature card, 701.40b / 701.58b; its morph or disguise
cost if it has one, 701.40c-d). Leaving the battlefield it is revealed (708.9: app/game/handlers/zones.py).

Instructions to manifest or cloak several cards are carried out one card at a time (701.40e,
701.58e). Manifest dread (701.62a): look at the top two cards, manifest one, put the other into the
graveyard — the choice is the manifesting player's private decision.
"""

from __future__ import annotations

from typing import Any

from app.game.rules_state import DecisionOption
from app.game.state import CardInstance, zone_key
from app.game.visibility import can_see
from app.rules import effects, selectors
from app.rules.plan import Plan, decide

Context = dict[str, Any]


def put_face_down(plan: Plan, card_id: str, player: str, kind: str, *, actor: str, spec: str | None = None, tapped: bool = False) -> bool:
    """Put one card onto the battlefield face down under ``player``'s control (701.40a / 701.58a).
    Its "enters" replacements are those that apply to the face-down creature (708.3). True if it
    entered."""
    from app.rules import replacements

    card = plan.state.cards.get(card_id)
    if card is None:
        return False
    from app.rules import prohibitions

    # -- prohibitions (wave 24D) -- 701.40f / 614.17d: the face-down object (a 2/2 creature card) is what must be allowed to enter:
    # Grafdigger's Cage stops a manifest from the library; the card then stays where it is, face up (silently in a hidden zone)
    if (barred := prohibitions.cant_enter(plan, card.model_copy(update={"face_down": True, "face_down_kind": kind, "face_down_as": spec}),
                                          player)) is not None:
        if barred[1]:
            plan.note(f"{barred[0]}: a card can't enter the battlefield", [card_id])
        return False
    probe: CardInstance = card.model_copy(update={"face_down": True, "face_down_kind": kind, "face_down_as": spec,
                                                  "zone": zone_key(player, "battlefield"), "controller": player})
    ep = replacements.entry_plan(plan, probe, player)
    payload: dict[str, Any] = {"type": "move", "card_ids": [card_id], "to": {"player": player, "zone": "battlefield"},
                               "face_down": True, "face_down_kind": kind, "face_down_as": spec}
    if ep.get("tapped") or tapped:
        payload["tapped"] = True
    plan.do(payload, actor=actor)
    entered = plan.state.cards.get(card_id)
    if entered is None or not entered.zone.endswith(":battlefield"):
        return False
    replacements.after_entry(plan, card_id, player)  # (other permanents' "enters with" counters: 122.6, 614.1c)
    return True


def manifest(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"[Player] manifest(s) / cloak(s) the top [N] card(s) of [their] library", "manifest dread":
    for each named player in APNAP order (101.4), one card at a time (701.40e). ``kind``: "manifest"
    or "cloak"; ``dread``: manifest dread (701.62a); ``n``: how many (dread: how many times).
    Binds the manifested permanents ("that creature", "those creatures": ``as``)."""
    players = effects._players(plan, ctx, e.get("who", "you"))
    if e.get("from") == "hand":  # -- hidden exile (wave 18A) -- "Manifest a card from your hand": the player picks it (private)
        pid = ctx["controller"]
        hand = list(plan.state.zones.get(zone_key(pid, "hand"), []))
        if not hand:
            return True
        decide(plan, player=pid, kind="choose_cards", prompt=f"{ctx.get('name') or 'Manifest'}: choose a card from your hand to put onto "
               "the battlefield face down", options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand],
               min_choices=1, max_choices=1, resume={"step": "manifest_hand", "ctx": ctx, "e": e})
        return False
    if e.get("library"):  # -- player-relative selectors (wave 53A) -- "you manifest the top card of that player's library" (Thieving Amalgam): another player's card, put onto the battlefield under your control
        lib = effects._players(plan, ctx, e["library"])
        if len(lib) != 1:
            return True
        e = {**e, "lib_pid": lib[0]}
    order = [p for p in plan.apnap() if p in players]
    ctx.setdefault("manifested", [])
    todo = [(p, effects._amount(plan, ctx, e.get("n", 1))) for p in order]
    if e.get("per_controller"):  # -- if you do (wave 52A) -- "For each permanent exiled this way, its controller cloaks the top card of their library." (Unexplained Absence)
        from app.rules import this_way

        counts = this_way.by_controller(plan, ctx, e["per_controller"])
        todo = [(p, counts[p]) for p in order if counts.get(p)]
    return _manifest_next(plan, ctx, e, todo)


def _manifest_next(plan: Plan, ctx: Context, e: dict[str, Any], todo: list[tuple[str, int]]) -> bool:
    kind = e.get("kind", "manifest")
    while todo:
        pid, left = todo[0]
        if left <= 0:
            todo = todo[1:]
            continue
        todo = [(pid, left - 1), *todo[1:]]
        library = plan.state.zones.get(zone_key(e.get("lib_pid", pid), "library"), [])
        if not library:
            continue  # (nothing to manifest: 701.40f in spirit — the instruction does what it can)
        if e.get("dread"):
            top = library[:2]
            if len(top) == 1:
                _manifested(plan, ctx, pid, top[0], "manifest")
                continue
            plan.do({"type": "look_top", "player": pid, "count": 2}, actor=pid)
            decide(plan, player=pid, kind="choose_cards", prompt="Manifest dread: choose the card to manifest (the other goes "
                   "to your graveyard)",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in top],
                   min_choices=1, max_choices=1,
                   resume={"step": "manifest_dread", "ctx": ctx, "e": e, "todo": todo, "cards": top})
            return False
        _manifested(plan, ctx, pid, library[0], kind)
    _bind(plan, ctx, e)
    return True


def _manifested(plan: Plan, ctx: Context, pid: str, card_id: str, kind: str, *, tapped: bool = False) -> None:
    if put_face_down(plan, card_id, pid, kind, actor=pid, tapped=tapped):
        ctx["manifested"] = [*ctx.get("manifested", []), card_id]
        verb = "cloaks" if kind == "cloak" else "manifests"
        plan.note(f"{plan.name(pid)} {verb} a card", actor=pid)


def _bind(plan: Plan, ctx: Context, e: dict[str, Any]) -> None:
    """"That creature" / "those creatures" after the instruction: the face-down permanents it made."""
    if e.get("as"):
        from app.rules import context

        context.bind_objects(plan, ctx, e["as"], [c for c in ctx.get("manifested", [])
                                                  if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")])


def resume_manifest_dread(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    ctx, e, cards = r["ctx"], r["e"], r["cards"]
    todo: list[tuple[str, int]] = [(str(t[0]), int(t[1])) for t in r["todo"]]
    pid = d.player
    library = plan.state.zones.get(zone_key(pid, "library"), [])
    pick = next((c for c in chosen if c in library), None)
    if pick is not None:
        _manifested(plan, ctx, pid, pick, "manifest")
    rest = [c for c in cards if c != pick and c in plan.state.zones.get(zone_key(pid, "library"), [])]
    if rest:
        plan.do({"type": "move", "card_ids": rest, "to": {"player": pid, "zone": "graveyard"}}, actor=pid)
    if _manifest_next(plan, ctx, e, todo):
        effects.continue_effects(plan, ctx)


def resume_manifest_hand(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    ctx.setdefault("manifested", [])
    pick = next((c for c in chosen if c in plan.state.zones.get(zone_key(d.player, "hand"), [])), None)
    if pick is not None:
        _manifested(plan, ctx, d.player, pick, e.get("kind", "manifest"))
    _bind(plan, ctx, e)
    effects.continue_effects(plan, ctx)


def _turn_up(plan: Plan, card_id: str, actor: str) -> bool:
    """Turn one face-down permanent face up by an effect (701.40g / 701.58g: a manifested or cloaked instant or sorcery card is
    revealed and stays face down, and nothing triggers; 708.8: the rest as for the special action)."""
    from app.rules import casting
    from app.rules import characteristics as chars

    card = plan.state.cards.get(card_id)
    from app.rules import static_perm100d  # -- static permanents (wave 100D) -- Karlov Watchdog

    if card is None or not card.face_down or not card.zone.endswith(":battlefield") or static_perm100d.face_up_barred(plan, card):
        return False
    printed = chars.of(card.model_copy(update={"face_down": False}), plan.info)
    if card.face_down_kind in ("manifest", "cloak") and printed.is_instant_or_sorcery:
        plan.do({"type": "reveal", "card_ids": [card_id]}, actor=actor)
        plan.do({"type": "hide", "card_ids": [card_id]}, actor=actor)
        return False
    plan.do({"type": "face_down", "card_ids": [card_id], "face_down": False}, actor=actor)
    casting.turned_up(plan, card)
    return True


def turn_face_up(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Turn target face-down creature face up", "you may turn a face-down creature you control face up" (``choose``: the
    selector; its controller picks one, privately): no cost is paid (it isn't the special action of 116.2b)."""
    pid = ctx["controller"]
    if e.get("choose"):
        mine = [c for c in selectors.candidates(plan, selectors.from_key(e["choose"]), pid, ctx.get("source_card"))
                if plan.state.cards[c].controller == pid and plan.state.cards[c].face_down
                and plan.state.cards[c].zone.endswith(":battlefield")]
        if not mine:
            return True
        decide(plan, player=pid, kind="choose_cards", prompt="Turn a face-down permanent face up",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Face-down permanent", card_id=c) for c in mine],
               min_choices=0 if e.get("optional") else 1, max_choices=1, resume={"step": "turn_face_up", "ctx": ctx, "e": e})
        return False
    cards = effects._cards(plan, ctx, e["who"])
    from app.rules import chosen_forms95

    if any(card.face_down and any(chosen_forms95.form(a.text.replace('this creature', '~')) for a in plan.ch(card.model_copy(update={'face_down': False})).abilities) for cid in cards if (card := plan.state.cards.get(cid)) is not None):
        return chosen_forms95.run_batch(plan, ctx, e, list(cards), [])
    done = [c for c in cards if _turn_up(plan, c, pid)]
    for c in done:
        plan.note(f"{plan.name(pid)} turns {plan.state.cards[c].name} face up")
    effects._remember(plan, ctx, e, done)
    return True


def resume_turn_face_up(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx = d.resume["ctx"]
    from app.rules import chosen_forms95

    if chosen:
        chosen_forms95.run_batch(plan, ctx, d.resume['e'], list(chosen), [])
        return
    for c in chosen:
        if _turn_up(plan, c, d.player):
            plan.note(f"{plan.name(d.player)} turns {plan.state.cards[c].name} face up")
    effects.continue_effects(plan, ctx)


def turn_face_down(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Turn target creature face down", "turn this creature face down": a face-up permanent becomes a 2/2 face-down creature with
    no text, name, subtypes or mana cost (708.2a); a face-down permanent can't be turned face down (708.2b)."""
    pid = ctx["controller"]
    cards = [c for c in effects._cards(plan, ctx, e["who"])
             if plan.state.cards[c].zone.endswith(":battlefield") and not plan.state.cards[c].face_down]
    if cards:
        plan.do({"type": "face_down", "card_ids": cards, "face_down": True, "kind": "generic", "face_down_as": e.get("spec")}, actor=pid)
    effects._remember(plan, ctx, e, cards)
    return True


def look_face_down(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Look at target face-down creature" (Aven Soulgazer, Smoke Teller): shown to the looking player alone (701.20e, as "look
    at target player's hand") until they say they're done, then anonymous again. A target that isn't face down any more, or the
    looker's own face-down creature (708.5 already lets them look), shows nothing."""
    me = ctx["controller"]
    cards = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].face_down
             and plan.state.cards[c].zone.endswith(":battlefield") and not can_see(plan.state, plan.state.cards[c], me)]
    if not cards:
        return True
    plan.do({"type": "reveal", "card_ids": cards, "to": [me]}, actor=me)
    decide(plan, player=me, kind="confirm", prompt=f"{ctx.get('name') or 'Look'}: you look at the face-down creature",
           options=[DecisionOption(id="ok", label="Done looking")], resume={"step": "look_face_down", "ctx": ctx, "cards": cards})
    return False


def resume_look_face_down(plan: Plan, d: Any, chosen: list[str]) -> None:
    left = [c for c in d.resume["cards"] if c in plan.state.cards and plan.state.cards[c].face_down and plan.state.cards[c].revealed_to]
    if left:
        plan.do({"type": "hide", "card_ids": left}, actor=d.player)
    effects.continue_effects(plan, d.resume["ctx"])


# -- hidden exile (wave 18A) -- cards exiled face down that "you may look at" (406.3a): the wordings are read in
# app/rules/permissions.py (``join_exile_play``, ``LOOK_EXILED``).


def look_exiled(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"You may look at it for as long as it remains exiled": the ability's controller alone sees the face-down exiled cards the
    earlier instruction exiled (a card they could already see, e.g. their own, shows nothing new)."""
    from app.rules import context

    pid = ctx["controller"]
    if not str(e.get("who", "")).startswith(context.PREFIX):
        return True
    cards = [c for c in context.objects(plan, ctx, e["who"][len(context.PREFIX):])
             if plan.state.cards[c].face_down and plan.state.cards[c].zone.endswith(":exile")
             and not can_see(plan.state, plan.state.cards[c], pid)]
    if cards:
        plan.do({"type": "reveal", "card_ids": cards, "to": [pid]}, actor=pid)
    return True


def exile_hand_down(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Exile all / any number of cards from your hand face down" (Ignorant Bliss, Scroll Rack): the controller exiles their own cards,
    so they keep looking at them (406.3: they were exiled face down, 708.5's controller sees them) and nobody else may. "Any
    number" is chosen privately (608.2d), and asked even with an empty hand so the question itself shows nothing. The cards are
    "exiled this way" (``as``)."""
    pid = ctx["controller"]
    hand = list(plan.state.zones.get(zone_key(pid, "hand"), []))
    if e.get("all"):
        _exile_hand(plan, ctx, e, pid, hand)
        return True
    decide(plan, player=pid, kind="choose_cards", prompt=f"{ctx.get('name') or 'Exile'}: choose any number of cards from your hand to exile "
           "face down", options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand],
           min_choices=min(1, len(hand)) if e.get("pick") else 0, max_choices=1 if e.get("pick") else len(hand),
           resume={"step": "exile_hand_down", "ctx": ctx, "e": e})
    return False


def _exile_hand(plan: Plan, ctx: Context, e: dict[str, Any], pid: str, cards: list[str]) -> None:
    before = effects._remember(plan, ctx, e, cards)
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"player": pid, "zone": "exile"}, "face_down": True,
                 "face_down_kind": "exile", "blind": bool(e.get("blind"))}, actor=pid)
        plan.note(f"{plan.name(pid)} exiles {len(cards)} card{'s' if len(cards) != 1 else ''} from their hand face down")
    if e.get("link"):
        from app.rules import exiled_with

        exiled_with.record(plan, ctx, cards)
    effects._moved(plan, ctx, e, before)


def resume_exile_hand_down(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    hand = plan.state.zones.get(zone_key(d.player, "hand"), [])
    _exile_hand(plan, ctx, e, d.player, [c for c in chosen if c in hand])
    effects.continue_effects(plan, ctx)


def put_down(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Put the top N cards of [a player's] library / any number of cards from your hand onto the battlefield face down [as …]": under
    the controller's control together (each is a face-down 2/2 or what the effect says, 708.2a). The hand cards are chosen
    privately, and the question is asked even with an empty hand (it tells nothing)."""
    pid = ctx["controller"]
    if e["from"] == "hand":
        hand = list(plan.state.zones.get(zone_key(pid, "hand"), []))
        decide(plan, player=pid, kind="choose_cards", prompt=f"{ctx.get('name') or 'Put'}: choose any number of cards from your hand to put "
               "onto the battlefield face down", options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand],
               min_choices=0, max_choices=len(hand), resume={"step": "put_down", "ctx": ctx, "e": e})
        return False
    cards: list[str] = []
    for owner in effects._library_owner(plan, ctx, e):
        cards += effects._library(plan, owner)[: max(0, effects._amount(plan, ctx, e["n"]))]
    return _enter_down(plan, ctx, e, pid, cards)


def _enter_down(plan: Plan, ctx: Context, e: dict[str, Any], pid: str, cards: list[str]) -> bool:
    from app.rules import attachments, face_down_entries64

    entries = face_down_entries64.prepare(plan, cards, pid, under_you=True, spec=e.get("spec"))
    return attachments.enter(plan, entries, ctx)


def resume_put_down(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    hand = plan.state.zones.get(zone_key(d.player, "hand"), [])
    if _enter_down(plan, ctx, e, d.player, [c for c in chosen if c in hand]):
        effects.continue_effects(plan, ctx)


def become_foretold(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"It becomes foretold [with a foretell cost of its mana cost reduced by {2}]" (702.143d): a card in exile becomes a foretold card
    — kept in its owner's foretell exile (only its owner may look), castable for a foretell cost it has after this turn has ended, even
    if it has no foretell ability. ``reduce``: the cost an effect gives it, its mana cost with that much less generic mana."""
    from app.rules import mana as M

    for cid in effects._cards(plan, ctx, e["who"]):
        card = plan.state.cards[cid]
        if not card.zone.endswith(":exile"):
            continue
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": "foretell"}}, actor=ctx["controller"])
        plan.rules.foretold[cid] = plan.state.turn.number
        if e.get("reduce") is not None:
            cost = M.parse_cost(plan.ch(card.model_copy(update={"zone": zone_key(card.owner, "hand")})).mana_cost)
            if cost.unsupported or cost.is_free or cost.x:
                continue
            less = M.ManaCost(generic=max(0, cost.generic - int(e["reduce"])), colored=cost.colored, hybrid=cost.hybrid, phyrexian=cost.phyrexian)
            plan.rules.foretell_costs[cid] = less.text()
    return True


def manifest_pile(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Exile [the creature cards of a graveyard / it / a creature you own] [and the top N cards of your library] in a face-down pile,
    shuffle that pile, then manifest / cloak those cards [tapped]": the cards are exiled together face down, the pile's order is
    shuffled (a recorded table shuffle: replay is deterministic), and each card is then manifested or cloaked in turn, one at a
    time (701.40e, 701.58e) — nobody looks at the cards in between."""
    pid = ctx["controller"]
    cards: list[str] = []
    if e.get("gy"):
        for owner in effects._players(plan, ctx, e["who"]):
            cards += [c for c in plan.state.zones.get(zone_key(owner, "graveyard"), []) if plan.ch(plan.state.cards[c]).is_creature]
    else:
        cards += [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    if e.get("top"):
        cards += effects._library(plan, pid)[: max(0, effects._amount(plan, ctx, e["top"]))]
    if not cards:
        return True
    plan.do({"type": "move", "card_ids": cards, "to": {"zone": "exile"}, "face_down": True, "face_down_kind": "exile"}, actor=pid)
    pile: list[str] = []
    # -- review (sys 18A) -- 406.3: the pile is shuffled by a table shuffle that re-keys it (as a library shuffle does), so no card
    # id links a manifested permanent to the card it was in the graveyard or on the battlefield; each owner's part is in their exile
    exiled = [c for c in cards if c in plan.state.cards and plan.state.cards[c].zone.endswith(":exile")]
    for key in dict.fromkeys(plan.state.cards[c].zone for c in exiled):
        part = [c for c in exiled if plan.state.cards[c].zone == key]
        slots = [i for i, c in enumerate(plan.state.zones[key]) if c in part]
        plan.do({"type": "shuffle", "player": key.split(":")[0], "zone": "exile", "card_ids": part}, actor=pid)
        pile += [plan.state.zones[key][i] for i in slots]
    ctx.setdefault("manifested", [])
    for c in pile:
        _manifested(plan, ctx, pid, c, e["kind"], tapped=bool(e.get("tapped")))
    _bind(plan, ctx, e)
    return True


def reveal_turn_up(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Reveal target face-down permanent. If it's a creature card, you may turn it face up." (Hauntwoods Shrieker): it is shown to all
    players (701.20a) and stays face down (701.20c: revealing moves nothing); then, if the card it is is a creature card, the controller
    chooses whether to turn it face up (no cost: it isn't the special action of 116.2b). Not a face-down permanent any more: nothing."""
    from app.rules import characteristics as chars

    pid = ctx["controller"]
    cards = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].face_down and plan.state.cards[c].zone.endswith(":battlefield")]
    if not cards:
        return True
    card = plan.state.cards[cards[0]]
    plan.do({"type": "reveal", "card_ids": cards}, actor=pid)
    if not chars.of(card.model_copy(update={"face_down": False}), plan.info).is_creature:
        plan.do({"type": "hide", "card_ids": cards}, actor=pid)
        return True
    decide(plan, player=pid, kind="confirm", prompt=f"{ctx.get('name') or 'It'}: turn the revealed creature card face up?",
           options=[DecisionOption(id="yes", label="Turn it face up"), DecisionOption(id="no", label="Leave it face down")],
           resume={"step": "reveal_turn_up", "ctx": ctx, "card": card.id})
    return False


def resume_reveal_turn_up(plan: Plan, d: Any, chosen: list[str]) -> None:
    card_id = d.resume["card"]
    card = plan.state.cards.get(card_id)
    if card is not None and card.face_down:
        if chosen == ["yes"] and _turn_up(plan, card_id, d.player):
            plan.note(f"{plan.name(d.player)} turns {plan.state.cards[card_id].name} face up")
        else:
            plan.do({"type": "hide", "card_ids": [card_id]}, actor=d.player)
    effects.continue_effects(plan, d.resume["ctx"])


def top_to_hand(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Put that many cards from the top of your library into your hand" (Scroll Rack): not a draw (121.1), so no draw replacement or
    trigger; as many as there are when the library has fewer."""
    pid = ctx["controller"]
    top = plan.state.zones.get(zone_key(pid, "library"), [])[: max(0, effects._amount(plan, ctx, e["n"]))]
    if top:
        plan.do({"type": "move", "card_ids": top, "to": {"player": pid, "zone": "hand"}}, actor=pid)
    return True


PRIMITIVES: dict[str, Any] = {"reveal_turn_up": reveal_turn_up, "manifest_pile": manifest_pile, "become_foretold": become_foretold, "put_down": put_down, "exile_hand_down": exile_hand_down, "top_to_hand": top_to_hand, "manifest": manifest, "turn_face_up": turn_face_up, "turn_face_down": turn_face_down,
                              "look_face_down": look_face_down, "look_exiled": look_exiled}
RESUME: dict[str, Any] = {"manifest_hand": resume_manifest_hand, "reveal_turn_up": resume_reveal_turn_up, "put_down": resume_put_down, "exile_hand_down": resume_exile_hand_down, "manifest_dread": resume_manifest_dread, "turn_face_up": resume_turn_face_up,
                          "look_face_down": resume_look_face_down}
