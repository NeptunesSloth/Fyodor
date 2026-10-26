"""CR 608.2c/g/h, 201.2a: counter, random mill, differently named free cast, cleanup."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/counter_random_recast_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = "Tibalt's Trickery"


def setup(cards, monkeypatch, roll=1, original='Lightning Bolt', rest=('Grizzly Bears',)):
    from app.rules import counter_random_recast
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    rolls = []

    def rolled(self, a, b):
        rolls.append((a, b))
        return roll

    monkeypatch.setattr(counter_random_recast.secrets.SystemRandom, 'randint', rolled)
    extras = [original, *rest]
    s = table(cards, extras, [NAME, 'Bruvac the Grandiloquent', 'The Water Crystal'], [])
    s.trickery_rolls = rolls
    spell = put(s, original, 'hand')
    trick = put(s, NAME, 'hand', 'p2')
    names = ['Forest'] * roll + list(rest)
    selected = []
    for name in names:
        selected.append(next(c.id for c in s.state.cards.values() if c.owner == 'p1' and c.name == name
                             and c.zone == 'p1:library' and c.id not in selected))
    others = [c for c in s.state.zones['p1:library'] if c not in selected]
    if others:
        act(s, 'p1', type='move', card_ids=others, to={'player': 'p1', 'zone': 'graveyard'})
    for cid in reversed(selected):
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'library'}, position='top')
    return s, spell, trick, selected


def cast(s, spell, trick):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority

    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, R=1, G=1, C=2, U=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id,
        **({'face': 1} if spell.name.startswith('Cosima,') else {}),
        **({'targets': ['p3']} if spell.name == 'Lightning Bolt' else {}))
    mana(s, 'p2', C=1, R=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=trick.id, targets=[spell.id])


def offer(s):
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get('step') == 'suspend_cast')
    return s.state.rules.decision


def test_trickery_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('roll', [1, 2, 3])
@pytest.mark.parametrize('accept', [False, True])
def test_random_mill_controller_free_cast_then_bottom(cards, monkeypatch, roll, accept):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, trick, selected = setup(cards, monkeypatch, roll, rest=('Forest', 'Grizzly Bears'))
    cast(s, spell, trick)
    d = offer(s)
    assert d.player == 'p1'
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert all(s.state.cards[cid].zone == 'p1:graveyard' for cid in selected[:roll])
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in selected[roll:])
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes' if accept else 'no'])
    settle(s)
    assert s.state.cards[selected[-1]].zone == ('p1:battlefield' if accept else 'p1:library')
    assert set(s.state.zones.get('p1:library', [])) == set(selected[roll:-1] if accept else selected[roll:])
    assert s.state.players['p3'].life == 40
    assert s.state.cards[trick.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_uncounterable_still_mills_and_offers_cast(cards, monkeypatch):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, trick, selected = setup(cards, monkeypatch, original='Allosaurus Shepherd')
    cast(s, spell, trick)
    d = offer(s)
    assert s.state.cards[spell.id].zone == 'stack'
    assert s.state.cards[selected[0]].zone == 'p1:graveyard'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['no'])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_no_nonland_hit_returns_all_exiled_cards(cards, monkeypatch):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, trick, selected = setup(cards, monkeypatch, rest=('Forest', 'Forest', 'Forest'))
    cast(s, spell, trick)
    settle(s)
    assert set(s.state.zones['p1:library']) == set(selected[1:])
    assert not s.state.zones.get('p1:exile')
    roundtrip(s)


def test_matching_spell_name_is_skipped_and_stays_exiled_until_cleanup(cards, monkeypatch):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, trick, selected = setup(cards, monkeypatch, rest=('Lightning Bolt', 'Grizzly Bears'))
    cast(s, spell, trick)
    d = offer(s)
    assert d.resume['card'] == selected[-1]
    assert s.state.cards[selected[1]].zone == 'p1:exile'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['no'])
    settle(s)
    assert set(s.state.zones['p1:library']) == set(selected[1:])
    roundtrip(s)


def test_library_exhausted_by_mill_does_not_draw_or_lose(cards, monkeypatch):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, trick, selected = setup(cards, monkeypatch, roll=3, rest=())
    cast(s, spell, trick)
    settle(s)
    assert not s.state.zones.get('p1:library')
    assert all(s.state.cards[cid].zone == 'p1:graveyard' for cid in selected)
    assert not s.state.rules.lost
    roundtrip(s)


def test_unpayable_mandatory_additional_cost_goes_to_bottom_without_dead_end(cards, monkeypatch):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, trick, selected = setup(cards, monkeypatch, rest=('Fling',))
    cast(s, spell, trick)
    settle(s)
    assert s.state.cards[selected[-1]].zone == 'p1:library'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_cancelling_free_cast_target_choice_finishes_cleanup(cards, monkeypatch):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, trick, selected = setup(cards, monkeypatch, original='Grizzly Bears', rest=('Lightning Bolt',))
    cast(s, spell, trick)
    d = offer(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes'])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'cast_target'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['cancel'])
    settle(s)
    assert s.state.cards[selected[-1]].zone == 'p1:library'
    assert s.state.cards[trick.id].zone == 'p2:graveyard'
    assert not s.state.rules.free_casts and s.state.rules.free_cast_then is None
    roundtrip(s)


def test_back_face_original_name_does_not_restrict_resulting_spell_face(cards, monkeypatch):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    name = 'Cosima, God of the Voyage // The Omenkeel'
    s, spell, trick, selected = setup(cards, monkeypatch, original=name, rest=(name,))
    cast(s, spell, trick)
    d = offer(s)
    assert {o.id for o in d.options} == {'yes', 'yes@1', 'no'}
    # Exiled card's front name differs from the original's back name. Casting its
    # back face with the original's name is explicitly legal (2021-02-05 ruling).
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes@1'])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert s.state.cards[selected[-1]].zone == 'p1:battlefield'
    assert chars(s, s.state.cards[selected[-1]]).name == 'The Omenkeel'
    roundtrip(s)


def test_mill_replacement_choice_resumes_without_reroll_or_countering_again(cards, monkeypatch):
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip

    # Two noncommuting replacements: (1*2)+4 = 6, while (1+4)*2 = 10.
    s, spell, trick, selected = setup(cards, monkeypatch, rest=tuple(['Forest'] * 10 + ['Grizzly Bears']))
    put(s, 'Bruvac the Grandiloquent', 'battlefield', 'p2')
    put(s, 'The Water Crystal', 'battlefield', 'p2')
    cast(s, spell, trick)
    until(s, lambda s: s.state.rules.decision is not None)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    roundtrip(s)
    settle(s)
    # settle accepts the free cast; exactly one random roll, then one replacement
    # ordering choice; either legal ordering mills6 or10, never a fresh roll.
    n = sum(s.state.cards[cid].zone == 'p1:graveyard' for cid in selected)
    assert n in (6, 10)
    assert s.trickery_rolls == [(1, 3)]
    assert s.state.cards[selected[-1]].zone == 'p1:battlefield'
    roundtrip(s)


def test_free_cast_x_is_zero_and_zero_toughness_creature_dies(cards, monkeypatch):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, trick, selected = setup(cards, monkeypatch, rest=('Hydroid Krasis',))
    cast(s, spell, trick)
    d = offer(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes'])
    settle(s)
    krasis = s.state.cards[selected[-1]]
    assert krasis.zone == 'p1:graveyard'
    assert not krasis.counters
    assert s.state.players['p1'].life == 40
    assert not s.state.zones.get('p1:library')
    assert not s.state.rules.lost
    roundtrip(s)


def test_rule_named_spell_skips_every_nonlegendary_creature_card(cards, monkeypatch):
    """Spy Kit (201.2a): a spell whose names come from a rule shares a name with any nonlegendary creature card (card_names.ANY_CREATURE)."""
    from app.rules import card_names
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle

    monkeypatch.setattr(card_names, 'reference_names', lambda ch: [card_names.ANY_CREATURE])
    s, spell, trick, selected = setup(cards, monkeypatch, rest=('Grizzly Bears', 'Lightning Bolt'))
    cast(s, spell, trick)
    d = offer(s)
    assert d.resume['card'] == selected[-1] and s.state.cards[selected[1]].zone == 'p1:exile'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['no'])
    settle(s)
    assert set(s.state.zones['p1:library']) == set(selected[1:])
