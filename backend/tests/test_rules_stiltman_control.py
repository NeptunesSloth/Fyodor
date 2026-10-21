"""CR 603.2c, 611.2a: stolen permanents gain a temporary sacrifice prohibition."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/stiltman_control_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Stilt-Man, Towering Terror'


def setup(cards):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Hobgoblin, Mantled Marauder', 'Krark-Clan Ironworks'],
              ['Sol Ring', 'Krark-Clan Ironworks', 'Grizzly Bears'], ['Sol Ring'])
    stilt = put(s, NAME, 'battlefield')
    villain = put(s, 'Hobgoblin, Mantled Marauder', 'battlefield')
    own_kci = put(s, 'Krark-Clan Ironworks', 'battlefield')
    their_kci = put(s, 'Krark-Clan Ironworks', 'battlefield', 'p2')
    prize = put(s, 'Sol Ring', 'battlefield', 'p2')
    other = put(s, 'Sol Ring', 'battlefield', 'p3')
    creature = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    land = put(s, 'Island', 'battlefield', 'p2')
    return s, stilt, villain, own_kci, their_kci, prize, other, creature, land


def hit_and_steal(s, attackers, prize, forbidden):
    from tests.game_helpers import act
    from tests.test_rules_banding import declare_only
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import roundtrip

    declare_only(s, attackers, [])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get('step') == 'trigger_target')
    d = s.state.rules.decision
    assert prize.id in {o.id for o in d.options}
    assert not ({c.id for c in forbidden} & {o.id for o in d.options})
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[prize.id])
    settle(s)
    assert s.state.cards[prize.id].controller == 'p1'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_stiltman_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('source_leaves', [False, True])
def test_stolen_permanent_cannot_be_sacrificed_until_control_and_grant_expire(cards, source_leaves):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, stilt, villain, own_kci, their_kci, prize, other, creature, land = setup(cards)
    hit_and_steal(s, [stilt, villain], prize, [other, creature, land])
    if source_leaves:
        act(s, 'p1', type='move', card_ids=[stilt.id], to={'player': 'p1', 'zone': 'graveyard'})
    wait_priority(s, 'p1')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=own_kci.id, ability=0,
            cost_choices=[{'component': 0, 'cards': [prize.id]}])
    assert s.state.model_dump_json() == before
    to_phase(s, 'end', turn=7)
    assert s.state.cards[prize.id].controller == 'p1'
    to_phase(s, 'main1', turn=8)
    assert s.state.cards[prize.id].controller == 'p2'
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=their_kci.id, ability=0,
        cost_choices=[{'component': 0, 'cards': [prize.id]}])
    settle(s)
    assert s.state.cards[prize.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_two_villains_hitting_same_player_trigger_once(cards):
    s, stilt, villain, _, _, prize, other, creature, land = setup(cards)
    hit_and_steal(s, [stilt, villain], prize, [other, creature, land])
    # A second simultaneous source must not cause another steal of the Ironworks.
    assert sum(c.owner == 'p2' and c.controller == 'p1' for c in s.state.cards.values()) == 1
