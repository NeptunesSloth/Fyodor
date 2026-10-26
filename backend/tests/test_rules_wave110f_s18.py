"""Wave 110F session 18, on real Oracle text. Every scenario checks the replay and a save and a load.

* 509.1g, 701.8, 701.19c: Glyph of Reincarnation: destroys the creatures the target Wall blocked this turn (no regeneration); for each that died, its caster puts a
  creature card from the graveyard of the player who controlled it the last time the Wall blocked it onto the battlefield under its owner's control.
"""

from __future__ import annotations

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30r_history import ability_index
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
    real('Zevlor, Elturel Exile', '{1}{U}{B}{R}', 4, 'Legendary Creature — Tiefling Warrior',
         'Haste\n{2}, {T}: When you next cast an instant or sorcery spell that targets only a single opponent or a single permanent an opponent controls this turn, '
         'for each other opponent, choose that player or a permanent they control, copy that spell, and the copy targets the chosen player or permanent.', ('4', '2'), 'BRU'),
    real('Lightning Bolt', '{R}', 1, 'Instant', 'Lightning Bolt deals 3 damage to any target.', None, 'R'),
    real('Test Pair 16F', '{R}', 1, 'Instant', 'Test Pair 16F deals 1 damage to target creature. Test Pair 16F deals 1 damage to target player.', None, 'R'),
    real('Grizzly Bears', '{1}{G}', 2, 'Creature — Bear', '', ('2', '2'), 'G'),
    real('Camouflage', '{G}', 1, 'Instant', 'Cast this spell only during your declare attackers step.\nThis turn, instead of declaring blockers, each defending player chooses any number of creatures they control and divides them into a number of piles equal to the number of attacking creatures for whom that player is the defending player. Creatures those players control that can block additional creatures may likewise be put into additional piles. Assign each pile to a different one of those attacking creatures at random. Each creature in a pile that can block the creature that pile is assigned to does so. (Piles can be empty.)', None, 'G'),
    real('Test Flyer 16F', '{1}', 1, 'Creature — Bird', 'Flying', ('1', '1'), ''),
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


# -- Zevlor, Elturel Exile (603.7, 707.10, 115.9c) ---------------------------------------------------------------------------------
def _zev(cards, p1=(), p2=(), p3=()):
    from tests.test_rules_wave100o_retarget import build3

    s = build3(cards, p1=("Zevlor, Elturel Exile", *p1), p2=p2, p3=p3)
    zev = next(c for c in s.state.cards.values() if c.name == "Zevlor, Elturel Exile")
    act(s, "p1", type="move", card_ids=[zev.id], to={"player": "p1", "zone": "battlefield"})
    ready(s, "Zevlor, Elturel Exile")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=zev.id, ability=ability_index(s, zev, "When you next cast"))
    answer(s)
    return s


def _bolt(s, target, **kw):
    from tests.test_rules_conditionals import until_asked
    from tests.test_rules_wave5b_stack_interaction import alice_casts

    alice_casts(s, "Lightning Bolt", targets=[target], R=1)
    until_asked(s)  # (Zevlor's delayed trigger goes on the stack above the spell)


def test_zevlor_copies_for_the_other_opponent_with_only_the_player_to_choose(cards):
    """Bolt at p2: p3 is the other opponent; the caster chooses p3 (or a permanent p3 controls) for the copy. Only the next such spell is copied."""
    s = _zev(cards, p1=("Lightning Bolt", "Lightning Bolt"))
    _bolt(s, "p2")  # (p3 controls nothing: the player is the only legal choice, so no question is asked)
    answer(s)
    assert s.state.players["p2"].life == 37 and s.state.players["p3"].life == 37 and s.state.players["p1"].life == 40
    _bolt(s, "p2")
    answer(s)
    assert s.state.players["p2"].life == 34 and s.state.players["p3"].life == 37  # (the watch was used up)
    check(s)


