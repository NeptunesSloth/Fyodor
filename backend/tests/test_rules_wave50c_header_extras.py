"""Wave 50C: more of a modal ability's header and modes (CR 2026-09-25), real Oracle text (tests/fixtures/wave50c_cards.json, from data/cards.sqlite). Every
scenario checks the replay and a save and a load.

* 700.2 / 608.2c: "choose one that hasn't been chosen and you lose 2 life —" (Zuko, Conflicted), "choose one and Glorfindel gets +1/+1 until end of turn":
  an instruction of the ability itself, carried out before the chosen mode, whichever it is.
* 608.2d: "Exile Zuko, then return him to the battlefield under an opponent's control." (Zuko; Sol'Kanar the Tainted): its controller chooses the opponent
  (one opponent: nothing to choose); the permanent is a new object (400.7) that its new controller controls (the abilities trigger for them).
* 700.2 (Sol'Kanar's ruling 2022-09-09): the memory of "that hasn't been chosen" is per ability of the object, and a mode with "up to one target" is chosen
  and remembered like any other.
* Gnostro's "{T}: Choose one. X is the number of spells you've cast this turn." (ruling 2020-11-10: X is determined as the ability resolves).
* 603.4: Jin Sakai's "if no other creatures are attacking that player" - the attacker is the only creature attacking the player it attacked.
"""

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
from tests.test_rules_wave34b_activated import ability, ask, attack, next_turn, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50c", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
SCRY = card("Peek Ahead", set_code="w50c", number="P02", mana_cost="{U}", cmc=1.0, type_line="Sorcery", oracle_text="Scry 1.", colors=["U"], color_identity=["U"])


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, SCRY], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def choose(s, *ids):
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards", d
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))
    return d


# --- Zuko, Conflicted ------------------------------------------------------------------------------------------------------------------------


def test_zuko_loses_two_life_and_does_the_mode_then_the_mode_is_spent(cards):
    s = build(cards, ["Zuko, Conflicted", "Grizzly Bears"], forests=30)
    zuko = put(s, "Zuko, Conflicted")
    to_phase(s, "main1", turn=3)
    d = ask(s)
    assert d.prompt == "Zuko, Conflicted: choose one mode that hasn't been chosen"
    mine = life(s)
    choose(s, "1:0")  # a +1/+1 counter on Zuko
    settle(s)
    assert life(s) == mine - 2 and s.state.cards[zuko.id].counters.get("+1/+1") == 1
    check(s)
    s = reloaded(s)
    to_phase(s, "main1", turn=5)
    d = ask(s)
    assert [o.id for o in d.options] == ["0:0", "2:0", "3:0"]  # (the second mode was chosen: not offered)
    mine = life(s)
    choose(s, "0:0")
    settle(s)
    assert life(s) == mine - 2
    check(s)


def test_zuko_goes_to_the_opponent_who_then_makes_the_choices(cards):
    s = build(cards, ["Zuko, Conflicted"], ["Grizzly Bears"], forests=30)
    put(s, "Zuko, Conflicted")
    to_phase(s, "main1", turn=3)
    mine = life(s)
    ask(s)
    choose(s, "3:0")  # exile Zuko, return him under an opponent's control
    settle(s)
    zuko = card_named(s, "Zuko, Conflicted")
    assert (zuko.zone, zuko.controller, zuko.owner) == ("p2:battlefield", "p2", "p1")
    assert life(s) == mine - 2  # (Alice lost the 2 life as the ability resolved: "you" is its controller)
    check(s)
    s = reloaded(s)
    to_phase(s, "main1", turn=4)  # Bob's first main phase: the new object's ability triggers for its controller, who chooses the mode
    d = ask(s)
    assert d.player == "p2" and [o.id for o in d.options] == ["0:0", "1:0", "2:0", "3:0"]  # (a new object: no mode is spent)


# --- Glorfindel, Dauntless Rescuer ---------------------------------------------------------------------------------------------------------


