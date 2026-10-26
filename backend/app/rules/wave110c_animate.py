"""-- Animate Artifact (wave 110C) -- "As long as enchanted artifact isn't a creature, it's an artifact creature with power and toughness each equal to its mana
value."

613.1d / 613.4b: the layer-4 type addition (205.1b) and the layer-7b base power and toughness of March of the Machines, for the one artifact the Aura is attached
to. The "isn't a creature" test is the group's subject ("noncreature artifact"), which app/rules/group_layers.py solves against the other type-changing effects
(613.8a: this effect depends on whatever makes the artifact a creature, so those apply first and then it adds nothing: a crewed Vehicle keeps its own power and
toughness), and 613.6: what it affects is determined when it begins to apply in the first layer."""

from __future__ import annotations

from typing import Any

TEXT = "As long as enchanted artifact isn't a creature, it's an artifact creature with power and toughness each equal to its mana value."
MARCH = "Each noncreature artifact is an artifact creature with power and toughness each equal to its mana value."


def definition(text: str) -> dict[str, Any] | None:
    from app.rules import selectors, type_statics

    if text.strip() != TEXT:
        return None
    march = type_statics.parse(MARCH)
    if march is None:
        return None
    return {**march, "who": selectors.Selector(types=("Artifact",), not_types=("Creature",), extras=("host_of_source",)).key()}
