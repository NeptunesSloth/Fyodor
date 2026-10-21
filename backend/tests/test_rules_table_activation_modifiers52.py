"""Table cost modifiers preserve source, zone, activation kind and individual floors."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting, coverage, mana_units
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = [
    "Power Artifact",
    "Embalmer's Tools",
    "Convergence of Dominion",
    "Eidolon of Obstruction",
    "Boom Scholar",
    "Dragonkin Berserker",
]


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/table_activation_modifiers52_cards.json").read_text())
    ):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards, names, opponents=()):
    s = table(cards, names, opponents, [])
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="set_prefs", hold_priority=True)
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    return s


def activate(s, source, text, *, pid="p1", mana=None, targets=()):
    wait_priority(s, pid)
    if mana:
        act(s, pid, type="add_mana", player=pid, mana=mana)
    ability = next(a for a in Plan(s.state, pid, s.cards, None).ch(source).abilities if text in a.text)
    act(
        s,
        pid,
        type="activate_ability",
        card_id=source.id,
        ability=ability.index,
        sources=[],
        targets=list(targets),
    )
    answer(s)


@pytest.mark.parametrize("name", NAMES)
def test_complete_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_power_artifact_actual_untap_floor_and_zero_cost_mana_ability(cards):
    s = game(cards, ["Power Artifact", "Basalt Monolith"])
    source = put(s, "Basalt Monolith", "battlefield")
    aura = put(s, "Power Artifact", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 2})
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[source.id], sources=[])
    answer(s)
    mana_index = next(i for i, _ in casting.mana_abilities(s.state, source, cards))
    act(s, "p1", type="activate_ability", card_id=source.id, ability=mana_index)
    answer(s)
    assert source.tapped
    assert mana_units.visible_pool(s.state, "p1") == {"C": 3}
    activate(s, source, "Untap")
    assert not source.tapped and mana_units.visible_pool(s.state, "p1") == {"C": 2}
    roundtrip(s)


def test_embalmers_actual_graveyard_return_is_reduced_to_black(cards):
    s = game(cards, ["Embalmer's Tools", "Reassembling Skeleton"])
    put(s, "Embalmer's Tools", "battlefield")
    source = put(s, "Reassembling Skeleton", "graveyard")
    activate(s, source, "Return", mana={"B": 1})
    assert source.zone == "p1:battlefield" and source.tapped
    assert not s.state.players["p1"].mana
    roundtrip(s)


def test_embalmers_does_not_discount_battlefield_creature(cards):
    s = game(cards, ["Embalmer's Tools", "Spectral Sailor"])
    put(s, "Embalmer's Tools", "battlefield")
    source = put(s, "Spectral Sailor", "battlefield")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "U": 1})
    ability = next(
        a for a in Plan(s.state, "p1", cards, None).ch(source).abilities if "Draw a card" in a.text
    )
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=source.id, ability=ability.index, sources=[])
    assert s.state.model_dump_json() == before
    activate(s, source, "Draw a card", mana={"C": 1})
    assert not s.state.players["p1"].mana
    roundtrip(s)


def test_convergence_floor_and_unrestricted_reduction_can_stack_to_zero_generic(cards):
    s = game(
        cards,
        ["Convergence of Dominion", "Embalmer's Tools", "Isamaru, Hound of Konda", "Reassembling Skeleton"],
    )
    source = put(s, "Reassembling Skeleton", "graveyard")
    commander = put(s, "Isamaru, Hound of Konda", "battlefield")
    act(s, "p1", type="set_commander", card_id=commander.id, value=True)
    put(s, "Convergence of Dominion", "battlefield")
    put(s, "Embalmer's Tools", "battlefield")
    activate(s, source, "Return", mana={"B": 1})
    assert source.zone == "p1:battlefield" and not s.state.players["p1"].mana
    roundtrip(s)


def test_eidolon_adds_mana_cost_without_changing_loyalty_cost(cards):
    s = game(cards, ["Jace Beleren"], ["Eidolon of Obstruction"])
    source = put(s, "Jace Beleren", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "U": 2})
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    answer(s)
    put(s, "Eidolon of Obstruction", "battlefield", "p2")
    assert source.counters["loyalty"] == 3
    activate(s, source, "+2:", mana={"C": 1})
    assert source.counters["loyalty"] == 5 and not s.state.players["p1"].mana
    roundtrip(s)


def test_unrestricted_reduction_applies_after_floored_reduction_on_actual_generic_cost(cards):
    s = game(
        cards,
        ["Convergence of Dominion", "Embalmer's Tools", "Isamaru, Hound of Konda", "Gravestone Strider"],
        ["Grizzly Bears"],
    )
    source = put(s, "Gravestone Strider", "graveyard")
    victim = put(s, "Grizzly Bears", "graveyard", "p2")
    commander = put(s, "Isamaru, Hound of Konda", "battlefield")
    act(s, "p1", type="set_commander", card_id=commander.id, value=True)
    put(s, "Convergence of Dominion", "battlefield")
    put(s, "Embalmer's Tools", "battlefield")
    activate(s, source, "Exile this card", targets=[victim.id])
    assert source.zone == "p1:exile" and victim.zone == "p2:exile"
    assert not s.state.players["p1"].mana
    roundtrip(s)


def test_boom_does_not_reduce_itself_but_other_boom_reduces_exhaust(cards):
    s = game(cards, ["Boom Scholar"], ["Boom Scholar"])
    source = put(s, "Boom Scholar", "battlefield")
    other = put(s, "Boom Scholar", "battlefield", "p2")
    act(s, "p1", type="set_controller", card_ids=[other.id], player="p1")
    activate(s, source, "Exhaust —", mana={"C": 2, "R": 1, "G": 1})
    assert source.counters.get("+1/+1") == 2
    assert "trample" in Plan(s.state, "p1", cards, None).ch(source).keywords
    assert "trample" in Plan(s.state, "p1", cards, None).ch(other).keywords
    assert not mana_units.visible_pool(s.state, "p1")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        activate(s, source, "Exhaust —")
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_single_boom_does_not_discount_own_exhaust(cards):
    s = game(cards, ["Boom Scholar"])
    source = put(s, "Boom Scholar", "battlefield")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "R": 1, "G": 1})
    ability = next(
        a for a in Plan(s.state, "p1", cards, None).ch(source).abilities if a.text.startswith("Exhaust —")
    )
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=source.id, ability=ability.index, sources=[])
    assert s.state.model_dump_json() == before
    activate(s, source, "Exhaust —", mana={"C": 2})
    assert source.counters.get("+1/+1") == 2
    assert not mana_units.visible_pool(s.state, "p1")
    roundtrip(s)


def test_dragonkin_actual_attacked_boast_cost_and_flying_dragon_token(cards):
    from tests.test_rules_conditional_prevention import attack

    s = game(cards, ["Dragonkin Berserker", "Shivan Dragon"])
    source = put(s, "Dragonkin Berserker", "battlefield")
    put(s, "Shivan Dragon", "battlefield")
    attack(s, [source], turn=7)
    activate(s, source, "Boast —", mana={"C": 3, "R": 1})
    tokens = [c for c in s.state.cards.values() if c.token and c.zone == "p1:battlefield"]
    assert len(tokens) == 1
    token = Plan(s.state, "p1", cards, None).ch(tokens[0])
    assert token.pt == (5, 5) and "Dragon" in token.subtypes and "flying" in token.keywords
    assert not mana_units.visible_pool(s.state, "p1")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        activate(s, source, "Boast —")
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_convergence_battlefield_mill_is_not_its_own_graveyard_discount(cards):
    s = game(cards, ["Convergence of Dominion", "Isamaru, Hound of Konda"])
    source = put(s, "Convergence of Dominion", "battlefield")
    commander = put(s, "Isamaru, Hound of Konda", "battlefield")
    act(s, "p1", type="set_commander", card_id=commander.id, value=True)
    before = len(s.state.zones["p1:graveyard"])
    activate(s, source, "Mill three cards", mana={"C": 3})
    assert source.tapped and len(s.state.zones["p1:graveyard"]) == before + 3
    assert not mana_units.visible_pool(s.state, "p1")
    roundtrip(s)


@pytest.mark.parametrize("name", NAMES)
def test_true_cold_native_cost_predicate_and_payment(cards, tmp_path, name):
    import subprocess
    import sys

    from app.rules import table_activation_modifiers52

    mana = {}
    targets = []
    expected = {}
    if name == "Power Artifact":
        s = game(cards, [name, "Basalt Monolith"])
        source = put(s, "Basalt Monolith", "battlefield")
        aura = put(s, name, "hand")
        act(s, "p1", type="add_mana", player="p1", mana={"U": 2})
        act(s, "p1", type="cast_spell", card_id=aura.id, targets=[source.id], sources=[])
        answer(s)
        act(s, "p1", type="tap", card_ids=[source.id], tapped=True)
        text, mana, expected = "Untap", {"C": 1}, {"untapped": True}
    elif name == "Embalmer's Tools":
        s = game(cards, [name, "Reassembling Skeleton"])
        put(s, name, "battlefield")
        source = put(s, "Reassembling Skeleton", "graveyard")
        text, mana, expected = "Return", {"B": 1}, {"zone": "p1:battlefield", "tapped": True}
    elif name == "Convergence of Dominion":
        s = game(
            cards,
            [name, "Embalmer's Tools", "Isamaru, Hound of Konda", "Gravestone Strider"],
            ["Grizzly Bears"],
        )
        put(s, name, "battlefield")
        put(s, "Embalmer's Tools", "battlefield")
        commander = put(s, "Isamaru, Hound of Konda", "battlefield")
        act(s, "p1", type="set_commander", card_id=commander.id, value=True)
        source = put(s, "Gravestone Strider", "graveyard")
        victim = put(s, "Grizzly Bears", "graveyard", "p2")
        text, targets, expected = (
            "Exile this card",
            [victim.id],
            {"zone": "p1:exile", "other_exiled": victim.id},
        )
    elif name == "Eidolon of Obstruction":
        s = game(cards, ["Jace Beleren"], [name])
        source = put(s, "Jace Beleren", "hand")
        act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "U": 2})
        act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
        answer(s)
        put(s, name, "battlefield", "p2")
        text, mana, expected = "+2:", {"C": 1}, {"loyalty": 5}
    elif name == "Boom Scholar":
        s = game(cards, [name], [name])
        source = put(s, name, "battlefield")
        other = put(s, name, "battlefield", "p2")
        act(s, "p1", type="set_controller", card_ids=[other.id], player="p1")
        text, mana, expected = "Exhaust —", {"C": 2, "R": 1, "G": 1}, {"counters": 2, "trample": True}
    else:
        from tests.test_rules_conditional_prevention import attack

        s = game(cards, [name, "Shivan Dragon"])
        source = put(s, name, "battlefield")
        put(s, "Shivan Dragon", "battlefield")
        attack(s, [source], turn=7)
        text, mana, expected = "Boast —", {"C": 3, "R": 1}, {"dragon_token": True}
    wait_priority(s, "p1")
    ability = next(a for a in Plan(s.state, "p1", cards, None).ch(source).abilities if text in a.text)
    intent = {
        "type": "activate_ability",
        "card_id": source.id,
        "ability": ability.index,
        "targets": targets,
        "sources": [],
    }
    saved = tmp_path / "game.json"
    saved.write_text(s.state.model_dump_json())
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"intent": intent, "mana": mana, "expected": expected}))
    code = r"""
