"""Wave 110B session 19: single cards (real Oracle text in tests/fixtures/wave110b_cards.json).

* Genesis of the Daleks: 701.55a a targeted opponent faces a villainous choice; option one destroys the Daleks and the opponents lose life equal to the total power of
  the Daleks that died this turn (608.2h, as they last existed), option two destroys the non-Daleks. 714.2 chapter IV after three Dalek makers.
* Dr. Eggman: 701.55a the opponent discards, or its controller may put a Construct, Robot or Vehicle card from their hand onto the battlefield (they may also decline, 603.5).
* Osseous Sticktwister: 118.12, 101.4 each opponent may sacrifice a nonland permanent or discard a card; 608.2h the damage (its power) goes only to those who did neither; delirium (205.2a).
* Jace, Multiverse Architect: 508.1c, 118.12 unless the opponent pays {2} their creatures can't attack Jaces (planeswalkers with the Jace subtype) this turn; the player stays open.
* The Creation of Avacyn: 406.3, 607.2a chapter II turns the face-down exiled card up (a creature costs life equal to its mana value); chapter III puts a creature onto the battlefield or the card into hand.
* Temporal Extortion: 118.12, 107.1a any player may pay half their life rounded up; if a player does, the spell is countered (no extra turn).
* Market Gnome: 702.167a, 603.10a exiled from the battlefield as a craft cost is paid (its own or another card's materials), not when it is exiled otherwise.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110b_kit import (
    build,
    card_named,
    cast,
    check,
    drive,
    life,
    mana,
    put,
    repository,
    to_hand,
    zone_of,
)

IDOL = "Idol of the Deep King // Sovereign's Macuahuitl"


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Temporal Extortion", "The Creation of Avacyn", "Genesis of the Daleks", "Dr. Eggman", "Market Gnome", "Osseous Sticktwister", "Jace, Multiverse Architect"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def choice(option):
    """Answer the villainous choice with ``option`` ("a" or "b"); anything else takes the first option."""
    return lambda d: [option] if d.kind == "choose_one" and "villainous" in d.prompt else None


def genesis_to_chapter_four(cards, bears=False):
    s = build(cards, ["Genesis of the Daleks"], ["Grizzly Bears"] if bears else [], forests=30, islands=40)
    mana(s, B=2, C=4)
    cast(s, "Genesis of the Daleks")
    for turn in (3, 5):
        to_phase(s, "main1", turn=turn)
    if bears:
        put(s, "Grizzly Bears", "p2")
    to_phase(s, "main2", turn=6)
    return s


@pytest.mark.parametrize(("option", "opp_life", "daleks_left"), [("a", 40 - 18, 0), ("b", 40, 6)])
def test_genesis_chapter_four_villainous_choice(cards, option, opp_life, daleks_left):
    s = genesis_to_chapter_four(cards, bears=True)
    assert sum(1 for c in s.state.cards.values() if c.name == "Dalek" and c.zone == "p1:battlefield") == 6  # 1 + 2 + 3 tokens (chapters I-III)
    for _ in range(10):  # on to Alice's next precombat main phase: the chapter IV trigger asks Bob
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    drive(s, choice(option))
    assert life(s, "p2") == opp_life
    assert sum(1 for c in s.state.cards.values() if c.name == "Dalek" and c.zone == "p1:battlefield") == daleks_left
    assert zone_of(s, "Grizzly Bears", "p2") == ("p2:battlefield" if option == "a" else "p2:graveyard")
    check(s)


@pytest.mark.parametrize(("option", "discarded", "copter_on_table"), [("a", True, False), ("b", False, True), ("c", False, False)])
def test_dr_eggman_end_step(cards, option, discarded, copter_on_table):
    s = build(cards, ["Dr. Eggman", "Smuggler's Copter"], ["Grizzly Bears"], forests=30)
    put(s, "Dr. Eggman")
    to_hand(s, "Smuggler's Copter")
    to_hand(s, "Grizzly Bears", "p2")
    to_phase(s, "main2", turn=1)
    for _ in range(6):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")

    def answer(d):
        if d.kind == "choose_one" and "villainous" in d.prompt:
            return ["a" if option == "a" else "b"]
        if d.kind == "choose_cards":  # "you may put …": the card, or nothing (603.5)
            return [d.options[0].id] if option == "b" else []
        return None

    for _ in range(40):  # (drive() reads an empty answer as the first option: the decline is sent by hand)
        d = s.state.rules.decision
        if d is None:
            break
        ids = answer(d)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1] if ids is None else ids)
    assert (zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard") is discarded
    assert (zone_of(s, "Smuggler's Copter") == "p1:battlefield") is copter_on_table
    check(s)


@pytest.mark.parametrize("craft", [True, False])
def test_market_gnome_only_when_exiled_for_a_craft_cost(cards, craft):
    s = build(cards, ["Market Gnome", IDOL], [], forests=30)
    gnome = put(s, "Market Gnome")
    idol = put(s, IDOL)
    hand0, life0 = sum(1 for c in s.state.cards.values() if c.zone == "p1:hand"), life(s, "p1")
    if craft:
        mana(s, R=1, C=2)
        act(s, "p1", type="activate_ability", card_id=idol.id, ability=2, cost_choices=[{"component": 2, "cards": [gnome.id]}])
    else:
        act(s, "p1", type="move", card_ids=[gnome.id], to={"zone": "exile"})
    drive(s)
    assert zone_of(s, "Market Gnome") == "p1:exile"
    assert (life(s, "p1") == life0 + 1) is craft and (sum(1 for c in s.state.cards.values() if c.zone == "p1:hand") == hand0 + 1) is craft
    check(s)


@pytest.mark.parametrize(("pick", "sacrificed", "discarded", "bob_life"), [("sacrifice", True, False, 40), ("discard", False, True, 40), ("neither", False, False, 38)])
def test_osseous_sticktwister_each_opponent_sacrifices_discards_or_takes_damage(cards, pick, sacrificed, discarded, bob_life):
    s = build(cards, ["Osseous Sticktwister", "Grizzly Bears", "Murder", "Smuggler's Copter"], ["Grizzly Bears", "Murder"], forests=30, islands=40)
    put(s, "Osseous Sticktwister")
    for name in ("Grizzly Bears", "Murder", "Smuggler's Copter", "Forest"):  # creature, instant, artifact, land: four card types (delirium)
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "graveyard"})
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Murder", "p2")
    to_phase(s, "main2", turn=1)
    for _ in range(6):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    want = {"sacrifice": "pay:0", "discard": "pay:1", "neither": "decline"}[pick]
    drive(s, lambda d: [want] if want in [o.id for o in d.options] else None)  # (a sacrificed permanent is the only one: chosen for them)
    assert (zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard") is sacrificed
    assert (zone_of(s, "Murder", "p2") == "p2:graveyard") is discarded
    assert life(s, "p2") == bob_life  # 2 damage = its power (608.2h), only to an opponent who did neither
    check(s)


def test_osseous_sticktwister_needs_delirium(cards):
    s = build(cards, ["Osseous Sticktwister", "Grizzly Bears", "Murder", "Smuggler's Copter"], ["Grizzly Bears"], forests=30, islands=40)
    put(s, "Osseous Sticktwister")
    for name in ("Grizzly Bears", "Murder", "Smuggler's Copter"):  # three card types only
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "graveyard"})
    to_phase(s, "main2", turn=1)
    for _ in range(6):
        assert s.state.rules.decision is None
        if s.state.turn.number == 2:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.number == 2 and life(s, "p2") == 40


def jace_table(cards, lands, pays):
    """Alice's Jace; Bob (with ``lands`` Islands) is at the beginning of combat in his turn: he pays {2} or not, and then declares attackers."""
    s = build(cards, ["Jace, Multiverse Architect"], ["Grizzly Bears"], forests=30, islands=40)
    mana(s, W=1, U=1, B=1, R=1, C=1)
    cast(s, "Jace, Multiverse Architect")
    jace = card_named(s, "Jace, Multiverse Architect")
    bears = put(s, "Grizzly Bears", "p2")
    s.state.rules.controlled_since[bears.id].turn = 0
    to_phase(s, "main1", turn=2)
    islands = [c.id for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library"][:lands]
    if islands:
        act(s, "p2", type="move", card_ids=islands, to={"player": "p2", "zone": "battlefield"})
    act(s, "p2", type="set_stops", own=["declare_attackers"], others=[], smart_pass=False)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_one":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay" if pays else "decline"])
        elif d is not None and d.kind == "declare_attackers":
            return s, jace, bears
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no combat")  # pragma: no cover


