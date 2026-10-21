"""Canonical native life44 instructions and saved continuations."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import activate, cast
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / "fixtures/life_sequences44_cards.json").read_text())


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards, extra=()):
    names = [
        "Ajani, Strength of the Pride",
        "Sorin, Grim Nemesis",
        "Resolute Archangel",
        "Sol Ring",
        "Grizzly Bears",
        "Llanowar Elves",
        "Forest",
        "Healing Salve",
        *extra,
    ]
    s = table(cards, names, names, names)
    start(s)
    return s


def test_ajani_true_condition_one_packet_own_and_opponents(cards):
    s = game(cards)
    source = cast(s, "Ajani, Strength of the Pride")
    ours = put(s, "Sol Ring", "battlefield")
    their = put(s, "Grizzly Bears", "battlefield", "p2")
    ring = put(s, "Sol Ring", "battlefield", "p3")
    act(s, "p1", type="set_life", player="p1", value=55)
    activate(s, source, "0:")
    assert all(c.zone == c.owner + ":exile" for c in [source, their, ring])
    assert ours.zone == "p1:battlefield"
    roundtrip(s)


def test_sorin_highest_life_native_tokens(cards):
    s = game(cards)
    source = cast(s, "Sorin, Grim Nemesis")
    act(s, "p1", type="counter", card_ids=[source.id], kind="loyalty", delta=3)
    for p, n in [("p1", 1), ("p2", 2), ("p3", 3)]:
        act(s, "p1", type="set_life", player=p, value=n)
    activate(s, source, "−9:")
    tokens = [c for c in s.state.cards.values() if c.token and c.zone == "p1:battlefield"]
    assert len(tokens) == 3
    from app.rules.plan import Plan

    assert all(
        Plan(s.state, "p1", cards, None).ch(c).pt == (1, 1)
        and "lifelink" in Plan(s.state, "p1", cards, None).ch(c).keywords
        for c in tokens
    )
    roundtrip(s)


def test_resolute_native_intervening_and_life_gain(cards):
    s = game(cards)
    act(s, "p1", type="set_life", player="p1", value=17)
    cast(s, "Resolute Archangel")
    assert s.state.players["p1"].life == 40
    roundtrip(s)


@pytest.mark.parametrize("life", [40, 54])
def test_ajani_false_threshold_still_legal_activation(cards, life):
    s = game(cards)
    source = cast(s, "Ajani, Strength of the Pride")
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    act(s, "p1", type="set_life", player="p1", value=life)
    activate(s, source, "0:")
    assert source.zone == "p1:battlefield" and victim.zone == "p2:battlefield"
    roundtrip(s)


def test_ajani_plus_then_actual_pridemate_token_trigger(cards):
    from tests.test_rules_designations import settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    source = cast(s, "Ajani, Strength of the Pride")
    put(s, "Grizzly Bears", "battlefield")
    activate(s, source, "−2:")
    token = next(c for c in s.state.cards.values() if c.token and c.name == "Ajani's Pridemate")
    assert chars(s, token).pt == (2, 2)
    # A real later turn resets the native planeswalker loyalty-use limit.
    for _ in range(3):
        act(s, s.state.turn.active_player, type="next_turn")
    to_phase(s, "main1")
    activate(s, source, "+1:")
    settle(s)
    assert s.state.players["p1"].life == 43
    assert token.counters.get("+1/+1") == 1
    roundtrip(s)


@pytest.mark.parametrize("life", [40, 47])
def test_resolute_intervening_if_does_not_trigger_at_or_above_start(cards, life):
    s = game(cards)
    act(s, "p1", type="set_life", player="p1", value=life)
    cast(s, "Resolute Archangel")
    assert s.state.players["p1"].life == life
    assert not s.state.rules.stack
    roundtrip(s)


@pytest.mark.parametrize(
    "name", ["Ajani, Strength of the Pride", "Sorin, Grim Nemesis", "Resolute Archangel"]
)
def test_actual_all_printed_coverage(cards, name):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == "FULL", result.manual_parts


@pytest.mark.parametrize("case", ["source_gone", "threshold_changed"])
def test_ajani_resolution_source_and_condition(cards, case):
    from tests.test_rules_designations import settle

    s = game(cards, ["Hero's Downfall", "Lightning Bolt"])
    source = cast(s, "Ajani, Strength of the Pride")
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    act(s, "p1", type="set_life", player="p1", value=55)
    act(s, "p1", type="set_prefs", hold_priority=True)
    activate(s, source, "0:", resolve=False)
    if case == "source_gone":
        cast(s, "Hero's Downfall", [source.id], pid="p2")
    else:
        cast(s, "Lightning Bolt", ["p1"], pid="p2")
    settle(s)
    assert victim.zone == ("p2:exile" if case == "source_gone" else "p2:battlefield")
    assert source.zone == ("p1:graveyard" if case == "source_gone" else "p1:battlefield")
    roundtrip(s)


@pytest.mark.parametrize("case", ["damage", "fizzle"])
def test_sorin_minus_x_damage_and_life_whole_target_legality(cards, case):
    from tests.test_rules_designations import settle

    s = game(cards, ["Murder"])
    source = cast(s, "Sorin, Grim Nemesis")
    target = put(s, "Grizzly Bears", "battlefield", "p2")
    act(s, "p1", type="set_prefs", hold_priority=True)
    # This helper intentionally supplies the actual announced loyalty X.
    from tests.test_rules_conditional_prevention import mana, wait_priority

    mana(s, C=10)
    wait_priority(s, "p1")
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=1,
        targets=[target.id],
        x_value=2,
        sources=[],
    )
    if case == "fizzle":
        cast(s, "Murder", [target.id], pid="p2")
    settle(s)
    assert target.zone == "p2:graveyard"
    assert s.state.players["p1"].life == (42 if case == "damage" else 40)
    assert source.counters.get("loyalty") == 4
    roundtrip(s)


def test_sorin_plus_reveals_real_card_and_native_mana_value(cards):
    from tests.test_rules_conditional_prevention import choose
    from tests.test_rules_designations import settle

    s = game(cards)
    source = cast(s, "Sorin, Grim Nemesis")
    top = put(s, "Healing Salve", "hand")
    act(s, "p1", type="move", card_ids=[top.id], to={"player": "p1", "zone": "library"}, index=0)
    activate(s, source, "+1:")
    while s.state.rules.decision:
        d = s.state.rules.decision
        choose(s, [o.id for o in d.options[: d.min_choices]])
    settle(s)
    assert top.zone == "p1:hand"
    assert s.state.players["p2"].life == 39 and s.state.players["p3"].life == 39
    roundtrip(s)


@pytest.mark.parametrize("case", ["archive", "condition_changed", "source_gone"])
def test_resolute_resolution_gain_replacement_condition_and_source(cards, case):
    from tests.test_rules_conditional_prevention import choose
    from tests.test_rules_designations import settle

    s = game(cards, ["Alhammarret's Archive", "Murder", "Healing Salve"])
    if case == "archive":
        put(s, "Alhammarret's Archive", "battlefield")
    act(s, "p1", type="set_life", player="p1", value=39)
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    source = cast(s, "Resolute Archangel", resolve=False)
    for _ in range(8):
        if s.state.cards[source.id].zone != "stack":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.stack
    if case == "condition_changed":
        cast(s, "Healing Salve", ["p1"], modes=[0])
    elif case == "source_gone":
        cast(s, "Murder", [source.id], pid="p2")
    while s.state.rules.decision:
        d = s.state.rules.decision
        choose(s, [o.id for o in d.options[: d.min_choices]])
    settle(s)
    assert s.state.players["p1"].life == ({"archive": 41, "condition_changed": 42, "source_gone": 40}[case])
    roundtrip(s)


@pytest.mark.parametrize("stage", ["ajani", "sorin", "resolute"])
def test_native_pending_cold_without_any_adapter(cards, tmp_path, stage):
    import subprocess
    import sys

    s = game(
        cards, ["Alhammarret's Archive", "Angel of Vitality", "Jinnie Fay, Jetmir's Second", "Captain Sisay"]
    )
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    if stage == "ajani":
        source = cast(s, "Ajani, Strength of the Pride")
        commander = put(s, "Captain Sisay", "battlefield", "p2")
        act(s, "p2", type="set_commander", card_id=commander.id)
        act(s, "p1", type="set_life", player="p1", value=55)
        activate(s, source, "0:")
        assert s.state.rules.decision
    elif stage == "sorin":
        put(s, "Jinnie Fay, Jetmir's Second", "battlefield")
        source = cast(s, "Sorin, Grim Nemesis")
        act(s, "p1", type="counter", card_ids=[source.id], kind="loyalty", delta=3)
        for p, n in [("p1", 1), ("p2", 2), ("p3", 3)]:
            act(s, "p1", type="set_life", player=p, value=n)
        activate(s, source, "−9:")
        assert s.state.rules.decision
    else:
        put(s, "Alhammarret's Archive", "battlefield")
        put(s, "Angel of Vitality", "battlefield")
        act(s, "p1", type="set_life", player="p1", value=39)
        source = cast(s, "Resolute Archangel")
        assert s.state.rules.decision and s.state.players["p1"].life == 39
    saved = tmp_path / "pending.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_conditional_prevention import choose
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
stage,source,victim=sys.argv[3:]
for _ in range(10):
 d=s.state.rules.decision
 if d is None:break
 if stage=='resolute':
  pick=next((o.id for o in d.options if 'archive' in o.label.lower()),None)
 elif stage=='sorin':
  pick=next((o.id for o in d.options if 'cat' in o.label.lower()),None)
 else:
  pick=next((o.id for o in d.options if o.id in ('yes','command')),None)
 choose(s,[pick] if pick is not None else [o.id for o in d.options[:d.min_choices]])
settle(s)
assert s.state.rules.decision is None
if stage=='resolute':assert s.state.players['p1'].life==42
elif stage=='sorin':
 tokens=[c for c in s.state.cards.values() if c.token and c.zone=='p1:battlefield']
 assert len(tokens)==3 and all('Cat' in Plan(s.state,'p1',repo,None).ch(c).subtypes for c in tokens)
 assert s.state.cards[source].zone=='p1:graveyard'
else:
 assert s.state.cards[source].zone=='p1:exile'
 assert s.state.cards[victim].zone=='p2:exile'
 commander=next(c for c in s.state.cards.values() if c.name=='Captain Sisay' and c.owner=='p2')
 assert commander.zone=='p2:command'
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), stage, source.id, victim.id],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ajani_native_flicker_does_not_exile_new_incarnation(cards):
    from app.rules.plan import Plan
    from tests.test_rules_designations import settle

    s = game(cards, ["Flicker", "Vedalken Orrery"])
    source = cast(s, "Ajani, Strength of the Pride")
    put(s, "Vedalken Orrery", "battlefield")
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    original = Plan(s.state, "p1", cards, None).oid(source)
    act(s, "p1", type="set_life", player="p1", value=55)
    act(s, "p1", type="set_prefs", hold_priority=True)
    activate(s, source, "0:", resolve=False)
    cast(s, "Flicker", [source.id])
    settle(s)
    current = s.state.cards[source.id]
    assert Plan(s.state, "p1", cards, None).oid(current) != original
    assert current.zone == "p1:battlefield" and current.counters.get("loyalty") == 5
    assert victim.zone == "p2:exile"
    roundtrip(s)


def test_ajani_native_creature_planeswalker_counted_twice(cards):
    from tests.test_rules_wave6c_tokens_pumps import chars

    s = game(cards, ["Gideon Blackblade"])
    source = cast(s, "Ajani, Strength of the Pride")
    gideon = cast(s, "Gideon Blackblade")
    put(s, "Grizzly Bears", "battlefield")
    assert {"Creature", "Planeswalker"} <= chars(s, gideon).types
    activate(s, source, "+1:")
    assert s.state.players["p1"].life == 44
    roundtrip(s)


def test_sorin_highest_total_reads_after_actual_response_and_source_death(cards):
    from tests.test_rules_designations import settle

    s = game(cards)
    source = cast(s, "Sorin, Grim Nemesis")
    act(s, "p1", type="counter", card_ids=[source.id], kind="loyalty", delta=3)
    for p, n in [("p1", 1), ("p2", 2), ("p3", 3)]:
        act(s, "p1", type="set_life", player=p, value=n)
    act(s, "p1", type="set_prefs", hold_priority=True)
    activate(s, source, "−9:", resolve=False)
    assert source.zone == "p1:graveyard"
    cast(s, "Healing Salve", ["p3"], modes=[0], pid="p2")
    settle(s)
    assert s.state.players["p3"].life == 6
    assert len([c for c in s.state.cards.values() if c.token and c.zone == "p1:battlefield"]) == 6
    roundtrip(s)


def test_sorin_all_negative_life_totals_create_no_tokens(cards):
    s = game(cards, ["Platinum Angel"])
    source = cast(s, "Sorin, Grim Nemesis")
    act(s, "p1", type="counter", card_ids=[source.id], kind="loyalty", delta=3)
    for p, n in [("p1", -1), ("p2", -2), ("p3", -3)]:
        put(s, "Platinum Angel", "battlefield", p)
        act(s, "p1", type="set_life", player=p, value=n)
    activate(s, source, "−9:")
    assert not any(c.token and c.zone == "p1:battlefield" for c in s.state.cards.values())
    assert not s.state.rules.lost
    roundtrip(s)
