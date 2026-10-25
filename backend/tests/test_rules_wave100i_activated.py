"""Wave 100I: exact activated-ability wordings (app/rules/activated100i.py), real Oracle text (tests/fixtures/wave100i_cards.json), CR 2026-09-25.
Every scenario checks the replay and a save and a load (tests/wave9c_kit.check).

* Native rewordings: Rise of the Hobgoblins, Stronghold Overseer, Scourglass, Riptide Chronologist, Root Greevil, Sabertooth Alley Cat.
* 611.2a: no duration stated (Mist Dragon, Surge Engine, Goblin Ski Patrol); 608.2d: one keyword lost by choice (Urborg, Walking Sponge); 702.14
  (Hammerheim).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.errors import ActionError
from app.rules import combat, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_conditionals import token_of
from tests.test_rules_effects import pass_until_stack_empty
from tests.test_rules_wave100f_attached import next_turn, settle, to_phase
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave100i_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w100i", number=f"I{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
CARDS = ["Rise of the Hobgoblins", "Stronghold Overseer", "Scourglass", "Riptide Chronologist", "Root Greevil", "Sabertooth Alley Cat", "Mist Dragon",
         "Surge Engine", "Goblin Ski Patrol", "Urborg", "Walking Sponge", "Hammerheim", "Chariot of the Sun", "Obelisk of Undoing", "Skycoach Waypoint",
         "Hexhaven Dueling Arena", "Coalborn Entity", "Soldevi Digger", "Terraformer", "Rocket Launcher", "Withering Wisps", "Savaen Elves",
         "Detention Vortex", "Soul Ransom", "Krovikan Sorcerer", "Credit Voucher", "Elsewhere Flask",
         "Portal of Sanctuary", "Essence Reliquary", "Storm Elemental", "Hope of Ghirapur", "Crown of Doom", "Thaumaton Torpedo", "Monstrous War-Leech",
         "Tornado", "Void Stalker", "Cybernetica Datasmith", "Cavernous Maw", "Grizzled Wolverine",
         "Carrionette", "Soul of Shandalar", "Kentaro, the Smiling Cat", "Conspiracy Unraveler",
         "Sivriss, Nightmare Speaker", "Zareth San, the Trickster", "Myojin of Grim Betrayal", "Gerrard's Hourglass Pendant",
         "Excavator", "Outpace Oblivion", "Mana Maze", "Stench of Evil", "Giant Albatross",
         "Timestream Navigator", "Arcum's Weathervane", "Dragonbroods' Relic", "Sengir Nosferatu"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", CARDS)
def test_the_cards_are_full(name):
    data = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or []}).level == "FULL"


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def kws(s, c):
    return set(ch(s, c).keywords)


def activate(s, c, ability, *targets, pid="p1", **pool):
    if pool:
        mana(s, pid, **pool)
    act(s, pid, type="activate_ability", card_id=c.id, ability=ability, targets=[t.id for t in targets])


def choose(s, label):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == label)])


def zone(s, c):
    return s.state.cards[c.id].zone


# -- native rewordings -------------------------------------------------------------------------------------------------------------------
def test_rise_of_the_hobgoblins_gives_first_strike_to_your_red_and_white_creatures(cards):
    s = build(cards, ["Rise of the Hobgoblins"])
    rise = put(s, "Rise of the Hobgoblins")
    red = token_of(s, "p1", "Red One", "Token Creature — Goblin", colors=["R"])
    white = token_of(s, "p1", "White One", "Token Creature — Soldier", colors=["W"])
    green = token_of(s, "p1", "Green One", "Token Creature — Elf", colors=["G"])
    theirs = token_of(s, "p2", "Their Red", "Token Creature — Goblin", colors=["R"])
    activate(s, rise, 1, R=1)
    settle(s)
    assert [("first strike" in kws(s, c)) for c in (red, white, green, theirs)] == [True, True, False, False]
    check(s)


def test_stronghold_overseer_pumps_shadow_and_shrinks_the_rest(cards):
    s = build(cards, ["Stronghold Overseer"])
    overseer = put(s, "Stronghold Overseer")  # 5/5 flying, shadow
    bear = token_of(s, "p2", "Bear", "Token Creature — Bear", "2/2")
    activate(s, overseer, 2, B=2)
    settle(s)
    assert pt(s, "Stronghold Overseer") == (6, 5) and ch(s, bear).pt == (1, 2)
    check(s)


def test_scourglass_only_in_your_upkeep_and_spares_artifacts_and_lands(cards):
    s = build(cards, ["Scourglass", "Rise of the Hobgoblins"])
    glass = put(s, "Scourglass")
    rise = put(s, "Rise of the Hobgoblins")
    bear = token_of(s, "p2", "Bear", "Token Creature — Bear")
    forest = put(s, "Forest")
    with pytest.raises(ActionError):
        activate(s, glass, 0)  # (main phase: "Activate only during your upkeep")
    act(s, "p1", type="set_stops", own=["upkeep", "main1"], others=[], smart_pass=False)
    to_phase(s, "upkeep", turn=3)
    activate(s, glass, 0)
    settle(s)
    assert zone(s, rise) == "p1:graveyard" and bear.id not in s.state.cards
    assert zone(s, forest) == "p1:battlefield" and zone(s, glass) == "p1:graveyard"
    check(s)


def test_riptide_chronologist_untaps_the_chosen_type(cards):
    s = build(cards, ["Riptide Chronologist"])
    chrono = put(s, "Riptide Chronologist")
    elf = token_of(s, "p1", "Elf A", "Token Creature — Elf")
    their_elf = token_of(s, "p2", "Elf B", "Token Creature — Elf")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear")
    act(s, "p1", type="tap", card_ids=[elf.id, bear.id])
    act(s, "p2", type="tap", card_ids=[their_elf.id])
    activate(s, chrono, 0, U=1)
    pass_until_stack_empty(s)
    choose(s, "Elf")
    settle(s)
    assert [s.state.cards[c.id].tapped for c in (elf, their_elf, bear)] == [False, False, True]
    check(s)


def test_root_greevil_destroys_every_enchantment_of_the_chosen_color(cards):
    s = build(cards, ["Root Greevil", "Rise of the Hobgoblins", "Scourglass"], ["Rise of the Hobgoblins"])
    greevil = put(s, "Root Greevil")
    mine, theirs, glass = put(s, "Rise of the Hobgoblins"), put(s, "Rise of the Hobgoblins", "p2"), put(s, "Scourglass")
    next_turn(s)
    next_turn(s)  # (no summoning sickness for {T})
    activate(s, greevil, 0, G=1, C=2)
    pass_until_stack_empty(s)
    choose(s, "Red")
    settle(s)
    assert zone(s, mine) == "p1:graveyard" and zone(s, theirs) == "p2:graveyard" and zone(s, glass) == "p1:battlefield"
    check(s)


def test_sabertooth_alley_cat_can_be_blocked_only_by_defenders(cards):
    s = build(cards, ["Sabertooth Alley Cat"], ["Surge Engine"])
    cat = put(s, "Sabertooth Alley Cat")
    wall = put(s, "Surge Engine", "p2")  # defender
    bear = token_of(s, "p2", "Bear", "Token Creature — Bear")
    activate(s, cat, 1, R=1, C=1)
    settle(s)
    p = Plan(s.state, actor="p1", info=s.cards, rng=None)

    def problem(blocker):
        return combat.block_problem(p.state, p.state.cards[blocker.id], p.ch(blocker), p.state.cards[cat.id], p.ch(cat), p.info)
    assert problem(bear) is not None and problem(wall) is None
    check(s)


# -- no duration stated (611.2a) ---------------------------------------------------------------------------------------------------------
def test_mist_dragon_gains_and_loses_flying_for_good(cards):
    s = build(cards, ["Mist Dragon"])
    dragon = put(s, "Mist Dragon")
    activate(s, dragon, 0)
    settle(s)
    next_turn(s)
    assert "flying" in kws(s, dragon)  # (it lasts past the cleanup step)
    to_phase(s, "main1", turn=3)
    activate(s, dragon, 1)
    settle(s)
    assert "flying" not in kws(s, dragon)
    activate(s, dragon, 0)
    settle(s)
    assert "flying" in kws(s, dragon)  # (613.7: the latest timestamp wins)
    check(s)


def test_surge_engine_needs_no_defender_then_stays_a_blue_five_four(cards):
    s = build(cards, ["Surge Engine"])
    engine = put(s, "Surge Engine")
    with pytest.raises(ActionError):
        activate(s, engine, 2, U=1, C=2)  # (it has defender)
    activate(s, engine, 1, U=1)
    settle(s)
    activate(s, engine, 2)
    settle(s)
    next_turn(s)
    assert pt(s, "Surge Engine") == (5, 4) and ch(s, engine).colors == {"U"}
    check(s)


def test_goblin_ski_patrol_once_with_a_snow_mountain_then_its_controller_sacrifices_it(cards):
    s = build(cards, ["Goblin Ski Patrol", "Snow-Covered Mountain"])
    patrol = put(s, "Goblin Ski Patrol")
    with pytest.raises(ActionError):
        activate(s, patrol, 0, R=1, C=1)  # (no snow Mountain)
    put(s, "Snow-Covered Mountain")
    activate(s, patrol, 0)
    settle(s)
    assert pt(s, "Goblin Ski Patrol") == (3, 1) and "flying" in kws(s, patrol)
    with pytest.raises(ActionError):
        activate(s, patrol, 0, R=1, C=1)  # ("Activate only once")
    next_turn(s)
    assert zone(s, patrol) == "p1:graveyard"
    check(s)


# -- one keyword lost by choice (608.2d), every landwalk (702.14) ------------------------------------------------------------------------
@pytest.mark.parametrize(("land", "index", "pick", "left"), [
    ("Urborg", 1, "Loses swampwalk", {"first strike", "trample"}),
    ("Walking Sponge", 0, "Loses trample", {"first strike", "swampwalk"}),
])
def test_one_keyword_is_lost_by_choice(cards, land, index, pick, left):
    s = build(cards, [land])
    source = put(s, land)
    if land == "Walking Sponge":
        next_turn(s)
        next_turn(s)
    knight = token_of(s, "p2", "Knight", "Token Creature — Knight", text="First strike\nSwampwalk\nTrample")
    activate(s, source, index, knight)
    pass_until_stack_empty(s)
    choose(s, pick)
    settle(s)
    assert kws(s, knight) == left
    check(s)


def test_hammerheim_strips_every_landwalk(cards):
    s = build(cards, ["Hammerheim"])
    land = put(s, "Hammerheim")
    walker = token_of(s, "p2", "Walker", "Token Creature — Spirit", text="Swampwalk\nNonbasic landwalk\nFlying")
    activate(s, land, 1, walker)
    settle(s)
    assert kws(s, walker) == {"flying"}
    check(s)


def answer(s, ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


def aged(s):
    """Two turns later, Alice's main phase (no summoning sickness for what was put before)."""
    to_phase(s, "main1", turn=s.state.turn.number + 2)


