"""Wave 29C: counts the engine used to cut off without saying (found by the audit of silent caps): the helpers offered while a player taps their
own mana (convoke / improvise / delve lists cut at 40 / 40 / 60, so a creature past the 40th could not be clicked), the amounts of energy a
"you may pay any amount of {E}" offers (60), the permanents kept tapped through an untap step (250), the permanents that may stay tapped (50).
A limit that remains (the Choose action takes 250 options) is said in the prompt.

Every scenario checks the replay and a save/load round trip."""

from __future__ import annotations

import pytest

from app.cards.importer import build_database
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import creature
from tests.test_rules_effects import mana, replay_matches
from tests.wave9c_kit import reloaded

HARNESSED = card("Harnessed Lightning", set_code="t29c", number="C01", mana_cost="{1}{R}", cmc=2.0, type_line="Instant", colors=["R"], color_identity=["R"],
                 oracle_text="Choose target creature. You get {E}{E}{E} (three energy counters), then you may pay any amount of {E}. "
                             "Harnessed Lightning deals that much damage to that creature.")


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), HARNESSED], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def table(cards, name, *, forests=15):
    alice = deck(cards, "Krenko, Mob Boss", [(1, name), (forests, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    state = enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False))
    for prefs in state.rules.prefs.values():
        prefs.payment = "self"  # (the player taps their own mana: the "tap your mana" prompt lists the helpers)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")
    spell = next(c for c in s.state.cards.values() if c.name == name)
    act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "hand"})
    return s, spell


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def test_every_creature_can_convoke_not_the_first_forty(cards):
    s, stoke = table(cards, "Stoke the Flames")
    ids = [creature(s, "p1", f"T{i:02d}", "1/1").id for i in range(45)]
    act(s, "p1", type="cast_spell", card_id=stoke.id, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and set(d.display["convoke"]) == set(ids)  # 702.51a: every untapped creature may help
    check(s)


def test_every_artifact_can_improvise_not_the_first_forty(cards):
    s, rev = table(cards, "Reverse Engineer")
    ids = []
    for i in range(45):
        act(s, "p1", type="create_token", player="p1", token={"name": f"Thopter{i:02d}", "type_line": "Token Artifact — Thopter"})
        ids.append(next(c.id for c in s.state.cards.values() if c.name == f"Thopter{i:02d}"))
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=rev.id)
    d = s.state.rules.decision
    assert d is not None and set(d.display["improvise"]) == set(ids)  # 702.126a
    check(s)


def test_every_card_of_a_big_graveyard_can_delve(cards):
    s, cruise = table(cards, "Treasure Cruise", forests=80)
    forests = [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][:70]
    act(s, "p1", type="move", card_ids=forests, to={"zone": "graveyard"})
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=cruise.id)
    d = s.state.rules.decision
    assert d is not None and set(d.display["delve"]) == set(forests)  # 702.66a: any card in the graveyard
    check(s)


def test_pay_any_amount_of_energy_offers_all_the_energy_the_player_has(cards):
    s, bolt = table(cards, "Harnessed Lightning")
    victim = creature(s, "p2", "Big Foe", "200/200")
    act(s, "p1", type="resource", player="p1", key="energy", delta=100)
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[victim.id])
    for _ in range(10):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and "pay how much" in d.prompt
    assert [o.id for o in d.options][0] == "103" and len(d.options) == 104  # 107.14: 100 + the three it just got, down to none
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["95"])
    for _ in range(10):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[victim.id].damage == 95 and s.state.players["p1"].resources.get("energy") == 8
    check(s)


def test_no_more_than_250_permanents_may_be_kept_tapped_by_an_untap_lock(cards):
    # 502.3: "Lands don't untap during their controllers' untap steps": every tapped land stays tapped, not the first 250 of them
    from tests.test_rules_effects import run_until

    s, _ = table(cards, "Treasure Cruise")
    act(s, "p1", type="create_token", player="p1", token={"name": "Lock Orb", "type_line": "Token Artifact",
                                                          "text": "Lands don't untap during their controllers' untap steps."})
    for n in (100, 100, 60):
        act(s, "p1", type="create_token", player="p1", count=n, tapped=True, stacked=False,
            token={"name": "Tapped Land", "type_line": "Token Land — Forest"})
    lands = [c.id for c in s.state.cards.values() if c.name == "Tapped Land"]
    assert len(lands) == 260 and all(s.state.cards[c].tapped for c in lands)
    run_until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.active_player == "p1" and s.state.turn.phase == "main1")
    assert all(s.state.cards[c].tapped for c in lands)
    check(s)


def test_a_limit_that_remains_is_said_in_the_prompt(cards):
    s, bolt = table(cards, "Harnessed Lightning")
    victim = creature(s, "p2", "Big Foe", "200/200")
    act(s, "p1", type="resource", player="p1", key="energy", delta=400)
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[victim.id])
    for _ in range(10):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and [o.id for o in d.options][0] == "250" and "at most 250" in d.prompt and "you have 403" in d.prompt
    check(s)
