"""Turn clock (stage 3): when a clock reaches zero and the host chose "Act for the player", the server answers with the safest legal
default (app/game/clock_defaults.py) -- never a concession or an elimination. Real Oracle text, a replay and a save/load round trip."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.clock_defaults import answers
from app.game.errors import ActionError
from app.game.mulligan import COMMANDER_LONDON
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, turn_on
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

FIXTURES = Path(__file__).parent / "fixtures"
FILES = ("attack_destinations34_cards.json", "turn_clock_defaults_cards.json")
TOLL = "Clock Toll"


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for f in FILES:
        for i, c in enumerate(json.loads((FIXTURES / f).read_text())):
            base[c["name"]] = card(c["name"], set_code=f[:5], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    # (synthetic, by the review's ruling: the plain "loses N life unless they pay {M}" 118.12a payment)
    base[TOLL] = card(TOLL, set_code="tcd", number="S1", type_line="Sorcery", oracle_text="Target player loses 4 life unless they pay {1}.")
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c["name"] for f in FILES for c in json.loads((FIXTURES / f).read_text())] + ["Murder", "Breeding Pool", TOLL]
    return table(cards, names, names, names)


def first_accepted(s, pid):
    for p in answers(s.state, pid, s.cards):
        try:
            act(s, pid, **p)
            return p
        except (ActionError, ValidationError):
            continue
    return None


def nobody_out(s):
    r = s.state.rules
    assert r is None or (not r.conceded and not r.lost)
    assert not any(p.left for p in s.state.players.values())


def until(s, done, limit=60):
    """Pass priority (no blockers, triggers in the order offered) until ``done(s)``."""
    for _ in range(limit):
        if done(s):
            return
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None and d.kind == "order":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
        elif d is not None:
            raise AssertionError(f"unexpected decision {d.kind}: {d.prompt}")
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got there")


def choose(d, ids):
    return {"type": "choose", "decision_id": d.id, "option_ids": ids}


def test_priority_is_passed(cards):  # 117.3d
    s = setup(cards)
    start(s)
    assert s.state.rules.priority == "p1" and s.state.rules.decision is None
    assert answers(s.state, "p1", s.cards) == [{"type": "pass_priority"}]
    assert answers(s.state, "p2", s.cards) == []  # (nobody waits on Bob)
    assert first_accepted(s, "p1") == {"type": "pass_priority"}
    assert s.state.rules.priority == "p2"
    nobody_out(s)
    roundtrip(s)


def test_a_may_trigger_is_declined(cards):  # 603.5, 608.2d: Bident of Thassa's "you may draw a card"
    s = setup(cards)
    put(s, "Bident of Thassa", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    start(s)
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind not in ("declare_blockers", "order"))
    d = s.state.rules.decision
    assert d.player == "p1" and d.kind == "confirm" and {o.id for o in d.options} == {"yes", "no"}  # (rules/effects.py: draw_may)
    hand = len(s.state.zones["p1:hand"])
    ans = answers(s.state, "p1", s.cards)
    assert ans[0] == choose(d, ["no"])
    assert first_accepted(s, "p1") == ans[0]
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand and s.state.players["p2"].life == 38
    nobody_out(s)
    roundtrip(s)


def test_a_cast_being_announced_is_taken_back(cards):  # 601.2c, 733.1
    s = setup(cards)
    victim = put(s, "Grizzly Bears", "battlefield", pid="p2")
    start(s)
    murder = put(s, "Murder", "hand")
    mana(s, B=2, C=1)
    pool = dict(s.state.players["p1"].mana)
    act(s, "p1", type="cast_spell", card_id=murder.id)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"
    ans = answers(s.state, "p1", s.cards)
    assert ans[0] == choose(d, ["cancel"])
    assert first_accepted(s, "p1") == ans[0]
    assert s.state.cards[murder.id].zone == "p1:hand" and not s.state.zones.get("stack")
    assert s.state.players["p1"].mana == pool
    assert s.state.rules.decision is None and s.state.cards[victim.id].zone == "p2:battlefield"
    nobody_out(s)
    roundtrip(s)


@pytest.mark.parametrize("juggernaut", [False, True])
def test_no_attack_unless_a_creature_must(cards, juggernaut):  # 508.1a, 508.1d
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    jug = put(s, "Juggernaut", "battlefield") if juggernaut else None
    start(s)
    to_phase(s, "declare_attackers", turn=4)
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_attackers" and d.player == "p1"
    ans = answers(s.state, "p1", s.cards)
    assert ans[0] == {"type": "declare_attackers", "attackers": []}
    got = first_accepted(s, "p1")
    assert s.state.cards[bear.id].attacking is None
    if jug is None:
        assert got == ans[0]
    else:
        assert got == {"type": "declare_attackers", "attackers": [{"card_id": jug.id, "target": "p2"}]}
        assert s.state.cards[jug.id].attacking is not None
    nobody_out(s)
    roundtrip(s)


def test_no_block_unless_a_creature_must(cards):  # 509.1a, 509.1c: only the creature that must block does
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    screen = put(s, "Razorgrass Screen", "battlefield", pid="p2")
    idle = put(s, "Grizzly Bears", "battlefield", pid="p2")
    start(s)
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    assert s.state.rules.decision.player == "p2"
    ans = answers(s.state, "p2", s.cards)
    assert ans[0] == {"type": "declare_blockers", "blocks": []}
    got = first_accepted(s, "p2")
    assert got != ans[0]  # the empty declaration is refused (509.1c)
    assert got == {"type": "declare_blockers", "blocks": [{"blocker_id": screen.id, "attacker_id": bear.id}]}
    assert s.state.cards[screen.id].blocking == bear.id and s.state.cards[idle.id].blocking is None
    nobody_out(s)
    roundtrip(s)


def test_mulligans_keep_then_bottom_the_first_cards(cards):  # 103.5
    from tests.test_rules_first_turn_untap_s7 import table as fresh

    s = fresh(cards, COMMANDER_LONDON)
    for _ in range(3):
        act(s, "p1", type="mulligan_take")
    assert answers(s.state, "p1", s.cards) == [{"type": "mulligan_keep"}]
    assert first_accepted(s, "p1") == {"type": "mulligan_keep"}
    seat = s.state.pregame.seats["p1"]
    assert seat.status == "bottoming" and seat.to_bottom == 2
    hand = list(s.state.zones["p1:hand"])
    assert first_accepted(s, "p1") == {"type": "mulligan_bottom", "card_ids": hand[:2]}
    assert s.state.zones["p1:library"][-2:] == hand[:2] and len(s.state.zones["p1:hand"]) == 5
    assert first_accepted(s, "p2") == {"type": "mulligan_keep"}
    assert s.state.pregame.finished
    nobody_out(s)
    roundtrip(s)


def assisted(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    start(s)
    turn_on(s, "assisted")
    return s, bear


def asked(s):
    return lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind not in ("declare_blockers", "order")


def test_assisted_rules_confirmations_are_applied(cards):  # 510.2
    s, bear = assisted(cards)
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    until(s, asked(s))
    d = s.state.rules.decision
    assert d.kind == "confirm" and d.prompt == "Combat damage: Grizzly Bears → Bob 2"
    assert answers(s.state, "p1", s.cards)[0] == choose(d, ["yes"])
    assert first_accepted(s, "p1") == choose(d, ["yes"])
    assert s.state.players["p2"].life == 38
    nobody_out(s)
    roundtrip(s)


def test_assisted_state_based_actions_are_applied_unless_a_player_would_lose(cards):  # 704.3, 704.5a, 704.5g
    s, bear = assisted(cards)
    act(s, "p1", type="set_damage", card_ids=[bear.id], delta=2)  # by hand
    act(s, "p1", type="pass_priority")
    d = s.state.rules.decision
    assert d.kind == "confirm" and d.resume["step"] == "sba_confirm" and "Grizzly Bears dies" in d.prompt
    assert first_accepted(s, "p1") == choose(d, ["yes"])
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    act(s, "p1", type="set_life", player="p2", value=0)  # by hand
    until(s, asked(s))
    d = s.state.rules.decision
    assert d.resume["step"] == "sba_confirm" and "Bob loses" in d.prompt
    assert answers(s.state, d.player, s.cards) == []  # an elimination is left to the table
    nobody_out(s)
    roundtrip(s)


def test_an_optional_damage_choice_is_declined(cards):  # 101.4, 118.12, 608.2d: Browbeat at 5 life
    from tests.test_rules_declaration_requirements33 import cast

    s = setup(cards)
    start(s)
    act(s, "p1", type="set_life", player="p1", value=5)
    cast(s, "Browbeat", ["p3"])
    hand = len(s.state.zones["p3:hand"])
    for pid in ("p1", "p2", "p3"):  # 101.4: each player chooses in APNAP order
        d = s.state.rules.decision
        assert d.player == pid and {o.id for o in d.options} == {"pay", "decline"}
        assert answers(s.state, pid, s.cards)[0] == choose(d, ["decline"])
        assert first_accepted(s, pid) == choose(d, ["decline"])
    settle(s)
    assert s.state.players["p1"].life == 5 and len(s.state.zones["p3:hand"]) == hand + 3
    nobody_out(s)
    roundtrip(s)


def test_a_shock_land_enters_tapped(cards):  # 614.12a, 608.2d: "you may pay 2 life. If you don't, it enters tapped."
    s = setup(cards)
    start(s)
    pool = put(s, "Breeding Pool", "hand")
    act(s, "p1", type="play_land", card_id=pool.id)
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {"pay", "tapped"}
    assert first_accepted(s, "p1") == choose(d, ["tapped"])
    assert s.state.cards[pool.id].zone == "p1:battlefield" and s.state.cards[pool.id].tapped
    assert s.state.players["p1"].life == 40
    nobody_out(s)
    roundtrip(s)


def test_a_pact_payment_is_left_to_the_table(cards):  # 118.12a: "you lose the game unless you pay": declining would eliminate
    from tests.test_rules_declaration_requirements33 import cast
    from tests.test_rules_wave30m_durations import settle as resolve

    s = setup(cards)
    start(s, turn=1)
    cast(s, "Summoner's Pact")
    resolve(s, prefer=["Grizzly Bears"])
    to_phase(s, "upkeep", turn=4)
    mana(s, G=2, C=2)
    until(s, asked(s))
    d = s.state.rules.decision
    assert d.player == "p1" and {"pay", "decline"} <= {o.id for o in d.options}
    assert answers(s.state, "p1", s.cards) == []
    nobody_out(s)
    roundtrip(s)


def test_a_cast_being_paid_for_is_taken_back(cards):  # 601.2h, 733.1: the payment prompt's "cancel"
    s = setup(cards)
    bears = put(s, "Grizzly Bears", "hand")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:2]
    act(s, "p1", type="move", card_ids=[f.id for f in forests], to={"player": "p1", "zone": "battlefield"})
    start(s)
    act(s, "p1", type="set_prefs", payment="self")
    pool = dict(s.state.players["p1"].mana)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    d = s.state.rules.decision
    assert d.resume["step"] in ("payment", "pay_mana") and "cancel" in {o.id for o in d.options}
    assert answers(s.state, "p1", s.cards)[0] == choose(d, ["cancel"])
    assert first_accepted(s, "p1") == choose(d, ["cancel"])
    assert s.state.cards[bears.id].zone == "p1:hand" and not s.state.zones.get("stack")
    assert s.state.players["p1"].mana == pool and not any(s.state.cards[f.id].tapped for f in forests)
    nobody_out(s)
    roundtrip(s)


def test_manual_resolution_is_left_to_the_table(cards):
    from app.game.session import GameSession
    from tests.game_helpers import enable, find, make_session

    s = GameSession(enable(make_session(cards).state), cards=cards)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="draw", count=7)
    ring = find(s.state, "Sol Ring", "p1")
    act(s, "p1", type="set_card_automation", card_id=ring.id, mode="manual")
    act(s, "p1", type="play_land", card_id=find(s.state, "Mountain", "p1").id)
    act(s, "p1", type="cast_spell", card_id=ring.id)
    assert s.state.rules.decision.kind == "manual_resolution"
    assert answers(s.state, "p1", s.cards) == []
    nobody_out(s)
    roundtrip(s)


# -- review round 2: a decline that harms the player is never picked (the table decides) --


def test_unless_they_discard_at_5_life_is_left_to_the_table(cards):  # 118.12a: Painful Quandary, declining loses 5 life
    from tests.test_rules_declaration_requirements33 import cast

    s = setup(cards)
    put(s, "Painful Quandary", "battlefield")
    victim = put(s, "Grizzly Bears", "battlefield")
    start(s)
    put(s, "Island", "hand", pid="p2")
    act(s, "p1", type="set_life", player="p2", value=5)
    cast(s, "Murder", [victim.id], pid="p2")
    until(s, asked(s))
    d = s.state.rules.decision
    assert d.player == "p2" and {o.id for o in d.options} == {"pay", "decline"}
    assert answers(s.state, "p2", s.cards) == []
    assert s.state.players["p2"].life == 5 and "p2" not in s.state.rules.lost
    nobody_out(s)
    roundtrip(s)


def test_loses_life_unless_they_pay_is_left_to_the_table(cards):  # 118.12a: "Target player loses 4 life unless they pay {1}."
    from tests.test_rules_declaration_requirements33 import cast

    s = setup(cards)
    start(s)
    mana(s, pid="p2", C=1)  # (118.3: PAY is offered only while it can be paid)
    cast(s, TOLL, ["p2"])
    until(s, asked(s))
    d = s.state.rules.decision
    assert d.player == "p2" and {"pay", "decline"} <= {o.id for o in d.options}
    assert answers(s.state, "p2", s.cards) == []
    assert s.state.players["p2"].life == 40
    nobody_out(s)
    roundtrip(s)


def test_sacrifice_or_take_damage_is_left_to_the_table(cards):  # Enchanter's Bane: "no" is "Take 2 damage"
    s = setup(cards)
    start(s)
    bane = put(s, "Enchanter's Bane", "battlefield")  # (after the earlier end steps of turn 1)
    act(s, "p1", type="set_life", player="p1", value=2)
    to_phase(s, "end", turn=4)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and (d.resume or {}).get("step") == "bane100e":
            break
        if d is not None:  # (its target: the Bane itself, the only enchantment)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.resume["step"] == "bane100e" and d.player == "p1"
    assert answers(s.state, "p1", s.cards) == []
    assert s.state.cards[bane.id].zone == "p1:battlefield" and s.state.players["p1"].life == 2
    nobody_out(s)
    roundtrip(s)


def test_a_commander_goes_to_the_command_zone(cards):  # 903.9a: its owner may put it into the command zone
    from tests.test_rules_designations import find

    s = setup(cards)
    start(s)
    krenko = find(s, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "graveyard"})
    until(s, asked(s))
    d = s.state.rules.decision
    assert d.resume["step"] == "commander_zone" and d.player == "p1"
    assert answers(s.state, "p1", s.cards)[0] == choose(d, ["yes"])
    assert first_accepted(s, "p1") == choose(d, ["yes"])
    assert s.state.cards[krenko.id].zone == "p1:command"
    nobody_out(s)
    roundtrip(s)
