"""Review 52b: cards wave 52 made FULL as side effects of its grammar changes, which no test named, played with real Oracle text (tests/fixtures/review52b_cards.json,
from data/cards.sqlite) against their rulings. Every scenario checks the replay and a save and a load.

* Bala Ged Thief, Disciple of Phenax, Klaw: "target player reveals a number of cards from their hand equal to N" — N read as the ability resolves (the rulings of
  2009-10-01, 2013-09-15: the Thief's Allies, the Disciple's devotion with itself), the player picks which cards to show, you choose one, it is discarded.
* Case of the Filched Falcon, Case of the Shattered Pact: "When this Case enters, …"; the Falcon's solved ability (its counters and a 0/0 Bird with no duration).
* Cauldron Haze: persist until end of turn on the chosen targets (702.79a).
* Duskmantle Guildmage: each resolution makes its own delayed trigger (ruling 2013-01-24), each opponent's graveyard, not yours.
* From the Catacombs: the creature returned is exiled if it would leave (614.1a); the sorcery escapes from the graveyard and goes back there (702.138a).
* Nurturing Pixie: the counter only if a permanent was returned. Rise of the Deathbringer: life lost equal to the cards drawn (121.2).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, next_turn
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "review52b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r52b", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
NAMES = ["Bala Ged Thief", "Disciple of Phenax", "Klaw, Sonic Subjugator", "Case of the Filched Falcon", "Case of the Shattered Pact", "Cauldron Haze",
         "Duskmantle Guildmage", "From the Catacombs", "Nurturing Pixie", "Rise of the Deathbringer"]
HAND = ["Grizzly Bears", "Opt", "Hill Giant", "Murder"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def settle(s, answer=None, limit=80):
    """Pass priority until the stack is empty; a decision is answered with ``answer(d)`` (option ids) when it gives some, else with its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            picked = answer(d) if answer is not None else None
            act(s, d.player, type="choose", decision_id=d.id, option_ids=picked if picked is not None else [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def names(s, ids):
    return sorted(s.state.cards[i].name for i in ids)


@pytest.mark.parametrize("name", NAMES)
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


# -- reveal N cards from hand ----------------------------------------------------------------------------------------------------------------------
def reveal_and_discard(cards, spell, mana_paid, setup=lambda s: None):
    """Bob holds HAND; Alice casts ``spell`` (its trigger aimed at Bob). Returns (session, how many Bob was asked to show, what Alice chose among)."""
    s = build(cards, [spell, "Kazandu Blademaster", "Grizzly Bears", "Hill Giant"], HAND)
    for n in HAND:
        to_hand(s, n, "p2")
    setup(s)
    to_hand(s, spell)
    mana(s, "p1", **mana_paid)
    act(s, "p1", type="cast_spell", card_id=card_named(s, spell).id)
    seen = {}

    def answer(d):
        ids = [o.id for o in d.options]
        if "p2" in ids:
            return ["p2"]
        if d.player == "p2":
            seen["shown"] = d.min_choices
            return ids[: d.min_choices]
        if all(i in s.state.cards and s.state.cards[i].zone == "p2:hand" for i in ids):
            seen["among"] = names(s, ids)
            return ids[:1]
        return None
    settle(s, answer)
    return s, seen


def test_bala_ged_thief_counts_the_allies_as_it_resolves(cards):
    s, seen = reveal_and_discard(cards, "Bala Ged Thief", {"B": 1, "C": 3}, lambda s: put(s, "Kazandu Blademaster"))
    assert seen["shown"] == 2 and len(seen["among"]) == 2  # the Thief and the Blademaster: two Allies, two of Bob's four cards shown, Bob's pick
    assert len(s.state.zones["p2:hand"]) == 3 and len(s.state.zones["p2:graveyard"]) == 1
    check(s)


def test_disciple_of_phenax_counts_its_own_black_symbols(cards):
    s, seen = reveal_and_discard(cards, "Disciple of Phenax", {"B": 2, "C": 2})
    assert seen["shown"] == 2 and len(s.state.zones["p2:hand"]) == 3  # devotion to black 2: {2}{B}{B}, the Disciple's own (ruling 2013-09-15)
    check(s)


def test_klaw_one_plus_the_creature_cards_in_your_graveyard(cards):
    def two_dead(s):
        for n in ("Grizzly Bears", "Hill Giant"):
            act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"zone": "graveyard"})
    s, seen = reveal_and_discard(cards, "Klaw, Sonic Subjugator", {"B": 1, "C": 2}, two_dead)
    assert seen["shown"] == 3 and len(s.state.zones["p2:hand"]) == 3
    check(s)


