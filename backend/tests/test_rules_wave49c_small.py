"""Wave 49C: single-wording gaps of cards ranked 25,000 and up (CR 2026-09-25), real Oracle text (tests/fixtures/wave49c_small_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 613.1f, 613.7: "All creatures lose flying." (Gravity Sphere), "All creatures lose flying and islandwalk." (Mystic Decree) - a static loss in timestamp order.
* 105.2, 509.1: "White creatures and blue creatures can't block." (Magistrate's Veto), "Green creatures and white creatures can't block this turn." (Flash of Defiance).
* 115.2: "… can't be the target of spells" (Spectral Shield), "… of blue or black spells" (Karplusan Strider), "… unless it attacked or blocked this turn" (Lurker) - abilities still may.
* 115.1, 608.2b: "Exile target creature with the greatest power among creatures on the battlefield." (Topple), "… target nonland permanent with the lowest mana value." (Culling Scales)
  - a tie is no beating, and the target must still be the one when it resolves; "Destroy target creature if it has the least power or is tied for least power …" (Wretched Banquet) judges as it resolves.
* Gained along the way: "Creatures can't be the targets of spells." (Dense Foliage), "... unless an opponent has 10 or less life." (Vampire Lacerator), "... if an opponent has 0 or less life, ..."
  (Heaven Sent), "Choose a card name, then target player mills a card. If a card with the chosen name was milled this way, you gain life equal to its mana value." (Lammastide Weave: the name is no
  "it"), "... becomes a creature with haste and \"...\"" (Druid Class).
* 102.4: "creatures your team controls" (Dwarven Lightsmith, Combo Attack), "another Warrior your team controls" (Thrasher Brute, Decorated Champion) - outside a team game "your team" is "you".
* Gained with the extremes: "Each creature with the greatest mana value has protection from each color." (Favor of the Mighty), "Put a +1/+1 counter on target creature you control with the
  greatest power." (Triumph of Gerrard), "if enchanted permanent is a creature with the greatest power among creatures on the battlefield" (Historian's Wisdom, intervening: 603.4), "if it has
  the greatest power or is tied for greatest power among creatures on the battlefield" (Strength-Testing Hammer). "Each opponent chooses a creature with the greatest mana value among
  creatures they control" (Summon: Valefor) stays manual: the extreme is among the chooser's own creatures.
* 506.4: "Untap target nonattacking creature. It gets +1/+3 until end of turn." (Alarum), "Target nonattacking, nonblocking creature gets +0/+2 until end of turn." (Unlikely Alliance).
* 508.1, 510.1: "Whenever this creature attacks and isn't blocked, it assigns no combat damage this turn and defending player loses 2 life." (Keeper of Tresserhorn, Lim-Dul's Paladin).
* 500.5a, 511.2: "until end of combat" - "Whenever this creature attacks and isn't blocked, it gets +2/+0 until end of combat." (Murk Dwellers), "{2}: This artifact becomes a 3/6 Golem artifact creature until
  end of combat. Activate only during combat." (Jade Statue), "Target blocking Wall you control gets +10/+0 until end of combat." (Glyph of Destruction): the effect ends with the combat phase.
* 700.2: "Target nonattacking creature gains reach and deathtouch until end of turn. Untap it." (Ruthless Instincts, mode one).
* 120.3, 608.2c: "~ deals 1 damage to each nonblack creature and an additional 1 damage to each green creature." (Kaervek's Hex), "… X damage to each creature with flying and 1 additional damage to each blue
  creature." (Tropical Storm), "… 2 damage to each attacking creature and 1 damage to you and each creature you control." (Hail Storm): two instructions of one source, in order.
* 120.3, 608.2c, 601.2h: "~ deals 3 damage to each creature without flying if {R} was spent to cast this spell and 3 damage to each creature with flying if {G} was spent to cast this spell."
  (Firespout): the two halves are two instructions, each with its own mana-spent condition (both when {R}{G} was spent).
* 118.12: "At the beginning of your upkeep, sacrifice this creature unless you mill two cards." (Deep Spawn) - the payment is the controller's choice.
* 602.2: "{3}, {T} or {R}, {T}: This artifact deals 1 damage to any target." (Granite Shard and the other Shards) - the ability may be paid either way, not both (the rulings).
* 702.129a: "Eternalize—{2}{W}{W}, Discard a card." (Sunscourge Champion, Sinuous Striker) - the keyword's cost has a second part, a discard from the hand (the card with
  eternalize is in the graveyard, so it cannot discard itself); with no other card in hand the ability cannot be activated.
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
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import ask, attach, attack, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49c_small_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49c", number=f"S{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = [c["name"] for c in DATA]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_the_cards_are_full(cards):
    for name in FULL:
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def eternalize(s, name="Sunscourge Champion", hand_left=1):
    """The card in the graveyard and (``hand_left``) a Forest in hand to discard; returns the card."""
    champ = card_named(s, name)
    act(s, "p1", type="move", card_ids=[champ.id], to={"zone": "graveyard"})
    if hand_left:
        to_hand(s, "Forest")
    mana(s, W=2, C=2)
    return champ


def test_eternalize_with_a_discard_makes_the_token_and_discards_a_card(cards):
    s = build(cards, ["Sunscourge Champion"])
    champ = eternalize(s)
    discarded = s.state.zones["p1:hand"][0]
    act(s, "p1", type="activate_ability", card_id=champ.id, ability=1)
    settle(s)
    assert s.state.cards[champ.id].zone == "p1:exile" and s.state.cards[discarded].zone == "p1:graveyard" and not s.state.zones["p1:hand"]
    (token,) = [c for c in s.state.cards.values() if c.token is not None and c.name == "Sunscourge Champion"]
    ch = Plan(s.state, "p1", s.cards, None).ch(token)
    assert ch.colors == {"B"} and "Zombie" in ch.subtypes and ch.pt == (4, 4)  # 702.129a
    assert life(s) == 44  # its enters trigger gains life equal to its power
    check(s)


def test_eternalize_with_a_discard_needs_a_card_in_hand(cards):
    s = build(cards, ["Sunscourge Champion"])
    champ = eternalize(s, hand_left=0)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=champ.id, ability=1)
    check(s)


def chars(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id])


@pytest.mark.parametrize("sphere", ["Gravity Sphere", "Mystic Decree"])
def test_a_world_enchantment_takes_flying_from_every_creature(cards, sphere):
    s = build(cards, [sphere, "Mulldrifter"], ["Mulldrifter"])
    put(s, "Mulldrifter")
    put(s, "Mulldrifter", "p2")
    assert "flying" in chars(s, "Mulldrifter").keywords
    put(s, sphere)
    assert "flying" not in chars(s, "Mulldrifter").keywords and "flying" not in chars(s, "Mulldrifter", "p2").keywords
    check(s)


def test_a_creature_keeps_flying_without_the_sphere(cards):
    s = build(cards, ["Mulldrifter"])
    put(s, "Mulldrifter")
    assert "flying" in chars(s, "Mulldrifter").keywords
    check(s)


def test_magistrates_veto_stops_white_and_blue_creatures_blocking_but_not_green(cards):
    s = build(cards, ["Magistrate's Veto", "Soul Warden", "Merfolk Looter", "Llanowar Elves"])
    for name in ("Magistrate's Veto", "Soul Warden", "Merfolk Looter", "Llanowar Elves"):
        put(s, name)
    assert "cant_block" in chars(s, "Soul Warden").imposed and "cant_block" in chars(s, "Merfolk Looter").imposed
    assert "cant_block" not in chars(s, "Llanowar Elves").imposed
    check(s)


def test_flash_of_defiance_stops_green_and_white_creatures_blocking_this_turn(cards):
    s = build(cards, ["Flash of Defiance", "Soul Warden", "Merfolk Looter", "Llanowar Elves"])
    for name in ("Soul Warden", "Merfolk Looter", "Llanowar Elves"):
        put(s, name)
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Flash of Defiance").id)
    settle(s)
    assert "cant_block" in chars(s, "Soul Warden").imposed and "cant_block" in chars(s, "Llanowar Elves").imposed
    assert "cant_block" not in chars(s, "Merfolk Looter").imposed
    check(s)


def test_spectral_shield_stops_spells_targeting_the_creature(cards):
    s = build(cards, ["Spectral Shield", "Grizzly Bears", "Lightning Bolt"])
    bears = put(s, "Grizzly Bears")
    attach(s, put(s, "Spectral Shield"), bears)
    assert chars(s, "Grizzly Bears").pt == (2, 4)
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[bears.id])
    check(s)


def test_karplusan_strider_stops_blue_and_black_spells_only(cards):
    s = build(cards, ["Karplusan Strider", "Lightning Bolt", "Capsize"])
    strider = put(s, "Karplusan Strider")
    mana(s, U=3, R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Capsize").id, targets=[strider.id])
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[strider.id])  # a red spell may
    settle(s)
    assert s.state.cards[strider.id].damage == 3
    check(s)


def test_lurker_can_be_targeted_by_spells_only_after_it_attacked(cards):
    s = build(cards, ["Lurker", "Lightning Bolt"])
    lurker = put(s, "Lurker")
    to_phase(s, "main1", turn=3)  # (no longer summoning sick)
    mana(s, R=1)
    bolt = to_hand(s, "Lightning Bolt")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[lurker.id])
    attack(s, lurker)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[lurker.id])  # it attacked this turn
    settle(s)
    assert s.state.cards[bolt.id].zone == "p1:graveyard"
    check(s)


def test_a_shard_is_activated_with_either_cost(cards):
    s = build(cards, ["Granite Shard"])
    shard = put(s, "Granite Shard")
    mana(s, R=1)
    act(s, "p1", type="activate_ability", card_id=shard.id, ability=1, targets=["p2"])  # {R}, {T}
    settle(s)
    assert life(s, "p2") == 39 and s.state.cards[shard.id].tapped
    check(s)


def test_a_shard_is_activated_with_three_generic(cards):
    s = build(cards, ["Granite Shard"])
    shard = put(s, "Granite Shard")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=shard.id, ability=0, targets=["p2"])  # {3}, {T}
    settle(s)
    assert life(s, "p2") == 39
    check(s)


def test_a_shard_needs_one_of_its_costs_in_full(cards):
    s = build(cards, ["Granite Shard"])
    shard = put(s, "Granite Shard")
    mana(s, C=2)  # not {3}, and no {R}
    for index in (0, 1):
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", card_id=shard.id, ability=index, targets=["p2"])
    check(s)


def upkeep_answering(s, answer, limit=200):
    """Alice's next upkeep: the optional payment is answered ``answer``; nobody attacks or blocks."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.number == 3 and s.state.turn.phase == "main1" and d is None:
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer] if answer in ids else ids[: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached the main phase")


@pytest.mark.parametrize(("answer", "milled", "alive"), [("pay", 2, True), ("decline", 0, False)])
def test_deep_spawn_is_sacrificed_unless_you_mill_two_cards(cards, answer, milled, alive):
    s = build(cards, ["Deep Spawn"])
    spawn = put(s, "Deep Spawn")
    library, graveyard = len(s.state.zones["p1:library"]), len(s.state.zones["p1:graveyard"])
    upkeep_answering(s, answer)
    assert (s.state.cards[spawn.id].zone == "p1:battlefield") is alive
    assert len(s.state.zones["p1:library"]) == library - milled - 1  # (and the draw for the turn)
    assert len(s.state.zones["p1:graveyard"]) == graveyard + milled + (0 if alive else 1)
    check(s)


def test_topple_targets_only_a_creature_with_the_greatest_power(cards):
    s = build(cards, ["Topple", "Llanowar Elves"], ["Grizzly Bears", "Twisted Abomination"])
    put(s, "Llanowar Elves")
    bears = put(s, "Grizzly Bears", "p2")
    big = put(s, "Twisted Abomination", "p2")
    mana(s, W=1, C=2)
    topple = to_hand(s, "Topple")
    for small in (bears, card_named(s, "Llanowar Elves")):
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=topple.id, targets=[small.id])
    act(s, "p1", type="cast_spell", card_id=topple.id, targets=[big.id])  # 5 power: nobody has more
    settle(s)
    assert s.state.cards[big.id].zone == "p2:exile"
    check(s)


