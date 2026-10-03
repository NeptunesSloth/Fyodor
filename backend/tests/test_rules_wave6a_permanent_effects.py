"""Wave 6A: effect bodies acting on permanents and cards.

* "[Object] doesn't untap during its controller's / your next untap step" (502.3; app/rules/next_untap.py): a
  one-shot effect on named objects; "its controller" is read when an untap step comes, and the effect ends
  with that untap step whether or not the permanent was tapped (611.2c: it modifies the rules, not the
  object). Mass wordings stay manual.

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import attack, creature, on_field, settle, to_hand, to_turn
from tests.test_rules_effects import mana
from tests.test_rules_wave4h_activation_costs import build, roundtrip

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Frost Breath', set_code="tst", number="A01", mana_cost='{2}{U}', cmc=3.0, type_line='Instant', oracle_text="Tap up to two target creatures. Those creatures don't untap during their controller's next untap step.", colors=['U'], color_identity=['U']),  # noqa: E501
    card("Kefnet's Monument", set_code="tst", number="A02", mana_cost='{3}', cmc=3.0, type_line='Legendary Artifact', oracle_text="Blue creature spells you cast cost {1} less to cast.\nWhenever you cast a creature spell, target creature an opponent controls doesn't untap during its controller's next untap step."),  # noqa: E501
    card('Arbalest Elite', set_code="tst", number="A03", mana_cost='{2}{W}{W}', cmc=4.0, type_line='Creature — Human Archer', oracle_text="{2}{W}, {T}: This creature deals 3 damage to target attacking or blocking creature. This creature doesn't untap during your next untap step.", power='2', toughness='3', colors=['W'], color_identity=['W']),  # noqa: E501
    card('Apes of Rath', set_code="tst", number="A04", mana_cost='{2}{G}{G}', cmc=4.0, type_line='Creature — Ape', oracle_text="Whenever this creature attacks, it doesn't untap during its controller's next untap step.", power='5', toughness='4', colors=['G'], color_identity=['G']),  # noqa: E501
    card("Ojutai's Breath", set_code="tst", number="A05", mana_cost='{2}{U}', cmc=3.0, type_line='Instant', oracle_text="Tap target creature. It doesn't untap during its controller's next untap step.\nRebound (If you cast this spell from your hand, exile it as it resolves. At the beginning of your next upkeep, you may cast this card from exile without paying its mana cost.)", colors=['U'], color_identity=['U'], keywords=['Rebound']),  # noqa: E501
    card('Sleep', set_code="tst", number="A06", mana_cost='{2}{U}{U}', cmc=4.0, type_line='Sorcery', oracle_text="Tap all creatures target player controls. Those creatures don't untap during that player's next untap step.", colors=['U'], color_identity=['U']),  # noqa: E501
    card("Bontu's Last Reckoning", set_code="tst", number="A07", mana_cost='{1}{B}{B}', cmc=3.0, type_line='Sorcery', oracle_text="Destroy all creatures. Lands you control don't untap during your next untap step.", colors=['B'], color_identity=['B']),  # noqa: E501
    card('Grizzly Bears', set_code="tst", number="A08", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Bear', oracle_text='', power='2', toughness='2', colors=['G'], color_identity=['G']),  # noqa: E501
]
FULL = ["Frost Breath", "Kefnet's Monument", "Arbalest Elite", "Apes of Rath", "Ojutai's Breath"]
STILL_MANUAL = {  # (card, the line that stays manual)
    "Sleep": "that player's next untap step",  # (that player's, not its controller's: not read)
    "Bontu's Last Reckoning": "Lands you control don't untap",  # 611.2c: a rules effect on whatever matches then
}


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", list(STILL_MANUAL))
def test_still_manual(cards, name):
    cov = coverage.of_card_data(cards.resolve(name))
    assert any(not f.supported and STILL_MANUAL[name] in f.label for f in cov.features)


def tapped(s, c):
    return s.state.cards[c.id].tapped


# -- next untap step -------------------------------------------------------------------------------------
def test_untap_rider_parses_named_objects_only():
    assert scripts.parse_effects("Tap target creature. It doesn't untap during its controller's next untap step.") == (
        [{"do": "tap", "who": "target"}, {"do": "stay_tapped", "who": "target", "during": "controller"}], "creature", False)
    for text in ("Each attacking creature doesn't untap during its controller's next untap step.",
                 "Lands you control don't untap during your next untap step.",
                 "Creatures target player controls don't untap during that player's next untap step.",
                 "Tap target creature. It doesn't untap during its controller's next two untap steps."):
        assert scripts.parse_effects(text) is None, text


def test_frost_breath_keeps_both_tapped_through_one_untap_step(cards):
    s = build(cards, p1=("Frost Breath",))
    breath = to_hand(s, "Frost Breath")
    a, b = creature(s, "p2", "Ox"), creature(s, "p2", "Yak")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=breath.id, targets=[a.id, b.id], target_counts=[2])
    settle(s)
    assert tapped(s, a) and tapped(s, b) and len(s.state.rules.stay_tapped) == 2
    roundtrip(s)
    to_turn(s, 2)  # Bob's untap step: they stay tapped (502.3)
    assert tapped(s, a) and tapped(s, b) and not s.state.rules.stay_tapped
    to_turn(s, 4)  # the next one: they untap
    assert not tapped(s, a) and not tapped(s, b)
    roundtrip(s)


def test_the_effect_is_used_up_even_when_the_permanent_was_untapped(cards):
    """Kefnet's Monument on an untapped creature: it untaps normally in its controller's next untap step, and the
    effect ends there (611.2c / 502.3), so a later tap is undone by the untap step after that."""
    s = build(cards, p1=("Kefnet's Monument", "Grizzly Bears"))
    on_field(s, "Kefnet's Monument")
    ox = creature(s, "p2", "Ox")
    bears = to_hand(s, "Grizzly Bears")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    d = s.state.rules.decision
    if d is not None and d.kind != "choose_targets":
        settle(s)
    settle(s)
    assert not tapped(s, ox) and s.state.rules.stay_tapped
    to_turn(s, 2)  # Bob's untap step: the effect ends (the Ox wasn't tapped)
    assert not s.state.rules.stay_tapped
    act(s, "p2", type="tap", card_ids=[ox.id], tapped=True)
    to_turn(s, 4)
    assert not tapped(s, ox)
    roundtrip(s)


def test_its_controller_is_read_when_the_untap_step_comes(cards):
    """Frost Breath on Bob's creature; Alice then gains control of it: it stays tapped during Alice's next untap
    step (its controller's at that time, 611.2c), and Bob's untap step before that doesn't use the effect up."""
    s = build(cards, p1=("Frost Breath",))
    breath = to_hand(s, "Frost Breath")
    ox = creature(s, "p2", "Ox")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=breath.id, targets=[ox.id], target_counts=[1])
    settle(s)
    assert tapped(s, ox)
    act(s, "p1", type="set_controller", card_ids=[ox.id], player="p1")
    to_turn(s, 2)  # Bob's untap step: not the Ox's controller's
    assert tapped(s, ox) and s.state.rules.stay_tapped
    to_turn(s, 3)  # Alice's: it stays tapped, and the effect ends
    assert tapped(s, ox) and not s.state.rules.stay_tapped
    to_turn(s, 5)
    assert not tapped(s, ox)
    roundtrip(s)


