"""Wave 110J: single-card wordings, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario checks the replay and a save and a load.

* 613.4c, 107.1a: Aspect of Wolf gives +X/+Y, X half the Forests its controller has (rounded down), Y half of them (rounded up).
* 611.2a, 305.7, 502.3: Orcish Farmer makes a land a Swamp until its controller's next untap step — the land's controller, not the Farmer's.
* 602.2, 611.2a: Bronze Cudgels pumps by the number of times its ability has resolved this turn (1, then 2: +3 in all), and starts over next turn.
* 508.1, 603.2: Mob Mentality triggers only when every non-Wall creature its controller has is attacking (a Wall may stay home); +X/+0 counts the attackers.
* 502.3, 611.2a: Mindbender Spores puts four fungus counters on the creature it blocks, which then stays tapped through its controller's untap step
  while it has one, and loses one at each of its controller's upkeeps.
* 608.2c, 115.1: Cannibalize targets two creatures of one player; its caster picks which is exiled, the other gets two +1/+1 counters.
* 613.1e-f: Ray of Frost removes all abilities only while the enchanted creature is red.
* 303.4f, 704.3: Kudzu / Steam Vines destroy the land when it becomes tapped; its controller may then move the Aura to any land.
* 702.24a, 603.2: Hibernation's End triggers each time its cumulative upkeep is paid, not when it is sacrificed.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110b_kit import attack, through_combat
from tests.wave110j_kit import (  # noqa: F401
    EXTRA,
    ability,
    activate,
    card_db,
    cast_on,
    ch,
    check,
    cost,
    full,
    mana,
    move,
    now,
    put,
    put_new,
    refused,
    settle,
    to_hand,
    to_phase,
)


@pytest.mark.parametrize("name", ["Aspect of Wolf", "Orcish Farmer", "Bronze Cudgels", "Mob Mentality", "Mindbender Spores"])
def test_the_cards_are_full(name):
    assert full(name)


@pytest.mark.parametrize(("forests", "bonus"), [(0, (0, 0)), (1, (0, 1)), (4, (2, 2)), (5, (2, 3))])
def test_aspect_of_wolf_rounds_each_half_its_own_way(cards, forests, bonus):
    s = build(cards, ["Aspect of Wolf", "Templar Knight"])
    knight = put_new(s, "Templar Knight")
    for _ in range(forests):
        put_new(s, "Forest")
    base = ch(s, knight).pt
    cast_on(s, "Aspect of Wolf", knight)
    assert tuple(int(a) - int(b) for a, b in zip(ch(s, knight).pt, base, strict=True)) == bonus
    check(s)


def ready(s, c):
    s.state.rules.controlled_since[c.id].turn = 0


def types(s, c):
    return set(ch(s, c).subtypes)


@pytest.mark.parametrize(("owner", "still_a_swamp_on_turn_2"), [("p2", False), ("p1", True)])
def test_orcish_farmer_lasts_until_the_lands_controllers_next_untap_step(cards, owner, still_a_swamp_on_turn_2):
    s = build(cards, ["Orcish Farmer"])
    farmer = put(s, "Orcish Farmer")
    ready(s, farmer)
    land = put_new(s, "Island" if owner == "p2" else "Forest", owner)
    base = types(s, land)
    activate(s, farmer, "{T}", targets=[land.id])
    assert types(s, land) == {"Swamp"} and base != {"Swamp"}
    to_phase(s, "main1", turn=2)
    assert (types(s, land) == {"Swamp"}) is still_a_swamp_on_turn_2
    to_phase(s, "main1", turn=3)
    assert types(s, land) == base
    check(s)


def test_bronze_cudgels_counts_its_resolutions(cards):
    s = build(cards, ["Bronze Cudgels", "Templar Knight"])
    knight, cudgels = put_new(s, "Templar Knight"), put(s, "Bronze Cudgels")
    mana(s, C=1)
    activate(s, cudgels, "Equip", targets=[knight.id])
    base = int(ch(s, knight).pt[0])
    for total in (1, 3, 6):
        mana(s, C=2)
        activate(s, cudgels, "{2}")
        assert int(ch(s, knight).pt[0]) == base + total
    to_phase(s, "main1", turn=3)
    mana(s, C=2)
    activate(s, cudgels, "{2}")
    assert int(ch(s, knight).pt[0]) == base + 1
    check(s)


@pytest.mark.parametrize(("stay_home", "bonus"), [("Wall of Stone", 2), ("Templar Knight", 0)])
def test_mob_mentality_needs_every_non_wall_creature_to_attack(cards, stay_home, bonus):
    s = build(cards, ["Mob Mentality", "Grizzly Bears", "Templar Knight", "Wall of Stone"])
    crew = {n: put_new(s, n) for n in ("Grizzly Bears", "Templar Knight", "Wall of Stone")}
    cast_on(s, "Mob Mentality", crew["Grizzly Bears"])
    base = int(ch(s, crew["Grizzly Bears"]).pt[0])
    attack(s, *(c for n, c in crew.items() if n != stay_home and n != "Wall of Stone"))
    settle(s)
    assert int(ch(s, crew["Grizzly Bears"]).pt[0]) == base + bonus
    check(s)


def test_mindbender_spores_keeps_the_blocked_creature_tapped_until_the_counters_run_out(cards):
    s = build(cards, ["Grizzly Bears"], ["Mindbender Spores"])
    bears, spores = put_new(s, "Grizzly Bears"), put(s, "Mindbender Spores", "p2")
    attack(s, bears)
    through_combat(s, [(spores, bears)])
    assert s.state.cards[bears.id].counters == {"fungus": 4} and s.state.cards[bears.id].tapped
    for turn, left in ((3, 3), (5, 2)):
        to_phase(s, "main1", turn=turn)
        assert s.state.cards[bears.id].counters == {"fungus": left} and s.state.cards[bears.id].tapped
    check(s)


def test_loki_is_full():
    assert full("Loki, God of Lies")


def test_loki_steals_the_spells_single_target_until_end_of_turn(cards):
    """115.9c, 611.2b: Loki takes the creature a spell targets; on its controller's turn it also untaps and gains haste; control ends at cleanup."""
    s = build(cards, ["Loki, God of Lies", "Aspect of Wolf", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Loki, God of Lies")
    bears = put_new(s, "Grizzly Bears", "p2")
    act(s, "p2", type="tap", card_ids=[bears.id])
    mana(s, G=1, C=1)
    cast_on(s, "Aspect of Wolf", bears)
    assert now(s, bears).controller == "p1" and not now(s, bears).tapped
    assert "haste" in ch(s, bears).keywords
    to_phase(s, "main1", turn=2)
    assert now(s, bears).controller == "p2"
    check(s)


def test_lithoform_blight_is_full():
    assert full("Lithoform Blight")


def test_lithoform_blight_replaces_a_lands_types_and_abilities(cards):
    """305.7, 613.1d, 613.1f: the land has no land types (so no intrinsic mana ability), only the two granted mana abilities; the Aura draws on entering."""
    s = build(cards, ["Lithoform Blight", "Forest"])
    forest = put_new(s, "Forest")
    assert "Forest" in ch(s, forest).subtypes
    hand = len(s.state.zones["p1:hand"])
    cast_on(s, "Lithoform Blight", forest)
    now_ch = ch(s, forest)
    assert not now_ch.subtypes and "Land" in now_ch.types
    assert sorted(a.text for a in now_ch.abilities if "Add" in a.text) == ["{T}, Pay 1 life: Add one mana of any color.", "{T}: Add {C}."]
    assert len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_love_on_the_battlefield_is_full():
    assert full("Love on the Battlefield")


@pytest.mark.parametrize(("attackers", "triggers"), [(1, False), (2, True), (3, False)])
def test_love_on_the_battlefield_needs_exactly_two_attackers(cards, attackers, triggers):
    """508.1, 603.2: exactly two attackers give first strike and a card; each unblocked one then grows by a +1/+1 counter when it hits a player."""
    s = build(cards, ["Love on the Battlefield", "Grizzly Bears", "Templar Knight", "Llanowar Elves"])
    put(s, "Love on the Battlefield")
    crew = [put_new(s, n) for n in ("Grizzly Bears", "Templar Knight", "Llanowar Elves")][:attackers]
    hand = len(s.state.zones["p1:hand"])
    attack(s, *crew)
    settle(s)
    assert (len(s.state.zones["p1:hand"]) == hand + 1) is triggers
    assert all(("first strike" in ch(s, c).keywords) is triggers for c in crew)
    through_combat(s)
    assert all((now(s, c).counters.get("+1/+1") == 1) is triggers for c in crew)
    check(s)


def test_rootwater_matriarch_is_full():
    assert full("Rootwater Matriarch")


@pytest.mark.parametrize("enchanted", [True, False])
def test_rootwater_matriarch_keeps_the_creature_only_while_it_is_enchanted(cards, enchanted):
    """611.2b, 303.4: control lasts while an Aura is attached to the creature, and does nothing if it has none as the ability resolves."""
    s = build(cards, ["Rootwater Matriarch", "Aspect of Wolf"], ["Grizzly Bears"])
    matriarch, bears = put(s, "Rootwater Matriarch"), put_new(s, "Grizzly Bears", "p2")
    ready(s, matriarch)
    aura = cast_on(s, "Aspect of Wolf", bears) if enchanted else None
    activate(s, matriarch, "{T}", targets=[bears.id])
    assert (now(s, bears).controller == "p1") is enchanted
    if enchanted:
        move(s, aura, "graveyard")
        act(s, "p1", type="pass_priority")  # (a table edit is looked at on the next intent)
        assert now(s, bears).controller == "p2"
    check(s)


def test_silumgar_scavenger_is_full():
    assert full("Silumgar Scavenger")


def test_silumgar_scavenger_gets_haste_only_for_the_creature_it_exploited(cards):
    """702.110b, 603.2: it grows for any other creature you control that dies, but gains haste only when it exploited that creature."""
    s = build(cards, ["Silumgar Scavenger", "Grizzly Bears", "Templar Knight", "Lightning Bolt"])
    bears, knight = put_new(s, "Grizzly Bears"), put_new(s, "Templar Knight")
    scavenger = cast_on(s, "Silumgar Scavenger")
    assert now(s, scavenger).zone.endswith(":battlefield") is True
    exploited = bears if now(s, bears).zone.endswith(":graveyard") else knight
    other = knight if exploited is bears else bears
    assert now(s, exploited).zone.endswith(":graveyard")
    assert now(s, scavenger).counters == {"+1/+1": 1} and "haste" in ch(s, scavenger).keywords
    to_phase(s, "main1", turn=3)
    assert "haste" not in ch(s, scavenger).keywords
    cast_on(s, "Lightning Bolt", other)
    assert now(s, scavenger).counters == {"+1/+1": 2} and "haste" not in ch(s, scavenger).keywords
    check(s)


@pytest.mark.parametrize("name", ["Cannibalize", "Ray of Frost", "Kudzu", "Steam Vines", "Hibernation's End"])
def test_wave_two_cards_are_full(name):
    assert full(name)


def test_cannibalize_caster_exiles_one_and_the_other_grows(cards):
    s = build(cards, ["Cannibalize", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears", "Llanowar Elves"])
    a, b = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Llanowar Elves", "p2")
    mana(s, B=1, C=1)
    c = to_hand(s, "Cannibalize")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[a.id, b.id], target_counts=[2])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"  # the caster chooses (608.2c)
    settle(s, answers=[[a.id]])
    assert now(s, a).zone.endswith(":exile") and now(s, b).counters == {"+1/+1": 2}
    check(s)


def test_cannibalize_refuses_creatures_of_two_players(cards):
    s = build(cards, ["Cannibalize", "Grizzly Bears"], ["Grizzly Bears"])
    a, b = put_new(s, "Grizzly Bears", "p1"), put_new(s, "Grizzly Bears", "p2")
    mana(s, B=1, C=1)
    c = to_hand(s, "Cannibalize")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, targets=[a.id, b.id], target_counts=[2])


@pytest.mark.parametrize(("who", "bare"), [("Mogg Fanatic", True), ("Llanowar Elves", False)])
def test_ray_of_frost_only_strips_red_creatures(cards, who, bare):
    s = build(cards, ["Ray of Frost", "Mogg Fanatic", "Llanowar Elves"])
    c = put_new(s, who)
    before = len(ch(s, c).abilities)
    cast_on(s, "Ray of Frost", c)
    assert (len(ch(s, c).abilities) == 0) is (bare and before > 0) and (bare or len(ch(s, c).abilities) == before)
    check(s)


@pytest.mark.parametrize("aura", ["Kudzu", "Steam Vines"])
def test_land_aura_destroys_the_tapped_land_and_moves_to_a_land_of_its_controllers_choice(cards, aura):
    s = build(cards, [aura, "Forest", "Mountain"], ["Forest"])
    forest, mountain = put_new(s, "Forest"), put_new(s, "Mountain")
    cast_on(s, aura, forest)
    hp = s.state.players["p1"].life
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=ability(s, forest, "{T}"))
    for _ in range(10):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and mountain.id in {o.id for o in d.options}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[mountain.id])
    settle(s)
    assert now(s, forest).zone.endswith(":graveyard")
    aura_card = next(c for c in s.state.cards.values() if c.name == aura)
    assert aura_card.attached_to == mountain.id
    assert s.state.players["p1"].life == hp - (1 if aura == "Steam Vines" else 0)
    check(s)