def test_topple_may_target_any_of_the_creatures_tied_for_greatest_power(cards):
    s = build(cards, ["Topple", "Grizzly Bears"], ["Grizzly Bears"])
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", "p2")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Topple").id, targets=[mine.id])  # both 2: either may be chosen
    settle(s)
    assert s.state.cards[mine.id].zone == "p1:exile" and s.state.cards[theirs.id].zone == "p2:battlefield"
    check(s)


@pytest.mark.parametrize(("target", "dies"), [("Llanowar Elves", True), ("Grizzly Bears", False)])
def test_wretched_banquet_destroys_only_the_creature_with_the_least_power(cards, target, dies):
    s = build(cards, ["Wretched Banquet", "Llanowar Elves"], ["Grizzly Bears"])
    put(s, "Llanowar Elves")
    put(s, "Grizzly Bears", "p2")
    mana(s, B=1)
    victim = card_named(s, target, "p1" if target == "Llanowar Elves" else "p2")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Wretched Banquet").id, targets=[victim.id])
    settle(s)
    assert (s.state.cards[victim.id].zone.endswith(":graveyard")) is dies
    check(s)


def test_culling_scales_destroys_the_nonland_permanent_with_the_lowest_mana_value(cards):
    s = build(cards, ["Culling Scales", "Llanowar Elves"], ["Grizzly Bears"])
    put(s, "Culling Scales")  # mana value 3
    elves = put(s, "Llanowar Elves")  # 1
    bears = put(s, "Grizzly Bears", "p2")  # 2
    to_phase(s, "main1", turn=3)
    assert s.state.cards[elves.id].zone == "p1:graveyard" and s.state.cards[bears.id].zone == "p2:battlefield"
    check(s)