# -- targets and simple instructions -------------------------------------------------------------------------------------------------------
def test_chariot_of_the_sun_flying_and_base_toughness_one_until_end_of_turn(cards):
    s = build(cards, ["Chariot of the Sun"])
    chariot = put(s, "Chariot of the Sun")
    ogre = token_of(s, "p1", "Ogre", "Token Creature — Ogre", "3/3")
    theirs = token_of(s, "p2", "Bear", "Token Creature — Bear")
    with pytest.raises(ActionError):
        activate(s, chariot, 0, theirs, C=2)  # (a creature you control)
    activate(s, chariot, 0, ogre)
    settle(s)
    assert ch(s, ogre).pt == (3, 1) and "flying" in kws(s, ogre)
    next_turn(s)
    assert ch(s, ogre).pt == (3, 3) and "flying" not in kws(s, ogre)
    check(s)


def test_obelisk_of_undoing_returns_only_what_you_own_and_control(cards):
    s = build(cards, ["Obelisk of Undoing", "Chariot of the Sun"], ["Chariot of the Sun"])
    obelisk = put(s, "Obelisk of Undoing")
    mine, theirs = put(s, "Chariot of the Sun"), put(s, "Chariot of the Sun", "p2")
    act(s, "p2", type="move", card_ids=[theirs.id], to={"player": "p1", "zone": "battlefield"})  # (Alice controls Bob's)
    with pytest.raises(ActionError):
        activate(s, obelisk, 0, theirs, C=6)
    activate(s, obelisk, 0, mine)
    settle(s)
    assert zone(s, mine) == "p1:hand"
    check(s)