def test_a_number_above_the_hand_shows_it_whole(cards):
    def big(s):
        put(s, "Kazandu Blademaster")
        for n in HAND[1:]:
            act(s, "p2", type="move", card_ids=[card_named(s, n, "p2").id], to={"zone": "graveyard"})
    s, seen = reveal_and_discard(cards, "Bala Ged Thief", {"B": 1, "C": 3}, big)
    assert "shown" not in seen and seen["among"] == ["Grizzly Bears"]  # one card, two Allies: the whole hand, nothing asked of Bob (ruling 2009-10-01)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    check(s)


# -- the Cases --------------------------------------------------------------------------------------------------------------------------------------
def test_filched_falcon_investigates_solves_and_makes_a_permanent_4_4_flier(cards):
    s = build(cards, ["Case of the Filched Falcon", "Mind Stone", "Ornithopter"])
    put(s, "Mind Stone")
    put(s, "Ornithopter")
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Case of the Filched Falcon").id)
    settle(s)
    assert [c.name for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"] == ["Clue"]  # three artifacts now
    next_turn(s)  # (solved at the end step: 719.3a)
    case = card_named(s, "Case of the Filched Falcon")
    assert "Solved" in s.state.cards[case.id].choices
    stone = card_named(s, "Mind Stone")
    mana(s, "p1", U=1, C=2)
    activate(s, "p1", case, "Sacrifice", targets=[stone.id])
    settle(s)
    assert zone_of(s, "Case of the Filched Falcon") == "p1:graveyard" and pt(s, "Mind Stone") == (4, 4)
    next_turn(s)  # no duration: still a 4/4 flying Bird artifact creature
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[stone.id])
    assert ch.is_creature and "Bird" in ch.subtypes and "Artifact" in ch.types and "flying" in ch.keywords and pt(s, "Mind Stone") == (4, 4)
    check(s)


def test_shattered_pact_finds_a_basic_land_as_it_enters(cards):
    s = build(cards, ["Case of the Shattered Pact"])
    mana(s, "p1", C=2)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Case of the Shattered Pact").id)
    settle(s, lambda d: [next(o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == "Forest")]
           if any(o.card_id and s.state.cards[o.card_id].name == "Forest" for o in d.options) else None)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (the Forest)
    assert any(s.state.cards[c].name == "Forest" for c in s.state.zones["p1:hand"])
    check(s)


# -- Cauldron Haze ------------------------------------------------------------------------------------------------------------------------------------
def test_cauldron_haze_a_target_that_dies_this_turn_comes_back_with_a_counter(cards):
    s = build(cards, ["Cauldron Haze", "Grizzly Bears", "Hill Giant", "Murder"])
    bears, giant = put(s, "Grizzly Bears"), put(s, "Hill Giant")
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Cauldron Haze").id, targets=[bears.id, giant.id], target_counts=[2])
    settle(s)
    mana(s, "p1", B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[bears.id])
    settle(s)
    back = s.state.cards[bears.id]
    assert back.zone == "p1:battlefield" and back.counters.get("-1/-1") == 1 and pt(s, "Grizzly Bears") == (1, 1)
    check(s)


