from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.rules import casting, coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture
def cards(settings):
    import json

    from app.cards.importer import build_database
    from tests.fixtures.cards import card, fixture_cards

    base = {c["name"]: c for c in fixture_cards()}
    data = json.loads(
        (Path(__file__).parent / "fixtures/artifact_activation_watchers51_cards.json").read_text()
    )
    for i, c in enumerate(data):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    r = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield r
    r.close()


@pytest.mark.parametrize("name", ["Powerleech", "Haunting Wind", "Artifact Possession"])
def test_canonical_whole_card_coverage(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def setup(cards, name, source_name="Basalt Monolith", extra=()):
    s = table(cards, [name, "Twiddle"], [source_name, *extra], [])
    source = put(s, source_name, "battlefield", pid="p2")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    if name == "Artifact Possession":
        w = put(s, name, "hand")
        act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "B": 1})
        act(s, "p1", type="cast_spell", card_id=w.id, targets=[source.id], sources=[])
        answer(s)
        assert s.state.cards[w.id].attached_to == source.id
    else:
        w = put(s, name, "battlefield")
    wait_priority(s, "p2")
    act(s, "p2", type="set_prefs", hold_priority=True)
    return s, w, source


@pytest.mark.parametrize("name", ["Powerleech", "Haunting Wind", "Artifact Possession"])
def test_actual_tap_symbol_cost_triggers_once_then_without_tap_untap_ability_once(cards, name):
    s, w, source = setup(cards, name)
    before = {p: v.life for p, v in s.state.players.items()}
    index = next(i for i, a in casting.mana_abilities(s.state, source, cards))
    act(s, "p2", type="activate_ability", card_id=source.id, ability=index)
    answer(s)
    delta = 2 if name == "Artifact Possession" else 1
    if name == "Powerleech":
        assert s.state.players["p1"].life == before["p1"] + 1
    else:
        assert s.state.players["p2"].life == before["p2"] - delta
    wait_priority(s, "p2")
    index = next(
        a.index
        for a in Plan(s.state, "p2", cards, None).ch(source).abilities
        if a.kind == "activated" and "Untap" in a.text
    )
    act(s, "p2", type="activate_ability", card_id=source.id, ability=index, sources=[])
    answer(s)
    if name == "Powerleech":
        assert s.state.players["p1"].life == before["p1"] + 2
    else:
        assert s.state.players["p2"].life == before["p2"] - 2 * delta


@pytest.mark.parametrize("name", ["Powerleech", "Haunting Wind", "Artifact Possession"])
def test_actual_untap_symbol_mana_activation_has_no_tap_symbol_cost(cards, name):
    s = table(cards, [name], ["Pili-Pala"], [])
    source = put(s, "Pili-Pala", "battlefield", pid="p2")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    act(s, "p2", type="tap", card_ids=[source.id], tapped=True)
    if name == "Artifact Possession":
        w = put(s, name, "hand")
        act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "B": 1})
        act(s, "p1", type="cast_spell", card_id=w.id, targets=[source.id], sources=[])
        answer(s)
    else:
        w = put(s, name, "battlefield")
    wait_priority(s, "p2")
    act(s, "p2", type="set_prefs", hold_priority=True)
    before = {p: v.life for p, v in s.state.players.items()}
    act(s, "p2", type="add_mana", player="p2", mana={"C": 2})
    index = next(i for i, a in casting.mana_abilities(s.state, source, cards))
    act(s, "p2", type="activate_ability", card_id=source.id, ability=index)
    answer(s)
    assert not s.state.cards[source.id].tapped
    if name == "Powerleech":
        assert s.state.players["p1"].life == before["p1"] + 1
    else:
        assert s.state.players["p2"].life == before["p2"] - (2 if name == "Artifact Possession" else 1)


@pytest.mark.parametrize("name", ["Haunting Wind", "Artifact Possession"])
def test_damage_reads_exact_artifact_current_controller_at_resolution(cards, name):
    s, w, source = setup(cards, name)
    index = next(i for i, a in casting.mana_abilities(s.state, source, cards))
    act(s, "p2", type="activate_ability", card_id=source.id, ability=index)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p3")
    answer(s)
    assert s.state.players["p2"].life == 40
    assert s.state.players["p3"].life == 40 - (2 if name == "Artifact Possession" else 1)


