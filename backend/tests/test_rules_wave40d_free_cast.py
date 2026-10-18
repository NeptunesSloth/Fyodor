"""Wave 40D: free-cast and cast-permission wordings (CR 2026-09-25), real Oracle text (tests/fixtures/wave40d_cards.json, from data/cards.sqlite). Every
scenario checks the replay and a save and a load.

* 601.3: casting from a graveyard needs a permission; it changes where, never when (normal timing) or what is paid. 400.7: "cards in your graveyard that
  were put there this turn" is read of the object now there (Banon: from anywhere but the battlefield; Kagha: from the library; Raul: milled, 701.17a — a
  card a search or another effect put there from the library is not "milled", the Raul ruling 2024-03-08).
* 608.2g / 118.9: "cast … without paying its mana cost" as an ability resolves; X is 0 (107.3b); 107.3c: "mana value X or less, where X is …" reads its
  count as the spell is chosen.
* 707.12: "exile target noncreature, nonland card … from a graveyard and copy it. You may cast the copy without paying its mana cost." (Narset, Enlightened Exile).
* 611.2a: "Until end of turn, you may cast noncreature spells from among those cards without paying their mana costs." (Narset, Enlightened Master): a permission
  for each card exiled, with the cast's own timing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.casting import castable
from app.rules.view import hints
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave30h_linked_exile import put_in, settle, stack_top, to_turn, zone  # noqa: F401
from tests.test_rules_wave30q_cast_permissions import castable_now, grave, refused
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand
from tests.wave9c_kit import reloaded as reloaded_session

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave40d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t40d", number=f"D{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
BANON, KAGHA, RAUL = "Banon, the Returners' Leader", "Kagha, Shadow Archdruid", "Raul, Trouble Shooter"
GANDALF, NARSET_EXILE, NARSET_MASTER = "Gandalf, Party Guest", "Narset, Enlightened Exile", "Narset, Enlightened Master"
NORIN, URZA, MALCOLM = "Norin, Swift Survivalist", "Urza, Lord High Artificer", "Malcolm, Alluring Scoundrel"
EMET = "Emet-Selch, Unsundered // Hades, Sorcerer of Eld"
FULL = [BANON, KAGHA, RAUL, GANDALF, NARSET_EXILE, NARSET_MASTER, NORIN, URZA, MALCOLM, EMET, "Epistolary Librarian", "Apex of Power", "Dream Pillager",
        "Fortune Teller's Talent", "Hazoret's Undying Fury"]


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def to_grave(s, name, via, pid="p1"):
    """Put that card into the graveyard from ``via`` ("hand" | "battlefield" | "library"): the arrival the turn's log keeps (400.7)."""
    if via == "hand":
        to_hand(s, name, pid)
    elif via == "battlefield":
        put(s, name, pid)
    else:
        put_in(s, name, "library", pid, "top")
    act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"player": pid, "zone": "graveyard"})


