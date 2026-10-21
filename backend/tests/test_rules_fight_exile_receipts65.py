"""Named opponent fight targets retain exile replacements regardless of actual damage."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast

NAMES = ['Mawloc', 'Unnatural Aggression', 'Faunsbane Troll', 'Burn from Within']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['exile_outcomes42_cards.json', 'exile_cast_outcomes45_cards.json', 'fight_exile_receipts65_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='fe65', number=str(i), **{k: v for k, v in c.items() if k not in {'name', 'set_code'}})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *NAMES, 'Fiery Annihilation', 'Forest', 'Sol Ring', 'Llanowar Elves', 'Lightning Bolt', 'Darksteel Myr', 'Healing Salve', 'Murder', 'Bonesplitter', 'Unsummon', "Mishra's Factory", 'Song of the Dryads', 'Stone Rain', 'Cloudshift', 'Blossoming Defense', 'Magnetic Theft', 'Reverberate', 'Torch the Tower', 'Centaur Courser', 'Jace Beleren', "Kumano's Blessing", 'Kumano Faces Kakkazan // Etching of Kumano', 'Hermetic Study', 'Naturalize', 'Pyroclasm', 'Control Magic', 'Act of Treason', 'Dominate', 'Regrowth')


@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_unnatural_fight_exiles_only_opposing_target_even_when_both_die(cards):
    s = setup(cards)
    own = put(s, 'Grizzly Bears', 'battlefield')
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Unnatural Aggression', targets=[own.id, opposing.id], target_counts=[1, 1])
    assert s.state.cards[own.id].zone == 'p1:graveyard'
    assert s.state.cards[opposing.id].zone == 'p2:exile'
    roundtrip(s)


def test_mawloc_actual_x_counters_and_optional_fight_exile(cards):
    s = setup(cards)
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    source = cast(s, 'Mawloc', x_value=3)
    d = s.state.rules.decision
    assert d and d.max_choices == 1 and d.min_choices == 0
    answer(s, [opposing.id])
    settle(s)
    assert s.state.cards[source.id].counters.get('+1/+1') == 3
    assert s.state.cards[opposing.id].zone == 'p2:exile'
    roundtrip(s)


def test_mawloc_can_decline_all_targets(cards):
    s = setup(cards)
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Mawloc', x_value=3)
    answer(s, [])
    assert s.state.cards[opposing.id].zone == 'p2:battlefield'
    roundtrip(s)




def test_unnatural_legal_opponent_still_watched_when_own_fighter_removed(cards):
    from tests.test_rules_conditional_prevention import cast as pending_cast

    s = setup(cards)
    own = put(s, 'Grizzly Bears', 'battlefield')
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    pending_cast(s, 'Unnatural Aggression', targets=[own.id, opposing.id], target_counts=[1, 1], resolve=False)
    pending_cast(s, 'Lightning Bolt', targets=[own.id])
    assert s.state.cards[opposing.id].zone == 'p2:battlefield'
    assert s.state.cards[opposing.id].damage == 0
    pending_cast(s, 'Lightning Bolt', targets=[opposing.id])
    assert s.state.cards[opposing.id].zone == 'p2:exile'
    roundtrip(s)


def test_faunsbane_actual_monster_role_cost_fight_and_exile(cards):
    s = setup(cards)
    source = cast(s, 'Faunsbane Troll')
    roles = [c for c in s.state.cards.values() if c.is_token and c.attached_to == source.id]
    assert len(roles) == 1
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[opposing.id],
        sources=[])
    if s.state.rules.decision is not None:
        answer(s, [roles[0].id])
    settle(s)
    assert s.state.cards[opposing.id].zone == 'p2:exile'
    assert not s.state.cards.get(roles[0].id) or not s.state.cards[roles[0].id].zone.endswith(':battlefield')
    roundtrip(s)


def test_mawloc_five_actual_x_counters_draws_and_can_decline_fight(cards):
    s = setup(cards)
    before = len(s.state.zones['p1:hand'])
    source = cast(s, 'Mawloc', x_value=5)
    while s.state.rules.decision is not None:
        answer(s, [])
    settle(s)
    assert s.state.cards[source.id].counters.get('+1/+1') == 5
    assert len(s.state.zones['p1:hand']) == before + 1
    roundtrip(s)


def test_burn_actual_damage_removes_indestructible_and_exiles_lethal_creature(cards):
    s = setup(cards)
    opposing = put(s, 'Darksteel Myr', 'battlefield', 'p2')
    cast(s, 'Burn from Within', targets=[opposing.id], x_value=2)
    assert s.state.cards[opposing.id].zone == 'p2:exile'
    roundtrip(s)


def test_burn_zero_damage_applies_neither_removal_nor_exile_replacement(cards):
    s = setup(cards)
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Burn from Within', targets=[opposing.id], x_value=0)
    cast(s, 'Murder', targets=[opposing.id])
    assert s.state.cards[opposing.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_burn_prevented_damage_leaves_indestructible_and_no_exile_receipt(cards):
    from tests.test_rules_conditional_prevention import cast as preventing_cast

    s = setup(cards)
    opposing = put(s, 'Darksteel Myr', 'battlefield', 'p2')
    preventing_cast(s, 'Healing Salve', targets=[opposing.id], modes=[1], pid='p2')
    cast(s, 'Burn from Within', targets=[opposing.id], x_value=3)
    cast(s, 'Murder', targets=[opposing.id])
    assert s.state.cards[opposing.id].zone == 'p2:battlefield'
    assert s.state.cards[opposing.id].damage == 0
    roundtrip(s)






def test_genuine_cold_unresolved_fight_keeps_named_opponent_exile_replacement(cards, tmp_path):
    import subprocess
    import sys

    from tests.test_rules_conditional_prevention import cast as pending_cast

    s = setup(cards)
    own = put(s, 'Grizzly Bears', 'battlefield')
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    pending_cast(s, 'Unnatural Aggression', targets=[own.id, opposing.id], target_counts=[1, 1], resolve=False)
    saved = tmp_path / 'fight65.json'
    saved.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_look import settle
p=Path(sys.argv[1])
repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:graveyard'
assert s.state.cards[sys.argv[4]].zone=='p2:exile'
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), own.id, opposing.id],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_named_creature_replacement_follows_original_object_after_it_ceases_creature(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority

    s = setup(cards)
    own = put(s, 'Llanowar Elves', 'battlefield')
    opposing = put(s, "Mishra's Factory", 'battlefield', 'p2')
    mana(s, pid='p2', C=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=opposing.id, ability=1, sources=[])
    settle(s)
    cast(s, 'Unnatural Aggression', targets=[own.id, opposing.id], target_counts=[1, 1])
    assert s.state.cards[opposing.id].zone == 'p2:battlefield'
    cast(s, 'Song of the Dryads', targets=[opposing.id])
    cast(s, 'Stone Rain', targets=[opposing.id])
    assert s.state.cards[opposing.id].zone == 'p2:exile'
    roundtrip(s)


def test_replacement_does_not_follow_creature_that_leaves_and_returns(cards):
    from tests.test_rules_conditional_prevention import cast as cast_for_player

    s = setup(cards)
    own = put(s, 'Llanowar Elves', 'battlefield')
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Unnatural Aggression', targets=[own.id, opposing.id], target_counts=[1, 1])
    cast_for_player(s, 'Cloudshift', targets=[opposing.id], pid='p2')
    cast(s, 'Murder', targets=[opposing.id])
    assert s.state.cards[opposing.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_faunsbane_source_departure_still_watches_target_without_fighting(cards):
    from tests.test_rules_conditional_prevention import cast as response_cast

    s = setup(cards)
    source = cast(s, 'Faunsbane Troll')
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[opposing.id], sources=[])
    if s.state.rules.decision is not None:
        answer(s, [s.state.rules.decision.options[0].id])
    response_cast(s, 'Murder', targets=[source.id])
    assert s.state.cards[opposing.id].zone == 'p2:battlefield'
    assert s.state.cards[opposing.id].damage == 0
    cast(s, 'Murder', targets=[opposing.id])
    assert s.state.cards[opposing.id].zone == 'p2:exile'
    roundtrip(s)
