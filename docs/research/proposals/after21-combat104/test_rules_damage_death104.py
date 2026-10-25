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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase as phase_until
from tests.test_rules_wave30p_combat import attack, block

DATA = json.loads((Path(__file__).parent / "fixtures/damage_death104_cards.json").read_text())
NAMES = ["Scythe of the Wretched", "Vampiric Embrace"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="cmd95", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup95(cards):
    names = list(
        dict.fromkeys(
            [c["name"] for c in DATA]
            + [
                "Grizzly Bears",
                "Llanowar Elves",
                "Sol Ring",
                "Cloudshift",
                "Murder",
                "Counterspell",
                "Wrath of God",
                "Lightning Bolt",
                "Forest",
            ]
        )
    )
    s = table(cards, names, names, names)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", full_control=True, hold_priority=True)
    return s


def to_phase(s, phase, turn=None):
    phase_until(s, phase, turn=turn)
    if phase in ("declare_attackers", "declare_blockers"):
        for _ in range(12):
            d = s.state.rules.decision
            if d is not None or s.state.turn.phase != phase:
                break
            act(s, s.state.rules.priority, type="pass_priority")


def start(s, turn=4):
    to_phase(s, "main1", turn=turn)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", full_control=True, hold_priority=True)


def combat95(s, attackers, blockers=()):
    to_phase(s, "declare_attackers", turn=4)
    attack(s, *[(c, "p2") for c in attackers])
    to_phase(s, "declare_blockers", turn=4)
    if s.state.rules.decision and s.state.rules.decision.kind == "declare_blockers":
        block(s, "p2", *blockers)
    else:
        assert not blockers
    to_phase(s, "main2", turn=4)


def cast95(s, name, targets=(), pid="p1", **extra):
    source = put(s, name, "hand", pid=pid)
    wait_priority(s, pid)
    mana(s, pid=pid, C=20, W=20, U=20, B=20, R=20, G=20)
    act(s, pid, type="cast_spell", card_id=source.id, targets=list(targets), **extra)
    settle(s)
    return source


@pytest.mark.parametrize("name", NAMES)
def test_whole104(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def pair104(cards, name):
    s = setup95(cards)
    host = put(s, "Grizzly Bears", "battlefield")
    bow = put(s, "Viridian Longbow", "battlefield")
    start(s)
    if name == NAMES[1]:
        source = cast95(s, name, [host.id])
    else:
        source = put(s, name, "battlefield")
        act(s, "p1", type="attach", card_ids=[source.id], to=host.id)
    act(s, "p1", type="attach", card_ids=[bow.id], to=host.id)
    return s, source, host


def shoot104(s, host, target):
    from tests.test_rules_wave4h_activation_costs import ability

    act(
        s,
        "p1",
        type="activate_ability",
        card_id=host.id,
        ability=ability(s, host, "{T}:"),
        targets=[target.id],
    )
    settle(s)


@pytest.mark.parametrize("name", NAMES)
def test_native_host_damage_death104(cards, name):
    s, source, host = pair104(cards, name)
    victim = put(s, "Llanowar Elves", "battlefield", pid="p2")
    shoot104(s, host, victim)
    if name == NAMES[0]:
        assert s.state.cards[victim.id].zone == "p1:battlefield"
        assert s.state.cards[source.id].attached_to == victim.id
    else:
        assert s.state.cards[victim.id].zone == "p2:graveyard"
        assert s.state.cards[host.id].counters.get("+1/+1") == 1


@pytest.mark.parametrize("name", NAMES)
def test_native_wrong_source_no_trigger104(cards, name):
    s, source, host = pair104(cards, name)
    victim = put(s, "Llanowar Elves", "battlefield", pid="p2")
    cast95(s, "Lightning Bolt", [victim.id])
    assert s.state.cards[victim.id].zone == "p2:graveyard"
    assert not s.state.cards[host.id].counters


@pytest.mark.parametrize("name", NAMES)
def test_detached_before_death_no_trigger104(cards, name):
    s, source, host = pair104(cards, name)
    victim = put(s, "Grizzly Bears", "battlefield", pid="p2")
    shoot104(s, host, victim)
    other = put(s, "Llanowar Elves", "battlefield")
    act(s, "p1", type="attach", card_ids=[source.id], to=other.id)
    cast95(s, "Murder", [victim.id])
    assert s.state.cards[victim.id].zone == "p2:graveyard"
    assert not s.state.cards[host.id].counters and not s.state.cards[other.id].counters


def pending104(s, source, host, victim):
    from tests.test_rules_wave4h_activation_costs import ability

    act(
        s,
        "p1",
        type="activate_ability",
        card_id=host.id,
        ability=ability(s, host, "{T}:"),
        targets=[victim.id],
    )
    for _ in range(20):
        if any(e.kind == "trigger" and e.source_card == source.id for e in s.state.rules.stack.values()):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("missing native damage/death trigger")


@pytest.mark.parametrize("name", NAMES)
def test_original_host_bound_at_death104(cards, name):
    s, source, host = pair104(cards, name)
    victim = put(s, "Llanowar Elves", "battlefield", pid="p2")
    other = put(s, "Llanowar Elves", "battlefield")
    pending104(s, source, host, victim)
    act(s, "p1", type="attach", card_ids=[source.id], to=other.id)
    settle(s)
    if name == NAMES[1]:
        assert s.state.cards[host.id].counters.get("+1/+1") == 1
        assert not s.state.cards[other.id].counters
    else:
        assert s.state.cards[victim.id].zone == "p1:battlefield"
        assert s.state.cards[source.id].attached_to == victim.id


def test_scythe_host_dies_simultaneously_with_victim104(cards):
    s, source, host = pair104(cards, NAMES[0])
    victim = put(s, "Grizzly Bears", "battlefield", pid="p2")
    shoot104(s, host, victim)
    cast95(s, "Wrath of God")
    assert s.state.cards[host.id].zone == "p1:graveyard"
    assert s.state.cards[victim.id].zone == "p1:battlefield"
    assert s.state.cards[source.id].attached_to == victim.id


def cold95(s, tmp_path, body):
    import subprocess
    import sys

    import app

    saved = tmp_path / "combat95.json"
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


@pytest.mark.parametrize("name", NAMES)
def test_genuine_cold_pending_host_death104(cards, name, tmp_path):
    s, source, host = pair104(cards, name)
    victim = put(s, "Llanowar Elves", "battlefield", pid="p2")
    pending104(s, source, host, victim)
    assertion = (
        f"assert s.state.cards[{victim.id!r}].zone=='p1:battlefield'"
        if name == NAMES[0]
        else f"assert s.state.cards[{host.id!r}].counters.get('+1/+1')==1"
    )
    cold95(s, tmp_path, "settle(s)\n" + assertion)
