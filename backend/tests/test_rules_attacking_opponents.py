"""CR 506.3 / 608.2c: creatures attacking opponents or their planeswalkers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/attacking_opponents_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_roar_of_resistance_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Roar of Resistance')).level == 'FULL'


@pytest.mark.parametrize('defender', ['player', 'planeswalker'])
@pytest.mark.parametrize('pay', [False, True])
def test_roar_can_pump_other_players_attackers_but_only_at_opponents_or_their_walkers(cards, defender, pay):
    from app.rules.plan import Plan
    from tests.test_rules_conditionals import until

    s = table(cards, ['Roar of Resistance', 'Jace Beleren', 'Llanowar Elves'],
              ['Grizzly Bears', 'Runeclaw Bear', 'Llanowar Elves'], ['Jace Beleren'])
    put(s, 'Roar of Resistance', 'battlefield')
    mine = put(s, 'Llanowar Elves', 'battlefield')
    my_walker = put(s, 'Jace Beleren', 'battlefield')
    their_walker = put(s, 'Jace Beleren', 'battlefield', 'p3')
    for walker in [my_walker, their_walker]:
        act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=3)
    at_me = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    at_my_walker = put(s, 'Runeclaw Bear', 'battlefield', 'p2')
    at_opponent = put(s, 'Llanowar Elves', 'battlefield', 'p2')
    until(s, lambda s: s.state.turn.number == 2 and s.state.rules.decision is not None
          and s.state.rules.decision.kind == 'declare_attackers')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'R': 1})
    act(s, 'p2', type='declare_attackers', attackers=[
        {'card_id': at_me.id, 'target': 'p1'}, {'card_id': at_my_walker.id, 'target': my_walker.id},
        {'card_id': at_opponent.id, 'target': 'p3' if defender == 'player' else their_walker.id}])
    assert len(s.state.zones['stack']) == 1
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay' if pay else 'decline'])
    settle(s)
    def ch(c):
        return Plan(s.state, 'p1', cards, None).ch(s.state.cards[c.id])
    assert ch(at_opponent).pt == ((3, 1) if pay else (1, 1))
    assert ch(at_me).pt == (2, 2) and ch(at_my_walker).pt == (2, 2) and ch(mine).pt == (1, 1)
    assert not s.state.zones['stack']
    roundtrip(s)


def test_roar_grants_haste_only_to_its_controllers_creature_tokens(cards):
    from app.rules.plan import Plan
    from tests.test_rules_wave5j_token_copies import token

    s = table(cards, ['Roar of Resistance', 'Grizzly Bears'], ['Grizzly Bears'])
    put(s, 'Roar of Resistance', 'battlefield')
    mine = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    made = token(s, 'p1', 'Bear')
    for c, expected in [(mine, False), (other, False), (made, True)]:
        assert ('haste' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[c.id]).keywords) == expected
    roundtrip(s)
