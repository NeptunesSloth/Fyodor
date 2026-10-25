"""-- lines (wave 110D) -- whole abilities read as an equivalent native wording (same meaning, citations at each entry; CR 2026-09-25)."""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

# the Oracle line (the card's name as ~) -> the wording the grammar already reads, with the same meaning
_AS: dict[str, str] = {
    # Oft-Nabbed Goat: 611.2 the activator gains control (the same "you" as the draw); the dies trigger counts the -1/-1 counters it last had (608.2h)
    "{1}: Draw a card. Gain control of ~ and put a -1/-1 counter on it. Only your opponents may activate this ability and only as a sorcery.":
        "{1}: Draw a card. Put a -1/-1 counter on ~. Gain control of ~. Only your opponents may activate this ability and only as a sorcery.",
    "When ~ dies, if it had one or more -1/-1 counters on it, its owner draws that many cards and each other player loses that much life.":
        "When ~ dies, if it had one or more -1/-1 counters on it, its owner draws X cards and each opponent loses X life, where X is the number of -1/-1 counters on it.",
    '{2}: If ~ isn\'t a creature, it becomes a 0/0 Construct Hero artifact creature with flying and "~ gets +1/+1 for each artifact you control" until end of turn.':
        "{2}: If ~ isn't a creature, it becomes a 0/0 Construct Hero artifact creature with flying until end of turn.",
    # Sorin, Ravenous Neonate: "a white permanent other than that creature or Sorin" (here ~) = other than Sorin (the native "another") and not the stolen creature (patched below)
    "−6: Gain control of target creature. It becomes a Vampire in addition to its other types. Put a lifelink counter on it if you control a white permanent other than that creature or ~.":
        "−6: Gain control of target creature. It becomes a Vampire in addition to its other types. Put a lifelink counter on it if you control another white permanent.",
    # Sheltering Prayers: 613.7 each basic land is checked against its own controller's land count (a controller-relative selector extra)
    "Basic lands each player controls have shroud as long as that player controls three or fewer lands.":
        "Basic lands controlled by a player who controls three or fewer lands have shroud.",
    # One with the Kami: the enchanted creature is itself modified (700.9: this Aura, which its controller controls, is attached), so "enchanted creature or
    # another modified creature you control" is every modified creature you control
    "Whenever enchanted creature or another modified creature you control dies, create X 1/1 colorless Spirit creature tokens, where X is that creature's power.":
        "Whenever a modified creature you control dies, create X 1/1 colorless Spirit creature tokens, where X is that creature's power.",
    # Hand of Vecna: a single object named Vecna per player under the legend rule (704.5j), so "a creature named Vecna" = "each"; X is the same for both
    "At the beginning of combat on your turn, equipped creature or a creature you control named Vecna gets +X/+X until end of turn, where X is the number of cards in your hand.":
        "At the beginning of combat on your turn, equipped creature gets +X/+X until end of turn, where X is the number of cards in your hand. Each creature you control named Vecna gets +X/+X until end of turn, where X is the number of cards in your hand.",
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
    # Mind Whip: the same unless-payment (118.12); the tap is the second consequence of not paying (patched in below)
    "At the beginning of the upkeep of enchanted creature's controller, that player may pay {3}. If they don't, ~ deals 2 damage to that player and you tap that creature.":
        "At the beginning of the upkeep of enchanted creature's controller, ~ deals 2 damage to that player unless they pay {3}.",
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == WARD_XP:
        return {"kind": "static", "static": "ward_xp110d", "effects": []}
    native = _AS.get(text)
    d = None if native is None else scripts.define(replace(ability, text=native), ch)
    if d is not None and text.startswith("−6: Gain control of target creature. It becomes a Vampire"):
        # the stolen creature is now yours: it counts in "another white permanent" when white, so it needs one more
        old = d["effects"][-2]["cond"]  # (the "only_if" before the counter)
        d["effects"][-2]["cond"] = {"any": [{"all": [{"not": {"object": "target", "is": 'sel:{"colors":["W"]}'}}, old]}, {**old, "n": 2}]}
    if d is not None and text.startswith("Whenever you untap one or more"):  # (own_untap: only the untap step of its controller, triggers.py)
        d = json.loads(json.dumps(d, default=str).replace('{"event_amount": 1}', '{"event_count": 1}'))
        d["cond"]["own_untap"] = True
    if d is not None and text.endswith("and you tap that creature."):  # (Mind Whip: both consequences follow a failed payment)
        d["effects"][1]["skip"] = 2
        d["effects"].append({"do": "tap", "who": "host"})
    if d is not None and text.startswith("{2}: If ~ isn't a creature, it becomes a 0/0 Construct Hero"):  # (Iron Man Armor: quoted static, 613.1f)
        d["effects"][-1]["abilities"] = ["This creature gets +1/+1 for each artifact you control."]
    if d is not None and text.startswith("When ~ dies, if it had one or more -1/-1 counters on it, its owner draws"):  # (Oft-Nabbed Goat: other than the owner)
        d["effects"][-1]["who"] = "each_other_than_source_owner110d"
    if d is not None and text.endswith("it enters tapped and attacking."):
        d["effects"][0]["tap_atk110d"] = "Enchantment"
    return d


# Minthara, Merciless Soul: ward {X} (702.21a) with X the experience counters its controller has as the ward ability triggers (122.1, 608.2h); read in
# triggers.targeted. Zero counters is ward {0}: nothing to pay, so no trigger.
WARD_XP = "~ has ward {X}, where X is the number of experience counters you have."


def ward_xp(plan: Any, card: Any) -> list[str]:
    from app.rules import permissions

    if not any(src.id == card.id for src, _, _ in permissions._table_statics(plan.state, plan.info, {"ward_xp110d"})):
        return []
    n = int(plan.state.players[card.controller].resources.get("experience", 0))
    return [f"{{{n}}}"] if n > 0 else []
