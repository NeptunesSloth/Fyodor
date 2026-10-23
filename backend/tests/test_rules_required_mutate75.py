"""Selected mutate authority never grants a plain cast or spends unrelated uses."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import alt_costs, casting, coverage
from app.rules.plan import Plan
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/required_mutate75_cards.json').read_text())
BROKKOS = 'Brokkos, Apex of Forever'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['exile_outcomes42_cards.json', 'exile_cast_outcomes45_cards.json',
                     'fight_exile_receipts65_cards.json', 'top_library_authorities69_cards.json',
                     'pooled_casting_authorities71_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='rm75', number=str(i), **{k: v for k, v in c.items() if k not in {'name', 'set_code'}})
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='rm75', number='a' + str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *[c['name'] for c in DATA], 'Lightning Bolt', 'Disperse', 'Counterspell')


def key(s, source, tag='mutate'):
    return next(o.key for o in alt_costs.offers(s.state, 'p1', source, Plan(s.state, 'p1', s.cards, None).ch(source), s.cards) if o.tag == tag)


def merge(s):
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'mutate_choice'
    answer(s, ['over'])
    settle(s)


def test_canonical_brokkos_whole75(cards):
    assert coverage.of_card_data(cards.resolve(BROKKOS)).level == 'FULL'


def test_own_graveyard_requires_actual_selected_mutate_and_pays_its_native_cost(cards):
    s = setup(cards)
    source = put(s, BROKKOS, 'graveyard')
    host = put(s, 'Grizzly Bears', 'battlefield')
    mana(s, C=2, B=1, G=2)
    assert not casting.castable(s.state, 'p1', source, cards)
    offers = casting.alt_castable(s.state, 'p1', source, cards)
    assert {o['id'] for o in offers} == {key(s, source)}
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id)
    assert s.state.model_dump(mode='json') == before
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source), targets=[host.id])
    merge(s)
    current = s.state.cards[host.id]
    assert current.name == BROKKOS and [p.name for p in current.merged] == [BROKKOS, 'Grizzly Bears']
    assert Plan(s.state, 'p1', cards, None).ch(current).pt == (6, 6)
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)


def test_fist_of_suns_cannot_replace_brokkos_required_mutate_authority(cards):
    s = setup(cards)
    cast(s, 'Fist of Suns')
    source = put(s, BROKKOS, 'graveyard')
    put(s, 'Grizzly Bears', 'battlefield')
    mana(s, W=1, U=1, B=1, R=1, G=3)
    all_offers = alt_costs.offers(s.state, 'p1', source, Plan(s.state, 'p1', cards, None).ch(source), cards)
    alternate = next(o for o in all_offers if o.tag != 'mutate')
    hinted = casting.alt_castable(s.state, 'p1', source, cards)
    assert {o['id'] for o in hinted} == {key(s, source)}
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=alternate.key)
    assert s.state.model_dump(mode='json') == before


def test_other_native_graveyard_permission_still_allows_an_ordinary_cast(cards):
    s = setup(cards)
    cast(s, 'Muldrotha, the Gravetide')
    source = put(s, BROKKOS, 'graveyard')
    mana(s, C=2, B=1, G=1, U=1)
    assert casting.castable(s.state, 'p1', source, cards)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert source.zone == 'p1:battlefield' and not source.merged
    roundtrip(s)


def test_own_mutate_authority_does_not_consume_the_other_creature_permission(cards):
    s = setup(cards)
    cast(s, 'Muldrotha, the Gravetide')
    source = put(s, BROKKOS, 'graveyard')
    host = put(s, 'Grizzly Bears', 'battlefield')
    mana(s, C=2, B=1, G=2)
    before = {k: v for k, v in s.state.rules.once_per_turn.items() if ':permission:' in k}
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source), targets=[host.id])
    merge(s)
    assert {k: v for k, v in s.state.rules.once_per_turn.items() if ':permission:' in k} == before
    other = put(s, 'Rivaz of the Claw', 'graveyard')
    mana(s, C=1, B=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=other.id)
    settle(s)
    assert other.zone == 'p1:battlefield'
    roundtrip(s)


def test_no_legal_mutate_host_never_offers_or_grants_a_graveyard_cast(cards):
    s = setup(cards)
    source = put(s, BROKKOS, 'graveyard')
    mana(s, C=10, W=10, U=10, B=10, R=10, G=10)
    assert casting.alt_castable(s.state, 'p1', source, cards) == []
    assert not casting.castable(s.state, 'p1', source, cards)


def test_other_native_graveyard_permission_also_allows_its_independent_fist_cost(cards):
    s = setup(cards)
    cast(s, 'Muldrotha, the Gravetide')
    cast(s, 'Fist of Suns')
    source = put(s, BROKKOS, 'graveyard')
    mana(s, W=1, U=1, B=1, R=1, G=1)
    alternative = next(o for o in alt_costs.offers(s.state, 'p1', source, Plan(s.state, 'p1', cards, None).ch(source), cards) if o.tag != 'mutate')
    assert alternative.key in {o['id'] for o in casting.alt_castable(s.state, 'p1', source, cards)}
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=alternative.key)
    settle(s)
    assert source.zone == 'p1:battlefield' and not source.merged
    assert any(':permission:' in k and k.endswith(':Creature') for k in s.state.rules.once_per_turn)
    roundtrip(s)


@pytest.mark.parametrize('mutating', [False, True])
def test_actual_hand_casts_keep_both_normal_and_mutate_options(cards, mutating):
    s = setup(cards)
    source = put(s, BROKKOS, 'hand')
    host = put(s, 'Grizzly Bears', 'battlefield')
    mana(s, C=5, U=5, B=5, G=5)
    if mutating:
        act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source), targets=[host.id])
        merge(s)
        assert s.state.cards[host.id].name == BROKKOS
    else:
        act(s, 'p1', type='cast_spell', card_id=source.id)
        settle(s)
        assert source.zone == 'p1:battlefield' and not source.merged
    roundtrip(s)


def test_countered_mutate_can_use_the_own_permission_again_from_its_new_graveyard_object(cards):
    s = setup(cards)
    source = put(s, BROKKOS, 'graveyard')
    host = put(s, 'Grizzly Bears', 'battlefield')
    original = s.state.rules.object_id(source.id)
    mana(s, C=2, B=1, G=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source), targets=[host.id])
    counter = put(s, 'Counterspell', 'hand', pid='p2')
    mana(s, pid='p2', U=2)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[source.id])
    settle(s)
    assert source.zone == 'p1:graveyard' and s.state.rules.object_id(source.id) != original
    mana(s, C=2, B=1, G=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source), targets=[host.id])
    merge(s)
    assert s.state.cards[host.id].name == BROKKOS
    roundtrip(s)


def test_actual_flash_permission_prevents_autopass_over_the_only_legal_graveyard_mutate(cards):
    s = setup(cards)
    cast(s, 'Leyline of Anticipation')
    source = put(s, BROKKOS, 'graveyard')
    host = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=2)
    settle(s)
    # Keep Brokkos the only possible response, not a convenient instant in hand.
    hand = list(s.state.zones['p1:hand'])
    if hand:
        act(s, 'p1', type='move', card_ids=hand, to={'player': 'p1', 'zone': 'library'})
    act(s, 'p1', type='clear_mana')
    mana(s, C=2, B=1, G=2)
    wait_priority(s, 'p1')
    assert not casting.castable(s.state, 'p1', source, cards)
    assert casting.has_responses(s.state, 'p1', cards)
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source), targets=[host.id])
    merge(s)
    assert s.state.cards[host.id].name == BROKKOS
    roundtrip(s)


def test_actual_mutate_cost_still_requires_payable_native_mana(cards):
    s = setup(cards)
    source = put(s, BROKKOS, 'graveyard')
    host = put(s, 'Grizzly Bears', 'battlefield')
    assert casting.alt_castable(s.state, 'p1', source, cards) == []
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source), targets=[host.id])
    assert s.state.model_dump(mode='json') == before


def test_payable_sorcery_mutate_is_not_invented_as_an_instant_response(cards):
    s = setup(cards)
    source = put(s, BROKKOS, 'graveyard')
    put(s, 'Grizzly Bears', 'battlefield')
    hand = list(s.state.zones['p1:hand'])
    if hand:
        act(s, 'p1', type='move', card_ids=hand, to={'player': 'p1', 'zone': 'library'})
    mana(s, C=2, B=1, G=2)
    assert casting.alt_castable(s.state, 'p1', source, cards)
    assert not casting.has_responses(s.state, 'p1', cards)


@pytest.mark.parametrize('mode', ['graveyard', 'pending_merge'])
def test_genuine_fresh_process_uses_only_the_native_selected_mutate_authority(cards, tmp_path, mode):
    import os
    import subprocess
    import sys

    s = setup(cards)
    source = put(s, BROKKOS, 'graveyard')
    host = put(s, 'Grizzly Bears', 'battlefield')
    mana(s, C=2, B=1, G=2)
    if mode == 'pending_merge':
        act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=key(s, source), targets=[host.id])
        settle(s)
        assert s.state.rules.decision.resume['step'] == 'mutate_choice'
    saved = tmp_path / 'mutate.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from app.game.errors import ActionError
from app.rules import casting
from tests.test_rules_required_mutate75 import key,BROKKOS
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from tests.test_rules_controller_tutors import answer
from tests.game_helpers import act
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
mode,source,host=sys.argv[3:]
if mode=='graveyard':
 assert not casting.castable(s.state,'p1',s.state.cards[source],r)
 before=s.state.model_dump(mode='json')
 try:act(s,'p1',type='cast_spell',card_id=source)
 except ActionError:pass
 else:raise AssertionError('The mutate-only authority allowed a normal cast')
 assert before==s.state.model_dump(mode='json')
 act(s,'p1',type='cast_spell',card_id=source,alt_cost=key(s,s.state.cards[source]),targets=[host])
 settle(s)
assert s.state.rules.payments[s.state.rules.object_id(source)].alternative=='mutate'
d=s.state.rules.decision
assert d and d.resume['step']=='mutate_choice'
answer(s,['over']);settle(s)
assert s.state.cards[host].name==BROKKOS and source not in s.state.cards
assert [p.name for p in s.state.cards[host].merged]==[BROKKOS,'Grizzly Bears']
roundtrip(s)
r.close()
'''
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), mode, source.id, host.id],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
