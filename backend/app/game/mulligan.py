"""Mulligan policy presets. See docs/MULLIGAN_RULES.md.

Official rules are implemented as data (London: CR 103.5; the multiplayer free mulligan:
CR 103.5c, as used by Commander). A pod's house rule is a named slot whose fields the host fills
in; nothing about it is assumed.
"""

from __future__ import annotations

from app.game.state import MulliganPolicy

LONDON = MulliganPolicy(id="london", display_name="London")
COMMANDER_LONDON = MulliganPolicy(id="commander_london", display_name="Commander London", free_mulligans=1)
# Our pod's "Boston mulligan" (NOT an official rule), as the pod plays it: every hand is 10 cards, you keep 7 and put
# 3 on the bottom; a mulligan deals 10 again. As in Commander (103.5c) the first mulligan is free and each later one puts
# one more card on the bottom. The host can still change any field (Table settings → Mulligan).
BOSTON_CUSTOM = MulliganPolicy(id="boston_custom", display_name="Boston (Custom Pod)", starting_hand_size=10, draw_count=10,
                               keep_bottom=3, free_mulligans=1, cards_to_bottom=1)
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
    return policy.keep_bottom + max(0, mulligans - policy.free_mulligans) * policy.cards_to_bottom
