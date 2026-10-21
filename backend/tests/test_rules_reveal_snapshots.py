"""Canonical revealed information, native damage/draw/mill, and later choices."""
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
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / 'fixtures/reveal_snapshots_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='rvs', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', [c['name'] for c in DATA[:11]])
def test_full_first(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def mana(s):
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 20, 'U': 6, 'R': 6, 'G': 6})


def cast(s, name, targets=()):
    source = put(s, name, 'hand')
    mana(s)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=list(targets))
    settle(s)
    return source


@pytest.mark.parametrize('land,damage', [('Mountain', 2), ('Forest', 1)])
def test_charbelcher_counts_nonlands_and_mountain_double(cards, land, damage):
    s = table(cards, ['Goblin Charbelcher', land, 'Sol Ring'])
    source = put(s, 'Goblin Charbelcher', 'battlefield')
    put(s, land, 'library')
    ring = put(s, 'Sol Ring', 'library')
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 40 - damage
    assert s.state.cards[ring.id].zone == 'p1:library'
    assert all(not s.state.cards[c].revealed_to for c in s.state.zones['p1:library'])
    roundtrip(s)


@pytest.mark.parametrize('land', [False, True])
def test_eruption_native_damage_or_original_spell_return(cards, land):
    s = table(cards, ['Cerebral Eruption'], ['Counterspell', 'Grizzly Bears'], ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    put(s, 'Island' if land else 'Counterspell', 'library', 'p2')
    source = cast(s, 'Cerebral Eruption', ['p2'])
    assert s.state.players['p2'].life == (40 if land else 38)
    assert s.state.cards[bear.id].zone == ('p2:battlefield' if land else 'p2:graveyard')
    assert s.state.cards[other.id].zone == 'p3:battlefield'
    assert s.state.cards[other.id].damage == 0
    assert s.state.cards[source.id].zone == ('p1:hand' if land else 'p1:graveyard')
    assert all(not s.state.cards[c].revealed_to for c in s.state.zones['p2:library'])
    roundtrip(s)


def test_chroma_counts_mana_symbols_not_cards_or_colors(cards):
    s = table(cards, ['Sanity Grinding', 'Counterspell', 'Sol Ring'])
    put(s, 'Sol Ring', 'library')
    put(s, 'Counterspell', 'library')
    cast(s, 'Sanity Grinding', ['p2'])
    assert len(s.state.zones['p2:graveyard']) == 2
    assert all(not s.state.cards[c].revealed_to for c in s.state.zones['p1:library'])
    roundtrip(s)


@pytest.mark.parametrize('same', [False, True])
def test_candles_actual_native_draw_or_same_name_graveyard(cards, same):
    s = table(cards, ['Candles of Leng', 'Sol Ring', 'Sol Ring', 'Grizzly Bears'])
    source = put(s, 'Candles of Leng', 'battlefield')
    rings = [c for c in s.state.cards.values() if c.name == 'Sol Ring']
    act(s, 'p1', type='move', card_ids=[rings[0].id], to={'player': 'p1', 'zone': 'library'}, position='top')
    act(s, 'p1', type='move', card_ids=[rings[1].id], to={'player': 'p1', 'zone': 'graveyard' if same else 'hand'})
    before = s.state.rules.turn_log.drew.get('p1', 0)
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    settle(s)
    assert s.state.cards[rings[0].id].zone == ('p1:graveyard' if same else 'p1:hand')
    assert s.state.rules.turn_log.drew.get('p1', 0) == before + (not same)
    roundtrip(s)


def test_trepanation_actual_equip_attack_counts_found_land(cards):
    from app.rules.plan import Plan
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Trepanation Blade', 'Grizzly Bears', 'Fervor'], ['Sol Ring'])
    source = put(s, 'Trepanation Blade', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Fervor', 'battlefield')
    ring = put(s, 'Sol Ring', 'library', 'p2')
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[bear.id])
    settle(s)
    assert s.state.cards[source.id].attached_to == bear.id
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    settle(s)
    assert s.state.cards[ring.id].zone == 'p2:graveyard'
    assert len(s.state.zones['p2:graveyard']) == 2
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).pt == (4, 2)
    roundtrip(s)