def test_a_new_object_is_not_affected(cards):
    s = build(cards, p1=("Frost Breath",), p2=("Grizzly Bears",))
    breath = to_hand(s, "Frost Breath")
    ox = on_field(s, "Grizzly Bears", pid="p2")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=breath.id, targets=[ox.id], target_counts=[1])
    settle(s)
    assert tapped(s, ox)
    act(s, "p2", type="move", card_ids=[ox.id], to={"player": "p2", "zone": "exile"})
    act(s, "p2", type="move", card_ids=[ox.id], to={"player": "p2", "zone": "battlefield"})  # a new object (400.7)
    act(s, "p2", type="tap", card_ids=[ox.id], tapped=True)
    to_turn(s, 2)
    assert not tapped(s, ox) and not s.state.rules.stay_tapped
    roundtrip(s)


def test_apes_of_rath_stay_tapped_after_attacking(cards):
    s = build(cards, p1=("Apes of Rath",))
    apes = on_field(s, "Apes of Rath")
    to_turn(s, 3, phase="main1")
    act(s, "p1", type="pass_priority")  # → combat
    attack(s, (apes, "p2"))
    settle(s)
    assert tapped(s, apes) and s.state.rules.stay_tapped
    to_turn(s, 5)  # Alice's next untap step
    assert tapped(s, apes) and not s.state.rules.stay_tapped
    to_turn(s, 7)
    assert not tapped(s, apes)
    roundtrip(s)
