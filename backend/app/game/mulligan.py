"""Mulligan policy presets. See docs/MULLIGAN_RULES.md.

Official rules are implemented as data (London: CR 103.5; the multiplayer free mulligan:
CR 103.5c, as used by Commander). A pod's house rule is a named slot whose fields the host fills
in; nothing about it is assumed.
"""

from __future__ import annotations

from app.game.state import MulliganPolicy

LONDON = MulliganPolicy(id="london", display_name="London")
COMMANDER_LONDON = MulliganPolicy(id="commander_london", display_name="Commander London", free_mulligans=1)
# Placeholder for our pod's "Boston mulligan". It is NOT an official rule and its mechanics are not
# defined here: until the host fills in the fields, a game can't start with it.
BOSTON_CUSTOM = MulliganPolicy(id="boston_custom", display_name="Boston (Custom Pod)", needs_definition=True)
CUSTOM = MulliganPolicy(id="custom", display_name="Custom")

PRESETS: dict[str, MulliganPolicy] = {p.id: p for p in (COMMANDER_LONDON, LONDON, BOSTON_CUSTOM, CUSTOM)}
CONFIGURABLE = {"boston_custom", "custom"}
NONE = "none"  # no guided mulligans: draw and mulligan by hand


def resolve_policy(rule: str, custom: MulliganPolicy | None = None) -> MulliganPolicy | None:
    """The policy for a table setting. ``custom`` supplies the fields for configurable slots."""
    if rule == NONE:
        return None
    preset = PRESETS.get(rule)
    if preset is None:
        raise ValueError(f"Unknown mulligan rule {rule!r}")
    if rule in CONFIGURABLE and custom is not None:
        # Keep the slot's identity; take every rule field from the host's definition.
        return custom.model_copy(update={"id": preset.id, "display_name": custom.display_name or preset.display_name})
    return preset.model_copy()


def to_bottom(policy: MulliganPolicy, mulligans: int) -> int:
    """How many cards a player puts on the bottom after taking ``mulligans`` mulligans."""
    return max(0, mulligans - policy.free_mulligans) * policy.cards_to_bottom
