"""Food Chain: selected exile costs and battlefield mana-value snapshots."""
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
from tests.test_rules_designations import roundtrip
from tests.wave9c_kit import build, put


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/food_chain_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




def setup(cards):
    s = build(cards, ['Food Chain', 'Grizzly Bears', 'Sun Titan', 'Phantasmal Image', 'Sagu Mauler', 'Lightning Bolt', 'Opalescence', 'Wolfbriar Elemental', 'March of the Machines', "Ashnod's Altar"])
    source = put(s, 'Food Chain')
    return s, source


def units(s):
    return s.state.players['p1'].mana_units


def activate(s, source, victim, color=None):
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0,
        cost_choices=[{'component': 0, 'cards': [victim.id]}],
        **({'mana_choice': color} if color else {}))


def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Food Chain')).level == 'FULL'


@pytest.mark.parametrize('color', ['W', 'U', 'B', 'R', 'G'])
def test_exact_single_color_and_creature_only_restriction(cards, color):
    s, source = setup(cards)
    victim = put(s, 'Grizzly Bears')
    activate(s, source, victim, color)
    assert s.state.cards[victim.id].zone == 'p1:exile'
    assert len(units(s)) == 3
    assert {u.sym for u in units(s)} == {color}
    assert {u.only for u in units(s)} == {'creature'}
    assert not s.state.zones.get("stack")
    roundtrip(s)


def test_cost_paid_before_color_choice_and_saved_prompt(cards):
    s, source = setup(cards)
    victim = put(s, 'Sun Titan')
    activate(s, source, victim)
    d = s.state.rules.decision
    assert d and d.resume.get('paid') is True
    assert s.state.cards[victim.id].zone == 'p1:exile'
    assert len(d.options) == 5
    assert not units(s)
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == '{B}{B}{B}{B}{B}{B}{B}')])
    assert len(units(s)) == 7
    roundtrip(s)


def test_face_down_uses_battlefield_zero_not_exiled_printing(cards):
    s, source = setup(cards)
    victim = put(s, 'Sagu Mauler')
    act(s, 'p1', type='face_down', card_ids=[victim.id], face_down=True, kind='manifest')
    activate(s, source, victim, 'G')
    assert len(units(s)) == 1
    roundtrip(s)


def test_zero_mana_value_token_is_a_valid_exile_cost(cards):
    from tests.test_rules_conditionals import creature
    s, source = setup(cards)
    victim = creature(s, 'p1', 'Soldier')
    activate(s, source, victim, 'W')
    assert victim.id not in s.state.cards
    assert len(units(s)) == 1
    roundtrip(s)


def test_copy_uses_copied_mana_value_and_cost_does_not_target(cards):
    from tests.test_rules_copy import cast_clone
    from tests.test_rules_designations import settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, source = setup(cards)
    titan = put(s, 'Sun Titan')
    image = cast_clone(s, name='Phantasmal Image', pick=titan.id, U=1, C=1)
    settle(s)
    assert chars(s, image).mana_value == 6
    activate(s, source, image, 'R')
    assert len(units(s)) == 7
    assert s.state.cards[image.id].zone == 'p1:exile'
    roundtrip(s)


def test_copied_token_uses_copied_mana_cost(cards):
    s, source = setup(cards)
    titan = put(s, 'Sun Titan')
    before = set(s.state.cards)
    act(s, 'p1', type='copy_card', card_id=titan.id, player='p1', count=1)
    victim = next(c for cid, c in s.state.cards.items() if cid not in before)
    activate(s, source, victim, 'U')
    assert victim.id not in s.state.cards
    assert len(units(s)) == 7
    roundtrip(s)