def test_waypoint_and_arena_prepare_a_creature_with_a_prepare_spell(cards):
    s = build(cards, ["Skycoach Waypoint", "Hexhaven Dueling Arena", "Eiganjo Dynastorian // Replenish"])
    waypoint, arena = put(s, "Skycoach Waypoint"), put(s, "Hexhaven Dueling Arena")
    dyn = put(s, "Eiganjo Dynastorian // Replenish")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear")
    activate(s, waypoint, 1, bear, C=3)
    settle(s)
    assert s.state.rules.prepared == {}  # (no prepare spell: nothing, ruling 2026-03-20)
    with pytest.raises(ActionError):
        activate(s, arena, 1, dyn, C=2)  # (it didn't attack this turn)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": dyn.id, "target": "p2"}])
    to_phase(s, "main2", turn=3)
    assert s.state.rules.prepared == {}  # (one attacker: its own trigger didn't prepare it)
    activate(s, arena, 1, dyn, C=2)
    settle(s)
    assert len(s.state.rules.prepared) == 1  # 722.3a
    check(s)


def test_coalborn_entity_hits_a_creature_token_a_player_or_a_planeswalker(cards):
    s = build(cards, ["Coalborn Entity"], ["Terraformer"])
    entity = put(s, "Coalborn Entity")
    card_creature = put(s, "Terraformer", "p2")
    token = token_of(s, "p2", "Bear", "Token Creature — Bear", "2/1")
    with pytest.raises(ActionError):
        activate(s, entity, 0, card_creature, R=1, C=2)  # (a nontoken creature)
    activate(s, entity, 0, token)
    settle(s)
    mana(s, R=1, C=2)
    act(s, "p1", type="activate_ability", card_id=entity.id, ability=0, targets=["p2"])
    settle(s)
    assert token.id not in s.state.cards and s.state.players["p2"].life == 39
    check(s)


def test_soldevi_digger_puts_the_top_graveyard_card_on_the_bottom(cards):
    s = build(cards, ["Soldevi Digger", "Terraformer", "Coalborn Entity"])
    digger = put(s, "Soldevi Digger")
    for name in ("Terraformer", "Coalborn Entity"):
        act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == name and c.owner == "p1")], to={"zone": "graveyard"})
    activate(s, digger, 0, C=2)
    settle(s)
    assert [s.state.cards[c].name for c in s.state.zones["p1:graveyard"]] == ["Terraformer"]
    assert s.state.cards[s.state.zones["p1:library"][-1]].name == "Coalborn Entity"
    check(s)


def test_terraformer_makes_each_land_you_control_the_chosen_type(cards):
    s = build(cards, ["Terraformer"])
    former = put(s, "Terraformer")
    forest = put(s, "Forest")
    bob_land = put(s, "Island", "p2")
    activate(s, former, 0, C=1)
    pass_until_stack_empty(s)
    choose(s, "Swamp")
    settle(s)
    assert ch(s, forest).subtypes == {"Swamp"} and ch(s, bob_land).subtypes == {"Island"}  # (305.7)
    next_turn(s)
    assert ch(s, forest).subtypes == {"Forest"}
    check(s)


def test_rocket_launcher_needs_continuous_control_and_is_destroyed_at_end_step(cards):
    s = build(cards, ["Rocket Launcher"])
    rocket = put(s, "Rocket Launcher")
    mana(s, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=rocket.id, ability=0, targets=["p2"])  # (it came under Alice's control this turn)
    aged(s)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=rocket.id, ability=0, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 39 and zone(s, rocket) == "p1:battlefield"
    next_turn(s)
    assert zone(s, rocket) == "p1:graveyard"
    check(s)


def test_withering_wisps_activates_as_often_as_your_snow_swamps(cards):
    s = build(cards, ["Withering Wisps", "Snow-Covered Swamp", "Coalborn Entity"])
    wisps = put(s, "Withering Wisps")
    put(s, "Snow-Covered Swamp")
    put(s, "Coalborn Entity")
    activate(s, wisps, 1, B=1)
    settle(s)
    with pytest.raises(ActionError):
        activate(s, wisps, 1, B=1)  # (one snow Swamp: once this turn)
    assert s.state.players["p1"].life == 39 and s.state.players["p2"].life == 39
    check(s)


def test_savaen_elves_destroys_only_an_aura_on_a_land(cards):
    s = build(cards, ["Savaen Elves", "Wild Growth", "Pacifism"])
    elves = put(s, "Savaen Elves")
    forest = put(s, "Forest")
    growth, pacifism = put(s, "Wild Growth"), put(s, "Pacifism")
    bear = token_of(s, "p2", "Bear", "Token Creature — Bear")
    act(s, "p1", type="attach", card_ids=[growth.id], to=forest.id)
    act(s, "p1", type="attach", card_ids=[pacifism.id], to=bear.id)
    aged(s)
    with pytest.raises(ActionError):
        activate(s, elves, 0, pacifism, G=2)
    activate(s, elves, 0, growth)
    settle(s)
    assert zone(s, growth) == "p1:graveyard" and zone(s, pacifism) == "p1:battlefield"
    check(s)


# -- only your opponents may activate (602.2) ------------------------------------------------------------------------------------------------
def bob_priority(s):
    """Alice passes in her main phase and Bob, who stops there, gets priority (117.3d)."""
    act(s, "p2", type="set_stops", own=["main1"], others=["main1"], smart_pass=False)
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"


