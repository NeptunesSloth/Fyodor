"""CR 110.4: count six distinct permanent types, not all card types or number of cards."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards

DATA = json.loads((Path(__file__).parent / 'fixtures/permanent_type_count_cards.json').read_text())
NAME = 'Matzalantli, the Great Door // The Core'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='ptc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, graveyard=()):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [c['name'] for c in DATA], [c['name'] for c in DATA])
    source = put(s, NAME, 'battlefield')
    for name in graveyard:
        put(s, cards.resolve(name)['name'], 'graveyard')
    return s, source


def finish(s):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    settle(s)
    roundtrip(s)


def test_real_oracle_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('names,number', [([], 0), (['Great Furnace'], 2),
                                        (['Great Furnace', 'Eidolon of Blossoms'], 4),
                                        (['Great Furnace', 'Sol Ring'], 2),
                                        (['Invasion of Zendikar'], 1),
                                        (['Forest', 'Island'], 1),
                                        (['Dryad Arbor', "Urza's Saga"], 3),
                                        (['Bitterblossom', 'Nameless Inversion', 'All Is Dust'], 1),
                                        (['Invasion of Zendikar', 'Jace Beleren', 'Grizzly Bears', 'Forest'], 4)])
def test_distinct_permanent_types_in_graveyard(cards, names, number):
    from app.rules import values
    from app.rules.plan import Plan
    from tests.test_rules_designations import roundtrip

    s, _ = setup(cards, names)
    parsed = values.parse_count('the number of permanent types among cards in your graveyard')
    assert parsed is not None
    assert values.evaluate(Plan.view(s.state, 'p1', s.cards), {'controller': 'p1'}, parsed) == number
    roundtrip(s)


def test_four_permanent_types_in_two_cards_allow_transform_but_do_not_untap(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana

    s, source = setup(cards, ['Great Furnace', 'Eidolon of Blossoms'])
    mana(s, C=4)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    finish(s)
    assert s.state.cards[source.id].face == 1 and s.state.cards[source.id].tapped
    assert not any(s.state.players['p1'].mana.values())


def test_instant_sorcery_and_kindred_do_not_satisfy_four_permanent_types(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    s, source = setup(cards, ['Bitterblossom', 'Nameless Inversion', 'All Is Dust'])
    mana(s, C=4)
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert s.state.cards[source.id].face == 0 and not s.state.cards[source.id].tapped
    assert s.state.players['p1'].mana == {'C': 4}
    roundtrip(s)


def test_core_counts_permanent_cards_not_distinct_permanent_types(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put

    s, source = setup(cards, ['Great Furnace', 'Eidolon of Blossoms', 'Nameless Inversion', 'All Is Dust'])
    mana(s, C=4)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    finish(s)
    wait_priority(s, 'p1')
    twiddle = put(s, 'Twiddle', 'hand')
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=twiddle.id, targets=[source.id])
    # Twiddle's optional untap choice is selected explicitly when present.
    from tests.test_rules_designations import settle

    settle(s)
    if (d := s.state.rules.decision) is not None:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['untap'])
    finish(s)
    assert not s.state.cards[source.id].tapped
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    d = s.state.rules.decision
    option = next(o.id for o in d.options if o.label == '{G}{G}')
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[option])
    from collections import Counter

    available = Counter(s.state.players['p1'].mana)
    available.update(unit.sym for unit in s.state.players['p1'].mana_units)
    assert available == {'G': 2}
    assert not s.state.rules.stack
    finish(s)


def test_activation_condition_is_not_rechecked_after_graveyard_is_exiled(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put

    s, source = setup(cards, ['Great Furnace', 'Eidolon of Blossoms'])
    crypt = put(s, "Tormod's Crypt", 'battlefield', pid='p2')
    mana(s, C=4)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=crypt.id, ability=0, targets=['p1'])
    finish(s)
    assert not s.state.zones.get('p1:graveyard')
    assert s.state.cards[source.id].face == 1 and s.state.cards[source.id].tapped


def test_other_graveyards_and_source_on_battlefield_do_not_add_types(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip

    s, source = setup(cards, ['Dryad Arbor', "Urza's Saga"])
    put(s, 'Sol Ring', 'graveyard', pid='p2')
    # The source is an artifact on the battlefield, and Bob's graveyard has an artifact;
    # Alice's graveyard nevertheless contains only land, creature, and enchantment.
    mana(s, C=4)
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert not s.state.cards[source.id].tapped
    assert s.state.players['p1'].mana == {'C': 4}
    roundtrip(s)


def test_loot_ability_does_not_require_four_permanent_types(cards):
    from tests.game_helpers import act

    s, source = setup(cards)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    finish(s)
    assert s.state.cards[source.id].face == 0 and s.state.cards[source.id].tapped
    assert len(s.state.zones['p1:hand']) == before
    assert len(s.state.zones['p1:graveyard']) == 1


def test_new_controller_uses_their_graveyard_not_the_owners(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip

    s, source = setup(cards, ['Great Furnace', 'Eidolon of Blossoms'])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', C=4)
    with pytest.raises(ActionError):
        act(s, 'p2', type='activate_ability', card_id=source.id, ability=1)
    assert not s.state.cards[source.id].tapped
    assert s.state.players['p2'].mana == {'C': 4}
    roundtrip(s)
    put(s, 'Great Furnace', 'graveyard', pid='p2')
    put(s, 'Eidolon of Blossoms', 'graveyard', pid='p2')
    act(s, 'p2', type='activate_ability', card_id=source.id, ability=1)
    finish(s)
    assert s.state.cards[source.id].face == 1 and s.state.cards[source.id].controller == 'p2'
    assert not any(s.state.players['p2'].mana.values())