def test_nested_activation_pays_creature_spell_from_saved_color_prompt(cards):
    from tests.test_rules_conditionals import pick
    from tests.test_rules_wave28d_nested_mana import self_payment
    from tests.wave9c_kit import reloaded, to_hand
    s, source = setup(cards)
    victim = put(s, 'Sun Titan')
    spell = to_hand(s, 'Grizzly Bears')
    put(s, 'Sagu Mauler')
    self_payment(s)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    roundtrip(s)
    pick(s, victim.id)
    assert s.state.rules.payment_outer is not None
    assert s.state.rules.decision.resume.get('paid') is True
    roundtrip(s)
    restored = reloaded(s)
    for game in (s, restored):
        d = game.state.rules.decision
        pick(game, next(o.id for o in d.options if o.label == '{G}' * 7))
        assert game.state.rules.payment_outer is None
        assert game.state.cards[spell.id].zone != 'p1:hand'
        assert len(units(game)) == 5
        roundtrip(game)


def test_creature_restricted_mana_cannot_cast_noncreature(cards):
    from app.game.errors import ActionError
    from tests.wave9c_kit import to_hand
    s, source = setup(cards)
    victim = put(s, 'Grizzly Bears')
    activate(s, source, victim, 'R')
    spell = to_hand(s, 'Lightning Bolt')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    assert len(units(s)) == 3
    assert s.state.cards[spell.id].zone == 'p1:hand'
    roundtrip(s)


def test_cancel_cost_does_not_exile_creature(cards):
    from tests.test_rules_conditionals import pick
    s, source = setup(cards)
    victim = put(s, 'Grizzly Bears')
    put(s, 'Sun Titan')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    d = s.state.rules.decision
    assert d and d.kind == 'choose_cards'
    roundtrip(s)
    pick(s)
    assert s.state.cards[victim.id].zone == 'p1:battlefield'
    assert not units(s)
    roundtrip(s)


def test_colorless_cannot_be_selected(cards):
    from app.game.errors import ActionError
    s, source = setup(cards)
    victim = put(s, 'Grizzly Bears')
    with pytest.raises(ActionError):
        activate(s, source, victim, 'C')
    assert s.state.cards[victim.id].zone == 'p1:battlefield'
    assert not units(s)
    roundtrip(s)


def test_animated_food_chain_can_exile_itself_and_keep_restriction(cards):
    from tests.test_rules_conditionals import pick
    s, source = setup(cards)
    put(s, 'Opalescence')
    from app.rules.plan import Plan
    old = Plan(s.state, 'p1', cards, None).oid(source)
    activate(s, source, source)
    assert s.state.cards[source.id].zone == 'p1:exile'
    roundtrip(s)
    d = s.state.rules.decision
    pick(s, next(o.id for o in d.options if o.label == '{G}' * 4))
    assert len(units(s)) == 4
    assert {u.only for u in units(s)} == {'creature'}
    assert {u.src for u in units(s)} == {old}
    assert all('Creature' in u.tags and 'Enchantment' in u.tags for u in units(s))
    snap = s.state.rules.lki[old]
    assert snap.controller == snap.owner == 'p1'
    assert snap.traits['colors'] == ['G']
    roundtrip(s)


def test_restricted_mana_pays_creature_multikicker_additional_cost(cards):
    from tests.test_rules_designations import settle
    from tests.wave9c_kit import to_hand
    s, source = setup(cards)
    victim = put(s, 'Sun Titan')
    activate(s, source, victim, 'G')
    spell = to_hand(s, 'Wolfbriar Elemental')
    before = set(s.state.cards)
    act(s, 'p1', type='cast_spell', card_id=spell.id, kicker=3)
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    wolves = [c for cid, c in s.state.cards.items() if cid not in before and c.name == 'Wolf']
    assert len(wolves) == 3
    assert not units(s)
    roundtrip(s)


def test_animated_altar_sacrificing_itself_keeps_original_source_traits(cards):
    from app.rules.plan import Plan
    s, _ = setup(cards)
    source = put(s, "Ashnod's Altar")
    put(s, 'March of the Machines')
    old = Plan(s.state, 'p1', cards, None).oid(source)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0,
        cost_choices=[{'component': 0, 'cards': [source.id]}])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert len(units(s)) == 2
    assert {u.src for u in units(s)} == {old}
    assert all('Creature' in u.tags and 'Artifact' in u.tags for u in units(s))
    snap = s.state.rules.lki[old]
    assert snap.controller == snap.owner == 'p1'
    roundtrip(s)
