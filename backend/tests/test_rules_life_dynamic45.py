import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import cast
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_effects import mana
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave4f_ability_words import tok
from tests.test_rules_wave30m_durations import to_phase

ROWS = json.loads(
    (Path(__file__).parent / "fixtures" / "life_dynamic45_cards.json").read_text()
)
NAMES = list(
    dict.fromkeys(
        [r["name"] for r in ROWS] + ["Forest", "Grizzly Bears", "Llanowar Elves"]
    )
)


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, row in enumerate(ROWS):
        base[row["name"]] = card(
            row["name"], number=str(i), **{k: v for k, v in row.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    return table(cards, NAMES, NAMES, NAMES)


def index(s, c):
    return next(
        a.index
        for a in Plan(s.state, "p1", s.cards, None).ch(c).abilities
        if "Formidable" in a.text
    )


def activate(s, c):
    mana(s, G=2, C=9)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=index(s, c))


@pytest.mark.parametrize(
    "power,negative,allowed",
    [(5, 0, False), (6, 0, True), (8, -3, False), (9, -3, True)],
)
def test_shaman_actual_formidable_threshold_and_signed_power(
    cards, power, negative, allowed
):
    from app.rules.casting import activatable

    s = game(cards)
    source = put(s, "Shaman of Forgotten Ways", "battlefield")
    tok(s, "Big", pt=f"{power}/10")
    if negative:
        tok(s, "Negative", pt=f"{negative}/3")
    to_phase(s, "main1", turn=4)
    mana(s, G=2, C=9)
    i = index(s, source)
    assert (
        {"card_id": source.id, "ability": i} in activatable(s.state, "p1", cards)
    ) == allowed
    if allowed:
        activate(s, source)
        settle(s)
        assert s.state.players["p1"].life == 2 + bool(negative)
    roundtrip(s)


def test_shaman_activation_survives_sourcegone_and_counts_current_creatures(cards):
    s = game(cards)
    source = put(s, "Shaman of Forgotten Ways", "battlefield")
    tok(s, "Big", pt="6/6")
    put(s, "Grizzly Bears", "battlefield", "p2")
    put(s, "Llanowar Elves", "battlefield", "p3")
    to_phase(s, "main1", turn=4)
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    activate(s, source)
    assert source.tapped
    act(
        s,
        "p1",
        type="move",
        card_ids=[source.id],
        to={"zone": "graveyard", "player": "p1"},
    )
    settle(s)
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [1, 1, 1]
    roundtrip(s)


@pytest.mark.parametrize(
    "name",
    [
        "Shaman of Forgotten Ways",
        "Axis of Mortality",
        "Touch of the Eternal",
        "Psychic Transfer",
        "Oketra's Last Mercy",
    ],
)
def test_exact_whole_canonical_supported(cards, name):
    from app.rules import coverage

    r = coverage.of_card_data(cards.resolve(name))
    assert r.level == "FULL", r.manual_parts


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (10, 15, (15, 10)),
        (10, 16, (10, 16)),
        (-4, 1, (1, -4)),
        (-5, 1, (-5, 1)),
        (12, 12, (12, 12)),
    ],
)
def test_psychic_transfer_native_signed_difference(cards, a, b, expected):
    s = game(cards)
    put(s, "Platinum Angel", "battlefield")
    put(s, "Platinum Angel", "battlefield", "p2")
    for p, n in [("p1", a), ("p2", b)]:
        act(s, "p1", type="set_life", player=p, value=n)
    cast(s, "Psychic Transfer", targets=["p2"])
    assert tuple(s.state.players[p].life for p in ("p1", "p2")) == expected
    roundtrip(s)


def test_oketra_sets_actual_starting_life_and_keeps_native_untap_selector(cards):
    s = game(cards)
    act(s, "p1", type="set_life", player="p1", value=7)
    cast(s, "Oketra's Last Mercy")
    assert s.state.players["p1"].life == 40
    assert s.state.rules.stay_tapped == [
        {"sel": 'sel:{"types":["Land"]}', "player": "p1"}
    ]
    roundtrip(s)


