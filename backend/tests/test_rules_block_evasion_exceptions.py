"""Canonical block-only exceptions leave abilities and unrelated evasion intact."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import combat, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack

NAMES = ["Aether Web", "Aetherflame Wall", "Wall of Diffusion", "Heartwood Dryad", "Street Savvy", "Staff of the Ages", "Dragon Hunter"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/block_evasion_exceptions_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="bee", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [
        c["name"]
        for c in json.loads(
            (Path(__file__).parent / "fixtures/block_evasion_exceptions_cards.json").read_text()
        )
    ]
    return table(cards, names, names, names)



def enchant(s, name, target):
    aura = put(s, name, "hand")
    mana(s, pid="p1", W=5, U=5, B=5, R=5, G=5, C=10)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[target.id])
    settle(s)
    return aura


def pair_problem(s, blocker, attacker):
    p = Plan(s.state, actor="p1", info=s.cards, rng=None)
    return combat.block_problem(p.state, p.state.cards[blocker.id], p.ch(blocker), p.state.cards[attacker.id], p.ch(attacker), p.info)


def block(s, blocker, attacker):
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "declare_blockers", turn=2)
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
    assert s.state.cards[blocker.id].blocking == attacker.id
    roundtrip(s)


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", ["Aetherflame Wall", "Wall of Diffusion", "Heartwood Dryad", "Aether Web"])
@pytest.mark.parametrize("shadow", [False, True])
def test_shadow_exception_preserves_ordinary_blocks(cards, name, shadow):
    s = setup(cards)
    blocker = put(s, "Grizzly Bears" if name == "Aether Web" else name, "battlefield")
    attacker = put(s, "Dauthi Slayer" if shadow else "Memnite", "battlefield", pid="p2")
    if name == "Aether Web":
        enchant(s, name, blocker)
    assert pair_problem(s, blocker, attacker) is None
    assert "shadow" not in Plan(s.state, actor="p1", info=s.cards, rng=None).ch(blocker).keywords
    block(s, blocker, attacker)


@pytest.mark.parametrize("name", ["Aetherflame Wall", "Wall of Diffusion", "Heartwood Dryad", "Aether Web"])
def test_shadow_exception_does_not_ignore_flying(cards, name):
    s = setup(cards)
    blocker = put(s, "Grizzly Bears" if name == "Aether Web" else name, "battlefield")
    attacker = put(s, "Dauthi Slayer", "battlefield", pid="p2")
    enchant(s, "Flight", attacker)
    if name == "Aether Web":
        enchant(s, name, blocker)
        assert pair_problem(s, blocker, attacker) is None
        block(s, blocker, attacker)
    else:
        assert pair_problem(s, blocker, attacker) is not None
        to_phase(s, "declare_attackers", turn=2)
        attack(s, (attacker, "p1"), pid="p2")
        to_phase(s, "declare_blockers", turn=2)
        with pytest.raises(ActionError):
            act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
        roundtrip(s)


LANDWALK = [
    ("Bog Wraith", "Swamp"), ("Shanodin Dryads", "Forest"), ("River Boa", "Island"),
    ("Goblin Mountaineer", "Mountain"), ("Zodiac Rooster", "Plains"),
    ("Dryad Sophisticate", "Dwarven Ruins"), ("Livonya Silone", "Kor Haven"),
    ("Zombie Musher", "Snow-Covered Island"), ("Legions of Lim-Dûl", "Snow-Covered Swamp"),
    ("Rime Dryad", "Snow-Covered Forest"),
]


@pytest.mark.parametrize("name", ["Street Savvy", "Staff of the Ages"])
@pytest.mark.parametrize(("walker", "land"), LANDWALK)
def test_landwalk_exception_covers_current_landwalk_kind(cards, name, walker, land):
    s = setup(cards)
    blocker = put(s, "Grizzly Bears", "battlefield")
    attacker = put(s, walker, "battlefield", pid="p2")
    put(s, land, "battlefield")
    assert pair_problem(s, blocker, attacker) is not None
    if name == "Street Savvy":
        enchant(s, name, blocker)
    else:
        put(s, name, "battlefield", pid="p3")
    assert pair_problem(s, blocker, attacker) is None
    p = Plan(s.state, "p1", s.cards, None)
    assert any("walk" in kw for kw in p.ch(attacker).keywords)
    block(s, blocker, attacker)


@pytest.mark.parametrize("name", ["Aetherflame Wall", "Wall of Diffusion", "Heartwood Dryad", "Aether Web", "Street Savvy"])
def test_external_rule_survives_host_ability_loss_but_printed_rule_does_not(cards, name):
    s = setup(cards)
    external = name in ("Aether Web", "Street Savvy")
    blocker = put(s, "Grizzly Bears" if external else name, "battlefield")
    attacker = put(s, "Bog Wraith" if name == "Street Savvy" else "Dauthi Slayer", "battlefield", pid="p2")
    if name == "Street Savvy":
        put(s, "Swamp", "battlefield")
    if external:
        enchant(s, name, blocker)
    assert pair_problem(s, blocker, attacker) is None
    enchant(s, "Lignify", blocker)
    if external:
        assert pair_problem(s, blocker, attacker) is None
        block(s, blocker, attacker)
    else:
        assert pair_problem(s, blocker, attacker) is not None
        roundtrip(s)


@pytest.mark.parametrize("dragon", [False, True])
def test_dragon_hunter_reach_is_only_for_current_dragons(cards, dragon):
    s = setup(cards)
    blocker = put(s, "Dragon Hunter", "battlefield")
    attacker = put(s, "Shivan Dragon" if dragon else "Wind Drake", "battlefield", pid="p2")
    p = Plan(s.state, "p1", s.cards, None)
    assert "reach" not in p.ch(blocker).keywords
    if dragon:
        assert pair_problem(s, blocker, attacker) is None
        block(s, blocker, attacker)
    else:
        assert pair_problem(s, blocker, attacker) is not None
        roundtrip(s)


@pytest.mark.parametrize("name", ["Aetherflame Wall", "Heartwood Dryad"])
@pytest.mark.parametrize("shadow_attacker", [False, True])
def test_actual_shadow_on_exception_blocker_preserves_normal_mode(cards, name, shadow_attacker):
    s = setup(cards)
    blocker = put(s, name, "battlefield")
    attacker = put(s, "Dauthi Slayer" if shadow_attacker else "Memnite", "battlefield", pid="p2")
    embrace = put(s, "Dauthi Embrace", "battlefield", pid="p2")
    to_phase(s, "main1", turn=2)
    mana(s, pid="p2", B=2)
    act(s, "p2", type="activate_ability", card_id=embrace.id, ability=0, targets=[blocker.id])
    settle(s)
    assert "shadow" in Plan(s.state, "p1", s.cards, None).ch(blocker).keywords
    if shadow_attacker:
        assert pair_problem(s, blocker, attacker) is None
        block(s, blocker, attacker)
    else:
        assert pair_problem(s, blocker, attacker) is not None
        roundtrip(s)


@pytest.mark.parametrize("name", ["Street Savvy", "Staff of the Ages"])
def test_landwalk_exception_ends_when_actual_source_leaves(cards, name):
    s = setup(cards)
    blocker = put(s, "Grizzly Bears", "battlefield")
    attacker = put(s, "Bog Wraith", "battlefield", pid="p2")
    put(s, "Swamp", "battlefield")
    source = enchant(s, name, blocker) if name == "Street Savvy" else put(s, name, "battlefield", pid="p3")
    assert pair_problem(s, blocker, attacker) is None
    spell = put(s, "Naturalize", "hand")
    mana(s, pid="p1", G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone.endswith(":graveyard")
    assert pair_problem(s, blocker, attacker) is not None
    roundtrip(s)


def test_dragon_hunter_reads_current_creature_types(cards):
    s = setup(cards)
    blocker = put(s, "Dragon Hunter", "battlefield")
    attacker = put(s, "Wind Drake", "battlefield", pid="p2")
    assert pair_problem(s, blocker, attacker) is not None
    equipment = put(s, "Runed Stalactite", "battlefield", pid="p2")
    to_phase(s, "main1", turn=2)
    mana(s, pid="p2", C=2)
    act(s, "p2", type="activate_ability", card_id=equipment.id, ability=1, targets=[attacker.id])
    settle(s)
    assert "Dragon" in Plan(s.state, "p1", s.cards, None).ch(attacker).subtypes
    assert pair_problem(s, blocker, attacker) is None
    block(s, blocker, attacker)


def test_attached_permission_follows_host_current_controller(cards):
    s = setup(cards)
    blocker = put(s, "Grizzly Bears", "battlefield")
    attacker = put(s, "Bog Wraith", "battlefield", pid="p3")
    put(s, "Swamp", "battlefield", pid="p2")
    aura = enchant(s, "Street Savvy", blocker)
    steal = put(s, "Confiscate", "hand", pid="p2")
    to_phase(s, "main1", turn=2)
    mana(s, pid="p2", U=2, C=4)
    act(s, "p2", type="cast_spell", card_id=steal.id, targets=[blocker.id])
    settle(s)
    assert s.state.cards[blocker.id].controller == "p2"
    assert s.state.cards[aura.id].controller == "p1"
    assert pair_problem(s, blocker, attacker) is None
    other = put(s, "Giant Spider", "battlefield", pid="p2")
    assert pair_problem(s, other, attacker) is not None
    to_phase(s, "declare_attackers", turn=3)
    attack(s, (attacker, "p2"), pid="p3")
    to_phase(s, "declare_blockers", turn=3)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
    assert s.state.cards[blocker.id].blocking == attacker.id
    roundtrip(s)


@pytest.mark.parametrize("name", ["Aether Web", "Staff of the Ages"])
def test_exception_declaration_resumes_in_fresh_process(cards, tmp_path, name):
    import subprocess
    import sys

    s = setup(cards)
    blocker = put(s, "Grizzly Bears", "battlefield")
    attacker = put(s, "Dauthi Slayer" if name == "Aether Web" else "Bog Wraith", "battlefield", pid="p2")
    if name == "Aether Web":
        enchant(s, name, blocker)
        enchant(s, "Lignify", blocker)
    else:
        put(s, "Swamp", "battlefield")
        put(s, name, "battlefield", pid="p3")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "declare_blockers", turn=2)
    path = tmp_path / "save.json"
    path.write_text(s.state.model_dump_json())
    script = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip
repo = CardRepository(Path(sys.argv[2]), ImageStore(Path(sys.argv[2]).parent / "images"))
s = GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()), cards=repo)
act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": sys.argv[3], "attacker_id": sys.argv[4]}])
assert s.state.cards[sys.argv[3]].blocking == sys.argv[4]
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, "-c", script, str(path), str(cards.db_path), blocker.id, attacker.id], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_shadow_permission_does_not_remove_menace_group_requirement(cards):
    s = setup(cards)
    first = put(s, "Heartwood Dryad", "battlefield")
    second = put(s, "Wall of Diffusion", "battlefield")
    attacker = put(s, "Boggart Brute", "battlefield", pid="p2")
    embrace = put(s, "Dauthi Embrace", "battlefield", pid="p2")
    to_phase(s, "main1", turn=2)
    mana(s, pid="p2", B=2)
    act(s, "p2", type="activate_ability", card_id=embrace.id, ability=0, targets=[attacker.id])
    settle(s)
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "declare_blockers", turn=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": first.id, "attacker_id": attacker.id}])
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": attacker.id} for b in [first, second]])
    assert all(s.state.cards[b.id].blocking == attacker.id for b in [first, second])
    roundtrip(s)


@pytest.mark.parametrize("name", ["Street Savvy", "Staff of the Ages"])
def test_landwalk_permission_leaves_flying_restriction(cards, name):
    s = setup(cards)
    blocker = put(s, "Grizzly Bears", "battlefield")
    attacker = put(s, "Bog Wraith", "battlefield", pid="p2")
    put(s, "Swamp", "battlefield")
    if name == "Street Savvy":
        enchant(s, name, blocker)
    else:
        put(s, name, "battlefield", pid="p3")
    assert pair_problem(s, blocker, attacker) is None
    enchant(s, "Flight", attacker)
    assert pair_problem(s, blocker, attacker) is not None
    roundtrip(s)


@pytest.mark.parametrize("name", ["Street Savvy", "Staff of the Ages"])
def test_artifact_landwalk_uses_same_block_exception(cards, name):
    s = setup(cards)
    blocker = put(s, "Grizzly Bears", "battlefield")
    attacker = put(s, "Memnite", "battlefield", pid="p2")
    put(s, "Darksteel Citadel", "battlefield")
    if name == "Street Savvy":
        enchant(s, name, blocker)
    else:
        put(s, name, "battlefield", pid="p3")
    equipment = put(s, "Vectis Gloves", "battlefield", pid="p2")
    to_phase(s, "main1", turn=2)
    mana(s, pid="p2", C=2)
    act(s, "p2", type="activate_ability", card_id=equipment.id, ability=1, targets=[attacker.id])
    settle(s)
    assert "artifact landwalk" in Plan(s.state, "p1", s.cards, None).ch(attacker).keywords
    assert pair_problem(s, blocker, attacker) is None
    block(s, blocker, attacker)


def test_global_exception_tracks_its_sources_actual_ability_loss(cards):
    s = setup(cards)
    blocker = put(s, "Grizzly Bears", "battlefield")
    attacker = put(s, "Bog Wraith", "battlefield", pid="p2")
    put(s, "Swamp", "battlefield")
    staff = put(s, "Staff of the Ages", "battlefield", pid="p3")
    enchant(s, "Ensoul Artifact", staff)
    assert pair_problem(s, blocker, attacker) is None
    loss = enchant(s, "Lignify", staff)
    assert pair_problem(s, blocker, attacker) is not None
    spell = put(s, "Naturalize", "hand")
    mana(s, pid="p1", G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[loss.id])
    settle(s)
    assert pair_problem(s, blocker, attacker) is None
    block(s, blocker, attacker)
