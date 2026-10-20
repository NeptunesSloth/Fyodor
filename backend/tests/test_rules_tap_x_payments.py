"""CR 702.29c/f, 614.1: cycling permissions and graveyard replacements."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/tap_x_payments_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_battlesphere_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Myr Battlesphere')).level == 'FULL'


def setup_attack(cards, *, vigilance=False, leave=False):
    from tests.game_helpers import act
    from tests.test_rules_banding import declare_only
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Myr Battlesphere', 'Gold Myr', 'Grizzly Bears', 'Vigilance'], ['Gold Myr'], [])
    sphere = put(s, 'Myr Battlesphere', 'hand')
    mana(s, C=7)
    act(s, 'p1', type='cast_spell', card_id=sphere.id)
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token]
    assert len(tokens) == 4
    gold = put(s, 'Gold Myr', 'battlefield')
    act(s, 'p1', type='tap', card_ids=[gold.id], tapped=True)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Gold Myr', 'battlefield', 'p2')
    if vigilance:
        aura = put(s, 'Vigilance', 'hand')
        mana(s, W=1)
        act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[sphere.id])
        settle(s)
    declare_only(s, [sphere], [])
    # The untap steps cleared Gold Myr's initial tapped state; tap it before resolving the trigger.
    act(s, 'p1', type='tap', card_ids=[gold.id], tapped=True)
    if leave:
        act(s, 'p1', type='move', card_ids=[sphere.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    return s, sphere, tokens, gold, bear, other


def answer(s, ids):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    d = s.state.rules.decision
    assert d and 'choose_x' in d.resume
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)


@pytest.mark.parametrize('n', [0, 2, 4])
def test_tapping_myrs_sets_x_for_both_power_and_damage(cards, n):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, sphere, tokens, gold, bear, other = setup_attack(cards)
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {c.id for c in tokens} | {'decline'}
    assert not {sphere.id, gold.id, bear.id, other.id} & {o.id for o in d.options}
    answer(s, [c.id for c in tokens[:n]])
    assert sum(s.state.cards[c.id].tapped for c in tokens) == n
    to_phase(s, 'main2', turn=4)
    assert s.state.players['p2'].life == 40 - 4 - 2 * n
    roundtrip(s)


def test_declining_payment_does_not_tap_any_myrs(cards):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _, tokens, _, _, _ = setup_attack(cards)
    answer(s, ['decline'])
    to_phase(s, 'main2', turn=4)
    assert not any(s.state.cards[c.id].tapped for c in tokens)
    assert s.state.players['p2'].life == 36
    roundtrip(s)


def test_vigilant_battlesphere_can_tap_itself_and_stays_attacking(cards):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, sphere, _, _, _, _ = setup_attack(cards, vigilance=True)
    d = s.state.rules.decision
    assert d and sphere.id in {o.id for o in d.options}
    answer(s, [sphere.id])
    assert s.state.cards[sphere.id].tapped
    to_phase(s, 'main2', turn=4)
    assert s.state.players['p2'].life == 34
    roundtrip(s)


def test_source_departure_still_allows_payment_and_damage_from_its_lki(cards):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, sphere, tokens, _, _, _ = setup_attack(cards, leave=True)
    answer(s, [c.id for c in tokens[:2]])
    to_phase(s, 'main2', turn=4)
    assert s.state.cards[sphere.id].zone == 'p1:graveyard'
    assert s.state.players['p2'].life == 38
    roundtrip(s)


def test_changed_cost_candidate_is_rejected_without_tapping_other_selected_myrs(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _, tokens, _, _, _ = setup_attack(cards)
    d = s.state.rules.decision
    assert d
    act(s, 'p1', type='tap', card_ids=[tokens[0].id], tapped=True)
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[tokens[0].id, tokens[1].id])
    assert not s.state.cards[tokens[1].id].tapped
    answer(s, [tokens[1].id])
    to_phase(s, 'main2', turn=4)
    assert s.state.players['p2'].life == 34
    roundtrip(s)