# ---- Banon, the Returners' Leader ----------------------------------------------------------------------------------------------------------
def test_banon_casts_one_creature_spell_put_into_the_graveyard_from_anywhere_but_the_battlefield(cards):
    """"Once during each of your turns, you may cast a creature spell from among cards in your graveyard that were put there from anywhere other than the
    battlefield this turn." A creature discarded from the hand and one put there from the library qualify; one that died on the battlefield, a noncreature
    card and a creature put there a turn ago do not; the first cast uses the turn's permission up. The cost is paid in full."""
    s = build(cards, [BANON, "Grizzly Bears", "Perilous Myr", "Mulldrifter", "Giant Growth", "Ambush Viper"], ["Grizzly Bears"])
    put(s, BANON)
    to_grave(s, "Ambush Viper", "hand")
    to_turn(s, 3)
    to_grave(s, "Grizzly Bears", "hand")
    to_grave(s, "Perilous Myr", "library")
    to_grave(s, "Mulldrifter", "battlefield")
    to_grave(s, "Giant Growth", "hand")
    mana(s, G=2)
    assert castable_now(s, cards, "Grizzly Bears") and castable_now(s, cards, "Perilous Myr")
    assert not castable_now(s, cards, "Mulldrifter") and not castable_now(s, cards, "Giant Growth") and not castable_now(s, cards, "Ambush Viper")
    refused(s, "Mulldrifter")
    h = hints(s.state, "p1", cards)  # (what the table offers)
    assert {card_named(s, "Grizzly Bears").id, card_named(s, "Perilous Myr").id} <= set(h["castable"])
    assert not {card_named(s, "Mulldrifter").id, card_named(s, "Giant Growth").id} & set(h["castable"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)
    settle(s)
    assert zone(s, "p1", "battlefield").count("Grizzly Bears") == 1 and not castable_now(s, cards, "Perilous Myr")
    check(s)


# ---- Kagha, Shadow Archdruid -----------------------------------------------------------------------------------------------------------------
def test_kagha_plays_a_land_or_casts_a_permanent_spell_put_into_the_graveyard_from_the_library_once_a_turn(cards):
    """"Once during each of your turns, you may play a land or cast a permanent spell from among cards in your graveyard that were put there from your
    library this turn." A land and a creature from the library qualify, a creature put there from the hand and an instant do not; ONE use for either: playing
    the land (which is also the turn's land play, 305.2) uses it up, and the creature can't be cast then."""
    s = build(cards, [KAGHA, "Command Tower", "Grizzly Bears", "Mulldrifter", "Giant Growth"], ["Grizzly Bears"])
    put(s, KAGHA)
    to_grave(s, "Command Tower", "library")
    to_grave(s, "Grizzly Bears", "library")
    to_grave(s, "Giant Growth", "library")
    to_grave(s, "Mulldrifter", "hand")
    mana(s, G=2)
    assert castable_now(s, cards, "Grizzly Bears") and not castable_now(s, cards, "Mulldrifter") and not castable_now(s, cards, "Giant Growth")
    act(s, "p1", type="play_land", card_id=card_named(s, "Command Tower").id)
    assert zone(s, "p1", "battlefield").count("Command Tower") == 1
    assert not castable_now(s, cards, "Grizzly Bears")  # (the one use is gone)
    refused(s, "Grizzly Bears")
    check(s)


def test_kagha_casts_the_creature_and_then_cant_play_the_land(cards):
    s = build(cards, [KAGHA, "Command Tower", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, KAGHA)
    to_grave(s, "Command Tower", "library")
    to_grave(s, "Grizzly Bears", "library")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)
    settle(s)
    assert zone(s, "p1", "battlefield").count("Grizzly Bears") == 1
    with pytest.raises(Exception):  # noqa: B017  (ActionError: the permission is used up)
        act(s, "p1", type="play_land", card_id=card_named(s, "Command Tower").id)
    check(s)


# ---- Raul, Trouble Shooter -------------------------------------------------------------------------------------------------------------------
def test_raul_casts_a_milled_card_not_one_another_effect_put_there_from_the_library(cards):
    """"Once during each of your turns, you may cast a spell from among cards in your graveyard that were milled this turn." Raul's own {T} mills a card
    for each player: the Grizzly Bears milled qualifies; a Perilous Myr put into the graveyard from the library by another effect (here a move, as a
    search would) was not milled, and Bob's milled card is in Bob's graveyard. One cast a turn; a card milled last turn can't be cast."""
    s = build(cards, [RAUL, "Grizzly Bears", "Perilous Myr", "Giant Growth"], ["Grizzly Bears", "Murder"])
    put(s, RAUL)
    to_grave(s, "Perilous Myr", "library")
    to_turn(s, 3)
    stack_top(s, ["Grizzly Bears", "Giant Growth"])
    stack_top(s, ["Murder"], "p2")
    act(s, "p1", type="activate_ability", card_id=card_named(s, RAUL).id, ability=1)
    settle(s)
    assert "Grizzly Bears" in zone(s, "p1", "graveyard") and "Murder" in zone(s, "p2", "graveyard")
    to_grave(s, "Perilous Myr", "library")
    mana(s, G=2, B=3)
    assert castable_now(s, cards, "Grizzly Bears") and not castable_now(s, cards, "Perilous Myr")
    assert not castable(s.state, "p1", card_named(s, "Murder", "p2"), cards, check_priority=False)  # (Bob's graveyard: "your graveyard")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)
    settle(s)
    assert zone(s, "p1", "battlefield").count("Grizzly Bears") == 1
    check(s)


# ---- Gandalf, Party Guest ----------------------------------------------------------------------------------------------------------------------
def combat_choice(s):
    """Pass priority from the first main phase into the beginning of combat, where the free-cast question waits."""
    for _ in range(4):
        act(s, "p1", type="pass_priority")
        d = s.state.rules.decision
        if d is not None:
            return d
    raise AssertionError("never asked")


def choose(s, *option_ids):
    d = s.state.rules.decision
    assert d is not None, "nothing was asked"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(option_ids))


