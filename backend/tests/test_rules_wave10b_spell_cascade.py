"""Wave 10B: statics that give spells cascade as they are cast (702.85a; app/rules/cast_limits.py ``granted_cascade``).

702.85a: cascade is a triggered ability, "When you cast this spell, …"; a spell that has it as it becomes cast (601.2i)
triggers it, one trigger per instance (702.85b). A static ability of a permanent gives it to the spells its controller
casts that match the wording. "The first spell you cast each turn" reads the spells cast before it this turn.
"""

from __future__ import annotations

import pytest

from app.rules import cast_limits, coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, to_hand
from tests.test_rules_effects import mana
from tests.test_rules_wave5b_stack_interaction import build, roundtrip

EXTRA = [
    card('Imoti, Celebrant of Bounty', set_code="tst", number="Y100", mana_cost='{1}{W}{U}', cmc=3.0, type_line='Legendary Creature — Human Cleric', oracle_text='Spells you cast with mana value 6 or greater have cascade.', power='2', toughness='2', colors=['W', 'U'], color_identity=['W', 'U']),  # noqa: E501
    card('Maelstrom Nexus', set_code="tst", number="Y101", mana_cost='{W}{U}{B}{R}{G}', cmc=5.0, type_line='Legendary Artifact', oracle_text='The first spell you cast each turn has cascade. (When you cast it, exile cards from the top of your library until you exile a nonland card that costs less. You may cast it without paying its mana cost. Put the exiled cards on the bottom in a random order.)', colors=['W', 'U', 'B', 'R', 'G'], color_identity=['W', 'U', 'B', 'R', 'G']),  # noqa: E501
    card('Wild-Magic Sorcerer', set_code="tst", number="Y102", mana_cost='{2}{R}', cmc=3.0, type_line='Creature — Human Sorcerer', oracle_text='The first spell you cast from exile each turn has cascade. (When you cast it, exile cards from the top of your library until you exile a nonland card that costs less. You may cast it without paying its mana cost. Put the exiled cards on the bottom in a random order.)', power='3', toughness='3', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Wildsear, Scouring Maw', set_code="tst", number="Y103", mana_cost='{3}{R}{G}', cmc=5.0, type_line='Legendary Creature — Dragon', oracle_text='Enchantment spells you cast from your hand have cascade. (When you cast one, exile cards from the top of your library until you exile a nonland card that costs less. You may cast it without paying its mana cost. Put the exiled cards on the bottom in a random order.)', power='4', toughness='4', colors=['R', 'G'], color_identity=['R', 'G']),  # noqa: E501
    card('The First Sliver', set_code="tst", number="Y104", mana_cost='{W}{U}{B}{R}{G}', cmc=5.0, type_line='Legendary Creature — Sliver', oracle_text="Cascade\nSliver spells you cast have cascade.", power='7', toughness='7', colors=['W', 'U', 'B', 'R', 'G'], color_identity=['W', 'U', 'B', 'R', 'G']),  # noqa: E501
    card('Zhulodok, Void Gorger', set_code="tst", number="Y105", mana_cost='{4}{C}{C}', cmc=6.0, type_line='Legendary Creature — Eldrazi Dragon', oracle_text='Flying\nColorless spells you cast from your hand with mana value 7 or greater have "Cascade, cascade."', power='7', toughness='5', color_identity=[]),  # noqa: E501
    card('Muscle Sliver', set_code="tst", number="Y106", mana_cost='{G}', cmc=1.0, type_line='Creature — Sliver', oracle_text='All Sliver creatures get +1/+1.', power='1', toughness='1', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Big Spender', set_code="tst", number="Y107", mana_cost='{5}{R}', cmc=6.0, type_line='Sorcery', oracle_text='You gain 1 life.', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Cheap Boon', set_code="tst", number="Y108", mana_cost='{G}', cmc=1.0, type_line='Enchantment', oracle_text='You gain 1 life.', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Act on Impulse', set_code="tst", number="Y111", mana_cost='{2}{R}', cmc=3.0, type_line='Sorcery', oracle_text='Exile the top three cards of your library. Until end of turn, you may play those cards.', colors=['R'], color_identity=['R']),  # noqa: E501
]
FULL = ["Imoti, Celebrant of Bounty", "Maelstrom Nexus", "Wild-Magic Sorcerer", "Wildsear, Scouring Maw", "The First Sliver",
        "Zhulodok, Void Gorger"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("text", [
    "Commander spells you cast have cascade.",  # (no commander-spell selector)
    "The first spell you cast each turn that mana from a Treasure was spent to cast has cascade.",
    "The first creature spell you cast each turn has cascade.",  # (a filter on the first spell: not read)
    "Spells you cast each turn have cascade.",
    "Spells you cast have demonstrate.",
])
def test_other_wordings_stay_manual(text):
    assert cast_limits.static_definition(text) is None


def field(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def cascades(s):
    """The cascade triggers on the stack."""
    return sum(1 for e in s.state.rules.stack.values()
               if e.kind == "trigger" and any(x.get("do") == "cascade" for x in e.effects))


def cast_and_count(s, c, **pay):
    mana(s, **pay)
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = s.state.rules.decision
    if d is not None:  # two cascade triggers of one controller: the order (603.3b) is asked
        assert d.kind == "order", d
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    return cascades(s)


def test_imoti_gives_cascade_to_spells_with_mana_value_6_or_more(cards):
    s = build(cards, p1=("Imoti, Celebrant of Bounty", "Big Spender", "Grizzly Bears"))
    field(s, "Imoti, Celebrant of Bounty")
    assert cast_and_count(s, to_hand(s, "Grizzly Bears"), G=2) == 0
    settle(s)
    assert cast_and_count(s, to_hand(s, "Big Spender"), R=1, C=5) == 1
    settle(s)
    roundtrip(s)


def test_a_cascade_spell_gets_one_more_instance_from_the_static(cards):
    """702.85b: each instance of cascade triggers separately."""
    s = build(cards, p1=("Maelstrom Nexus", "Bloodbraid Elf"))
    field(s, "Maelstrom Nexus")
    assert cast_and_count(s, to_hand(s, "Bloodbraid Elf"), R=1, G=1, C=2) == 2
    settle(s)
    roundtrip(s)


def test_cascade_from_exile_wordings():
    d = cast_limits.static_definition("The first spell you cast from exile each turn has cascade.")
    assert d is not None and d["first"] == "from" and d["from"] == "exile" and d["filter"] is None
    d = cast_limits.static_definition("Instant and sorcery spells you cast from your hand have cascade.")
    assert d is not None and d["first"] is None and d["from"] == "hand" and d["filter"] is not None


def test_maelstrom_nexus_first_spell_each_turn_only(cards):
    s = build(cards, p1=("Maelstrom Nexus", "Grizzly Bears", "Lightning Bolt"))
    field(s, "Maelstrom Nexus")
    assert cast_and_count(s, to_hand(s, "Grizzly Bears"), G=2) == 1
    settle(s)
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    assert cascades(s) == 0  # the second spell this turn
    settle(s)
    roundtrip(s)


def test_wildsear_enchantment_spells_from_hand(cards):
    s = build(cards, p1=("Wildsear, Scouring Maw", "Cheap Boon", "Grizzly Bears"))
    field(s, "Wildsear, Scouring Maw")
    assert cast_and_count(s, to_hand(s, "Grizzly Bears"), G=2) == 0
    settle(s)
    assert cast_and_count(s, to_hand(s, "Cheap Boon"), G=1) == 1
    settle(s)
    roundtrip(s)


def test_first_sliver_sliver_spells(cards):
    s = build(cards, p1=("The First Sliver", "Muscle Sliver", "Grizzly Bears"))
    field(s, "The First Sliver")
    assert cast_and_count(s, to_hand(s, "Muscle Sliver"), G=1) == 1
    settle(s)
    assert cast_and_count(s, to_hand(s, "Grizzly Bears"), G=2) == 0
    settle(s)
    roundtrip(s)


def test_wild_magic_sorcerer_first_spell_cast_from_exile_each_turn(cards):
    """Only a spell cast from exile cascades, and only the first one this turn (the impulse draw's cards are exiled)."""
    s = build(cards, p1=("Wild-Magic Sorcerer", "Act on Impulse", "Grizzly Bears", "Lightning Bolt", "Llanowar Elves"))
    field(s, "Wild-Magic Sorcerer")
    for name in ("Llanowar Elves", "Lightning Bolt", "Grizzly Bears"):  # (the top three, Bears first)
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p1")
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"}, position="top")
    impulse = to_hand(s, "Act on Impulse")
    assert cast_and_count(s, impulse, R=1, C=2) == 0  # cast from the hand
    settle(s)
    bears, bolt = (next(c for c in s.state.cards.values() if c.name == n and c.owner == "p1")
                   for n in ("Grizzly Bears", "Lightning Bolt"))
    assert bears.zone == bolt.zone == "p1:exile"
    assert cast_and_count(s, bears, G=2) == 1  # the first spell cast from exile
    settle(s)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    assert cascades(s) == 0  # the second
    settle(s)
    roundtrip(s)


def test_zhulodok_gives_two_instances_to_colorless_big_spells_from_hand(cards):
    d = cast_limits.static_definition('Colorless spells you cast from your hand with mana value 7 or greater have "Cascade, cascade."')
    assert d is not None and d["count"] == 2 and d["from"] == "hand" and d["filter"] is not None
