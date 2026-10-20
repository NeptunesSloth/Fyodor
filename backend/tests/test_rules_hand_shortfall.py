"""CR 608.2h, 121.2c: hand shortfalls are captured before draws and replacements."""
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
from tests.test_rules_designations import build, put, roundtrip, settle


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/hand_shortfall_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='hsf', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('mine,theirs', [(1, 4), (3, 3), (5, 2)])
def test_balance_of_power_draws_only_the_positive_hand_difference(cards, mine, theirs):
    assert coverage.of_card_data(cards.resolve('Balance of Power')).level == 'FULL'
    s = build(cards, ['Balance of Power'])
    spell = put(s, 'Balance of Power', 'hand')
    fill_hand(s, 'p1', mine + 1, keep=[spell.id])
    fill_hand(s, 'p2', theirs)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'U': 2})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    settle(s)
    assert len(s.state.zones['p1:hand']) == max(mine, theirs)
    assert len(s.state.zones['p2:hand']) == theirs
    roundtrip(s)


def fill_hand(s, player, n, keep=()):
    old = [c for c in s.state.zones.get(player + ':hand', []) if c not in keep]
    if old:
        act(s, player, type='move', card_ids=old, to={'player': player, 'zone': 'library'})
    want = n - len(keep)
    ids = list(s.state.zones[player + ':library'])[:want]
    assert len(ids) == want
    if ids:
        act(s, player, type='move', card_ids=ids, to={'player': player, 'zone': 'hand'})


def pod(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    lists = [deck(cards, 'Krenko, Mob Boss', [(1, 'Tales of the Ancestors'), (1, 'Balance of Power'), (1, "Alhammarret's Archive"), (1, "Underrealm Lich"), (20, 'Forest')])]
    lists += [deck(cards, 'Krenko, Mob Boss', [(20, 'Forest')]) for _ in range(2)]
    s = GameSession(enable(new_game([PlayerSetup(name, cards=d) for name, d in zip(['A', 'B', 'C'], lists, strict=True)], shuffle=False)), cards=cards)
    act(s, 'p1', type='pass_priority')
    return s


@pytest.mark.parametrize('double', [False, True])
@pytest.mark.parametrize('sizes', [(1, 2, 3), (4, 1, 2), (3, 3, 3), (0, 0, 0)])
def test_tales_captures_every_players_shortfall_before_any_player_draws(cards, double, sizes):
    assert coverage.of_card_data(cards.resolve('Tales of the Ancestors')).level == 'FULL'
    s = pod(cards)
    if double:
        put(s, "Alhammarret's Archive", 'battlefield')
    spell = put(s, 'Tales of the Ancestors', 'hand')
    fill_hand(s, 'p1', sizes[0] + 1, keep=[spell.id])
    fill_hand(s, 'p2', sizes[1])
    fill_hand(s, 'p3', sizes[2])
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'U': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    largest = max(sizes)
    expected = [sizes[0] + (largest - sizes[0]) * (2 if double else 1), largest, largest]
    assert [len(s.state.zones[p + ':hand']) for p in ['p1', 'p2', 'p3']] == expected
    roundtrip(s)


def test_balance_of_power_reads_hand_counts_at_resolution(cards):
    from tests.test_rules_wave31d_spell_copies import hold

    s = build(cards, ['Balance of Power'])
    spell = put(s, 'Balance of Power', 'hand')
    fill_hand(s, 'p1', 2, keep=[spell.id])
    fill_hand(s, 'p2', 4)
    hold(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'U': 2})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    act(s, 'p2', type='move', card_ids=list(s.state.zones['p2:hand'])[:2], to={'player': 'p2', 'zone': 'graveyard'})
    settle(s)
    assert len(s.state.zones['p1:hand']) == len(s.state.zones['p2:hand']) == 2
    roundtrip(s)


def test_balance_cannot_target_its_controller(cards):
    s = build(cards, ['Balance of Power'])
    spell = put(s, 'Balance of Power', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'U': 2})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p1'])
    assert before == s.state.model_dump(mode='json')
    roundtrip(s)


