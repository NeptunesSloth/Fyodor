"""Current damage receipts determine the triggering opponent and Incinerator's cost."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast

NAMES = ['Fear of Burning Alive', "Chandra's Incinerator", 'Lightning Bolt', 'Shock',
         'Earthquake', 'Healing Salve', 'Hermetic Study', 'Platinum Emperion',
         'Giant Growth', 'Fog', 'Reclaim', 'Raging Goblin', 'Jace Beleren',
         'Forest', 'Sol Ring', 'Llanowar Elves']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['exile_outcomes42_cards.json', 'exile_cast_outcomes45_cards.json', 'relative_damage_receipts65_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='rd65', number=str(i), **{k: v for k, v in c.items() if k not in {'name', 'set_code'}})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *NAMES)


def direct_cast(s, name, targets=()):
    source = put(s, name, 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=list(targets), sources=[])
    settle(s)
    return source


def five_damage(s, target='p2'):
    mana(s, R=2)
    direct_cast(s, 'Lightning Bolt', [target])
    direct_cast(s, 'Shock', [target])
    assert not s.state.players['p1'].mana


def pay_incinerator(s, generic):
    mana(s, C=generic, R=1)
    source = direct_cast(s, "Chandra's Incinerator")
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    record = next(r for r in s.state.rules.payments.values() if r.card == source.id)
    assert record.total_cost == (f'{{{generic}}}' if generic else '') + '{R}'
    assert not s.state.players['p1'].mana
    roundtrip(s)
    return s.state.cards[source.id]


@pytest.mark.parametrize('name', ["Chandra's Incinerator"])
def test_whole_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_actual_five_noncombat_damage_reduces_to_red(cards):
    s = setup(cards)
    five_damage(s)
    assert s.state.players['p2'].life == 35
    pay_incinerator(s, 0)


def test_life_gain_does_not_reduce_actual_damage_history_discount(cards):
    from tests.test_rules_conditional_prevention import cast as cast_for_player

    s = setup(cards)
    five_damage(s)
    cast_for_player(s, 'Healing Salve', targets=['p2'], pid='p2', modes=[0])
    assert s.state.players['p2'].life == 38
    pay_incinerator(s, 0)


def test_departed_opponents_still_count_for_incinerator_cost(cards):
    s = setup(cards)
    five_damage(s)
    act(s, 'p2', type='concede')
    from app.rules.plan import live_players

    assert 'p2' not in live_players(s.state)
    pay_incinerator(s, 0)


def test_damage_from_opponents_source_still_reduces_caster_cost(cards):
    from tests.test_rules_conditional_prevention import cast as cast_for_player

    s = setup(cards)
    cast_for_player(s, 'Lightning Bolt', targets=['p3'], pid='p2')
    assert s.state.players['p3'].life == 37
    pay_incinerator(s, 2)


def test_own_player_damage_does_not_reduce_cost(cards):
    s = setup(cards)
    five_damage(s, 'p1')
    mana(s, C=4, R=1)
    source = put(s, "Chandra's Incinerator", 'hand')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    assert s.state.model_dump_json() == before
    mana(s, C=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)



@pytest.mark.parametrize('recipient', ['p2', 'p3'])
def test_native_incinerator_trigger_uses_damaged_player_and_damage_amount(cards, recipient):
    s = setup(cards)
    cast(s, "Chandra's Incinerator")
    target = put(s, 'Grizzly Bears', 'battlefield', recipient)
    other = put(s, 'Grizzly Bears', 'battlefield', 'p3' if recipient == 'p2' else 'p2')
    cast(s, 'Lightning Bolt', targets=[recipient])
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'trigger_target'
    assert [o.id for o in d.options] == [target.id]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == recipient + ':graveyard'
    assert s.state.cards[other.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_opponents_damage_source_does_not_trigger_your_incinerator(cards):
    from tests.test_rules_conditional_prevention import cast as cast_for_player

    s = setup(cards)
    cast(s, "Chandra's Incinerator")
    target = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    cast_for_player(s, 'Lightning Bolt', targets=['p3'], pid='p2')
    assert s.state.rules.decision is None
    assert s.state.cards[target.id].zone == 'p3:battlefield'
    roundtrip(s)


def test_genuine_cold_incinerator_pending_target_retains_recipient(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    cast(s, "Chandra's Incinerator")
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Lightning Bolt', targets=['p2'])
    saved = tmp_path / 'incinerator65.json'
    saved.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_look import settle
p=Path(sys.argv[1])
repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision
assert d and [o.id for o in d.options]==[sys.argv[3]]
act(s,d.player,type='choose',decision_id=d.id,option_ids=[sys.argv[3]])
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p2:graveyard'
assert s.state.rules.decision is None
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), target.id],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_incinerator_combat_damage_does_not_trigger_noncombat_ability_or_discount(cards):
    from tests.test_rules_conditional_prevention import attack, damage

    s = setup(cards)
    source = cast(s, "Chandra's Incinerator")
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attack(s, [source], target='p2', turn=4)
    damage(s)
    assert s.state.players['p2'].life == 34
    assert s.state.rules.decision is None
    assert s.state.cards[victim.id].zone == 'p2:battlefield'
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'main2')
    pay_incinerator(s, 5)


def test_damage_prevention_reduces_discount_and_creates_no_trigger(cards):
    from tests.test_rules_conditional_prevention import cast as cast_for_player

    s = setup(cards)
    cast_for_player(s, 'Healing Salve', targets=['p2'], pid='p2', modes=[1])
    cast(s, 'Lightning Bolt', targets=['p2'])
    assert s.state.players['p2'].life == 40
    assert s.state.rules.decision is None
    # The cast helper leaves abundant mana: clear it before exact payment.
    s.state.players['p1'].mana.clear()
    pay_incinerator(s, 5)
