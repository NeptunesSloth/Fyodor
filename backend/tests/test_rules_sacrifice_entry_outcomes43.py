"""Canonical Shilgengar direct-sacrifice LKI and simultaneous native entry proofs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_linked_aggregates import activate, cast
from tests.test_rules_shared_damage_choices import table

NAME = 'Shilgengar, Sire of Famine'
DATA = json.loads((Path(__file__).parent / 'fixtures/sacrifice_entry_outcomes43_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='seo', number=str(i), **{('card_faces' if k == 'faces' else k): v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def scene(cards):
    names = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Lightning Bolt']
    s = table(cards, names, names, names)
    source = put(s, NAME, 'hand')
    cast(s, source)
    settle(s)
    assert 'flying' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).keywords
    return s, source


def bloods(s):
    p = Plan(s.state, 'p1', s.cards, None)
    return [c for c in s.state.cards.values() if c.zone == 'p1:battlefield' and c.is_token and 'Blood' in p.ch(c).subtypes]


def sacrifice(s, source, target):
    activate(s, source, ability=1, cost_choices=[{'component': 0, 'cards': [target.id]}])
    settle(s)


def six_bloods(s, source):
    angel = put(s, 'Serra Angel', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[angel.id], kind='+1/+1', delta=2)
    sacrifice(s, source, angel)
    assert len(bloods(s)) == 6
    return angel


def reanimate(s, source):
    from tests.test_rules_bandmate_references import mana, wait_priority

    ids = [c.id for c in bloods(s)]
    assert len(ids) == 6
    act(s, 'p1', type='clear_mana', player='p1')
    mana(s, W=1, B=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2,
        cost_choices=[{'component': 1, 'cards': ids}])
    settle(s)


def test_full_canonical_production(cards):
    q = coverage.of_card_data(cards.resolve(NAME))
    assert q.level == 'FULL', [(f.label, f.supported) for f in q.features]


@pytest.mark.parametrize('angel', [False, True])
def test_actual_sacrifice_uses_direct_angel_lki_toughness_instead_of_one(cards, angel):
    s, source = scene(cards)
    target = put(s, 'Serra Angel' if angel else 'Grizzly Bears', 'battlefield')
    anthem = put(s, 'Glorious Anthem', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[target.id], kind='+1/+1', delta=2)
    sacrifice(s, source, target)
    assert s.state.cards[target.id].zone == 'p1:graveyard'
    assert len(bloods(s)) == (7 if angel else 1)
    act(s, 'p1', type='move', card_ids=[anthem.id], to={'zone': 'graveyard'})
    assert len(bloods(s)) == (7 if angel else 1)
    roundtrip(s)


def test_actual_six_blood_hybrid_cost_returns_all_own_creatures_as_vampires_with_finality(cards):
    s, source = scene(cards)
    angel = six_bloods(s, source)
    bear = put(s, 'Grizzly Bears', 'graveyard')
    instant = put(s, 'Lightning Bolt', 'graveyard')
    opponent = put(s, 'Serra Angel', 'graveyard', pid='p2')
    reanimate(s, source)
    p = Plan(s.state, 'p1', cards, None)
    for c, original in [(angel, 'Angel'), (bear, 'Bear')]:
        assert s.state.cards[c.id].zone == 'p1:battlefield'
        assert s.state.cards[c.id].counters == {'finality': 1}
        assert {'Vampire', original} <= p.ch(s.state.cards[c.id]).subtypes
    assert s.state.cards[instant.id].zone == 'p1:graveyard'
    assert s.state.cards[opponent.id].zone == 'p2:graveyard'
    assert not bloods(s)
    from app.rules import mana_units

    assert not mana_units.visible_pool(s.state, 'p1')
    roundtrip(s)


def test_actual_created_blood_has_native_discard_sacrifice_draw_ability(cards):
    s, source = scene(cards)
    victim = put(s, 'Grizzly Bears', 'battlefield')
    sacrifice(s, source, victim)
    blood = bloods(s)[0]
    discard = put(s, 'Llanowar Elves', 'hand')
    before = len(s.state.zones.get('p1:hand', []))
    activate(s, blood, ability=0)
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[discard.id])
    settle(s)
    assert s.state.cards[discard.id].zone == 'p1:graveyard'
    assert blood.id not in s.state.cards or not s.state.cards[blood.id].zone.endswith(':battlefield')
    assert len(s.state.zones.get('p1:hand', [])) == before
    roundtrip(s)


@pytest.mark.parametrize('copy_ability', [False, True])
def test_actual_cost_lki_survives_source_exile_or_copied_activated_ability(cards, copy_ability):
    s, source = scene(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    angel = put(s, 'Serra Angel', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[angel.id], kind='+1/+1', delta=2)
    activate(s, source, ability=1, cost_choices=[{'component': 0, 'cards': [angel.id]}])
    original = s.state.zones['stack'][-1]
    if copy_ability:
        engine = put(s, 'Lithoform Engine', 'battlefield')
        activate(s, engine, ability=0, targets=[original])
    else:
        spell = put(s, 'Swords to Plowshares', 'hand')
        cast(s, spell, targets=[source.id])
    settle(s)
    assert s.state.rules.decision is None
    assert len(bloods(s)) == (12 if copy_ability else 6)
    assert s.state.cards[angel.id].zone == 'p1:graveyard'
    if not copy_ability:
        assert s.state.cards[source.id].zone == 'p1:exile'
    roundtrip(s)


def test_actual_blood_tokens_with_extra_food_subtype_still_pay_six_blood_cost(cards):
    s, source = scene(cards)
    angel = six_bloods(s, source)
    put(s, 'Glorious Anthem', 'battlefield')
    march = put(s, 'March of the Machines', 'hand')
    cast(s, march)
    settle(s)
    ygra = put(s, 'Ygra, Eater of All', 'battlefield')
    p = Plan(s.state, 'p1', cards, None)
    assert len(bloods(s)) == 6
    assert all({'Blood', 'Food'} <= p.ch(c).subtypes for c in bloods(s))
    reanimate(s, source)
    assert not bloods(s)
    assert s.state.cards[angel.id].zone == 'p1:battlefield'
    assert s.state.cards[angel.id].counters == {'finality': 1}
    assert s.state.cards[ygra.id].counters == {'+1/+1': 12}
    roundtrip(s)


@pytest.mark.parametrize('animate', [False, True])
def test_entry_vampire_survives_copy_animation_and_finality_survives_ability_loss(cards, animate):
    s, source = scene(cards)
    six_bloods(s, source)
    ring = put(s, 'Sol Ring', 'battlefield')
    incoming = put(s, 'Phyrexian Metamorph', 'graveyard')
    reanimate(s, source)
    d = s.state.rules.decision
    assert d is not None and ring.id in [o.id for o in d.options]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[ring.id])
    settle(s)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[incoming.id])
    assert 'Artifact' in ch.types and 'Creature' not in ch.types
    assert 'Vampire' not in ch.subtypes
    assert s.state.cards[incoming.id].counters == {'finality': 1}
    if animate:
        march = put(s, 'March of the Machines', 'hand')
        cast(s, march)
        settle(s)
        p = Plan(s.state, 'p1', cards, None)
        assert 'Creature' in p.ch(s.state.cards[incoming.id]).types
        assert 'Vampire' in p.ch(s.state.cards[incoming.id]).subtypes
        assert 'Vampire' not in p.ch(s.state.cards[ring.id]).subtypes
        humility = put(s, 'Humility', 'hand')
        cast(s, humility)
        settle(s)
    spell = put(s, 'Naturalize', 'hand')
    cast(s, spell, targets=[incoming.id])
    settle(s)
    assert s.state.cards[incoming.id].zone == 'p1:exile'
    roundtrip(s)


def test_vampire_characteristic_is_present_for_actual_entry_replacement(cards):
    s, source = scene(cards)
    angel = six_bloods(s, source)
    bear = put(s, 'Grizzly Bears', 'graveyard')
    mimic = put(s, 'Metallic Mimic', 'hand')
    cast(s, mimic)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and 'Vampire' in [o.id for o in d.options]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['Vampire'])
    settle(s)
    reanimate(s, source)
    assert s.state.rules.decision is None
    for c in (angel, bear):
        assert s.state.cards[c.id].counters == {'finality': 1, '+1/+1': 1}
    roundtrip(s)


def test_actual_kindred_artifact_copy_retains_added_vampire_before_any_animation(cards):
    s, source = scene(cards)
    six_bloods(s, source)
    wand = put(s, "Diviner's Wand", 'battlefield')
    incoming = put(s, 'Phyrexian Metamorph', 'graveyard')
    reanimate(s, source)
    d = s.state.rules.decision
    assert d is not None and wand.id in [o.id for o in d.options]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[wand.id])
    settle(s)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[incoming.id])
    assert {'Kindred', 'Artifact'} <= ch.types and 'Creature' not in ch.types
    assert {'Wizard', 'Equipment', 'Vampire'} <= ch.subtypes
    assert s.state.cards[incoming.id].counters == {'finality': 1}
    roundtrip(s)


def test_actual_later_animation_vampire_dependency_true_cold(cards, tmp_path):
    import subprocess
    import sys

    s, source = scene(cards)
    six_bloods(s, source)
    ring = put(s, 'Sol Ring', 'battlefield')
    incoming = put(s, 'Phyrexian Metamorph', 'graveyard')
    reanimate(s, source)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[ring.id])
    settle(s)
    march = put(s, 'March of the Machines', 'hand')
    cast(s, march)
    settle(s)
    saved = tmp_path / 'shilgengar43-later-animation.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
saved, db, incoming, ring = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent/'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
s.perform('p1', {'type':'set_prefs','response':'on'})
p = Plan(s.state,'p1',repo,None)
assert 'Creature' in p.ch(s.state.cards[incoming]).types
assert 'Vampire' in p.ch(s.state.cards[incoming]).subtypes
assert 'Vampire' not in p.ch(s.state.cards[ring]).subtypes
assert s.state.cards[incoming].counters == {'finality':1}
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), incoming.id, ring.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_actual_angel_lki_quantity_native_jinnie_choice_true_cold(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose

    s, source = scene(cards)
    angel = put(s, 'Serra Angel', 'battlefield')
    put(s, 'Glorious Anthem', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[angel.id], kind='+1/+1', delta=2)
    put(s, "Jinnie Fay, Jetmir's Second", 'battlefield')
    sacrifice(s, source, angel)
    d = s.state.rules.decision
    assert d is not None
    choice = next(o.id for o in d.options if 'create Dogs' in o.label)
    s = cold_choose(s, cards, tmp_path, [choice])
    settle(s)
    dogs = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield'
            and Plan(s.state, 'p1', cards, None).ch(c).name == 'Dog']
    assert len(dogs) == 7 and not bloods(s)
    assert all({'vigilance'} <= Plan(s.state, 'p1', cards, None).ch(c).keywords for c in dogs)
    roundtrip(s)


@pytest.mark.parametrize('failure', ['five', 'other_creature', 'opponent', 'mana', 'self', 'nontoken_blood'])
def test_actual_sacrifice_cost_eligibility_rejects_atomically(cards, failure):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import mana, wait_priority

    s, source = scene(cards)
    six_bloods(s, source)
    ids = [c.id for c in bloods(s)]
    ability, component = 2, 1
    if failure == 'five':
        ids = ids[:5]
    elif failure == 'other_creature':
        ids[-1] = put(s, 'Grizzly Bears', 'battlefield').id
    elif failure == 'opponent':
        act(s, 'p1', type='move', card_ids=[ids[-1]], to={'zone': 'battlefield', 'player': 'p2'})
    elif failure == 'self':
        ability, component, ids = 1, 0, [source.id]
    elif failure == 'nontoken_blood':
        incoming = put(s, 'Phyrexian Metamorph', 'hand')
        cast(s, incoming)
        settle(s)
        d = s.state.rules.decision
        if d is not None and d.prompt.startswith('Pay {3}{U/P}'):
            act(s, d.player, type='choose', decision_id=d.id, option_ids=['0'])
            settle(s)
            d = s.state.rules.decision
        assert d is not None and ids[0] in [o.id for o in d.options]
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[ids[0]])
        settle(s)
        assert 'Blood' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[incoming.id]).subtypes
        assert not s.state.cards[incoming.id].is_token
        ids[-1] = incoming.id
    act(s, 'p1', type='clear_mana', player='p1')
    if failure != 'mana':
        mana(s, W=1, B=2)
    wait_priority(s, 'p1')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability,
            cost_choices=[{'component': component, 'cards': ids}])
    assert s.state.model_dump(mode='json') == before


@pytest.mark.parametrize('modifier,expected', [('Doubling Season', 2), ('Vorinclex, Monstrous Raider', 0), ('Solemnity', 0)])
def test_actual_finality_entry_replacements_and_independent_vampire_form(cards, modifier, expected):
    s, source = scene(cards)
    angel = six_bloods(s, source)
    put(s, modifier, 'battlefield', pid='p2' if modifier.startswith('Vorinclex') else 'p1')
    reanimate(s, source)
    assert s.state.rules.decision is None
    assert s.state.cards[angel.id].counters == ({'finality': expected} if expected else {})
    assert 'Vampire' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[angel.id]).subtypes
    for _ in range(2):
        bolt = put(s, 'Lightning Bolt', 'hand')
        cast(s, bolt, targets=[angel.id])
        settle(s)
    assert s.state.cards[angel.id].zone == ('p1:exile' if expected else 'p1:graveyard')
    roundtrip(s)


@pytest.mark.parametrize('barrier,destination', [("Grafdigger's Cage", 'graveyard'), ('Containment Priest', 'exile')])
def test_actual_prevented_or_replaced_return_pays_cost_without_finality_or_vampire(cards, barrier, destination):
    s, source = scene(cards)
    angel = six_bloods(s, source)
    bear = put(s, 'Grizzly Bears', 'graveyard')
    put(s, barrier, 'battlefield')
    reanimate(s, source)
    assert s.state.rules.decision is None and not bloods(s)
    for c in (angel, bear):
        assert s.state.cards[c.id].zone == 'p1:' + destination
        assert not s.state.cards[c.id].counters
        assert 'Vampire' not in Plan(s.state, 'p1', cards, None).ch(s.state.cards[c.id]).subtypes
    roundtrip(s)


@pytest.mark.parametrize('first,expected', [('Doubling Season', 1), ('Vorinclex', 0)])
def test_actual_simultaneous_return_counter_order_true_cold(cards, tmp_path, first, expected):
    import subprocess
    import sys

    s, source = scene(cards)
    angel = six_bloods(s, source)
    bear = put(s, 'Grizzly Bears', 'graveyard')
    put(s, 'Doubling Season', 'battlefield')
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
    reanimate(s, source)
    assert s.state.rules.decision is not None
    saved = tmp_path / 'shilgengar43-blood.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle
from tests.test_rules_sacrifice_entry_outcomes43 import bloods
saved, db, first, expected, angel, bear = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
for _ in range(10):
    d = s.state.rules.decision
    if d is None: break
    option = next(o for o in d.options if first in o.label)
    s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':[option.id]})
    settle(s)
assert s.state.rules.decision is None
from app.rules.plan import Plan
for cid in (angel, bear):
    assert s.state.cards[cid].zone == 'p1:battlefield'
    assert s.state.cards[cid].counters == ({'finality':int(expected)} if int(expected) else {})
    assert 'Vampire' in Plan(s.state,'p1',repo,None).ch(s.state.cards[cid]).subtypes
assert not bloods(s)
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), first, str(expected), angel.id, bear.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
