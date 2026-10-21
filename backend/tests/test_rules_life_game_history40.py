"""Actual Gollum/Blood Tyrant histories and native player departures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import attack, cast
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_life_history_outcomes40 import DATA
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import stops, to_phase


@pytest.fixture()
def cards(settings):
    rows = [
        *DATA,
        *json.loads((Path(__file__).parent / "fixtures/life_game_history40_supports.json").read_text()),
    ]
    base = {c["name"]: c for c in fixture_cards()}
    for i, row in enumerate(rows):
        base[row["name"]] = card(
            row["name"], set_code="lg40", number=str(i), **{k: v for k, v in row.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards, seats=3, letters=1):
    names = [
        "Gollum, Obsessed Stalker",
        "Blood Tyrant",
        "Healing Salve",
        "Fervor",
        "Grizzly Bears",
        "Lightning Bolt",
        "Platinum Angel",
        "Bloodletter of Aclazotz",
        "Door to Nothingness",
        "Witness Protection",
        "Act of Aggression",
        "Cloudshift",
        "Archfiend of Despair",
        "Platinum Emperion",
        "Tainted Remedy",
        "Solemnity",
        "Doubling Season",
        "Stifle",
        "Clone",
    ]
    names.extend(["Bloodletter of Aclazotz"] * (letters - 1))
    if seats == 3:
        s = table(cards, names, names, names)
    else:
        from app.game.factory import PlayerSetup, new_game
        from app.game.session import GameSession
        from tests.game_helpers import deck, enable

        decks = [
            deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (20, "Forest")]) for _ in range(seats)
        ]
        s = GameSession(
            enable(new_game([PlayerSetup(str(i), cards=d) for i, d in enumerate(decks)], shuffle=False)),
            cards=cards,
        )
        for pid in s.state.players:
            act(s, pid, type="set_prefs", response="on")
        act(s, "p1", type="pass_priority")
    start(s)
    put(s, "Fervor", "battlefield")
    stops(s, "upkeep", "main1", "declare_attackers", "declare_blockers", "combat_damage", "main2", "end")
    return s


def test_blood_tyrant_actual_upkeep_all_players(cards):
    s = game(cards)
    tyrant = put(s, "Blood Tyrant", "battlefield")
    to_phase(s, "upkeep", turn=7)
    settle(s)
    assert [p.life for p in s.state.players.values()] == [39, 39, 39]
    assert s.state.cards[tyrant.id].counters.get("+1/+1") == 3
    roundtrip(s)


def test_blood_tyrant_concession_actual_trigger(cards):
    s = game(cards)
    tyrant = put(s, "Blood Tyrant", "battlefield")
    act(s, "p2", type="concede")
    settle(s)
    assert s.state.cards[tyrant.id].counters.get("+1/+1") == 5
    roundtrip(s)


def test_gollum_actual_combat_and_gross_gain(cards):
    s = game(cards)
    gollum = put(s, "Gollum, Obsessed Stalker", "battlefield")
    attack(s, [gollum], turn=4)
    to_phase(s, "main2", turn=4)
    cast(s, "Healing Salve", ["p1"], modes=[0])
    cast(s, "Lightning Bolt", ["p1"])
    assert s.state.players["p1"].life == 40
    to_phase(s, "end", turn=4)
    settle(s)
    assert s.state.players["p2"].life == 36  # one combat, three recorded gain
    assert s.state.players["p3"].life == 40
    assert Plan(s.state, "p1", cards, None).rules.named_combat_damage
    roundtrip(s)


def test_blood_tyrant_state_based_loss(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s = game(cards)
    tyrant = put(s, "Blood Tyrant", "battlefield")
    act(s, "p2", type="life", player="p2", delta=-40)
    wait_priority(s, "p1")
    act(s, "p1", type="pass_priority")
    settle(s)
    assert s.state.rules.lost.get("p2")
    assert s.state.cards[tyrant.id].counters.get("+1/+1") == 5
    roundtrip(s)


def test_blood_tyrant_effect_loss(cards):
    from tests.test_rules_conditional_prevention import activate

    s = game(cards)
    tyrant = put(s, "Blood Tyrant", "battlefield")
    door = put(s, "Door to Nothingness", "battlefield")
    activate(s, door, "Target player loses the game", ["p2"])
    assert s.state.rules.lost.get("p2")
    assert s.state.cards[tyrant.id].counters.get("+1/+1") == 5
    roundtrip(s)


def test_gollum_name_at_damage_not_current_name(cards):
    s = game(cards)
    gollum = put(s, "Gollum, Obsessed Stalker", "battlefield")
    aura = cast(s, "Witness Protection", [gollum.id])
    attack(s, [gollum], turn=7)
    to_phase(s, "main2", turn=7)
    cast(s, "Healing Salve", ["p1"], modes=[0])
    # The printed name returns before the end-step ability can trigger.
    act(s, "p1", type="move", card_ids=[aura.id], to={"zone": "graveyard"})
    to_phase(s, "end", turn=7)
    settle(s)
    assert s.state.players["p2"].life == 39
    assert "gollum, obsessed stalker" not in s.state.rules.named_combat_damage
    roundtrip(s)


def test_blood_tyrant_simultaneous_two_players_lose(cards):
    s = game(cards, seats=4)
    tyrant = put(s, "Blood Tyrant", "battlefield")
    for pid in ["p2", "p3"]:
        act(s, pid, type="life", player=pid, delta=-40)
    act(s, s.state.rules.priority, type="pass_priority")
    settle(s)
    assert set(s.state.rules.lost) == {"p2", "p3"}
    assert s.state.cards[tyrant.id].counters.get("+1/+1") == 10
    roundtrip(s)


def test_loser_owned_source_triggers_for_surviving_controller(cards):
    s = game(cards)
    tyrant = put(s, "Blood Tyrant", "battlefield", "p2")
    cast(s, "Act of Aggression", [tyrant.id], life_symbols=[])
    assert s.state.cards[tyrant.id].controller == "p1"
    act(s, "p2", type="concede")
    abilities = [c for c in s.state.cards.values() if c.zone == "stack" and c.ability]
    assert len(abilities) == 1 and abilities[0].controller == "p1"
    assert abilities[0].ability.source_id == tyrant.id
    settle(s)
    assert not s.state.rules.pending_triggers
    roundtrip(s)


def test_losing_controller_cannot_put_own_tyrant_trigger_on_stack(cards):
    s = game(cards)
    put(s, "Blood Tyrant", "battlefield", "p2")
    act(s, "p2", type="concede")
    assert not s.state.rules.pending_triggers
    assert not any(c.zone == "stack" and c.ability for c in s.state.cards.values())
    roundtrip(s)


def test_gollum_other_controller_earlier_turn_and_new_incarnation(cards):
    s = game(cards)
    other = put(s, "Gollum, Obsessed Stalker", "battlefield", "p2")
    put(s, "Fervor", "battlefield", "p2")
    attack(s, [other], pid="p2", target="p3", turn=5)
    to_phase(s, "main2", turn=5)
    act(s, "p2", type="move", card_ids=[other.id], to={"zone": "graveyard"})
    to_phase(s, "main1", turn=7)
    mine = put(s, "Gollum, Obsessed Stalker", "battlefield")
    cast(s, "Cloudshift", [mine.id])
    cast(s, "Healing Salve", ["p1"], modes=[0])
    to_phase(s, "end", turn=7)
    settle(s)
    assert s.state.players["p2"].life == 40
    assert s.state.players["p3"].life == 36
    roundtrip(s)


def test_legacy_unknown_named_history_is_explicit_not_inferred(cards):
    s = game(cards)
    put(s, "Gollum, Obsessed Stalker", "battlefield")
    saved = s.state.model_dump(mode="json")
    for key in ["named_combat_damage", "named_combat_history_known", "named_combat_history_notice"]:
        saved["rules"].pop(key, None)
    from app.game.state import GameState

    s.state = GameState.model_validate(saved)
    cast(s, "Healing Salve", ["p1"], modes=[0])
    to_phase(s, "end", turn=4)
    settle(s)
    assert not s.state.rules.named_combat_history_known
    assert s.state.rules.named_combat_history_notice
    assert s.state.players["p2"].life == 40
    roundtrip(s)


def pending_loss(s):
    tyrant = put(s, "Blood Tyrant", "battlefield")
    # Seven real identical replacements exceed the native order-exploration budget.
    # This produces an honest native 616 chooser without inventing a replacement.
    letters = [
        c.id for c in s.state.cards.values() if c.owner == "p1" and c.name == "Bloodletter of Aclazotz"
    ]
    assert len(letters) == 7
    act(s, "p1", type="move", card_ids=letters, to={"player": "p1", "zone": "battlefield"})
    for pid in ["p2", "p3"]:
        act(s, pid, type="life", player=pid, delta=960)
    to_phase(s, "upkeep", turn=7)
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.resume["step"] == "replace_order"
    return tyrant


def complete_choices(s):
    for _ in range(25):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            return
        act(
            s,
            d.player,
            type="choose",
            decision_id=d.id,
            option_ids=[o.id for o in d.options][: max(1, d.min_choices)],
        )
    raise AssertionError("choices did not finish")


def test_tyrant_actual_replacement_bound_loss_saved_and_cold(cards, tmp_path):
    import subprocess
    import sys

    s = game(cards, letters=7)
    tyrant = pending_loss(s)
    roundtrip(s)
    saved = tmp_path / "tyrant40.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_life_game_history40 import complete_choices
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
complete_choices(s)
assert [p.life for p in s.state.players.values()]==[39,872,872]
assert s.state.cards[sys.argv[3]].counters.get('+1/+1')==257
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), tyrant.id],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    complete_choices(s)
    assert [p.life for p in s.state.players.values()] == [39, 872, 872]
    assert s.state.cards[tyrant.id].counters.get("+1/+1") == 257
    roundtrip(s)


@pytest.mark.parametrize("answer", ["stifle", "blink", "steal"])
def test_game_loss_trigger_counterable_and_exact_source(cards, answer):
    s = game(cards)
    tyrant = put(s, "Blood Tyrant", "battlefield")
    act(s, "p3", type="concede")
    ability = next(c for c in s.state.cards.values() if c.zone == "stack" and c.ability)
    if answer == "stifle":
        cast(s, "Stifle", [ability.id])
    elif answer == "blink":
        cast(s, "Cloudshift", [tyrant.id])
    else:
        cast(s, "Act of Aggression", [tyrant.id], pid="p2", life_symbols=[])
    settle(s)
    assert s.state.cards[tyrant.id].counters.get("+1/+1", 0) == (5 if answer == "steal" else 0)
    assert s.state.cards[tyrant.id].controller == ("p2" if answer == "steal" else "p1")
    roundtrip(s)


def test_tyrant_counts_zero_when_player_cannot_lose_life(cards):
    s = game(cards)
    tyrant = put(s, "Blood Tyrant", "battlefield")
    put(s, "Platinum Emperion", "battlefield")
    to_phase(s, "upkeep", turn=7)
    settle(s)
    assert [p.life for p in s.state.players.values()] == [40, 39, 39]
    assert s.state.cards[tyrant.id].counters.get("+1/+1") == 2
    roundtrip(s)


def test_concession_ignores_cannot_lose_game(cards):
    s = game(cards)
    tyrant = put(s, "Blood Tyrant", "battlefield")
    put(s, "Platinum Angel", "battlefield", "p2")
    act(s, "p2", type="concede")
    settle(s)
    assert s.state.cards[tyrant.id].counters.get("+1/+1") == 5
    roundtrip(s)


@pytest.mark.parametrize("name", ["Gollum, Obsessed Stalker", "Blood Tyrant"])
def test_canonical_full(cards, name):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == "FULL", result.manual_parts