def test_detention_vortex_only_an_opponent_as_a_sorcery(cards):
    s = build(cards, ["Detention Vortex"])
    vortex = put(s, "Detention Vortex")
    bear = token_of(s, "p2", "Bear", "Token Creature — Bear")
    act(s, "p1", type="attach", card_ids=[vortex.id], to=bear.id)
    with pytest.raises(ActionError):
        activate(s, vortex, 2, C=3)  # (its controller can't)
    bob_priority(s)
    with pytest.raises(ActionError, match="sorcery"):
        activate(s, vortex, 2, pid="p2", C=3)  # (not as a sorcery for Bob)
    to_phase(s, "main1", turn=2)
    activate(s, vortex, 2, pid="p2", C=3)
    settle(s)
    assert zone(s, vortex) == "p1:graveyard"
    check(s)


def test_soul_ransom_an_opponent_discards_two_and_its_controller_sacrifices_it_and_draws(cards):
    s = build(cards, ["Soul Ransom"], ["Terraformer", "Coalborn Entity"])
    ransom = to_hand(s, "Soul Ransom")
    bear = token_of(s, "p2", "Bear", "Token Creature — Bear")
    mana(s, U=1, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=ransom.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].controller == "p1"
    cards_in = [next(c for c in s.state.cards.values() if c.name == n and c.owner == "p2") for n in ("Terraformer", "Coalborn Entity")]
    for c in cards_in:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})
    with pytest.raises(ActionError):
        activate(s, ransom, 2)  # (only an opponent)
    hand = len(s.state.zones["p1:hand"])
    bob_priority(s)
    activate(s, ransom, 2, pid="p2")
    if s.state.rules.decision is not None and s.state.rules.decision.player == "p2":
        answer(s, [c.id for c in cards_in])
    settle(s)
    assert zone(s, ransom) == "p1:graveyard" and len(s.state.zones["p1:hand"]) == hand + 2 and s.state.cards[bear.id].controller == "p2"
    assert all(zone(s, c) == "p2:graveyard" for c in cards_in)
    check(s)


# -- hand and library -------------------------------------------------------------------------------------------------------------------------
def test_krovikan_sorcerer_draws_two_and_discards_one_of_them(cards):
    s = build(cards, ["Krovikan Sorcerer", "Dark Ritual"])
    sorcerer = put(s, "Krovikan Sorcerer")
    ritual = next(c for c in s.state.cards.values() if c.name == "Dark Ritual" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[ritual.id], to={"zone": "hand"})
    aged(s)
    before = set(s.state.zones["p1:hand"])
    activate(s, sorcerer, 1)
    if s.state.rules.decision is not None and s.state.rules.decision.resume.get("step") == "ability_cost":
        answer(s, [ritual.id])
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    drawn = [o.id for o in d.options]
    assert len(drawn) == 2 and not set(drawn) & before  # (only the two cards drawn this way are offered)
    answer(s, drawn[:1])
    settle(s)
    assert zone(s, ritual) == "p1:graveyard" and s.state.cards[drawn[0]].zone == "p1:graveyard" and s.state.cards[drawn[1]].zone == "p1:hand"
    check(s)


def test_credit_voucher_shuffles_the_chosen_cards_away_and_draws_that_many(cards):
    s = build(cards, ["Credit Voucher", "Terraformer", "Coalborn Entity", "Soldevi Digger"])
    voucher = put(s, "Credit Voucher")
    picked = []
    for n in ("Terraformer", "Coalborn Entity", "Soldevi Digger"):
        c = next(c for c in s.state.cards.values() if c.name == n and c.owner == "p1")
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
        picked.append(c.id)
    size = len(s.state.zones["p1:hand"])
    activate(s, voucher, 0, C=2)
    pass_until_stack_empty(s)
    answer(s, picked[:2])
    settle(s)
    assert len(s.state.zones["p1:hand"]) == size and zone(s, voucher) == "p1:graveyard"
    assert s.state.rules.decision is None  # (no order asked: the library is shuffled, 701.24d)
    check(s)


# -- with the Auras attached (303.4) ---------------------------------------------------------------------------------------------------------
def test_portal_of_sanctuary_returns_the_creature_and_every_aura_but_not_equipment(cards):
    s = build(cards, ["Portal of Sanctuary", "Bonesplitter"], ["Pacifism"])
    portal = put(s, "Portal of Sanctuary")
    ogre = token_of(s, "p1", "Ogre", "Token Creature — Ogre", "3/3")
    theirs = token_of(s, "p2", "Bear", "Token Creature — Bear")
    pacifism, splitter = put(s, "Pacifism", "p2"), put(s, "Bonesplitter")
    act(s, "p2", type="attach", card_ids=[pacifism.id], to=ogre.id)
    act(s, "p1", type="attach", card_ids=[splitter.id], to=ogre.id)
    with pytest.raises(ActionError):
        activate(s, portal, 0, theirs, C=1)  # (a creature you control)
    activate(s, portal, 0, ogre)
    settle(s)
    assert ogre.id not in s.state.cards and zone(s, pacifism) == "p2:hand"  # (each to its owner's hand; the token ceases to exist, 704.5d)
    assert zone(s, splitter) == "p1:battlefield" and s.state.cards[splitter.id].attached_to is None  # (Equipment stays: ruling 2019-07-12)
    check(s)


def test_essence_reliquary_takes_only_your_auras_and_never_itself(cards):
    s = build(cards, ["Essence Reliquary", "Wild Growth"], ["Wild Growth"])
    reliquary = put(s, "Essence Reliquary")
    forest = put(s, "Forest")
    mine, theirs = put(s, "Wild Growth"), put(s, "Wild Growth", "p2")
    act(s, "p1", type="attach", card_ids=[mine.id], to=forest.id)
    act(s, "p2", type="attach", card_ids=[theirs.id], to=forest.id)
    with pytest.raises(ActionError):
        activate(s, reliquary, 0, reliquary)  # ("another target permanent")
    activate(s, reliquary, 0, forest)
    settle(s)
    assert zone(s, forest) == "p1:hand" and zone(s, mine) == "p1:hand" and zone(s, theirs) == "p2:graveyard"  # (704.5m: Bob's Aura, left behind)
    check(s)


# -- the card a cost exiled, combat damage history, the owner ----------------------------------------------------------------------------------
def top_of_library(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone != f"{pid}:battlefield")
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return c