@pytest.mark.parametrize("name", ["Powerleech", "Haunting Wind", "Artifact Possession"])
def test_plain_tap_event_without_activation_triggers_once(cards, name):
    s, w, source = setup(cards, name)
    before = {p: v.life for p, v in s.state.players.items()}
    wait_priority(s, "p1")
    spell = put(s, "Twiddle", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 1})
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[source.id], sources=[])
    answer(s)
    if name == "Powerleech":
        assert s.state.players["p1"].life == before["p1"] + 1
    else:
        assert s.state.players["p2"].life == before["p2"] - (2 if name == "Artifact Possession" else 1)


def test_old_unknown_cost_receipt_cannot_satisfy_without_tap_predicate():
    from app.game.rules_state import PaymentRecord
    from app.rules import activated_copy_effects

    old = PaymentRecord.model_validate({"card": "legacy", "controller": "p1"})
    assert old.activation_cost_has_tap is None
    assert not activated_copy_effects.matches({"has_tap": False}, {"has_tap": old.activation_cost_has_tap})
    assert activated_copy_effects.matches({"has_tap": False}, {"has_tap": False})
    assert not activated_copy_effects.matches({"has_tap": False}, {"has_tap": True})


@pytest.mark.parametrize("name", ["Powerleech", "Haunting Wind", "Artifact Possession"])
def test_tapping_other_permanents_cost_is_not_literal_tap_symbol(cards, name):
    s, w, source = setup(cards, name, source_name="Clock of Omens", extra=["Sol Ring"])
    ring = put(s, "Sol Ring", "battlefield", pid="p2")
    index = next(
        a.index for a in Plan(s.state, "p2", cards, None).ch(source).abilities if a.kind == "activated"
    )
    before = {p: v.life for p, v in s.state.players.items()}
    act(
        s,
        "p2",
        type="activate_ability",
        card_id=source.id,
        ability=index,
        targets=[source.id],
        cost_choices=[{"component": 0, "cards": [source.id, ring.id]}],
    )
    answer(s)
    assert s.state.cards[ring.id].tapped and not s.state.cards[source.id].tapped
    if name == "Powerleech":
        assert s.state.players["p1"].life == before["p1"] + 3
    else:
        assert s.state.players["p2"].life == before["p2"] - (4 if name == "Artifact Possession" else 3)


@pytest.mark.parametrize("name", ["Powerleech", "Haunting Wind", "Artifact Possession"])
@pytest.mark.parametrize("source_name", ["Lotus Petal", "Lion's Eye Diamond"])
def test_sacrificed_artifact_uses_exact_lki_controller_and_actual_tap_cost(cards, name, source_name):
    s, w, source = setup(cards, name, source_name=source_name)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p3")
    wait_priority(s, "p3")
    act(s, "p3", type="set_prefs", hold_priority=True)
    before = {p: v.life for p, v in s.state.players.items()}
    index = next(i for i, a in casting.mana_abilities(s.state, source, cards))
    act(s, "p3", type="activate_ability", card_id=source.id, ability=index)
    answer(s)
    assert s.state.cards[source.id].zone == "p2:graveyard"
    assert s.state.players["p2"].life == before["p2"]
    if name == "Powerleech":
        assert s.state.players["p1"].life == before["p1"] + 1
    elif name == "Haunting Wind":
        assert s.state.players["p3"].life == before["p3"] - 1
    else:
        # {T} already tapped the enchanted artifact; the no-{T} sacrifice
        # activation completes after the Aura has become unattached.
        assert s.state.players["p3"].life == before["p3"] - (2 if source_name == "Lotus Petal" else 0)


@pytest.mark.parametrize("name", ["Powerleech", "Haunting Wind", "Artifact Possession"])
def test_crew_keyword_records_no_literal_tap_cost_without_fabricated_payment(cards, name):
    s, w, source = setup(cards, name, source_name="Smuggler's Copter", extra=["Memnite"])
    helper = put(s, "Memnite", "battlefield", pid="p2")
    ch = Plan(s.state, "p2", cards, None).ch(source)
    index = next(a.index for a in ch.abilities if casting.crew_power(ch, a.index) is not None)
    before = {p: v.life for p, v in s.state.players.items()}
    act(s, "p2", type="activate_ability", card_id=source.id, ability=index, crew=[helper.id])
    answer(s)
    assert s.state.cards[helper.id].tapped and not s.state.cards[source.id].tapped
    assert Plan(s.state, "p2", cards, None).ch(source).is_creature
    if name == "Powerleech":
        assert s.state.players["p1"].life == before["p1"] + 2
    else:
        assert s.state.players["p2"].life == before["p2"] - 2


