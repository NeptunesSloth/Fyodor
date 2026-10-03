"""Wave 9C: radiance ("Target creature and each other creature that shares a color with it …"), researched against
CR 2026-09-25.

Radiance is an ability word (207.2c): no rules meaning. The instruction affects the target and each other object of the
named type that shares a color with it (105.4: at least one color in common), judged as it is carried out (608.2h); a
colorless target shares nothing, so only it is affected. Each scenario checks the replay and a save and a load.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, cast, check, life, mana, pt, put, to_hand, zone_of

EXTRA = [
    card('Cleansing Beam', set_code='tst', number='E01', mana_cost='{4}{R}', cmc=5.0, type_line='Instant', oracle_text='Radiance — Cleansing Beam deals 2 damage to target creature and each other creature that shares a color with it.', colors=['R'], color_identity=['R'], keywords=['Radiance']),  # noqa: E501
    card('Wojek Siren', set_code='tst', number='E02', mana_cost='{W}', cmc=1.0, type_line='Instant', oracle_text='Radiance — Target creature and each other creature that shares a color with it get +1/+1 until end of turn.', colors=['W'], color_identity=['W'], keywords=['Radiance']),  # noqa: E501
    card('Brightflame', set_code='tst', number='E03', mana_cost='{X}{R}{R}{W}{W}', cmc=4.0, type_line='Sorcery', oracle_text='Radiance — Brightflame deals X damage to target creature and each other creature that shares a color with it. You gain life equal to the damage dealt this way.', colors=['R', 'W'], color_identity=['R', 'W'], keywords=['Radiance']),  # noqa: E501
    card('Leave No Trace', set_code='tst', number='E04', mana_cost='{1}{W}', cmc=2.0, type_line='Instant', oracle_text='Radiance — Destroy target enchantment and each other enchantment that shares a color with it.', colors=['W'], color_identity=['W'], keywords=['Radiance']),  # noqa: E501
    card('Wojek Embermage', set_code='tst', number='E05', mana_cost='{3}{R}', cmc=4.0, type_line='Creature — Human Wizard', oracle_text='Radiance — {T}: This creature deals 1 damage to target creature and each other creature that shares a color with it.', colors=['R'], color_identity=['R'], keywords=['Radiance'], power='1', toughness='2'),  # noqa: E501
    card('Incite Hysteria', set_code='tst', number='E06', mana_cost='{2}{R}', cmc=3.0, type_line='Sorcery', oracle_text='Radiance — Until end of turn, target creature and each other creature that shares a color with it gain "This creature can\'t block."', colors=['R'], color_identity=['R'], keywords=['Radiance']),  # noqa: E501
    card('Rally the Righteous', set_code='tst', number='E07', mana_cost='{1}{R}{W}', cmc=3.0, type_line='Instant', oracle_text='Radiance — Untap target creature and each other creature that shares a color with it. Those creatures get +2/+0 until end of turn.', colors=['R', 'W'], color_identity=['R', 'W'], keywords=['Radiance']),  # noqa: E501
    card('Green Bear', set_code='tst', number='E10', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Bear', oracle_text='', power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Red Imp', set_code='tst', number='E11', mana_cost='{2}{R}', cmc=3.0, type_line='Creature — Imp', oracle_text='', power='3', toughness='3', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Gruul Pair', set_code='tst', number='E12', mana_cost='{R}{G}', cmc=2.0, type_line='Creature — Elemental', oracle_text='', power='3', toughness='3', colors=['R', 'G'], color_identity=['R', 'G'], keywords=[]),  # noqa: E501
    card('Steel Golem', set_code='tst', number='E13', mana_cost='{3}', cmc=3.0, type_line='Artifact Creature — Golem', oracle_text='', power='3', toughness='3', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Second Golem', set_code='tst', number='E14', mana_cost='{3}', cmc=3.0, type_line='Artifact Creature — Golem', oracle_text='', power='3', toughness='3', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('White Omen', set_code='tst', number='E15', mana_cost='{1}{W}', cmc=2.0, type_line='Enchantment', oracle_text='', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Second White Omen', set_code='tst', number='E16', mana_cost='{1}{W}', cmc=2.0, type_line='Enchantment', oracle_text='', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Blue Omen', set_code='tst', number='E17', mana_cost='{1}{U}', cmc=2.0, type_line='Enchantment', oracle_text='', colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
]
FULL = ["Cleansing Beam", "Wojek Siren", "Brightflame", "Leave No Trace", "Wojek Embermage", "Incite Hysteria",
        "Rally the Righteous"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def board(cards, spell, *, extra_mine=(), extra_theirs=()):
    """Alice has the spell and a Green Bear, a Gruul Pair and a Steel Golem; Bob a Red Imp, a Green Bear and a Second Golem."""
    s = build(cards, ("Green Bear", "Gruul Pair", "Steel Golem", spell, *extra_mine),
              ("Red Imp", "Green Bear", "Second Golem", *extra_theirs))
    for n in ("Green Bear", "Gruul Pair", "Steel Golem"):
        put(s, n)
    for n in ("Red Imp", "Green Bear", "Second Golem"):
        put(s, n, "p2")
    return s


def target(s, name, pid="p1"):
    from tests.wave9c_kit import card_named

    return card_named(s, name, pid).id


# -- coverage ----------------------------------------------------------------------------------------------------
def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", c["name"]


def test_a_second_target_or_other_wordings_stay_manual():
    from tests.test_rules_scripts import ch as characteristics

    for text in ("Target creature and each other creature that shares a creature type with it gets +1/+1 until end of turn.",
                 "Target creature and each other creature that shares a color with it get +1/+1 until end of turn. "
                 "Destroy target land.",
                 "Target creature and each other creature you control that shares a color with it get +1/+1 until end of turn."):
        assert coverage.of_characteristics(characteristics("Test", "Instant", text)).level != "FULL", text


# -- the shared color decides who is affected --------------------------------------------------------------------
def test_cleansing_beam_hits_the_target_and_every_creature_sharing_a_color_with_it(cards):
    s = board(cards, "Cleansing Beam")
    to_hand(s, "Cleansing Beam")
    mana(s, R=5)
    cast(s, "Cleansing Beam", targets=[target(s, "Red Imp", "p2")])
    # red: the Red Imp (2 damage on a 3/3) and the red-green Pair share red; the green bears and golems do not
    assert s.state.cards[target(s, "Red Imp", "p2")].damage == 2
    assert s.state.cards[target(s, "Gruul Pair")].damage == 2
    for n, p in (("Green Bear", "p1"), ("Green Bear", "p2"), ("Steel Golem", "p1"), ("Second Golem", "p2")):
        assert s.state.cards[target(s, n, p)].damage == 0, (n, p)
    check(s)


def test_a_multicolored_target_shares_with_either_of_its_colors(cards):
    s = board(cards, "Cleansing Beam")
    to_hand(s, "Cleansing Beam")
    mana(s, R=5)
    cast(s, "Cleansing Beam", targets=[target(s, "Gruul Pair")])
    for n, p in (("Gruul Pair", "p1"), ("Red Imp", "p2"), ("Green Bear", "p1"), ("Green Bear", "p2")):
        assert s.state.cards[target(s, n, p)].damage == 2, (n, p)
    assert s.state.cards[target(s, "Steel Golem")].damage == 0
    check(s)


def test_a_colorless_target_shares_no_color_with_anything(cards):
    """A colorless object has no color to share (105.2c), so only the target itself is affected."""
    s = board(cards, "Cleansing Beam")
    to_hand(s, "Cleansing Beam")
    mana(s, R=5)
    cast(s, "Cleansing Beam", targets=[target(s, "Steel Golem")])
    assert s.state.cards[target(s, "Steel Golem")].damage == 2
    assert s.state.cards[target(s, "Second Golem", "p2")].damage == 0  # (colorless too: they share nothing)
    for n, p in (("Gruul Pair", "p1"), ("Red Imp", "p2"), ("Green Bear", "p1")):
        assert s.state.cards[target(s, n, p)].damage == 0, (n, p)
    check(s)


def test_wojek_siren_pumps_the_group_until_end_of_turn(cards):
    s = board(cards, "Wojek Siren")
    to_hand(s, "Wojek Siren")
    mana(s, W=1)
    cast(s, "Wojek Siren", targets=[target(s, "Green Bear")])
    assert pt(s, "Green Bear") == (4, 4) and pt(s, "Green Bear", "p2") == (4, 4) and pt(s, "Gruul Pair") == (4, 4)
    assert pt(s, "Red Imp", "p2") == (3, 3) and pt(s, "Steel Golem") == (3, 3)
    check(s)


def test_leave_no_trace_destroys_enchantments_sharing_a_color(cards):
    s = build(cards, ("White Omen", "Second White Omen", "Leave No Trace"), ("Blue Omen",))
    for n in ("White Omen", "Second White Omen"):
        put(s, n)
    put(s, "Blue Omen", "p2")
    to_hand(s, "Leave No Trace")
    mana(s, W=2)
    cast(s, "Leave No Trace", targets=[target(s, "White Omen")])
    assert zone_of(s, "White Omen") == "p1:graveyard" and zone_of(s, "Second White Omen") == "p1:graveyard"
    assert zone_of(s, "Blue Omen", "p2") == "p2:battlefield"
    check(s)


def test_brightflame_gains_life_for_all_the_damage_dealt(cards):
    s = board(cards, "Brightflame")
    to_hand(s, "Brightflame")
    mana(s, R=2, W=2, G=2)
    before = life(s)
    cast(s, "Brightflame", targets=[target(s, "Red Imp", "p2")], x_value=2)
    assert s.state.cards[target(s, "Red Imp", "p2")].damage == 2 and s.state.cards[target(s, "Gruul Pair")].damage == 2
    assert life(s) == before + 4  # (two creatures were dealt 2 damage each)
    check(s)


def test_incite_hysteria_stops_the_group_from_blocking(cards):
    """Bob's Green Bear is the target: it can't block, and neither can the other green creature (Gruul Pair is Alice's,
    so it is not attacking here); his Red Imp shares no color with it and still can."""
    from tests.game_helpers import turn_on
    from tests.test_rules_conditionals import attack, sandbox, through_combat
    from tests.wave9c_kit import card_named

    s = sandbox(cards, "Incite Hysteria", "Steel Golem", p2=("Green Bear", "Red Imp"))
    for n in ("Steel Golem",):
        put(s, n)
    for n in ("Green Bear", "Red Imp"):
        put(s, n, "p2")
    to_hand(s, "Incite Hysteria")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    mana(s, R=3)
    cast(s, "Incite Hysteria", targets=[card_named(s, "Green Bear", "p2").id])
    act(s, "p1", type="pass_priority")  # → combat
    attack(s, (card_named(s, "Steel Golem"), "p2"))
    blocks = lambda n: [{"blocker_id": card_named(s, n, "p2").id, "attacker_id": card_named(s, "Steel Golem").id}]  # noqa: E731
    with pytest.raises(ActionError, match="can't block"):
        act(s, "p2", type="declare_blockers", blocks=blocks("Green Bear"))
    act(s, "p2", type="declare_blockers", blocks=blocks("Red Imp"))
    through_combat(s)
    assert zone_of(s, "Steel Golem") == "p1:graveyard" and zone_of(s, "Red Imp", "p2") == "p2:graveyard"  # (3 damage each)
    check(s)


def test_rally_the_righteous_untaps_and_pumps_the_group(cards):
    s = board(cards, "Rally the Righteous")
    for n, p in (("Red Imp", "p2"), ("Gruul Pair", "p1"), ("Green Bear", "p1")):
        act(s, p, type="tap", card_ids=[target(s, n, p)])
    to_hand(s, "Rally the Righteous")
    mana(s, R=1, W=1, G=1)
    cast(s, "Rally the Righteous", targets=[target(s, "Red Imp", "p2")])
    assert pt(s, "Red Imp", "p2") == (5, 3) and pt(s, "Gruul Pair") == (5, 3)
    assert pt(s, "Green Bear") == (3, 3)
    tapped = {n: s.state.cards[target(s, n, p)].tapped for n, p in (("Red Imp", "p2"), ("Gruul Pair", "p1"), ("Green Bear", "p1"))}
    assert tapped == {"Red Imp": False, "Gruul Pair": False, "Green Bear": True}  # (the bear shares no color with the imp)
    check(s)


def test_wojek_embermage_pings_the_group(cards):
    from tests.game_helpers import turn_on
    from tests.test_rules_conditionals import sandbox
    from tests.wave9c_kit import card_named

    s = sandbox(cards, "Wojek Embermage", "Green Bear", "Gruul Pair", p2=("Red Imp",))
    for n in ("Wojek Embermage", "Green Bear", "Gruul Pair"):
        put(s, n)
    put(s, "Red Imp", "p2")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    em = card_named(s, "Wojek Embermage")
    act(s, "p1", type="activate_ability", card_id=em.id, ability=0, targets=[target(s, "Red Imp", "p2")])
    settle(s)
    assert s.state.cards[target(s, "Red Imp", "p2")].damage == 1 and s.state.cards[target(s, "Gruul Pair")].damage == 1
    assert s.state.cards[em.id].damage == 1  # (the Embermage is red too)
    assert s.state.cards[target(s, "Green Bear")].damage == 0
    check(s)