def test_dense_foliage_stops_spells_targeting_creatures_but_not_players(cards):
    s = build(cards, ["Dense Foliage", "Grizzly Bears", "Lightning Bolt"])
    put(s, "Dense Foliage")
    bears = put(s, "Grizzly Bears")
    mana(s, R=2)
    bolt = to_hand(s, "Lightning Bolt")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[bears.id])
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    assert life(s, "p2") == 37
    check(s)


@pytest.mark.parametrize(("bob", "after"), [(40, 39), (10, 40)])
def test_vampire_lacerator_costs_life_unless_an_opponent_has_ten_or_less(cards, bob, after):
    s = build(cards, ["Vampire Lacerator"])
    put(s, "Vampire Lacerator")
    act(s, "p1", type="set_life", player="p2", value=bob)
    to_phase(s, "main1", turn=3)
    assert life(s) == after
    check(s)


@pytest.mark.parametrize(("named", "gained"), [("Grizzly Bears", 2), ("Lightning Bolt", 0)])
def test_lammastide_weave_gains_life_only_for_the_milled_card_with_the_chosen_name(cards, named, gained):
    from tests.test_rules_wave49c_names import run
    from tests.wave43b_kit import on_top

    s = build(cards, ["Lammastide Weave"], ["Grizzly Bears"])
    on_top(s, "Grizzly Bears", "p2")
    hand = len(s.state.zones["p1:hand"])
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lammastide Weave").id, targets=["p2"])
    run(s, named)
    assert life(s) == 40 + gained and len(s.state.zones["p1:hand"]) == hand + 1  # (it draws a card besides)
    check(s)