@pytest.mark.parametrize("name", ["Powerleech", "Haunting Wind", "Artifact Possession"])
def test_true_cold_untap_cost_paid_before_mana_color_choice(cards, tmp_path, name):
    import subprocess
    import sys

    s = table(cards, [name], ["Pili-Pala"], [])
    source = put(s, "Pili-Pala", "battlefield", pid="p2")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    act(s, "p2", type="tap", card_ids=[source.id], tapped=True)
    if name == "Artifact Possession":
        w = put(s, name, "hand")
        act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "B": 1})
        act(s, "p1", type="cast_spell", card_id=w.id, targets=[source.id], sources=[])
        answer(s)
    else:
        w = put(s, name, "battlefield")
    wait_priority(s, "p2")
    act(s, "p2", type="set_prefs", hold_priority=True)
    act(s, "p2", type="add_mana", player="p2", mana={"C": 2})
    index = next(i for i, a in casting.mana_abilities(s.state, source, cards))
    act(s, "p2", type="activate_ability", card_id=source.id, ability=index)
    assert s.state.rules.decision is not None
    assert not s.state.cards[source.id].tapped
    saved = tmp_path / "tap-cost.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.game.session import GameSession
from tests.test_rules_activated_copy_family import answer
repo=CardRepository(Path(sys.argv[-1]),ImageStore(Path(sys.argv[-1]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
s.view('p3');answer(s)
name=sys.argv[2]
if name=='Powerleech':assert s.state.players['p1'].life==41
else:assert s.state.players['p2'].life==40-(2 if name=='Artifact Possession' else 1)
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
"""
    run = subprocess.run(
        [sys.executable, "-c", code, str(saved), name, str(cards.db_path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert run.returncode == 0, run.stderr


@pytest.mark.parametrize("name", ["Powerleech", "Haunting Wind"])
def test_opponent_activates_your_artifact_uses_actor_for_trigger_and_source_controller_for_damage(
    cards, name
):
    s = table(cards, [name, "Well of Knowledge"], [], [])
    put(s, name, "battlefield")
    source = put(s, "Well of Knowledge", "battlefield")
    to_phase(s, "draw", 2)
    wait_priority(s, "p2")
    act(s, "p2", type="set_prefs", hold_priority=True)
    act(s, "p2", type="add_mana", player="p2", mana={"C": 2})
    index = next(
        a.index for a in Plan(s.state, "p2", cards, None).ch(source).abilities if a.kind == "activated"
    )
    act(s, "p2", type="activate_ability", card_id=source.id, ability=index, sources=[])
    answer(s)
    assert s.state.players["p1"].life == (41 if name == "Powerleech" else 39)
    assert s.state.players["p2"].life == 40


@pytest.mark.parametrize("name", ["Powerleech", "Haunting Wind"])
def test_nonartifact_activated_ability_does_not_trigger(cards, name):
    s = table(cards, [name], ["Shivan Dragon"], [])
    put(s, name, "battlefield")
    source = put(s, "Shivan Dragon", "battlefield", pid="p2")
    to_phase(s, "main1", 4)
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1})
    index = next(
        a.index for a in Plan(s.state, "p2", cards, None).ch(source).abilities if a.kind == "activated"
    )
    act(s, "p2", type="activate_ability", card_id=source.id, ability=index, sources=[])
    answer(s)
    assert all(p.life == 40 for p in s.state.players.values())


def test_powerleech_your_own_artifact_tap_and_activation_do_not_trigger(cards):
    s, w, source = setup(cards, "Powerleech")
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p1")
    wait_priority(s, "p1")
    index = next(i for i, a in casting.mana_abilities(s.state, source, cards))
    act(s, "p1", type="activate_ability", card_id=source.id, ability=index)
    answer(s)
    assert s.state.players["p1"].life == 40


def test_possession_reattachment_uses_current_host_for_new_activation(cards):
    s, w, source = setup(cards, "Artifact Possession", extra=["Grim Monolith"])
    other = put(s, "Grim Monolith", "battlefield", pid="p2")
    act(s, "p1", type="attach", card_ids=[w.id], to=other.id)
    act(s, "p2", type="add_mana", player="p2", mana={"C": 3})
    index = next(
        a.index for a in Plan(s.state, "p2", cards, None).ch(source).abilities if a.kind == "activated"
    )
    act(s, "p2", type="activate_ability", card_id=source.id, ability=index, sources=[])
    answer(s)
    assert s.state.players["p2"].life == 40
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"C": 4})
    index = next(
        a.index for a in Plan(s.state, "p2", cards, None).ch(other).abilities if a.kind == "activated"
    )
    act(s, "p2", type="activate_ability", card_id=other.id, ability=index, sources=[])
    answer(s)
    assert s.state.players["p2"].life == 38


def test_possession_pending_damage_keeps_original_event_artifact_after_reattach(cards):
    s, w, source = setup(cards, "Artifact Possession", extra=["Grim Monolith"])
    other = put(s, "Grim Monolith", "battlefield", pid="p2")
    index = next(i for i, a in casting.mana_abilities(s.state, source, cards))
    act(s, "p2", type="activate_ability", card_id=source.id, ability=index)
    act(s, "p1", type="attach", card_ids=[w.id], to=other.id)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p3")
    answer(s)
    assert s.state.players["p2"].life == 40 and s.state.players["p3"].life == 38


@pytest.mark.parametrize("name", ["Powerleech", "Haunting Wind", "Artifact Possession"])
def test_zero_output_artifact_mana_activation_still_taps_and_triggers_once(cards, name):
    s, w, source = setup(cards, name, source_name="Everflowing Chalice")
    assert not s.state.cards[source.id].counters
    before = {p: v.life for p, v in s.state.players.items()}
    index = next(i for i, a in casting.mana_abilities(s.state, source, cards))
    act(s, "p2", type="activate_ability", card_id=source.id, ability=index)
    answer(s)
    assert s.state.cards[source.id].tapped
    assert not s.state.players["p2"].mana and not s.state.players["p2"].mana_units
    if name == "Powerleech":
        assert s.state.players["p1"].life == before["p1"] + 1
    else:
        assert s.state.players["p2"].life == before["p2"] - (2 if name == "Artifact Possession" else 1)


@pytest.mark.parametrize("name", ["Powerleech", "Haunting Wind", "Artifact Possession"])
def test_true_cold_tapped_sacrificed_token_event_retains_lki(cards, tmp_path, name):
    import subprocess
    import sys

    s = table(cards, [name], [], [])
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    act(
        s,
        "p2",
        type="create_token",
        player="p2",
        token={
            "name": "Treasure",
            "type_line": "Token Artifact — Treasure",
            "text": "{T}, Sacrifice this artifact: Add one mana of any color.",
        },
    )
    source = next(c for c in s.state.cards.values() if c.name == "Treasure" and c.controller == "p2")
    if name == "Artifact Possession":
        w = put(s, name, "hand")
        act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "B": 1})
        act(s, "p1", type="cast_spell", card_id=w.id, targets=[source.id], sources=[])
        answer(s)
    else:
        w = put(s, name, "battlefield")
    wait_priority(s, "p2")
    act(s, "p2", type="set_prefs", hold_priority=True)
    index = next(i for i, a in casting.mana_abilities(s.state, source, cards))
    act(s, "p2", type="activate_ability", card_id=source.id, ability=index)
    d = s.state.rules.decision
    if d is not None:
        chosen = next((o.id for o in d.options if o.id == "Green"), d.options[0].id)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[chosen])
    assert source.id not in s.state.cards
    assert any(e.kind == "trigger" for e in s.state.rules.stack.values())
    saved = tmp_path / "token-tap.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.game.session import GameSession
from tests.test_rules_activated_copy_family import answer
repo=CardRepository(Path(sys.argv[-1]),ImageStore(Path(sys.argv[-1]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
s.view('p3');answer(s)
name=sys.argv[2]
if name=='Powerleech':assert s.state.players['p1'].life==41
else:assert s.state.players['p2'].life==40-(2 if name=='Artifact Possession' else 1)
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
"""
    run = subprocess.run(
        [sys.executable, "-c", code, str(saved), name, str(cards.db_path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert run.returncode == 0, run.stderr
