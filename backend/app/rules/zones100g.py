"""-- zones (wave 100G) -- graveyard returns, chapters and look/reveal lines the grammar doesn't read, by their exact Oracle wording.

Each wording is read as an equivalent sentence the grammar already reads (608.2c: the instructions in printed order), or as that
sentence's parse with one field changed (a target group's minimum, a selector, the counters a card enters with). An unknown or variant
wording is never matched (the line stays manual)."""
from __future__ import annotations

from typing import Any

Parsed = tuple[list[dict[str, Any]], Any, bool]

# Sentences the grammar reads in other words with the same meaning.
REWRITES = {
    # Grim Captain's Call: four choices made in order as it resolves, nothing targeted (the official rulings: a card of two of these types may be
    # returned for one and another card for the other; a missing type is skipped)
    "Return a Pirate card from your graveyard to your hand, then do the same for Vampire, Dinosaur, and Merfolk.":
        "Return a Pirate card from your graveyard to your hand. Return a Vampire card from your graveyard to your hand. Return a Dinosaur card from your "
        "graveyard to your hand. Return a Merfolk card from your graveyard to your hand.",
    # Ajani Fells the Godsire II: ", then" is the next instruction (608.2c)
    "Create a 2/1 white Cat Warrior creature token, then put a vigilance counter on a creature you control.":
        "Create a 2/1 white Cat Warrior creature token. Put a vigilance counter on a creature you control.",
    # Kang Dynasty III: the count as it resolves (608.2h), then the second instruction (608.2c)
    "Target creature you control gets +1/+1 until end of turn for each card in your hand and can't be blocked this turn.":
        "Target creature you control gets +1/+1 until end of turn for each card in your hand. It can't be blocked this turn.",
    # Defossilize: the same creature explores twice (701.44a; the official ruling: it explores even if it has left the battlefield)
    "Return target creature card from your graveyard to the battlefield. That creature explores, then it explores again.":
        "Return target creature card from your graveyard to the battlefield. It explores. It explores.",
}


def _plain(text: str) -> Parsed | None:
    from app.rules import scripts

    return scripts.parse_effects(text)


def _sel(phrase: str) -> str:
    from app.rules import selectors

    s = selectors.parse(phrase)
    assert s is not None, phrase
    return s.key()


def _either(*phrases: str, **fields: Any) -> str:
    from app.rules.selectors import Selector

    return Selector(either=tuple(_sel(p) for p in phrases), card=True, **fields).key()


def _vengeful_regrowth() -> Parsed | None:
    """Vengeful Regrowth: "that many" is the number of land cards actually put onto the battlefield (the official ruling: a target gone in
    response makes no token) — this_way's count of the cards the return put there."""
    p = _plain("Return up to three target land cards from your graveyard to the battlefield tapped. Create a 4/2 green Plant Warrior creature token "
               "with reach for each card returned this way.")
    if p is None or [e["do"] for e in p[0]] != ["return_card", "create_token"] or p[0][1]["n"].get("this_way") != "returned":
        return None
    return [p[0][0], {**p[0][1], "n": {**p[0][1]["n"], "this_way": "battlefield_put"}}], p[1], False


def _clear_the_stage() -> Parsed | None:
    """Clear the Stage: the return is optional as it resolves (603.5-style "you may", 608.2c) and only if the condition holds then (after the
    -3/-3: the official ruling); the card may be targeted either way (the official ruling)."""
    pump, ret = _plain("Target creature gets -3/-3 until end of turn."), _plain(
        "If you control a creature with power 4 or greater, return up to one target creature card from your graveyard to your hand.")
    if pump is None or ret is None or [e["do"] for e in ret[0]] != ["only_if", "return_card"] or ret[0][0].get("skip") != 1:
        return None
    from app.rules import scripts

    return [*scripts._renumber(pump[0], [0]), {**ret[0][0], "skip": 2}, {"do": "may_rest"}, *scripts._renumber(ret[0][1:], [1])], \
        scripts._as_groups(pump[1]) + scripts._as_groups(ret[1]), False


def _perennation() -> Parsed | None:
    """Perennation: the card enters with both counters on it (122.6; hexproof and indestructible counters are keyword counters, 122.1b)."""
    p = _plain("Return target permanent card from your graveyard to the battlefield with a hexproof counter on it.")
    if p is None or len(p[0]) != 1 or p[0][0].get("counter") != "hexproof":
        return None
    e = {k: v for k, v in p[0][0].items() if k != "counter"}
    return [{**e, "conditional_counters": [{"kind": "hexproof", "n": 1}, {"kind": "indestructible", "n": 1}]}], p[1], False


def _rob_the_hoard() -> Parsed | None:
    """Rob the Hoard: one card that is an artifact, an enchantment or legendary (115.1: a card of any of these kinds)."""
    p = _plain("Return target legendary card from your graveyard to your hand.")
    if p is None or not isinstance(p[1], str):
        return None
    return p[0], _either("artifact card from your graveyard", "enchantment card from your graveyard", "legendary card from your graveyard",
                         zones=("graveyard",), zone_owner="you"), False


def _leonardos_technique() -> Parsed | None:
    """Leonardo's Technique: "one or two target" — at least one target (601.2c, 115.1); "each with" limits every card by itself."""
    p = _plain("Return up to two target creature cards with mana value 3 or less from your graveyard to the battlefield.")
    if p is None or not isinstance(p[1], list) or len(p[1]) != 1 or p[1][0].get("max") != 2:
        return None
    return p[0], [{**p[1][0], "min": 1}], False


def _unearthly_child() -> Parsed | None:
    """An Unearthly Child: the first card that is a Doctor, has doctor's companion (702.135a) or is a Vehicle (701.20a reveal)."""
    p = _plain("Reveal cards from the top of your library until you reveal a Vehicle card. Put that card into your hand and the rest on the bottom of "
               "your library in a random order.")
    if p is None or [e["do"] for e in p[0]] != ["look_top", "pick_looked", "rest_looked"]:
        return None
    until = _either("Doctor card", "card with doctor's companion", "Vehicle card", zones=("library",))
    return [{**p[0][0], "until": until}, *p[0][1:]], p[1], False


def _vault12() -> Parsed | None:
    """Vault 12 II: every rad counter of every player still in the game (122.1, 102.1), counted as the chapter resolves (608.2h)."""
    p = _plain("Create X 2/2 black Zombie Mutant creature tokens, where X is the number of rad counters you have.")
    if p is None or [e["do"] for e in p[0]] != ["create_token"] or p[0][0].get("n") != {"player_counters": "rad"}:
        return None
    return [{**p[0][0], "n": {"player_counters": "rad", "of": "all"}}], p[1], False


