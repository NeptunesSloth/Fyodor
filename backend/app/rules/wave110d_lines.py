"""-- lines (wave 110D) -- whole abilities read as an equivalent native wording (same meaning, citations at each entry; CR 2026-09-25)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

# the Oracle line (the card's name as ~) -> the wording the grammar already reads, with the same meaning
_AS: dict[str, str] = {
    # Thelon of Havenwood: "each Fungus on the battlefield" is each permanent with the Fungus subtype (a selector reads permanents on the battlefield; 109.2)
    "{B}{G}, Exile a Fungus card from a graveyard: Put a spore counter on each Fungus on the battlefield.":
        "{B}{G}, Exile a Fungus card from a graveyard: Put a spore counter on each Fungus.",
    # Jeska, Thrice Reborn: a loyalty counter "for each time" = a number of counters equal to the number of times (122.6, 903.8)
    "~ enters with a loyalty counter on it for each time you've cast a commander from the command zone this game.":
        "~ enters with a number of loyalty counters on it equal to the number of times you've cast a commander from the command zone this game.",
    # Heliod's Punishment: "It" is the enchanted creature, so one sentence with the same three parts (613.1f, 508.1c, 509.1b)
    'Enchanted creature can\'t attack or block. It loses all abilities and has "{T}: Remove a task counter from ‹granter›. Then if it has no task counters on it, destroy ‹granter›."':
        'Enchanted creature can\'t attack or block, loses all abilities, and has "{T}: Remove a task counter from ‹granter›. Then if it has no task counters on it, destroy ‹granter›."',
    # Infantry Shield: the granted keyword is the triggered ability it stands for (702.181a, X read as it resolves, 107.3c)
    "Equipped creature has menace and mobilize X, where X is its power.":
        'Equipped creature has menace and "Whenever this creature attacks, create X tapped and attacking 1/1 red Warrior creature tokens, '
        'where X is its power. Sacrifice them at the beginning of the next end step."',
    # Unable to Scream: a creature that is not face down can't be turned face up anyway (708.2), so the condition changes nothing
    "As long as enchanted creature is face down, it can't be turned face up.": "Enchanted creature can't be turned face up.",
    # Mjölnir: doubling all of a source's damage is "it deals double that damage instead" to any recipient (120.1, 614.1)
    "Double all damage equipped creature would deal.":
        "If equipped creature would deal damage to a permanent or player, it deals double that damage instead.",
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    native = _AS.get(scripts.self_text(ability.text, ch.name))
    return None if native is None else scripts.define(replace(ability, text=native), ch)