def test_an_opponent_at_zero_life_is_read_in_a_conditional_clause(cards):
    from app.rules import conditions

    s = build(cards, [])
    cond = conditions.parse("an opponent has 0 or less life", objects=True)
    assert not conditions.holds(Plan(s.state, "p1", s.cards, None), {"controller": "p1"}, cond)
    act(s, "p1", type="set_life", player="p2", value=0)
    assert conditions.holds(Plan(s.state, "p1", s.cards, None), {"controller": "p1"}, cond)
    assert not conditions.holds(Plan(s.state, "p2", s.cards, None), {"controller": "p2"}, cond)  # (Bob's opponent is Alice, who has 40)


def test_dwarven_lightsmith_pumps_the_creatures_you_control(cards):
    s = build(cards, ["Dwarven Lightsmith", "Grizzly Bears"], ["Grizzly Bears"])
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", "p2")
    mana(s, W=1, C=5)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Dwarven Lightsmith").id)
    settle(s)
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[mine.id]).pt == (3, 3)  # +1/+1 until end of turn
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[theirs.id]).pt == (2, 2)
    check(s)


def test_thrasher_brute_drains_when_it_or_another_warrior_enters(cards):
    s = build(cards, ["Thrasher Brute", "Decorated Champion"])
    champion = put(s, "Decorated Champion")
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Thrasher Brute").id, targets=["p2"])
    settle(s)
    assert life(s, "p2") == 39 and life(s) == 41  # its own trigger
    assert s.state.cards[champion.id].counters.get("+1/+1") == 1  # another Warrior entered under Alice's control
    check(s)


