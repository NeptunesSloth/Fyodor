"""Wave 22F (casting & costs). Real Oracle text, replay and save/load for each.

* 601.2c / 601.2f: "This spell costs {N} less to cast if it targets …" is read once the targets are chosen.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

EXTRA = [
    real("Seized from Slumber", "{4}{W}", 5, "Instant", "This spell costs {3} less to cast if it targets a tapped creature.\n"
         "Destroy target creature.", None, "W"),
    real("Mystical Dispute", "{2}{U}", 3, "Instant", "This spell costs {2} less to cast if it targets a blue spell.\n"
         "Counter target spell unless its controller pays {3}.", None, "U"),
    real("Vanish into Eternity", "{2}{W}", 3, "Instant", "This spell costs {3} more to cast if it targets a creature.\n"
         "Exile target nonland permanent.", None, "W"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *FLASH, *ORRERY, *LIFE], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_target_cost_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_costs_less_if_it_targets_a_tapped_creature(cards):
    s = build(cards, ["Seized from Slumber"], ["Grizzly Bears", "Grizzly Bears"])
    spell = to_hand(s, "Seized from Slumber")
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"]
    for c in bears:
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p2", type="tap", card_ids=[bears[0].id])
    mana(s, W=1, C=1)  # {4}{W} is out of reach; {1}{W} is the price against a tapped creature
    with pytest.raises(ActionError):  # an untapped target: the full price
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears[1].id])
    assert s.state.cards[spell.id].zone == "p1:hand"  # nothing was paid or moved
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears[0].id])
    answer(s)
    assert s.state.cards[bears[0].id].zone == "p2:graveyard"
    check(s)


def test_costs_less_if_it_targets_a_blue_spell(cards):
    s = build(cards, ["Mystical Dispute", "Lightning Bolt"], ["Opt"])
    dispute, bolt, opt = to_hand(s, "Mystical Dispute"), to_hand(s, "Lightning Bolt"), to_hand(s, "Opt", "p2")
    put(s, "Island", "p2")
    mana(s, U=1, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p2", type="tap", card_ids=[put(s, "Island", "p2").id])
    mana(s, "p2", U=1)
    act(s, "p2", type="cast_spell", card_id=opt.id)  # Bob responds with a blue spell
    with pytest.raises(ActionError):  # a red spell: {2}{U} is out of reach with {U}
        act(s, "p1", type="cast_spell", card_id=dispute.id, targets=[bolt.id])
    act(s, "p1", type="cast_spell", card_id=dispute.id, targets=[opt.id])  # a blue spell: {U}
    answer(s)
    check(s)


def test_costs_more_if_it_targets_a_creature(cards):
    s = build(cards, ["Vanish into Eternity", "Llanowar Elves"], ["Grizzly Bears", "Sol Ring"])
    spell = to_hand(s, "Vanish into Eternity")
    bears, ring = put(s, "Grizzly Bears", "p2"), put(s, "Sol Ring", "p2")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[ring.id])  # not a creature: {2}{W}
    answer(s)
    assert s.state.cards[ring.id].zone == "p2:exile"
    check(s)
    s = build(cards, ["Vanish into Eternity"], ["Grizzly Bears"])
    spell, bears = to_hand(s, "Vanish into Eternity"), put(s, "Grizzly Bears", "p2")
    mana(s, W=1, C=2)
    with pytest.raises(ActionError):  # a creature: {5}{W}
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id])


# -- flash "if …" (601.3b-d) --
FLASH = [
    real("Rout", "{3}{W}{W}", 5, "Sorcery", "You may cast this spell as though it had flash if you pay {2} more to cast it. (You may cast it any time "
         "you could cast an instant.)\nDestroy all creatures. They can't be regenerated.", None, "W"),
    real("Silver Scrutiny", "{X}{U}{U}", 2, "Sorcery", "You may cast this spell as though it had flash if X is 3 or less.\nDraw X cards.", None, "U"),
    real("Flash Photography", "{2}{U}{U}", 4, "Sorcery", "You may cast this spell as though it had flash if it targets a permanent you control.\n"
         "Create a token that's a copy of target permanent.\nFlashback {4}{U}{U}", None, "U"),
]


@pytest.mark.parametrize("name", [c["name"] for c in FLASH if c["name"] != "Rout"])
def test_flash_condition_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_rout_flash_line_is_read(cards):  # (its "can't be regenerated" half is track 22C's, so the card isn't FULL yet)
    feats = {f.id: f.supported for f in coverage.of_card_data(cards.resolve("Rout")).features}
    assert feats["text:0"]


def _stack_busy(s):
    """Alice's Lightning Bolt and Bob's Opt in response are on the stack: Alice has priority again and a sorcery needs flash."""
    bolt, opt = to_hand(s, "Lightning Bolt"), to_hand(s, "Opt", "p2")
    put(s, "Island", "p2")  # (so Bob can respond and the Bolt waits on the stack)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    mana(s, "p2", U=1)
    act(s, "p2", type="cast_spell", card_id=opt.id)


def test_flash_if_you_pay_more(cards):
    s = build(cards, ["Rout", "Lightning Bolt"], ["Opt"])
    rout = to_hand(s, "Rout")
    mana(s, W=2, C=3)  # {3}{W}{W}: not enough for the flash price {5}{W}{W}
    _stack_busy(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=rout.id)
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=rout.id)
    answer(s)
    assert s.state.cards[rout.id].zone == "p1:graveyard"
    check(s)


def test_no_extra_cost_at_sorcery_timing(cards):
    s = build(cards, ["Rout"])
    rout = to_hand(s, "Rout")
    mana(s, W=2, C=3)
    act(s, "p1", type="cast_spell", card_id=rout.id)
    answer(s)
    assert s.state.cards[rout.id].zone == "p1:graveyard"


def test_flash_if_x_is_three_or_less(cards):
    s = build(cards, ["Silver Scrutiny", "Lightning Bolt"], ["Opt"])
    scrutiny = to_hand(s, "Silver Scrutiny")
    mana(s, U=2, C=4)
    _stack_busy(s)
    with pytest.raises(ActionError, match="X is 3 or less"):
        act(s, "p1", type="cast_spell", card_id=scrutiny.id, x_value=4)
    act(s, "p1", type="cast_spell", card_id=scrutiny.id, x_value=3)
    answer(s)
    assert s.state.cards[scrutiny.id].zone == "p1:graveyard"
    check(s)


def test_flash_if_it_targets_a_permanent_you_control(cards):
    s = build(cards, ["Flash Photography", "Lightning Bolt", "Grizzly Bears"], ["Grizzly Bears", "Opt"])
    photo = to_hand(s, "Flash Photography")
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    mana(s, U=2, C=2)
    _stack_busy(s)
    with pytest.raises(ActionError, match="flash condition"):  # the target is theirs: no flash
        act(s, "p1", type="cast_spell", card_id=photo.id, targets=[theirs.id])
    act(s, "p1", type="cast_spell", card_id=photo.id, targets=[mine.id])
    answer(s)
    check(s)


# -- spend mana as though it were mana of any color (609.4b) --
ORRERY = [
    real("Chromatic Orrery", "{7}", 7, "Legendary Artifact", "You may spend mana as though it were mana of any color.\n{T}: Add {C}{C}{C}{C}{C}.\n"
         "{5}, {T}: Draw a card for each color among permanents you control."),
]


def test_orrery_line_is_read(cards):
    feats = {f.id: f.supported for f in coverage.of_card_data(cards.resolve("Chromatic Orrery")).features}
    assert feats["text:0"]


def test_colorless_mana_pays_colored_costs_with_an_orrery(cards):
    s = build(cards, ["Chromatic Orrery", "Grizzly Bears", "Grizzly Bears"])
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"]
    for b in bears:
        act(s, "p1", type="move", card_ids=[b.id], to={"zone": "hand"})
    mana(s, C=2)  # {1}{G}: colorless can't pay {G} without the Orrery
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears[0].id)
    put(s, "Chromatic Orrery")
    act(s, "p1", type="cast_spell", card_id=bears[0].id)
    answer(s)
    assert s.state.cards[bears[0].id].zone == "p1:battlefield"
    check(s)


# -- "cost an additional N life" for its targets (601.2f, 119.4) --
LIFE = [
    real("Terror of the Peaks", "{3}{R}{R}", 5, "Creature — Dragon", "Flying\nSpells your opponents cast that target this creature cost an "
         "additional 3 life to cast.\nWhenever another creature you control enters, this creature deals damage equal to that creature's power "
         "to any target.", ("5", "4"), "R"),
]


def test_terror_of_the_peaks_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Terror of the Peaks")).level == "FULL"


def test_spells_that_target_terror_cost_3_life(cards):
    s = build(cards, ["Terror of the Peaks", "Lightning Bolt"], ["Lightning Bolt"])
    terror, mine, theirs = put(s, "Terror of the Peaks"), to_hand(s, "Lightning Bolt"), to_hand(s, "Lightning Bolt", "p2")
    mana(s, R=1)
    mana(s, "p2", R=2)
    act(s, "p1", type="cast_spell", card_id=mine.id, targets=["p1"])  # (Bob may respond)
    life_before = s.state.players["p2"].life
    act(s, "p2", type="set_life", player="p2", value=2)
    with pytest.raises(ActionError):  # 119.4: only 2 life to pay 3
        act(s, "p2", type="cast_spell", card_id=theirs.id, targets=[terror.id])
    act(s, "p2", type="set_life", player="p2", value=life_before)
    act(s, "p2", type="cast_spell", card_id=theirs.id, targets=[terror.id])
    assert s.state.players["p2"].life == life_before - 3
    answer(s)
    check(s)
