"""Wave 27C: "up to X target …, where X is <a count>" (CR 107.3c, 601.2c): the number of targets is that count as the targets are chosen."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, put

REAL = [
    ("Recantation", "{2}{U}{U}", "Enchantment", None, None,
     "At the beginning of your upkeep, you may put a verse counter on this enchantment.\n"
     "{U}, Sacrifice this enchantment: Return up to X target permanents to their owners' hands, where X is the number of verse counters on this enchantment."),
    ("Marshal's Anthem", "{1}{W}{W}", "Enchantment", None, None,
     "Multikicker {1}{W} (You may pay an additional {1}{W} any number of times as you cast this spell.)\nCreatures you control get +1/+1.\n"
     "When this enchantment enters, return up to X target creature cards from your graveyard to the battlefield, where X is the number of times this enchantment was kicked."),
    ("Endurance Bobblehead", "{3}", "Artifact — Bobblehead", None, None,
     "{T}: Add one mana of any color.\n{3}, {T}: Up to X target creatures you control get +1/+0 and gain indestructible until end of turn, where X is the "
     "number of Bobbleheads you control as you activate this ability. Activate only as a sorcery."),
]
EXTRA = [card(n, set_code="t27c", number=f"T{i:02d}", mana_cost=mc, cmc=4.0, type_line=tl, oracle_text=text)
         for i, (n, mc, tl, p, t, text) in enumerate(REAL)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Recantation", "Endurance Bobblehead"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_bobblehead_one_bobblehead_allows_one_target(cards):
    s = build(cards, ["Endurance Bobblehead"])
    put(s, "Endurance Bobblehead")
    a, b = creature(s, "p1", "Bear A"), creature(s, "p1", "Bear B")
    from tests.wave9c_kit import mana

    mana(s, C=3)
    index = 1
    with pytest.raises(ActionError):  # (X = 1 Bobblehead: two targets are too many)
        act(s, "p1", type="activate_ability", card_id=card_named(s, "Endurance Bobblehead").id, ability=index,
            targets=[a.id, b.id], target_counts=[2])
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Endurance Bobblehead").id, ability=index, targets=[a.id], target_counts=[1])
    answer(s)
    check(s)


def test_recantation_counts_its_verse_counters_though_it_is_sacrificed(cards):
    from tests.wave9c_kit import mana

    s = build(cards, ["Recantation"])
    put(s, "Recantation")
    a, b, c = (creature(s, "p2", n) for n in ("Bear A", "Bear B", "Bear C"))
    act(s, "p1", type="counter", card_ids=[card_named(s, "Recantation").id], kind="verse", delta=2)
    mana(s, U=1)
    rec = card_named(s, "Recantation").id
    with pytest.raises(ActionError):  # (two verse counters: three targets are too many)
        act(s, "p1", type="activate_ability", card_id=rec, ability=1, targets=[a.id, b.id, c.id], target_counts=[3])
    act(s, "p1", type="activate_ability", card_id=rec, ability=1, targets=[a.id, b.id], target_counts=[2])
    answer(s)
    check(s)


@pytest.mark.parametrize("kicks", [0, 1])
def test_marshals_anthem_trigger_counts_its_kicks(cards, kicks):
    from tests.wave9c_kit import mana, to_hand

    s = build(cards, ["Marshal's Anthem", "Llanowar Elves"])
    act(s, "p1", type="move", card_ids=[card_named(s, "Llanowar Elves").id], to={"zone": "graveyard"})
    spell = to_hand(s, "Marshal's Anthem")
    mana(s, W=6)
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=kicks)
    from tests.test_rules_conditionals import until_asked

    d = until_asked(s)
    if kicks:  # (X = 1: one of the creature cards may be chosen)
        assert d is not None and d.max_choices == 1
    else:  # (X = 0: no targets, nothing to choose)
        assert d is None
    check(s)
