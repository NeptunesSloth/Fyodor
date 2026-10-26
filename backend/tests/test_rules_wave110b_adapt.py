"""Wave 110B: Biomancer's Familiar (701.46a adapt, 614.5 one-shot, 602.5 tap ability)."""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import build, check, mana, put, settle

FAMILIAR = ("Activated abilities of creatures you control cost {2} less to activate. This effect can't reduce the mana in that cost to less than one mana.\n"
            "{T}: The next time target creature adapts this turn, it adapts as though it had no +1/+1 counters on it.")
ADAPTER = "{G}: Adapt 2. (If this creature has no +1/+1 counters on it, put two +1/+1 counters on it.)"


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository
    from tests.fixtures.cards import fixture_cards
    from tests.test_rules_wave12a_counters_keywords import real

    settings.ensure_dirs()
    extra = [real("Biomancer's Familiar", "{1}{G}{U}", 3, "Creature — Elf Wizard", FAMILIAR, ("2", "2"), "GU"),
             real("Test Adapter", "{2}{G}", 3, "Creature — Lizard", ADAPTER, ("1", "1"), "G")]
    build_database([*fixture_cards(), *extra], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def counters(s, c):
    return s.state.cards[c.id].counters.get("+1/+1", 0)


def adapt(s, adapter):
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=adapter.id, ability=0)
    settle(s)


def game(cards, familiar, start):
    s = build(cards, ["Biomancer's Familiar", "Test Adapter"], [], forests=30)
    adapter = put(s, "Test Adapter")
    if start:
        act(s, "p1", type="counter", card_ids=[adapter.id], kind="+1/+1", delta=start)
    if familiar:
        fam = put(s, "Biomancer's Familiar")
        s.state.rules.controlled_since[fam.id].turn = 0
        act(s, "p1", type="activate_ability", card_id=fam.id, ability=1, targets=[adapter.id])
        settle(s)
    return s, adapter


def test_adapt_ignores_existing_counters_once(cards):
    """701.46a: with the Familiar's effect the adapter that has two +1/+1 counters gets two more; the next adapt (effect used up) does nothing."""
    assert coverage.of_card_data(cards.resolve("Biomancer's Familiar")).level == "FULL"
    s, adapter = game(cards, True, 2)
    adapt(s, adapter)
    assert counters(s, adapter) == 4
    adapt(s, adapter)
    assert counters(s, adapter) == 4
    check(s)


@pytest.mark.parametrize("familiar,start,after", [(False, 2, 2), (False, 0, 2), (True, 0, 2)])
def test_adapt_otherwise_as_printed(cards, familiar, start, after):
    """Without the effect a creature with counters stays as it is; without counters it gets two; the effect is used up by an adapt that would have worked anyway."""
    s, adapter = game(cards, familiar, start)
    adapt(s, adapter)
    assert counters(s, adapter) == after
    if familiar:
        adapt(s, adapter)
        assert counters(s, adapter) == 2  # the effect was used up by the first adapt
    check(s)
