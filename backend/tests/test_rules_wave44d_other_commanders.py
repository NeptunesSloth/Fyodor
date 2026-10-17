"""Wave 44D: commanders whose only blocker was one line of the "other" families (CR 2026-09-25), real Oracle text
(tests/fixtures/wave44d_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 702.11d hexproof from [quality] (Nevinyrral, Knight of Grace): not "hexproof", only the sources with the quality are shut out; 601.3a Brisela's mana value bound.
* 601.2f cost changers: a mana value bound (The Scarlet Witch), the first spell with {X} (Zimone, Infinite Analyst), {X} for an activation (Agatha), a stored {X} (Will, Rowan).
* triggers and costs: Zuko, Mizzix, Syr Vondam, The Master of Lake-town, Minn, Tifa, The Incredible Hulk, Meren, Bortuk.
* abilities: Ellie, Jace, Nissa, Sheoldred (transformed returns), Hisoka, Mageta, Jolrael.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import pass_until_stack_empty
from tests.test_rules_wave34b_activated import next_turn, stops, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave44d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w44d", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
BRISELA, NEVINYRRAL, KNIGHT = "Brisela, Voice of Nightmares", "Nevinyrral, Urborg Tyrant", "Knight of Grace"
ELLIE, MEREN, BORTUK = "Ellie, Vengeful Hunter", "Meren of Clan Nel Toth", "Bortuk Bonerattle"
JACE, NISSA, SHEOLDRED = "Jace, Vryn's Prodigy // Jace, Telepath Unbound", "Nissa, Vastwood Seer // Nissa, Sage Animist", "Sheoldred // The True Scriptures"
ZUKO, MIZZIX, WITCH = "Zuko, Firebending Master", "Mizzix of the Izmagnus", "The Scarlet Witch"
MINN, MASTER, VONDAM = "Minn, Wily Illusionist", "The Master of Lake-town", "Syr Vondam, Sunstar Exemplar"
HISOKA, MAGETA, JOLRAEL = "Hisoka, Minamo Sensei", "Mageta the Lion", "Jolrael, Empress of Beasts"
WILL, ROWAN, ZIMONE, AGATHA = "Will, Scion of Peace", "Rowan, Scion of War", "Zimone, Infinite Analyst", "Agatha of the Vile Cauldron"
TIFA, HULK = "Tifa, Martial Artist", "Bruce Banner // The Incredible Hulk"
FULL = [BRISELA, NEVINYRRAL, KNIGHT, ELLIE, MEREN, BORTUK, JACE, NISSA, SHEOLDRED, ZUKO, MIZZIX, WITCH, MINN, MASTER, VONDAM, HISOKA, MAGETA, JOLRAEL, WILL, ROWAN,
        ZIMONE, AGATHA, TIFA, HULK]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=to_hand(s, name, pid).id, **kw)


# ---- 601.3a, 601.3: Brisela's mana value bound --------------------------------------------------------------------------------------------------------
def test_brisela_stops_an_opponent_casting_spells_with_mana_value_3_or_less(cards):
    s = build(cards, ["Lightning Bolt", "Fireball", "Divination", "Hill Giant"], [BRISELA])
    put(s, BRISELA, "p2")
    mana(s, R=8, U=3, W=2)
    with pytest.raises(ActionError, match="can't cast"):
        cast(s, "Lightning Bolt", targets=["p2"])  # mana value 1
    with pytest.raises(ActionError, match="can't cast"):
        cast(s, "Divination")  # mana value 3
    cast(s, "Hill Giant")  # mana value 4: fine
    pass_until_stack_empty(s)
    check(s)


def test_brisela_does_not_stop_its_own_controller_and_lets_an_x_spell_begin(cards):
    s = build(cards, [BRISELA, "Lightning Bolt", "Fireball"], [])
    put(s, BRISELA)
    mana(s, R=6)
    cast(s, "Lightning Bolt", targets=["p2"])  # (the controller's own spells are not "your opponents'")
    pass_until_stack_empty(s)
    check(s)
    t = build(cards, ["Fireball"], [BRISELA])
    put(t, BRISELA, "p2")
    mana(t, R=6)
    cast(t, "Fireball", targets=["p2"], x_value=4)  # 601.3a: a choice (the X) could lift its mana value past 3, so the cast may begin
    check(t)


# ---- 702.11d: hexproof from [quality] --------------------------------------------------------------------------------------------------------------
def test_nevinyrral_is_hexproof_from_artifacts_creatures_and_enchantments_only(cards):
    s = build(cards, ["Lightning Bolt", "Pacifism"], [NEVINYRRAL])
    nev = put(s, NEVINYRRAL, "p2")
    mana(s, R=2, W=2, C=2)
    with pytest.raises(ActionError):
        cast(s, "Pacifism", targets=[nev.id])  # an enchantment spell: its caster is an opponent
    cast(s, "Lightning Bolt", targets=[nev.id])  # a red instant: the only hexproof it has is from three card types
    pass_until_stack_empty(s)
    assert s.state.cards[nev.id].damage == 3
    check(s)


def test_knight_of_grace_is_hexproof_from_black_and_its_controller_can_still_target_it(cards):
    s = build(cards, ["Murder", "Lightning Bolt"], [KNIGHT])
    knight = put(s, KNIGHT, "p2")
    mana(s, B=3, R=1, C=2)
    with pytest.raises(ActionError):
        cast(s, "Murder", targets=[knight.id])
    cast(s, "Lightning Bolt", targets=[knight.id])
    pass_until_stack_empty(s)
    assert zone_of(s, KNIGHT, "p2") == "p2:graveyard"  # (a 2/2 takes 3)
    check(s)
    t = build(cards, [KNIGHT, "Murder"], [])
    own = put(t, KNIGHT)
    mana(t, B=3)
    cast(t, "Murder", targets=[own.id])  # hexproof never stops the controller (702.11b)
    check(t)



# ---- 601.2f: cost changers -----------------------------------------------------------------------------------------------------------------------------
def test_the_scarlet_witch_takes_her_power_off_instants_and_sorceries_of_mana_value_4_or_more(cards):
    s = build(cards, [WITCH, "Day of Judgment"], [])
    put(s, WITCH)
    mana(s, W=2)
    cast(s, "Day of Judgment")  # {2}{W}{W}, mana value 4: {2} less (her power)
    pass_until_stack_empty(s)
    assert zone_of(s, "Day of Judgment") == "p1:graveyard"
    check(s)


def test_the_scarlet_witch_counts_the_x_of_a_spell_and_leaves_a_lower_mana_value_alone(cards):
    s = build(cards, [WITCH, "Fireball", "Divination"], [])
    put(s, WITCH)
    mana(s, R=1, C=1)
    cast(s, "Fireball", targets=["p2"], x_value=3)  # {3}{R}, mana value 4 with the X chosen: {1}{R}
    assert zone_of(s, "Fireball") == "p1:graveyard"
    mana(s, U=1, C=1)
    with pytest.raises(ActionError):
        cast(s, "Divination")  # mana value 3: {2}{U} in full
    check(s)


def test_zimone_cheapens_only_the_first_spell_with_x_each_turn(cards):
    s = build(cards, [ZIMONE, "Fireball"], [])
    z = put(s, ZIMONE)
    act(s, "p1", type="counter", card_ids=[z.id], kind="+1/+1", delta=2)
    mana(s, R=1, C=1)
    cast(s, "Fireball", targets=["p2"], x_value=3)  # {3}{R}: {1} less for each of the two counters
    assert zone_of(s, "Fireball") == "p1:graveyard"
    pass_until_stack_empty(s)
    mana(s, R=1, C=1)
    with pytest.raises(ActionError):
        cast(s, "Fireball", targets=["p2"], x_value=3)  # not the first this turn (and four counters now): in full
    check(s)


def test_agatha_takes_her_power_off_the_activated_abilities_of_creatures_you_control(cards):
    s = build(cards, [AGATHA], [])
    put(s, AGATHA)
    mana(s, R=1, G=1, C=3)
    act(s, "p1", type="activate_ability", card_id=card_named(s, AGATHA).id, ability=1)  # {4}{R}{G} less {1} (her power): five mana
    assert not any(s.state.players["p1"].mana.values())  # (all five paid)
    check(s)
    t = build(cards, [AGATHA], [])
    put(t, AGATHA)
    mana(t, R=1, G=1, C=2)
    with pytest.raises(ActionError):
        act(t, "p1", type="activate_ability", card_id=card_named(t, AGATHA).id, ability=1)  # four mana is not enough
    check(t)


def test_will_makes_white_and_blue_spells_cost_less_by_the_life_gained_as_it_resolves(cards):
    s = build(cards, [WILL, "Divination", "Hill Giant"], [])
    put(s, WILL)
    next_turn(s)
    act(s, "p1", type="life", delta=2)
    act(s, "p1", type="activate_ability", card_id=card_named(s, WILL).id, ability=1)
    pass_until_stack_empty(s)
    mana(s, U=1)
    cast(s, "Divination")  # {2}{U}, blue: two less
    assert zone_of(s, "Divination") == "p1:graveyard"
    mana(s, C=1)
    with pytest.raises(ActionError):
        cast(s, "Hill Giant")  # colorless: in full
    check(s)


def test_rowan_makes_black_and_red_spells_cost_less_by_the_life_lost(cards):
    s = build(cards, [ROWAN, "Fireball"], [])
    put(s, ROWAN)
    next_turn(s)
    act(s, "p1", type="life", delta=-2)
    act(s, "p1", type="activate_ability", card_id=card_named(s, ROWAN).id, ability=1)
    pass_until_stack_empty(s)
    mana(s, R=1)
    cast(s, "Fireball", targets=["p2"], x_value=2)  # {2}{R}: two less
    assert zone_of(s, "Fireball") == "p1:graveyard"
    check(s)


# ---- triggers ------------------------------------------------------------------------------------------------------------------------------------------
def exp(s, pid="p1"):
    return s.state.players[pid].resources.get("experience", 0)


def decide(s, ids):
    d = s.state.rules.decision
    assert d is not None, "no decision"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    pass_until_stack_empty(s)


def test_zuko_gets_an_experience_counter_for_a_spell_cast_during_combat_only(cards):
    s = build(cards, [ZUKO, "Lightning Bolt", "Giant Growth"], [])
    z = put(s, ZUKO)
    mana(s, R=1, G=1)
    cast(s, "Lightning Bolt", targets=["p2"])
    pass_until_stack_empty(s)
    assert exp(s) == 0  # (cast in the main phase)
    stops(s)
    to_phase(s, "begin_combat")
    mana(s, G=1)
    cast(s, "Giant Growth", targets=[z.id])
    pass_until_stack_empty(s)
    assert exp(s) == 1
    check(s)


def test_mizzix_counts_only_spells_with_more_mana_value_than_the_experience_counters(cards):
    s = build(cards, [MIZZIX, "Lightning Bolt", "Fiery Temper", "Giant Growth"], [])
    z = put(s, MIZZIX)
    mana(s, R=5, G=1)
    cast(s, "Lightning Bolt", targets=["p2"])  # mana value 1 > 0
    pass_until_stack_empty(s)
    assert exp(s) == 1
    cast(s, "Fiery Temper", targets=["p2"])  # mana value 3 > 1
    pass_until_stack_empty(s)
    assert exp(s) == 2
    cast(s, "Giant Growth", targets=[z.id])  # mana value 1, not more than 2
    pass_until_stack_empty(s)
    assert exp(s) == 2
    check(s)


def test_syr_vondam_destroys_a_permanent_when_exiled_with_power_4_or_more(cards):
    s = build(cards, [VONDAM, "Swords to Plowshares"], ["Grizzly Bears"])
    v = put(s, VONDAM)
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="counter", card_ids=[v.id], kind="+1/+1", delta=2)
    mana(s, W=1)
    cast(s, "Swords to Plowshares", targets=[v.id])
    pass_until_stack_empty(s)
    if s.state.rules.decision is not None:
        decide(s, [bears.id])
    assert zone_of(s, VONDAM) == "p1:exile" and s.state.cards[bears.id].zone == "p2:graveyard"
    check(s)


def test_syr_vondam_with_power_under_4_destroys_nothing(cards):
    s = build(cards, [VONDAM, "Swords to Plowshares"], ["Grizzly Bears"])
    v = put(s, VONDAM)
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, W=1)
    cast(s, "Swords to Plowshares", targets=[v.id])
    pass_until_stack_empty(s)
    assert zone_of(s, VONDAM) == "p1:exile" and s.state.cards[bears.id].zone == "p2:battlefield"
    check(s)


def fill_graveyard(s, pid, n):
    ids = [c for c in s.state.zones[f"{pid}:library"][:n]]
    act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "graveyard"})


def test_the_master_of_lake_town_draws_for_each_graveyard_with_seven_or_more_cards(cards):
    s = build(cards, [MASTER, "Murder"], [])
    master = put(s, MASTER)
    fill_graveyard(s, "p1", 6)  # (seven with the Master)
    fill_graveyard(s, "p2", 7)
    mana(s, B=3)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Murder", targets=[master.id])
    pass_until_stack_empty(s)
    assert len(s.state.zones["p1:hand"]) == hand + 2
    check(s)


def test_the_master_of_lake_town_skips_a_graveyard_with_fewer_cards(cards):
    s = build(cards, [MASTER, "Murder"], [])
    master = put(s, MASTER)
    fill_graveyard(s, "p1", 5)  # (six with the Master)
    fill_graveyard(s, "p2", 7)
    mana(s, B=3)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Murder", targets=[master.id])
    pass_until_stack_empty(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_minn_puts_a_permanent_with_mana_value_up_to_the_dead_illusions_power_from_hand(cards):
    s = build(cards, [MINN, "Phantasmal Forces", "Murder", "Hill Giant", "Nessian Asp"], [])
    put(s, MINN)
    forces = put(s, "Phantasmal Forces")
    giant, asp = to_hand(s, "Hill Giant"), to_hand(s, "Nessian Asp")
    mana(s, B=3)
    cast(s, "Murder", targets=[forces.id])  # a 4/1 Illusion
    pass_until_stack_empty(s)
    decide(s, [giant.id])  # (mana value 4; the Asp's 5 is not offered)
    assert s.state.cards[giant.id].zone == "p1:battlefield" and s.state.cards[asp.id].zone == "p1:hand"
    check(s)


def test_tifa_untaps_and_adds_a_combat_phase_after_a_big_hit_in_the_first_combat(cards):
    s = build(cards, [TIFA], [])
    t = put(s, TIFA)
    act(s, "p1", type="counter", card_ids=[t.id], kind="+1/+1", delta=3)  # 7/7
    next_turn(s)
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": t.id, "target": "p2"}])
    to_phase(s, "combat_damage")
    pass_until_stack_empty(s)
    assert s.state.rules.extra_phases[:1] == ["begin_combat"]
    assert not s.state.cards[t.id].tapped  # (untapped by the trigger)
    check(s)
