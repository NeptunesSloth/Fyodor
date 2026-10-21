"""CR 608.2f, 701.14: captured creatures and simultaneous one-to-one fights."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/token_fight_pairs_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




NAME = "Ezuri's Predation"


def setup(cards, *, opponents=('Grizzly Bears', 'Colossal Dreadmaw'), modifiers=()):
    s = table(cards, [NAME, 'Soul Warden', *modifiers], ['Grizzly Bears', 'Colossal Dreadmaw',
                    'Slippery Bogle', 'Mirran Crusader', 'Vampire Nighthawk', 'Vigor'])
    for name in modifiers:
        put(s, name, 'battlefield')
    prey = [put(s, name, 'battlefield', 'p2') for name in opponents]
    return s, prey


def cast(s):
    source = put(s, NAME, 'hand')
    mana(s, C=5, G=3)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    return source


def choose(s, selected):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=selected)
    settle(s)


def assign(s, *, last=False):
    pairs = []
    while (d := s.state.rules.decision) is not None and d.resume.get('step') == 'token_fight_pairs':
        assert d.resume['stage'] == 'fighter'
        token = d.options[-1 if last else 0].id
        pairs.append((token, d.resume['victim']))
        choose(s, [token])
    return pairs


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_zero_opposing_creatures_creates_nothing(cards):
    s, _ = setup(cards, opponents=())
    cast(s)
    assert not any(c.name == 'Phyrexian Beast' for c in s.state.cards.values())
    assert s.state.rules.decision is None
    roundtrip(s)


def test_creates_one_per_opposing_creature_and_fights_simultaneously(cards):
    s, prey = setup(cards)
    warden = put(s, 'Soul Warden', 'battlefield')
    cast(s)
    assert s.state.players['p1'].life == 40  # entry triggers wait until all fights finish
    assert warden.id in s.state.cards
    assert len(s.state.rules.decision.options) == 2  # own Warden was not counted
    made = [c.id for c in s.state.cards.values() if c.name == 'Phyrexian Beast']
    assert len(made) == 2
    pairs = assign(s, last=True)
    assert len(pairs) == 2
    assert s.state.cards[prey[0].id].zone == 'p2:graveyard'
    assert s.state.cards[prey[1].id].zone == 'p2:battlefield'
    assert s.state.cards[prey[1].id].damage == 4
    assert sum(cid in s.state.cards for cid in made) == 1
    assert s.state.players['p1'].life == 42
    # A single shared simultaneous damage batch, including both directions of both fights.
    damage = [f for f in s.state.rules.turn_log.facts if f.kind == 'damaged']
    assert len(damage) == 4
    assert len({f.batch for f in damage}) == 1
    roundtrip(s)


@pytest.mark.parametrize('modifier,created', [('Doubling Season', 'Phyrexian Beast'), ('Divine Visitation', 'Angel')])
def test_replacements_change_tokens_without_extra_fights(cards, modifier, created):
    s, prey = setup(cards, opponents=('Grizzly Bears',), modifiers=(modifier,))
    cast(s)
    made = [c.id for c in s.state.cards.values() if c.name == created]
    assert len(made) == (2 if modifier == 'Doubling Season' else 1)
    pairs = assign(s, last=True)
    assert len(pairs) == 1 and pairs[0][0] == made[-1]
    assert s.state.cards[prey[0].id].zone == 'p2:graveyard'
    assert sum(s.state.cards[cid].damage > 0 for cid in made) == 1
    roundtrip(s)


def test_hexproof_does_not_prevent_untargeted_fight_and_protection_prevents_damage(cards):
    s, prey = setup(cards, opponents=('Slippery Bogle', 'Mirran Crusader'))
    cast(s)
    pairs = assign(s)
    assert len(pairs) == 2
    assert s.state.cards[prey[0].id].zone == 'p2:graveyard'
    assert s.state.cards[prey[1].id].zone == 'p2:battlefield'
    assert s.state.cards[prey[1].id].damage == 0
    roundtrip(s)


def test_deathtouch_and_lifelink_are_read_from_actual_fight_source(cards):
    s, prey = setup(cards, opponents=('Vampire Nighthawk',))
    cast(s)
    made = [c.id for c in s.state.cards.values() if c.name == 'Phyrexian Beast']
    assign(s)
    assert made[0] not in s.state.cards
    assert s.state.cards[prey[0].id].zone == 'p2:graveyard'
    assert s.state.players['p2'].life == 42
    roundtrip(s)


def test_creation_replacement_order_resumes_before_pair_choices(cards):
    s, prey = setup(cards, opponents=('Grizzly Bears',), modifiers=('Divine Visitation', 'Chatterfang, Squirrel General'))
    cast(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'replace_order'
    assert not any(c.name == 'Angel' for c in s.state.cards.values())
    option = next(o.id for o in d.options if o.label.startswith('Divine Visitation first'))
    choose(s, [option])
    assert sorted(c.name for c in s.state.cards.values() if c.is_token) == ['Angel', 'Squirrel']
    d = s.state.rules.decision
    squirrel = next(o.id for o in d.options if o.label == 'Squirrel')
    choose(s, [squirrel])
    # Exactly one fight, even though replacement made an additional creature token.
    assert s.state.cards[prey[0].id].zone == 'p2:battlefield'
    assert s.state.cards[prey[0].id].damage == 1
    assert any(c.name == 'Angel' and c.damage == 0 for c in s.state.cards.values())
    roundtrip(s)


def test_duplicate_assignment_is_rejected_before_any_damage(cards):
    s, _ = setup(cards)
    cast(s)
    d = s.state.rules.decision
    first = d.options[0].id
    choose(s, [first])
    d = s.state.rules.decision
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[first])
    assert s.state.model_dump(mode='json') == before
    assert all(c.damage == 0 for c in s.state.cards.values())
    assign(s)
    roundtrip(s)


def test_multiple_opponents_are_captured_before_creation(cards):
    s, prey = setup(cards, opponents=('Grizzly Bears',))
    other = put(s, 'Atraxa, Praetors\' Voice', 'battlefield', 'p3')
    cast(s)
    assert len(s.state.rules.decision.options) == 2
    pairs = assign(s)
    assert {b for _, b in pairs} == {prey[0].id, other.id}
    assert s.state.cards[prey[0].id].zone == 'p2:graveyard'
    roundtrip(s)


def test_damage_replacement_choice_keeps_pairs_and_entire_damage_batch_pending(cards):
    s, prey = setup(cards, opponents=('Vigor', 'Grizzly Bears'), modifiers=('Furnace of Rath',))
    cast(s)
    made = [c.id for c in s.state.cards.values() if c.name == 'Phyrexian Beast']
    assign(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'replace_order'
    # The affected player orders prevention versus damage doubling. No partial fight committed.
    assert d.player == 'p2'
    assert all(c.damage == 0 for c in s.state.cards.values())
    assert all(not c.counters for c in s.state.cards.values())
    roundtrip(s)
    option = next(o.id for o in d.options if o.label.startswith('Furnace of Rath first'))
    choose(s, [option])
    assert s.state.rules.decision is None
    assert s.state.cards[prey[1].id].counters.get('+1/+1') == 8
    assert all(cid not in s.state.cards for cid in made)
    roundtrip(s)