def test_decorated_champion_ignores_a_creature_that_is_not_a_warrior(cards):
    s = build(cards, ["Decorated Champion", "Grizzly Bears"])
    champion = put(s, "Decorated Champion")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Grizzly Bears").id)
    settle(s)
    assert not s.state.cards[champion.id].counters.get("+1/+1")
    check(s)


def test_combo_attack_has_two_of_your_creatures_deal_their_power_to_a_creature(cards):
    s = build(cards, ["Combo Attack", "Grizzly Bears", "Grizzly Bears"], ["Twisted Abomination"])
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"]
    for c in bears:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    big = put(s, "Twisted Abomination", "p2")  # 5/3
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Combo Attack").id, targets=[bears[0].id, bears[1].id, big.id], target_counts=[2, 1])
    settle(s)
    assert s.state.cards[big.id].zone == "p2:graveyard"  # 2 + 2 damage to a toughness 3
    check(s)


def test_triumph_of_gerrard_puts_its_counter_on_the_creature_you_control_with_the_greatest_power(cards):
    s = build(cards, ["Triumph of Gerrard", "Grizzly Bears", "Llanowar Elves"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Triumph of Gerrard").id)
    settle(s)
    assert s.state.cards[bears.id].counters.get("+1/+1") == 1 and not s.state.cards[elves.id].counters.get("+1/+1")
    check(s)


def test_favor_of_the_mighty_gives_protection_to_the_creature_with_the_greatest_mana_value(cards):
    s = build(cards, ["Favor of the Mighty", "Grizzly Bears"], ["Twisted Abomination"])
    put(s, "Grizzly Bears")
    put(s, "Favor of the Mighty")
    big = put(s, "Twisted Abomination", "p2")  # mana value 6
    plan = Plan(s.state, "p1", s.cards, None)
    assert any("rotection from each color" in a.text for a in plan.ch(s.state.cards[big.id]).abilities)
    assert not any("rotection" in a.text for a in chars(s, "Grizzly Bears").abilities)
    check(s)


@pytest.mark.parametrize(("bobs", "draws"), [([], True), (["Twisted Abomination"], False)])
def test_historians_wisdom_draws_only_for_the_creature_with_the_greatest_power(cards, bobs, draws):
    s = build(cards, ["Historian's Wisdom", "Grizzly Bears"], bobs)
    bears = put(s, "Grizzly Bears")
    for name in bobs:
        put(s, name, "p2")  # power 5 against Alice's 2 + 2
    wisdom = to_hand(s, "Historian's Wisdom")
    hand = len(s.state.zones["p1:hand"])
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=wisdom.id, targets=[bears.id])
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + (1 if draws else 0)
    check(s)


@pytest.mark.parametrize("bigger", [False, True])
def test_strength_testing_hammer_draws_when_the_equipped_creature_has_the_greatest_power(cards, bigger):
    s = build(cards, ["Strength-Testing Hammer", "Grizzly Bears", "Twisted Abomination", "Giant Growth", "Giant Growth", "Giant Growth"])
    bears = put(s, "Grizzly Bears")
    attach(s, put(s, "Strength-Testing Hammer"), bears)
    big = put(s, "Twisted Abomination")
    to_phase(s, "main1", turn=3)
    if bigger:
        for _ in range(3):
            mana(s, G=1)
            act(s, "p1", type="cast_spell", card_id=to_hand(s, "Giant Growth").id, targets=[big.id])
            settle(s)  # 5 + 9 = 14 against at most 2 + 6
    else:
        act(s, "p1", type="move", card_ids=[big.id], to={"zone": "graveyard"})
    hand = len(s.state.zones["p1:hand"])
    attack(s, bears)
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand + (0 if bigger else 1)
    check(s)


def test_alarum_untaps_and_pumps_a_creature_that_is_not_attacking(cards):
    s = build(cards, ["Alarum", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="tap", card_ids=[bears.id])
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Alarum").id, targets=[bears.id])
    settle(s)
    assert not s.state.cards[bears.id].tapped and Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bears.id]).pt == (3, 5)
    check(s)


