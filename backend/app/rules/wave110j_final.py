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


PRIMITIVES = {"mentored110j": mentored, "sacrificed110j": sacrificed}
