"""CR 101.4 / 611.2b: chosen survivors and the lifetime of their vow restriction."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/loyalty_survivors_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_promise_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Promise of Loyalty')).level == 'FULL'


def setup(cards, extra=None, extra_pid='p1', preexisting=False):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    decks = {pid: ['Grizzly Bears', 'Llanowar Elves'] for pid in ['p1', 'p2', 'p3']}
    decks['p1'].append('Promise of Loyalty')
    extras = [extra] if isinstance(extra, str) else list(extra or [])
    decks[extra_pid] += extras
    s = table(cards, decks['p1'], decks['p2'], decks['p3'])
    chosen, rest = {}, {}
    for pid in decks:
        chosen[pid] = put(s, 'Grizzly Bears', 'battlefield', pid)
        rest[pid] = put(s, 'Llanowar Elves', 'battlefield', pid)
    if preexisting:
        act(s, 'p1', type='counter', card_ids=[chosen['p2'].id], kind='vow', delta=1)
    for name in extras:
        put(s, name, 'battlefield', extra_pid)
    return s, chosen, rest


def resolve_promise(s, chosen):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle

    source = put(s, 'Promise of Loyalty', 'hand')
    mana(s, W=5)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    for pid in ['p1', 'p2', 'p3']:
        d = s.state.rules.decision
        assert d and d.player == pid
        assert chosen[pid].id in {o.id for o in d.options}
        roundtrip(s)
        act(s, pid, type='choose', decision_id=d.id, option_ids=[chosen[pid].id])
        settle(s)


def forbidden(s, card, target='p1'):
    from app.rules import combat
    from app.rules.plan import Plan

    plan = Plan(s.state, card.controller, s.cards, None)
    return combat.attack_forbidden(plan, plan.ch(plan.state.cards[card.id]), target)


def test_players_choose_survivors_then_put_counters_and_sacrifice_all_other_creatures(cards):
    from tests.test_rules_designations import roundtrip

    s, chosen, rest = setup(cards)
    resolve_promise(s, chosen)
    for pid in chosen:
        assert s.state.cards[chosen[pid].id].zone == f'{pid}:battlefield'
        assert s.state.cards[chosen[pid].id].counters['vow'] == 1
        assert s.state.cards[rest[pid].id].zone == f'{pid}:graveyard'
        assert forbidden(s, chosen[pid])
    assert not forbidden(s, chosen['p2'], 'p3')
    roundtrip(s)


def test_counter_prohibition_keeps_chosen_creatures_without_restricting_them(cards):
    from tests.test_rules_designations import roundtrip

    s, chosen, rest = setup(cards, 'Solemnity')
    resolve_promise(s, chosen)
    for pid in chosen:
        assert s.state.cards[chosen[pid].id].zone == f'{pid}:battlefield'
        assert not s.state.cards[chosen[pid].id].counters.get('vow')
        assert not forbidden(s, chosen[pid])
        assert s.state.cards[rest[pid].id].zone == f'{pid}:graveyard'
    roundtrip(s)


def test_each_player_is_counter_putter_and_replacements_apply_before_sacrifices(cards):
    from tests.test_rules_designations import roundtrip

    s, chosen, rest = setup(cards, 'Vorinclex, Monstrous Raider')
    resolve_promise(s, chosen)
    assert s.state.cards[chosen['p1'].id].counters['vow'] == 2
    for pid in ['p2', 'p3']:
        assert not s.state.cards[chosen[pid].id].counters.get('vow')
        assert not forbidden(s, chosen[pid])
        assert s.state.cards[rest[pid].id].zone == f'{pid}:graveyard'
    vorinclex = next(c for c in s.state.cards.values() if c.name == 'Vorinclex, Monstrous Raider')
    assert vorinclex.zone == 'p1:graveyard'
    roundtrip(s)


def test_restriction_ends_per_creature_and_readding_counter_does_not_restore_it(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, chosen, _ = setup(cards)
    resolve_promise(s, chosen)
    c = chosen['p2']
    act(s, 'p1', type='counter', card_ids=[c.id], kind='vow', delta=-1)
    act(s, 'p1', type='counter', card_ids=[c.id], kind='vow', delta=1)
    # Both changes occurred before the next intent: the zero-counter event still ends the duration.
    to_phase(s, 'main1', turn=2)
    assert not forbidden(s, c)
    assert forbidden(s, chosen['p3'])
    roundtrip(s)


def test_restriction_follows_survivor_through_control_change(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, chosen, _ = setup(cards)
    resolve_promise(s, chosen)
    c = chosen['p2']
    act(s, 'p1', type='set_controller', card_ids=[c.id], player='p3')
    assert forbidden(s, c, 'p1')
    assert not forbidden(s, c, 'p2')
    roundtrip(s)


def test_cant_attack_caster_or_their_planeswalker_but_can_attack_other_opponent(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, chosen, _ = setup(cards, 'Jace Beleren')
    jace = next(c for c in s.state.cards.values() if c.name == 'Jace Beleren')
    act(s, 'p1', type='counter', card_ids=[jace.id], kind='loyalty', delta=3)
    resolve_promise(s, chosen)
    to_phase(s, 'declare_attackers', turn=2)
    for target in ['p1', jace.id]:
        with pytest.raises(ActionError):
            act(s, 'p2', type='declare_attackers', attackers=[{'card_id': chosen['p2'].id, 'target': target}])
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': chosen['p2'].id, 'target': 'p3'}])
    to_phase(s, 'main2', turn=2)
    assert s.state.players['p3'].life == 38
    roundtrip(s)


def test_sacrifice_protection_spares_unchosen_creatures_without_restricting_them(cards):
    from tests.test_rules_designations import roundtrip

    s, chosen, rest = setup(cards, 'Tajuru Preserver', 'p2')
    resolve_promise(s, chosen)
    assert s.state.cards[rest['p2'].id].zone == 'p2:battlefield'
    assert not forbidden(s, rest['p2'])
    assert forbidden(s, chosen['p2'])
    assert s.state.cards[rest['p1'].id].zone == 'p1:graveyard'
    roundtrip(s)


def test_preexisting_vow_counter_can_sustain_restriction_when_new_counters_are_prohibited(cards):
    from tests.test_rules_designations import roundtrip

    s, chosen, _ = setup(cards, 'Solemnity', preexisting=True)
    resolve_promise(s, chosen)
    assert s.state.cards[chosen['p2'].id].counters['vow'] == 1
    assert forbidden(s, chosen['p2'])
    assert not forbidden(s, chosen['p3'])
    roundtrip(s)


def test_per_player_putters_survive_counter_ordering_decision_and_reload(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, chosen, _ = setup(cards, ('Vorinclex, Monstrous Raider', 'Pir, Imaginative Rascal'))
    resolve_promise(s, chosen)
    d = s.state.rules.decision
    assert d and '616.1' in d.prompt
    for _ in range(4):
        d = s.state.rules.decision
        if d is None:
            break
        assert '616.1' in d.prompt
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
        settle(s)
    assert s.state.cards[chosen['p1'].id].counters['vow'] in (3, 4)
    assert not s.state.cards[chosen['p2'].id].counters.get('vow')
    assert not s.state.cards[chosen['p3'].id].counters.get('vow')
    roundtrip(s)