def gandalf_game(cards, extra=()):
    s = build(cards, [GANDALF, *extra, "Blaze", "Lightning Bolt", "Murder", "Grizzly Bears", "Giant Growth"], ["Grizzly Bears"])
    put(s, GANDALF)
    for n in ("Blaze", "Lightning Bolt", "Murder", "Grizzly Bears", "Giant Growth"):
        to_hand(s, n)
    return s


def test_gandalf_offers_spells_up_to_twice_the_legendary_wizards_and_none_may_be_chosen(cards):
    """"…mana value X or less from your hand without paying its mana cost, where X is twice the number of legendary Wizards you control." Alone, Gandalf (a
    legendary Wizard) makes X 2: Blaze (1), Lightning Bolt and Giant Growth qualify, Murder (3) and the creature don't. Declining casts nothing."""
    s = gandalf_game(cards)
    d = combat_choice(s)
    assert d.kind == "choose_cards" and sorted(o.label for o in d.options) == ["Blaze", "Giant Growth", "Lightning Bolt"]
    s = reloaded_session(s)
    choose(s)  # (none)
    assert s.state.rules.decision is None and zone(s, "p1", "hand").count("Blaze") == 1 and not s.state.zones.get("stack")
    assert s.state.players["p2"].life == 40
    check(s)


def test_gandalf_counts_its_legendary_wizards_as_the_spell_is_chosen_and_a_blaze_has_x_0(cards):
    """A second legendary Wizard (Lim-Dûl) makes X 4, so Murder (3) is offered too. Blaze (X damage to any target) cast this way has X 0 (107.3b, the Gandalf ruling 2026-06-29):
    it is on the stack with X 0 and deals no damage (Bob stays at 40)."""
    s = gandalf_game(cards, ["Lim-Dûl the Necromancer"])
    put(s, "Lim-Dûl the Necromancer")
    d = combat_choice(s)
    assert sorted(o.label for o in d.options) == ["Blaze", "Giant Growth", "Lightning Bolt", "Murder"]
    blaze = card_named(s, "Blaze")
    choose(s, blaze.id)
    d = s.state.rules.decision
    assert d is not None and d.kind in ("choose_targets", "choose_cards", "choose_one")
    choose(s, "p2")
    settle(s)  # (Alice has no mana at all: the cast paid nothing, and Blaze's X is 0)
    assert s.state.players["p2"].life == 40 and card_named(s, "Blaze").zone == "p1:graveyard" and "Blaze" not in zone(s, "p1", "hand")
    assert zone(s, "p1", "hand").count("Murder") == 1 and not s.state.zones.get("stack")
    check(s)


def test_epistolary_librarian_limit_is_the_number_of_attacking_creatures(cards):
    """"…a spell with mana value X or less from your hand without paying its mana cost, where X is the number of attacking creatures." Two attackers make X 2
    (the Bolt, 1, is offered; the Murder, 3, and the Mulldrifter, 5, are not); the count is the one as the ability resolves (107.3c)."""
    s = build(cards, ["Epistolary Librarian", "Grizzly Bears", "Murder", "Lightning Bolt", "Mulldrifter"], ["Grizzly Bears"])
    put(s, "Epistolary Librarian")
    put(s, "Grizzly Bears")
    for n in ("Murder", "Lightning Bolt", "Mulldrifter"):
        to_hand(s, n)
    to_turn(s, 3)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, n).id, "target": "p2"} for n in ("Epistolary Librarian", "Grizzly Bears")])
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and sorted(o.label for o in d.options) == ["Lightning Bolt"], d
    s = reloaded_session(s)
    choose(s, card_named(s, "Lightning Bolt").id)
    choose(s, "p2")
    settle(s)
    assert zone(s, "p1", "graveyard") == ["Lightning Bolt"] and "Murder" in zone(s, "p1", "hand")
    check(s)