def test_hibernations_end_searches_each_time_the_upkeep_is_paid_but_not_when_sacrificed(cards):
    s = build(cards, ["Hibernation's End", "Llanowar Elves", "Forest", "Forest"])
    end = put(s, "Hibernation's End")
    put_new(s, "Forest")
    for _ in range(300):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_one" and (d.resume or {}).get("step") == "pay_or_sacrifice":
            break
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    settle(s)  # the may-search: the first option is "yes"
    assert now(s, end).counters == {"age": 1}
    elves = [c for c in s.state.cards.values() if c.name == "Llanowar Elves"]
    assert elves[0].zone.endswith(":battlefield")
    check(s)


def test_rumbling_ruin_is_full():
    assert full("Rumbling Ruin")


@pytest.mark.parametrize("counters", [0, 2, 3])
def test_rumbling_ruin_stops_blockers_with_power_up_to_the_counters_counted(cards, counters):
    """611.2c: the count is made as the trigger resolves; creatures with power at most that number can't block this turn."""
    s = build(cards, ["Rumbling Ruin", "Llanowar Elves"], ["Mogg Fanatic", "Templar Knight"])
    mine = put_new(s, "Llanowar Elves")
    small, big = put_new(s, "Mogg Fanatic", "p2"), put_new(s, "Templar Knight", "p2")
    sp, bp = int(ch(s, small).pt[0]), int(ch(s, big).pt[0])
    assert sp < bp
    if counters:
        act(s, "p1", type="set_counter", card_id=mine.id, kind="+1/+1", value=counters)
    cast_on(s, "Rumbling Ruin")
    settle(s)
    stopped = {c.id for c in (small, big) if int(ch(s, c).pt[0]) <= counters}
    assert {c.id for c in (small, big) if "cant_block" in ch(s, c).imposed} == stopped
    check(s)