def test_alarum_cannot_target_an_attacking_creature(cards):
    s = build(cards, ["Alarum", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    stops(s)
    attack(s, bears)
    mana(s, W=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Alarum").id, targets=[bears.id])
    check(s)


def test_unlikely_alliance_needs_a_creature_that_neither_attacks_nor_blocks(cards):
    s = build(cards, ["Unlikely Alliance", "Grizzly Bears"])
    alliance = put(s, "Unlikely Alliance")
    bears = put(s, "Grizzly Bears")
    mana(s, W=1, C=1)
    act(s, "p1", type="activate_ability", card_id=alliance.id, ability=0, targets=[bears.id])
    settle(s)
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bears.id]).pt == (2, 4)
    check(s)


def test_an_unblocked_attacker_assigns_no_combat_damage_and_the_defender_loses_life(cards):
    """Lim-D\u00fbl's Paladin has the same sentence (4 life) but an upkeep cost of its own, so Keeper of Tresserhorn shows it."""
    s = build(cards, ["Keeper of Tresserhorn"])
    attacker = put(s, "Keeper of Tresserhorn")
    to_phase(s, "main1", turn=3)
    stops(s)
    attack(s, attacker)
    to_phase(s, "main2")
    assert life(s, "p2") == 38  # (the power it would have dealt is not assigned)
    check(s)


def test_murk_dwellers_gets_plus_two_only_until_the_end_of_combat(cards):
    s = build(cards, ["Murk Dwellers"])
    dwellers = put(s, "Murk Dwellers")
    to_phase(s, "main1", turn=3)
    stops(s)
    attack(s, dwellers)
    to_phase(s, "combat_damage")
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[dwellers.id]).pt == (4, 2)
    to_phase(s, "main2")
    assert life(s, "p2") == 36 and Plan(s.state, "p1", s.cards, None).ch(s.state.cards[dwellers.id]).pt == (2, 2)  # (it dealt 4; the pump is over)
    check(s)


def test_jade_statue_is_a_creature_only_during_combat(cards):
    s = build(cards, ["Jade Statue"])
    statue = put(s, "Jade Statue")
    mana(s, C=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=statue.id, ability=0)  # not during combat
    stops(s)
    to_phase(s, "declare_attackers")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=statue.id, ability=0)
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[statue.id])
    assert ch.types == {"Artifact", "Creature"} and ch.pt == (3, 6) and "Golem" in ch.subtypes
    to_phase(s, "main2")
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[statue.id]).types == {"Artifact"}
    check(s)


def test_glyph_of_destruction_pumps_the_blocking_wall_for_the_combat_only(cards):
    s = build(cards, ["Grizzly Bears"], ["Wall of Omens", "Glyph of Destruction"])
    bears = put(s, "Grizzly Bears")
    wall = put(s, "Wall of Omens", "p2")
    glyph = to_hand(s, "Glyph of Destruction", "p2")
    to_phase(s, "main1", turn=3)
    stops(s)
    attack(s, bears)
    d = ask(s)
    assert d.kind == "declare_blockers"
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": bears.id}])
    act(s, "p1", type="pass_priority")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=glyph.id, targets=[wall.id])
    settle(s)
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[wall.id]).pt == (10, 4)
    to_phase(s, "main2")
    assert s.state.cards[bears.id].zone == "p1:graveyard"  # 10 damage from the Wall
    assert s.state.cards[wall.id].damage == 0 and Plan(s.state, "p1", s.cards, None).ch(s.state.cards[wall.id]).pt == (0, 4)  # (prevented; and the +10/+0 ended with the combat)
    check(s)


