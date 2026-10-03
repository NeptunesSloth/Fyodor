"""Wave 12B: lure (509.1c) — "All creatures able to block this creature do so." as a static and as an activated ability."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_combat import creature
from tests.test_rules_conditionals import settle
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave6c_tokens_pumps import build, card_named, mana, reloaded
from tests.test_rules_wave7e_activated import combat_table

EXTRA = [
    card('Deadbridge Goliath', set_code='tst', number='Y01', mana_cost='{2}{G}{G}', cmc=4.0, type_line='Creature — Insect Skeleton', oracle_text="Scavenge {4}{G}{G} ({4}{G}{G}, Exile this card from your graveyard: Put a number of +1/+1 counters equal to this card's power on target creature. Scavenge only as a sorcery.)", power='5', toughness='5', colors=['G'], color_identity=['G'], keywords=['Scavenge']),  # noqa: E501
    card('Redeem', set_code='tst', number='Y02', mana_cost='{W}', cmc=1.0, type_line='Instant', oracle_text='Prevent all damage that would be dealt this turn to up to two target creatures.', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card("Djeru's Resolve", set_code='tst', number='Y03', mana_cost='{W}', cmc=1.0, type_line='Instant', oracle_text='Untap target creature. Prevent all damage that would be dealt to it this turn.', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Murder', set_code='tst', number='Y06', mana_cost='{1}{B}{B}', cmc=3.0, type_line='Instant', oracle_text='Destroy target creature.', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Test Merfolk', set_code='tst', number='Y04', mana_cost='{U}', cmc=1.0, type_line='Creature — Merfolk', oracle_text='', power='1', toughness='1', colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Wanderwine Test', set_code='tst', number='Y05', mana_cost='{G}', cmc=1.0, type_line='Creature — Merfolk Wizard', oracle_text='Champion a Merfolk (When this enters, sacrifice it unless you exile another Merfolk you control. When this leaves the battlefield, that card returns to the battlefield.)', power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=['Champion']),  # noqa: E501
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_scavenge_puts_counters_equal_to_the_exiled_cards_power(cards):
    s = build(cards, "Deadbridge Goliath", forests=12)
    goliath = card_named(s, "Deadbridge Goliath")
    bear = creature(s, "p1", "Bear", "2/2")
    act(s, "p1", type="move", card_ids=[goliath.id], to={"zone": "graveyard"})
    mana(s, G=2, C=4)
    act(s, "p1", type="activate_ability", card_id=goliath.id, ability=0, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].counters == {"+1/+1": 5}  # 702.97a: the power of the card exiled
    assert s.state.cards[goliath.id].zone == "p1:exile"
    check(s)


def test_prevention_to_targets_and_to_it(cards):
    from tests.test_rules_attachments import build as build_attach
    from tests.test_rules_attachments import mana, named, to_hand, token
    from tests.test_rules_effects import pass_until_stack_empty
    from tests.test_rules_wave6b_damage import PINGER, cast, ping, roundtrip, zone

    s = build_attach(cards, "Redeem", "Djeru's Resolve")
    a, b, c, d = (token(s, "p1", n, "1/1", PINGER) for n in "ABCD")
    redeem = to_hand(s, "Redeem")  # 615.1: damage to the two targets this turn is prevented
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=redeem.id, targets=[a.id, b.id], target_counts=[2])
    pass_until_stack_empty(s)
    ping(s, c, a.id)
    ping(s, d, b.id)
    assert zone(s, a) == zone(s, b) == "p1:battlefield"
    cast(s, "Djeru's Resolve", targets=[c.id], W=1)
    ping(s, a, c.id)
    assert zone(s, c) == "p1:battlefield" and not named(s, "C").tapped
    roundtrip(s)


def test_champion_exiles_a_creature_and_returns_it_when_the_champion_leaves(cards):
    from tests.test_rules_attachments import to_hand
    from tests.test_rules_conditionals import pick, until_asked
    from tests.test_rules_wave6c_tokens_pumps import put

    for answer in ("pay", "decline"):
        s = build(cards, "Wanderwine Test", "Test Merfolk", "Murder")
        merfolk = put(s, "Test Merfolk")
        champion = to_hand(s, "Wanderwine Test")
        mana(s, G=1)
        act(s, "p1", type="cast_spell", card_id=champion.id)
        d = until_asked(s)
        assert d.kind == "choose_one" and [o.id for o in d.options] == ["pay", "decline"]
        pick(s, answer)
        if answer == "pay" and s.state.rules.decision is not None:  # (the one Merfolk is chosen on its own otherwise)
            pick(s, merfolk.id)
        settle(s)
        if answer == "decline":  # 702.72a: sacrificed unless a creature was exiled
            assert s.state.cards[champion.id].zone == "p1:graveyard" and s.state.cards[merfolk.id].zone == "p1:battlefield"
            continue
        assert s.state.cards[champion.id].zone == "p1:battlefield" and s.state.cards[merfolk.id].zone == "p1:exile"
        murder = to_hand(s, "Murder")
        mana(s, B=2, C=1)
        act(s, "p1", type="cast_spell", card_id=murder.id, targets=[champion.id])
        settle(s)
        assert s.state.cards[merfolk.id].zone == "p1:battlefield"  # the exiled card returns when the champion leaves
        check(s)


def test_exerted_avengers_prevention_shield_covers_the_combat_damage_to_it(cards):
    from tests.test_rules_combat_triggers import through_combat
    from tests.test_rules_conditionals import token_of
    from tests.test_rules_wave6e_statics import attack_with

    s = build(cards)
    text = ("You may exert this creature as it attacks. When you do, prevent all combat damage that would be dealt to it this turn. "
            "(An exerted creature won't untap during your next untap step.)")
    avenger = token_of(s, "p1", "Avenger", "Token Creature — Human Warrior", "3/1", "Haste\n" + text)
    guard = token_of(s, "p2", "Guard", "Token Creature — Bear", "3/3")
    attack_with(s, avenger)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[avenger.id])
    through_combat(s, {"p2": [(guard, avenger)]})
    assert s.state.cards[avenger.id].zone == "p1:battlefield" and guard.id not in s.state.cards  # 615.1: it takes none, deals 3
    check(s)


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def test_static_lure_makes_every_able_creature_block(cards):
    from tests.test_rules_combat import attack, block

    s, lure, guard, spare = combat_table(cards, "All creatures able to block this creature do so.")
    act(s, "p1", type="pass_priority")
    attack(s, (lure, "p2"))
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2")
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2", (guard, lure))
    block(s, "p2", (guard, lure), (spare, lure))
    check(s)


def test_lure_for_one_kind_of_creature(cards):
    from tests.test_rules_combat import attack, block

    s, lure, guard, spare = combat_table(cards, "All Walls able to block this creature do so.")
    act(s, "p2", type="create_token", player="p2", token={"name": "Bulwark", "type_line": "Token Creature — Wall",
                                                          "power": "0", "toughness": "4"})
    wall = next(c for c in s.state.cards.values() if c.name == "Bulwark")
    act(s, "p1", type="pass_priority")
    attack(s, (lure, "p2"))
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2", (guard, lure))  # (only the Wall is made to block)
    block(s, "p2", (wall, lure))
    check(s)


def test_activated_lure_lasts_the_turn(cards):
    from tests.test_rules_combat import attack, block

    s, lure, guard, spare = combat_table(cards, "{2}{G}: All creatures able to block this creature this turn do so.")
    mana(s, G=1, C=2)
    act(s, "p1", type="activate_ability", card_id=lure.id, ability=0)
    settle(s)
    act(s, "p1", type="pass_priority")
    attack(s, (lure, "p2"))
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2", (guard, lure))
    block(s, "p2", (guard, lure), (spare, lure))
    check(s)


# -- landwalk variants (702.14a, 702.14c) --
@pytest.mark.parametrize(("walk", "land", "blockable"), [
    ("Snow landwalk", "Token Snow Land — Forest", False),
    ("Snow landwalk", "Token Land — Forest", True),
    ("Snow swampwalk", "Token Snow Land — Forest", True),
    ("Snow forestwalk", "Token Snow Land — Forest", False),
    ("Nonbasic landwalk", "Token Land", False),
    ("Nonbasic landwalk", "Token Basic Land — Forest", True),
    ("Legendary landwalk", "Token Legendary Land", False),
    ("Legendary landwalk", "Token Land", True),
    ("Artifact landwalk", "Token Artifact Land", False),
    ("Desertwalk", "Token Land — Desert", False),
])
def test_landwalk_variants(cards, walk, land, blockable):
    from tests.test_rules_combat import _blocks, _evasion_table

    s, sneak, guard = _evasion_table(cards, walk)
    act(s, "p2", type="create_token", player="p2", token={"name": "Terrain", "type_line": land})
    assert _blocks(s, sneak, guard) is blockable
    check(s)
