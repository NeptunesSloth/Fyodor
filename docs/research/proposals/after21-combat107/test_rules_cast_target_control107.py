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

DATA = json.loads((Path(__file__).parent / "fixtures/cast_target_control107_cards.json").read_text())
NAMES = ["Loki, God of Lies", "Dack Fayden"]


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
                "Giant Growth",
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
def test_whole107(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def pair107(cards, name):
    from tests.test_rules_wave7b_activation import ability_index

    s = setup95(cards)
    start(s)
    source = put(s, name, "battlefield")
    if name == NAMES[1]:
        act(s, "p1", type="set_counter", card_id=source.id, kind="loyalty", value=6)
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=source.id,
            ability=ability_index(s, source, "You get an emblem"),
        )
        settle(s)
        assert s.state.cards[source.id].zone == "p1:graveyard"
        assert any(
            c.zone == "p1:command" and c.token and c.token.type_line == "Emblem"
            for c in s.state.cards.values()
        )
    return s, source


def pending107(s, target, spell="Giant Growth"):
    source = put(s, spell, "hand")
    mana(s, C=10, W=10, U=10, B=10, R=10, G=10)
    act(s, "p1", type="cast_spell", card_id=source.id, targets=[target.id])
    assert any(e.kind == "trigger" and e.event and e.event.cast_targets for e in s.state.rules.stack.values())
    return source


def test_loki_own_turn_untaps_haste_and_control_expires107(cards):
    from tests.test_rules_wave30m_durations import chars

    s, source = pair107(cards, NAMES[0])
    target = put(s, "Grizzly Bears", "battlefield", pid="p2")
    act(s, "p2", type="tap", card_ids=[target.id], tapped=True)
    cast95(s, "Giant Growth", [target.id])
    assert s.state.cards[target.id].controller == "p1" and not s.state.cards[target.id].tapped
    assert "haste" in chars(s, target).keywords
    to_phase(s, "main1", turn=5)
    assert s.state.cards[target.id].controller == "p2" and "haste" not in chars(s, target).keywords


def test_loki_opponent_turn_control_does_not_untap_or_give_haste107(cards):
    from tests.test_rules_wave30m_durations import chars

    s, source = pair107(cards, NAMES[0])
    target = put(s, "Grizzly Bears", "battlefield", pid="p2")
    to_phase(s, "main1", turn=5)
    act(s, "p2", type="tap", card_ids=[target.id], tapped=True)
    cast95(s, "Giant Growth", [target.id])
    assert s.state.cards[target.id].controller == "p1" and s.state.cards[target.id].tapped
    assert "haste" not in chars(s, target).keywords
    to_phase(s, "main1", turn=6)
    assert s.state.cards[target.id].controller == "p2"


@pytest.mark.parametrize("single", [True, False])
def test_loki_counts_distinct_cast_targets_not_target_words107(cards, single):
    s, source = pair107(cards, NAMES[0])
    first = put(s, "Grizzly Bears", "battlefield", pid="p2")
    second = put(s, "Llanowar Elves", "battlefield", pid="p2")
    cast95(
        s,
        "Seeds of Strength",
        [first.id, first.id, first.id if single else second.id],
        target_counts=[1, 1, 1],
    )
    assert s.state.cards[first.id].controller == ("p1" if single else "p2")
    assert s.state.cards[second.id].controller == "p2"


def test_original_creature_blink_does_not_take_new_incarnation107(cards):
    s, source = pair107(cards, NAMES[0])
    target = put(s, "Grizzly Bears", "battlefield", pid="p2")
    pending107(s, target)
    oid = s.state.rules.object_id(target.id)
    cast95(s, "Cloudshift", [target.id], pid="p2")
    assert s.state.rules.object_id(target.id) != oid
    assert s.state.cards[target.id].controller == "p2"


def test_untargeted_control_ignores_later_shroud107(cards):
    s, source = pair107(cards, NAMES[0])
    target = put(s, "Grizzly Bears", "battlefield", pid="p2")
    pending107(s, target)
    cast95(s, "Veil of Secrecy", [target.id], pid="p2")
    assert s.state.cards[target.id].controller == "p1"


def test_native_dack_ultimate_controls_all_original_permanents_indefinitely107(cards):
    s, source = pair107(cards, NAMES[1])
    first = put(s, "Grizzly Bears", "battlefield", pid="p2")
    second = put(s, "Llanowar Elves", "battlefield", pid="p2")
    cast95(s, "Seeds of Strength", [first.id, second.id, first.id], target_counts=[1, 1, 1])
    assert s.state.cards[first.id].controller == s.state.cards[second.id].controller == "p1"
    to_phase(s, "main1", turn=5)
    assert s.state.cards[first.id].controller == s.state.cards[second.id].controller == "p1"
    assert s.state.cards[source.id].zone == "p1:graveyard"


def test_dack_original_cast_targets_survive_countered_spell107(cards):
    s, source = pair107(cards, NAMES[1])
    target = put(s, "Sol Ring", "battlefield", pid="p2")
    spell = pending107(s, target, "Shatter")
    cast95(s, "Counterspell", [spell.id])
    assert s.state.cards[spell.id].zone == "p1:graveyard"
    assert s.state.cards[target.id].zone == "p1:battlefield" and s.state.cards[target.id].controller == "p1"


def test_dack_other_players_cast_does_not_trigger107(cards):
    s, source = pair107(cards, NAMES[1])
    target = put(s, "Grizzly Bears", "battlefield", pid="p3")
    cast95(s, "Giant Growth", [target.id], pid="p2")
    assert s.state.cards[target.id].controller == "p3"


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
def test_genuine_cold_original_cast_target_trigger107(cards, name, tmp_path):
    s, source = pair107(cards, name)
    target = put(s, "Grizzly Bears", "battlefield", pid="p2")
    pending107(s, target)
    expected = "p2" if name == NAMES[0] else "p1"
    body = "settle(s)\n" + f"assert s.state.cards[{target.id!r}].controller=='p1'\n"
    body += "from tests.test_rules_wave30m_durations import to_phase\nto_phase(s,'main1',turn=5)\n"
    body += f"assert s.state.cards[{target.id!r}].controller=={expected!r}"
    cold95(s, tmp_path, body)