def test_storm_elemental_grows_only_when_the_exiled_card_is_a_snow_land(cards):
    s = build(cards, ["Storm Elemental", "Snow-Covered Mountain", "Terraformer"])
    storm = put(s, "Storm Elemental")  # 3/4
    top_of_library(s, "Terraformer")
    activate(s, storm, 2, U=1)
    settle(s)
    assert pt(s, "Storm Elemental") == (3, 4)
    top_of_library(s, "Snow-Covered Mountain")
    activate(s, storm, 2, U=1)
    settle(s)
    assert pt(s, "Storm Elemental") == (4, 5)
    check(s)


def test_hope_of_ghirapur_stops_the_player_it_hit_from_casting_noncreature_spells(cards):
    s = build(cards, ["Hope of Ghirapur"], ["Dark Ritual", "Terraformer"])
    hope = put(s, "Hope of Ghirapur")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=hope.id, ability=1, targets=["p2"])  # (no damage dealt yet)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": hope.id, "target": "p2"}])
    to_phase(s, "main2", turn=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=hope.id, ability=1, targets=["p1"])  # (Alice wasn't dealt combat damage by it)
    act(s, "p1", type="activate_ability", card_id=hope.id, ability=1, targets=["p2"])
    settle(s)
    ritual, former = to_hand(s, "Dark Ritual", "p2"), to_hand(s, "Terraformer", "p2")
    to_phase(s, "main1", turn=4)
    mana(s, "p2", B=1, U=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=ritual.id)
    act(s, "p2", type="cast_spell", card_id=former.id)  # (creature spells are fine, ruling 2017-02-09)
    settle(s)
    assert zone(s, former) == "p2:battlefield"
    check(s)


def test_crown_of_doom_never_goes_back_to_its_owner(cards):
    s = build(cards, ["Crown of Doom"])
    crown = put(s, "Crown of Doom")
    mana(s, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=crown.id, ability=1, targets=["p1"])
    act(s, "p1", type="activate_ability", card_id=crown.id, ability=1, targets=["p2"])
    settle(s)
    assert s.state.cards[crown.id].controller == "p2"
    to_phase(s, "main1", turn=2)
    mana(s, "p2", C=2)
    with pytest.raises(ActionError):
        act(s, "p2", type="activate_ability", card_id=crown.id, ability=1, targets=["p1"])  # (its owner: ruling 2014-11-07)
    check(s)


def test_thaumaton_torpedo_costs_three_less_after_a_spacecraft_attacked(cards):
    s = build(cards, ["Thaumaton Torpedo"])
    torpedo = put(s, "Thaumaton Torpedo")
    ship = token_of(s, "p1", "Ship", "Token Artifact Creature — Spacecraft", "2/2")
    bear = token_of(s, "p2", "Bear", "Token Creature — Bear")
    to_phase(s, "main1", turn=3)
    mana(s, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=torpedo.id, ability=0, targets=[bear.id])  # ({6}: no Spacecraft attacked)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ship.id, "target": "p2"}])
    to_phase(s, "main2", turn=3)
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=torpedo.id, ability=0, targets=[bear.id])
    settle(s)
    assert bear.id not in s.state.cards and zone(s, torpedo) == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("kicked", [0, 1])
def test_monstrous_war_leech_mills_four_as_it_enters_if_kicked(cards, kicked):
    s = build(cards, ["Monstrous War-Leech", "Terraformer"])
    top_of_library(s, "Terraformer")
    leech = to_hand(s, "Monstrous War-Leech")
    mana(s, B=1, C=3, **({"U": 1} if kicked else {}))
    act(s, "p1", type="cast_spell", card_id=leech.id, **({"kicker": 1} if kicked else {}))
    settle(s)
    assert len(s.state.zones["p1:graveyard"]) == (4 if kicked else 1)  # (unkicked: only the Leech itself)
    assert zone(s, leech) == ("p1:battlefield" if kicked else "p1:graveyard")  # (unkicked: a 0/0, 704.5f)
    if kicked:
        assert pt(s, "Monstrous War-Leech") == (3, 3)  # (Terraformer, mana value 3, milled as it entered)
    check(s)


def test_tornado_costs_three_life_per_velocity_counter(cards):
    s = build(cards, ["Tornado"], ["Tornado"])
    tornado = put(s, "Tornado")
    a, b = token_of(s, "p2", "Bear A", "Token Creature — Bear"), token_of(s, "p2", "Bear B", "Token Creature — Bear")
    activate(s, tornado, 1, a, G=1, C=2)  # (no velocity counter: no life)
    settle(s)
    assert a.id not in s.state.cards and s.state.cards[tornado.id].counters.get("velocity") == 1 and s.state.players["p1"].life == 40
    with pytest.raises(ActionError):
        activate(s, tornado, 1, b, G=1, C=2)  # ("Activate only once each turn")
    other = put(s, "Tornado", "p2")  # (another Tornado with two velocity counters: 6 life)
    act(s, "p2", type="counter", card_ids=[other.id], kind="velocity", delta=2)
    bob_priority(s)  # (no timing restriction: Bob, in Alice's turn)
    activate(s, other, 1, b, pid="p2", G=1, C=2)
    settle(s)
    assert b.id not in s.state.cards and s.state.players["p2"].life == 34 and s.state.cards[other.id].counters.get("velocity") == 3
    check(s)


def test_void_stalker_shuffles_itself_and_the_target_into_their_owners_libraries(cards):
    s = build(cards, ["Void Stalker"], ["Terraformer"])
    stalker = put(s, "Void Stalker")
    bear = put(s, "Terraformer", "p2")
    aged(s)
    activate(s, stalker, 0, bear, U=1, C=2)
    settle(s)
    assert s.state.cards[stalker.id].zone == "p1:library" and s.state.cards[bear.id].zone == "p2:library"
    check(s)


def test_cybernetica_datasmith_one_player_draws_another_gets_the_robot(cards):
    s = build(cards, ["Cybernetica Datasmith"])
    smith = put(s, "Cybernetica Datasmith")
    aged(s)
    mana(s, U=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=smith.id, ability=1, targets=["p1", "p1"], target_counts=[1, 1])  # ("another target player", 115.3)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=smith.id, ability=1, targets=["p1", "p2"], target_counts=[1, 1])
    settle(s)
    robot = next(c for c in s.state.cards.values() if c.name == "Robot")
    assert len(s.state.zones["p1:hand"]) == hand + 1 and robot.controller == "p2"
    check(s)