def test_blast_no_cast_target_then_native_reflexive_target(cards):
    s = table(cards, ['Calibrated Blast', 'Siege Mastodon'])
    found = put(s, 'Siege Mastodon', 'library')
    source = cast(s, 'Calibrated Blast')
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    d = s.state.rules.decision
    assert d is not None and 'p2' in {o.id for o in d.options}
    pick(s, ['p2'])
    settle(s)
    assert s.state.players['p2'].life == 35
    assert s.state.cards[found.id].zone == 'p1:library'
    roundtrip(s)


def test_whistle_hand_move_then_distinct_reflexive_creature_target(cards):
    s = table(cards, ["Yuna's Whistle", 'Siege Mastodon', 'Grizzly Bears', 'Llanowar Elves'])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    found = put(s, 'Siege Mastodon', 'library')
    source = cast(s, "Yuna's Whistle")
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[found.id].zone == 'p1:hand'
    d = s.state.rules.decision
    assert d is not None and {bear.id, elf.id} <= {o.id for o in d.options}
    pick(s, [elf.id])
    settle(s)
    assert s.state.cards[elf.id].counters.get('+1/+1') == 5
    assert not s.state.cards[bear.id].counters
    roundtrip(s)


def test_naya_original_cast_entry_sum_of_each_library_top(cards):
    s = table(cards, ['Naya Soulbeast', 'Grizzly Bears'], ['Sol Ring'], ['Counterspell'])
    put(s, 'Grizzly Bears', 'library')
    put(s, 'Sol Ring', 'library', 'p2')
    put(s, 'Counterspell', 'library', 'p3')
    source = cast(s, 'Naya Soulbeast')
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].counters.get('+1/+1') == 5
    assert all(not s.state.cards[c].revealed_to for p in ['p1', 'p2', 'p3'] for c in s.state.zones[f'{p}:library'])
    roundtrip(s)


@pytest.mark.parametrize('all_creatures', [False, True])
def test_preserve_actual_upkeep_and_all_card_condition(cards, all_creatures):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Game Preserve', 'Grizzly Bears'], ['Grizzly Bears', 'Sol Ring'], ['Grizzly Bears'])
    put(s, 'Game Preserve', 'battlefield')
    to_phase(s, 'upkeep', turn=4)
    bears = [put(s, 'Grizzly Bears', 'library', p) for p in ['p1', 'p2', 'p3']]
    if not all_creatures:
        put(s, 'Sol Ring', 'library', 'p2')
    settle(s)
    for bear in bears:
        assert s.state.cards[bear.id].zone == f'{bear.owner}:' + ('battlefield' if all_creatures else 'library')
    roundtrip(s)


@pytest.mark.parametrize('creature', [False, True])
def test_raid_actual_reveal_entry_or_graveyard_and_delayed_sacrifice(cards, creature):
    from app.rules.plan import Plan
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Impromptu Raid', 'Grizzly Bears', 'Sol Ring'])
    source = put(s, 'Impromptu Raid', 'battlefield')
    found = put(s, 'Grizzly Bears' if creature else 'Sol Ring', 'library')
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    settle(s)
    assert s.state.cards[found.id].zone == ('p1:battlefield' if creature else 'p1:graveyard')
    if creature:
        assert 'haste' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[found.id]).keywords
        to_phase(s, 'end')
        settle(s)
        assert s.state.cards[found.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('found_artifact', [False, True])
def test_dissector_actual_x_bounded_reveal_entry_and_self_sacrifice(cards, found_artifact):
    s = table(cards, ['Thought Dissector'], ['Sol Ring'])
    source = put(s, 'Thought Dissector', 'battlefield')
    ring = put(s, 'Sol Ring', 'library' if found_artifact else 'hand', 'p2')
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=2, targets=['p2'])
    settle(s)
    assert s.state.cards[source.id].zone == ('p1:graveyard' if found_artifact else 'p1:battlefield')
    if found_artifact:
        assert s.state.cards[ring.id].zone == 'p1:battlefield'
        assert s.state.cards[ring.id].owner == 'p2'
    else:
        assert len(s.state.zones['p2:graveyard']) == 2
    roundtrip(s)


