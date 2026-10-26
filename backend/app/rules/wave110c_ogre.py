"""-- Ogre Battlecaster (wave 110C) -- "Whenever this creature attacks, you may cast target instant or sorcery card from your graveyard by paying {R}{R} in
addition to its other costs. If that spell would be put into a graveyard, exile it instead. When you cast that spell, this creature gets +X/+0 until end of
turn, where X is that spell's mana value."

608.2g / 118.9d: the cast as the ability resolves is the ordinary free-cast effect, paying its mana cost (the effect's ``paid``) and the extra {R}{R} as an
additional cost (601.2b, 601.2f: casting.cast_free adds ``extra_mana110c``); the exile-instead rider is the effect's ``exile_gy`` (614.1). 603.7c: "When you
cast that spell" is a reflexive trigger of that very spell's cast: it goes on the stack above the spell (603.3) with the spell's mana value as it was cast
(the spell's X included, 202.3e), and does nothing if the creature has left the battlefield."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ("Whenever this creature attacks, you may cast target instant or sorcery card from your graveyard by paying {R}{R} in addition to its other costs. "
        "If that spell would be put into a graveyard, exile it instead. When you cast that spell, this creature gets +X/+0 until end of turn, where X is "
        "that spell's mana value.")
PLAIN = ("Whenever this creature attacks, you may cast target instant or sorcery card from your graveyard. "
         "If that spell would be put into a graveyard, exile it instead.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != "triggered" or scripts.self_text(ability.text, ch.name).replace("~", "this creature") != TEXT:
        return None
    base = scripts.define(replace(ability, text=PLAIN), ch)
    if base is None or [e.get("do") for e in base["effects"]] != ["free_cast"]:
        return None
    return {**base, "effects": [{**base["effects"][0], "extra_mana110c": "{R}{R}", "pump110c": True}]}


def cast_trigger(plan: Any, pending: dict[str, Any], card: Any, spell_ch: Any) -> None:
    """The reflexive "when you cast that spell" of the free cast that was just made (``pending``: the free-cast ability's context)."""
    from app.rules import scripts, trigger_multipliers, triggers

    if not pending.get("e", {}).get("pump110c"):
        return
    ctx = pending["ctx"]
    src = plan.state.cards.get(ctx.get("source_card") or "")
    if src is None:
        return
    effects = scripts.parse_effects(f"This creature gets +{int(spell_ch.mana_value)}/+0 until end of turn.")[0]
    triggers._add(plan, controller=ctx["controller"], source_card=src.id, source_object=ctx["source_object"], name=src.name or "Ogre Battlecaster",
                  index=trigger_multipliers.REFLEXIVE, definition={"kind": "triggered", "trigger": "reflexive", "effects": effects, "optional": False, "target": None})
