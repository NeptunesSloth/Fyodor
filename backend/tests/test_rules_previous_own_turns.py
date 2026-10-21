"""Previous own turns are neither the last global turn nor the running current turn."""

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

NAMES = ["Giant Turtle", "Halls of Mist", "Goblin Rock Sled", "Tangle Kelp", "Weathered Sentinels"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/previous_own_turns_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="pot", number=str(i), **{k: v for k, v in c.items() if k != "name"}
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
            (Path(__file__).parent / "fixtures/previous_own_turns_cards.json").read_text()
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


@pytest.mark.parametrize("name", ["Giant Turtle", "Halls of Mist"])
def test_attack_skip_uses_previous_own_turn_and_empty_turn_clears_it(cards, name):
    s = setup(cards)
    attacker = put(s, "Giant Turtle" if name == "Giant Turtle" else "Grizzly Bears", "battlefield", pid="p2")
    if name == "Halls of Mist":
        put(s, name, "battlefield")
        ids = [c.id for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:3]
        act(s, "p1", type="move", card_ids=ids, to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "declare_attackers", turn=5)
    assert Plan(s.state, "p2", s.cards, None).ch(attacker).is_creature
    with pytest.raises(ActionError):
        attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "declare_attackers", turn=8)
    attack(s, (attacker, "p1"), pid="p2")
    assert s.state.cards[attacker.id].attacking
    roundtrip(s)


@pytest.mark.parametrize("name", ["Goblin Rock Sled", "Tangle Kelp"])
def test_untap_skip_references_previous_controller_turn_then_recovers(cards, name):
    s = setup(cards)
    attacker = put(s, "Goblin Rock Sled" if name == "Goblin Rock Sled" else "Grizzly Bears", "battlefield", pid="p2")
    put(s, "Mountain", "battlefield")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    if name == "Tangle Kelp":
        to_phase(s, "main1", turn=4)
        enchant(s, name, attacker)
    to_phase(s, "main1", turn=5)
    assert s.state.cards[attacker.id].tapped
    to_phase(s, "main1", turn=8)
    assert not s.state.cards[attacker.id].tapped
    roundtrip(s)


def test_sentinels_conditional_defender_is_player_specific(cards):
    s = setup(cards)
    sentinel = put(s, "Weathered Sentinels", "battlefield")
    attacker = put(s, "Grizzly Bears", "battlefield", pid="p2")
    walker = put(s, "Jace Beleren", "battlefield", pid="p2")
    act(s, "p2", type="counter", card_ids=[walker.id], kind="loyalty", delta=3)
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "declare_attackers", turn=4)
    for target in ["p3", walker.id]:
        with pytest.raises(ActionError):
            attack(s, (sentinel, target))
    attack(s, (sentinel, "p2"))
    assert s.state.cards[sentinel.id].attacking.id == "p2"
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(sentinel)
    assert "defender" in ch.keywords and "indestructible" in ch.keywords
    assert ch.pt == (5, 8)
    roundtrip(s)


@pytest.mark.parametrize("name", ["Giant Turtle", "Goblin Rock Sled"])
def test_consecutive_extra_turn_uses_just_completed_own_turn(cards, name):
    s = setup(cards)
    attacker = put(s, name, "battlefield", pid="p2")
    put(s, "Mountain", "battlefield")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "main2", turn=2)
    spell = put(s, "Time Warp", "hand", pid="p2")
    mana(s, pid="p2", U=2, C=3)
    act(s, "p2", type="cast_spell", card_id=spell.id, targets=["p2"])
    settle(s)
    to_phase(s, "declare_attackers", turn=3)
    assert s.state.turn.active_player == "p2"
    if name == "Goblin Rock Sled":
        assert s.state.cards[attacker.id].tapped
    with pytest.raises(ActionError):
        attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "declare_attackers", turn=6)
    assert s.state.turn.active_player == "p2"
    attack(s, (attacker, "p1"), pid="p2")
    roundtrip(s)


