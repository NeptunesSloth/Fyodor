import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/exchange_spells93_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"],
            set_code="exc93",
            number=str(i),
            **{k: v for k, v in c.items() if k not in {"name", "set_code"}},
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_native_nonowner_controller_concedes_restores_original_caster93(cards):
    s = table(cards, ["Aethersnatch"], ["Grizzly Bears"], ["Sol Ring"])
    bear = put(s, "Grizzly Bears", "hand", pid="p2")
    steal = put(s, "Aethersnatch", "hand")
    start(s, turn=5)
    act(s, "p2", type="set_prefs", hold_priority=True)
    mana(s, pid="p2", C=1, G=1)
    act(s, "p2", type="cast_spell", card_id=bear.id)
    wait_priority(s, "p1")
    mana(s, C=4, U=2)
    act(s, "p1", type="cast_spell", card_id=steal.id, targets=[bear.id])
    for _ in range(20):
        if steal.zone != "stack":
            break
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type="pass_priority")
    assert bear.zone == "stack" and bear.controller == "p1"
    act(s, "p1", type="concede")
    assert bear.zone == "stack" and bear.controller == "p2"


def cast_pending(s, pid, card, targets=(), **cost):
    wait_priority(s, pid)
    mana(s, pid=pid, **cost)
    act(s, pid, type="cast_spell", card_id=card.id, targets=list(targets))


def resolve_only(s, spell):
    for _ in range(30):
        if spell.zone != "stack":
            return
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("spell did not resolve")


def test_owner_departure_removes_owned_spell_despite_foreign_controller93(cards):
    s = table(cards, ["Aethersnatch"], ["Grizzly Bears"], ["Sol Ring"])
    bear = put(s, "Grizzly Bears", "hand", pid="p2")
    steal = put(s, "Aethersnatch", "hand")
    start(s, turn=5)
    act(s, "p2", type="set_prefs", hold_priority=True)
    cast_pending(s, "p2", bear, C=1, G=1)
    cast_pending(s, "p1", steal, [bear.id], C=4, U=2)
    resolve_only(s, steal)
    assert bear.zone == "stack" and bear.controller == "p1"
    act(s, "p2", type="concede")
    assert bear.zone != "stack" and bear.id not in s.state.rules.stack


def test_ordered_native_spell_control_effects_restore_underlying_layer93(cards):
    s = table(cards, ["Aethersnatch"], ["Aethersnatch"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "hand", pid="p3")
    a = put(s, "Aethersnatch", "hand")
    b = put(s, "Aethersnatch", "hand", pid="p2")
    start(s, turn=6)
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="set_prefs", hold_priority=True)
    cast_pending(s, "p3", bear, C=1, G=1)
    cast_pending(s, "p1", a, [bear.id], C=4, U=2)
    resolve_only(s, a)
    assert bear.controller == "p1"
    cast_pending(s, "p2", b, [bear.id], C=4, U=2)
    resolve_only(s, b)
    assert bear.zone == "stack" and bear.controller == "p2"
    act(s, "p2", type="concede")
    assert bear.zone == "stack" and bear.controller == "p1"
    act(s, "p1", type="concede")
    assert bear.zone == "stack" and bear.controller == "p3"