def test_kongmings_contraptions_is_full():
    assert full("Kongming's Contraptions")


@pytest.mark.parametrize("attacked", [True, False])
def test_kongmings_contraptions_only_when_attacked_in_the_declare_attackers_step(cards, attacked):
    """506.3, 602.5b: only in the declare attackers step and only while creatures attack its controller."""
    s = build(cards, ["Templar Knight", "Kongming's Contraptions"], ["Kongming's Contraptions"])
    knight = put_new(s, "Templar Knight")
    kong = put_new(s, "Kongming's Contraptions", "p2" if attacked else "p1")
    to_phase(s, "main1", turn=3)  # (past each controller's first turn: no summoning sickness for the {T} cost)
    act(s, "p2", type="set_stops", own=[], others=["declare_attackers"], smart_pass=False)
    act(s, "p1", type="set_stops", own=["declare_attackers"], others=[], smart_pass=False)
    act(s, "p1", type="pass_priority")
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": knight.id, "target": "p2"}])
    assert s.state.turn.phase == "declare_attackers"
    if attacked:
        act(s, "p1", type="pass_priority")
        activate(s, kong, "{T}:", pid="p2", targets=[knight.id])
        assert now(s, knight).zone.endswith(":graveyard")  # (2 damage kills the 2/2)
        check(s)
    else:
        refused(s, "attack", kong, "{T}:", targets=[knight.id])