def test_a_free_cast_whose_optional_additional_cost_cant_be_paid_is_the_plain_one(cards):
    """Was a pinned limit (wave 40D: a free cast was never asked about kicker, bargain, gift, casualty …). Wave 41D lifts it (118.9d, 601.2b:
    tests/test_rules_wave41d_free_cast_optional.py asks the caster): Alice has no mana for Burst Lightning's {4}, so no kicker is offered, nothing is asked
    and Burst Lightning cast through Gandalf is the unkicked one (2 damage, not 4)."""
    s = build(cards, [GANDALF, "Burst Lightning"], ["Grizzly Bears"])
    put(s, GANDALF)
    to_hand(s, "Burst Lightning")
    combat_choice(s)
    choose(s, card_named(s, "Burst Lightning").id)
    choose(s, "p2")
    settle(s)
    assert s.state.players["p2"].life == 38 and s.state.rules.decision is None
    check(s)


# ---- Narset, Enlightened Exile ---------------------------------------------------------------------------------------------------------------
def narset_attack(cards):
    """Narset (power 3) attacks on turn 3 with Blaze (mana value 1), Murder (3) and a Grizzly Bears in graveyards."""
    s = build(cards, [NARSET_EXILE, "Blaze", "Murder", "Grizzly Bears"], ["Lightning Bolt"])
    put(s, NARSET_EXILE)
    grave(s, "Blaze", "Murder", "Grizzly Bears")
    grave(s, "Lightning Bolt", pid="p2")
    to_turn(s, 3)
    act(s, "p1", type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_attackers", d
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, NARSET_EXILE).id, "target": "p2"}])
    return s


def test_narset_exiles_a_card_with_mana_value_below_her_power_and_casts_its_copy_with_x_0(cards):
    """"exile target noncreature, nonland card with mana value less than Narset's power from a graveyard and copy it" — her power is 3: Blaze (1) and
    Lightning Bolt (1, Bob's graveyard) are targets, Murder (3) and the creature are not (the "and copy it" wording used to stop at the comma). The copy is
    cast as the ability resolves for {0}: X is 0 (the Narset ruling 2023-05-12), and the exiled card stays exiled."""
    s = narset_attack(cards)
    d = s.state.rules.decision
    assert d is not None and d.kind in ("choose_targets", "choose_cards", "choose_one"), d
    assert sorted(o.label for o in d.options) == ["Blaze", "Lightning Bolt"]
    choose(s, card_named(s, "Blaze").id)
    d = s.state.rules.decision
    assert d is not None and [o.label for o in d.options] == ["Blaze"], d  # (the copy: "cast it?" — one at a time, or none)
    s = reloaded_session(s)
    choose(s, d.options[0].id)
    choose(s, "p2")
    settle(s)
    assert [(c.before, c.after) for c in s.state.players["p2"].life_history] == [(40, 36)]  # (only Narset's combat damage, 4 with prowess: the copy's X was 0)
    assert zone(s, "p1", "exile") == ["Blaze"] and "Blaze" not in zone(s, "p1", "graveyard")
    assert zone(s, "p1", "graveyard") == ["Grizzly Bears", "Murder"]
    check(s)


# ---- Narset, Enlightened Master --------------------------------------------------------------------------------------------------------------
def test_narset_master_may_cast_any_number_of_the_exiled_noncreature_spells_free_this_turn(cards):
    """"Whenever Narset attacks, exile the top four cards of your library. Until end of turn, you may cast noncreature spells from among those cards without
    paying their mana costs." Each exiled card gets its own permission (611.2a): the Bolt and the Pyroclasm (a sorcery, cast in the postcombat main phase: normal timing) are
    cast (any number), the creature never; nothing is paid. At the end of the turn the permission is over: the Giant Growth left in exile can't be cast later."""
    top = ["Lightning Bolt", "Grizzly Bears", "Giant Growth", "Pyroclasm"]
    s = build(cards, [NARSET_MASTER, *top], ["Grizzly Bears"])
    put(s, NARSET_MASTER)
    to_turn(s, 3)
    stack_top(s, top)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, NARSET_MASTER).id, "target": "p2"}])
    settle(s)
    assert zone(s, "p1", "exile") == sorted(top)
    s = reloaded_session(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id, free=True)  # (a creature spell: not from among these)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, free=True, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Pyroclasm").id, free=True)  # (a sorcery, at sorcery speed: the postcombat main phase)
    settle(s)
    assert zone(s, "p1", "graveyard") == sorted([NARSET_MASTER, "Lightning Bolt", "Pyroclasm"])  # (the Pyroclasm killed Narset, too)
    assert zone(s, "p1", "exile") == ["Giant Growth", "Grizzly Bears"]
    assert s.state.players["p2"].life == 40 - 3 - 3  # (Narset's combat damage 3 and the Bolt's 3; no mana was spent)
    check(s)
    to_turn(s, 5)
    put(s, "Grizzly Bears", "p2")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Giant Growth").id, free=True, targets=[card_named(s, "Grizzly Bears", "p2").id])  # (over)
    check(s)


