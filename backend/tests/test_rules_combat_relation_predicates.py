"""Canonical combat-pair predicates use the declaring players and derived objects."""

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

NAMES = ["Spectral Grasp", "Serpent of Yawning Depths", "Godhunter Octopus", "Kraken of the Straits", "Ironclaw Curse", "Graxiplon"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/combat_relation_predicates_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="crp", number=str(i), **{k: v for k, v in c.items() if k != "name"}
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
            (Path(__file__).parent / "fixtures/combat_relation_predicates_cards.json").read_text()
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


@pytest.mark.parametrize(("kind", "legal"), [("Leviathan", True), ("Giant Octopus", True), ("Kraken Hatchling", True), ("Benthic Behemoth", True), ("Grizzly Bears", False)])
def test_serpent_shared_subtype_evasion(cards, kind, legal):
    s = setup(cards)
    attacker = put(s, "Serpent of Yawning Depths", "battlefield", pid="p2")
    blocker = put(s, kind, "battlefield")
    if legal:
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


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_kraken_counts_current_controllers_islands(cards, count):
    s = setup(cards)
    attacker = put(s, "Kraken of the Straits", "battlefield", pid="p2")
    blocker = put(s, "Grizzly Bears", "battlefield")
    islands = [c.id for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library"][:count]
    if islands:
        act(s, "p2", type="move", card_ids=islands, to={"player": "p2", "zone": "battlefield"})
    assert (pair_problem(s, blocker, attacker) is None) == (count <= 2)
    if count <= 2:
        block(s, blocker, attacker)
    else:
        to_phase(s, "declare_attackers", turn=2)
        attack(s, (attacker, "p1"), pid="p2")
        to_phase(s, "declare_blockers", turn=2)
        with pytest.raises(ActionError):
            act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
        roundtrip(s)


@pytest.mark.parametrize("name", [None, "Propaganda", "Street Savvy"])
def test_godhunter_attack_uses_either_defending_permanent_branch(cards, name):
    s = setup(cards)
    attacker = put(s, "Godhunter Octopus", "battlefield", pid="p2")
    if name == "Propaganda":
        # Non-Aura enchantment satisfies the first alternative without an enchanted permanent.
        # Use Dauthi Embrace so this proof has no unrelated attack fee.
        put(s, "Dauthi Embrace", "battlefield")
    elif name:
        bear = put(s, "Grizzly Bears", "battlefield")
        aura = enchant(s, name, bear)
        act(s, "p3", type="set_controller", card_ids=[aura.id], player="p3")
        # Aura controller may differ from the enchanted permanent's controller.
    to_phase(s, "declare_attackers", turn=2)
    if name:
        attack(s, (attacker, "p1"), pid="p2")
        assert s.state.cards[attacker.id].attacking
    else:
        with pytest.raises(ActionError):
            attack(s, (attacker, "p1"), pid="p2")
        assert not s.state.cards[attacker.id].attacking
    roundtrip(s)


@pytest.mark.parametrize(("attacker_name", "legal"), [("Kraken Hatchling", True), ("Elvish Mystic", False), ("Grizzly Bears", False)])
def test_ironclaw_uses_blocker_toughness_including_curse(cards, attacker_name, legal):
    s = setup(cards)
    blocker = put(s, "Grizzly Bears", "battlefield")
    attacker = put(s, attacker_name, "battlefield", pid="p2")
    enchant(s, "Ironclaw Curse", blocker)
    assert Plan(s.state, "p1", s.cards, None).ch(blocker).pt == (2, 1)
    assert (pair_problem(s, blocker, attacker) is None) == legal
    if legal:
        block(s, blocker, attacker)
    else:
        to_phase(s, "declare_attackers", turn=2)
        attack(s, (attacker, "p1"), pid="p2")
        to_phase(s, "declare_blockers", turn=2)
        with pytest.raises(ActionError):
            act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
        roundtrip(s)


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_graxiplon_counts_shared_type_among_all_defenders_creatures(cards, count):
    s = setup(cards)
    attacker = put(s, "Graxiplon", "battlefield", pid="p2")
    blocker = put(s, "Grizzly Bears", "battlefield")
    for name in ["Elvish Mystic", "Elvish Visionary", "Llanowar Elves"][:count]:
        put(s, name, "battlefield")
    assert (pair_problem(s, blocker, attacker) is None) == (count >= 3)
    if count >= 3:
        # The blocker is a Bear, not one of the three Elves establishing the permission.
        block(s, blocker, attacker)
    else:
        to_phase(s, "declare_attackers", turn=2)
        attack(s, (attacker, "p1"), pid="p2")
        to_phase(s, "declare_blockers", turn=2)
        with pytest.raises(ActionError):
            act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
        roundtrip(s)


@pytest.mark.parametrize("aura_owner", ["p1", "p3"])
def test_spectral_grasp_binds_aura_controller_not_enchanted_controller(cards, aura_owner):
    s = setup(cards)
    blocker = put(s, "Grizzly Bears", "battlefield")
    attacker = put(s, "Runeclaw Bear", "battlefield", pid="p2")
    aura = enchant(s, "Spectral Grasp", blocker)
    if aura_owner == "p3":
        act(s, "p3", type="set_controller", card_ids=[aura.id], player="p3")
    # Neither p1 nor p3 controls the p2 attacker, so this block is permitted.
    assert pair_problem(s, blocker, attacker) is None
    block(s, blocker, attacker)


@pytest.mark.parametrize("group", ["two_pairs", "changeling", "wrong_player"])
def test_graxiplon_shared_type_is_current_not_total_or_source_controller(cards, group):
    s = setup(cards)
    attacker = put(s, "Graxiplon", "battlefield", pid="p2")
    blocker = put(s, "Grizzly Bears", "battlefield")
    pid = "p3" if group == "wrong_player" else "p1"
    for name in ["Elvish Mystic", "Llanowar Elves"]:
        put(s, name, "battlefield", pid=pid)
    if group == "two_pairs":
        put(s, "Runeclaw Bear", "battlefield")
    elif group == "changeling":
        put(s, "Chameleon Colossus", "battlefield")
    else:
        put(s, "Elvish Visionary", "battlefield", pid=pid)
    assert (pair_problem(s, blocker, attacker) is None) == (group == "changeling")
    if group == "changeling":
        block(s, blocker, attacker)
    else:
        roundtrip(s)


def test_ironclaw_reads_derived_toughness_and_survives_host_ability_loss(cards):
    s = setup(cards)
    blocker = put(s, "Grizzly Bears", "battlefield")
    attacker = put(s, "Giant Octopus", "battlefield", pid="p2")
    other = put(s, "Giant Spider", "battlefield")
    enchant(s, "Ironclaw Curse", blocker)
    assert pair_problem(s, blocker, attacker) is not None
    assert pair_problem(s, other, attacker) is None
    enchant(s, "Lignify", blocker)
    assert Plan(s.state, "p1", s.cards, None).ch(blocker).pt[1] == 3
    assert pair_problem(s, blocker, attacker) is not None
    enchant(s, "Street Savvy", blocker)
    assert Plan(s.state, "p1", s.cards, None).ch(blocker).pt[1] == 5
    assert pair_problem(s, blocker, attacker) is None
    block(s, blocker, attacker)


@pytest.mark.parametrize("name", ["Serpent of Yawning Depths", "Kraken of the Straits", "Graxiplon"])
def test_source_ability_loss_removes_its_combat_predicate(cards, name):
    s = setup(cards)
    source = put(s, name, "battlefield", pid="p2")
    attacker = put(s, "Giant Octopus", "battlefield", pid="p2") if name == "Serpent of Yawning Depths" else source
    blocker = put(s, "Grizzly Bears", "battlefield")
    if name == "Kraken of the Straits":
        ids = [c.id for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library"][:3]
        act(s, "p2", type="move", card_ids=ids, to={"player": "p2", "zone": "battlefield"})
    assert pair_problem(s, blocker, attacker) is not None
    enchant(s, "Lignify", source)
    assert pair_problem(s, blocker, attacker) is None
    block(s, blocker, attacker)


@pytest.mark.parametrize("steal", [False, True])
def test_spectral_grasp_actual_controller_change_updates_protected_attackers(cards, steal):
    s = setup(cards)
    blocker = put(s, "Grizzly Bears", "battlefield", pid="p2")
    attacker = put(s, "Runeclaw Bear", "battlefield")
    aura = enchant(s, "Spectral Grasp", blocker)
    assert pair_problem(s, blocker, attacker) is not None
    if steal:
        to_phase(s, "main1", turn=3)
        spell = put(s, "Confiscate", "hand", pid="p3")
        mana(s, pid="p3", U=2, C=4)
        act(s, "p3", type="cast_spell", card_id=spell.id, targets=[aura.id])
        settle(s)
        assert s.state.cards[aura.id].controller == "p3"
        assert pair_problem(s, blocker, attacker) is None
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (attacker, "p2"))
    to_phase(s, "declare_blockers", turn=4)
    payload = dict(type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
    if steal:
        act(s, "p2", **payload)
        assert s.state.cards[blocker.id].blocking == attacker.id
    else:
        with pytest.raises(ActionError):
            act(s, "p2", **payload)
    roundtrip(s)


def test_kraken_count_tracks_actual_stolen_source_controller(cards):
    s = setup(cards)
    attacker = put(s, "Kraken of the Straits", "battlefield", pid="p2")
    blocker = put(s, "Grizzly Bears", "battlefield", pid="p2")
    ids = [c.id for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library"][:3]
    act(s, "p2", type="move", card_ids=ids, to={"player": "p2", "zone": "battlefield"})
    assert pair_problem(s, blocker, attacker) is not None
    enchant(s, "Confiscate", attacker)
    assert s.state.cards[attacker.id].controller == "p1"
    assert pair_problem(s, blocker, attacker) is None
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (attacker, "p2"))
    to_phase(s, "declare_blockers", turn=4)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
    assert s.state.cards[blocker.id].blocking == attacker.id
    roundtrip(s)


@pytest.mark.parametrize(("name", "count", "legal"), [("Kraken of the Straits", 2, True), ("Kraken of the Straits", 3, False), ("Graxiplon", 2, False), ("Graxiplon", 3, True)])
def test_current_predicate_cold_declaration_and_replay(cards, tmp_path, name, count, legal):
    import subprocess
    import sys

    s = setup(cards)
    attacker = put(s, name, "battlefield", pid="p2")
    blocker = put(s, "Grizzly Bears", "battlefield")
    if name == "Graxiplon":
        for n in ["Elvish Mystic", "Llanowar Elves", "Elvish Visionary"][:count]:
            put(s, n, "battlefield")
    else:
        ids = [c.id for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library"][:count]
        act(s, "p2", type="move", card_ids=ids, to={"player": "p2", "zone": "battlefield"})
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "declare_blockers", turn=2)
    path = tmp_path / "save.json"
    path.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
legal=sys.argv[5]=='True'
try:s.perform('p1',{'type':'declare_blockers','blocks':[{'blocker_id':sys.argv[3],'attacker_id':sys.argv[4]}]})
except ActionError:
    assert not legal
else:
    assert legal and s.state.cards[sys.argv[3]].blocking==sys.argv[4]
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, "-c", code, str(path), str(cards.db_path), blocker.id, attacker.id, str(legal)], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_kraken_legality_is_locked_before_blocking_mana_payment(cards):
    s = setup(cards)
    attacker = put(s, "Kraken of the Straits", "battlefield", pid="p2")
    blocker = put(s, "Vodalian Merchant", "battlefield")
    lord = put(s, "Lord of Atlantis", "battlefield")
    altar = put(s, "Phyrexian Altar", "battlefield")
    fallback = put(s, "Island", "battlefield")  # Native availability can use this; manual payment chooses the Altar.
    enchant(s, "Oppressive Rays", blocker)
    ids = [c.id for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library"][:2]
    act(s, "p2", type="move", card_ids=ids, to={"player": "p2", "zone": "battlefield"})
    act(s, "p1", type="set_prefs", payment="self")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "declare_blockers", turn=2)
    assert Plan(s.state, "p1", s.cards, None).ch(blocker).pt[0] == 2
    mana(s, pid="p1", C=2)
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
    assert s.state.rules.decision and s.state.rules.decision.resume["step"] == "pay_mana"
    act(s, "p1", type="activate_ability", card_id=altar.id, ability=0, mana_choice="G", cost_choices=[{"component": 0, "cards": [lord.id]}])
    assert s.state.cards[lord.id].zone == "p1:graveyard"
    assert not s.state.cards[fallback.id].tapped
    assert Plan(s.state, "p1", s.cards, None).ch(blocker).pt[0] == 1
    assert pair_problem(s, blocker, attacker) is not None
    assert s.state.cards[blocker.id].blocking == attacker.id
    roundtrip(s)


@pytest.mark.parametrize("other_legal", [False, True])
def test_godhunter_destination_predicate_participates_in_goad_requirements(cards, other_legal):
    s = setup(cards)
    attacker = put(s, "Godhunter Octopus", "battlefield", pid="p2")
    put(s, "Dauthi Embrace", "battlefield")
    if other_legal:
        put(s, "Dauthi Embrace", "battlefield", pid="p3")
    blade = put(s, "Bloodthirsty Blade", "battlefield")
    mana(s, pid="p1", C=1)
    act(s, "p1", type="activate_ability", card_id=blade.id, ability=1, targets=[attacker.id])
    settle(s)
    to_phase(s, "declare_attackers", turn=2)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[])
    invalid = "p1" if other_legal else "p3"
    with pytest.raises(ActionError):
        attack(s, (attacker, invalid), pid="p2")
    valid = "p3" if other_legal else "p1"
    attack(s, (attacker, valid), pid="p2")
    assert s.state.cards[attacker.id].attacking.id == valid
    roundtrip(s)


def test_kraken_zero_threshold_still_excludes_negative_power(cards):
    s = setup(cards)
    attacker = put(s, "Kraken of the Straits", "battlefield", pid="p2")
    blocker = put(s, "Giant Spider", "battlefield")
    act(s, "p1", type="counter", card_ids=[blocker.id], kind="-1/-1", delta=3)
    assert Plan(s.state, "p1", s.cards, None).ch(blocker).pt == (-1, 1)
    assert pair_problem(s, blocker, attacker) is not None
    act(s, "p1", type="counter", card_ids=[blocker.id], kind="-1/-1", delta=-1)
    assert Plan(s.state, "p1", s.cards, None).ch(blocker).pt == (0, 2)
    assert pair_problem(s, blocker, attacker) is None
    block(s, blocker, attacker)