def test_glorfindel_gets_the_pump_whichever_mode_is_chosen(cards):
    s = build(cards, ["Glorfindel, Dauntless Rescuer", "Peek Ahead"], forests=30)
    put(s, "Glorfindel, Dauntless Rescuer")
    assert pt(s, "Glorfindel, Dauntless Rescuer") == (3, 2)
    to_hand(s, "Peek Ahead")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Peek Ahead").id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards" and d.prompt.startswith("Glorfindel"):
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d.prompt == "Glorfindel, Dauntless Rescuer: choose one mode"
    choose(s, "1:0")  # can't be blocked by more than one creature
    settle(s)
    assert pt(s, "Glorfindel, Dauntless Rescuer") == (4, 3)
    check(s)
    s = reloaded(s)
    assert pt(s, "Glorfindel, Dauntless Rescuer") == (4, 3)
    to_phase(s, "main1", turn=3)
    assert pt(s, "Glorfindel, Dauntless Rescuer") == (3, 2)  # until end of turn


# --- Sol'Kanar the Tainted -------------------------------------------------------------------------------------------------------------------


def test_solkanar_damage_mode_with_a_target_is_remembered_and_the_last_mode_gives_it_away(cards):
    s = build(cards, ["Sol'Kanar the Tainted"], ["Grizzly Bears", "Grizzly Bears"], forests=30)
    put(s, "Sol'Kanar the Tainted")
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"]
    for c in bears:
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    to_phase(s, "end", turn=1)
    ask(s)
    choose(s, "2:0")  # 3 damage to up to one other target creature or planeswalker
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears[0].id])
    settle(s)
    assert s.state.cards[bears[0].id].zone == "p2:graveyard" and s.state.cards[bears[1].id].zone == "p2:battlefield"
    check(s)
    s = reloaded(s)
    to_phase(s, "end", turn=3)
    d = ask(s)
    assert [o.id for o in d.options] == ["0:0", "1:0", "3:0"]  # (mode 3 - the damage - was chosen: not offered)
    choose(s, "3:0")
    settle(s)
    sk = card_named(s, "Sol'Kanar the Tainted")
    assert (sk.zone, sk.controller, sk.owner) == ("p2:battlefield", "p2", "p1")
    check(s)


# --- Gnostro, Voice of the Crags -------------------------------------------------------------------------------------------------------------


def test_gnostro_x_is_the_spells_cast_this_turn(cards):
    s = build(cards, ["Gnostro, Voice of the Crags", "Lightning Bolt", "Lightning Bolt"], forests=30)
    put(s, "Gnostro, Voice of the Crags")
    next_turn(s)
    gnostro = card_named(s, "Gnostro, Voice of the Crags")
    for _ in range(2):  # two spells this turn
        to_hand(s, "Lightning Bolt")
        mana(s, R=1)
        act(s, "p1", type="cast_spell", card_id=[c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.zone == "p1:hand"][0].id, targets=["p2"])
        settle(s)
    mine = life(s)
    act(s, "p1", type="activate_ability", card_id=gnostro.id, ability=ability(s, "Gnostro, Voice of the Crags", contains="Choose one"), modes=[2])
    settle(s)
    assert life(s) == mine + 2  # X = 2
    check(s)
    s = reloaded(s)
    assert life(s) == mine + 2


# --- Jin Sakai, Ghost of Tsushima ----------------------------------------------------------------------------------------------------------


def test_jin_sakai_triggers_for_a_lone_attacker_only(cards):
    s = build(cards, ["Jin Sakai, Ghost of Tsushima", "Grizzly Bears", "Grizzly Bears"], ["Grizzly Bears"], forests=30)
    put(s, "Jin Sakai, Ghost of Tsushima")
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"]
    for c in bears:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    stops(s)
    next_turn(s)
    attack(s, *bears)  # two attackers: neither is alone
    assert s.state.rules.decision is None or s.state.rules.decision.kind != "choose_cards"
    check(s)
    s = build(cards, ["Jin Sakai, Ghost of Tsushima", "Grizzly Bears"], ["Grizzly Bears"], forests=30)
    put(s, "Jin Sakai, Ghost of Tsushima")
    lone = put(s, "Grizzly Bears")
    stops(s)
    next_turn(s)
    attack(s, lone)
    d = ask(s)
    assert d.kind == "choose_cards" and [o.label[:7] for o in d.options] == ["Standof", "Ghost —"]
    choose(s, "0:0")  # double strike
    settle(s)
    assert "double strike" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[lone.id]).keywords
    check(s)