def test_earthbind_is_full():
    assert full("Earthbind")


@pytest.mark.parametrize("flier", [True, False])
def test_earthbind_hurts_and_grounds_only_a_flier(cards, flier):
    """611.3a, 400.7: the Aura deals 2 damage to a flying creature and gains the ability; a ground creature is left alone."""
    name = "Serra Angel" if flier else "Templar Knight"
    s = build(cards, ["Earthbind", name])
    c = put_new(s, name)
    assert ("flying" in ch(s, c).keywords) is flier
    aura = cast_on(s, "Earthbind", c)
    assert (now(s, c).damage == 2) is flier and "flying" not in ch(s, c).keywords
    assert aura.zone.endswith(":battlefield")
    check(s)


def test_splintering_wind_is_full():
    assert full("Splintering Wind")


def test_splintering_wind_token_deals_damage_to_you_and_your_creatures_when_it_leaves(cards):
    """603.7, 608.2h: when the Splinter leaves, it deals 1 damage to its creator and each creature they control; the 1 damage to the target came first."""
    s = build(cards, ["Splintering Wind", "Llanowar Elves", "Lightning Bolt"], ["Llanowar Elves"])
    wind, mine, theirs = put_new(s, "Splintering Wind"), put_new(s, "Llanowar Elves"), put_new(s, "Llanowar Elves", "p2")
    mana(s, "p1", G=3)
    activate(s, wind, "{2}{G}", targets=[theirs.id])
    assert now(s, theirs).zone.endswith(":graveyard")
    token = next(c for c in s.state.cards.values() if c.name == "Splinter" and c.zone.endswith(":battlefield"))
    assert {"flying"} <= ch(s, token).keywords
    life = s.state.players["p1"].life
    cast_on(s, "Lightning Bolt", token)
    assert s.state.players["p1"].life == life - 1 and now(s, mine).zone.endswith(":graveyard")
    check(s)


