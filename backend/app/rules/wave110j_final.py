"""Wave 110J final pass: effect primitives of the last unsettled-then-settled cards (each block names its rule)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import emit

if TYPE_CHECKING:
    from app.rules.plan import Plan


def mentored(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """702.134c: the mentor ability resolved (its target was still legal, 608.2b), so the source creature "mentors" that creature."""
    from app.rules import effects

    for cid in effects._cards(plan, ctx, "target"):
        card = plan.state.cards.get(cid)
        if card is not None:
            emit(plan.state, "mentored", object_id=plan.oid(card), card=cid, player=ctx["controller"], source=ctx.get("source_object"),
                 by_card=ctx.get("source_card"))
    return True


SILHOUETTE = ("Choose target creature. If a spell or ability that targets that creature would cause a source to deal damage to that creature "
              "this turn, prevent that damage.")


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Silhouette: 615.1 / 611.2a, a prevention effect of the resolved spell lasting this turn. Its recipient is the target as it is now (400.7); it
    applies only to damage whose cause (the spell or ability resolving, ``cause_oids``) has that creature among its targets (115.1)."""
    if body.strip() != SILHOUETTE:
        return None
    return ([{"do": "source_shield", "src": "any", "to": "target", "props": {"cause_targets_recipient110j": True}}], "creature", False)


def cause_targets_recipient(plan: Plan, ev: dict[str, Any]) -> bool:
    card = plan.state.cards.get(ev.get("target") or "")
    return card is not None and plan.oid(card) in (ev.get("cause_oids") or ())


def cause_oids(ctx: dict[str, Any]) -> list[str]:
    """The objects the resolving spell or ability targets (every group)."""
    refs = [r for group in ctx.get("groups") or [ctx.get("targets") or []] for r in group]
    return [r["object_id"] for r in refs if isinstance(r, dict) and r.get("object_id")]


# -- Defensive Formation -- 510.1a: "Rather than the attacking player, you assign the combat damage of each creature attacking you." Every damage assignment choice
# (division among blockers, trample, "as though it weren't blocked", Butcher Orgg's ability) is the defender's (ruling 2014-04-26, Scryfall: "Damage assignment
# choices from Trample and other things which allow alternative damage assignments for attacking creatures are all made by you").
FORMATION = ("Rather than the attacking player, you assign the combat damage of each creature attacking you. You can divide that creature's combat damage as you "
             "choose among any of the creatures blocking it.")


def definition(text: str) -> dict[str, Any] | None:
    return {"kind": "static", "static": "assigns110j", "effects": []} if text == FORMATION else None


def assigner(plan: Plan, attacker: Any) -> str | None:
    """The player who assigns ``attacker``'s combat damage instead of its controller: the player it attacks, if they control a Defensive Formation."""
    from app.rules import scripts

    target = attacker.attacking
    if target is None or target.kind != "player" or target.id == attacker.controller:
        return None
    for cid in plan.state.zones.get(f"{target.id}:battlefield", []):
        card = plan.state.cards[cid]
        if not card.face_down and plan.in_game(card) and not plan.manual(card) and any(
                d.get("static") == "assigns110j" for d in scripts.definitions(plan.ch(card)).values() if d.get("kind") == "static"):
            return target.id
    return None


# -- Gluttonous Hellkite -- 601.2 / 603.3: the cast trigger resolves before the spell (ruling 2014-05-29): each player sacrifices X creatures (X is the spell's, 107.3i),
# then "enters with two +1/+1 counters on it for each creature sacrificed this way" (614.12, 122.6): the number actually sacrificed, not X (ruling).
HELLKITE = ("When you cast this spell, each player sacrifices X creatures. This creature enters with two +1/+1 counters on it for each creature sacrificed "
            "this way.")