@pytest.mark.parametrize(("lands", "pays"), [(2, True), (2, False), (1, False), (0, False)])
def test_jace_multiverse_architect_taxes_attacks_on_jaces_only(cards, lands, pays):
    """508.1c, 118.12: unless Bob paid {2} (only possible with two lands), his creatures can't attack Jaces; the player is still open."""
    s, jace, bears = jace_table(cards, lands, pays)
    if not pays:
        with pytest.raises(ActionError, match="can't attack Jace"):
            act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": jace.id}])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": jace.id if pays else "p1"}])
    assert s.state.cards[bears.id].attacking.id == (jace.id if pays else "p1")
    check(s)


def avacyn_game(cards, fetch):
    """Alice casts the Saga on turn 1: chapter I searches for ``fetch``; chapter II (turn 3) turns it up; chapter III (turn 5) puts it onto the battlefield or into her hand."""
    s = build(cards, ["The Creation of Avacyn", fetch], [], forests=30, islands=40)
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "The Creation of Avacyn").id)
    drive(s, lambda d: [o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == fetch] or None)
    return s


@pytest.mark.parametrize(("fetch", "life_lost", "choice", "zone"), [("Shivan Dragon", 6, "battlefield", "p1:battlefield"), ("Shivan Dragon", 6, "hand", "p1:hand"),
                                                                    ("Murder", 0, None, "p1:hand")])