def test_extra_untap_in_current_turn_does_not_replace_previous_own_turn(cards):
    s = setup(cards)
    sled = put(s, "Goblin Rock Sled", "battlefield", pid="p2")
    put(s, "Sphinx of the Second Sun", "battlefield", pid="p2")
    put(s, "Mountain", "battlefield")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (sled, "p1"), pid="p2")
    assert s.state.cards[sled.id].tapped
    to_phase(s, "main2", turn=2)
    settle(s)
    to_phase(s, "upkeep", turn=2)
    assert not s.state.cards[sled.id].tapped
    assert "p2" not in s.state.rules.completed_own_turns
    roundtrip(s)


def test_blinked_attacker_is_a_new_rules_object(cards):
    s = setup(cards)
    attacker = put(s, "Giant Turtle", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    old = s.state.rules.object_id(attacker.id)
    to_phase(s, "main1", turn=4)
    spell = put(s, "Cloudshift", "hand", pid="p2")
    mana(s, pid="p2", W=1)
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=spell.id, targets=[attacker.id])
    settle(s)
    assert s.state.rules.object_id(attacker.id) != old
    to_phase(s, "declare_attackers", turn=5)
    attack(s, (attacker, "p1"), pid="p2")
    roundtrip(s)


@pytest.mark.parametrize("target", ["p3", "walker"])
def test_sentinels_require_attack_on_you_not_another_player_or_your_walker(cards, target):
    s = setup(cards)
    sentinel = put(s, "Weathered Sentinels", "battlefield")
    attacker = put(s, "Grizzly Bears", "battlefield", pid="p2")
    walker = put(s, "Jace Beleren", "battlefield")
    act(s, "p1", type="counter", card_ids=[walker.id], kind="loyalty", delta=3)
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, walker.id if target == "walker" else target), pid="p2")
    to_phase(s, "declare_attackers", turn=4)
    with pytest.raises(ActionError):
        attack(s, (sentinel, "p2"))
    roundtrip(s)


@pytest.mark.parametrize("name", ["Giant Turtle", "Goblin Rock Sled"])
def test_history_resumes_after_three_players_in_fresh_process(cards, tmp_path, name):
    import subprocess
    import sys

    s = setup(cards)
    attacker = put(s, name, "battlefield", pid="p2")
    put(s, "Mountain", "battlefield")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "end", turn=4)
    saved = tmp_path / "own-turn.json"
    saved.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
card=s.state.cards[sys.argv[3]]
to_phase(s,'declare_attackers',turn=5)
try:attack(s,(card,'p1'),pid='p2')
except ActionError:pass
else:raise AssertionError('previous own turn restriction lost')
if sys.argv[4]=='Goblin Rock Sled':assert s.state.cards[card.id].tapped
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, "-c", code, str(saved), str(cards.db_path), attacker.id, name], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def next_own_declaration(s, pid, after):
    for _ in range(600):
        if s.state.turn.active_player == pid and s.state.turn.number > after and s.state.turn.phase == "declare_attackers":
            return
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("No next own turn")


def test_phasing_preserves_attacker_object_history(cards):
    s = setup(cards)
    attacker = put(s, "Giant Turtle", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    oid = s.state.rules.object_id(attacker.id)
    to_phase(s, "main1", turn=4)
    spell = put(s, "Reality Ripple", "hand")
    mana(s, pid="p1", U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[attacker.id])
    settle(s)
    assert s.state.cards[attacker.id].zone == "p2:phased"
    to_phase(s, "declare_attackers", turn=5)
    assert s.state.cards[attacker.id].zone == "p2:battlefield"
    assert s.state.rules.object_id(attacker.id) == oid
    with pytest.raises(ActionError):
        attack(s, (attacker, "p1"), pid="p2")
    roundtrip(s)


def test_skipped_own_turn_does_not_overwrite_last_completed_own_turn(cards):
    s = setup(cards)
    attacker = put(s, "Giant Turtle", "battlefield", pid="p2")
    tog = put(s, "Chronatog", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "main1", turn=3)
    act(s, "p3", type="pass_priority")
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="activate_ability", card_id=tog.id, ability=0)
    settle(s)
    next_own_declaration(s, "p2", 2)
    assert s.state.rules.completed_own_turns["p2"].turn == 2
    assert s.state.turn.number > 5
    with pytest.raises(ActionError):
        attack(s, (attacker, "p1"), pid="p2")
    roundtrip(s)


