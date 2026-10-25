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

DATA = json.loads((Path(__file__).parent / "fixtures/vampire_returns105_cards.json").read_text())
NAMES = ["Krovikan Vampire", "Seraph"]


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
def test_whole105(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def pair105(cards, name, victim_name="Llanowar Elves"):
    s = setup95(cards)
    source = put(s, name, "battlefield")
    bow = put(s, "Viridian Longbow", "battlefield")
    start(s)
    act(s, "p1", type="attach", card_ids=[bow.id], to=source.id)
    victim = put(s, victim_name, "battlefield", pid="p2")
    from tests.test_rules_wave4h_activation_costs import ability

    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability(s, source, "{T}:"),
        targets=[victim.id],
    )
    settle(s)
    assert s.state.cards[victim.id].zone == (
        "p2:graveyard" if victim_name == "Llanowar Elves" else "p2:battlefield"
    )
    return s, source, victim


@pytest.mark.parametrize("name", NAMES)
def test_native_end_return_then_original_source_lost105(cards, name):
    s, source, victim = pair105(cards, name)
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.cards[victim.id].zone == "p1:battlefield"
    cast95(s, "Dominate", [source.id], pid="p2", x_value=7)
    assert s.state.cards[source.id].controller == "p2"
    assert s.state.cards[victim.id].zone == "p2:graveyard"


@pytest.mark.parametrize("name", NAMES)
def test_source_dies_before_return105(cards, name):
    s, source, victim = pair105(cards, name)
    cast95(s, "Murder", [source.id])
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.cards[victim.id].zone == ("p1:battlefield" if name == NAMES[1] else "p2:graveyard")
    if name == NAMES[1]:
        assert not any(x.when.get("event") == "lose_control" for x in s.state.rules.delayed)


def test_seraph_foreign_at_return_regain_then_lose105(cards):
    s, source, victim = pair105(cards, NAMES[1])
    cast95(s, "Dominate", [source.id], pid="p2", x_value=7)
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.cards[victim.id].zone == "p1:battlefield"
    assert any(x.when.get("event") == "lose_control" for x in s.state.rules.delayed)
    cast95(s, "Dominate", [source.id], x_value=7)
    assert s.state.cards[victim.id].zone == "p1:battlefield"
    cast95(s, "Word of Seizing", [source.id], pid="p2")
    assert s.state.cards[victim.id].zone == "p2:graveyard"


@pytest.mark.parametrize("name", NAMES)
def test_blinked_source_cannot_claim_old_damage105(cards, name):
    s, source, victim = pair105(cards, name, "Grizzly Bears")
    original = s.state.rules.object_id(source.id)
    cast95(s, "Cloudshift", [source.id])
    assert s.state.rules.object_id(source.id) != original
    cast95(s, "Murder", [victim.id])
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:graveyard"


def test_krovikan_additional_damaged_creature_dies_in_response105(cards):
    from tests.test_rules_wave4h_activation_costs import ability

    s, source, victim = pair105(cards, NAMES[0])
    other = put(s, "Grizzly Bears", "battlefield", pid="p2")
    cast95(s, "Word of Seizing", [source.id])
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability(s, source, "{T}:"),
        targets=[other.id],
    )
    settle(s)
    to_phase(s, "end", turn=4)
    assert s.state.zones.get("stack")
    cast95(s, "Murder", [other.id])
    assert s.state.cards[victim.id].zone == "p1:battlefield"
    assert s.state.cards[other.id].zone == "p1:battlefield"


@pytest.mark.parametrize("name", NAMES)
def test_original_graveyard_object_not_new_incarnation105(cards, name):
    s, source, victim = pair105(cards, name)
    old = s.state.rules.object_id(victim.id)
    act(s, "p2", type="move", card_ids=[victim.id], to={"player": "p2", "zone": "hand"})
    act(s, "p2", type="move", card_ids=[victim.id], to={"player": "p2", "zone": "graveyard"})
    assert s.state.rules.object_id(victim.id) != old
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:graveyard"


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
def test_genuine_cold_after_damage_death_before_end105(cards, name, tmp_path):
    s, source, victim = pair105(cards, name)
    cold95(
        s,
        tmp_path,
        "from tests.test_rules_wave30m_durations import to_phase\nto_phase(s,'end',turn=4)\nsettle(s)\n"
        + f"assert s.state.cards[{victim.id!r}].zone=='p1:battlefield'",
    )


def test_seraph_simultaneous_death_still_creates_return105(cards):
    s, source, victim = pair105(cards, NAMES[1], "Grizzly Bears")
    cast95(s, "Wrath of God")
    assert s.state.cards[source.id].zone == "p1:graveyard"
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.cards[victim.id].zone == "p1:battlefield"
    assert not any(x.when.get("event") == "lose_control" for x in s.state.rules.delayed)


def test_genuine_cold_krovikan_legacy_successor_unknown105(cards, tmp_path):
    from app.game.state import GameState

    s, source, victim = pair105(cards, NAMES[0])
    data = s.state.model_dump(mode="json")
    for departure in data["rules"]["turn_log"]["left"]:
        departure.pop("new_object_id105", None)
    s.state = GameState.model_validate(data)
    to_phase(s, "end", turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == "manual_resolution" and d.resume["step"] == "vampire_returns105_legacy"
    cold95(s, tmp_path, "pick(s,['done']);settle(s)\nassert s.state.rules.decision is None")


def test_loss_watcher_ignores_precreation_native_control_event105(cards):
    from app.rules import context, delayed, vampire_returns105
    from app.rules.plan import Plan

    s=setup95(cards)
    source=put(s,NAMES[1],"battlefield")
    returned=put(s,"Grizzly Bears","battlefield")
    start(s)
    p=Plan(s.state,"p1",s.cards,None)
    oid=p.oid(source)
    p.do({"type":"set_controller","card_ids":[source.id],"player":"p2"},actor="p1")
    sequence=vampire_returns105.loss_effects()
    ctx={"controller":"p1","source_card":source.id,"source_object":oid,"name":"Seraph",
         "effects":sequence,"next":1}
    context.bind_objects(p,ctx,"returned105",[returned.id])
    assert delayed.create(p,ctx,sequence[0])
    watch=p.rules.delayed[-1]
    assert watch.when["after_batch105"]==p.rules.batch
    assert not p.rules.pending_triggers
    delayed.on_events(p,list(p.rules.events))
    assert not p.rules.pending_triggers and watch in p.rules.delayed
    p.do({"type":"set_controller","card_ids":[source.id],"player":"p1"},actor="p1")
    p.do({"type":"set_controller","card_ids":[source.id],"player":"p2"},actor="p1")
    delayed.on_events(p,list(p.rules.events))
    assert len(p.rules.pending_triggers)==1 and watch not in p.rules.delayed