@pytest.mark.parametrize("accept", [False, True])
def test_axis_native_upkeep_targets_then_optional_exchange(cards, accept):
    s = game(cards)
    cast(s, "Axis of Mortality")
    for p, n in [("p1", 10), ("p2", 17)]:
        act(s, "p1", type="set_life", player=p, value=n)
    to_phase(s, "upkeep", turn=4)
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards", (d, s.state.turn)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["p1", "p2"])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and [o.id for o in d.options] == ["yes", "no"], d
    act(
        s,
        d.player,
        type="choose",
        decision_id=d.id,
        option_ids=["yes" if accept else "no"],
    )
    settle(s)
    assert [s.state.players[p].life for p in ("p1", "p2")] == (
        [17, 10] if accept else [10, 17]
    )
    roundtrip(s)


def test_touch_native_upkeep_current_permanents(cards):
    s = game(cards)
    cast(s, "Touch of the Eternal")
    put(s, "Grizzly Bears", "battlefield")
    put(s, "Forest", "battlefield")
    put(s, "Grizzly Bears", "battlefield", "p2")
    to_phase(s, "upkeep", turn=4)
    settle(s)
    assert s.state.players["p1"].life == 3
    roundtrip(s)


@pytest.mark.parametrize("mix", ["{R}{G}", "{G}{G}"])
def test_shaman_mana_native_immediate_mixed_restricted_units(cards, mix):
    from app.game.errors import ActionError

    s = game(cards)
    source = put(s, "Shaman of Forgotten Ways", "battlefield")
    to_phase(s, "main1", turn=4)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0, sources=[])
    d = s.state.rules.decision
    assert d is not None, (s.state.players["p1"], s.state.rules.stack)
    assert len(d.options) == 15 and all("C" not in o.label for o in d.options)
    pick = next(o.id for o in d.options if o.label == mix)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    assert not s.state.rules.stack and source.tapped
    units = s.state.players["p1"].mana_units
    assert len(units) == 2 and all(u.only for u in units)
    assert all(u.src == Plan(s.state, "p1", cards, None).oid(source) for u in units)
    ring = put(s, "Sol Ring", "hand")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=ring.id, sources=[])
    assert s.state.model_dump_json() == before
    bear = put(s, "Grizzly Bears", "hand")
    act(s, "p1", type="cast_spell", card_id=bear.id, sources=[])
    settle(s)
    assert bear.zone == "p1:battlefield" and not s.state.players["p1"].mana_units
    roundtrip(s)


@pytest.mark.parametrize("name", ["Thelonite Hermit", "Hidden Dragonslayer"])
def test_shaman_restricted_mana_can_cast_morph_and_megamorph(cards, name):
    s = game(cards)
    source = put(s, "Shaman of Forgotten Ways", "battlefield")
    to_phase(s, "main1", turn=4)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0, sources=[])
    d = s.state.rules.decision
    pick = next(o.id for o in d.options if o.label == "{R}{G}")
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    mana(s, C=1)
    spell = put(s, name, "hand")
    act(s, "p1", type="cast_spell", card_id=spell.id, face_down=True, sources=[])
    settle(s)
    assert (
        spell.zone == "p1:battlefield"
        and spell.face_down
        and not s.state.players["p1"].mana_units
    )
    assert Plan(s.state, "p1", cards, None).ch(spell).pt == (2, 2)
    roundtrip(s)


def test_shaman_summoning_sickness_and_eleven_mana_cost_reject_atomically(cards):
    from app.game.errors import ActionError

    s = game(cards)
    source = put(s, "Shaman of Forgotten Ways", "battlefield")
    tok(s, "Big", pt="6/6")
    mana(s, G=2, C=9)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError, match="summoning sickness"):
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=source.id,
            ability=index(s, source),
        )
    assert s.state.model_dump_json() == before
    to_phase(s, "main1", turn=4)
    mana(s, G=2, C=8)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=source.id,
            ability=index(s, source),
            sources=[],
        )
    assert s.state.model_dump_json() == before and not source.tapped
    roundtrip(s)


def test_shaman_mixed_packet_freezes_counts_and_commits_all_after_616(cards):
    s = game(cards)
    source = put(s, "Shaman of Forgotten Ways", "battlefield")
    tok(s, "Big", pt="6/6")
    put(s, "Grizzly Bears", "battlefield", "p2")
    put(s, "Llanowar Elves", "battlefield", "p3")
    for name in ["Alhammarret's Archive", "Cleric Class"]:
        put(s, name, "battlefield")
    to_phase(s, "main1", turn=4)
    act(s, "p1", type="set_life", player="p1", value=1)
    activate(s, source)
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume["site"] == "life_changes44"
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [1, 40, 40]
    assert d.resume["request"]["changes"] == [["p1", 1], ["p2", -39], ["p3", -39]]
    pick = next(o.id for o in d.options if o.label.startswith("Cleric Class first"))
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    settle(s)
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [5, 1, 1]
    roundtrip(s)