def test_creation_of_avacyn(cards, fetch, life_lost, choice, zone):
    s = avacyn_game(cards, fetch)
    card = card_named(s, fetch)
    assert s.state.cards[card.id].zone == "p1:exile" and s.state.cards[card.id].face_down
    to_phase(s, "main1", turn=3)
    drive(s)
    assert not s.state.cards[card.id].face_down and life(s, "p1") == 40 - life_lost  # chapter II
    to_phase(s, "main1", turn=5)
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[choice])
    assert zone_of(s, fetch) == zone
    check(s)


def extortion_game(cards, payers):
    s = build(cards, ["Temporal Extortion"], [], forests=30, islands=40)
    mana(s, B=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Temporal Extortion").id)
    drive(s, lambda d: ["pay" if d.player in payers else "decline"])  # (every player is asked in turn order: 101.4)
    return s


@pytest.mark.parametrize(("payers", "lives", "countered"), [((), (40, 40), False), (("p1",), (20, 40), True), (("p2",), (40, 20), True), (("p1", "p2"), (20, 20), True)])
def test_temporal_extortion_any_player_may_pay_half_their_life_to_counter_it(cards, payers, lives, countered):
    """118.12, 107.1a: half their life total rounded up (40 -> 20) is paid by each player who chooses to; if any player did, the spell is countered (no extra turn, 701.6a)."""
    s = extortion_game(cards, payers)
    assert (life(s, "p1"), life(s, "p2")) == lives
    assert (zone_of(s, "Temporal Extortion") == "p1:graveyard") is True  # (a resolved or a countered sorcery ends in the graveyard)
    if not countered:
        to_phase(s, "main1", turn=2)
        assert s.state.turn.active_player == "p1"  # the extra turn comes right after this one
    else:
        to_phase(s, "main1", turn=2)
        assert s.state.turn.active_player == "p2"
    check(s)


def test_pay_half_life_rounds_up(cards):
    """107.1a: at 41 life half is 21 when rounded up, so the payer keeps 20."""
    s = build(cards, ["Temporal Extortion"], [], forests=30, islands=40)
    act(s, "p1", type="set_life", player="p2", value=41)
    mana(s, B=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Temporal Extortion").id)
    drive(s, lambda d: ["pay" if d.player == "p2" else "decline"])
    assert life(s, "p2") == 20