import json,sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import mana_units
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
spec=json.loads(Path(sys.argv[3]).read_text())
if spec['mana']:act(s,'p1',type='add_mana',player='p1',mana=spec['mana'])
act(s,'p1',**spec['intent']);answer(s)
c=s.state.cards[spec['intent']['card_id']];e=spec['expected'];view=Plan(s.state,'p1',repo,None)
assert not mana_units.visible_pool(s.state,'p1')
if 'zone' in e:assert c.zone==e['zone']
if e.get('tapped'):assert c.tapped
if e.get('untapped'):assert not c.tapped
if 'other_exiled' in e:assert s.state.cards[e['other_exiled']].zone=='p2:exile'
if 'loyalty' in e:assert c.counters.get('loyalty')==e['loyalty']
if 'counters' in e:assert c.counters.get('+1/+1')==e['counters']
if e.get('trample'):assert 'trample' in view.ch(c).keywords
if e.get('dragon_token'):
 tokens=[x for x in s.state.cards.values() if x.token and x.zone=='p1:battlefield']
 assert len(tokens)==1 and view.ch(tokens[0]).pt==(5,5) and 'flying' in view.ch(tokens[0]).keywords
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), str(spec)],
        cwd=Path(table_activation_modifiers52.__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_embalmers_taps_new_zombie_for_actual_mill_without_summoning_restriction(cards):
    s = game(cards, ["Embalmer's Tools", "Walking Corpse"])
    source = put(s, "Embalmer's Tools", "battlefield")
    zombie = put(s, "Walking Corpse", "battlefield")
    before = len(s.state.zones["p2:graveyard"])
    ability = next(
        a for a in Plan(s.state, "p1", cards, None).ch(source).abilities if "Target player mills" in a.text
    )
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability.index,
        targets=["p2"],
        sources=[],
        cost_choices=[{"component": 0, "cards": [zombie.id]}],
    )
    answer(s)
    assert zombie.tapped and not source.tapped
    assert len(s.state.zones["p2:graveyard"]) == before + 1
    roundtrip(s)