# ---- Norin, Swift Survivalist ----------------------------------------------------------------------------------------------------------------
def norin_blocked(cards):
    """Turn 3: Alice's Grizzly Bears attacks, Bob's Grizzly Bears blocks it, and Norin's "you may exile it?" is asked."""
    s = build(cards, [NORIN, "Grizzly Bears", "Mulldrifter"], ["Grizzly Bears"])
    put(s, NORIN)
    put(s, "Grizzly Bears")
    put(s, "Grizzly Bears", "p2")
    to_turn(s, 3)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, "Grizzly Bears").id, "target": "p2"}])
    d = s.state.rules.decision
    while d is None or d.kind != "declare_blockers":
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": card_named(s, "Grizzly Bears", "p2").id, "attacker_id": card_named(s, "Grizzly Bears").id}])
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} >= {"yes", "no"}, d
    return reloaded_session(s)


def test_norin_exiles_a_blocked_creature_and_plays_it_from_exile_this_turn_only(cards):
    """"Whenever a creature you control becomes blocked, you may exile it. You may play that card from exile this turn." The card exiled can be cast, paying
    its cost, in the postcombat main phase (the Norin ruling 2024-09-20: normal timing); a card not cast stays in exile, and next turn it can't be cast."""
    s = norin_blocked(cards)
    choose(s, "yes")
    settle(s)
    assert zone(s, "p1", "exile") == ["Grizzly Bears"]
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)
    settle(s)
    assert zone(s, "p1", "battlefield").count("Grizzly Bears") == 1 and zone(s, "p1", "exile") == []
    check(s)


def test_norin_a_card_left_in_exile_cant_be_played_on_a_later_turn_and_a_declined_exile_grants_nothing(cards):
    s = norin_blocked(cards)
    choose(s, "yes")
    settle(s)
    to_turn(s, 5)
    mana(s, G=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)  # ("this turn": over)
    check(s)
    s = norin_blocked(cards)
    choose(s, "no")
    settle(s)
    assert zone(s, "p1", "exile") == [] and zone(s, "p1", "graveyard").count("Grizzly Bears") <= 1
    check(s)


# ---- Urza, Lord High Artificer ---------------------------------------------------------------------------------------------------------------
def urza_game(cards, top):
    s = build(cards, [URZA, top, "Giant Growth"], ["Grizzly Bears"], forests=0)  # (a library of one card: the shuffle can't change which is on top)
    put(s, URZA)
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Giant Growth")
    mana(s, C=5)
    act(s, "p1", type="activate_ability", card_id=card_named(s, URZA).id, ability=2)
    settle(s)
    put_in(s, "Giant Growth", "library")  # (so that she has a card to draw on her next turn)
    return s


def test_urza_shuffles_exiles_the_top_card_and_may_play_it_free_until_end_of_turn(cards):
    """"{5}: Shuffle your library, then exile the top card. Until end of turn, you may play that card without paying its mana cost." The spell exiled is cast
    free (118.9, with a target chosen as for any cast); it is a permission for that object this turn only, so a card not cast stays in exile for good."""
    s = urza_game(cards, "Murder")
    assert zone(s, "p1", "exile") == ["Murder"] and s.state.players["p1"].mana.get("C", 0) == 0
    s = reloaded_session(s)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, free=True, targets=[card_named(s, "Grizzly Bears", "p2").id])
    settle(s)
    assert zone(s, "p1", "graveyard") == ["Murder"] and zone(s, "p2", "graveyard") == ["Grizzly Bears"]
    check(s)


