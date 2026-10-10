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
from app.rules import player_control, selectors
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

_ATTACKING_PHASES = ("declare_attackers", "declare_blockers", "combat_damage", "end_combat")


def enter_attacking(plan: Plan, ctx: dict[str, Any], cards: list[str]) -> bool:
    """The returned ``cards`` (now on the battlefield) become attacking creatures (508.4). True when
    done; False when their controller is asked whom they attack (the resolution then pauses)."""
    from app.rules import battles

    pid = ctx["controller"]
    attackers = [c for c in cards if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")
                 and plan.state.cards[c].controller == pid and plan.ch(plan.state.cards[c]).is_creature
                 and not battles.is_battle(plan.ch(plan.state.cards[c]))]
    if not attackers or plan.state.turn.phase not in _ATTACKING_PHASES or pid != plan.active:
        return True
    defenders = [p for p in plan.live() if p != pid]
    options = [DecisionOption(id=p, label=plan.name(p)) for p in defenders]
    options += [DecisionOption(id=c.id, label=f"{c.name} ({plan.name(c.controller)})", card_id=c.id)
                for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller in defenders
                and plan.in_game(c) and "Planeswalker" in plan.ch(c).types]
    options += [DecisionOption(id=b, label=f"{plan.state.cards[b].name} (battle)", card_id=b)
                for b in battles.attackable(plan.state, pid, defenders, plan.ch)]
    if not options:
        return True
    if len(options) == 1:
        _attack_with(plan, attackers, options[0].id, pid)
        return True
    # -- falsification (wave 30D) -- 508.4: one question per creature (token_grammar.enter_attacking), the rest follow in ``more``
    decide(plan, player=pid, kind="choose_one",
           prompt=f"{plan.state.cards[attackers[0]].name or 'Creature'} enters attacking: attacking whom?"
           + (f" ({len(attackers) - 1} more to place)" if len(attackers) > 1 else ""),
           options=options, resume={"step": "enter_attacking", "ctx": ctx, "cards": attackers[:1], "more": attackers[1:]})
    return False


def _attack_with(plan: Plan, cards: list[str], target: str, actor: str) -> None:
    kind = "player" if target in plan.state.players else "card"
    cards = [c for c in cards if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")]
    if kind == "card" and (target not in plan.state.cards or not plan.state.cards[target].zone.endswith(":battlefield")):
        return  # 508.4a: the planeswalker or battle is gone: never an attacking creature
    if kind == "player" and target not in plan.live():
        return  # 508.4a: that player left the game
    if cards:
        plan.do({"type": "attack", "card_ids": cards, "target": {"kind": kind, "id": target}}, actor=actor)


def resume_enter_attacking(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if chosen:
        _attack_with(plan, d.resume["cards"], chosen[0], d.player)
    if d.resume.get("more") and not enter_attacking(plan, d.resume["ctx"], d.resume["more"]):  # (wave 30D: the next creature)
        return
    effects.continue_effects(plan, d.resume["ctx"])


# -- Gifts piles ---------------------------------------------------------------------------------------
_GIFTS = re.compile(
    r"Search your library for up to (?P<n>two|three|four|five) (?P<sel>(?:[a-z]+ )?cards?) with different names and reveal "
    r"them\. (?P<who>Target opponent|An opponent) chooses (?P<k>one|two) of those cards\. Put the chosen cards? into your "
    r"graveyard and the rest (?P<rest>into your hand|onto the battlefield tapped)(?:\. Then shuffle|, then shuffle)\.")
_N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def gifts_ability(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """The whole text of a Gifts-style spell as one effect (scripts.parse_effects), or None."""
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
    from app.rules import characteristics as chars

    pid = ctx["controller"]
    library = plan.state.zones.get(zone_key(pid, "library"), [])
    from app.rules import (
        prohibitions,  # -- prohibitions (wave 22B) -- 614.17: "Players can't search libraries." (nothing can be found)
    )

    if (why := prohibitions.cant_search(plan, pid, ctx["controller"])) is not None:
        plan.note(f"{why}: {plan.name(pid)} can't search their library", actor=pid)
        library = []
    sel = selectors.from_key(e["sel"])
    matching = [c for c in library
                if selectors.matches(plan, sel, plan.state.cards[c], chars.of(plan.state.cards[c], plan.info), pid)]
    decide(plan, player=pid, kind="choose_cards", prompt=f"Search your library (up to {e['max']} {e['label']} with different names)",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in matching],
           min_choices=0, max_choices=min(e["max"], len(matching)), resume={"step": "gifts_found", "ctx": ctx, "e": e},
           decider=player_control.search_controller(plan, pid))  # (wave 18H) 723.2: Opposition Agent
    return False


def resume_gifts_found(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    names = [(plan.state.cards[c].name or "").lower() for c in chosen]
    if len(set(names)) != len(names):
        from app.game.errors import ActionError

        raise ActionError("The cards you find must have different names")
    if agents := player_control.search_exile(plan, d.player):  # (wave 18H) Opposition Agent: each card found is exiled (a new
        for cid in chosen:  # object, 400.7: the piles are never made) and its controller may play it
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": d.player, "zone": "exile"}}, actor=d.player)
        player_control.permit_exiled(plan, agents, list(chosen))
        _gifts_finish(plan, ctx, e, [], [])
        return
    for cid in chosen:
        plan.do({"type": "reveal", "card_ids": [cid]}, actor=d.player)  # 701.20a: to everyone
    found = list(chosen)
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
    decide(plan, player=opponent, kind="choose_cards", prompt=f"{ctx.get('name') or 'Gifts'}: choose {e['k']} for the graveyard",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in found],
           min_choices=e["k"], max_choices=e["k"], resume={"step": "gifts_split", "ctx": ctx, "e": e, "found": found})


def resume_gifts_split(plan: Plan, d: Any, chosen: list[str]) -> None:
    _gifts_finish(plan, d.resume["ctx"], d.resume["e"], d.resume["found"], list(chosen))


def _gifts_finish(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], found: list[str], chosen: list[str]) -> None:
    from app.rules import attachments, effects

    pid = ctx["controller"]
    found = [c for c in found if plan.state.cards[c].zone == zone_key(pid, "library")]
    to_gy = [c for c in found if c in chosen]
    rest = [c for c in found if c not in chosen]
    if to_gy:
        plan.do({"type": "move", "card_ids": to_gy, "to": {"player": pid, "zone": "graveyard"}}, actor=pid)
    if rest and e["rest"] == "battlefield_tapped":
        entries = [{"card": c, "player": pid, "actor": pid, "tapped": True} for c in rest]
        if not attachments.enter(plan, entries, ctx, shuffle=pid):
            return  # (an Aura chooses what it enchants; the library is shuffled on resume)
    elif rest:
        plan.do({"type": "move", "card_ids": rest, "to": {"player": pid, "zone": "hand"}}, actor=pid)
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
RESUME = {"enter_attacking": resume_enter_attacking, "gifts_found": resume_gifts_found,
          "gifts_opponent": resume_gifts_opponent, "gifts_split": resume_gifts_split, "may_mill": resume_may_mill}