@pytest.mark.parametrize("name", ["Eidolon of Obstruction", "Dragonkin Berserker"])
def test_actual_first_strike_kills_blocker_before_regular_damage(cards, name):
    from tests.test_rules_conditional_prevention import attack, damage

    s = game(cards, [name], ["Grizzly Bears"])
    source = put(s, name, "battlefield")
    blocker = put(s, "Grizzly Bears", "battlefield", "p2")
    attack(s, [source], turn=7)
    to_phase(s, "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": source.id}])
    damage(s)
    assert blocker.zone == "p2:graveyard" and source.zone == "p1:battlefield"
    assert source.damage == 0
    roundtrip(s)


def test_convergence_without_current_commander_does_not_reduce_graveyard_cost(cards):
    s = game(cards, ["Convergence of Dominion", "Gravestone Strider"], ["Grizzly Bears"])
    put(s, "Convergence of Dominion", "battlefield")
    source = put(s, "Gravestone Strider", "graveyard")
    victim = put(s, "Grizzly Bears", "graveyard", "p2")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    ability = next(
        a for a in Plan(s.state, "p1", cards, None).ch(source).abilities if "Exile this card" in a.text
    )
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=source.id,
            ability=ability.index,
            targets=[victim.id],
            sources=[],
        )
    assert s.state.model_dump_json() == before
    activate(s, source, "Exile this card", mana={"C": 1}, targets=[victim.id])
    assert source.zone == "p1:exile" and victim.zone == "p2:exile"
    assert not mana_units.visible_pool(s.state, "p1")
    roundtrip(s)


def test_four_dragons_reduce_only_generic_boast_cost(cards):
    from tests.test_rules_conditional_prevention import attack

    s = game(cards, ["Dragonkin Berserker", *(["Shivan Dragon"] * 4)])
    source = put(s, "Dragonkin Berserker", "battlefield")
    dragons = [c for c in s.state.cards.values() if c.name == "Shivan Dragon" and c.owner == "p1"]
    assert len(dragons) == 4
    for dragon in dragons:
        act(s, "p1", type="move", card_ids=[dragon.id], to={"player": "p1", "zone": "battlefield"})
    attack(s, [source], turn=7)
    activate(s, source, "Boast —", mana={"R": 1})
    assert not mana_units.visible_pool(s.state, "p1")
    assert sum(bool(c.token) and c.zone == "p1:battlefield" for c in s.state.cards.values()) == 1
    roundtrip(s)