def test_urza_plays_an_exiled_land_free_and_a_card_not_cast_is_lost_next_turn(cards):
    s = urza_game(cards, "Command Tower")
    act(s, "p1", type="play_land", card_id=card_named(s, "Command Tower").id)
    assert zone(s, "p1", "battlefield").count("Command Tower") == 1
    check(s)
    s = urza_game(cards, "Murder")
    to_turn(s, 3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, free=True, targets=[card_named(s, "Grizzly Bears", "p2").id])
    check(s)


# ---- Malcolm, Alluring Scoundrel -------------------------------------------------------------------------------------------------------------
def malcolm_hits(cards, counters):
    """Malcolm (with ``counters`` chorus counters) connects on turn 3: draw a card, then discard one — the Lightning Bolt — and the free cast may be asked."""
    s = build(cards, [MALCOLM, "Lightning Bolt", "Murder"], ["Grizzly Bears"])
    put(s, MALCOLM)
    act(s, "p1", type="counter", card_ids=[card_named(s, MALCOLM).id], kind="chorus", delta=counters)
    to_hand(s, "Lightning Bolt")
    to_hand(s, "Murder")
    to_turn(s, 3)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, MALCOLM).id, "target": "p2"}])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards" and any(o.card_id == card_named(s, "Lightning Bolt").id for o in d.options):
            return s, d
        act(s, s.state.rules.priority, type="pass_priority") if d is None else choose(s, *[o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never asked")


def test_malcolm_casts_the_discarded_card_free_with_four_chorus_counters(cards):
    """"…put a chorus counter on it. Draw a card, then discard a card. If there are four or more chorus counters on Malcolm, you may cast the discarded card
    without paying its mana cost." With three counters the new one makes four: the Lightning Bolt discarded is cast for {0}."""
    s, d = malcolm_hits(cards, 3)
    choose(s, card_named(s, "Lightning Bolt").id)  # (discard it)
    d = s.state.rules.decision
    assert d is not None and [o.label for o in d.options] == ["Lightning Bolt"], d
    s = reloaded_session(s)
    choose(s, d.options[0].id)
    choose(s, "p2")
    settle(s)
    assert zone(s, "p1", "graveyard") == ["Lightning Bolt"] and s.state.players["p2"].life == 40 - 2 - 3  # (Malcolm is a 2/2; the Bolt costs nothing)
    check(s)


def test_malcolm_with_fewer_than_four_counters_just_discards(cards):
    s, d = malcolm_hits(cards, 2)
    choose(s, card_named(s, "Lightning Bolt").id)
    settle(s)
    assert zone(s, "p1", "graveyard") == ["Lightning Bolt"] and s.state.players["p2"].life == 38
    assert s.state.rules.decision is None
    check(s)


# ---- Emet-Selch, Unsundered // Hades, Sorcerer of Eld ----------------------------------------------------------------------------------------
def test_hades_plays_cards_from_the_graveyard_during_its_controllers_turn(cards):
    """"During your turn, you may play cards from your graveyard." — lands and spells (305.1, 601.1), paying everything and keeping the land drop. Not on
    Bob's turn, and not Bob's cards from Bob's graveyard."""
    s = build(cards, [EMET, "Grizzly Bears", "Command Tower", "Giant Growth"], ["Grizzly Bears"])
    grave(s, "Grizzly Bears", "Command Tower", "Giant Growth")
    put(s, EMET)
    act(s, "p1", type="set_face", card_id=card_named(s, EMET).id, face=1)  # (Hades, Sorcerer of Eld)
    grave(s, "Grizzly Bears", pid="p2")
    mana(s, G=2)
    assert castable_now(s, cards, "Grizzly Bears")
    assert not castable(s.state, "p1", card_named(s, "Grizzly Bears", "p2"), cards, check_priority=False)
    s = reloaded_session(s)
    act(s, "p1", type="play_land", card_id=card_named(s, "Command Tower").id)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)
    settle(s)
    assert zone(s, "p1", "battlefield").count("Grizzly Bears") == 1 and zone(s, "p1", "battlefield").count("Command Tower") == 1
    check(s)
    to_turn(s, 2)
    mana(s, G=1)
    assert not castable_now(s, cards, "Giant Growth")  # ("During your turn": an instant, with the mana, on Bob's turn)
    to_turn(s, 3)
    mana(s, G=1)
    assert castable_now(s, cards, "Giant Growth")
    check(s)


# ---- Fortune Teller's Talent (Level 2 reads "play cards from the top of your library") ------------------------------------------------------
def test_fortune_teller_talent_level_2_plays_the_top_card_only_after_a_spell_was_cast_this_turn(cards):
    """"As long as you've cast a spell this turn, you may play cards from the top of your library." (611.3a: read afresh each time the top card is looked at;
    the level 1 line lets its controller look at it.) Lands too: before any spell this turn the Command Tower on top can't be played, after a Sol Ring it can."""
    from tests.test_rules_wave16a_class import bar

    s = build(cards, ["Fortune Teller's Talent", "Sol Ring", "Command Tower"], ["Grizzly Bears"])
    talent = put(s, "Fortune Teller's Talent")
    mana(s, U=1, C=3)
    act(s, "p1", type="activate_ability", card_id=talent.id, ability=bar(s, talent, 2))
    settle(s)
    stack_top(s, ["Command Tower"])
    to_hand(s, "Sol Ring")
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=card_named(s, "Command Tower").id)  # (no spell cast yet this turn)
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Sol Ring").id)
    settle(s)
    s = reloaded_session(s)
    act(s, "p1", type="play_land", card_id=card_named(s, "Command Tower").id)
    assert zone(s, "p1", "battlefield").count("Command Tower") == 1
    check(s)