@pytest.mark.parametrize("name", ["Oketra's Last Mercy", "Touch of the Eternal"])
def test_dynamic_set_life_prohibition_keeps_total_unchanged(cards, name):
    s = game(cards)
    put(s, "Platinum Emperion", "battlefield")
    act(s, "p1", type="set_life", player="p1", value=7)
    cast(s, name)
    if name == "Touch of the Eternal":
        to_phase(s, "upkeep", turn=4)
        settle(s)
    assert s.state.players["p1"].life == 7
    if name == "Oketra's Last Mercy":
        assert s.state.rules.stay_tapped
    roundtrip(s)


def test_shaman_creature_only_mana_cannot_pay_activated_ability_cost(cards):
    from app.game.errors import ActionError

    s = game(cards)
    source = put(s, "Shaman of Forgotten Ways", "battlefield")
    evra = put(s, "Evra, Halcyon Witness", "battlefield")
    to_phase(s, "main1", turn=4)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0, sources=[])
    d = s.state.rules.decision
    pick = next(o.id for o in d.options if o.label == "{G}{G}")
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    mana(s, C=2)
    i = next(
        a.index
        for a in Plan(s.state, "p1", cards, None).ch(evra).abilities
        if "Exchange" in a.text
    )
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=evra.id, ability=i, sources=[])
    assert (
        s.state.model_dump_json() == before
        and len(s.state.players["p1"].mana_units) == 2
    )
    roundtrip(s)


def test_oketra_live_mass_untap_includes_lands_entering_later_and_expires_together(
    cards,
):
    s = game(cards)
    forest = put(s, "Forest", "battlefield")
    spell = cast(s, "Oketra's Last Mercy")
    # Recast our own spell through native Regrowth; both effects end at the same actual untap.
    cast(s, "Regrowth", targets=[spell.id])
    assert spell.zone == "p1:hand"
    cast(s, "Oketra's Last Mercy")
    wastes = put(s, "Wastes", "battlefield")
    act(s, "p1", type="tap", card_ids=[forest.id, wastes.id], tapped=True)
    to_phase(s, "main1", turn=4)
    assert forest.tapped and wastes.tapped and not s.state.rules.stay_tapped
    to_phase(s, "main1", turn=7)
    assert not forest.tapped and not wastes.tapped
    roundtrip(s)


@pytest.mark.parametrize("case", ["illegal", "prohibited"])
def test_axis_native_illegal_or_prohibited_exchange_changes_neither_total(cards, case):
    s = game(cards)
    cast(s, "Axis of Mortality")
    if case == "prohibited":
        put(s, "Platinum Emperion", "battlefield")
    for p, n in [("p1", 10), ("p2", 17)]:
        act(s, "p1", type="set_life", player=p, value=n)
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    to_phase(s, "upkeep", turn=4)
    d = s.state.rules.decision
    assert d.kind == "choose_cards"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["p1", "p2"])
    if case == "illegal":
        cast(s, "Blossoming Calm", pid="p2")
    else:
        settle(s)
        d = s.state.rules.decision
        assert d and [o.id for o in d.options] == ["yes", "no"]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
        settle(s)
    assert [s.state.players[p].life for p in ("p1", "p2")] == (
        [10, 19] if case == "illegal" else [10, 17]
    )
    roundtrip(s)


def test_touch_sourcegone_counts_surviving_permanents_and_replacement_pause(cards):
    s = game(cards)
    source = cast(s, "Touch of the Eternal")
    put(s, "Grizzly Bears", "battlefield")
    put(s, "Forest", "battlefield")
    for name in ["Alhammarret's Archive", "Cleric Class"]:
        put(s, name, "battlefield")
    act(s, "p1", type="set_life", player="p1", value=1)
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    to_phase(s, "upkeep", turn=4)
    assert any(
        t.kind == "trigger" and t.source_card == source.id
        for t in s.state.rules.stack.values()
    )
    act(
        s,
        "p1",
        type="move",
        card_ids=[source.id],
        to={"zone": "graveyard", "player": "p1"},
    )
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume["request"]["changes"] == [["p1", 3]]
    assert s.state.players["p1"].life == 1
    pick = next(o.id for o in d.options if o.label.startswith("Cleric Class first"))
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    settle(s)
    assert s.state.players["p1"].life == 9
    roundtrip(s)


