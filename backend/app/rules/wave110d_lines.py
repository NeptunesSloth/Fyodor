"""-- lines (wave 110D) -- whole abilities read as an equivalent native wording (same meaning, citations at each entry; CR 2026-09-25)."""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

# the Oracle line (the card's name as ~) -> the wording the grammar already reads, with the same meaning
_AS: dict[str, str] = {
    # Common Cause: "they" are the nonartifact creatures the line names (statics._condition "share_color110d", 105.4: one color all of them have)
    "Nonartifact creatures get +2/+2 as long as they all share a color.":
        "Nonartifact creatures get +2/+2 as long as all nonartifact creatures share a color.",
    # Summoner's Grimoire (granted trigger): 508.4, 614.12 only an enchantment card enters tapped and attacking (put_from_hand.resume, tap_atk110d)
    "Whenever ~ attacks, you may put a creature card from your hand onto the battlefield. If that card is an enchantment card, it enters tapped and attacking.":
        "Whenever ~ attacks, you may put a creature card from your hand onto the battlefield.",
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
    # The Millennium Calendar: untapping in the untap step happens to every permanent at once (502.3), one batch (603.2c); the count is read below
    "Whenever you untap one or more permanents during your untap step, put that many time counters on ~.":
        "Whenever one or more permanents you control become untapped, put that many time counters on this artifact.",
    # "1,000" is the number 1000 (107.1)
    "When there are 1,000 or more time counters on ~, sacrifice it and each opponent loses 1,000 life.":
        "When there are 1000 or more time counters on this artifact, sacrifice it and each opponent loses 1000 life.",
    # Tourach's / Thelon's Chant: the player who puts a land onto the battlefield is the one it enters under (400.7, 110.2); an exact text only
    "Whenever a player puts a Forest onto the battlefield, ~ deals 3 damage to that player unless they put a -1/-1 counter on a creature they control.":
        "Whenever a Forest enters, ~ deals 3 damage to its controller unless they put a -1/-1 counter on a creature they control.",
    "Whenever a player puts a Swamp onto the battlefield, ~ deals 3 damage to that player unless the player puts a -1/-1 counter on a creature they control.":
        "Whenever a Swamp enters, ~ deals 3 damage to its controller unless they put a -1/-1 counter on a creature they control.",
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    native = _AS.get(text)
    d = None if native is None else scripts.define(replace(ability, text=native), ch)
    if d is not None and text.startswith("Whenever you untap one or more"):  # (own_untap: only the untap step of its controller, triggers.py)
        d = json.loads(json.dumps(d, default=str).replace('{"event_amount": 1}', '{"event_count": 1}'))
        d["cond"]["own_untap"] = True
    if d is not None and text.endswith("it enters tapped and attacking."):
        d["effects"][0]["tap_atk110d"] = "Enchantment"
    return d