def test_shimatsu_is_full():
    assert full("Shimatsu the Bloodcloaked")


@pytest.mark.parametrize("n", [0, 1, 2])
def test_shimatsu_sacrifices_any_number_of_permanents_for_that_many_counters(cards, n):
    """614.1c, 702.82a-style entry choice: as Shimatsu enters, sacrifice any number of permanents (zero allowed, lands too); one +1/+1 counter each."""
    s = build(cards, ["Shimatsu the Bloodcloaked", "Grizzly Bears", "Forest"])
    bears, forest = put_new(s, "Grizzly Bears"), put_new(s, "Forest")
    picks = [bears.id, forest.id][:n]
    c = to_hand(s, "Shimatsu the Bloodcloaked")
    mana(s, "p1", **cost("Shimatsu the Bloodcloaked"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s, answers=[*picks, "done"])
    assert now(s, c).zone.endswith(":battlefield" if n else ":graveyard")  # (0/0 with no counters: 704.5f)
    assert now(s, c).counters.get("+1/+1", 0) == n or not n
    assert [now(s, x).zone.endswith(":graveyard") for x in (bears, forest)] == [i < n for i in range(2)]
    check(s)


def test_razor_boomerang_is_full():
    assert full("Razor Boomerang")


def test_razor_boomerang_unattaches_pings_and_returns_to_its_owners_hand(cards):
    """602.2, 701.3b, 120.3: the equipped creature taps and the Equipment is unattached as a cost; the Equipment (the source) deals 1 damage, then goes to hand."""
    s = build(cards, ["Razor Boomerang", "Grizzly Bears"])
    bears, rb = put_new(s, "Grizzly Bears"), put_new(s, "Razor Boomerang")
    ready(s, bears)
    mana(s, "p1", C=2)
    activate(s, rb, "Equip {2}", targets=[bears.id])
    assert now(s, rb).attached_to == bears.id
    before = s.state.players["p2"].life
    activate(s, bears, "{T}, Unattach", targets=["p2"])
    assert s.state.players["p2"].life == before - 1 and now(s, bears).tapped
    assert now(s, rb).zone == "p1:hand"
    check(s)


def test_war_historian_is_full():
    assert full("War Historian")


@pytest.mark.parametrize("battle", [True, False])
def test_war_historian_is_indestructible_only_once_it_attacked_a_battle(cards, battle):
    """310.5, 508.1, 611.3a: indestructible for the turn once it was declared as an attacker against a battle; not when it attacked a player."""
    from tests.test_rules_review34_head import SIEGE, bobs_attack, drive, seasoned

    s = build(cards, [], [SIEGE, "War Historian"])
    hist, siege = put(s, "War Historian", "p2"), put(s, SIEGE, "p2")
    act(s, "p2", type="counter", card_ids=[siege.id], kind="defense", delta=4)
    drive(s, lambda d: "p1" if "p1" in [o.id for o in d.options] else None)
    seasoned(s, hist)
    assert "indestructible" not in ch(s, hist).keywords
    bobs_attack(s, [(hist, siege.id if battle else "p1")])
    drive(s)
    assert ("indestructible" in ch(s, hist).keywords) is battle
    check(s)


def test_wiitigo_cards_are_full():
    assert full("Wiitigo") and full("Shape of the Wiitigo")


def _block_scenario(cards, host_name, how):
    """Bob's Bears attack Alice on turn 2; Alice's creature blocks it (or not, or Bob doesn't attack); returns the state, the creature."""
    s = build(cards, [host_name, "Shape of the Wiitigo", "Wall of Stone"], ["Grizzly Bears"])
    host = put_new(s, host_name if host_name != "Shape of the Wiitigo" else "Wall of Stone")
    act(s, "p1", type="counter", card_ids=[host.id], kind="+1/+1", delta=3)
    if host_name == "Shape of the Wiitigo":
        mana(s, "p1", G=1, C=1)
        cast_on(s, "Shape of the Wiitigo", host)
    bears = put_new(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=2)
    if how != "none":
        ready(s, bears)
        while s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
        while (d := s.state.rules.decision) is None or d.kind != "declare_blockers":
            act(s, s.state.rules.priority, type="pass_priority")
        blocks = [{"blocker_id": host.id, "attacker_id": bears.id}] if how == "block" else []
        act(s, "p1", type="declare_blockers", blocks=blocks)
    return s, host


@pytest.mark.parametrize("host_name", ["Wiitigo", "Shape of the Wiitigo"])
@pytest.mark.parametrize(("how", "delta"), [("block", 1), ("unblocked", -1), ("none", -1)])
def test_wiitigo_counts_from_the_last_upkeep(cards, host_name, how, delta):
    """503.1, 509.1g: +1/+1 counter at your upkeep if it blocked or was blocked (attacked or blocked: the Aura) since your last upkeep, else it loses one."""
    s, host = _block_scenario(cards, host_name, how)
    counters = now(s, host).counters["+1/+1"] + delta  # (Shape of the Wiitigo puts six on it as it enters)
    to_phase(s, "upkeep", turn=3)
    settle(s)
    assert now(s, host).counters.get("+1/+1") == counters
    to_phase(s, "upkeep", turn=5)  # (nothing happened since the turn-3 upkeep: it shrinks by one)
    settle(s)
    assert now(s, host).counters.get("+1/+1") == counters - 1
    check(s)
