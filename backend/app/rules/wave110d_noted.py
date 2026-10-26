"""-- noted mana type (wave 110D) -- Jeweled Amulet: "{1}, {T}: Put a charge counter on this artifact. Note the type of mana spent to pay this activation cost.
Activate only if there are no charge counters on this artifact." and "{T}, Remove a charge counter from this artifact: Add one mana of this artifact's last
noted type."

* 607.2e: the note is linked information of this object (its object id, 400.7: a new Amulet knows nothing); it is recorded as the activation resolves from the
  payment receipt (mana_noted_profiles.note_payment, the same record "spent" conditions read) and read by the second ability.
* 106.1: the types of mana are white, blue, black, red, green and colorless; the {1} paid with one mana notes that one type. Nothing noted (never activated, an
  older object, or a payment of several types) is handed to manual play rather than guessed.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

IN = "{1}, {T}: Put a charge counter on ~. Note the type of mana spent to pay this activation cost. Activate only if there are no charge counters on ~."
OUT = "{T}, Remove a charge counter from ~: Add one mana of ~'s last noted type."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import mana_noted_profiles, scripts

    if (ice := mana_noted_profiles.definition(ability, ch)) is not None:  # Ice Cauldron: the staged exile + note profile (607.2e)
        return ice
    if ability.kind != "activated" or scripts.self_text(ability.text, ch.name) != IN:
        return None
    base = scripts.define(replace(ability, text="{1}, {T}: Put a charge counter on this artifact. Activate only if there are no charge counters on this artifact."), ch)
    return {**base, "effects": [*base["effects"], {"do": "note_actual_mana"}]} if base else None


def parse_mana(text: str, identity: tuple[str, ...], name: str) -> Any:
    from app.rules import mana as M
    from app.rules import mana_noted_profiles, scripts

    if (ice := mana_noted_profiles.parse_mana(text, identity, name)) is not None:
        return ice
    if scripts.self_text(text, name) == OUT:
        return M.ManaAbility(tap=True, sacrifice_self=False, options=((),), extra_cost="Remove a charge counter from ~", chooses=True, native_body=True,
                             immediate_effects=({"do": "noted_type110d"},))
    return None


def output(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import exiled_with, immediate_mana_resolutions
    from app.rules import mana as M
    from app.rules.plan import decide

    note = plan.rules.noted_mana.get(exiled_with.link_key(ctx))
    types = [c for c in M.ALL_MANA if note is not None and (note.mana or {}).get(c)]
    if note is None or note.mana is None or len(types) != 1:
        decide(plan, player=ctx["controller"], kind="manual_resolution",
               prompt="No single noted type of mana is recorded for this object. Add the mana by hand, then press Done.",
               options=[DecisionOption(id="done", label="Done")], resume={"step": "unknown_noted_mana", "ctx": ctx})
        return False
    immediate_mana_resolutions.produce_chosen(plan, ctx, ctx["controller"], types)
    return False


PRIMITIVES = {"noted_type110d": output}