def _each_color(kind: str, tail: str = "") -> Any:
    """All Suns' Dawn, Rogues' Gallery: "for each color, up to one target card of that color" — five target groups, one per color (601.2c),
    each card chosen once (the official ruling: two white-and-blue cards, one as the white card and one as the blue one), its color checked
    again as it resolves (608.2b)."""
    def build() -> Parsed | None:
        from app.rules import static_spell100c

        colors = ("white", "blue", "black", "red", "green")
        p = static_spell100c._seq(*(f"Return up to one target {c} {kind} from your graveyard to your hand." for c in colors), *([tail] if tail else []))
        if p is None or not isinstance(p[1], list) or len(p[1]) != 5:
            return None
        return p[0], [{**g, "distinct_from": list(range(i))} if i else g for i, g in enumerate(p[1])], False
    return build


def _nightmares() -> Parsed | None:
    """Nightmares and Daydreams I-III: a delayed trigger until your next turn (603.7, 500.4); its target chosen each time it triggers (603.3d),
    "that spell" the spell whose casting triggered it (603.7c), its mana value as it is on the stack (202.3e)."""
    p = _plain("Until your next turn, whenever you cast an instant or sorcery spell, target player mills two cards.")
    if p is None or [e["do"] for e in p[0]] != ["delayed", "deferred:mill"] or p[0][1].get("n") != 2:
        return None
    return [p[0][0], {**p[0][1], "n": {"mana_value": "event"}}], p[1], False


def _fenric() -> Parsed | None:
    """The Curse of Fenric II: one effect of no duration (611.2a: it lasts) — its types and legendary (layer 4, 205.1a), no abilities (layer 6),
    6/6 (layer 7b) and the name Fenric (layer 3, 613.1c: a text-changing effect; 201.5 keeps its self-references)."""
    p = _plain("Target nontoken creature becomes a 6/6 Horror creature.")
    if p is None or [e["do"] for e in p[0]] != ["become"] or p[0][0].get("duration") != "permanent":
        return None
    return [{**p[0][0], "legendary": True, "lose_abilities": True}, {"do": "named100g", "who": "target", "name": "Fenric"}], p[1], False


def named(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, layers

    cards = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    if cards:
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer="3", source=ctx.get("source_object"), controller=ctx["controller"],
                          duration="permanent", label=f"named {e['name']}", set_name=e["name"])
        plan.note(f"{', '.join(plan.state.cards[c].name or 'It' for c in cards)} is named {e['name']}", cards, actor=ctx["controller"])
    return True