def test_cold_whistle_reflexive_target_after_revealed_card_changed_zone(cards, tmp_path):
    from tests.test_rules_reveal_outcomes import cold_answer

    s = table(cards, ["Yuna's Whistle", 'Siege Mastodon', 'Grizzly Bears', 'Llanowar Elves'])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    found = put(s, 'Siege Mastodon', 'library')
    cast(s, "Yuna's Whistle")
    assert s.state.cards[found.id].zone == 'p1:hand'
    # The revealed object no longer exists in its library incarnation when the
    # separate reflexive ability chooses its target; the recorded value is five.
    s = cold_answer(s, cards, tmp_path, [elf.id])
    assert s.state.cards[elf.id].counters.get('+1/+1') == 5
    assert not s.state.cards[bear.id].counters
    roundtrip(s)


@pytest.mark.parametrize('name', ['Calibrated Blast', "Yuna's Whistle"])
def test_no_qualifying_card_does_not_create_reflexive_trigger(cards, name):
    s = table(cards, [name])
    cast(s, name)
    assert not s.state.zones['stack']
    assert s.state.rules.decision is None
    assert s.state.players['p2'].life == 40
    assert all(not s.state.cards[c].revealed_to for c in s.state.zones['p1:library'])
    roundtrip(s)


def test_dissector_zero_reveals_nothing_and_does_not_sacrifice(cards):
    s = table(cards, ['Thought Dissector'], ['Sol Ring'])
    source = put(s, 'Thought Dissector', 'battlefield')
    ring = put(s, 'Sol Ring', 'library', 'p2')
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, x_value=0, targets=['p2'])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[ring.id].zone == 'p2:library'
    assert not s.state.cards[ring.id].revealed_to
    roundtrip(s)


def test_cold_charbelcher_bottom_order_hides_revealed_cards(cards, tmp_path):
    from tests.test_rules_reveal_outcomes import cold_answer

    s = table(cards, ['Goblin Charbelcher', 'Mountain', 'Sol Ring'])
    source = put(s, 'Goblin Charbelcher', 'battlefield')
    put(s, 'Mountain', 'library')
    put(s, 'Sol Ring', 'library')
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=['p2'])
    # Do not auto-answer the private ordering choice.
    for _ in range(12):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    d = s.state.rules.decision
    assert d is not None and d.kind == 'order'
    assert s.state.players['p2'].life == 38
    s = cold_answer(s, cards, tmp_path, [o.id for o in d.options])
    assert all(not s.state.cards[c].revealed_to for c in s.state.zones['p1:library'])
    roundtrip(s)


def test_chroma_counts_hybrid_phyrexian_and_split_card_symbols(cards):
    s = table(cards, ['Sanity Grinding', 'Overbeing of Myth', 'Gitaxian Probe', 'Fire // Ice'])
    for name in ['Overbeing of Myth', 'Gitaxian Probe', 'Fire // Ice']:
        put(s, name, 'library')
    before = len(s.state.zones['p2:library'])
    cast(s, 'Sanity Grinding', ['p2'])
    assert len(s.state.zones['p2:library']) == before - 7
    assert all(not s.state.cards[c].revealed_to for c in s.state.zones['p1:library'])
    roundtrip(s)


def test_candles_otherwise_is_a_replaceable_draw(cards):
    s = table(cards, ['Candles of Leng', 'Abundance', 'Sol Ring'])
    source = put(s, 'Candles of Leng', 'battlefield')
    put(s, 'Abundance', 'battlefield')
    ring = put(s, 'Sol Ring', 'library')
    drawn = s.state.rules.turn_log.drew.get('p1', 0)
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and 'decline' in {o.id for o in d.options}
    pick(s, [next(o.id for o in d.options if o.id != 'decline')])
    pick(s, ['nonland'])
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:hand'
    assert s.state.rules.turn_log.drew.get('p1', 0) == drawn
    assert all(not s.state.cards[c].revealed_to for c in s.state.zones['p1:library'])
    roundtrip(s)
