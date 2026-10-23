"""Native paid top-library casting keeps its selected object and exact authority."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library

NAMES = [
    "The Belligerent",
    "Falco Spara, Pactweaver",
    "Into the Pit",
    "Isu the Abominable",
    "The Fourth Doctor",
]
SUPPORT = [
    "Millikin",
    "Progenitus",
    "Boreal Druid",
    "Snow-Covered Forest",
    "Seat of the Synod",
    "Future Sight",
    "Light 'Em Up",
    "Disperse",
    "Sol Ring",
    "Lightning Bolt",
    "Forest",
    "Grizzly Bears",
    "Llanowar Elves",
    "Centaur Courser",
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for filename in [
        "exile_outcomes42_cards.json",
        "exile_cast_outcomes45_cards.json",
        "fight_exile_receipts65_cards.json",
        "top_library_authorities69_cards.json",
    ]:
        for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / filename).read_text())):
            base[c["name"]] = card(
                c["name"],
                set_code="tl69",
                number=str(i),
                **{k: v for k, v in c.items() if k not in {"name", "set_code"}},
            )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *NAMES, *SUPPORT)


def test_pit_native_cast_from_top_can_sacrifice_the_permission_source(cards):
    s = setup(cards)
    source = cast(s, "Into the Pit")
    top = stack_library(s, ["Lightning Bolt", "Grizzly Bears"])
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=top[0],
        targets=["p2"],
        cost_choices=[{"component": 0, "cards": [source.id]}],
    )
    settle(s)
    assert s.state.cards[source.id].zone == "p1:graveyard"
    assert s.state.cards[top[0]].zone == "p1:graveyard"
    assert s.state.players["p2"].life == 37
    assert s.state.zones["p1:library"][0] == top[1]
    roundtrip(s)


def test_pit_progenitus_cost_shuffle_does_not_replace_the_announced_top_spell(cards):
    s = setup(cards)
    source = cast(s, "Into the Pit")
    sacrifice = put(s, "Progenitus", "battlefield")
    top = stack_library(s, ["Lightning Bolt", "Grizzly Bears", "Forest"])
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=top[0],
        targets=["p2"],
        cost_choices=[{"component": 0, "cards": [sacrifice.id]}],
    )
    settle(s)
    d = s.state.rules.decision
    if d:
        answer(s, [o.id for o in d.options][: d.min_choices])
        settle(s)
    assert s.state.cards[source.id].zone == "p1:battlefield"
    assert s.state.cards[sacrifice.id].zone == "p1:library"
    assert s.state.cards[top[0]].zone == "p1:graveyard"
    assert s.state.players["p2"].life == 37
    roundtrip(s)


def test_pit_cannot_activate_instant_only_millikin_during_spell_payment(cards):
    s = setup(cards)
    source = cast(s, "Into the Pit")
    millikin = put(s, "Millikin", "battlefield")
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "main1", turn=4)
    settle(s)
    top = stack_library(s, ["Sol Ring", "Grizzly Bears", "Forest"])
    act(s, "p1", type="clear_mana")
    from app.game.errors import ActionError

    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match="Pick untapped mana sources"):
        act(
            s,
            "p1",
            type="cast_spell",
            card_id=top[0],
            sources=[millikin.id],
            cost_choices=[{"component": 0, "cards": [source.id]}],
        )
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


@pytest.mark.parametrize("name", [n for n in NAMES if not n.startswith("Falco")])
def test_four_static_cards_are_fully_parsed(cards, name):
    from app.rules import coverage

    got = coverage.of_card_data(cards.resolve(name))
    assert got.level == "FULL", got


def test_pit_rejects_land_cost_and_opponent_permanent_atomically(cards):
    from app.game.errors import ActionError

    s = setup(cards)
    cast(s, "Into the Pit")
    land = put(s, "Forest", "battlefield")
    enemy = put(s, "Grizzly Bears", "battlefield", pid="p2")
    top = stack_library(s, ["Lightning Bolt", "Forest"])
    for invalid in [land.id, enemy.id]:
        before = s.state.model_dump(mode="json")
        with pytest.raises(ActionError):
            act(
                s,
                "p1",
                type="cast_spell",
                card_id=top[0],
                targets=["p2"],
                cost_choices=[{"component": 0, "cards": [invalid]}],
            )
        assert s.state.model_dump(mode="json") == before
    roundtrip(s)


@pytest.mark.parametrize("color", ["G", "W", "U", "decline"])
def test_isu_snow_land_from_top_pays_selected_one_of_three_colors_or_declines(cards, color):
    from app.game.visibility import can_see
    from app.rules.plan import Plan

    s = setup(cards)
    isu = cast(s, "Isu the Abominable")
    top = stack_library(s, ["Snow-Covered Forest", "Lightning Bolt", "Forest"])
    assert can_see(s.state, s.state.cards[top[0]], "p1")
    assert not can_see(s.state, s.state.cards[top[0]], "p2")
    act(s, "p1", type="clear_mana")
    mana(s, **{("G" if color == "decline" else color): 1})
    act(s, "p1", type="play_land", card_id=top[0])
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume["step"] == "pay_or_sacrifice", d
    if color == "decline":
        option = next(o.id for o in d.options if o.id == "decline")
    else:
        option = next(o.id for o in d.options if "{" + color + "}" in o.label)
        assert all(
            o.id in {"pay:0", "decline", "pay:" + str(["G", "W", "U"].index(color))} for o in d.options
        )
    answer(s, [option])
    settle(s)
    assert s.state.cards[isu.id].counters.get("+1/+1", 0) == int(color != "decline")
    assert s.state.players["p1"].mana == ({"G": 1} if color == "decline" else {})
    assert not Plan(s.state, "p1", cards, None).rules.decision
    from app.game.errors import ActionError

    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=top[1], targets=["p2"])
    assert before == s.state.model_dump(mode="json")
    roundtrip(s)


@pytest.mark.parametrize("kind", ["land", "spell"])
def test_doctor_selected_historic_cast_or_land_creates_food_and_uses_shared_once(cards, kind):
    from app.game.errors import ActionError

    s = setup(cards)
    cast(s, "The Fourth Doctor")
    top = stack_library(
        s,
        [
            "Seat of the Synod" if kind == "land" else "Sol Ring",
            "Sol Ring" if kind == "land" else "Seat of the Synod",
        ],
    )
    act(s, "p1", type="play_land" if kind == "land" else "cast_spell", card_id=top[0])
    settle(s)
    assert s.state.cards[top[0]].zone == "p1:battlefield"
    foods = [c for c in s.state.cards.values() if c.name == "Food" and c.zone == "p1:battlefield"]
    assert len(foods) == 1
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell" if kind == "land" else "play_land", card_id=top[1])
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


def test_doctor_only_selected_authority_creates_food_and_hand_cast_does_not(cards):
    s = setup(cards)
    cast(s, "The Fourth Doctor")
    cast(s, "Future Sight")
    top = stack_library(s, ["Sol Ring", "Seat of the Synod"])
    act(s, "p1", type="cast_spell", card_id=top[0])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "slot", d
    answer(s, [next(o.id for o in d.options if "Future Sight" in o.label)])
    settle(s)
    assert not any(c.name == "Food" for c in s.state.cards.values())
    act(s, "p1", type="play_land", card_id=top[1])
    d = s.state.rules.decision
    assert d, d
    answer(s, [next(o.id for o in d.options if "The Fourth Doctor" in o.label)])
    settle(s)
    assert len([c for c in s.state.cards.values() if c.name == "Food"]) == 1
    # A historic spell cast from hand did not use this top-library authority.
    cast(s, "Millikin")
    assert len([c for c in s.state.cards.values() if c.name == "Food"]) == 1
    roundtrip(s)


def bell_attacks(s):
    from tests.test_rules_wave4h_activation_costs import ability
    from tests.test_rules_wave30m_durations import to_phase

    ship = cast(s, "The Belligerent")
    pilot = cast(s, "Grizzly Bears")
    elf = cast(s, "Llanowar Elves")
    to_phase(s, "begin_combat", turn=4)
    settle(s)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=ship.id,
        ability=ability(s, ship, "Crew"),
        crew=[pilot.id, elf.id],
    )
    settle(s)
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ship.id, "target": "p2"}])
    settle(s)
    return ship


def test_belligerent_actual_attack_grants_private_look_survives_departure_and_expires(cards):
    from app.game.errors import ActionError
    from app.game.visibility import can_see
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    ship = bell_attacks(s)
    assert any(c.name == "Treasure" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    top = stack_library(s, ["Lightning Bolt", "Forest", "Grizzly Bears"])
    assert can_see(s.state, s.state.cards[top[0]], "p1")
    assert not can_see(s.state, s.state.cards[top[0]], "p2")
    assert not can_see(s.state, s.state.cards[top[0]], "spectator")
    cast(s, "Disperse", targets=[ship.id])
    assert s.state.cards[ship.id].zone == "p1:hand"
    assert can_see(s.state, s.state.cards[top[0]], "p1")
    act(s, "p1", type="cast_spell", card_id=top[0], targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 37
    assert can_see(s.state, s.state.cards[top[1]], "p1")
    # Sorcery/land timing still applies despite top-library access.
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=top[1])
    assert s.state.model_dump(mode="json") == before
    to_phase(s, "main2", turn=4)
    settle(s)
    act(s, "p1", type="play_land", card_id=top[1])
    settle(s)
    assert s.state.cards[top[1]].zone == "p1:battlefield"
    to_phase(s, "upkeep", turn=5)
    settle(s)
    assert not any(p.look_top for p in s.state.rules.permissions)
    assert not can_see(s.state, s.state.cards[top[2]], "p1")
    roundtrip(s)


@pytest.mark.parametrize("name", [n for n in NAMES if not n.startswith("Falco")])
def test_genuine_cold_original_top_authority_and_pending_trigger(cards, tmp_path, name):
    import os
    import subprocess
    import sys

    s = setup(cards)
    if name == "The Belligerent":
        source = bell_attacks(s)
        cast(s, "Disperse", targets=[source.id])
        target = stack_library(s, ["Lightning Bolt", "Forest"])[0]
        mode = "bolt"
    elif name == "Falco Spara, Pactweaver":
        source = cast(s, name)
        target = stack_library(s, ["Lightning Bolt", "Forest"])[0]
        mode = "falco"
    elif name == "Into the Pit":
        source = cast(s, name)
        target = stack_library(s, ["Lightning Bolt", "Forest"])[0]
        mode = "pit"
    elif name == "Isu the Abominable":
        source = cast(s, name)
        target = stack_library(s, ["Snow-Covered Forest", "Forest"])[0]
        act(s, "p1", type="clear_mana")
        mana(s, U=1)
        act(s, "p1", type="play_land", card_id=target)
        settle(s)
        mode = "isu"
        assert s.state.rules.decision.resume["step"] == "pay_or_sacrifice"
    else:
        source = cast(s, name)
        target = stack_library(s, ["Sol Ring", "Forest"])[0]
        act(s, "p1", type="cast_spell", card_id=target)
        mode = "doctor"
        assert s.state.zones["stack"]
    saved = tmp_path / "saved.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.game.visibility import can_see
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_look import settle
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
source,target,mode=sys.argv[3:6]
if mode in ('bolt','falco','pit'):
 assert can_see(s.state,s.state.cards[target],'p1')
 assert not can_see(s.state,s.state.cards[target],'p2')
 kw={'cost_choices':[{'component':0,'cards':[source]}]} if mode=='pit' else {}
 act(s,'p1',type='cast_spell',card_id=target,targets=['p2'],**kw);settle(s)
 assert s.state.players['p2'].life==37
 if mode=='pit':assert s.state.cards[source].zone=='p1:graveyard'
 if mode=='falco':assert not s.state.cards[source].counters.get('shield')
elif mode=='isu':
 d=s.state.rules.decision
 answer(s,[next(o.id for o in d.options if '{U}' in o.label)]);settle(s)
 assert s.state.cards[source].counters.get('+1/+1')==1
 assert not s.state.players['p1'].mana
else:
 settle(s)
 assert s.state.cards[target].zone=='p1:battlefield'
 assert len([c for c in s.state.cards.values() if c.name=='Food' and c.zone=='p1:battlefield'])==1
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id, target, mode],
        capture_output=True,
        text=True,
        timeout=60,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", ["Into the Pit", "Isu the Abominable", "The Fourth Doctor"])
def test_static_private_top_authority_ends_with_original_source(cards, name):
    from app.game.errors import ActionError
    from app.game.visibility import can_see

    s = setup(cards)
    source = cast(s, name)
    top = stack_library(s, ["Boreal Druid" if name.startswith("Isu") else "Sol Ring", "Forest"])
    assert can_see(s.state, s.state.cards[top[0]], "p1")
    assert not can_see(s.state, s.state.cards[top[0]], "p2")
    cast(s, "Disperse", targets=[source.id])
    assert not can_see(s.state, s.state.cards[top[0]], "p1")
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=top[0])
    assert before == s.state.model_dump(mode="json")
    roundtrip(s)


def test_isu_snow_spell_from_top_triggers_only_for_another_snow_permanent(cards):
    from app.game.errors import ActionError

    s = setup(cards)
    source = cast(s, "Isu the Abominable")
    assert not s.state.rules.decision
    top = stack_library(s, ["Boreal Druid", "Forest"])
    act(s, "p1", type="clear_mana")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=top[0])
    settle(s)
    assert s.state.cards[top[0]].zone == "p1:battlefield"
    assert not s.state.rules.decision  # no resources to pay; the new Druid is summoning sick
    assert not s.state.cards[source.id].counters.get("+1/+1")
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=top[1])
    assert before == s.state.model_dump(mode="json")
    roundtrip(s)


def test_doctor_nonhistoric_top_cannot_be_cast_or_played_and_private_look_is_still_available(cards):
    from app.game.errors import ActionError
    from app.game.visibility import can_see

    s = setup(cards)
    cast(s, "The Fourth Doctor")
    top = stack_library(s, ["Lightning Bolt", "Forest"])
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=top[0], targets=["p2"])
    assert before == s.state.model_dump(mode="json")
    assert can_see(s.state, s.state.cards[top[0]], "p1")
    assert not can_see(s.state, s.state.cards[top[0]], "p2")
    roundtrip(s)


def test_belligerent_does_not_look_before_attack_and_old_look_marker_is_not_invented(cards):
    from app.game.state import GameState
    from app.game.visibility import can_see

    s = setup(cards)
    cast(s, "The Belligerent")
    top = stack_library(s, ["Lightning Bolt", "Forest"])
    assert not can_see(s.state, s.state.cards[top[0]], "p1")
    # Default false remains false in legacy permissions that carry no look authority.
    from app.game.rules_state import Permission

    s.state.rules.permissions.append(
        Permission(id="legacy-top69", player="p1", zone="library_top", cast=True, turn=s.state.turn.number)
    )
    old = s.state.model_dump(mode="json")
    for p in old["rules"]["permissions"]:
        p.pop("look_top", None)
    loaded = GameState.model_validate(old)
    assert not can_see(loaded, loaded.cards[top[0]], "p1")


def test_doctor_original_use_trigger_survives_source_bounce_and_recast_has_new_once_scope(cards):
    s = setup(cards)
    source = cast(s, "The Fourth Doctor")
    top = stack_library(s, ["Sol Ring", "Seat of the Synod"])
    act(s, "p1", type="cast_spell", card_id=top[0])
    assert any(e.kind == "trigger" and e.source_card == source.id for e in s.state.rules.stack.values())
    cast(s, "Disperse", targets=[source.id])
    assert s.state.cards[source.id].zone == "p1:hand"
    assert len([c for c in s.state.cards.values() if c.name == "Food"]) == 1
    cast(s, "The Fourth Doctor")
    act(s, "p1", type="play_land", card_id=top[1])
    settle(s)
    assert len([c for c in s.state.cards.values() if c.name == "Food"]) == 2
    roundtrip(s)


def test_pit_top_cast_still_pays_mana_and_failed_payment_does_not_sacrifice(cards):
    from app.game.errors import ActionError

    s = setup(cards)
    source = cast(s, "Into the Pit")
    top = stack_library(s, ["Lightning Bolt", "Forest"])
    act(s, "p1", type="clear_mana")
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="cast_spell",
            card_id=top[0],
            targets=["p2"],
            cost_choices=[{"component": 0, "cards": [source.id]}],
        )
    assert s.state.model_dump(mode="json") == before
    assert s.state.cards[source.id].zone == "p1:battlefield"
    roundtrip(s)
