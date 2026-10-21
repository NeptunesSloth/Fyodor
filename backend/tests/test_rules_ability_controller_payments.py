"""CR 113.7a / 118.12a: an ability controller pays to avoid a counter."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/ability_controller_payments_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_ayesha_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Ayesha Tanaka')).level == 'FULL'


@pytest.mark.parametrize('payment', ['pay', 'decline', 'unavailable'])
@pytest.mark.parametrize('source_left', [False, True])
def test_ayesha_asks_the_ability_controller_even_if_its_artifact_source_is_gone(cards, payment, source_left):
    s = table(cards, ['Ayesha Tanaka'], ['Mind Stone'])
    ayesha = put(s, 'Ayesha Tanaka', 'battlefield')
    stone = put(s, 'Mind Stone', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    wait_priority(s, 'p2')
    mana(s, 'p2', C=1)
    act(s, 'p2', type='activate_ability', card_id=stone.id, ability=1)
    sid = next(sid for sid, entry in s.state.rules.stack.items() if entry.source_card == stone.id)
    if not source_left:
        # The sacrificed card is a new object: bringing it back must not redirect the counter.
        act(s, 'p1', type='move', card_ids=[stone.id], to={'player': 'p2', 'zone': 'battlefield'})
    wait_priority(s, 'p1')
    if payment != 'unavailable':
        mana(s, 'p2', W=1)
    before = len(s.state.zones['p2:hand'])
    act(s, 'p1', type='activate_ability', card_id=ayesha.id, ability=1, targets=[sid])
    roundtrip(s)
    settle(s)
    d = s.state.rules.decision
    if payment == 'unavailable':
        assert d is None or d.kind != 'optional_payment'
    else:
        assert d and d.player == 'p2' and {o.id for o in d.options} == {'pay', 'decline'}
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[payment])
        settle(s)
    assert len(s.state.zones['p2:hand']) == before + (payment == 'pay')
    assert sid not in s.state.rules.stack
    roundtrip(s)


def test_ayesha_cannot_target_a_nonartifact_activated_ability(cards):
    from app.game.errors import ActionError

    s = table(cards, ['Ayesha Tanaka'], ['Prodigal Pyromancer'])
    ayesha = put(s, 'Ayesha Tanaka', 'battlefield')
    pyro = put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=pyro.id, ability=0, targets=['p3'])
    sid = next(sid for sid, entry in s.state.rules.stack.items() if entry.source_card == pyro.id)
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=ayesha.id, ability=1, targets=[sid])
    assert not s.state.cards[ayesha.id].tapped
    roundtrip(s)
    settle(s)
    assert s.state.players['p3'].life == 39
    roundtrip(s)


@pytest.mark.parametrize('text', [
    "Counter target spell unless that ability's controller pays {W}.",
    "Destroy target artifact unless that ability's controller pays {W}.",
    "Counter up to two target activated abilities unless that ability's controller pays {W}.",
])
def test_ability_controller_pronoun_requires_one_ability_target(text):
    from app.rules import scripts

    assert scripts._parse_effects(text, None) is None


def test_ayesha_cannot_target_an_artifact_triggered_ability(cards):
    from app.game.errors import ActionError

    s = table(cards, ['Ayesha Tanaka'], ['Ichor Wellspring'])
    ayesha = put(s, 'Ayesha Tanaka', 'battlefield')
    wellspring = put(s, 'Ichor Wellspring', 'hand', 'p2')
    to_phase(s, 'main1', turn=5)
    mana(s, 'p2', C=2)
    act(s, 'p2', type='cast_spell', card_id=wellspring.id)
    for _ in range(12):
        entries = [(sid, e) for sid, e in s.state.rules.stack.items() if e.kind == 'trigger' and e.source_card == wellspring.id]
        if entries:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert entries
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=ayesha.id, ability=1, targets=[entries[0][0]])
    assert not s.state.cards[ayesha.id].tapped
    roundtrip(s)
    settle(s)
    roundtrip(s)