def test_tales_can_be_foretold_and_cast_on_a_later_turn(cards):
    from tests.test_rules_wave34b_activated import next_turn

    s = build(cards, ['Tales of the Ancestors'])
    spell = put(s, 'Tales of the Ancestors', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=spell.id, ability=1)
    assert s.state.cards[spell.id].zone == 'p1:foretell'
    roundtrip(s)
    next_turn(s)
    fill_hand(s, 'p1', 1)
    fill_hand(s, 'p2', 3)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'U': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert len(s.state.zones['p1:hand']) == len(s.state.zones['p2:hand']) == 3
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Tales of the Ancestors', 'Balance of Power'])
def test_hand_shortfalls_survive_replacement_order_prompts(cards, name):
    from tests.test_rules_designations import pick

    s = pod(cards)
    put(s, "Alhammarret's Archive", 'battlefield')
    put(s, "Underrealm Lich", 'battlefield')
    spell = put(s, name, 'hand')
    fill_hand(s, 'p1', 2, keep=[spell.id])
    fill_hand(s, 'p2', 3 if name == 'Balance of Power' else 2)
    fill_hand(s, 'p3', 3)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'U': 2})
    act(s, 'p1', type='cast_spell', card_id=spell.id, **({'targets': ['p2']} if name == 'Balance of Power' else {}))
    settle(s)
    assert s.state.rules.decision is not None
    roundtrip(s)
    prompts = 0
    seen = []
    for _ in range(20):
        d = s.state.rules.decision
        if d is None:
            break
        assert d.kind != 'manual_resolution'
        seen.append((d.kind, [(o.id, o.label) for o in d.options]))
        roundtrip(s)
        pick(s, [next((o.id for o in d.options if o.label.startswith("Alhammarret")), d.options[0].id)])
        prompts += 1
        settle(s)
    assert prompts > 0 and s.state.rules.decision is None
    assert [len(s.state.zones[p + ':hand']) for p in ['p1', 'p2', 'p3']] == [5, 3, 3], seen
    roundtrip(s)


@pytest.mark.parametrize('their_hand', [0, 1, 2, 3])
def test_skull_raid_draws_the_shortfall_of_actual_discards(cards, their_hand):
    from tests.test_rules_designations import pick

    assert coverage.of_card_data(cards.resolve('Skull Raid')).level == 'FULL'
    s = build(cards, ['Skull Raid'])
    spell = put(s, 'Skull Raid', 'hand')
    fill_hand(s, 'p1', 2, keep=[spell.id])
    fill_hand(s, 'p2', their_hand)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'B': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    settle(s)
    if their_hand > 2:
        d = s.state.rules.decision
        assert d is not None and d.player == 'p2'
        assert not s.view('p1')['rules']['decision'].get('options')
        roundtrip(s)
        pick(s, [o.id for o in d.options[:2]])
        settle(s)
    assert len(s.state.zones['p1:hand']) == 1 + max(0, 2 - their_hand)
    assert len(s.state.zones['p2:hand']) == max(0, their_hand - 2)
    roundtrip(s)


def test_skull_raid_counts_a_discard_whose_destination_was_replaced(cards):
    s = build(cards, ['Skull Raid'], bob=((1, 'Obstinate Baloth'), (10, 'Island')))
    spell = put(s, 'Skull Raid', 'hand')
    fill_hand(s, 'p1', 2, keep=[spell.id])
    baloth = put(s, 'Obstinate Baloth', 'hand', pid='p2')
    fill_hand(s, 'p2', 2, keep=[baloth.id])
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'B': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    settle(s)
    assert s.state.cards[baloth.id].zone == 'p2:battlefield'
    assert len(s.state.zones['p1:hand']) == 1 and not s.state.zones['p2:hand']
    assert s.state.players['p2'].life == 44
    roundtrip(s)


@pytest.mark.parametrize('first,expected', [("Alhammarret's Archive", 3), ('Blood Scrivener', 4)])
def test_pending_draws_recheck_hand_dependent_replacements(cards, first, expected):
    from tests.test_rules_designations import pick

    s = build(cards, ['Balance of Power', "Alhammarret's Archive", 'Blood Scrivener'])
    put(s, "Alhammarret's Archive", 'battlefield')
    put(s, 'Blood Scrivener', 'battlefield')
    spell = put(s, 'Balance of Power', 'hand')
    fill_hand(s, 'p1', 1, keep=[spell.id])
    fill_hand(s, 'p2', 1)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'U': 2})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    pick(s, [next(o.id for o in d.options if o.label.startswith(first))])
    settle(s)
    assert s.state.rules.decision is None
    assert len(s.state.zones['p1:hand']) == expected
    assert s.state.players['p1'].life == 39
    roundtrip(s)
