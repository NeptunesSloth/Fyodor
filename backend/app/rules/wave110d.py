"""-- wave 110D -- the one place the wave's modules (app/rules/wave110d_*.py) register themselves: effect templates, primitives, whole-ability and
whole-body wordings. Each module has its own docstring with the rules (CR 2026-09-25) and the cards it serves."""
from __future__ import annotations

from typing import Any

from app.rules import (
    mana_noted_profiles,
    wave110d_aura,
    wave110d_chef,
    wave110d_crown,
    wave110d_enter,
    wave110d_fire,
    wave110d_granter,
    wave110d_hit,
    wave110d_lines,
    wave110d_mech,
    wave110d_meld,
    wave110d_misc,
    wave110d_noted,
    wave110d_rooms,
    wave110d_rules,
)

TEMPLATES: list[Any] = [*wave110d_rules.TEMPLATES]
PRIMITIVES: dict[str, Any] = {**wave110d_enter.PRIMITIVES, **wave110d_aura.PRIMITIVES, **wave110d_granter.PRIMITIVES, **wave110d_hit.PRIMITIVES, **wave110d_crown.PRIMITIVES, **wave110d_lines.PRIMITIVES, **wave110d_fire.PRIMITIVES, **wave110d_chef.PRIMITIVES, **wave110d_meld.PRIMITIVES, **wave110d_mech.PRIMITIVES, **wave110d_rooms.PRIMITIVES, **wave110d_misc.PRIMITIVES, **wave110d_noted.PRIMITIVES, **mana_noted_profiles.PRIMITIVES}
RESUME: dict[str, Any] = {**wave110d_crown.RESUME, **wave110d_rooms.RESUME, **wave110d_misc.RESUME, **mana_noted_profiles.RESUME}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    """A whole ability (scripts.define): the first module that reads it."""
    from app.rules import (
        wave110d_aura,
        wave110d_crown,
        wave110d_enter,
        wave110d_hit,
        wave110d_lines,
        wave110d_noted,
        wave110d_rooms,
    )

    return wave110d_lines.definition(ability, ch) or wave110d_rooms.definition(ability, ch) or wave110d_misc.definition(ability, ch) or wave110d_enter.definition(ability, ch) or wave110d_hit.definition(ability, ch) or wave110d_crown.definition(ability, ch) or wave110d_aura.definition(ability, ch) or wave110d_noted.definition(ability, ch)


def parse(body: str) -> Any:
    """A whole spell / effect body (scripts.parse_effects): the first module that reads it."""
    return None
