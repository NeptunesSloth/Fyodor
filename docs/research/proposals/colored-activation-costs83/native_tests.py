"""Native conditional colored activation reductions with frozen entry keywords."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Flying Drone", "Kami of Jealous Thirst"]
DATA = json.loads((Path(__file__).parent / "fixtures/colored_activation_costs83_cards.json").read_text())


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name):
    ns = [c["name"] for c in DATA] * 3
    s = table(cards, ns, ns, ns)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True, response="on")
    to_phase(s, "main1", 4)
    source = put(s, name, "battlefield")
    s.state.rules.controlled_since[source.id].turn = 0
    return s, source


def spell(s, name, mana=None, targets=()):
    c = put(s, name, "hand")
    wait_priority(s, 'p1')
    if mana:
        act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=c.id, sources=[], targets=list(targets))
    answer(s)
    return c


def activate(s, source, mana, expected):
    wait_priority(s, 'p1')
    if mana:
        act(s, 'p1', type='add_mana', player='p1', mana=mana)
    index = next(a.index for a in Plan(s.state, 'p1', s.cards, None).ch(source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, sources=[])
    ability = next(c for c in s.state.cards.values() if c.zone == 'stack' and c.ability is not None)
    paid = s.state.rules.payments[s.state.rules.object_id(ability.id)]
    from app.rules import mana as M

    assert paid.mana_spent == mana
    required = M.parse_cost(expected)
    assert sum(paid.mana_spent.values()) == required.generic + len(required.colored)
    assert sum(s.state.players['p1'].mana.values()) == 0
    return ability


def test_canonical_both(cards):
    assert all(coverage.of_card_data(cards.resolve(n)).level == 'FULL' for n in NAMES)


def test_kami_two_draws_does_not_discount(cards):
    s, source = setup(cards, NAMES[1])
    spell(s, 'Opt', {'U': 1})
    assert s.state.rules.turn_log.drew['p1'] == 2
    activate(s, source, {'C': 4, 'B': 1}, '{4}{B}')
    answer(s)
    assert s.state.players['p1'].life == 42 and s.state.players['p2'].life == 38


def test_kami_three_actual_draws_free_and_once_each_turn(cards):
    s, source = setup(cards, NAMES[1])
    spell(s, 'Divination', {'C': 2, 'U': 1})
    assert s.state.rules.turn_log.drew['p1'] == 3
    activate(s, source, {}, '{0}')
    answer(s)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        activate(s, source, {}, '{0}')
    assert s.state.model_dump_json() == before


@pytest.mark.parametrize('name', NAMES)
def test_qualifying_reduction_keeps_actual_activation_tax(cards, name):
    s, source = setup(cards, name)
    if name == NAMES[1]:
        spell(s, 'Divination', {'C': 2, 'U': 1})
    else:
        spell(s, 'Ornithopter')
    put(s, 'Suppression Field', 'battlefield')
    activate(s, source, {'C': 2}, '{2}')


def test_drone_own_entry_alone_does_not_qualify(cards):
    s, source = setup(cards, NAMES[0])
    activate(s, source, {'C': 1, 'U': 1}, '{1}{U}')
    answer(s)


def test_drone_actual_other_flyer_entry_and_draw_discard(cards):
    s, source = setup(cards, NAMES[0])
    spell(s, 'Ornithopter')
    entry = next(e for e in s.state.rules.turn_log.entered if e.card != source.id and 'flying' in (e.keywords83 or []))
    assert 'Creature' in entry.types
    before = len(s.state.zones['p1:graveyard'])
    activate(s, source, {}, '{0}')
    answer(s)
    assert len(s.state.zones['p1:graveyard']) == before + 1


def test_drone_flying_lost_after_entry_still_qualifies(cards):
    s, source = setup(cards, NAMES[0])
    flyer = spell(s, 'Ornithopter')
    spell(s, 'Turn to Frog', {'C': 1, 'U': 1}, [flyer.id])
    assert 'flying' not in Plan(s.state, 'p1', s.cards, None).ch(flyer).keywords
    activate(s, source, {}, '{0}')


def test_drone_flying_gained_after_entry_does_not_qualify(cards):
    s, source = setup(cards, NAMES[0])
    bear = spell(s, 'Grizzly Bears', {'C': 1, 'G': 1})
    spell(s, 'Jump', {'U': 1}, [bear.id])
    assert 'flying' in Plan(s.state, 'p1', s.cards, None).ch(bear).keywords
    activate(s, source, {'C': 1, 'U': 1}, '{1}{U}')


def test_drone_opponent_flyer_entry_does_not_qualify(cards):
    s, source = setup(cards, NAMES[0])
    put(s, 'Ornithopter', 'battlefield', 'p2')
    activate(s, source, {'C': 1, 'U': 1}, '{1}{U}')


def test_legacy_entry_keywords_unknown_preview_safe_explicit_action_guarded(cards):
    s, source = setup(cards, NAMES[0])
    flyer = spell(s, 'Ornithopter')
    entry = next(e for e in s.state.rules.turn_log.entered if e.card == flyer.id)
    entry.keywords83 = None
    s.view('p1')
    s.view('p2')
    wait_priority(s, 'p1')
    before = s.state.model_dump_json()
    index = next(a.index for a in Plan(s.state, 'p1', s.cards, None).ch(source).abilities if a.kind == 'activated')
    with pytest.raises(ActionError, match='entry-time flying history'):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, sources=[])
    assert s.state.model_dump_json() == before
