"""Wave 21A: the static_other long tail, small slice (CR 2026-09-25).

* 106.4 / 500.4: "You don't lose unspent red mana as steps and phases end." (Ashling, Flame Dancer), and "Omnath gets +1/+1 for each unspent
  green mana you have." (Omnath, Locus of Mana).
* 702.34a: "Each instant and sorcery card in your graveyard has flashback. The flashback cost is equal to that card's mana cost." (Lier,
  Disciple of the Drowned; "During your turn, …": Return the Past).
* 614.12: "Non-Phyrexian creatures enter tapped." (Phyrexian Censor).
* 508.1c-d / 506.3d: "This creature can't attack unless defending player controls a Forest." (Gorilla Pack, Bog Serpent …), "… can't attack if
  defending player controls an untapped creature with power 3 or greater." (Orgg), "… unless defending player is the monarch"
  (Crown-Hunter Hireling), "… unless you control more creatures than defending player." / "can't block unless you control more creatures
  than attacking player." (Mogg Toady).

Every scenario uses the cards' current Oracle text (tests/fixtures/wave21a_cards.json, from data/cards.sqlite), checks that replaying the
recorded history reproduces the table, and that a save/load round trip keeps it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave5j_token_copies import cast, ch, drive, find, game, mana, put, roundtrip, token

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave21a_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t21a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]
NAMES = [c["name"] for c in EXTRA]
WALKER = card("Phyrexian Walker", set_code="t21a", number="A90", mana_cost="{0}", cmc=0.0, type_line="Artifact Creature — Phyrexian",
              oracle_text="", power="0", toughness="3")


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, WALKER], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def level(name):
    c = next(c for c in EXTRA if c["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


@pytest.mark.parametrize("name", NAMES)
def test_the_promoted_cards_are_full(name):
    assert level(name) == "FULL", name


def unready(s, *cs):
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0  # (there since before the turn: no summoning sickness)


def pool(s, pid="p1"):
    return dict(s.state.players[pid].mana)


def next_step(s):
    start = s.state.turn.phase
    until(s, lambda s: s.state.turn.phase != start, limit=60)


# -- unspent mana -----------------------------------------------------------------------------------------------------
def test_ashling_keeps_red_mana_through_steps_and_turns(cards):
    s = game(cards, ["Ashling, Flame Dancer"])
    put(s, "Ashling, Flame Dancer")
    mana(s, "p1", R=2, G=1, U=1)
    next_step(s)
    assert pool(s) == {"R": 2}  # 500.4: the green and blue emptied; the red is never lost
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1", limit=200)
    assert pool(s) == {"R": 2}  # (not even as the turn ends)
    roundtrip(s)


def test_omnath_keeps_green_and_counts_it(cards):
    s = game(cards, ["Omnath, Locus of Mana"])
    omnath = put(s, "Omnath, Locus of Mana")
    assert ch(s, omnath).pt == (1, 1)
    mana(s, "p1", G=3, R=1)
    assert ch(s, omnath).pt == (4, 4)  # +1/+1 for each unspent green mana (the red isn't counted)
    next_step(s)
    assert pool(s) == {"G": 3} and ch(s, omnath).pt == (4, 4)
    roundtrip(s)


# -- flashback from a static ---------------------------------------------------------------------------------------------
def test_lier_gives_instants_flashback_for_their_mana_cost(cards):
    s = game(cards, ["Lier, Disciple of the Drowned", "Lightning Bolt", "Grizzly Bears"])
    put(s, "Grizzly Bears", "graveyard")
    bolt = put(s, "Lightning Bolt", "graveyard")
    mana(s, "p1", R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # (no Lier yet)
    put(s, "Lier, Disciple of the Drowned")
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    until(s, lambda s: not s.state.zones.get("stack"), limit=20)
    assert s.state.players["p2"].life == 37 and pool(s) == {}
    assert s.state.cards[bolt.id].zone == "p1:exile"  # 702.34a: exiled as it leaves the stack
    bears = find(s, "Grizzly Bears")
    mana(s, "p1", G=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears.id)  # (a creature card in the graveyard has none)
    roundtrip(s)


def test_return_the_past_gives_flashback_during_your_turn(cards):
    s = game(cards, ["Return the Past", "Lightning Bolt"])
    put(s, "Return the Past")
    bolt = put(s, "Lightning Bolt", "graveyard")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    until(s, lambda s: not s.state.zones.get("stack"), limit=20)
    assert s.state.players["p2"].life == 37
    roundtrip(s)


# -- enters tapped ------------------------------------------------------------------------------------------------------
def test_phyrexian_censor_taps_the_non_phyrexians_only(cards):
    s = game(cards, ["Phyrexian Censor", "Grizzly Bears", "Phyrexian Walker"])
    put(s, "Phyrexian Censor")
    bears = cast(s, "Grizzly Bears", G=1, C=1)
    drive(s)
    walker = cast(s, "Phyrexian Walker")
    drive(s)
    assert s.state.cards[bears.id].tapped and not s.state.cards[walker.id].tapped
    roundtrip(s)


# -- where it may attack / block ------------------------------------------------------------------------------------------
def to_attack(s):
    until(s, lambda s: s.state.turn.number == 1 and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")


def hit(s):
    """The attack went through (nobody blocks): the defending player was dealt damage."""
    until(s, lambda s: s.state.turn.phase in ("combat_damage", "end_combat", "main2"), limit=30)
    return s.state.players["p2"].life < 40


def attack(s, c, target="p2"):
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": target}])


def test_gorilla_pack_needs_a_forest_of_the_defending_player(cards):
    s = game(cards, ["Gorilla Pack"])
    pack = put(s, "Gorilla Pack")
    unready(s, pack)
    token(s, "p1", "Forest", None, "Token Land — Forest")  # (its own Forest doesn't count)
    to_attack(s)
    with pytest.raises(ActionError, match="can't attack"):
        attack(s, pack)
    token(s, "p2", "Forest", None, "Token Land — Forest")
    attack(s, pack)
    assert hit(s)
    roundtrip(s)


def test_orgg_stays_home_while_they_have_an_untapped_big_creature(cards):
    s = game(cards, ["Orgg"])
    orgg = put(s, "Orgg")
    unready(s, orgg)
    big = token(s, "p2", "Ogre", "3/3", "Token Creature — Ogre")
    to_attack(s)
    with pytest.raises(ActionError, match="can't attack"):
        attack(s, orgg)
    act(s, "p2", type="tap", card_ids=[big.id], tapped=True)  # 3/3 but tapped: no longer in the way
    attack(s, orgg)
    assert hit(s)
    roundtrip(s)


def test_crown_hunter_hireling_attacks_only_the_monarch(cards):
    s = game(cards, ["Crown-Hunter Hireling"])
    hireling = put(s, "Crown-Hunter Hireling")
    unready(s, hireling)
    to_attack(s)
    with pytest.raises(ActionError, match="can't attack"):
        attack(s, hireling)
    act(s, "p2", type="set_monarch", player="p2")
    attack(s, hireling)
    assert hit(s)
    roundtrip(s)


def test_mogg_toady_attacks_only_when_its_controller_has_more_creatures(cards):
    s = game(cards, ["Mogg Toady"])
    toady = put(s, "Mogg Toady")
    unready(s, toady)
    token(s, "p2", "Wolf", "2/2", "Token Creature — Wolf")
    to_attack(s)
    with pytest.raises(ActionError, match="can't attack"):
        attack(s, toady)  # two creatures against one is more; one against one is not: Toady and the Wolf, so it is 1 v 1
    token(s, "p1", "Bear", "2/2", "Token Creature — Bear")
    attack(s, toady)
    assert hit(s)
    roundtrip(s)


def test_mogg_toady_blocks_only_when_its_controller_has_more_creatures(cards):
    s = game(cards, [], ["Mogg Toady"])
    toady = put(s, "Mogg Toady", pid="p2")
    raider = token(s, "p1", "Raider", "2/2", "Token Creature — Test")
    unready(s, raider)
    to_attack(s)
    attack(s, raider)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    with pytest.raises(ActionError, match="can't block"):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": toady.id, "attacker_id": raider.id}])  # (1 creature each)
    token(s, "p2", "Wolf", "2/2", "Token Creature — Wolf")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": toady.id, "attacker_id": raider.id}])
    roundtrip(s)
