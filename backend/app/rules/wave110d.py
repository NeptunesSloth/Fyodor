"""-- wave 110D -- the one place the wave's modules (app/rules/wave110d_*.py) register themselves: effect templates, primitives, whole-ability and
whole-body wordings. Each module has its own docstring with the rules (CR 2026-09-25) and the cards it serves."""
from __future__ import annotations

from typing import Any

from app.rules import wave110d_aura, wave110d_enter, wave110d_granter, wave110d_hit, wave110d_rules

TEMPLATES: list[Any] = [*wave110d_rules.TEMPLATES]
PRIMITIVES: dict[str, Any] = {**wave110d_enter.PRIMITIVES, **wave110d_aura.PRIMITIVES, **wave110d_granter.PRIMITIVES, **wave110d_hit.PRIMITIVES}
RESUME: dict[str, Any] = {}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    """A whole ability (scripts.define): the first module that reads it."""
    from app.rules import wave110d_aura, wave110d_enter, wave110d_hit, wave110d_lines

    return wave110d_lines.definition(ability, ch) or wave110d_enter.definition(ability, ch) or wave110d_hit.definition(ability, ch) or wave110d_aura.definition(ability, ch)


def parse(body: str) -> Any:
    """A whole spell / effect body (scripts.parse_effects): the first module that reads it."""
    return None