def test_cavernous_maw_needs_three_other_caves_on_the_battlefield_or_in_the_graveyard(cards):
    s = build(cards, ["Cavernous Maw", "Echoing Deeps"])
    maw = put(s, "Cavernous Maw")
    for i in range(2):
        token_of(s, "p1", f"Cave {i}", "Token Land — Cave", "0/0")
    token_of(s, "p2", "Their Cave", "Token Land — Cave", "0/0")  # (not yours)
    with pytest.raises(ActionError):
        activate(s, maw, 1, C=2)  # (two other Caves)
    deeps = next(c for c in s.state.cards.values() if c.name == "Echoing Deeps")
    act(s, "p1", type="move", card_ids=[deeps.id], to={"zone": "graveyard"})
    activate(s, maw, 1)
    settle(s)
    now = ch(s, maw)
    assert now.pt == (3, 3) and {"Creature", "Land"} <= now.types and {"Cave", "Elemental"} <= now.subtypes  # (205.1b)
    check(s)


def test_grizzled_wolverine_only_while_a_creature_blocks_it_once_a_turn(cards):
    s = build(cards, ["Grizzled Wolverine"])
    wolverine = put(s, "Grizzled Wolverine")  # 2/2
    bear = token_of(s, "p2", "Bear", "Token Creature — Bear", "2/2")
    act(s, "p1", type="set_stops", own=["declare_blockers"], others=[], smart_pass=False)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": wolverine.id, "target": "p2"}])
    mana(s, R=1)
    with pytest.raises(ActionError):
        activate(s, wolverine, 0)  # (not the declare blockers step)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bear.id, "attacker_id": wolverine.id}])
    assert s.state.turn.phase == "declare_blockers" and s.state.rules.priority == "p1"
    activate(s, wolverine, 0, R=1)
    settle(s)
    assert pt(s, "Grizzled Wolverine") == (4, 2)
    with pytest.raises(ActionError):
        activate(s, wolverine, 0, R=1)  # (only once each turn)
    check(s)


# -- from the graveyard (113.6m) ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("pays", [False, True])
def test_carrionette_exiles_itself_and_the_target_unless_its_controller_pays(cards, pays):
    s = build(cards, ["Carrionette"], ["Terraformer"])
    nette = put(s, "Carrionette")
    former = put(s, "Terraformer", "p2")
    with pytest.raises(ActionError):
        activate(s, nette, 0, former, B=2, C=2)  # (on the battlefield: only from your graveyard)
    act(s, "p1", type="move", card_ids=[nette.id], to={"zone": "graveyard"})
    if pays:
        mana(s, "p2", C=2)
    activate(s, nette, 0, former)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    if pays:  # (118.12a: that creature's controller decides; with no mana to pay it isn't asked, 118.3)
        assert d is not None and d.player == "p2"
        act(s, "p2", type="choose", decision_id=d.id, option_ids=["pay"])
    settle(s)
    assert (zone(s, nette), zone(s, former)) == (("p1:graveyard", "p2:battlefield") if pays else ("p1:exile", "p2:exile"))
    check(s)


def test_soul_of_shandalar_hits_a_player_and_one_of_their_creatures_from_play_or_the_graveyard(cards):
    s = build(cards, ["Soul of Shandalar"], ["Terraformer", "Coalborn Entity"])
    soul = put(s, "Soul of Shandalar")
    former, mine = put(s, "Terraformer", "p2"), token_of(s, "p1", "Bear", "Token Creature — Bear", "2/4")
    mana(s, R=2, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=soul.id, ability=1, targets=["p2", mine.id], target_counts=[1, 1])  # (Bob doesn't control it)
    act(s, "p1", type="activate_ability", card_id=soul.id, ability=1, targets=["p2", former.id], target_counts=[1, 1])
    settle(s)
    assert s.state.players["p2"].life == 37 and zone(s, former) == "p2:graveyard"
    act(s, "p1", type="move", card_ids=[soul.id], to={"zone": "graveyard"})
    mana(s, R=2, C=3)
    act(s, "p1", type="activate_ability", card_id=soul.id, ability=2, targets=["p2"], target_counts=[1, 0])  # (no creature: ruling 2014-07-18)
    settle(s)
    assert s.state.players["p2"].life == 34 and zone(s, soul) == "p1:exile"
    check(s)


# -- alternative costs for the table (118.9) ---------------------------------------------------------------------------------------------
def test_kentaro_lets_samurai_be_cast_for_generic_mana_equal_to_their_mana_value(cards):
    s = build(cards, ["Kentaro, the Smiling Cat", "Samurai of the Pale Curtain", "Terraformer"])
    kentaro = put(s, "Kentaro, the Smiling Cat")
    samurai, former = to_hand(s, "Samurai of the Pale Curtain"), to_hand(s, "Terraformer")
    mana(s, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=former.id, alt_cost=f"{kentaro.id}:1")  # (not a Samurai)
    act(s, "p1", type="cast_spell", card_id=samurai.id, alt_cost=f"{kentaro.id}:1")  # ({W}{W}: two generic mana)
    settle(s)
    assert zone(s, samurai) == "p1:battlefield" and mana_pool(s) == {"C": 1}
    check(s)


def test_conspiracy_unraveler_casts_by_collecting_evidence_ten(cards):
    s = build(cards, ["Conspiracy Unraveler", "Soul of Shandalar", "Terraformer", "Cybernetica Datasmith", "Storm Elemental"])
    unraveler = put(s, "Conspiracy Unraveler")
    for n in ("Soul of Shandalar", "Terraformer"):  # (mana value 6 + 3: not enough)
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"zone": "graveyard"})
    smith = to_hand(s, "Cybernetica Datasmith")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=smith.id, alt_cost=f"{unraveler.id}:1")
    act(s, "p1", type="move", card_ids=[card_named(s, "Storm Elemental").id], to={"zone": "graveyard"})  # (+ 4: 13)
    act(s, "p1", type="cast_spell", card_id=smith.id, alt_cost=f"{unraveler.id}:1")
    if s.state.rules.decision is not None:
        d = s.state.rules.decision
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    settle(s)
    assert zone(s, smith) == "p1:battlefield" and len(s.state.zones["p1:graveyard"]) == 0
    check(s)


