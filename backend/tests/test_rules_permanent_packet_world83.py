"""Tariff uses actual current greatest mana value and colored payment cost."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/permanent83_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, 'main1', 1)
    return s


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def cast(s, name):
    c = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'W': 1})
    act(s, 'p1', type='cast_spell', card_id=c.id, targets=[], sources=[])
    settle(s)
    return c



def test_prepared_native_departures_in_distinct_groups_keep_remaining_world_original_interval(cards):
    from app.rules import permanent_payments83, replacements, world_durations80
    from app.rules.context import ref_of
    from app.rules.permanent_payments83 import Offer83, Packet83
    from app.rules.plan import Plan

    s = game(cards)
    left = put(s, 'Concordant Crossroads', 'battlefield')
    right = put(s, 'In the Eye of Chaos', 'battlefield', 'p2')
    remaining = put(s, 'Living Plane', 'battlefield', 'p3')
    # Exercise the native prepared-departure interface directly. No priority/SBA
    # check occurs between the individual table mutations of this one packet.
    p = Plan(s.state, 'p1', s.cards, None)
    world_durations80.before(p)
    original = p.rules.world_intervals80[p.oid(remaining)].model_copy(deep=True)
    epoch = p.rules.world_epoch80
    left_ref, right_ref = ref_of(p, left.id), ref_of(p, right.id)
    assert left_ref is not None and right_ref is not None
    packet = Packet83(rows=[
        Offer83(object=left_ref, payer='p1', name=left.name,
                routes=[replacements.Cand('prepared bottom replacement', 'library:bottom')._asdict()], chosen_route=0),
        Offer83(object=right_ref, payer='p2', name=right.name, chosen_route=0),
    ], remaining=[], life=0, before=p.freeze_departures([left.id, right.id]))
    permanent_payments83.commit(p, {'controller': 'p1'}, {'packet': packet.model_dump(mode='json'), 'batch_start': p.rules.batch})
    assert p.world_depth80 == 0
    assert p.rules.world_epoch80 == epoch
    assert set(p.rules.world_intervals80) == {p.oid(remaining)}
    assert p.rules.world_intervals80[p.oid(remaining)] == original
    assert p.state.cards[left.id].zone == 'p1:library'
    assert p.state.cards[right.id].zone == 'p2:graveyard'
    changes = [e for e in p.rules.events if e.kind == 'zone_change' and e.card in {left.id, right.id}]
    assert len({e.batch for e in changes[-2:]}) == 1
    assert not world_durations80.dying(p)