# -- Duskmantle Guildmage -------------------------------------------------------------------------------------------------------------------------------
def test_duskmantle_guildmage_each_activation_its_own_trigger_opponents_only(cards):
    s = build(cards, ["Duskmantle Guildmage"])
    guildmage = put(s, "Duskmantle Guildmage")
    for _ in range(2):
        mana(s, "p1", U=1, B=1, C=1)
        activate(s, "p1", guildmage, "Whenever")
        settle(s)
    next_turn(s)  # (the delayed abilities ended with the turn: nothing happens now)
    mana(s, "p1", U=1, B=1, C=2)
    activate(s, "p1", guildmage, "mills", targets=["p2"])
    settle(s)
    assert life(s, "p2") == 40
    for _ in range(2):
        mana(s, "p1", U=1, B=1, C=1)
        activate(s, "p1", guildmage, "Whenever")
        settle(s)
    for target in ("p2", "p1"):
        mana(s, "p1", U=1, B=1, C=2)
        activate(s, "p1", guildmage, "mills", targets=[target])
        settle(s)
    assert life(s, "p2") == 40 - 4 and life(s, "p1") == 40  # two cards, two delayed abilities: 4 (ruling 2013-01-24); Alice's own graveyard: nothing
    check(s)


# -- From the Catacombs -----------------------------------------------------------------------------------------------------------------------------
def test_from_the_catacombs_reanimates_an_opponents_creature_which_is_exiled_when_it_leaves(cards):
    s = build(cards, ["From the Catacombs", "Murder"], ["Grizzly Bears"])
    bears = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    mana(s, "p1", B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "From the Catacombs").id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[bears.id].controller == "p1"
    assert s.state.cards[bears.id].counters.get("corpse") == 1 and s.state.table.initiative == "p1"
    assert zone_of(s, "From the Catacombs") == "p1:graveyard"
    mana(s, "p1", B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:exile"  # "exile it instead of putting it anywhere else"
    check(s)


def test_from_the_catacombs_escapes_and_goes_back_to_the_graveyard(cards):
    s = build(cards, ["From the Catacombs", "Opt", "Murder", "Hill Giant", "Mind Stone", "Ornithopter"], ["Grizzly Bears"])
    bears = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    for n in ("From the Catacombs", "Opt", "Murder", "Hill Giant", "Mind Stone", "Ornithopter"):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"zone": "graveyard"})
    mana(s, "p1", B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "From the Catacombs").id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    assert zone_of(s, "From the Catacombs") == "p1:graveyard" and len(s.state.zones["p1:exile"]) == 5  # (702.138a: not exiled; five others paid)
    check(s)


# -- Nurturing Pixie ---------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bounce", [True, False])
def test_nurturing_pixie_a_counter_only_if_a_permanent_was_returned(cards, bounce):
    s = build(cards, ["Nurturing Pixie", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    mana(s, "p1", W=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Nurturing Pixie").id)
    settle(s, lambda d: ([bears.id] if bounce else []) if bears.id in [o.id for o in d.options] else None)
    assert zone_of(s, "Grizzly Bears") == ("p1:hand" if bounce else "p1:battlefield")
    assert s.state.cards[card_named(s, "Nurturing Pixie").id].counters.get("+1/+1", 0) == (1 if bounce else 0)
    check(s)


# -- Rise of the Deathbringer ---------------------------------------------------------------------------------------------------------------------------
def test_rise_of_the_deathbringer_loses_life_equal_to_the_cards_drawn(cards):
    s = build(cards, ["Rise of the Deathbringer", "Hill Giant", "Grizzly Bears"])
    put(s, "Hill Giant")
    put(s, "Grizzly Bears")
    hand = len(s.state.zones["p1:hand"])
    mana(s, "p1", B=1, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Rise of the Deathbringer").id, modes=[0])
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand + 3 and life(s) == 37  # the Giant's power 3: three drawn, three life
    check(s)
