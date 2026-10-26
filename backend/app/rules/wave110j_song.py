"""-- last cards (wave 110J) -- Titania's Song: "If this enchantment leaves the battlefield, this effect continues until end of turn."

While the enchantment is on the battlefield its effect is a static ability's (611.3a): it applies to every noncreature artifact, including
ones that arrive later (app/rules/type_statics.py ``song110j``). When it leaves, the effect is no longer a static ability's: it continues
until end of turn for exactly the artifacts it was affecting at that moment (lead decision, on the principle of 611.2c), so an artifact
that enters afterwards isn't affected. Built as a resolved "becomes" effect (layer 4 artifact creature, 205.1b; layer 6 loses all
abilities; layer 7b power and toughness each equal to its mana value) locked to that set. Summoning sickness is the ordinary rule (302.6;
ruling 2008-08-01: an artifact you controlled continuously since your turn began can attack and {T} though it just became a creature).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Leaving = list[tuple[str, str, str, str, list[str]]]  # (card, object, controller, name, affected objects)


def before(plan: Plan, payload: dict[str, Any]) -> Leaving:
    """The Songs this step may move off the battlefield, each with the objects its static applies to right now (613.6: ``members``)."""
    ids = {c for c in payload.get("card_ids") or () if isinstance(c, str)}
    songs = [c for c in ids if (card := plan.state.cards.get(c)) is not None and card.zone.endswith(":battlefield")]
    if not songs:
        return []
    from app.rules import layers

    out: Leaving = []
    for st in layers.statics(plan.state, plan.info):
        if st.source in songs and st.definition.get("song110j") and st.members:
            card = plan.state.cards[st.source]
            members = [plan.oid(m) for cid in sorted(st.members) if (m := plan.state.cards.get(cid)) is not None and m.zone.endswith(":battlefield")]
            out.append((st.source, plan.oid(card), st.controller, plan.ch(card).name, members))
    return out


def after(plan: Plan, leaving: Leaving) -> None:
    """A Song that left: its effect continues until end of turn for the set it was affecting (artifacts that left with it are new objects, 400.7)."""
    from app.rules import effects

    for cid, oid, controller, name, members in leaving:
        card = plan.state.cards.get(cid)
        if (card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == oid) or not members:
            continue
        effects.become(plan, {"controller": controller, "name": name, "source_object": oid, "source_card": cid},
                       {"who": "union:" + "+".join(f"obj:{m}" for m in members), "types": ["Artifact", "Creature"], "retain": True,
                        "p": {"mana_value": "it"}, "t": {"mana_value": "it"}, "lose_abilities": True, "duration": "end_of_turn"})