def test_an_ability_may_still_target_a_creature_spells_cannot_target(cards):
    s = build(cards, ["Dense Foliage", "Granite Shard", "Grizzly Bears"])
    put(s, "Dense Foliage")
    shard = put(s, "Granite Shard")
    bears = put(s, "Grizzly Bears")
    mana(s, R=1)
    act(s, "p1", type="activate_ability", card_id=shard.id, ability=1, targets=[bears.id])  # an ability: 115.2 names spells only
    settle(s)
    assert s.state.cards[bears.id].damage == 1
    check(s)


def test_an_aura_spell_cannot_target_a_creature_either(cards):
    s = build(cards, ["Dense Foliage", "Pacifism", "Grizzly Bears"])
    put(s, "Dense Foliage")
    bears = put(s, "Grizzly Bears")
    mana(s, W=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Pacifism").id, targets=[bears.id])  # 303.4a: an Aura spell targets
    check(s)


def test_ruthless_instincts_first_mode_needs_a_nonattacking_creature(cards):
    s = build(cards, ["Ruthless Instincts", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="tap", card_ids=[bears.id])
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Ruthless Instincts").id, modes=[0], targets=[bears.id])
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bears.id])
    assert not s.state.cards[bears.id].tapped and {"reach", "deathtouch"} <= set(ch.keywords)
    check(s)


def test_kaervek_s_hex_hits_nonblack_creatures_and_green_ones_twice(cards):
    s = build(cards, ["Kaervek's Hex", "Grizzly Bears", "Dregscape Zombie"])
    bears = put(s, "Grizzly Bears")  # green: 1 + 1
    zombie = put(s, "Dregscape Zombie")  # black: neither
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Kaervek's Hex").id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard" and s.state.cards[zombie.id].zone == "p1:battlefield" and s.state.cards[zombie.id].damage == 0
    check(s)


def test_tropical_storm_deals_its_extra_damage_to_blue_creatures_only(cards):
    s = build(cards, ["Tropical Storm", "Mulldrifter", "Merfolk Looter", "Grizzly Bears"])
    flyer = put(s, "Mulldrifter")  # blue, flying: X + 1
    looter = put(s, "Merfolk Looter")  # blue, no flying: nothing (the 1 additional is for blue creatures "and" the first for flying ones)
    bears = put(s, "Grizzly Bears")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Tropical Storm").id, x_value=2)
    settle(s)
    assert s.state.cards[flyer.id].zone == "p1:graveyard" and s.state.cards[bears.id].damage == 0
    assert s.state.cards[looter.id].zone == "p1:graveyard"  # 1 additional damage to a 1/1 blue creature
    check(s)


def test_hail_storm_hits_attackers_harder_and_you_and_your_creatures_lightly(cards):
    s = build(cards, ["Hail Storm", "Grizzly Bears", "Llanowar Elves"])
    bears = put(s, "Grizzly Bears")
    elves = put(s, "Llanowar Elves")
    to_phase(s, "main1", turn=3)
    stops(s)
    attack(s, bears)
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Hail Storm").id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"  # 2 as an attacker + 1 as your creature
    assert s.state.cards[elves.id].zone == "p1:graveyard" and life(s) == 39  # 1 damage to a 1/1 you control, and 1 to you
    check(s)


def test_firespout_hits_what_the_spent_mana_names(cards):
    s = build(cards, ["Firespout", "Grizzly Bears", "Mulldrifter"])
    bears = put(s, "Grizzly Bears")
    flyer = put(s, "Mulldrifter")
    mana(s, R=1, C=2)  # only {R} was spent: the creatures without flying
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Firespout").id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard" and s.state.cards[flyer.id].zone == "p1:battlefield" and s.state.cards[flyer.id].damage == 0
    check(s)


def test_firespout_does_both_when_both_colors_were_spent(cards):
    s = build(cards, ["Firespout", "Grizzly Bears", "Mulldrifter"])
    bears = put(s, "Grizzly Bears")
    flyer = put(s, "Mulldrifter")
    mana(s, R=1, G=1, C=1)  # {2}{R/G}: {R} for the hybrid symbol, {G} and {C} for the generic part
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Firespout").id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard" and s.state.cards[flyer.id].zone == "p1:graveyard"
    check(s)
