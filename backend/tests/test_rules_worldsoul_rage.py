"""Worldsoul Rage: X-bounded land selection across hand and graveyard."""
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
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/worldsoul_rage_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()





def setup(cards, x=2, extra=()):
    s = table(cards, ["Worldsoul's Rage", 'Forest', 'Mountain', 'Plains', 'Grizzly Bears', *extra],
              ['Forest', 'Grizzly Bears'], ['Mountain', 'Healing Salve'])
    spell = put(s, "Worldsoul's Rage", 'hand')
    forest = put(s, 'Forest', 'hand')
    mountain = put(s, 'Mountain', 'graveyard')
    plains = put(s, 'Plains', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'G': 1, **({'C': x} if x else {})})
    return s, spell, forest, mountain, plains


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Worldsoul's Rage")).level == 'FULL'


@pytest.mark.parametrize('selected', [('forest', 'mountain'), ('forest',), ('mountain',), ()])
def test_choose_up_to_x_from_both_your_zones(cards, selected):
    s, spell, forest, mountain, plains = setup(cards)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=2, targets=['p2'], sources=[])
    until_asked(s)
    d = s.state.rules.decision
    assert d and d.max_choices == 2
    assert {forest.id, mountain.id, plains.id} <= {o.id for o in d.options}
    assert s.state.players['p2'].life == 38
    roundtrip(s)
    by_name = {'forest': forest.id, 'mountain': mountain.id}
    ids = [by_name[n] for n in selected]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)
    for c in (forest, mountain):
        if c.id in ids:
            assert s.state.cards[c.id].zone == 'p1:battlefield' and s.state.cards[c.id].tapped
        else:
            assert s.state.cards[c.id].zone == ('p1:hand' if c.id == forest.id else 'p1:graveyard')
    roundtrip(s)


def test_zero_x_has_no_land_choice_even_with_matching_cards_in_hand(cards):
    s, spell, forest, mountain, _ = setup(cards, x=0)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=0, targets=['p2'], sources=[])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.players['p2'].life == 40
    assert s.state.cards[forest.id].zone == 'p1:hand'
    assert s.state.cards[mountain.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_selection_excludes_nonlands_and_other_players_graveyards(cards):
    from app.game.errors import ActionError
    s, spell, forest, mountain, plains = setup(cards, x=1)
    nonland = put(s, 'Grizzly Bears', 'hand')
    theirs = put(s, 'Forest', 'graveyard', pid='p2')
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=1, targets=['p2'], sources=[])
    until_asked(s)
    d = s.state.rules.decision
    assert d and d.max_choices == 1
    assert {o.id for o in d.options} == {forest.id, mountain.id, plains.id}
    before = s.state.model_dump(mode='json')
    for invalid in ([forest.id, mountain.id], [nonland.id], [theirs.id]):
        with pytest.raises(ActionError):
            act(s, d.player, type='choose', decision_id=d.id, option_ids=invalid)
        assert s.state.model_dump(mode='json') == before
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[mountain.id])
    settle(s)
    roundtrip(s)


def test_illegal_only_target_counters_entire_spell_without_land_choice(cards):
    s, spell, forest, mountain, _ = setup(cards)
    victim = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=2, targets=[victim.id], sources=[])
    act(s, 'p2', type='move', card_ids=[victim.id], to={'player': 'p2', 'zone': 'hand'})
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[forest.id].zone == 'p1:hand'
    assert s.state.cards[mountain.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_lethal_damage_waits_for_land_instruction_before_state_based_actions(cards):
    s, spell, forest, _, _ = setup(cards)
    victim = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=2, targets=[victim.id], sources=[])
    until_asked(s)
    d = s.state.rules.decision
    assert d
    assert s.state.cards[victim.id].zone == 'p2:battlefield' and s.state.cards[victim.id].damage == 2
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[forest.id])
    settle(s)
    assert s.state.cards[victim.id].zone == 'p2:graveyard'
    assert s.state.cards[forest.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_entry_untap_triggers_happen_after_tapped_lands_enter(cards):
    s, spell, forest, mountain, _ = setup(cards, extra=['Amulet of Vigor'])
    put(s, 'Amulet of Vigor', 'battlefield')
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=2, targets=['p2'], sources=[])
    until_asked(s)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[forest.id, mountain.id])
    assert s.state.cards[forest.id].tapped and s.state.cards[mountain.id].tapped
    settle(s)
    assert not s.state.cards[forest.id].tapped and not s.state.cards[mountain.id].tapped
    roundtrip(s)


def test_creature_land_from_graveyard_still_obeys_entry_prohibitions(cards):
    s, spell, forest, _, _ = setup(cards, extra=["Grafdigger's Cage", 'Dryad Arbor'])
    put(s, "Grafdigger's Cage", 'battlefield')
    arbor = put(s, 'Dryad Arbor', 'graveyard')
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=2, targets=['p2'], sources=[])
    until_asked(s)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[forest.id, arbor.id])
    settle(s)
    assert s.state.cards[forest.id].zone == 'p1:battlefield'
    assert s.state.cards[arbor.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('x', [2, 5])
def test_damage_prevention_does_not_prevent_later_land_instruction(cards, x):
    from tests.test_rules_bandmate_references import wait_priority
    s, spell, forest, _, _ = setup(cards, x=x)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=x, targets=['p2'], sources=[])
    shield = put(s, 'Healing Salve', 'hand', pid='p3')
    act(s, 'p3', type='add_mana', player='p3', mana={'W': 1})
    wait_priority(s, 'p3')
    act(s, 'p3', type='cast_spell', card_id=shield.id, modes=[1], targets=['p2'], sources=[])
    until_asked(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    assert s.state.players['p2'].life == 40 - max(0, x - 3)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[forest.id])
    settle(s)
    assert s.state.cards[forest.id].zone == 'p1:battlefield' and s.state.cards[forest.id].tapped
    roundtrip(s)


def test_hidden_hand_choice_does_not_disclose_whether_land_matches(cards):
    from app.game.visibility import SPECTATOR
    seen = []
    for has_land in (False, True):
        s, spell, forest, mountain, plains = setup(cards)
        put(s, 'Grizzly Bears', 'hand')
        for c in (mountain, plains, *([] if has_land else [forest])):
            act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'})
        act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=2, targets=['p2'], sources=[])
        until_asked(s)
        d = s.state.rules.decision
        assert d and {o.id for o in d.options} == ({forest.id} if has_land else set())
        public = {v: s.view(v)['rules']['decision'] for v in ('p2', SPECTATOR)}
        seen.append({v: {k: value for k, value in data.items() if k != 'id'} for v, data in public.items()})
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    assert seen[0] == seen[1]
