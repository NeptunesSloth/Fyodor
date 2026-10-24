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
from tests.game_helpers import act
from tests.test_rules_conditionals import token_of
from tests.test_rules_effects import pass_until_stack_empty
from tests.test_rules_wave100f_attached import next_turn, settle, to_phase
from tests.wave9c_kit import build, check, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave100i_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w100i", number=f"I{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
CARDS = ["Rise of the Hobgoblins", "Stronghold Overseer", "Scourglass", "Riptide Chronologist", "Root Greevil", "Sabertooth Alley Cat", "Mist Dragon",
         "Surge Engine", "Goblin Ski Patrol", "Urborg", "Walking Sponge", "Hammerheim", "Chariot of the Sun", "Obelisk of Undoing", "Skycoach Waypoint",
         "Hexhaven Dueling Arena", "Coalborn Entity", "Soldevi Digger", "Terraformer", "Rocket Launcher", "Withering Wisps", "Savaen Elves",
         "Detention Vortex", "Soul Ransom", "Krovikan Sorcerer", "Credit Voucher", "Elsewhere Flask"]


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
