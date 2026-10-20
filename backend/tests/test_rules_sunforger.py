"""CR 701.3d/608.2g: unattach, search, mandatory free cast, then shuffle."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting, coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import build, put, roundtrip, settle

DATA = Path(__file__).parent / 'fixtures/sunforger_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='sun', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, extra=(), attached=True):
    from tests.test_rules_wave31d_spell_copies import hold
    s = build(cards, ['Sunforger', 'Grizzly Bears', *extra])
    source = put(s, 'Sunforger', 'battlefield')
    host = put(s, 'Grizzly Bears', 'battlefield')
    if attached:
        act(s, 'p1', type='attach', card_ids=[source.id], to=host.id)
    hold(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'W': 1})
    return s, source, host


def resolve_search(s, source):
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert s.state.cards[source.id].attached_to is None
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == 'choose_cards' and 'Search' in d.prompt
    roundtrip(s)
    return d


def choose(s, ids):
    d = s.state.rules.decision
    assert d
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    roundtrip(s)


def test_canonical_sunforger_supported(cards):
    c = coverage.of_card_data(cards.resolve('Sunforger'))
    assert c.level == 'FULL', c.manual_parts


def test_unattached_source_cannot_pay_unattach_and_rejection_preserves_mana(cards):
    s, source, _ = setup(cards, attached=False)
    assert not any(a['card_id'] == source.id and a['ability'] == 1 for a in casting.activatable(s.state, 'p1', cards))
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert s.state.model_dump(mode='json') == before and mana_pool(s, 'p1') == {'R': 1, 'W': 1}
    roundtrip(s)


def test_search_qualification_and_failure_to_find_still_shuffle(cards):
    names = ['Lightning Bolt', 'Swords to Plowshares', 'Counterspell', 'Boros Charm', 'Return to Dust', 'Seething Song', 'Fire // Ice', 'Bonecrusher Giant // Stomp']
    s, source, _ = setup(cards, names)
    for name in names:
        put(s, name, 'library')
    old = set(s.state.zones['p1:library'])
    d = resolve_search(s, source)
    found = {s.state.cards[o.id].name for o in d.options}
    assert found == {'Lightning Bolt', 'Swords to Plowshares', 'Boros Charm', 'Return to Dust', 'Fire // Ice', 'Seething Song'}
    choose(s, [])
    settle(s)
    assert set(s.state.zones['p1:library']).isdisjoint(old)
    assert mana_pool(s, 'p1') == {}
    roundtrip(s)


def test_found_bolt_must_be_cast_then_library_shuffles_before_spell_resolves(cards):
    s, source, _ = setup(cards, ['Lightning Bolt'])
    bolt = put(s, 'Lightning Bolt', 'library')
    d = resolve_search(s, source)
    assert bolt.id in {o.id for o in d.options}
    old = set(s.state.zones['p1:library']) - {bolt.id}
    choose(s, [bolt.id])
    d = s.state.rules.decision
    assert d and d.min_choices == 1
    with pytest.raises(ActionError):
        choose(s, [])
    choose(s, [bolt.id])
    d = s.state.rules.decision
    assert d, s.state.rules
    assert any(o.id == 'p2' for o in d.options)
    choose(s, ['p2'])
    assert s.state.cards[bolt.id].zone == 'stack'
    assert set(s.state.zones['p1:library']).isdisjoint(old)
    assert s.state.players['p2'].life == 40
    settle(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_cage_prevents_casting_found_card_but_it_stays_in_library_and_shuffles(cards):
    s, source, _ = setup(cards, ['Lightning Bolt', "Grafdigger's Cage"])
    bolt = put(s, 'Lightning Bolt', 'library')
    put(s, "Grafdigger's Cage", 'battlefield')
    resolve_search(s, source)
    old = set(s.state.zones['p1:library'])
    choose(s, [bolt.id])
    settle(s)
    assert s.state.players['p2'].life == 40
    assert set(s.state.zones['p1:library']).isdisjoint(old)
    assert any(s.state.cards[c].name == 'Lightning Bolt' for c in s.state.zones['p1:library'])
    roundtrip(s)


def test_blue_half_of_eligible_red_split_card_can_be_cast(cards):
    s, source, host = setup(cards, ['Fire // Ice'])
    split = put(s, 'Fire // Ice', 'library')
    resolve_search(s, source)
    choose(s, [split.id])
    d = s.state.rules.decision
    assert d and f'{split.id}@1' in {o.id for o in d.options}
    choose(s, [f'{split.id}@1'])
    d = s.state.rules.decision
    assert d and host.id in {o.id for o in d.options}
    choose(s, [host.id])
    assert s.state.cards[split.id].zone == 'stack'
    settle(s)
    assert s.state.cards[host.id].tapped
    roundtrip(s)


def test_source_can_leave_after_activation_without_stopping_search(cards):
    s, source, _ = setup(cards, ['Lightning Bolt'])
    put(s, 'Lightning Bolt', 'library')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    d = s.state.rules.decision
    assert d and 'Search' in d.prompt
    choose(s, [])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_opposition_agent_redirected_found_card_cannot_be_cast_by_sunforger(cards):
    s, source, _ = setup(cards, ['Lightning Bolt', 'Opposition Agent'])
    bolt = put(s, 'Lightning Bolt', 'library')
    agent = put(s, 'Opposition Agent', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[agent.id], player='p2')
    d = resolve_search(s, source)
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[bolt.id])
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    assert s.state.players['p2'].life == 40
    assert any(g.card == bolt.id and g.player == 'p2' for g in s.state.rules.permissions)
    roundtrip(s)


def test_cancelling_targets_reoffers_required_cast_without_reshuffling_or_refunding_unattach(cards):
    from app.game.rules_state import cancelable

    s, source, _ = setup(cards, ['Lightning Bolt'])
    bolt = put(s, 'Lightning Bolt', 'library')
    resolve_search(s, source)
    choose(s, [bolt.id])
    choose(s, [bolt.id])
    d = s.state.rules.decision
    assert d and cancelable(d)
    library = list(s.state.zones['p1:library'])
    choose(s, ['cancel'])
    d = s.state.rules.decision
    assert d and d.min_choices == 1 and bolt.id in {o.id for o in d.options}
    assert list(s.state.zones['p1:library']) == library
    assert s.state.cards[source.id].attached_to is None and mana_pool(s, 'p1') == {}
    choose(s, [bolt.id])
    choose(s, ['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_free_fling_pays_mandatory_sacrifice_cost(cards):
    s, source, host = setup(cards, ['Fling'])
    fling = put(s, 'Fling', 'library')
    resolve_search(s, source)
    choose(s, [fling.id])
    choose(s, [fling.id])
    choose(s, ['p2'])
    d = s.state.rules.decision
    if d is not None:
        assert host.id in {o.id for o in d.options}
        choose(s, [host.id])
    assert s.state.cards[host.id].zone == 'p1:graveyard'
    settle(s)
    assert s.state.players['p2'].life == 38
    roundtrip(s)


def test_mandatory_cost_with_no_creature_leaves_fling_in_library_and_shuffles(cards):
    s, source, host = setup(cards, ['Fling'])
    fling = put(s, 'Fling', 'library')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    act(s, 'p1', type='move', card_ids=[host.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    library = set(s.state.zones['p1:library'])
    choose(s, [fling.id])
    settle(s)
    assert set(s.state.zones['p1:library']).isdisjoint(library)
    assert any(s.state.cards[c].name == 'Fling' for c in s.state.zones['p1:library'])
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_no_legal_targets_leaves_found_card_in_library_then_shuffles(cards):
    s, source, _ = setup(cards, ['Reckless Rage'])
    spell = put(s, 'Reckless Rage', 'library')
    resolve_search(s, source)
    old = set(s.state.zones['p1:library'])
    choose(s, [spell.id])
    settle(s)
    assert set(s.state.zones['p1:library']).isdisjoint(old)
    assert any(s.state.cards[c].name == 'Reckless Rage' for c in s.state.zones['p1:library'])
    roundtrip(s)


def test_copied_pending_ability_searches_without_paying_another_unattach_cost(cards):
    s, source, _ = setup(cards, ['Lithoform Engine', 'Lightning Bolt'])
    engine = put(s, 'Lithoform Engine', 'battlefield')
    put(s, 'Lightning Bolt', 'library')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    original = next(cid for cid, e in s.state.rules.stack.items() if e.source_card == source.id)
    act(s, 'p1', type='activate_ability', card_id=engine.id, ability=0, targets=[original])
    searches = 0
    for _ in range(6):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        assert 'Search' in d.prompt
        searches += 1
        choose(s, [])
    assert searches == 2 and s.state.cards[source.id].attached_to is None
    assert mana_pool(s, 'p1') == {}
    roundtrip(s)


@pytest.mark.parametrize('kicked', [False, True])
def test_free_cast_can_pay_or_decline_optional_kicker(cards, kicked):
    s, source, _ = setup(cards, ['Burst Lightning'])
    spell = put(s, 'Burst Lightning', 'library')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    resolve_search(s, source)
    choose(s, [spell.id])
    choose(s, [spell.id])
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {'kicker:1'} and d.min_choices == 0
    choose(s, ['kicker:1'] if kicked else [])
    choose(s, ['p2'])
    settle(s)
    assert s.state.players['p2'].life == (36 if kicked else 38)
    assert mana_pool(s, 'p1') == ({} if kicked else {'C': 4})
    roundtrip(s)


def test_free_x_spell_uses_zero_and_does_not_ask_to_pay_x(cards):
    s, source, _ = setup(cards, ['Comet Storm'])
    spell = put(s, 'Comet Storm', 'library')
    resolve_search(s, source)
    choose(s, [spell.id])
    choose(s, [spell.id])
    d = s.state.rules.decision
    assert d and 'p2' in {o.id for o in d.options}
    choose(s, ['p2'])
    assert s.state.rules.stack[spell.id].x == 0
    settle(s)
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_pending_ability_keeps_activating_player_after_equipment_control_changes(cards):
    s, source, _ = setup(cards, ['Lightning Bolt'])
    put(s, 'Lightning Bolt', 'library')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1' and 'Search' in d.prompt
    choose(s, [])
    settle(s)
    assert s.state.cards[source.id].controller == 'p2'
    roundtrip(s)


def test_unattach_can_be_paid_from_an_opponents_creature(cards):
    s, source, host = setup(cards, ['Lightning Bolt'])
    put(s, 'Lightning Bolt', 'library')
    act(s, 'p1', type='set_controller', card_ids=[host.id], player='p2')
    resolve_search(s, source)
    choose(s, [])
    settle(s)
    assert s.state.cards[host.id].controller == 'p2' and s.state.cards[source.id].attached_to is None
    roundtrip(s)


def test_selected_mdfc_only_offers_its_spell_face_without_land_play(cards):
    s, source, _ = setup(cards, ['Valakut Awakening // Valakut Stoneforge'])
    spell = put(s, 'Valakut Awakening // Valakut Stoneforge', 'library')
    resolve_search(s, source)
    choose(s, [spell.id])
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {f'{spell.id}@0'}
    choose(s, [f'{spell.id}@0'])
    settle(s)
    d = s.state.rules.decision
    if d is not None:
        assert d.min_choices == 0
        choose(s, [])
        settle(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('pooled', [False, True])
def test_required_tax_payment_can_decline_mana_abilities_but_must_use_sufficient_pool(cards, pooled):
    s, source, _ = setup(cards, ['Lightning Bolt', 'Thorn of Amethyst', 'Mountain'])
    spell = put(s, 'Lightning Bolt', 'library')
    put(s, 'Thorn of Amethyst', 'battlefield')
    land = put(s, 'Mountain', 'battlefield')
    if pooled:
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    resolve_search(s, source)
    choose(s, [spell.id])
    choose(s, [spell.id])
    choose(s, ['p2'])
    if pooled:
        assert s.state.cards[spell.id].zone == 'stack'
    else:
        d = s.state.rules.decision
        assert d and d.resume['step'] == 'pay_mana'
        assert any(o.id == 'cancel' and 'Decline' in o.label for o in d.options)
        choose(s, ['cancel'])
    settle(s)
    assert s.state.players['p2'].life == (37 if pooled else 40)
    assert not s.state.cards[land.id].tapped and mana_pool(s, 'p1') == {}
    if not pooled:
        assert any(s.state.cards[c].name == 'Lightning Bolt' for c in s.state.zones['p1:library'])
    roundtrip(s)


def test_hidden_quality_mandatory_cost_may_be_declined_even_when_card_is_present(cards):
    s, source, _ = setup(cards, ['Surge of Strength', 'Lightning Bolt'])
    spell = put(s, 'Surge of Strength', 'library')
    red = put(s, 'Lightning Bolt', 'hand')
    resolve_search(s, source)
    choose(s, [spell.id])
    d = s.state.rules.decision
    assert d and d.min_choices == 0 and spell.id in {o.id for o in d.options}
    choose(s, [])
    settle(s)
    assert s.state.cards[red.id].zone == 'p1:hand'
    assert any(s.state.cards[c].name == 'Surge of Strength' for c in s.state.zones['p1:library'])
    roundtrip(s)


def test_no_cards_in_hand_makes_generic_discard_additional_cost_impossible(cards):
    s, source, _ = setup(cards, ['Thrill of Possibility'])
    spell = put(s, 'Thrill of Possibility', 'library')
    hand = list(s.state.zones['p1:hand'])
    if hand:
        act(s, 'p1', type='move', card_ids=hand, to={'player': 'p1', 'zone': 'graveyard'})
    resolve_search(s, source)
    choose(s, [spell.id])
    settle(s)
    assert s.state.rules.decision is None
    assert any(s.state.cards[c].name == 'Thrill of Possibility' for c in s.state.zones['p1:library'])
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_lightning_axe_mandatory_either_cost_uses_locked_mana_payment(cards, pay):
    s, source, host = setup(cards, ['Lightning Axe'])
    spell = put(s, 'Lightning Axe', 'library')
    hand = list(s.state.zones['p1:hand'])
    if hand:
        act(s, 'p1', type='move', card_ids=hand, to={'player': 'p1', 'zone': 'graveyard'})
    if pay:
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 5})
    resolve_search(s, source)
    choose(s, [spell.id])
    choose(s, [spell.id])
    choose(s, [host.id])
    if not pay:
        assert s.state.rules.decision.resume['step'] == 'pay_mana'
        choose(s, ['cancel'])
    settle(s)
    assert s.state.cards[host.id].zone == ('p1:graveyard' if pay else 'p1:battlefield')
    assert mana_pool(s, 'p1') == {}
    roundtrip(s)


def test_required_mana_decline_resumes_in_a_fresh_python_process(cards, tmp_path):
    import subprocess
    import sys

    s, source, _ = setup(cards, ['Lightning Bolt', 'Thorn of Amethyst', 'Mountain'])
    spell = put(s, 'Lightning Bolt', 'library')
    put(s, 'Thorn of Amethyst', 'battlefield')
    land = put(s, 'Mountain', 'battlefield')
    resolve_search(s, source)
    choose(s, [spell.id])
    choose(s, [spell.id])
    choose(s, ['p2'])
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    saved = tmp_path / 'required-cast.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved, db, land = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
d = s.state.rules.decision
s.perform(d.player, {'type':'choose', 'decision_id':d.id, 'option_ids':['cancel']})
assert s.state.rules.free_cast_then is None and s.state.rules.decision is None
assert s.state.players['p2'].life == 40 and not s.state.cards[land].tapped
assert any(s.state.cards[c].name == 'Lightning Bolt' for c in s.state.zones['p1:library'])
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
assert GameState.model_validate_json(s.state.model_dump_json()).model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), land.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