def test_foreign_original_caster_restored_instead_of_owner93(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_library_look import settle

    s = table(
        cards,
        ["Aethersnatch"],
        ["Gonti, Lord of Luxury"],
        ["Grizzly Bears", "Forest", "Sol Ring", "Llanowar Elves"],
    )
    bear = put(s, "Grizzly Bears", "library", pid="p3")
    gonti = put(s, "Gonti, Lord of Luxury", "hand", pid="p2")
    steal = put(s, "Aethersnatch", "hand")
    start(s, turn=5)
    from tests.test_rules_refused_look import stack_library

    stack_library(s, ["Grizzly Bears", "Forest", "Sol Ring", "Llanowar Elves"], pid="p3")
    cast_pending(s, "p2", gonti, C=2, B=2)
    settle(s)
    assert s.state.rules.decision.player == "p2"
    pick(s, ["p3"])
    settle(s)
    pick(s, [bear.id])
    settle(s)
    assert bear.zone == "p3:exile"
    act(s, "p2", type="set_prefs", hold_priority=True)
    cast_pending(s, "p2", bear, C=2)
    assert bear.owner == "p3" and bear.controller == "p2"
    cast_pending(s, "p1", steal, [bear.id], C=4, U=2)
    resolve_only(s, steal)
    assert bear.controller == "p1"
    act(s, "p1", type="concede")
    assert bear.zone == "stack" and bear.controller == "p2" and bear.owner == "p3"


@pytest.mark.parametrize("name", ["Perplexing Chimera", "Sudden Substitution"])
def test_whole_exact_exchange93(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def chimera_pending93(cards):
    s = table(cards, ["Perplexing Chimera", "Grizzly Bears"], ["Murder"], ["Llanowar Elves"])
    chimera = put(s, "Perplexing Chimera", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    elf = put(s, "Llanowar Elves", "battlefield", pid="p3")
    murder = put(s, "Murder", "hand", pid="p2")
    start(s, turn=5)
    cast_pending(s, "p2", murder, [bear.id], C=1, B=2)
    from tests.test_rules_library_look import settle

    settle(s)
    assert s.state.rules.decision.player == "p1"
    return s, chimera, murder, bear, elf


def test_chimera_exchange_and_original_ability_controller_retargets93(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_library_look import settle

    s, chimera, murder, bear, elf = chimera_pending93(cards)
    assert {o.id for o in s.state.rules.decision.options} == {"yes", "no"}
    pick(s, ["yes"])
    settle(s)
    assert chimera.controller == "p2" and murder.controller == "p1"
    assert s.state.rules.decision.player == "p1"
    pick(s, [elf.id])
    settle(s)
    assert elf.zone == "p3:graveyard" and bear.zone == "p1:battlefield"
    assert murder.zone == "p2:graveyard"


def test_chimera_decline_does_not_offer_new_targets93(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_library_look import settle

    s, chimera, murder, bear, elf = chimera_pending93(cards)
    pick(s, ["no"])
    settle(s)
    assert chimera.controller == "p1" and murder.zone == "p2:graveyard"
    assert bear.zone == "p1:graveyard" and elf.zone == "p3:battlefield"


def test_sudden_third_player_new_spell_controller_retargets93(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_library_look import settle

    s = table(cards, ["Sudden Substitution", "Grizzly Bears"], ["Murder"], ["Llanowar Elves"])
    bear = put(s, "Grizzly Bears", "battlefield")
    elf = put(s, "Llanowar Elves", "battlefield", pid="p3")
    murder = put(s, "Murder", "hand", pid="p2")
    sudden = put(s, "Sudden Substitution", "hand")
    start(s, turn=5)
    act(s, "p2", type="set_prefs", hold_priority=True)
    cast_pending(s, "p2", murder, [bear.id], C=1, B=2)
    wait_priority(s, "p1")
    mana(s, C=2, U=2)
    act(s, "p1", type="cast_spell", card_id=sudden.id, targets=[murder.id, elf.id], target_counts=[1, 1])
    settle(s)
    assert murder.controller == "p3" and elf.controller == "p2"
    assert s.state.rules.decision.player == "p3"
    pick(s, [elf.id])
    settle(s)
    assert elf.zone == "p3:graveyard" and bear.zone == "p1:battlefield"


def test_chimera_source_destroyed_before_trigger_cannot_exchange93(cards):
    from tests.test_rules_library_look import settle

    s = table(cards, ["Perplexing Chimera", "Murder", "Grizzly Bears"], ["Murder"], ["Llanowar Elves"])
    source = put(s, "Perplexing Chimera", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    theirs = put(s, "Murder", "hand", pid="p2")
    mine = put(s, "Murder", "hand")
    start(s, turn=5)
    act(s, "p2", type="set_prefs", hold_priority=True)
    cast_pending(s, "p2", theirs, [bear.id], C=1, B=2)
    cast_pending(s, "p1", mine, [source.id], C=1, B=2)
    settle(s)
    assert s.state.rules.decision is None
    assert source.zone == "p1:graveyard" and bear.zone == "p1:graveyard"
    assert theirs.zone == "p2:graveyard"


def test_chimera_spell_countered_before_trigger_cannot_exchange93(cards):
    from tests.test_rules_library_look import settle

    s = table(cards, ["Perplexing Chimera", "Counterspell", "Grizzly Bears"], ["Murder"], ["Sol Ring"])
    source = put(s, "Perplexing Chimera", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    theirs = put(s, "Murder", "hand", pid="p2")
    counter = put(s, "Counterspell", "hand")
    start(s, turn=5)
    act(s, "p2", type="set_prefs", hold_priority=True)
    cast_pending(s, "p2", theirs, [bear.id], C=1, B=2)
    cast_pending(s, "p1", counter, [theirs.id], U=2)
    settle(s)
    assert s.state.rules.decision is None
    assert source.controller == "p1" and bear.zone == "p1:battlefield"
    assert theirs.zone == "p2:graveyard"


def test_chimera_new_source_controller_does_not_choose_new_targets93(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_library_look import settle

    s = table(
        cards, ["Perplexing Chimera", "Grizzly Bears"], ["Murder"], ["Word of Seizing", "Llanowar Elves"]
    )
    source = put(s, "Perplexing Chimera", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    elf = put(s, "Llanowar Elves", "battlefield", pid="p3")
    theirs = put(s, "Murder", "hand", pid="p2")
    ray = put(s, "Word of Seizing", "hand", pid="p3")
    start(s, turn=5)
    act(s, "p2", type="set_prefs", hold_priority=True)
    cast_pending(s, "p2", theirs, [bear.id], C=1, B=2)
    cast_pending(s, "p3", ray, [source.id], C=3, R=2)
    settle(s)
    pick(s, ["no"])  # Source's additional trigger for Ray itself.
    settle(s)
    assert source.controller == "p3", (
        s.state.rules.decision,
        [(c.name, c.zone, c.controller) for c in s.state.cards.values() if c.zone == "stack"],
    )
    pick(s, ["yes"])  # Original p1 trigger for p2's Murder.
    settle(s)
    assert source.controller == "p2" and theirs.controller == "p3"
    assert s.state.rules.decision.player == "p1"
    pick(s, [elf.id])
    settle(s)
    assert bear.zone == "p1:battlefield" and elf.zone == "p3:graveyard"


def test_sudden_legal_spell_still_retargets_after_mana_sacrifice_target93(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_library_look import settle

    s = table(cards, ["Sudden Substitution", "Grizzly Bears"], ["Murder"], ["Wild Cantor", "Llanowar Elves"])
    bear = put(s, "Grizzly Bears", "battlefield")
    cantor = put(s, "Wild Cantor", "battlefield", pid="p3")
    elf = put(s, "Llanowar Elves", "battlefield", pid="p3")
    murder = put(s, "Murder", "hand", pid="p2")
    sudden = put(s, "Sudden Substitution", "hand")
    start(s, turn=5)
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", hold_priority=True)
    cast_pending(s, "p2", murder, [bear.id], C=1, B=2)
    wait_priority(s, "p1")
    mana(s, C=2, U=2)
    act(s, "p1", type="cast_spell", card_id=sudden.id, targets=[murder.id, cantor.id], target_counts=[1, 1])
    wait_priority(s, "p3")
    act(s, "p3", type="activate_ability", card_id=cantor.id, ability=0)
    if s.state.rules.decision:
        assert s.state.rules.decision.player == "p3"
        pick(s, [s.state.rules.decision.options[0].id])
    settle(s)
    assert cantor.zone == "p3:graveyard" and murder.controller == "p2"
    assert s.state.rules.decision.player == "p2"
    pick(s, [elf.id])
    settle(s)
    assert elf.zone == "p3:graveyard" and bear.zone == "p1:battlefield"


def test_sudden_spell_owner_concedes_no_exchange_or_retarget93(cards):
    from tests.test_rules_library_look import settle

    s = table(cards, ["Sudden Substitution", "Grizzly Bears"], ["Murder"], ["Llanowar Elves"])
    bear = put(s, "Grizzly Bears", "battlefield")
    elf = put(s, "Llanowar Elves", "battlefield", pid="p3")
    murder = put(s, "Murder", "hand", pid="p2")
    sudden = put(s, "Sudden Substitution", "hand")
    start(s, turn=5)
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", hold_priority=True)
    cast_pending(s, "p2", murder, [bear.id], C=1, B=2)
    wait_priority(s, "p1")
    mana(s, C=2, U=2)
    act(s, "p1", type="cast_spell", card_id=sudden.id, targets=[murder.id, elf.id], target_counts=[1, 1])
    act(s, "p2", type="concede")
    settle(s)
    assert s.state.rules.decision is None
    assert elf.controller == "p3" and bear.zone == "p1:battlefield"


def cold93(s, tmp_path, body):
    import subprocess
    import sys

    import app

    saved = tmp_path / "exchange93.json"
    saved.write_text(s.state.model_dump_json())
    code = (
        """import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import pick
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
"""
        + body
        + "\nrepo.close()\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(s.cards.db_path)],
        cwd=Path(app.__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_genuine_cold_layered_stack_control_restores_after_concession93(cards, tmp_path):
    s = table(cards, ["Aethersnatch"], ["Grizzly Bears"], ["Sol Ring"])
    bear = put(s, "Grizzly Bears", "hand", pid="p2")
    steal = put(s, "Aethersnatch", "hand")
    start(s, turn=5)
    act(s, "p2", type="set_prefs", hold_priority=True)
    cast_pending(s, "p2", bear, C=1, G=1)
    cast_pending(s, "p1", steal, [bear.id], C=4, U=2)
    resolve_only(s, steal)
    assert bear.zone == "stack" and bear.controller == "p1"
    cold93(
        s,
        tmp_path,
        f"act(s,'p1',type='concede')\nassert s.state.cards[{bear.id!r}].zone=='stack'\nassert s.state.cards[{bear.id!r}].controller=='p2'",
    )


def test_genuine_cold_chimera_optional_native_continuation93(cards, tmp_path):
    s, source, murder, bear, elf = chimera_pending93(cards)
    cold93(
        s,
        tmp_path,
        f"pick(s,['yes']);settle(s)\nassert s.state.rules.decision.player=='p1'\npick(s,[{elf.id!r}]);settle(s)\nassert s.state.cards[{source.id!r}].controller=='p2'\nassert s.state.cards[{elf.id!r}].zone=='p3:graveyard'",
    )


def test_chimera_original_source_blinked_before_trigger_cannot_exchange93(cards):
    from tests.test_rules_library_look import settle

    s = table(cards, ["Perplexing Chimera", "Cloudshift", "Grizzly Bears"], ["Murder"], ["Sol Ring"])
    source = put(s, "Perplexing Chimera", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    theirs = put(s, "Murder", "hand", pid="p2")
    blink = put(s, "Cloudshift", "hand")
    start(s, turn=5)
    original = s.state.rules.object_id(source.id)
    act(s, "p2", type="set_prefs", hold_priority=True)
    cast_pending(s, "p2", theirs, [bear.id], C=1, B=2)
    cast_pending(s, "p1", blink, [source.id], W=1)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.rules.object_id(source.id) != original
    assert source.zone == "p1:battlefield" and source.controller == "p1"
    assert bear.zone == "p1:graveyard"


def test_spell_control_persists_when_exchanged_chimera_leaves93(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_library_look import settle

    s = table(cards, ["Perplexing Chimera", "Murder"], ["Grizzly Bears"], ["Sol Ring"])
    source = put(s, "Perplexing Chimera", "battlefield")
    bear = put(s, "Grizzly Bears", "hand", pid="p2")
    kill = put(s, "Murder", "hand")
    start(s, turn=5)
    cast_pending(s, "p2", bear, C=1, G=1)
    settle(s)
    pick(s, ["yes"])
    # Stop as soon as the trigger leaves: don't resolve the exchanged creature spell.
    assert source.controller == "p2" and bear.zone == "stack" and bear.controller == "p1"
    cast_pending(s, "p1", kill, [source.id], C=1, B=2)
    settle(s)
    assert s.state.rules.decision.player == "p2"
    pick(s, ["no"])
    resolve_only(s, kill)
    assert source.zone == "p1:graveyard"
    assert bear.zone == "stack" and bear.controller == "p1"
    settle(s)
    assert bear.zone == "p1:battlefield" and bear.owner == "p2"


def sudden_pending93(cards):
    from tests.test_rules_library_look import settle

    s = table(cards, ["Sudden Substitution", "Grizzly Bears"], ["Murder"], ["Llanowar Elves"])
    bear = put(s, "Grizzly Bears", "battlefield")
    elf = put(s, "Llanowar Elves", "battlefield", pid="p3")
    murder = put(s, "Murder", "hand", pid="p2")
    sudden = put(s, "Sudden Substitution", "hand")
    start(s, turn=5)
    act(s, "p2", type="set_prefs", hold_priority=True)
    cast_pending(s, "p2", murder, [bear.id], C=1, B=2)
    wait_priority(s, "p1")
    mana(s, C=2, U=2)
    act(s, "p1", type="cast_spell", card_id=sudden.id, targets=[murder.id, elf.id], target_counts=[1, 1])
    settle(s)
    assert s.state.rules.decision.player == "p3"
    return s, murder, bear, elf


def test_genuine_cold_sudden_spell_controller_retargets93(cards, tmp_path):
    s, murder, bear, elf = sudden_pending93(cards)
    cold93(
        s,
        tmp_path,
        f"assert s.state.rules.decision.player=='p3'\npick(s,[{elf.id!r}]);settle(s)\nassert s.state.cards[{elf.id!r}].zone=='p3:graveyard'\nassert s.state.cards[{bear.id!r}].zone=='p1:battlefield'\nassert s.state.cards[{murder.id!r}].zone=='p2:graveyard'",
    )


def test_new_spell_controller_leaves_during_retarget_no_new_target_offer93(cards):
    from tests.test_rules_library_look import settle

    s, murder, bear, elf = sudden_pending93(cards)
    act(s, "p3", type="concede")
    assert murder.controller == "p2"
    assert s.state.rules.decision is None
    settle(s)
    assert bear.zone == "p1:graveyard" and murder.zone == "p2:graveyard"


def test_original_stack_control_history_pruned_after_permanent_resolves93(cards):
    from tests.test_rules_library_look import settle

    s = table(cards, ["Aethersnatch"], ["Grizzly Bears", "Murder"], ["Sol Ring"])
    bear = put(s, "Grizzly Bears", "hand", pid="p2")
    steal = put(s, "Aethersnatch", "hand")
    start(s, turn=5)
    act(s, "p2", type="set_prefs", hold_priority=True)
    cast_pending(s, "p2", bear, C=1, G=1)
    original = s.state.rules.object_id(bear.id)
    cast_pending(s, "p1", steal, [bear.id], C=4, U=2)
    resolve_only(s, steal)
    assert s.state.rules.control_baselines[original] == "p2"
    assert any(original in e.affected and e.layer == "2" for e in s.state.rules.effects)
    settle(s)
    assert bear.zone == "p1:battlefield" and bear.controller == "p1"
    assert s.state.rules.object_id(bear.id) != original
    assert original not in s.state.rules.control_baselines
    from app.rules import layers

    new = s.state.rules.object_id(bear.id)
    layers.prune(s.state)
    assert any(original in e.affected and new in e.affected for e in s.state.rules.effects)
    kill = put(s, "Murder", "hand", pid="p2")
    cast_pending(s, "p2", kill, [bear.id], C=1, B=2)
    settle(s)
    assert bear.zone == "p2:graveyard"
    layers.prune(s.state)
    assert not any(original in e.affected for e in s.state.rules.effects)


def test_sudden_split_second_blocks_ordinary_response_atomically93(cards):
    from app.game.errors import ActionError

    s = table(cards, ["Sudden Substitution", "Grizzly Bears"], ["Murder"], ["Counterspell", "Llanowar Elves"])
    bear = put(s, "Grizzly Bears", "battlefield")
    elf = put(s, "Llanowar Elves", "battlefield", pid="p3")
    murder = put(s, "Murder", "hand", pid="p2")
    sudden = put(s, "Sudden Substitution", "hand")
    counter = put(s, "Counterspell", "hand", pid="p3")
    start(s, turn=5)
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", hold_priority=True)
    cast_pending(s, "p2", murder, [bear.id], C=1, B=2)
    wait_priority(s, "p1")
    mana(s, C=2, U=2)
    act(s, "p1", type="cast_spell", card_id=sudden.id, targets=[murder.id, elf.id], target_counts=[1, 1])
    wait_priority(s, "p3")
    mana(s, pid="p3", U=2)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError, match="[Ss]plit second"):
        act(s, "p3", type="cast_spell", card_id=counter.id, targets=[sudden.id])
    assert s.state.model_dump_json() == before
