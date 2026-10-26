"""Wave 110F session 16, on real Oracle text. Every scenario checks the replay and a save and a load.

* 509.1g, 701.8, 701.19c: Glyph of Reincarnation: destroys the creatures the target Wall blocked this turn (no regeneration); for each that died, its caster puts a
  creature card from the graveyard of the player who controlled it the last time the Wall blocked it onto the battlefield under its owner's control.
"""

from __future__ import annotations

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100f_attached import to_phase
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
)
from tests.wave9c_kit import build, check, mana, put, zone_of
from tests.wave36a_kit import attack, attack_as, block, ready, to_turn_of

_GLYPH = ("Cast this spell only after combat.\nDestroy all creatures that were blocked by target Wall this turn. They can't be regenerated. For each creature that died this way, "
          "put a creature card from the graveyard of the player who controlled that creature the last time it became blocked by that Wall onto the battlefield under its owner's control.")
_BASE.extend([
    real('Glyph of Reincarnation', '{2}{G}{G}', 4, 'Instant', _GLYPH, None, 'G'),
    real('Test Wall 16F', '{1}', 1, 'Creature — Wall', 'Defender\nThis creature can block an additional creature each combat.', ('0', '6'), ''),
    real('Test Raider A 16F', '{1}', 1, 'Creature — Ogre', '', ('2', '2'), ''),
    real('Test Raider B 16F', '{1}', 1, 'Creature — Orc', '', ('3', '3'), ''),
    real('Threaten', '{2}{R}', 3, 'Sorcery', 'Untap target creature and gain control of it until end of turn. That creature gains haste until end of turn.', None, 'R'),
    real('Test Elf 16F', '{1}', 1, 'Creature — Elf', '', ('1', '1'), ''),
])


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Glyph of Reincarnation")).level == "FULL"


def _after_combat(cards, *, wall_blocks):
    """p1 attacks with two creatures into p2's Wall; the Wall blocks ``wall_blocks`` (names); p1 holds the Glyph in its second main phase."""
    s = build(cards, ["Glyph of Reincarnation", "Test Raider A 16F", "Test Raider B 16F", "Test Elf 16F"], ["Test Wall 16F"])
    a, b = put(s, "Test Raider A 16F"), put(s, "Test Raider B 16F")
    wall = put(s, "Test Wall 16F", "p2")
    ready(s, "Test Raider A 16F", "Test Raider B 16F")
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    attack(s, a, b)
    block(s, "p2", *[(wall, x) for x in (a, b) if x.name in wall_blocks])
    to_phase(s, "main2")
    mana(s, G=2, C=2)
    return s, a, b, wall


def test_glyph_destroys_what_the_wall_blocked_and_returns_a_creature_card(cards):
    """Only the blocked creature is destroyed (the other attacker was never blocked); its controller's graveyard supplies the card, chosen by the caster."""
    s, a, b, wall = _after_combat(cards, wall_blocks=["Test Raider A 16F"])
    elf = next(c for c in s.state.cards.values() if c.name == "Test Elf 16F" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[elf.id], to={"player": "p1", "zone": "graveyard"})
    cast(s, "Glyph of Reincarnation", [wall.id])
    answer(s, elf.id)
    assert zone_of(s, "Test Elf 16F") == "p1:battlefield"
    assert zone_of(s, "Test Raider A 16F") == "p1:graveyard" and zone_of(s, "Test Raider B 16F") == "p1:battlefield"
    check(s)


def test_glyph_with_two_blocked_creatures_returns_two_cards(cards):
    s, a, b, wall = _after_combat(cards, wall_blocks=["Test Raider A 16F", "Test Raider B 16F"])
    cast(s, "Glyph of Reincarnation", [wall.id])
    answer(s)
    assert zone_of(s, "Test Raider A 16F") == "p1:battlefield" and zone_of(s, "Test Raider B 16F") == "p1:battlefield"
    check(s)


def test_glyph_unblocked_creature_is_not_destroyed(cards):
    s, a, b, wall = _after_combat(cards, wall_blocks=[])
    cast(s, "Glyph of Reincarnation", [wall.id])
    answer(s)
    assert zone_of(s, "Test Raider A 16F") == "p1:battlefield" and zone_of(s, "Test Raider B 16F") == "p1:battlefield"


def test_glyph_uses_the_graveyard_of_the_player_who_controlled_the_creature_when_it_was_blocked(cards):
    """p2 steals p1's Raider with Threaten and attacks; p1's Wall blocks it. The Raider is p1's card, but p2 controlled it when it was blocked: the card comes from p2's graveyard."""
    s = build(cards, ["Glyph of Reincarnation", "Test Raider A 16F", "Test Wall 16F"], ["Threaten", "Test Elf 16F"])
    raider, wall = put(s, "Test Raider A 16F"), put(s, "Test Wall 16F")
    elf = next(c for c in s.state.cards.values() if c.name == "Test Elf 16F" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[elf.id], to={"player": "p2", "zone": "graveyard"})
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    to_turn_of(s, "p2")
    mana(s, "p2", R=1, C=2)
    cast(s, "Threaten", [raider.id], pid="p2")
    answer(s)
    attack_as(s, "p2", [raider], "p1")
    block(s, "p1", (wall, raider))
    to_phase(s, "main2")
    act(s, "p2", type="pass_priority")
    mana(s, "p1", G=2, C=2)
    cast(s, "Glyph of Reincarnation", [wall.id])
    answer(s)
    assert zone_of(s, "Test Raider A 16F") == "p1:graveyard"
    assert zone_of(s, "Test Elf 16F", "p2") == "p2:battlefield"
    check(s)