@pytest.mark.parametrize("pays", [True, False])
def test_sivriss_mills_and_returns_the_card_unless_the_opponent_pays_three_life(cards, pays):
    s = build(cards, ["Sivriss, Nightmare Speaker", "Terraformer"])
    sivriss = put(s, "Sivriss, Nightmare Speaker")
    fodder = token_of(s, "p1", "Bear", "Token Creature — Bear")
    aged(s)
    top = top_of_library(s, "Terraformer")
    act(s, "p1", type="activate_ability", card_id=sivriss.id, ability=0)
    while (d := s.state.rules.decision) is not None and d.player == "p1":
        answer(s, [fodder.id] if any(o.id == fodder.id for o in d.options) else [d.options[0].id])
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and zone(s, top) == "p1:graveyard"  # (milled first, then Bob decides)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["pay" if pays else "decline"])
    settle(s)
    assert zone(s, top) == ("p1:graveyard" if pays else "p1:hand") and s.state.players["p2"].life == (37 if pays else 40)
    check(s)


def test_zareth_san_swaps_in_from_the_hand_for_an_unblocked_rogue(cards):
    s = build(cards, ["Zareth San, the Trickster"])
    zareth = to_hand(s, "Zareth San, the Trickster")
    rogue = token_of(s, "p1", "Rogue", "Token Creature — Rogue", "1/1")
    act(s, "p1", type="set_stops", own=["declare_blockers"], others=[], smart_pass=False)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": rogue.id, "target": "p2"}])
    mana(s, U=1, B=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=zareth.id, ability=1)  # (not unblocked before blockers are declared: ruling 2020-09-25)
    act(s, "p1", type="pass_priority")  # (Bob has no creature: no blocks; Alice stops in the declare blockers step)
    assert s.state.turn.phase == "declare_blockers" and s.state.rules.priority == "p1"
    mana(s, U=1, B=1, C=2)
    act(s, "p1", type="activate_ability", card_id=zareth.id, ability=1)
    if (d := s.state.rules.decision) is not None and d.player == "p1":
        answer(s, [rogue.id])
    settle(s)
    now = s.state.cards[zareth.id]
    assert now.zone == "p1:battlefield" and now.tapped and now.attacking is not None and rogue.id not in s.state.cards
    check(s)


# -- the graveyard's history this turn (400.7) --------------------------------------------------------------------------------------------
def test_gerrards_hourglass_pendant_returns_only_what_died_from_the_battlefield_this_turn(cards):
    s = build(cards, ["Gerrard's Hourglass Pendant", "Terraformer", "Rise of the Hobgoblins", "Coalborn Entity"])
    pendant = put(s, "Gerrard's Hourglass Pendant")
    former, rise, forest = put(s, "Terraformer"), put(s, "Rise of the Hobgoblins"), put(s, "Forest")
    aged(s)
    act(s, "p1", type="move", card_ids=[former.id, rise.id, forest.id], to={"zone": "graveyard"})
    discarded = to_hand(s, "Coalborn Entity")
    act(s, "p1", type="move", card_ids=[discarded.id], to={"zone": "graveyard"})  # (from the hand: stays, ruling 2022-09-09)
    activate(s, pendant, 2, C=4)
    settle(s)
    assert all(zone(s, c) == "p1:battlefield" and s.state.cards[c.id].tapped for c in (former, rise, forest))
    assert zone(s, discarded) == "p1:graveyard" and zone(s, pendant) == "p1:exile"
    check(s)