# ---- Hazoret's Undying Fury ------------------------------------------------------------------------------------------------------------------
def test_hazorets_undying_fury_shuffles_exiles_four_and_casts_any_number_up_to_mana_value_5_free(cards):
    """"Shuffle your library, then exile the top four cards. You may cast any number of spells with mana value 5 or less from among them without paying their
    mana costs. Lands you control don't untap during your next untap step." (the sorcery's rulings 2017-07-14: each spell must be 5 or less, the lands stay
    tapped through that one untap step only). The Twisted Abomination (6) is never offered; the Murder is left uncast."""
    s = build(cards, ["Hazoret's Undying Fury", "Lightning Bolt", "Frogmite", "Twisted Abomination", "Murder", "Giant Growth", "Opt", *["Mountain"] * 6],
              ["Grizzly Bears"], forests=0)
    for n in ("Giant Growth", "Opt"):
        to_hand(s, n)
    to_hand(s, "Hazoret's Undying Fury")
    lands = [c for c in s.state.cards.values() if c.name == "Mountain" and c.owner == "p1"]
    for c in lands:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    assert sorted(zone(s, "p1", "library")) == ["Frogmite", "Lightning Bolt", "Murder", "Twisted Abomination"]
    put(s, "Grizzly Bears", "p2")  # (so that the Murder has a target: without one it can't be cast, 601.2c, and isn't offered)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Hazoret's Undying Fury").id)
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and sorted(o.label for o in d.options) == ["Frogmite", "Lightning Bolt", "Murder"], d
    assert all(s.state.cards[c.id].tapped for c in lands)
    s = reloaded_session(s)
    choose(s, card_named(s, "Lightning Bolt").id)
    choose(s, "p2")
    d = s.state.rules.decision
    assert d is not None and sorted(o.label for o in d.options) == ["Frogmite", "Murder"], d  # (one at a time, 608.2g)
    choose(s, card_named(s, "Frogmite").id)
    choose(s)  # (none of the rest)
    settle(s)
    assert zone(s, "p1", "battlefield").count("Frogmite") == 1 and s.state.players["p2"].life == 37
    assert sorted(zone(s, "p1", "exile")) == ["Murder", "Twisted Abomination"]
    for n in ("Giant Growth", "Opt"):  # (cards to draw on her next two turns)
        put_in(s, n, "library")
    check(s)
    to_turn(s, 3)
    assert all(s.state.cards[c.id].tapped for c in lands)  # (the untap step skipped them)
    to_turn(s, 5)
    assert not any(s.state.cards[c.id].tapped for c in lands)
    check(s)
