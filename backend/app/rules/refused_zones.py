"""Forms the reanimation, tutor and sized-amount waves first left manual (wave 3R4): helpers that
need a decision of their own. A leaf module over app/rules/effects.py, which registers its
primitives and resume handlers.

Researched against the Comprehensive Rules of 2026-09-25 (data/rules/comprehensive_rules/).

* "Return target creature card from your graveyard to the battlefield tapped and attacking" (508.4):
  the creature's controller, if they are the attacking player (506.3b), chooses which defending
  player, planeswalker or battle it attacks; it was never declared as an attacker (no attack
  triggers, 508.4c ignores attack requirements). Outside the combat phase (506.3) or for a player
  who isn't attacking, it just enters tapped. Entering after blockers were declared, it is
  unblocked (508.4d: app/rules/combat.py reads ``RulesState.blocked``). Noncreatures and battles
  never attack (506.3a, 506.3f).
* Gifts piles: "Search your library for up to four [land] cards with different names and reveal them.
  Target opponent / An opponent chooses two of those cards. Put the chosen cards into your graveyard
  and the rest into your hand [onto the battlefield tapped]. Then shuffle." (Gifts Ungiven, Realms
  Uncharted, Elemental Teachings). The search is a private choice (701.23, 401.2); the cards found are
  revealed (701.20a), so the opponent's choice may show them. "An opponent" is chosen by the spell's
  controller as it resolves (the 801 example: the caster chooses which opponent makes the choice). With
  two or fewer cards found, all of them are "the chosen cards" (Gifts' rulings). The library is
  shuffled at the end (701.24).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key
from app.rules import player_control, selectors, token_grammar
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan


def enter_attacking(plan: Plan, ctx: dict[str, Any], cards: list[str], at: dict[str, Any] | None = None) -> bool:
    """The returned ``cards`` (now on the battlefield) become attacking creatures (508.4): token_grammar.enter_attacking, the one reading of it.
    True when done; False when their controller is asked whom they attack (the resolution then pauses)."""
    return token_grammar.enter_attacking(plan, ctx, cards, at)


# -- Gifts piles ---------------------------------------------------------------------------------------
_GIFTS = re.compile(
    r"Search your library for up to (?P<n>two|three|four|five) (?P<sel>(?:[a-z]+ )?cards?) with different names and reveal "
    r"them\. (?P<who>Target opponent|An opponent) chooses (?P<k>one|two) of those cards\. Put the chosen cards? into your "
    r"graveyard and the rest (?P<rest>into your hand|onto the battlefield tapped)(?:\. Then shuffle|, then shuffle)\.")
_EXACT_SPLIT = re.compile(
    r"Search your library for (?P<n>two|three|four|five) cards and reveal them\. "
    r"Target opponent chooses one\. Put that card into your hand and the rest into your graveyard\. Then shuffle\.")
_TURTLES = ("Search your library and/or outside the game for exactly four legendary creature cards you own with different names, then reveal those cards. "
            "An opponent chooses two of them. Put the chosen cards into your hand and shuffle the rest into your library.")  # (wave 110I)
_N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def gifts_ability(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """The whole text of a Gifts-style spell as one effect (scripts.parse_effects), or None."""
    from app.rules import search_packets

    if (packet := search_packets.parse(body)) is not None:
        return packet
    if body.strip() == _TURTLES:  # -- final pass (wave 110I) -- 903.11: no card can come from outside the game here, so only the library is searched; 701.23b: a hidden zone may be searched without finding (all four or none)
        turtles_sel = selectors.parse("legendary creature card")
        assert turtles_sel is not None
        return [{"do": "gifts", "sel": selectors.replace(turtles_sel, zones=("library",), zone_owner="you", card=True).key(), "max": 4, "k": 2,
                 "label": "legendary creature cards", "chooser": "opponent", "exact": True, "none_ok": True, "chosen_to": "hand", "rest": "stay"}], None, False
    if exact := _EXACT_SPLIT.fullmatch(body.strip()):
        exact_sel = selectors.parse("card")
        assert exact_sel is not None
        exact_key = selectors.replace(exact_sel, zones=("library",), zone_owner="you", card=True).key()
        return [{"do": "gifts", "sel": exact_key, "max": _N[exact["n"]], "k": 1, "label": "cards",
                 "chooser": "target", "exact": True, "different_names": False,
                 "chosen_to": "hand", "rest": "graveyard"}], "opponent", False
    m = _GIFTS.fullmatch(body.strip())
    if m is None:
        return None
    sel = selectors.parse(m["sel"].replace("cards", "card"))
    if sel is None or not sel.card or sel.player is not None:
        return None
    key = selectors.replace(sel, zones=("library",), zone_owner="you", card=True).key()
    target = "opponent" if m["who"] == "Target opponent" else None
    return [{"do": "gifts", "sel": key, "max": _N[m["n"]], "k": _N[m["k"]], "label": m["sel"],
             "chooser": "target" if target else "opponent",
             "rest": "hand" if m["rest"] == "into your hand" else "battlefield_tapped"}], target, False


def gifts(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import (
        wave110i_cards,  # -- cards (wave 110I) -- Panglacial Wurm: the cast window before the cards are found
    )

    pid = ctx["controller"]
    library = plan.state.zones.get(zone_key(pid, "library"), [])
    from app.rules import (
        prohibitions,  # -- prohibitions (wave 22B) -- 614.17: "Players can't search libraries." (nothing can be found)
    )

    if (why := prohibitions.cant_search(plan, pid, ctx["controller"])) is not None:
        plan.note(f"{why}: {plan.name(pid)} can't search their library", actor=pid)
        library = []
    else:
        prohibitions.note_search(plan, pid, pid)  # -- most-played cards (wave 43B) -- "Whenever an opponent searches their library"; Aven Mindcensor: the top four
        library = library[:prohibitions.search_depth(plan, pid)]
    from app.rules import card_names

    sel = selectors.from_key(e["sel"])
    pool = [*library, *(plan.state.zones.get(zone_key(pid, "graveyard"), []) if "graveyard" in e.get("zones", []) else [])]
    matching = [c for c in pool
                if selectors.matches(plan, sel, plan.state.cards[c], plan.ch(plan.state.cards[c]), pid)
                and (not e.get("excluded_name") or not card_names.has_name(plan.ch(plan.state.cards[c]), e["excluded_name"]))]
    count = min(e["max"], len(matching))
    if e.get("none_ok"):  # different names: at most one found card per name
        count = min(e["max"], len({(plan.state.cards[c].name or "").lower() for c in matching}))
        e = {**e, "need": count}
    quantity = str(e["max"]) if e.get("exact") else f"up to {e['max']}"
    names = " with different names" if e.get("different_names", True) else ""
    least = count if e.get("exact") and not e.get("none_ok") else 0
    options = [DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in matching]
    pang = wave110i_cards.pang_options(plan, e, pid)  # -- cards (wave 110I) -- Panglacial Wurm: one extra option of this same decision (nothing extra shown to the others)
    bounds = {"pang_least": least, "pang_greatest": count} if pang else {}
    decide(plan, player=pid, kind="choose_cards", prompt=f"Search your library ({quantity} {e['label']}{names})",
           options=[*options, *pang],
           min_choices=0 if pang else least, max_choices=count + bool(pang), resume={"step": "gifts_found", "ctx": ctx, "e": e, **bounds},
           decider=player_control.search_controller(plan, pid))  # (wave 18H) 723.2: Opposition Agent
    return False


def resume_gifts_found(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects, wave110i_cards

    if wave110i_cards.pang_resume(plan, d, chosen):
        return
    wave110i_cards.pang_forced(d, chosen)
    ctx, e = d.resume["ctx"], d.resume["e"]
    names = [(plan.state.cards[c].name or "").lower() for c in chosen]
    from app.rules import card_names

    unique = (not any(card_names.share(plan.ch(plan.state.cards[a]), plan.ch(plan.state.cards[b]))
                      for i, a in enumerate(chosen) for b in chosen[i + 1:]) if e.get("packet") else len(set(names)) == len(names))
    if e.get("different_names", True) and not unique:
        from app.game.errors import ActionError

        raise ActionError("The cards you find must have different names")
    if e.get("none_ok") and len(chosen) not in (0, e["need"]):
        from app.game.errors import ActionError

        raise ActionError(f"Find exactly {e['need']} cards (or none)")
    if e.get("different_power"):
        powers = [plan.ch(plan.state.cards[c]).pt for c in chosen]
        numbers = [pt[0] if pt is not None else 0 for pt in powers]
        if len(set(numbers)) != len(numbers):
            from app.game.errors import ActionError

            raise ActionError("The cards you find must have different powers")
    agents = player_control.search_exile(plan, d.player)
    diverted = [c for c in chosen if agents and plan.state.cards[c].zone.endswith(":library")]
    if diverted:  # (wave 18H) Opposition Agent: each card found is exiled (a new
        for cid in diverted:  # object, 400.7: the piles are never made) and its controller may play it
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": d.player, "zone": "exile"}}, actor=d.player)
        player_control.permit_exiled(plan, agents, diverted)
        chosen = [c for c in chosen if c not in diverted]
        if not chosen:
            _gifts_finish(plan, ctx, e, [], [])
            return
    if e.get("exile_first") and chosen:
        plan.do({"type": "move", "card_ids": list(chosen), "to": {"player": d.player, "zone": "exile"}}, actor=d.player)
    for cid in chosen:
        plan.do({"type": "reveal", "card_ids": [cid]}, actor=d.player)  # 701.20a: to everyone
    found = list(chosen)
    if e.get("packet"):
        e = {**e, "found_objects": {c: plan.oid(plan.state.cards[c]) for c in found}}
    if e.get("chooser") == "random_distinct_three":
        import secrets

        from app.rules import randomness  # -- random choices (wave MBC-D) --
        picked = randomness.sample(plan, plan.rng or secrets.SystemRandom(), found, 1, kind='card', player=ctx['controller']) if len(found) == 3 and unique else []
        _gifts_finish(plan, ctx, e, found, picked)
        return
    if len(found) <= e["k"]:
        _gifts_finish(plan, ctx, e, found, found)
        return
    if e["chooser"] == "target":
        who = effects._players(plan, ctx, "target")
        if not who:
            _gifts_finish(plan, ctx, e, found, [])  # (the target player left: nobody chooses)
            return
        _ask_opponent(plan, ctx, e, found, who[0])
        return
    opponents = [p for p in plan.live() if p != ctx["controller"]]
    if len(opponents) == 1:
        _ask_opponent(plan, ctx, e, found, opponents[0])
        return
    decide(plan, player=ctx["controller"], kind="choose_one", prompt="Which opponent chooses?",
           options=[DecisionOption(id=p, label=plan.name(p)) for p in opponents],
           resume={"step": "gifts_opponent", "ctx": ctx, "e": e, "found": found})


def resume_gifts_opponent(plan: Plan, d: Any, chosen: list[str]) -> None:
    _ask_opponent(plan, d.resume["ctx"], d.resume["e"], d.resume["found"], chosen[0])


def _ask_opponent(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], found: list[str], opponent: str) -> None:
    decide(plan, player=opponent, kind="choose_cards", prompt=f"{ctx.get('name') or 'Gifts'}: choose {e['k']} for the {e.get('chosen_to', 'graveyard')}",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in found],
           min_choices=e["k"], max_choices=e["k"], resume={"step": "gifts_split", "ctx": ctx, "e": e, "found": found})


def resume_gifts_split(plan: Plan, d: Any, chosen: list[str]) -> None:
    _gifts_finish(plan, d.resume["ctx"], d.resume["e"], d.resume["found"], list(chosen))


def _gifts_finish(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], found: list[str], chosen: list[str]) -> None:
    from app.rules import attachments, effects

    pid = ctx["controller"]
    found = [c for c in found if c in plan.state.cards and (
        plan.oid(plan.state.cards[c]) == e["found_objects"].get(c) if e.get("packet") else
        plan.state.cards[c].zone == zone_key(pid, "library"))]
    picked = [c for c in found if c in chosen]
    rest = [c for c in found if c not in chosen]
    if picked:
        plan.do({"type": "move", "card_ids": picked, "to": {"player": pid, "zone": e.get("chosen_to", "graveyard")}}, actor=pid)
    if rest and e["rest"] in ("battlefield", "battlefield_tapped"):
        entries = [{"card": c, "player": pid, "actor": pid, "tapped": e["rest"] == "battlefield_tapped"} for c in rest]
        if not attachments.enter(plan, entries, ctx, shuffle=pid):
            return  # (an Aura chooses what it enchants; the library is shuffled on resume)
    elif rest and e["rest"] == "cast":
        from app.rules import context

        context.bind_objects(plan, ctx, "packet_casts", rest)
        at = ctx["next"]
        ctx["effects"][at:at] = [{"do": "free_cast", "zone": "that", "who": "ref:packet_casts", "n": 99,
                                  "exact_refs": True, "optional": True}]
    elif rest and e["rest"] != "stay":  # "stay": still in the library, shuffled below
        plan.do({"type": "move", "card_ids": rest, "to": {"player": pid, "zone": e["rest"]}}, actor=pid)
    plan.do({"type": "shuffle", "player": pid, "zone": "library"}, actor=pid)
    effects.continue_effects(plan, ctx)


# -- "You may mill N cards. Then …" --------------------------------------------------------------------------
def may_mill(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """701.17: the controller may mill; the rest of the ability happens whether or not they did."""
    decide(plan, player=ctx["controller"], kind="confirm", prompt=f"{ctx.get('name') or 'It'}: mill {e['n']} cards?",
           options=[DecisionOption(id="yes", label=f"Mill {e['n']}"), DecisionOption(id="no", label="Don't mill")],
           resume={"step": "may_mill", "ctx": ctx, "e": e})
    return False


def resume_may_mill(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    if chosen and chosen[0] == "yes":
        effects.mill(plan, ctx, {"who": "you", "n": e["n"]})
    effects.continue_effects(plan, ctx)


PRIMITIVES: dict[str, Any] = {"gifts": gifts, "may_mill": may_mill}
RESUME = {"enter_attacking": token_grammar.resume_token_attack, "gifts_found": resume_gifts_found,
          "gifts_opponent": resume_gifts_opponent, "gifts_split": resume_gifts_split, "may_mill": resume_may_mill}