def test_myojin_of_grim_betrayal_takes_every_creature_card_put_into_a_graveyard_this_turn(cards):
    s = build(cards, ["Myojin of Grim Betrayal", "Terraformer"], ["Coalborn Entity"])
    myojin = put(s, "Myojin of Grim Betrayal")
    act(s, "p1", type="counter", card_ids=[myojin.id], kind="indestructible", delta=1)
    mine, theirs = to_hand(s, "Terraformer"), put(s, "Coalborn Entity", "p2")
    act(s, "p1", type="move", card_ids=[mine.id], to={"zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[theirs.id], to={"zone": "graveyard"})
    activate(s, myojin, 1)
    settle(s)
    assert [s.state.cards[c.id].zone for c in (mine, theirs)] == ["p1:battlefield", "p1:battlefield"]  # (from anywhere, any graveyard)
    assert s.state.cards[theirs.id].controller == "p1" and not s.state.cards[myojin.id].counters.get("indestructible")
    check(s)


def test_excavator_gives_the_landwalk_of_the_sacrificed_basic_land(cards):
    s = build(cards, ["Excavator", "Snow-Covered Swamp"])
    excavator = put(s, "Excavator")
    swamp = put(s, "Snow-Covered Swamp")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear")
    activate(s, excavator, 0, bear)
    while (d := s.state.rules.decision) is not None and d.player == "p1" and any(o.id == swamp.id for o in d.options):
        answer(s, [swamp.id])
    settle(s)
    assert zone(s, swamp) == "p1:graveyard" and kws(s, bear) == {"swampwalk"}  # (its land type; "snow" is a supertype, 205.4)
    next_turn(s)
    assert kws(s, bear) == set()
    check(s)


def test_outpace_oblivion_hits_each_player_without_max_speed(cards):
    s = build(cards, ["Outpace Oblivion"])
    outpace = put(s, "Outpace Oblivion")
    settle(s)
    act(s, "p1", type="set_resource", player="p1", key="speed", value=4)
    act(s, "p1", type="set_resource", player="p2", key="speed", value=3)
    activate(s, outpace, 2, C=2)
    settle(s)
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (40, 38) and zone(s, outpace) == "p1:graveyard"  # (speed 4 is max)
    check(s)


def test_mana_maze_forbids_the_color_of_the_spell_most_recently_cast(cards):
    s = build(cards, ["Mana Maze", "Dark Ritual", "Carrionette", "Grizzly Bears"])
    put(s, "Mana Maze")
    ritual, nette, bears = to_hand(s, "Dark Ritual"), to_hand(s, "Carrionette"), to_hand(s, "Grizzly Bears")
    mana(s, B=2, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=ritual.id)  # (the first spell this turn: nothing to share, ruling 2004-10-04)
    settle(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=nette.id)  # (black, like Dark Ritual)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    act(s, "p1", type="cast_spell", card_id=nette.id)  # (the most recent is green now)
    settle(s)
    assert zone(s, bears) == "p1:battlefield" and zone(s, nette) == "p1:battlefield"
    check(s)


def test_stench_of_evil_one_damage_per_destroyed_plains_unless_its_controller_pays(cards):
    s = build(cards, ["Stench of Evil", "Plains"], ["Plains"])
    mine, theirs = put(s, "Plains"), put(s, "Plains", "p2")
    stench = to_hand(s, "Stench of Evil")
    mana(s, B=2, C=2)
    mana(s, "p2", C=2)
    act(s, "p1", type="cast_spell", card_id=stench.id)
    pass_until_stack_empty(s)
    asked = []
    while (d := s.state.rules.decision) is not None:
        asked.append(d.player)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay" if d.player == "p2" else "decline"])
        pass_until_stack_empty(s)
    settle(s)
    assert asked == ["p2"] and zone(s, mine) == "p1:graveyard" and zone(s, theirs) == "p2:graveyard"  # (Alice has no mana left: not asked)
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (39, 40)
    check(s)


@pytest.mark.parametrize("pays", [False, True])
def test_giant_albatross_takes_the_creature_that_killed_it_unless_its_controller_pays_two_life(cards, pays):
    s = build(cards, ["Giant Albatross"], ["Soul of Shandalar"])
    bird = put(s, "Giant Albatross")
    soul = put(s, "Soul of Shandalar", "p2")
    to_phase(s, "main1", turn=2)
    mana(s, "p2", R=2, C=3)
    mana(s, "p1", U=1, C=1)
    act(s, "p2", type="activate_ability", card_id=soul.id, ability=1, targets=["p1", bird.id], target_counts=[1, 1])
    pass_until_stack_empty(s)
    asked = []
    while (d := s.state.rules.decision) is not None:
        asked.append(d.player)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay"] if d.player == "p1" or pays else ["decline"])
        pass_until_stack_empty(s)
    settle(s)
    assert zone(s, bird) == "p1:graveyard" and asked == ["p1", "p2"]  # (Alice pays {1}{U}; then Bob decides for his Soul)
    assert zone(s, soul) == ("p2:battlefield" if pays else "p2:graveyard") and s.state.players["p2"].life == (38 if pays else 40)
    check(s)


def test_timestream_navigator_goes_to_the_library_bottom_for_an_extra_turn_with_the_citys_blessing(cards):
    s = build(cards, ["Timestream Navigator"])
    nav = put(s, "Timestream Navigator")
    aged(s)
    mana(s, U=2, C=2)
    with pytest.raises(ActionError):
        activate(s, nav, 1)  # (no city's blessing yet: 702.131)
    for i in range(9):
        token_of(s, "p1", f"Thing {i}", "Token Artifact — Thing", "0/0")
    settle(s)
    turn = s.state.turn.number
    activate(s, nav, 1)
    settle(s)
    assert s.state.zones["p1:library"][-1] == nav.id  # (the cost: its owner's library, on the bottom)
    next_turn(s)
    assert s.state.turn.number == turn + 1 and s.state.turn.active_player == "p1"  # (the extra turn, 500.7)
    check(s)


def test_arcums_weathervane_takes_or_gives_the_snow_supertype_for_good(cards):
    s = build(cards, ["Arcum's Weathervane", "Snow-Covered Swamp"])
    vane = put(s, "Arcum's Weathervane")
    swamp, forest = put(s, "Snow-Covered Swamp"), put(s, "Forest")
    with pytest.raises(ActionError):
        activate(s, vane, 1, swamp, C=2)  # (already snow)
    activate(s, vane, 0, swamp)
    settle(s)
    assert ch(s, swamp).supertypes == {"Basic"}  # (205.4: only snow goes)
    aged(s)
    activate(s, vane, 1, forest, C=2)
    settle(s)
    assert ch(s, forest).supertypes == {"Basic", "Snow"} and ch(s, swamp).supertypes == {"Basic"}
    check(s)


def test_dragonbroods_relic_makes_the_reliquary_dragon_whose_enters_ability_deals_three(cards):
    s = build(cards, ["Dragonbroods' Relic"])
    relic = put(s, "Dragonbroods' Relic")
    activate(s, relic, 1, W=1, U=1, B=1, R=1, G=1, C=3)
    pass_until_stack_empty(s)
    while (d := s.state.rules.decision) is not None:  # (the token's own enters trigger: its target)
        answer(s, ["p2"] if any(o.id == "p2" for o in d.options) else [d.options[0].id])
        pass_until_stack_empty(s)
    settle(s)
    dragon = next(c for c in s.state.cards.values() if c.name == "Reliquary Dragon")
    assert kws(s, dragon) >= {"flying", "lifelink"} and ch(s, dragon).colors == {"W", "U", "B", "R", "G"} and ch(s, dragon).pt == (4, 4)
    assert s.state.players["p2"].life == 37 and zone(s, relic) == "p1:graveyard"
    check(s)


def test_sengir_nosferatu_becomes_a_bat_that_brings_it_back(cards):
    s = build(cards, ["Sengir Nosferatu"])
    vamp = put(s, "Sengir Nosferatu")
    activate(s, vamp, 1, B=1, C=1)
    settle(s)
    bat = next(c for c in s.state.cards.values() if c.name == "Bat")
    assert zone(s, vamp) == "p1:exile" and "flying" in kws(s, bat) and ch(s, bat).pt == (1, 2)
    activate(s, bat, 1, B=1, C=1)
    pass_until_stack_empty(s)
    if s.state.rules.decision is not None:
        answer(s, [vamp.id])
    settle(s)
    assert zone(s, vamp) == "p1:battlefield" and bat.id not in s.state.cards
    check(s)
