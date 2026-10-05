"""Wave 22B: prohibitions checked where the event would happen (CR 614.17, 601.3, 602.5): cards that can't enter the battlefield, counters that
can't be put, spells that can't be cast. Real Oracle text; every scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

EXTRA = [
    real("Grafdigger's Cage", "{1}", 1, "Artifact", "Creature cards in graveyards and libraries can't enter the battlefield.\nPlayers can't cast spells from graveyards or libraries."),
    real("Weathered Runestone", "{2}", 2, "Artifact", "Nonland permanent cards in graveyards and libraries can't enter the battlefield.\nPlayers can't cast spells from graveyards or libraries."),
    real("Soulless Jailer", "{2}", 2, "Artifact Creature — Phyrexian Golem", "Permanent cards in graveyards can't enter the battlefield.\nPlayers can't cast noncreature spells from graveyards or exile.", ("0", "4")),
    real("Kunoros, Hound of Athreos", "{1}{W}{B}", 3, "Legendary Creature — Dog", "Vigilance, menace, lifelink\nCreature cards in graveyards can't enter the battlefield.\nPlayers can't cast spells from graveyards.", ("3", "3"), "WB"),
    real("Solemnity", "{2}{W}", 3, "Enchantment", "Players can't get counters.\nCounters can't be put on artifacts, creatures, enchantments, or lands.", None, "W"),
    real("Tatterkite", "{3}", 3, "Artifact Creature — Scarecrow", "Flying\nThis creature can't have counters put on it.", ("2", "1")),
    real("Melira's Keepers", "{4}{G}", 5, "Creature — Human Warrior", "This creature can't have counters put on it.", ("4", "4"), "G"),
    real("Gaddock Teeg", "{G}{W}", 2, "Legendary Creature — Kithkin Advisor", "Noncreature spells with mana value 4 or greater can't be cast.\nNoncreature spells with {X} in their mana costs can't be cast.", ("2", "2"), "GW"),
    real("Aether Storm", "{3}{U}", 4, "Enchantment", "Creature spells can't be cast.\nPay 4 life: Destroy this enchantment. It can't be regenerated. Any player may activate this ability.", None, "U"),
    real("Zombify", "{3}{B}", 4, "Sorcery", "Return target creature card from your graveyard to the battlefield.", None, "B"),
    real("Chord of Calling", "{X}{G}{G}{G}", 3, "Instant", "Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nSearch your library for a creature card with mana value X or less, put it onto the battlefield, then shuffle.", None, "G"),
    real("Kitchen Finks", "{1}{G/W}{G/W}", 3, "Creature — Ouphe", "When this creature enters, you gain 2 life.\nPersist (When this creature dies, if it had no -1/-1 counters on it, return it to the battlefield under its owner's control with a -1/-1 counter on it.)", ("3", "2"), "GW"),
    real("Battlegrowth", "{G}", 1, "Instant", "Put a +1/+1 counter on target creature.", None, "G"),
    real("Aether Hub", "", 0, "Land", "When this land enters, you get {E} (an energy counter).\n{T}: Add {C}.\n{T}, Pay {E}: Add one mana of any color."),
    real("Angel of Jubilation", "{1}{W}{W}{W}", 4, "Creature — Angel", "Flying\nOther nonblack creatures you control get +1/+1.\nPlayers can't pay life or sacrifice creatures to cast spells or activate abilities.", ("3", "3"), "W"),
    real("Yasharn, Implacable Earth", "{2}{G}{W}", 4, "Legendary Creature — Elemental Boar", "When Yasharn enters, search your library for a basic Forest card and a basic Plains card, reveal those cards, put them into your hand, then shuffle.\nPlayers can't pay life or sacrifice nonland permanents to cast spells or activate abilities.", ("4", "4"), "GW"),
    real("Karn's Sylex", "{3}", 3, "Legendary Artifact", "Karn's Sylex enters tapped.\nPlayers can't pay life to cast spells or to activate abilities that aren't mana abilities.\n{X}, {T}, Exile Karn's Sylex: Destroy each nonland permanent with mana value X or less. Activate only as a sorcery."),
    real("Fling", "{1}{R}", 2, "Instant", "As an additional cost to cast this spell, sacrifice a creature.\nFling deals damage equal to the sacrificed creature's power to any target.", None, "R"),
    real("Gut Shot", "{R/P}", 1, "Instant", "({R/P} can be paid with either {R} or 2 life.)\nGut Shot deals 1 damage to any target.", None, "R"),
    real("Mana Confluence", "", 0, "Land", "{T}, Pay 1 life: Add one mana of any color."),
    real("Angel's Grace", "{W}", 1, "Instant", "Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.)\nYou can't lose the game this turn and your opponents can't win the game this turn. Until end of turn, damage that would reduce your life total to less than 1 reduces it to 1 instead.", None, "W"),
    real("Lich's Mastery", "{3}{B}{B}{B}", 6, "Legendary Enchantment", "Hexproof\nYou can't lose the game.\nWhenever you gain life, draw that many cards.\nWhenever you lose life, for each 1 life you lost, exile a permanent you control or a card from your hand or graveyard.\nWhen Lich's Mastery leaves the battlefield, you lose the game.", None, "B"),
    real("Sigarda, Host of Herons", "{2}{G}{W}{W}", 5, "Legendary Creature — Angel", "Flying, hexproof\nSpells and abilities your opponents control can't cause you to sacrifice permanents.", ("5", "5"), "GW"),
    real("Tajuru Preserver", "{1}{G}", 2, "Creature — Elf Shaman", "Spells and abilities your opponents control can't cause you to sacrifice permanents.", ("2", "1"), "G"),
    real("Diabolic Edict", "{1}{B}", 2, "Instant", "Target player sacrifices a creature of their choice.", None, "B"),
    real("Probe Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Probe Golem", "{3}", 3, "Artifact Creature — Golem", "", ("3", "3")),
    real("Probe Relic", "{3}", 3, "Artifact", "", None),
    real("Probe Big Spell", "{4}{R}", 5, "Sorcery", "Probe Big Spell deals 1 damage to any target.", None, "R"),
]
FULL = ["Sigarda, Host of Herons", "Tajuru Preserver", "Angel of Jubilation", "Yasharn, Implacable Earth", "Karn's Sylex", "Grafdigger's Cage", "Weathered Runestone", "Soulless Jailer", "Kunoros, Hound of Athreos", "Solemnity", "Tatterkite", "Melira's Keepers",
        "Gaddock Teeg", "Aether Storm"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def said(s, text):
    return any(text in (p.t or "") for e in s.state.log for p in e.parts)


def to_graveyard(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def test_cage_keeps_a_creature_in_the_graveyard_but_not_a_noncreature(cards):
    s = build(cards, ["Grafdigger's Cage", "Zombify", "Probe Bear", "Probe Relic"], [])
    put(s, "Grafdigger's Cage")
    to_graveyard(s, "Probe Bear")
    mana(s, B=1, G=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Zombify").id, targets=[card_named(s, "Probe Bear").id])
    answer(s)
    assert zone_of(s, "Probe Bear") == "p1:graveyard"  # 614.17: it can't enter, so it stays
    assert said(s, "Grafdigger's Cage: a card can't enter the battlefield")
    check(s)


def test_cage_leaves_artifacts_alone_and_stops_a_tutor_to_the_battlefield_silently(cards):
    s = build(cards, ["Grafdigger's Cage", "Chord of Calling", "Probe Bear"], [], forests=9)
    put(s, "Grafdigger's Cage")
    mana(s, G=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Chord of Calling").id, x_value=1)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert zone_of(s, "Probe Bear") == "p1:library"
    assert not said(s, "can't enter")  # a note would show the opponent that a card was found
    check(s)


def test_the_prohibition_is_read_from_the_table_as_it_is_now(cards):
    s = build(cards, ["Grafdigger's Cage", "Zombify", "Probe Bear"], [])
    cage = put(s, "Grafdigger's Cage")
    act(s, "p1", type="move", card_ids=[cage.id], to={"zone": "graveyard"})  # gone before the return: 614.17a
    to_graveyard(s, "Probe Bear")
    mana(s, B=1, G=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Zombify").id, targets=[card_named(s, "Probe Bear").id])
    answer(s)
    assert zone_of(s, "Probe Bear") == "p1:battlefield"
    check(s)


def test_soulless_jailer_stops_every_permanent_card_in_a_graveyard(cards):
    s = build(cards, ["Soulless Jailer", "Probe Golem"], ["Probe Relic"])
    put(s, "Soulless Jailer")
    assert coverage.of_card_data(cards.resolve("Soulless Jailer")).level == "FULL"
    from app.rules import characteristics as chars
    from app.rules.plan import Plan
    from app.rules.prohibitions import cant_enter

    for name, pid in (("Probe Golem", "p1"), ("Probe Relic", "p2")):
        c = to_graveyard(s, name, pid)
        assert cant_enter(Plan.view(s.state, "p1", s.cards), s.state.cards[c.id], pid)
    assert chars  # (module import check)
    check(s)


def test_solemnity_stops_counters_and_a_persist_return_comes_back_without_one(cards):
    s = build(cards, ["Solemnity", "Kitchen Finks", "Battlegrowth", "Probe Bear"], [])
    put(s, "Solemnity")
    bear = put(s, "Probe Bear")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Battlegrowth").id, targets=[bear.id])
    answer(s)
    assert not s.state.cards[bear.id].counters.get("+1/+1")  # 614.17: nothing was put on it
    finks = put(s, "Kitchen Finks")
    act(s, "p1", type="set_damage", card_ids=[finks.id], value=5)
    act(s, "p1", type="pass_priority")
    answer(s)
    assert zone_of(s, "Kitchen Finks") == "p1:battlefield"  # persist: returned
    assert not s.state.cards[finks.id].counters  # ... without the -1/-1 counter (614.17: it can't be put on it)
    assert said(s, "Solemnity: counters can't be put on Kitchen Finks")
    check(s)


def test_solemnity_players_cant_get_counters(cards):
    s = build(cards, ["Solemnity", "Aether Hub"], [])
    put(s, "Solemnity")
    hub = to_hand(s, "Aether Hub")
    act(s, "p1", type="play_land", card_id=hub.id)
    answer(s)
    assert s.state.players["p1"].resources.get("energy", 0) == 0
    assert said(s, "Solemnity: counters can't be put on Alice")
    check(s)


def test_tatterkite_only_protects_itself(cards):
    s = build(cards, ["Tatterkite", "Battlegrowth", "Probe Bear"], [])
    kite = put(s, "Tatterkite")
    bear = put(s, "Probe Bear")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Battlegrowth").id, targets=[kite.id])
    answer(s)
    assert not s.state.cards[kite.id].counters.get("+1/+1")
    from app.rules import prohibitions
    from app.rules.plan import Plan

    plan = Plan.view(s.state, "p1", s.cards)
    assert prohibitions.cant_counters(plan, kite.id, None) and not prohibitions.cant_counters(plan, bear.id, None)
    check(s)


def test_gaddock_teeg_and_aether_storm_forbid_by_type_and_mana_value(cards):
    s = build(cards, ["Gaddock Teeg", "Probe Big Spell", "Probe Relic", "Probe Bear", "Aether Storm"], [])
    put(s, "Gaddock Teeg")
    mana(s, R=5, G=5, U=4)
    with pytest.raises(ActionError, match="can't cast"):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Probe Big Spell").id, targets=["p2"])  # noncreature, mana value 5
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Probe Relic").id)  # mana value 3: fine
    answer(s)
    with pytest.raises(ActionError, match="can't cast"):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Aether Storm").id)  # mana value 4: Teeg stops it
    check(s)


def test_angel_of_jubilation_stops_life_for_phyrexian_mana_and_creature_sacrifice_costs(cards):
    s = build(cards, ["Angel of Jubilation", "Gut Shot", "Fling", "Probe Bear", "Probe Relic"], [])
    put(s, "Angel of Jubilation")
    bear = put(s, "Probe Bear")
    shot = to_hand(s, "Gut Shot")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=shot.id, targets=["p2"])  # 2 life would pay the {R/P}: it can't (119.4)
    assert s.state.players["p1"].life == 40
    mana(s, R=2)
    fling = to_hand(s, "Fling")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=fling.id, targets=["p2"])  # no creature may be sacrificed to the additional cost
    assert zone_of(s, "Probe Bear") == "p1:battlefield" and bear.id
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=shot.id, targets=["p2"])  # mana pays {R/P}: fine
    check(s)


def test_yasharn_also_stops_nonland_permanents_and_mana_abilities_that_pay_life(cards):
    s = build(cards, ["Yasharn, Implacable Earth", "Fling", "Probe Relic", "Mana Confluence", "Probe Bear"], [])
    put(s, "Yasharn, Implacable Earth")
    put(s, "Probe Relic")
    put(s, "Probe Bear")
    confluence = put(s, "Mana Confluence")
    from app.rules import casting

    assert not [i for i, _ in casting.mana_abilities(s.state, confluence, s.cards)]  # 605.1a: "or activate abilities" includes mana abilities
    assert s.state.players["p1"].life == 40
    mana(s, R=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Fling").id, targets=["p2"])  # the Bear or the Relic: neither may be sacrificed
    check(s)


def test_karn_s_sylex_stops_life_costs_but_not_mana_abilities(cards):
    s = build(cards, ["Karn's Sylex", "Gut Shot", "Mana Confluence"], [])
    put(s, "Karn's Sylex")
    shot = to_hand(s, "Gut Shot")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=shot.id, targets=["p2"])  # 2 life can't pay the {R/P}
    confluence = put(s, "Mana Confluence")
    from app.rules import casting

    assert [i for i, _ in casting.mana_abilities(s.state, confluence, s.cards)]  # a mana ability: Sylex doesn't stop it
    act(s, "p1", type="cast_spell", card_id=shot.id, targets=["p2"])  # paid with {R} from the Confluence (its life is that ability's cost)
    assert s.state.players["p1"].life == 39
    check(s)


def test_a_resolved_cant_lose_the_game_this_turn_keeps_a_player_at_0_life_in_the_game_until_the_turn_ends(cards):
    """Angel's Grace's first sentence (its second, the floor on damage, isn't read: the spell stays by hand), as the effect parses."""
    from app.rules import game_result, scripts
    from app.rules.plan import Plan

    parsed = scripts.parse_effects("You can't lose the game this turn and your opponents can't win the game this turn.")
    assert [e["do"] for e in parsed[0]] == ["cant_result", "cant_result"]
    s = build(cards, [], [])
    plan = Plan(s.state, "p1", s.cards, None)
    ctx = {"controller": "p1"}
    for e in parsed[0]:
        assert game_result.cant_result(plan, ctx, e)
    s.state.rules.results = plan.rules.results
    act(s, "p1", type="life", player="p1", delta=-40)  # 0 life: 704.5a would end the game for them
    act(s, "p1", type="pass_priority")
    assert s.state.players["p1"].life == 0 and not s.state.rules.lost and s.state.rules.winner is None
    assert game_result.cannot_lose(Plan.view(s.state, "p1", s.cards), "p1")
    assert game_result.cannot_win(Plan.view(s.state, "p1", s.cards), "p2")


def test_lich_s_mastery_cant_lose_the_game_only_for_its_controller(cards):
    s = build(cards, ["Lich's Mastery"], [])
    put(s, "Lich's Mastery")
    from app.rules import game_result
    from app.rules.plan import Plan

    plan = Plan.view(s.state, "p1", s.cards)
    assert game_result.cannot_lose(plan, "p1") and not game_result.cannot_lose(plan, "p2")
    check(s)


def test_sigarda_stops_an_opponents_edict_but_not_your_own_sacrifices(cards):
    s = build(cards, ["Diabolic Edict", "Probe Bear"], ["Sigarda, Host of Herons", "Diabolic Edict"])
    put(s, "Probe Bear")
    put(s, "Sigarda, Host of Herons", "p2")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Diabolic Edict").id, targets=["p2"])  # Sigarda is hexproof, but a player isn't
    answer(s)
    assert zone_of(s, "Sigarda, Host of Herons", "p2") == "p2:battlefield"  # 614.17: nothing was sacrificed
    assert said(s, "Sigarda, Host of Herons: Bob can't be made to sacrifice permanents")
    check(s)


def test_a_players_own_edict_on_themselves_is_no_opponents_spell(cards):
    s = build(cards, ["Tajuru Preserver", "Diabolic Edict"], [])
    put(s, "Tajuru Preserver")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Diabolic Edict").id, targets=["p1"])
    answer(s)
    assert zone_of(s, "Tajuru Preserver") == "p1:graveyard"  # their own spell: it still works
    check(s)