def test_current_controller_selects_which_players_previous_turn_is_relevant(cards):
    s = setup(cards)
    attacker = put(s, "Giant Turtle", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "main1", turn=4)
    enchant(s, "Confiscate", attacker)
    assert s.state.cards[attacker.id].controller == "p1"
    to_phase(s, "declare_attackers", turn=7)
    attack(s, (attacker, "p2"))
    roundtrip(s)


@pytest.mark.parametrize("name", ["Giant Turtle", "Tangle Kelp"])
def test_source_ability_loss_or_departure_removes_history_restriction(cards, name):
    s = setup(cards)
    attacker = put(s, "Giant Turtle" if name == "Giant Turtle" else "Grizzly Bears", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "main1", turn=4)
    if name == "Giant Turtle":
        enchant(s, "Lignify", attacker)
    else:
        aura = enchant(s, name, attacker)
        spell = put(s, "Naturalize", "hand")
        mana(s, pid="p1", G=1, C=1)
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[aura.id])
        settle(s)
    to_phase(s, "declare_attackers", turn=5)
    assert not s.state.cards[attacker.id].tapped
    attack(s, (attacker, "p1"), pid="p2")
    roundtrip(s)


def test_legacy_unavailable_history_is_conservative_read_only_and_recovers(cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    s = setup(cards)
    attacker = put(s, "Giant Turtle", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "end", turn=4)
    saved = s.state.model_dump(mode="json")
    for field in ["completed_own_turns", "own_turn_history_known", "own_turn_history_notice"]:
        saved["rules"].pop(field)
    saved["rules"]["turn_log"].pop("active_player")
    legacy = GameSession(GameState.model_validate(saved), cards=cards)
    before = legacy.state.model_dump(mode="json")
    p = Plan.view(legacy.state, "p2", cards)
    assert combat.attack_problem(p.state, p.state.cards[attacker.id], p.ch(p.state.cards[attacker.id]))
    assert legacy.state.model_dump(mode="json") == before
    to_phase(legacy, "declare_attackers", turn=5)
    with pytest.raises(ActionError):
        attack(legacy, (attacker, "p1"), pid="p2")
    assert legacy.state.rules.own_turn_history_notice
    to_phase(legacy, "declare_attackers", turn=8)
    attack(legacy, (attacker, "p1"), pid="p2")
    notices = [e for e in legacy.state.log if any("Earlier attack history" in (part.t or "") for part in e.parts)]
    assert len(notices) == 1
    roundtrip(legacy)


def test_sentinels_permission_does_not_grant_haste(cards):
    s = setup(cards)
    attacker = put(s, "Grizzly Bears", "battlefield", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (attacker, "p1"), pid="p2")
    to_phase(s, "main1", turn=4)
    sentinel = put(s, "Weathered Sentinels", "battlefield")
    to_phase(s, "declare_attackers", turn=4)
    with pytest.raises(ActionError):
        attack(s, (sentinel, "p2"))
    roundtrip(s)


@pytest.mark.parametrize("target", ["p3", "walker"])
def test_unconditional_defender_bypass_can_satisfy_other_destinations(cards, target):
    s = setup(cards)
    sentinel = put(s, "Weathered Sentinels", "battlefield")
    put(s, "High Alert", "battlefield")
    walker = put(s, "Jace Beleren", "battlefield", pid="p2")
    act(s, "p2", type="counter", card_ids=[walker.id], kind="loyalty", delta=3)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (sentinel, walker.id if target == "walker" else target))
    roundtrip(s)


def test_entering_attacking_is_not_recorded_as_a_declared_attack(cards):
    s = setup(cards)
    source = put(s, "Yore-Tiller Nephilim", "battlefield", pid="p2")
    turtle = put(s, "Giant Turtle", "graveyard", pid="p2")
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (source, "p1"), pid="p2")
    for _ in range(40):
        if s.state.cards[turtle.id].attacking:
            break
        settle(s)
        d = s.state.rules.decision
        if d is not None:
            selected = turtle.id if any(o.id == turtle.id for o in d.options) else "p1" if any(o.id == "p1" for o in d.options) else d.options[0].id
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[selected])
    assert s.state.cards[turtle.id].attacking
    oid = s.state.rules.object_id(turtle.id)
    assert oid not in s.state.rules.turn_log.attackers["p2"]
    to_phase(s, "declare_attackers", turn=5)
    attack(s, (turtle, "p1"), pid="p2")
    roundtrip(s)