def test_zevlor_targeted_permanent_names_the_opponent_who_controls_it(cards):
    """A Bolt at p2's creature: p2 is the opponent it concerns, so the copy goes to p3 or a permanent p3 controls."""
    s = _zev(cards, p1=("Lightning Bolt",), p2=("Grizzly Bears",), p3=("Grizzly Bears",))
    bear2 = put(s, "Grizzly Bears", "p2")
    bear3 = put(s, "Grizzly Bears", "p3")
    _bolt(s, bear2.id)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {"p3", bear3.id}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bear3.id])
    answer(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard" and zone_of(s, "Grizzly Bears", "p3") == "p3:graveyard"
    check(s)


def test_zevlor_ignores_a_spell_that_does_not_target_only_an_opponent_thing(cards):
    """A Bolt at your own creature does not match, so the watch stays; the next Bolt at an opponent is the one copied."""
    s = _zev(cards, p1=("Lightning Bolt", "Lightning Bolt", "Grizzly Bears"))
    mine = put(s, "Grizzly Bears")
    _bolt(s, mine.id)
    answer(s)
    assert s.state.rules.decision is None and s.state.players["p3"].life == 40
    _bolt(s, "p2")
    answer(s)
    assert s.state.players["p2"].life == 37 and s.state.players["p3"].life == 37
    check(s)


def test_zevlor_does_not_copy_a_spell_with_two_different_targets(cards):
    """115.9c: "targets only a single" opponent or permanent: a spell with two different targets does not match, and the watch is not used up."""
    from tests.test_rules_wave5b_stack_interaction import alice_casts

    s = _zev(cards, p1=("Test Pair 16F", "Lightning Bolt"), p2=("Grizzly Bears",), p3=("Grizzly Bears",))
    bear2 = put(s, "Grizzly Bears", "p2")
    alice_casts(s, "Test Pair 16F", targets=[bear2.id, "p3"], counts=[1, 1], R=1)
    answer(s)
    assert s.state.players["p3"].life == 39 and s.state.players["p2"].life == 40
    _bolt(s, "p2")
    answer(s)
    assert s.state.players["p2"].life == 37 and s.state.players["p3"].life == 36  # (1 from the pair, 3 from the copy)
    check(s)


# -- Camouflage (509.1, 509.1b) ----------------------------------------------------------------------------------------------------
def _camo(cards, mine, theirs, attackers):
    s = build(cards, ["Camouflage", *mine], theirs)
    cs = [put(s, n) for n in mine]
    ready(s, *dict.fromkeys(mine))
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    atk = [c for c in cs if c.name in attackers]
    attack(s, *atk)
    mana(s, G=1)
    cast(s, "Camouflage")
    return s, atk


def _blocked_by(s, attacker):
    return sorted(c.name for c in s.state.cards.values() if c.blocks(attacker.id))


def _choose(s, pid, *ids):
    d = s.state.rules.decision
    assert d is not None and d.player == pid, d
    act(s, pid, type="choose", decision_id=d.id, option_ids=list(ids))
    return s.state.rules.decision


def _asked(s):
    for _ in range(30):
        if s.state.rules.decision is not None:
            return s.state.rules.decision
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never asked")


def test_camouflage_two_piles_each_creature_blocks_a_random_attacker(cards):
    """Two attackers, two chosen creatures, one per pile: each pile goes to a different attacker, so each attacker ends up blocked by exactly one of them."""
    s, (a, b) = _camo(cards, ["Test Raider A 16F", "Test Raider B 16F"], ["Test Wall 16F", "Test Elf 16F"], ["Test Raider A 16F", "Test Raider B 16F"])
    wall, elf = put(s, "Test Wall 16F", "p2"), put(s, "Test Elf 16F", "p2")
    d = _asked(s)
    assert d.kind == "choose_cards" and d.player == "p2" and {o.id for o in d.options} == {wall.id, elf.id}
    d = _choose(s, "p2", wall.id, elf.id)
    assert {o.label for o in d.options} == {"Pile 1", "Pile 2"}
    _choose(s, "p2", "0")
    _choose(s, "p2", "1")
    assert sorted(_blocked_by(s, a) + _blocked_by(s, b)) == ["Test Elf 16F", "Test Wall 16F"] and len(_blocked_by(s, a)) == 1
    check(s)


def test_camouflage_empty_piles_mean_no_blocks(cards):
    """"Piles can be empty": choosing no creature blocks nothing."""
    s, (a, b) = _camo(cards, ["Test Raider A 16F", "Test Raider B 16F"], ["Test Wall 16F"], ["Test Raider A 16F", "Test Raider B 16F"])
    put(s, "Test Wall 16F", "p2")
    _asked(s)
    _choose(s, "p2")
    assert _blocked_by(s, a) == [] and _blocked_by(s, b) == []
    check(s)


def test_camouflage_one_attacker_one_pile_and_a_creature_that_cannot_block_it_does_not(cards):
    """One attacker: one pile gets every chosen creature without asking. A creature that can't block a flyer (509.1b) stays out of the block, the flyer-blocker blocks."""
    s, (fl,) = _camo(cards, ["Test Flyer 16F"], ["Test Wall 16F", "Test Flyer 16F"], ["Test Flyer 16F"])
    wall = put(s, "Test Wall 16F", "p2")
    bird = put(s, "Test Flyer 16F", "p2")
    _asked(s)
    _choose(s, "p2", wall.id, bird.id)
    assert _blocked_by(s, fl) == ["Test Flyer 16F"]
    check(s)


def test_camouflage_a_creature_that_can_block_additional_creatures_may_join_two_piles(cards):
    """509.1a: the Wall that can block an additional creature may be put in both piles, so both attackers are blocked by it."""
    s, (a, b) = _camo(cards, ["Test Raider A 16F", "Test Raider B 16F"], ["Test Wall 16F"], ["Test Raider A 16F", "Test Raider B 16F"])
    wall = put(s, "Test Wall 16F", "p2")
    _asked(s)
    d = _choose(s, "p2", wall.id)
    assert d.max_choices == 2
    _choose(s, "p2", "0", "1")
    assert _blocked_by(s, a) == ["Test Wall 16F"] and _blocked_by(s, b) == ["Test Wall 16F"]
    check(s)