def hellkite(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    if ability.kind != "triggered" or ability.text != HELLKITE:
        return None
    base = scripts.define(replace(ability, text="When you cast this spell, each player sacrifices X creatures."), ch)
    if base is None or base.get("trigger") != "cast_self" or [e.get("do") for e in base["effects"]] != ["sacrifice_choice"]:
        return None
    return {**base, "effects": [{**base["effects"][0], "as": "sac110j"}, {"do": "sacrificed110j"}], "enters110j": True}


def sacrificed(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    plan.rules.sacrificed110j[ctx.get("source_object") or ""] = len(context.objects(plan, ctx, "sac110j"))
    return True


def entry_counters(plan: Plan, card: Any, ch: Any) -> int:
    """+1/+1 counters the Hellkite enters with (two per creature its spell's cast trigger had sacrificed)."""
    from app.rules import scripts

    if not any(d.get("enters110j") for d in scripts.definitions(ch).values()):
        return 0
    return 2 * plan.rules.sacrificed110j.get(plan.oid(card), 0)


# -- Ogre Battlecaster -- "you may cast target instant or sorcery card from your graveyard by paying {R}{R} in addition to its other costs. If that spell would be
# put into a graveyard, exile it instead. When you cast that spell, this creature gets +X/+0 until end of turn, where X is that spell's mana value."
# 608.2g: the cast happens as the ability resolves (ruling: "You must cast the spell as the triggered ability resolves"); 118.8: {R}{R} is an additional cost;
# 603.7a: "When you cast that spell" is a delayed trigger created first, for that one card (as Havengul Lich's), and dropped when nothing was cast.
OGRE = ("Whenever this creature attacks, you may cast target instant or sorcery card from your graveyard by paying {R}{R} in addition to its other costs. If that "
        "spell would be put into a graveyard, exile it instead. When you cast that spell, this creature gets +X/+0 until end of turn, where X is that spell's mana value.")


def ogre(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    if ability.kind != "triggered" or ability.text != OGRE:
        return None
    base = scripts.define(replace(ability, text="Whenever this creature attacks, you may cast target instant or sorcery card from your graveyard. If that spell would be "
                                                "put into your graveyard, exile it instead."), ch)
    pump = scripts.parse_effects("This creature gets +X/+0 until end of turn, where X is that spell's mana value.")
    if base is None or pump is None or [e.get("do") for e in base["effects"]] != ["free_cast"] or [e.get("do") for e in pump[0]] != ["pump"]:
        return None
    return {**base, "effects": [{"do": "ogre_watch110j", "pump": {**pump[0][0], "p": {"mana_value": "event"}}},  # ("that spell": the cast event's, as a deferred value)
                                 {**base["effects"][0], "extra_mana110j": "{R}{R}"}, {"do": "ogre_drop110j"}]}


def ogre_watch(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import delayed
    from app.rules.effects import _cards

    cards = _cards(plan, ctx, "target")
    if cards:
        cond = {"event": "cast", "subject": "player", "player": "you", "spell": 'sel:{"zones":["stack"]}', "card110b": cards[0]}
        wrapped = delayed.wrap_when([e["pump"]], {"kind": "watch", "cond": cond, "text": "you cast that spell", "ogre110j": True}, this_turn=True)
        wrapped[0]["once"] = True
        ctx["effects"][ctx["next"]:ctx["next"]] = wrapped
    return True


def ogre_drop(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The cast was declined (or could not happen): the watch for it goes, so no later cast of that card pumps the Ogre."""
    if not ctx.get("free_cast_done"):
        plan.rules.delayed = [t for t in plan.rules.delayed if not (t.when.get("ogre110j") and t.source_object == ctx.get("source_object"))]
    return True


# -- Garth One-Eye -- "{T}: Choose a card name that hasn't been chosen from among Disenchant, Braingeyser, Terror, Shivan Dragon, Regrowth, and Black Lotus. Create a copy of
# the card with the chosen name. You may cast the copy." Rulings 2017-03-14 (Scryfall): the name is chosen as the ability resolves; each Garth keeps its own names (the same
# object: leaving and returning forgets, another player gaining control remembers, 400.7); casting the copy is optional, but its name stays used; you pay its costs.
# 707.12: the copy is a card copy made outside the game's zones; made in exile and cast through the same continuation as every other copied card (card_copy_sources).
GARTH = ("{T}: Choose a card name that hasn't been chosen from among Disenchant, Braingeyser, Terror, Shivan Dragon, Regrowth, and Black Lotus. Create a copy of the card with "
         "the chosen name. You may cast the copy.")
GARTH_NAMES = ("Disenchant", "Braingeyser", "Terror", "Shivan Dragon", "Regrowth", "Black Lotus")
GARTH_KEY = "Names chosen"


def garth_definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import card_copy_sources, scripts

    if ability.kind != "activated" or scripts.self_text(ability.text, ch.name) != GARTH.replace("Garth One-Eye", "~"):
        return None
    base = scripts.define(replace(ability, text="{T}: Draw a card."), ch)
    if base is None:
        return None
    return {**base, "effects": [{"do": "garth110j"}, card_copy_sources.copy_cast(paid=True)[1]]}


def _garth_chosen(card: Any) -> list[str]:
    return [n for n in card.choices.get(GARTH_KEY, "").split(", ") if n]


def garth(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is None or plan.oid(card) != ctx.get("source_object") or not card.zone.endswith(":battlefield"):
        # (the names belong to that object: gone, they can't be told: the copy is made by hand)
        ctx["effects"][ctx["next"]:] = [x for x in ctx["effects"][ctx["next"]:] if x.get("do") != "free_cast"]
        plan.note(f"{ctx.get('name') or 'Garth One-Eye'} left the battlefield: which names it had chosen isn't known; create the copy by hand")
        return True
    left = [n for n in GARTH_NAMES if n not in _garth_chosen(card)]
    if not left:
        ctx["effects"][ctx["next"]:] = [x for x in ctx["effects"][ctx["next"]:] if x.get("do") != "free_cast"]
        plan.note(f"{card.name} has chosen every name: nothing happens")
        return True
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{card.name}: choose a card name that hasn't been chosen",
           options=[DecisionOption(id=n, label=n) for n in left], resume={"step": "garth110j", "ctx": ctx})
    return False


def resume_garth(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import card_copy_sources, effects

    ctx = d.resume["ctx"]
    card = plan.state.cards[ctx["source_card"]]
    name = chosen[0]
    names = [*_garth_chosen(card), name]
    plan.do({"type": "set_choice", "card_id": card.id, "key": GARTH_KEY, "value": ", ".join(names)}, actor=ctx["controller"])
    found = getattr(plan.info, "resolve", lambda n: None)(name)
    made: list[str] = []
    if found is not None:
        created = plan.do({"type": "copy_card", "card_id": card.id, "player": ctx["controller"], "count": 1, "zone": "exile", "printing": found["id"], "name": name},
                          actor=ctx["controller"])
        made = list(getattr(getattr(created, "r", None), "ids", []))
    effects._remember(plan, ctx, {"as": card_copy_sources.COPIES}, made)
    plan.note(f"{card.name} chose {name}: a copy is created")
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"mentored110j": mentored, "sacrificed110j": sacrificed, "ogre_watch110j": ogre_watch, "ogre_drop110j": ogre_drop, "garth110j": garth}
RESUME = {"garth110j": resume_garth}