def loyalty_twice(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Urza Assembles the Titans III: for the rest of this turn its controller's planeswalkers may use loyalty abilities twice (606.3; the official
    rulings: the same ability twice or two different ones; more such effects don't add a third) — a turn mark, read by cast_limits.loyalty_rule."""
    plan.rules.once_per_turn[f"loyalty_twice100g:{ctx['controller']}"] = plan.state.turn.number
    plan.note(f"{plan.name(ctx['controller'])} may activate loyalty abilities twice this turn", actor=ctx["controller"])
    return True


def face_down_looked(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Write into Being, Hide in Plain Sight: ``n`` of the cards looked at, the looker's private choice (the official ruling: the others don't
    learn which), manifested / cloaked one at a time (701.40e, 701.58b: facedown.put_face_down)."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    owner, cards = effects._looked(plan, ctx)
    n = min(int(e["n"]), len(cards))
    if n == len(cards):
        _face_down(plan, ctx, e, owner, cards)
        return True
    decide(plan, player=owner, kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: choose {n} to {e['kind']} (put onto the battlefield face down)",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in cards], min_choices=n, max_choices=n,
           resume={"step": "face_down_looked100g", "ctx": ctx, "e": e})
    return False


def _face_down(plan: Any, ctx: dict[str, Any], e: dict[str, Any], owner: str, cards: list[str]) -> None:
    from app.rules import facedown

    for c in cards:
        facedown._manifested(plan, ctx, owner, c, e["kind"])


def resume_face_down_looked(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    owner, cards = effects._looked(plan, ctx)
    picked = list(dict.fromkeys(c for c in chosen if c in cards))
    if len(picked) != min(int(e["n"]), len(cards)):
        raise ActionError(f"Choose {e['n']} of those cards")
    _face_down(plan, ctx, e, owner, picked)
    effects.continue_effects(plan, ctx)


def top_or_bottom(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Write into Being: "put the other on the top or bottom of your library" — the looker's choice (it is already on top: "top" leaves it)."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    owner, cards = effects._looked(plan, ctx)
    ctx["looked"] = []
    if not cards:
        return True
    decide(plan, player=owner, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: put the other card on the top or the bottom of your library",
           options=[DecisionOption(id="top", label="Top"), DecisionOption(id="bottom", label="Bottom")],
           resume={"step": "top_or_bottom100g", "ctx": ctx, "cards": cards, "owner": owner})
    return False


def resume_top_or_bottom(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if chosen not in (["top"], ["bottom"]):
        raise ActionError("Choose top or bottom")
    r = d.resume
    if chosen == ["bottom"]:
        effects.bottom_at_random(plan, r["owner"], [c for c in r["cards"] if c in plan.state.zones.get(f"{r['owner']}:library", [])], actor=r["owner"])
    plan.note(f"{plan.name(r['owner'])} puts a card on the {chosen[0]} of their library", actor=r["owner"])
    effects.continue_effects(plan, r["ctx"])


def choose_greatest(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Fall of the Impostor III: a creature with the greatest power among the creatures that player controls, as it resolves (only theirs:
    the official rulings); a tie, the ability's controller chooses (nothing is targeted) — bound as ``as`` for the exile after it."""
    from app.game.rules_state import DecisionOption
    from app.rules import context, effects, sba
    from app.rules.plan import decide

    players = effects._players(plan, ctx, e["who"])
    theirs = [c for c in plan.state.cards.values() if players and c.zone == f"{players[0]}:battlefield" and plan.in_game(c) and plan.ch(c).is_creature]
    power = {c.id: sba.power(c, plan.ch(c)) or 0 for c in theirs}
    best = [cid for cid, p in power.items() if p == max(power.values())] if power else []
    if len(best) <= 1:
        context.bind_objects(plan, ctx, e["as"], best)
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: choose a creature with the greatest power",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in sorted(best)], min_choices=1, max_choices=1,
           resume={"step": "choose_greatest100g", "ctx": ctx, "e": e, "best": sorted(best)})
    return False


def resume_choose_greatest(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    if len(chosen) != 1 or chosen[0] not in d.resume["best"]:
        raise ActionError("Choose one of those creatures")
    context.bind_objects(plan, d.resume["ctx"], d.resume["e"]["as"], chosen)
    effects.continue_effects(plan, d.resume["ctx"])


def choose_event(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Zurgo and Ojutai: "you may return one of those Dragons" — none or one of the trigger's batch (the Dragons that dealt the damage) still on
    the battlefield, chosen as it resolves (the official ruling: not targeted) — bound as ``as`` for the bounce after it."""
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    those = sorted(c for c in context.objects(plan, ctx, context.EVENT) if plan.state.cards[c].zone.endswith(":battlefield"))
    context.bind_objects(plan, ctx, e["as"], [])
    if not those:
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: you may choose one of them to return to its owner's hand",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in those], min_choices=0, max_choices=1,
           resume={"step": "choose_event100g", "ctx": ctx, "e": e, "those": those})
    return False


def resume_choose_event(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    if len(chosen) > 1 or not set(chosen) <= set(d.resume["those"]):
        raise ActionError("Choose at most one of those creatures")
    context.bind_objects(plan, d.resume["ctx"], d.resume["e"]["as"], chosen)
    effects.continue_effects(plan, d.resume["ctx"])


def return_total_power(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Moorland Rescuer: any number of other creature cards from your graveyard whose powers add up to X or less — X its power as it last existed
    on the battlefield (the official ruling; 608.2h) — chosen as it resolves (608.2d), then returned together (the ruling: even if it left)."""
    from app.game.rules_state import DecisionOption
    from app.rules import selectors, values
    from app.rules.plan import decide

    cap = values.evaluate(plan, ctx, {"power": "self"})
    pool = sorted(c for c in selectors.candidates(plan, selectors.from_key(e["sel"]), ctx["controller"], ctx.get("source_card"))
                  if c != ctx.get("source_card"))
    if not pool:
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: choose creature cards with total power {cap} or less to return",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool], min_choices=0, max_choices=len(pool),
           resume={"step": "return_total_power100g", "ctx": ctx, "e": e, "cap": cap, "pool": pool})
    return False


def _power(plan: Any, cid: str) -> int:
    from app.rules import sba

    card = plan.state.cards[cid]
    return max(0, sba.power(card, plan.ch(card)) or 0)


def resume_return_total_power(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    r = d.resume
    cards = [c for c in dict.fromkeys(chosen) if c in r["pool"] and plan.state.cards[c].zone == f"{r['ctx']['controller']}:graveyard"]
    if len(cards) != len(set(chosen)) or sum(_power(plan, c) for c in cards) > r["cap"]:
        raise ActionError(f"Those cards must have total power {r['cap']} or less")
    if effects._return_cards(plan, r["ctx"], {"do": "return_card", "to": "battlefield", "tapped": False, "under": "you"}, cards):
        effects.continue_effects(plan, r["ctx"])


def bottom_linked(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Trial of a Time Lord IV, Vault 13 III: the cards exiled with the Saga still in exile go to the bottom of their owners' libraries, each
    owner in turn order (101.4) ordering their own (401.4); one owner per instance — the next one is queued before the order is asked."""
    from app.rules import effects

    cards = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":exile")]
    for owner in plan.apnap():
        mine = [c for c in cards if plan.state.cards[c].owner == owner]
        if len(mine) == 1:
            plan.do({"type": "move", "card_ids": mine, "to": {"player": owner, "zone": "library"}, "position": "bottom"}, actor=owner)
        elif mine:
            ctx["effects"] = [*ctx["effects"][:ctx["next"]], dict(e), *ctx["effects"][ctx["next"]:]]
            effects._ask_order(plan, ctx, owner, owner, mine, "bottom")
            return False
    return True


def turn_up_linked(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Summoner's Egg: the card exiled with it (607.2a) turned face up in exile — public from then on (406.3) — and the creature cards among them
    bound as ``as`` (a noncreature card stays exiled face up: the official ruling; nothing "turned face up" triggers, it isn't a permanent)."""
    from app.rules import context, effects

    cards = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":exile")]
    down = [c for c in cards if plan.state.cards[c].face_down]
    if down:
        plan.do({"type": "face_down", "card_ids": down, "face_down": False}, actor=ctx["controller"])
    context.bind_objects(plan, ctx, e["as"], [c for c in cards if plan.ch(plan.state.cards[c]).is_creature])
    return True


def self_exiled(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Esper Origins: the resolving spell's card, just exiled by spell_self_move (608.2n), bound as ``as`` — its new object in exile (400.7j)."""
    from app.rules import context

    card = plan.state.cards.get(ctx.get("stack_id") or "")
    context.bind_objects(plan, ctx, e["as"], [card.id] if card is not None and card.zone.endswith(":exile") else [])
    return True


def opponent_pick(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Tasigur: "a nonland card of an opponent's choice" — as it resolves you choose an opponent, who then chooses the card from your graveyard (the
    official rulings: nothing is targeted; any nonland card there, not only the milled ones). The graveyard is public (404.2)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    me = ctx["controller"]
    opponents = [p for p in plan.apnap() if p != me and p in plan.live()]
    if len(opponents) > 1:
        decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose an opponent to choose the card",
               options=[DecisionOption(id=p, label=plan.name(p)) for p in opponents], resume={"step": "opponent_pick100g", "ctx": ctx, "e": e})
        return False
    return _opponent_choose(plan, ctx, e, opponents[0]) if opponents else True


def _opponent_choose(plan: Any, ctx: dict[str, Any], e: dict[str, Any], who: str) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import selectors
    from app.rules.plan import decide

    pool = sorted(selectors.candidates(plan, selectors.from_key(e["sel"]), ctx["controller"], ctx.get("source_card")))
    if not pool:
        return True
    decide(plan, player=who, kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: choose a card for {plan.name(ctx['controller'])} to return to their hand",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool], min_choices=1, max_choices=1,
           resume={"step": "opponent_card100g", "ctx": ctx, "e": e, "pool": pool})
    return False


def resume_opponent_pick(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if len(chosen) != 1 or chosen[0] == d.player or chosen[0] not in plan.live():
        raise ActionError("Choose an opponent")
    if _opponent_choose(plan, d.resume["ctx"], d.resume["e"], chosen[0]):
        effects.continue_effects(plan, d.resume["ctx"])


def resume_opponent_card(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    r = d.resume
    if len(chosen) != 1 or chosen[0] not in r["pool"]:
        raise ActionError("Choose one of those cards")
    if effects._return_cards(plan, r["ctx"], {"do": "return_card", "to": "hand"}, chosen):
        effects.continue_effects(plan, r["ctx"])


def three_each(plan: Any, ctx: dict[str, Any], e: dict[str, Any], picked: list[str] | None = None, todo: list[str] | None = None) -> bool:
    """The Three Seasons III: the controller chooses three cards in each graveyard (all of them when it has fewer; public cards, 404.2), graveyard by
    graveyard in turn order (101.4); then the owners shuffle them in (701.24a) — a player with nothing chosen doesn't shuffle (the official ruling)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    picked = list(picked or [])
    todo = [p for p in plan.apnap() if p in plan.live()] if todo is None else list(todo)
    while todo:
        pid, todo = todo[0], todo[1:]
        cards = list(plan.state.zones.get(f"{pid}:graveyard", []))
        if len(cards) <= 3:
            picked += cards
            continue
        decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: choose three cards in {plan.name(pid)}'s graveyard",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in cards], min_choices=3, max_choices=3,
               resume={"step": "three_each100g", "ctx": ctx, "e": e, "picked": picked, "todo": todo, "pool": cards})
        return False
    groups = {pid: [c for c in picked if plan.state.cards[c].zone == f"{pid}:graveyard"] for pid in plan.apnap()}  # (library cards get new ids)
    for pid, mine in groups.items():
        if mine:
            plan.do({"type": "move", "card_ids": mine, "to": {"player": pid, "zone": "library"}}, actor=pid)
            plan.do({"type": "shuffle", "player": pid, "zone": "library"}, actor=pid)
    return True


def resume_three_each(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    r = d.resume
    if len(set(chosen)) != 3 or not set(chosen) <= set(r["pool"]):
        raise ActionError("Choose three of those cards")
    if three_each(plan, r["ctx"], r["e"], [*r["picked"], *dict.fromkeys(chosen)], r["todo"]):
        effects.continue_effects(plan, r["ctx"])


def landwalk(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Giant Slug, Illusionary Presence, Barbarian Guides: "choose a [basic] land type" as it resolves (205.3i: subtypes only — no "Snow", the
    official ruling), then "[snow] landwalk of the chosen type" (702.14a, c) until end of turn — the choice its controller's (the ruling: the
    activator's, 603.7d)."""
    from app.game.rules_state import DecisionOption
    from app.rules.layers import LAND_TYPES
    from app.rules.plan import decide

    kinds = ["Plains", "Island", "Swamp", "Mountain", "Forest"] if e.get("basic") else sorted(LAND_TYPES - {"Urza's"})
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a {'basic ' if e.get('basic') else ''}land type",
           options=[DecisionOption(id=k, label=k) for k in kinds], min_choices=1, max_choices=1, resume={"step": "landwalk100g", "ctx": ctx, "e": e, "kinds": kinds})
    return False


def resume_landwalk(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    r = d.resume
    if len(chosen) != 1 or chosen[0] not in r["kinds"]:
        raise ActionError("Choose one land type")
    walk = f"{'snow ' if r['e'].get('snow') else ''}{chosen[0].lower()}walk"
    if effects.grant(plan, r["ctx"], {"do": "grant", "who": r["e"]["who"], "keywords": [walk]}):
        effects.continue_effects(plan, r["ctx"])


def random_looked(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Getaway Barrel: "a random creature card from among them" — the table's pick among the revealed cards (public, 701.20a; nobody chooses,
    random_choice's reading), logged; then moved as pick_looked moves a chosen one."""
    import secrets

    from app.rules import effects, selectors

    _, looked = effects._looked(plan, ctx)
    ctx["looked"] = looked
    sel = selectors.from_key(e["sel"])
    pool = sorted(c for c in looked if selectors.matches(plan, sel, plan.state.cards[c], plan.ch(plan.state.cards[c]), ctx["controller"],
                                                         ctx.get("source_card")))
    if not pool:
        return True
    pick = (plan.rng or secrets.SystemRandom()).choice(pool)
    plan.note(f"{ctx.get('name') or 'It'}: chosen at random →", [pick], actor=ctx["controller"])
    return bool(effects._picked(plan, ctx, e, [pick]))


def cyber_linked(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Death in Heaven III: the creature cards exiled with the Saga (607.2a) still in exile, onto the battlefield face down under its controller's
    control as 2/2 Cyberman artifact creatures (708.2a: the effect says what they are; the official rulings)."""
    from app.rules import context, effects

    found = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":exile")
             and "Creature" in plan.ch(plan.state.cards[c]).types]
    context.bind_objects(plan, ctx, "cyber100g", found)
    return bool(effects.return_card(plan, ctx, {"do": "return_card", "who": "ref:cyber100g", "to": "battlefield", "under": "you", "face_down": True,
                                                "spec": "2/2 Cyberman artifact creature"}))


def power_covers(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Vulpine Harvester: "if its mana value is less than or equal to their total power" — the attacking Phyrexians' powers as the ability
    resolves, each as it last existed if it left (the official ruling: counted even if no longer attacking or a Phyrexian; 608.2h; a negative
    total is 0, 107.1b); otherwise the return doesn't happen (608.2c)."""
    from app.rules import context, effects, selectors

    total = max(0, sum(selectors._stat(ch, "power") or 0 for _, ch in context.infos(plan, ctx, context.EVENT)))
    cards = effects._cards(plan, ctx, e["who"])
    if not cards or plan.ch(plan.state.cards[cards[0]]).mana_value > total:
        ctx["next"] = len(ctx["effects"])
    return True


PRIMITIVES = {"named100g": named, "power_covers100g": power_covers, "random_looked100g": random_looked, "cyber_linked100g": cyber_linked, "landwalk100g": landwalk, "three_each100g": three_each, "opponent_pick100g": opponent_pick, "self_exiled100g": self_exiled, "turn_up_linked100g": turn_up_linked, "return_total_power100g": return_total_power, "bottom_linked100g": bottom_linked, "choose_greatest100g": choose_greatest, "choose_event100g": choose_event, "loyalty_twice100g": loyalty_twice, "face_down_looked100g": face_down_looked, "top_or_bottom100g": top_or_bottom}
RESUME = {"landwalk100g": resume_landwalk, "three_each100g": resume_three_each, "opponent_pick100g": resume_opponent_pick, "opponent_card100g": resume_opponent_card, "return_total_power100g": resume_return_total_power, "choose_greatest100g": resume_choose_greatest, "choose_event100g": resume_choose_event, "face_down_looked100g": resume_face_down_looked, "top_or_bottom100g": resume_top_or_bottom}

_BUILT = {
    "For each color, return up to one target card of that color from your graveyard to your hand. Exile ~.": _each_color("card", "Exile ~."),
    "For each color, return up to one target creature card of that color from your graveyard to your hand.": _each_color("creature card"),
    "Create X 2/2 black Zombie Mutant creature tokens, where X is the total number of rad counters among players.": _vault12,
    "Target nontoken creature becomes a 6/6 legendary Horror creature named Fenric and loses all abilities.": _fenric,
    "Until your next turn, whenever you cast an instant or sorcery spell, target player mills cards equal to that spell's mana value.": _nightmares,
    "Return up to three target land cards from your graveyard to the battlefield tapped. Create that many 4/2 green Plant Warrior creature tokens with "
    "reach.": _vengeful_regrowth,
    "Target creature gets -3/-3 until end of turn. If you control a creature with power 4 or greater, you may return up to one target creature card "
    "from your graveyard to your hand.": _clear_the_stage,
    "Return target permanent card from your graveyard to the battlefield with a hexproof counter and an indestructible counter on it.": _perennation,
    "Return target artifact, enchantment, or legendary card from your graveyard to your hand.": _rob_the_hoard,
    "Return one or two target creature cards each with mana value 3 or less from your graveyard to the battlefield.": _leonardos_technique,
    "Reveal cards from the top of your library until you reveal a Doctor card, a card with doctor's companion, or a Vehicle card. Put that card into "
    "your hand and the rest on the bottom of your library in a random order.": _unearthly_child,
}


def parse(body: str) -> Parsed | None:
    body = body.strip()  # (an activated ability's effect text comes after "cost:" with its space)
    if body == "Prevent all combat damage that would be dealt this turn. You may look at each face-down creature that's attacking or blocking.":
        p = _plain("Prevent all combat damage that would be dealt this turn.")  # (Revealing Wind: then a private look, 701.20e; "may": nothing else happens)
        if p is None or [x["do"] for x in p[0]] != ["prevent_all"]:
            return None
        return [*p[0], {"do": "look_face_down", "who": _sel("face-down creature that's attacking or blocking")}], None, False
    if body == ("For each opponent, tap up to one target creature that player controls. Goad those creatures. Until your next turn, whenever any "
                "of those creatures deals combat damage to a player, draw a card."):  # (Kang Dynasty I, II: one watch on all the targets, 603.7c)
        p = _plain("For each opponent, tap up to one target creature that player controls. Goad those creatures.")
        w = _plain("Tap target creature. Until your next turn, whenever that creature deals combat damage to a player, draw a card.")
        if p is None or w is None or [x["do"] for x in w[0]] != ["tap", "delayed", "deferred:draw"] or w[0][1].get("who") != "target":
            return None
        return [*p[0], {**w[0][1], "who": "target:0"}, w[0][2]], p[1], p[2]
    if body == "Target player mills two cards, then exiles their graveyard.":  # (Death in Heaven I, II: the exile linked to III, 607.2a)
        return _plain("Target player mills two cards. Exile that player's graveyard.")
    if body == ("Put all creature cards exiled with ~ onto the battlefield face down under your control. They're 2/2 Cyberman "
                "artifact creatures."):  # (Death in Heaven III)
        return [{"do": "linked_cards", "as": "heaven100g"}, {"do": "cyber_linked100g", "who": "ref:heaven100g"}], None, False
    if body == ("Starting with you, each player votes for innocent or guilty. If guilty gets more votes, the owner of each card exiled with ~ puts "
                "that card on the bottom of their library."):  # (Trial of a Time Lord IV: 701.38 vote, then the linked cards, 607.2a)
        p = _plain("Starting with you, each player votes for innocent or guilty. If guilty gets more votes, draw a card.")
        if p is None or [x["do"] for x in p[0]] != ["vote", "only_if", "draw"]:
            return None
        return [p[0][0], {**p[0][1], "skip": 2}, {"do": "linked_cards", "as": "trial100g"}, {"do": "bottom_linked100g", "who": "ref:trial100g"}], None, False
    if body == "Return two cards exiled with ~ to the battlefield under their owners' control and put the rest on the bottom of their owners' libraries.":
        # (Vault 13 III: two of the linked cards, the controller's choice as it resolves (608.2d), then the rest)
        return [{"do": "linked_cards", "as": "vault13"}, {"do": "return_choice", "who": "ref:vault13", "to": "battlefield", "tapped": False, "under": "owner",
                                                         "n": 2, "upto": False, "label": "card exiled with it"},
                {"do": "bottom_linked100g", "who": "ref:vault13"}], None, False
    if body == ("Surveil 2. You gain 2 life. If this spell was cast from a graveyard, exile it, then put it onto the battlefield transformed under its "
                "owner's control with a finality counter on it."):  # (Esper Origins: 608.2n the spell card moves itself; 712.14a back face up; 122.6)
        p = _plain("Surveil 2. You gain 2 life. If this spell was cast from a graveyard, draw a card.")
        if p is None or [x["do"] for x in p[0]] != ["surveil", "gain_life", "only_if", "draw"]:
            return None
        return [*p[0][:2], {**p[0][2], "skip": 3}, {"do": "spell_self_move", "to": "exile"}, {"do": "self_exiled100g", "as": "esper100g"},
                {"do": "return_card", "who": "ref:esper100g", "to": "battlefield", "tapped": False, "under": "owner", "transformed": True,
                 "counter": "finality"}], None, False
    if body == "Mill two cards, then return a nonland card of an opponent's choice from your graveyard to your hand.":  # (Tasigur)
        p = _plain("Mill two cards.")
        if p is None or [x["do"] for x in p[0]] != ["mill"]:
            return None
        return [*p[0], {"do": "opponent_pick100g", "sel": _sel("nonland card from your graveyard")}], None, False
    if body == "Choose three cards in each graveyard. Their owners shuffle those cards into their libraries.":
        return [{"do": "three_each100g"}], None, False
    if body == ("Choose target opponent. If they control fewer lands than you, create a number of 4/4 green Troll Warrior creature tokens with trample "
                "equal to the difference."):  # (Waking the Trolls III: none when they control as many or more, 107.1b)
        p = _plain("Create a number of 4/4 green Troll Warrior creature tokens with trample equal to the number of lands target opponent controls.")
        if p is None or [x["do"] for x in p[0]] != ["create_token"] or p[1] != "opponent":
            return None
        theirs = p[0][0]["n"]
        return [{**p[0][0], "n": {"minus": [theirs["of"], theirs]}}], p[1], False
    if body == "Exile a creature with the greatest power among creatures target opponent controls.":
        return [{"do": "choose_greatest100g", "who": "target", "as": "impostor100g"}, {"do": "exile", "who": "ref:impostor100g"}], "opponent", False
    if body == "Target opponent may sacrifice a nonland, nontoken permanent of their choice. If they don't, they lose 2 life and you draw a card.":
        p = _plain("Target opponent loses 2 life unless they sacrifice a nonland, nontoken permanent.")  # (Braids's Frightful Return III: 118.12, "unless")
        if p is None or [x["do"] for x in p[0]] != ["optional_payment", "only_if", "lose_life"]:
            return None
        return [p[0][0], {**p[0][1], "skip": 2}, p[0][2], {"do": "draw", "who": "you", "n": 1}], p[1], False
    if body == "You may activate the loyalty abilities of planeswalkers you control twice this turn rather than only once.":
        return [{"do": "loyalty_twice100g"}], None, False
    if body == "Look at the top two cards of your library. Manifest one of those cards, then put the other on the top or bottom of your library.":
        return [{"do": "look_top", "n": 2, "player": "you", "reveal": False}, {"do": "face_down_looked100g", "n": 1, "kind": "manifest"},
                {"do": "top_or_bottom100g"}], None, False
    if body == "Look at the top five cards of your library, cloak two of them, and put the rest on the bottom of your library in a random order.":
        return [{"do": "look_top", "n": 5, "player": "you", "reveal": False}, {"do": "face_down_looked100g", "n": 2, "kind": "cloak"},
                {"do": "rest_looked", "to": "bottom_random"}], None, False
    if (native := REWRITES.get(body)) is not None:
        return _plain(native)
    build = _BUILT.get(body)
    return build() if build is not None else None


# -- whole abilities -- an Oracle line read as a native line (its definition), then, where needed, one field of it changed.
POWER_NE_BASE = "power_ne_base100g"  # a selector extra: its power isn't its base power (208.4b: after layers 7a-7b, before counters and 7c)
TRANSFORMED = "transformed100g"  # a selector extra: a transformed permanent (701.27g: a double-faced permanent with its back face up; never melded or merged)
# a selector extra: blocking the source (509.1g) — a dying creature as it last existed (603.10a: triggers._snapshot_card keeps its blocks)
BLOCKING_SOURCE = "blocks_this100g"


def extra_ok(plan: Any, extra: str, card: Any, ch: Any, source: str | None = None) -> bool:
    from app.rules import characteristics as chars
    from app.rules import selectors

    if extra == POWER_NE_BASE:
        return ch.base_pt is not None and (selectors._stat(ch, "power") or 0) != ch.base_pt[0]
    if extra == BLOCKING_SOURCE:
        return source is not None and card.blocks(source)
    if extra == TRANSFORMED:  # (static_conditions' "you control a transformed permanent" test, per permanent)
        return card.zone.endswith(":battlefield") and card.face == 1 and not card.face_down and not card.melded and not card.merged \
            and chars.transformable(card, plan.info)
    return False


def attacked(plan: Any, you: str) -> int:
    """The players ``you`` attacked in this combat's declaration (508.1), whether or not they or the attackers are still there (the official
    ruling, as melee counts them; a creature put onto the battlefield attacking was never declared)."""
    return len([p for p in plan.rules.attacked_players.get(you, []) if p != you])


def _custodi(d: dict[str, Any]) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import selectors

    t = d.get("target") or {}
    s = selectors.from_key(t["what"]) if str(t.get("what", "")).startswith(selectors.PREFIX) else None
    if s is None or s.compare != (("mv", "<=", 3),):
        return None
    return {**d, "target": {**t, "what": replace(s, compare=(("mv", "<=", "attacked100g"),)).key()}}


def _with_extra(key: str, extra: str) -> str:
    from dataclasses import replace

    from app.rules import selectors

    s = selectors.from_key(key)
    return replace(s, extras=(*s.extras, extra)).key()


def _jason(d: dict[str, Any]) -> dict[str, Any] | None:
    """Jason Bright: the creature as it last existed on the battlefield (603.10a, 608.2h): an intervening "if" about that fixed information holds
    as it resolves exactly when it held as it triggered (603.4), so it is the trigger's own filter."""
    cond = d.get("cond") or {}
    if cond.get("event") != "die" or cond.get("subject") != "sel":
        return None
    return {**d, "cond": {**cond, "sel": _with_extra(cond["sel"], POWER_NE_BASE)}}


def _connoisseur(d: dict[str, Any]) -> dict[str, Any] | None:
    each = d.get("each") or {}
    if d.get("static") != "grant" or not (each.get("value") or {}).get("count"):
        return None
    from app.rules.selectors import Selector

    return {**d, "each": {**each, "value": {"count": Selector(controller="you", extras=(TRANSFORMED,)).key()}}}


def _garruk(d: dict[str, Any]) -> dict[str, Any] | None:
    """Garruk Relentless: a state trigger (603.8; the official ruling: it can't retrigger while on the stack)."""
    from app.rules import conditions

    state = conditions.parse("~ has two or fewer loyalty counters on it", objects=True)
    return {**d, "state": state} if d.get("trigger") == "state" and state is not None else None


def _harvest_wurm(d: dict[str, Any]) -> dict[str, Any] | None:
    """Harvest Wurm: "unless you return …" — a choice of none or one basic land card from your graveyard as it resolves (the official rulings: with
    none to return it is sacrificed; the card may be returned even if the Wurm has left)."""
    if [e.get("do") for e in d["effects"]] != ["optional_payment", "only_if", "sacrifice"]:
        return None
    back = {"do": "return_choice", "to": "hand", "sel": _sel("basic land card from your graveyard"), "n": 1, "upto": True,
            "label": "basic land card", "as": "wurm100g"}
    none = {"do": "only_if", "cond": {"value": {"this_way": "returned", "of": None, "ref_count": "wurm100g"}, "op": "<=", "n": 0}, "skip": 1}
    return {**d, "effects": [back, none, d["effects"][2]]}


_TIME_LORD_DIES = ("When this creature dies, reveal cards from the top of your library until you reveal a Time Lord creature card. Put that card onto the "
                   "battlefield and the rest on the bottom of your library in a random order.")


def _time_lord(key: str) -> str:
    """The same selector with the creature type Time Lord for Doctor (205.3m)."""
    from dataclasses import replace

    from app.rules import selectors

    s = selectors.from_key(key)
    return replace(s, subtypes=tuple("Time Lord" if t == "Doctor" else t for t in s.subtypes)).key()


def _time_lord_regeneration() -> Parsed | None:
    """Time Lord Regeneration: until end of turn (611.2a) the target Time Lord has the dies trigger (its definition: _AS)."""
    p = _plain(f'Until end of turn, target Doctor you control gains "{_TIME_LORD_DIES}"')
    if p is None or [e["do"] for e in p[0]] != ["grant"] or not isinstance(p[1], str):
        return None
    return p[0], _time_lord(p[1]), False


_BUILT[f'Until end of turn, target Time Lord you control gains "{_TIME_LORD_DIES.replace("this creature", "~")}"'] = _time_lord_regeneration  # (the body as self_text gives it)


def _token_text(text: str, *, name: str | None = None, add: bool = False) -> Any:
    """The one token the native line creates, with these rules text lines ("this creature": the token itself, as its own dies trigger reads it)."""
    def fix(d: dict[str, Any]) -> dict[str, Any] | None:
        effects = d["effects"]
        if [e.get("do") for e in effects] != ["create_token"] or (name is not None and effects[0]["token"].get("name") != name):
            return None
        token = effects[0]["token"]
        return {**d, "effects": [{**effects[0], "token": {**token, "text": f"{token['text']}\n{text}" if add else text}}]}
    return fix


def _walk(**flags: bool) -> Any:
    """The native line's forestwalk grant made the chosen type's landwalk (zones100g.landwalk), deferred with it."""
    def fix(d: dict[str, Any]) -> dict[str, Any] | None:
        es = d["effects"]
        i = next((i for i, e in enumerate(es) if e.get("do") in ("grant", "deferred:grant") and e.get("keywords") == ["forestwalk"]), None)
        return None if i is None else {**d, "effects": [*es[:i], {"do": es[i]["do"].replace("grant", "landwalk100g"), "who": es[i]["who"], **flags},
                                                         *es[i + 1:]]}
    return fix


_AS: dict[str, tuple[str, Any]] = {
    # Reef Worm: each token's dies trigger makes the next one (the inner quotes are the Whale's own ability)
    "When this creature dies, create a 3/3 blue Fish creature token with \"When this token dies, create a 6/6 blue Whale creature token with 'When this "
    "token dies, create a 9/9 blue Kraken creature token.'\"": (
        "When this creature dies, create a 3/3 blue Fish creature token.",
        _token_text('When this creature dies, create a 6/6 blue Whale creature token with "When this creature dies, create a 9/9 blue Kraken creature '
                    'token."')),
    # Ozox: Jumblebones, its two abilities (the name in them is the token's own, 201.5)
    "When Ozox dies, create Jumblebones, a legendary 2/1 black Skeleton creature token with \"Jumblebones can't block\" and \"When Jumblebones leaves "
    "the battlefield, return target card named Ozox, the Clattering King from your graveyard to your hand.\"": (
        "When ~ dies, create Jumblebones, a legendary 2/1 black Skeleton creature token with \"Jumblebones can't block.\"",
        _token_text("When Jumblebones leaves the battlefield, return target card named Ozox, the Clattering King from your graveyard to your hand.",
                    name="Jumblebones", add=True)),
    # Lifeline: "the first card" is the dying creature's card (its new object, 400.7); "another creature" — the dying one isn't on the battlefield any
    # more, so any creature there is another (checked as it triggers and resolves, 603.4); each trigger its own delayed return (the official rulings)
    "Whenever a creature dies, if another creature is on the battlefield, return the first card to the battlefield under its owner's control at the "
    "beginning of the next end step.": ("Whenever a creature dies, if a creature is on the battlefield, return that card to the battlefield under its "
                                        "owner's control at the beginning of the next end step.", None),
    # Catapult Fodder: each of the three by itself (the official ruling)
    "At the beginning of combat on your turn, if you control three or more creatures that each have toughness greater than their power, transform "
    "this creature.": ("At the beginning of combat on your turn, if you control three or more creatures with toughness greater than their power, "
                       "transform this creature.", None),
    # Edgar Markov's Coffin: "Then if": a condition of the instructions after it (608.2c), not an intervening "if"; "those counters": every bloodline counter
    "At the beginning of your upkeep, create a 1/1 white and black Vampire creature token with lifelink and put a bloodline counter on Edgar Markov's "
    "Coffin. Then if there are three or more bloodline counters on it, remove those counters and transform it.":
        ("At the beginning of your upkeep, create a 1/1 white and black Vampire creature token with lifelink. Put a bloodline counter on ~. If ~ has "
         "three or more bloodline counters on it, remove all bloodline counters from ~ and transform ~.", None),
    "When Garruk has two or fewer loyalty counters on him, transform him.": ("When ~ has no loyalty counters on it, transform ~.", _garruk),
    # Guardian Scalelord: "X or less, where X is this creature's power" — its power as the target is chosen and again as it resolves (608.2b; 107.3c),
    # as it last existed if it has left (608.2h: selectors.source_stat)
    "Whenever this creature attacks, return target nonland permanent card with mana value X or less from your graveyard to the battlefield, where X "
    "is this creature's power.": ("Whenever this creature attacks, return target nonland permanent card with mana value less than or equal to this "
                                  "creature's power from your graveyard to the battlefield.", None),
    # Rekindling Phoenix's Elemental: two instructions, in order (608.2c); the one target is the whole ability's — an illegal one, nothing
    # happens and the token stays (608.2b; the official ruling); the card named Rekindling Phoenix, whatever copies it (the official ruling)
    "At the beginning of your upkeep, sacrifice this token and return target card named Rekindling Phoenix from your graveyard to the battlefield. "
    "It gains haste until end of turn.": ("At the beginning of your upkeep, sacrifice this creature. Return target card named Rekindling Phoenix from "
                                          "your graveyard to the battlefield. It gains haste until end of turn.", None),
    # Zurgo and Ojutai: the look as the native line, then the optional return of one of the Dragons of the batch (choose_event100g)
    "Whenever one or more Dragons you control deal combat damage to a player or battle, look at the top three cards of your library. Put one of them "
    "into your hand and the rest on the bottom of your library in any order. You may return one of those Dragons to its owner's hand.": (
        "Whenever one or more Dragons you control deal combat damage to a player or battle, look at the top three cards of your library. Put one of "
        "them into your hand and the rest on the bottom of your library in any order.",
        lambda d: {**d, "effects": [*d["effects"], {"do": "choose_event100g", "as": "zurgo100g"}, {"do": "bounce", "who": "ref:zurgo100g"}]}),
    # Woodcaller Automaton: the land's base power and toughness set (layer 7b, 613.4b) to the Automaton's as the ability resolves, or as it last
    # existed (the official ruling; 608.2h) — 3/3 when cast prototyped (702.160)
    "When this creature enters, if you cast it, untap target land you control. It becomes a Treefolk creature with haste and base power and "
    "toughness equal to this creature's power and toughness. It's still a land.": (
        "When this creature enters, if you cast it, untap target land you control. It becomes a 3/3 Treefolk creature with haste. It's still a land.",
        lambda d: {**d, "effects": [{**e, "p": {"power": "self"}, "t": {"toughness": "self"}} if e.get("do") == "become" and (e.get("p"), e.get("t")) == (3, 3)
                                    else e for e in d["effects"]]}),
    # Time Lord Regeneration's granted ability: "Time Lord" is one creature type of two words (205.3m), which the phrase grammar doesn't split
    _TIME_LORD_DIES: ("When this creature dies, reveal cards from the top of your library until you reveal a Doctor creature card. Put that card onto "
                      "the battlefield and the rest on the bottom of your library in a random order.",
                      lambda d: {**d, "effects": [{**e, "until": _time_lord(e["until"])} if e.get("do") == "look_top" and e.get("until") else e
                                                  for e in d["effects"]]}),
    # Moorland Rescuer: the return (return_total_power100g), then "Exile this card": the card it became in the graveyard (400.7, event.new)
    "When this creature dies, return any number of other creature cards with total power X or less from your graveyard to the battlefield, where X is "
    "this creature's power. Exile this card.": (
        "When this creature dies, exile it.",
        lambda d: {**d, "effects": [{"do": "return_total_power100g", "sel": _sel("creature card from your graveyard")}, *d["effects"]]}
        if [e.get("do") for e in d["effects"]] == ["exile"] else None),
    # Custodi Soulcaller: X as the target is chosen and again as it resolves (608.2b) — the same number, the declaration's (zones100g.attacked)
    "Whenever this creature attacks, return target creature card with mana value X or less from your graveyard to the battlefield, where X is the "
    "number of players you attacked this combat.": ("Whenever this creature attacks, return target creature card with mana value 3 or less from your "
                                                    "graveyard to the battlefield.", _custodi),
    # Summoner's Egg: the linked card (607.2a) turned face up, then onto the battlefield if it's a creature card (zones100g.turn_up_linked)
    "When this creature dies, turn the exiled card face up. If it's a creature card, put it onto the battlefield under your control.": (
        "When this creature dies, draw a card.",
        lambda d: {**d, "effects": [{"do": "linked_cards", "as": "egg100g"}, {"do": "turn_up_linked100g", "who": "ref:egg100g", "as": "egg_creature100g"},
                                    {"do": "return_card", "who": "ref:egg_creature100g", "to": "battlefield", "tapped": False, "under": "you"}]}),
    # Imperial Mask: 102.3: teammates are the other players of a team; the engine's Commander game is Free-for-All (903.2, 806: no teams), so
    # nobody creates a token — the ability still triggers (603.4, not a token) and does nothing
    "When this enchantment enters, if it's not a token, each of your teammates creates a token that's a copy of this enchantment.": (
        "When this enchantment enters, if it's not a token, draw a card.", lambda d: {**d, "effects": []} if d.get("if") else None),
    # Olivia, Crimson Bride: "you don't control a legendary Vampire" is "you control no legendary Vampires" (a state trigger of the creature, 603.8)
    "Whenever Olivia attacks, return target creature card from your graveyard to the battlefield tapped and attacking. It gains \"When you don't "
    "control a legendary Vampire, exile this creature.\"": ("Whenever ~ attacks, return target creature card from your graveyard to the battlefield "
                                                           "tapped and attacking. It gains \"When you control no legendary Vampires, exile this "
                                                           "creature.\"", None),
    "This creature gets +1/+0 for each transformed permanent you control.": ("This creature gets +1/+0 for each artifact you control.", _connoisseur),
    "Whenever a Zombie or Mutant you control dies, if its power was different from its base power, draw a card.":
        ("Whenever a Zombie or Mutant you control dies, draw a card.", _jason),
    # Veiled Ascension: "a flying counter" is one more flying counter than it would enter with otherwise, as "an additional" one (614.1c, 122.6)
    "Face-down creatures you control enter with a flying counter on them.": ("Face-down creatures you control enter with an additional flying counter "
                                                                             "on them.", None),
    # Baneclaw Marauder: the blocker as it last existed (603.10a), its controller then (608.2h)
    "Whenever a creature blocking this creature dies, that creature's controller loses 1 life.":
        ("Whenever a blocking creature dies, that creature's controller loses 1 life.",
         lambda d: {**d, "cond": {**d["cond"], "sel": _with_extra(d["cond"]["sel"], BLOCKING_SOURCE)}} if (d.get("cond") or {}).get("event") == "die" else None),
    # Giant Slug, Illusionary Presence, Barbarian Guides: the land type chosen as it resolves, then that landwalk (zones100g.landwalk)
    "{5}: At the beginning of your next upkeep, choose a basic land type. This creature gains landwalk of the chosen type until the end of that "
    "turn.": ("{5}: At the beginning of your next upkeep, this creature gains forestwalk until end of turn.", _walk(basic=True)),
    "At the beginning of your upkeep, choose a land type. This creature gains landwalk of the chosen type until end of turn.":
        ("At the beginning of your upkeep, this creature gains forestwalk until end of turn.", _walk()),
    "{2}{R}, {T}: Choose a land type. Target creature you control gains snow landwalk of the chosen type until end of turn. Return that creature "
    "to its owner's hand at the beginning of the next end step.": (
        "{2}{R}, {T}: Target creature you control gains forestwalk until end of turn. Return that creature to its owner's hand at the beginning of "
        "the next end step.", _walk(snow=True)),
    # Getaway Barrel: the table's pick among the revealed creature cards (zones100g.random_looked)
    "When this artifact is put into a graveyard from the battlefield, reveal the top thirteen cards of your library. Put a random creature card "
    "from among them onto the battlefield. Put the rest on the bottom of your library in a random order.": (
        "When this artifact is put into a graveyard from the battlefield, reveal the top thirteen cards of your library. Put a creature card from "
        "among them onto the battlefield. Put the rest on the bottom of your library in a random order.",
        lambda d: {**d, "effects": [{**e, "do": "random_looked100g"} if e.get("do") == "pick_looked" and not e.get("optional") else e
                                    for e in d["effects"]]}),
    # Vulpine Harvester: any artifact card is a legal target; the power check as it resolves (zones100g.power_covers)
    "Whenever one or more Phyrexians you control attack, return target artifact card from your graveyard to the battlefield if its mana value "
    "is less than or equal to their total power.": (
        "Whenever one or more Phyrexians you control attack, return target artifact card from your graveyard to the battlefield.",
        lambda d: {**d, "effects": [{"do": "power_covers100g", "who": "target"}, *d["effects"]]}
        if [e.get("do") for e in d["effects"]] == ["return_card"] else None),
    "When this creature enters, sacrifice it unless you return a basic land card from your graveyard to your hand.":
        ("When this creature enters, sacrifice it unless you discard a card.", _harvest_wurm),
}


_AS[_TIME_LORD_DIES.replace("this creature", "~")] = _AS[_TIME_LORD_DIES]  # (the grant's own check reads it with ~ for "this creature")


def native(text: str) -> str:
    """The native words of a line read as another line with nothing changed (its meaning the same), else the line itself."""
    found = _AS.get(text)
    return found[0] if found is not None and found[1] is None else text


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    found = _AS.get(ability.text)
    if found is None:
        return None
    from dataclasses import replace

    from app.rules import scripts

    native = scripts.define(replace(ability, text=found[0]), ch)
    return native if native is None or found[1] is None else found[1](native)