@pytest.mark.parametrize(
    "stage", ["shaman", "shaman_616", "axis", "touch", "psychic", "oketra"]
)
def test_dynamic_life_actual_fresh_process(cards, tmp_path, stage):
    import os
    import subprocess
    import sys

    s = game(cards)
    source = None
    if stage.startswith("shaman"):
        source = put(s, "Shaman of Forgotten Ways", "battlefield")
        tok(s, "Big", pt="6/6")
        put(s, "Grizzly Bears", "battlefield", "p2")
        put(s, "Llanowar Elves", "battlefield", "p3")
        if stage == "shaman_616":
            for name in ["Alhammarret's Archive", "Cleric Class"]:
                put(s, name, "battlefield")
        to_phase(s, "main1", turn=4)
        act(
            s,
            "p1",
            type="set_prefs",
            hold_priority=True,
            auto_resolve_own_triggers="off",
        )
        if stage == "shaman_616":
            act(s, "p1", type="set_life", player="p1", value=1)
        activate(s, source)
        if stage == "shaman_616":
            settle(s)
            assert s.state.rules.decision and s.state.players["p1"].life == 1
        else:
            act(
                s,
                "p1",
                type="move",
                card_ids=[source.id],
                to={"zone": "graveyard", "player": "p1"},
            )
    elif stage == "axis":
        cast(s, "Axis of Mortality")
        for p, n in [("p1", 10), ("p2", 17)]:
            act(s, "p1", type="set_life", player=p, value=n)
        to_phase(s, "upkeep", turn=4)
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["p1", "p2"])
        settle(s)
        assert s.state.rules.decision
    elif stage == "touch":
        cast(s, "Touch of the Eternal")
        put(s, "Grizzly Bears", "battlefield")
        act(
            s,
            "p1",
            type="set_prefs",
            hold_priority=True,
            auto_resolve_own_triggers="off",
        )
        to_phase(s, "upkeep", turn=4)
    elif stage == "psychic":
        for p, n in [("p1", 10), ("p2", 15)]:
            act(s, "p1", type="set_life", player=p, value=n)
        cast(s, "Psychic Transfer", targets=["p2"], resolve=False)
    else:
        act(s, "p1", type="set_life", player="p1", value=7)
        cast(s, "Oketra's Last Mercy", resolve=False)
    saved = tmp_path / "state.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
