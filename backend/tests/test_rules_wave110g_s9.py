"""Wave 110G session 9: cards that need a cause on zone changes or a new prohibition.

* Sacred Ground: 603.2 / 704.3 an opponent's resolving spell or ability that puts a land into your graveyard returns it; your own spell and state-based actions do not.
* Whippoorwill: 701.19c / 615.12 / 614.9 / 700.4 the creature can't regenerate, its damage can't be prevented or dealt instead to another permanent, and it is exiled if it dies.
"""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build
from tests.wave110b_kit import cast, check, mana, put

EXTRA = [
    real("Sacred Ground", "{1}{W}", 2, "Enchantment", "Whenever a spell or ability an opponent controls causes a land to be put into your graveyard from the battlefield, return that card to the battlefield.", None, "W"),
    real("Stone Rain", "{2}{R}", 3, "Sorcery", "Destroy target land.", None, "R"),
    real("Dryad Arbor", "", 0, "Land Creature — Forest Dryad", "(This land isn't a spell, it's affected by summoning sickness, and it has \"{T}: Add {G}.\")", ("1", "1"), "G"),
]
EXTRA += [
    real("Whippoorwill", "{G}", 1, "Creature \u2014 Bird", "{G}{G}, {T}: Target creature can't be regenerated this turn. Damage that would be dealt to that creature this turn can't be "
         "prevented or dealt instead to another permanent or player. When the creature dies this turn, exile the creature.", ("1", "1"), "G"),
    real("Carom", "{1}{W}", 2, "Instant", "The next 1 damage that would be dealt to target creature this turn is dealt to another target creature instead.\nDraw a card.", None, "W"),
    real("Hill Giant", "{3}{R}", 4, "Creature \u2014 Giant", "", ("3", "3"), "R"),
]
NAMES = [c["name"] for c in EXTRA if c["name"] not in ("Stone Rain", "Carom", "Hill Giant")]


def answer(s, limit=60):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("owner_casts, back", [(False, True), (True, False)])
def test_sacred_ground_returns_a_land_only_when_an_opponents_spell_caused_it(cards, owner_casts, back):
    """Sacred Ground: Stone Rain from the opponent returns your land; your own Stone Rain on it does not."""
    s = build(cards, ["Stone Rain", "Sacred Ground"], ["Sacred Ground"])
    you = "p1" if owner_casts else "p2"
    put(s, "Sacred Ground", you)
    land = put(s, "Forest") if owner_casts else put(s, "Island", "p2")
    mana(s, "p1", C=1, R=1, G=1)
    cast(s, "Stone Rain", [land.id])
    assert s.state.cards[land.id].zone == f"{you}:{'battlefield' if back else 'graveyard'}"
    check(s)


def test_sacred_ground_ignores_a_land_that_dies_to_state_based_damage(cards):
    """Sacred Ground (704.5g): the land creature dies to lethal damage, a state-based action, not as a spell or ability puts it there."""
    s = build(cards, ["Lightning Bolt"], ["Sacred Ground", "Dryad Arbor"])
    put(s, "Sacred Ground", "p2")
    arbor = put(s, "Dryad Arbor", "p2")
    mana(s, "p1", R=1)
    cast(s, "Lightning Bolt", [arbor.id])
    assert s.state.cards[arbor.id].zone == "p2:graveyard"
    check(s)


@pytest.mark.parametrize("firm", [True, False])
def test_whippoorwill_damage_ignores_carom_and_the_creature_is_exiled(cards, firm):
    """Whippoorwill: with it, Bolt's 3 damage stays on the Giant (Carom can't redirect it) and the dead Giant is exiled; without it Carom moves 1."""
    s = build(cards, ["Whippoorwill", "Carom", "Lightning Bolt", "Hill Giant", "Grizzly Bears"])
    from tests.test_rules_conditionals import until

    giant, bears, bird = (put(s, n) for n in ("Hill Giant", "Grizzly Bears", "Whippoorwill"))
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # past summoning sickness
    if firm:
        mana(s, "p1", G=2)
        act(s, "p1", type="activate_ability", card_id=bird.id, ability=0, targets=[giant.id])
        answer(s)
    mana(s, "p1", W=1, C=1, R=1)
    cast(s, "Carom", [giant.id, bears.id], target_counts=[1, 1])
    answer(s)
    cast(s, "Lightning Bolt", [giant.id])
    answer(s)
    got = s.state.cards
    if firm:
        assert got[giant.id].zone == "p1:exile" and got[bears.id].damage == 0
    else:
        assert (got[giant.id].damage, got[bears.id].damage) == (2, 1)
    check(s)