stage=sys.argv[3]
if stage in ('axis','shaman_616'):
 d=s.state.rules.decision
 assert d is not None
 pick=next(o.id for o in d.options if o.label.startswith('Cleric Class first')) if stage=='shaman_616' else 'yes'
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[pick]})
settle(s)
assert s.state.rules.decision is None
life=[s.state.players[p].life for p in ('p1','p2','p3')]
if stage=='shaman':assert life==[1,1,1],life
elif stage=='shaman_616':assert life==[5,1,1],life
elif stage=='axis':assert life==[17,10,40],life
elif stage=='touch':assert life==[2,40,40],life
elif stage=='psychic':assert life==[15,10,40],life
else:assert life==[40,40,40] and s.state.rules.stay_tapped,life
roundtrip(s)
"""
    backend = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(backend)}
    child = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), stage],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
    )
    assert child.returncode == 0, child.stdout + child.stderr


def test_touch_trigger_keeps_receiver_after_source_control_change_and_ignores_phased(
    cards,
):
    s = game(cards)
    source = cast(s, "Touch of the Eternal")
    bear = put(s, "Grizzly Bears", "battlefield")
    put(s, "Forest", "battlefield")
    put(s, "Sol Ring", "battlefield")
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    to_phase(s, "upkeep", turn=4)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    act(s, "p1", type="phase_shift", card_ids=[bear.id], out=True)
    settle(s)
    assert [s.state.players[p].life for p in ("p1", "p2")] == [2, 40]
    roundtrip(s)


def test_oketra_skipped_untap_does_not_expire_waiting_mass_effect(cards):
    s = game(cards)
    forest = put(s, "Forest", "battlefield")
    cast(s, "Oketra's Last Mercy")
    act(s, "p1", type="tap", card_ids=[forest.id], tapped=True)
    to_phase(s, "end", turn=3)
    stasis = put(s, "Stasis", "battlefield", "p3")
    to_phase(s, "main1", turn=4)
    assert forest.tapped and s.state.rules.stay_tapped
    act(
        s,
        "p1",
        type="move",
        card_ids=[stasis.id],
        to={"zone": "graveyard", "player": "p3"},
    )
    to_phase(s, "main1", turn=7)
    assert forest.tapped and not s.state.rules.stay_tapped
    to_phase(s, "main1", turn=10)
    assert not forest.tapped
    roundtrip(s)


@pytest.mark.parametrize("initial", [7, 60, 27])
def test_oketra_custom_start_and_signed_change(cards, initial):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from app.game.state import GameSettings
    from tests.game_helpers import deck, enable
    from tests.test_rules_declaration_requirements33 import start

    names = ["Oketra's Last Mercy", "Forest"]
    setups = [
        PlayerSetup(
            n,
            cards=deck(
                cards, "Krenko, Mob Boss", [(1, k) for k in names] + [(20, "Forest")]
            ),
        )
        for n in ["A", "B", "C"]
    ]
    s = GameSession(
        enable(
            new_game(setups, settings=GameSettings(starting_life=27), shuffle=False)
        ),
        cards=cards,
    )
    for p in s.state.players:
        act(s, p, type="set_prefs", response="on")
    act(s, "p1", type="pass_priority")
    start(s)
    act(s, "p1", type="set_life", player="p1", value=initial)
    before = len(s.state.players["p1"].life_history)
    cast(s, "Oketra's Last Mercy")
    assert s.state.players["p1"].life == 27
    assert len(s.state.players["p1"].life_history) - before == bool(initial != 27)
    assert s.state.rules.stay_tapped
    roundtrip(s)


def test_shaman_all_creatures_leave_before_resolution_native_simultaneous_draw(cards):
    s = game(cards)
    source = put(s, "Shaman of Forgotten Ways", "battlefield")
    big = tok(s, "Big", pt="6/6")
    to_phase(s, "main1", turn=4)
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    activate(s, source)
    act(
        s,
        "p1",
        type="move",
        card_ids=[source.id, big.id],
        to={"zone": "graveyard", "player": "p1"},
    )
    settle(s)
    assert all(p.life == 0 for p in s.state.players.values())
    assert len(s.state.rules.lost) == 3 and s.state.rules.winner is None
    roundtrip(s)


@pytest.mark.parametrize("case", ["response", "self", "prohibited", "616"])
def test_psychic_native_current_legality_and_life_replacements(cards, case):
    s = game(cards)
    if case == "prohibited":
        put(s, "Platinum Emperion", "battlefield")
    if case == "616":
        for name in ["Alhammarret's Archive", "Cleric Class"]:
            put(s, name, "battlefield")
    for p, n in [("p1", 10), ("p2", 15)]:
        act(s, "p1", type="set_life", player=p, value=n)
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    cast(
        s, "Psychic Transfer", targets=["p1" if case == "self" else "p2"], resolve=False
    )
    if case == "response":
        act(s, "p1", type="set_life", player="p2", value=16)
    settle(s)
    if case == "616":
        d = s.state.rules.decision
        assert d and d.resume["request"]["changes"] == [["p1", 5], ["p2", -5]]
        assert [s.state.players[p].life for p in ("p1", "p2")] == [10, 15]
        pick = next(
            o.id for o in d.options if o.label.startswith("Alhammarret's Archive first")
        )
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        settle(s)
    assert [s.state.players[p].life for p in ("p1", "p2")] == (
        [21, 10] if case == "616" else [10, 16] if case == "response" else [10, 15]
    )
    roundtrip(s)


def test_oketra_does_not_apply_next_untap_instruction_until_life_choice_commits(cards):
    s = game(cards)
    for name in ["Alhammarret's Archive", "Cleric Class"]:
        put(s, name, "battlefield")
    act(s, "p1", type="set_life", player="p1", value=7)
    cast(s, "Oketra's Last Mercy")
    d = s.state.rules.decision
    assert d and d.resume["request"]["changes"] == [["p1", 33]]
    assert s.state.players["p1"].life == 7 and not s.state.rules.stay_tapped
    pick = next(o.id for o in d.options if o.label.startswith("Cleric Class first"))
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    settle(s)
    assert s.state.players["p1"].life == 75 and s.state.rules.stay_tapped
    roundtrip(s)
