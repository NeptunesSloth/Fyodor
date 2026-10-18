"""Wave 53B: a value chosen as the spell or ability resolves, used as the filter of the instructions after it (CR 608.2c-d, 205.2a, 105.1,
205.3m): "Choose a color. … discards all cards of that color", "Choose a card type, then reveal the top four cards … all cards of the chosen
type revealed this way", "Choose a permanent type. Return all cards of the chosen type from your graveyard". Real Oracle text
(tests/fixtures/wave53b_cards.json, from data/cards.sqlite); every scenario checks the replay and a save and a load.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave12a_counters_keywords import answer, on_top
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of
from tests.wave53b_kit import open_repo


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", ["Persecute", "Vigean Intuition", "Winding Way", "Creeping Renaissance", "Addle", "Crosis, the Purger", "Searing Rays"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def option_ids(s):
    return [o.id for o in s.state.rules.decision.options]


def cast(s, name, *, targets=None, **pool):
    c = to_hand(s, name)
    mana(s, "p1", **pool)
    act(s, "p1", type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}))
    return c


def test_persecute_discards_every_card_of_the_color_chosen_as_it_resolves(cards):
    s = build(cards, ["Persecute"], ["Probe Bolt", "Probe Goblin", "Probe Elf", "Probe Relic"])
    for n in ("Probe Bolt", "Probe Goblin", "Probe Elf", "Probe Relic"):
        to_hand(s, n, "p2")
    cast(s, "Persecute", targets=["p2"], B=2, C=2)
    assert s.state.rules.decision.player == "p1" and option_ids(s) == ["White", "Blue", "Black", "Red", "Green"]
    answer(s, "Red")
    assert [zone_of(s, n, "p2") for n in ("Probe Bolt", "Probe Goblin", "Probe Elf", "Probe Relic")] == ["p2:graveyard", "p2:graveyard", "p2:hand", "p2:hand"]  # (colorless is no color: 105.2c)
    check(s)


def test_vigean_intuition_takes_the_cards_of_the_chosen_type_and_mills_the_rest(cards):
    s = build(cards, ["Vigean Intuition", "Probe Land", "Probe Elf", "Probe Relic", "Probe Rock"])
    for n in ("Probe Rock", "Probe Relic", "Probe Elf", "Probe Land"):
        on_top(s, n, "p1")
    cast(s, "Vigean Intuition", G=1, U=1, C=3)
    assert len(option_ids(s)) == 9 and "Land" in option_ids(s)
    answer(s, "Artifact")  # Probe Rock is an artifact creature: an artifact
    assert (zone_of(s, "Probe Relic"), zone_of(s, "Probe Rock")) == ("p1:hand", "p1:hand")
    assert (zone_of(s, "Probe Land"), zone_of(s, "Probe Elf")) == ("p1:graveyard", "p1:graveyard")
    check(s)


def test_winding_way_offers_only_the_two_types_it_lists(cards):
    s = build(cards, ["Winding Way", "Probe Land", "Probe Elf", "Probe Relic", "Probe Rock"])
    for n in ("Probe Rock", "Probe Relic", "Probe Elf", "Probe Land"):
        on_top(s, n, "p1")
    cast(s, "Winding Way", G=1, C=1)
    assert option_ids(s) == ["Creature", "Land"]
    answer(s, "Creature")
    assert sorted(zone_of(s, n) for n in ("Probe Elf", "Probe Rock")) == ["p1:hand", "p1:hand"]
    assert (zone_of(s, "Probe Land"), zone_of(s, "Probe Relic")) == ("p1:graveyard", "p1:graveyard")
    check(s)


def test_creeping_renaissance_offers_the_six_permanent_types(cards):
    s = build(cards, ["Creeping Renaissance", "Probe Relic", "Probe Elf", "Probe Bolt"])
    for n in ("Probe Relic", "Probe Elf", "Probe Bolt"):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    cast(s, "Creeping Renaissance", G=2, C=3)
    assert option_ids(s) == ["Artifact", "Battle", "Creature", "Enchantment", "Land", "Planeswalker"]
    answer(s, "Artifact")
    assert (zone_of(s, "Probe Relic"), zone_of(s, "Probe Elf"), zone_of(s, "Probe Bolt")) == ("p1:hand", "p1:graveyard", "p1:graveyard")
    check(s)


def test_addle_chooses_one_card_of_the_color_named(cards):
    s = build(cards, ["Addle"], ["Probe Bolt", "Probe Goblin", "Probe Elf"])
    for n in ("Probe Bolt", "Probe Goblin", "Probe Elf"):
        to_hand(s, n, "p2")
    cast(s, "Addle", targets=["p2"], B=1, C=1)
    answer(s, "Red", card_named(s, "Probe Goblin", "p2").id)
    assert [zone_of(s, n, "p2") for n in ("Probe Bolt", "Probe Goblin", "Probe Elf")] == ["p2:hand", "p2:graveyard", "p2:hand"]
    check(s)


def test_searing_rays_counts_each_players_own_creatures_of_the_color(cards):
    s = build(cards, ["Searing Rays", "Probe Goblin", "Probe Elf"], ["Probe Goblin", "Probe Goblin"])
    put(s, "Probe Goblin")
    put(s, "Probe Elf")
    for g in [c for c in s.state.cards.values() if c.name == "Probe Goblin" and c.owner == "p2"]:
        act(s, "p2", type="move", card_ids=[g.id], to={"player": "p2", "zone": "battlefield"})
    before = (life(s, "p1"), life(s, "p2"))
    cast(s, "Searing Rays", R=1, C=2)
    answer(s, "Red")
    assert (before[0] - life(s, "p1"), before[1] - life(s, "p2")) == (1, 2)
    check(s)


def test_crosis_discards_the_chosen_color_after_the_payment(cards):
    s = build(cards, ["Crosis, the Purger", "Probe Swamp", "Probe Swamp", "Probe Swamp"], ["Probe Bolt", "Probe Goblin", "Probe Elf"])
    for n in ("Probe Bolt", "Probe Goblin", "Probe Elf"):
        to_hand(s, n, "p2")
    crosis = put(s, "Crosis, the Purger")
    s.state.rules.controlled_since[crosis.id].turn = 0
    for swamp in [c for c in s.state.cards.values() if c.name == "Probe Swamp" and c.owner == "p1"]:
        act(s, "p1", type="move", card_ids=[swamp.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="pass_priority")  # → combat: Alice declares attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": crosis.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_one" and "Red" in option_ids(s))
    answer(s, "Red")
    assert [zone_of(s, n, "p2") for n in ("Probe Bolt", "Probe Goblin", "Probe Elf")] == ["p2:graveyard", "p2:graveyard", "p2:hand"]
    check(s)


# ---- more in-resolution choices (step 2): "that player controls", "revealed this way", numbers ------------------------------------------------------------------------
STEP2 = ["Expel the Interlopers", "By Invitation Only", "Void", "Tsabo's Decree", "Elvish Soultiller", "World Queller", "Fertile Imagination", "Blood Oath",
         "Darigaaz, the Igniter"]


@pytest.mark.parametrize("name", STEP2)
def test_step2_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def on_field(s, name, pid="p1", n=1):
    for c in [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:battlefield"]


def test_tsabo_decree_discards_and_destroys_only_the_chosen_type_of_the_target_player(cards):
    s = build(cards, ["Tsabo's Decree", "Probe Elf", "Probe Goblin"], ["Probe Elf", "Probe Elf Two", "Probe Goblin", "Probe Bolt"])
    on_field(s, "Probe Elf")
    on_field(s, "Probe Goblin")
    on_field(s, "Probe Elf", "p2")
    on_field(s, "Probe Goblin", "p2")
    for n in ("Probe Elf Two", "Probe Bolt"):
        to_hand(s, n, "p2")
    cast(s, "Tsabo's Decree", targets=["p2"], B=1, C=5)
    assert "Elf" in option_ids(s) and "Goblin" in option_ids(s)
    answer(s, "Elf")
    assert zone_of(s, "Probe Elf Two", "p2") == "p2:graveyard" and zone_of(s, "Probe Bolt", "p2") == "p2:hand"  # (creature cards of that type only)
    assert zone_of(s, "Probe Elf", "p2") == "p2:graveyard" and zone_of(s, "Probe Goblin", "p2") == "p2:battlefield"
    assert zone_of(s, "Probe Elf") == "p1:battlefield"  # (only the target player's creatures)
    check(s)


def test_elvish_soultiller_shuffles_the_chosen_type_from_the_graveyard_when_it_dies(cards):
    s = build(cards, ["Elvish Soultiller", "Probe Elf", "Probe Goblin", "Murder"])
    soul = on_field(s, "Elvish Soultiller")[0]
    for n in ("Probe Elf", "Probe Goblin"):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    cast(s, "Murder", targets=[soul.id], B=2, C=1)
    answer(s, "Elf")
    assert (zone_of(s, "Probe Elf"), zone_of(s, "Elvish Soultiller"), zone_of(s, "Probe Goblin")) == ("p1:library", "p1:library", "p1:graveyard")
    check(s)


def test_fertile_imagination_counts_the_cards_of_the_chosen_type_it_revealed(cards):
    s = build(cards, ["Fertile Imagination"], ["Probe Elf", "Probe Elf Two", "Probe Bolt", "Probe Land"])
    for n in ("Probe Elf", "Probe Elf Two", "Probe Bolt", "Probe Land"):
        to_hand(s, n, "p2")
    cast(s, "Fertile Imagination", targets=["p2"], G=2, C=2)
    answer(s, "Creature")
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == "Saproling"]) == 4  # (two creature cards revealed, two tokens each)
    assert all(zone_of(s, n, "p2") == "p2:hand" for n in ("Probe Elf", "Probe Elf Two", "Probe Bolt", "Probe Land"))  # (revealing moves nothing)
    check(s)


def test_blood_oath_deals_damage_for_each_revealed_card_of_the_chosen_type(cards):
    s = build(cards, ["Blood Oath"], ["Probe Bolt", "Probe Elf", "Probe Land"])
    for n in ("Probe Bolt", "Probe Elf", "Probe Land"):
        to_hand(s, n, "p2")
    before = life(s, "p2")
    cast(s, "Blood Oath", targets=["p2"], R=1, C=3)
    answer(s, "Instant")
    assert before - life(s, "p2") == 3  # (one instant)
    check(s)


def test_blood_oath_with_no_card_of_the_type_deals_nothing(cards):
    s = build(cards, ["Blood Oath"], ["Probe Elf"])
    to_hand(s, "Probe Elf", "p2")
    before = life(s, "p2")
    cast(s, "Blood Oath", targets=["p2"], R=1, C=3)
    answer(s, "Sorcery")
    assert life(s, "p2") == before
    check(s)


def test_expel_the_interlopers_destroys_the_creatures_with_power_at_least_the_chosen_number(cards):
    s = build(cards, ["Expel the Interlopers", "Probe Elf", "Probe Elf Two", "Probe Knight"], ["Probe Goblin"])
    for n in ("Probe Elf", "Probe Elf Two", "Probe Knight"):
        on_field(s, n)
    on_field(s, "Probe Goblin", "p2")
    cast(s, "Expel the Interlopers", W=2, C=3)
    assert option_ids(s) == [str(n) for n in range(11)]
    answer(s, "2")
    assert [zone_of(s, n) for n in ("Probe Elf", "Probe Elf Two", "Probe Knight")] == ["p1:battlefield", "p1:graveyard", "p1:graveyard"]  # (power 1, 2, 3)
    assert zone_of(s, "Probe Goblin", "p2") == "p2:battlefield"
    check(s)


def test_by_invitation_only_makes_each_player_sacrifice_that_many(cards):
    s = build(cards, ["By Invitation Only", "Probe Elf", "Probe Elf Two", "Probe Knight"], ["Probe Goblin", "Probe Goblin"])
    for n in ("Probe Elf", "Probe Elf Two", "Probe Knight"):
        on_field(s, n)
    on_field(s, "Probe Goblin", "p2", 2)
    cast(s, "By Invitation Only", W=2, C=3)
    assert option_ids(s)[-1] == "13"
    answer(s, "2")  # (Alice then picks two of her three, Bob his two)
    assert sum(zone_of(s, n) == "p1:battlefield" for n in ("Probe Elf", "Probe Elf Two", "Probe Knight")) == 1
    assert not [c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Probe Goblin" and c.zone == "p2:battlefield"]
    check(s)


def test_void_destroys_artifacts_and_creatures_with_the_chosen_value_and_discards_nonlands(cards):
    s = build(cards, ["Void", "Probe Elf", "Probe Elf Two", "Probe Rock", "Probe Relic"], ["Probe Knight", "Probe Land", "Probe Elf Two"])
    for n in ("Probe Elf", "Probe Elf Two", "Probe Rock", "Probe Relic"):
        on_field(s, n)
    for n in ("Probe Knight", "Probe Land", "Probe Elf Two"):
        to_hand(s, n, "p2")
    cast(s, "Void", targets=["p2"], B=1, R=1, C=3)
    answer(s, "2")  # (Elf Two {1}{G} and Rock {2}: mana value 2; the Relic and the Elf are 1)
    assert [zone_of(s, n) for n in ("Probe Elf", "Probe Elf Two", "Probe Rock", "Probe Relic")] == ["p1:battlefield", "p1:graveyard", "p1:graveyard", "p1:battlefield"]
    assert [zone_of(s, n, "p2") for n in ("Probe Knight", "Probe Land", "Probe Elf Two")] == ["p2:hand", "p2:hand", "p2:graveyard"]
    check(s)


def test_world_queller_makes_each_player_sacrifice_a_permanent_of_the_chosen_type(cards):
    s = build(cards, ["World Queller", "Probe Elf", "Probe Relic"], ["Probe Goblin", "Probe Relic"])
    for n in ("World Queller", "Probe Elf"):
        on_field(s, n)
    on_field(s, "Probe Goblin", "p2")
    on_field(s, "Probe Relic", "p2")
    for _ in range(80):
        d = s.state.rules.decision
        if d is None:
            if zone_of(s, "Probe Goblin", "p2") != "p2:battlefield":
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif "Creature" in [o.id for o in d.options] and "Land" in [o.id for o in d.options]:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["Creature"])
        else:
            pick = next((o.id for o in d.options if o.label in ("Probe Elf", "Probe Goblin")), d.options[0].id)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    assert zone_of(s, "Probe Goblin", "p2") == "p2:graveyard" and zone_of(s, "Probe Elf") == "p1:graveyard"
    assert zone_of(s, "World Queller") == "p1:battlefield" and zone_of(s, "Probe Relic", "p2") == "p2:battlefield"
    check(s)


# ---- protection from a quality the permanent chose as it entered (step 3): 702.16a, 702.16n, 614.12a ----------------------------------------------------------------
STEP3 = ["Serra's Emissary", "Voice of All", "Order of the Stars", "Riders of Gavony", "Benevolent Blessing"]


@pytest.mark.parametrize("name", STEP3)
def test_step3_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_voice_of_all_has_protection_from_the_color_it_chose(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Voice of All", "Lightning Bolt", "Probe Elf"])
    cast(s, "Voice of All", W=2, C=2)
    assert option_ids(s) == ["White", "Blue", "Black", "Red", "Green"]
    answer(s, "Red")
    voice = card_named(s, "Voice of All")
    assert voice.choices == {"Chosen color": "Red"}
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    with pytest.raises(ActionError):  # 702.16b: a red spell can't target it
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[voice.id])
    elf = on_field(s, "Probe Elf")[0]
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[elf.id])  # (a green creature is no different)
    check(s)


def test_order_of_the_stars_takes_a_different_color(cards):
    from app.rules import protection
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

    s = build(cards, ["Order of the Stars"])
    cast(s, "Order of the Stars", W=1)
    answer(s, "Green")
    order = card_named(s, "Order of the Stars")
    assert order.choices == {"Chosen color": "Green"}
    ch = Plan(s.state, "p1", s.cards, None).ch(order)
    assert protection.protected_from(ch, Characteristics(name="g", colors=frozenset({"G"})))
    assert not protection.protected_from(ch, Characteristics(name="r", colors=frozenset({"R"})))  # (protection from green only)
    check(s)


def test_serra_emissary_protects_its_controller_and_creatures_from_the_chosen_card_type(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Serra's Emissary", "Lightning Bolt", "Probe Elf"], ["Probe Elf"])
    on_field(s, "Probe Elf")
    cast(s, "Serra's Emissary", W=3, C=4)
    assert "Instant" in option_ids(s) and "Creature" in option_ids(s)
    answer(s, "Instant")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=2)
    for target in ("p1", card_named(s, "Probe Elf").id, card_named(s, "Serra's Emissary").id):
        with pytest.raises(ActionError):  # 702.16b: an instant can't target you or your creatures
            act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[target])
    before = life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # (an opponent has no protection)
    answer(s)
    assert life(s, "p2") == before - 3
    check(s)


def test_serra_emissary_creature_choice_stops_creature_damage_to_you_and_your_creatures(cards):
    from app.rules import player_shields, protection
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

    s = build(cards, ["Serra's Emissary", "Probe Elf"])
    on_field(s, "Probe Elf")
    cast(s, "Serra's Emissary", W=3, C=4)
    answer(s, "Creature")
    plan = Plan(s.state, "p1", s.cards, None)
    creature = Characteristics(name="x", types=frozenset({"Creature"}))
    spell = Characteristics(name="y", types=frozenset({"Instant"}))
    assert player_shields.protected_from(plan, "p1", creature) is not None and player_shields.protected_from(plan, "p1", spell) is None
    assert player_shields.protected_from(plan, "p2", creature) is None
    elf = plan.ch(card_named(s, "Probe Elf"))
    assert protection.protected_from(elf, creature) and not protection.protected_from(elf, spell)
    check(s)


def test_riders_of_gavony_protects_humans_from_creatures_of_the_chosen_type(cards):
    from app.rules import protection
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

    s = build(cards, ["Riders of Gavony", "Order of the Stars", "Probe Elf"])
    on_field(s, "Order of the Stars")
    on_field(s, "Probe Elf")
    cast(s, "Riders of Gavony", W=2, C=2)
    answer(s, "Goblin")
    plan = Plan(s.state, "p1", s.cards, None)
    goblin = Characteristics(name="g", types=frozenset({"Creature"}), subtypes=frozenset({"Goblin"}))
    elf = Characteristics(name="e", types=frozenset({"Creature"}), subtypes=frozenset({"Elf"}))
    human = plan.ch(card_named(s, "Order of the Stars"))
    assert protection.protected_from(human, goblin) and not protection.protected_from(human, elf)
    assert not protection.protected_from(plan.ch(card_named(s, "Probe Elf")), goblin)  # (only Humans)
    check(s)


def test_benevolent_blessing_keeps_the_auras_and_equipment_you_control(cards):
    from app.rules import attachments
    from app.rules.plan import Plan

    s = build(cards, ["Benevolent Blessing", "Probe Elf", "Probe Hex"], ["Probe Hex"])
    elf = on_field(s, "Probe Elf")[0]
    mine = on_field(s, "Probe Hex")[0]
    theirs = on_field(s, "Probe Hex", "p2")[0]
    blessing = to_hand(s, "Benevolent Blessing")
    mana(s, "p1", W=1, C=1)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="cast_spell", card_id=blessing.id, targets=[elf.id])
    answer(s, "Red")

    def problem(source):
        return attachments.host_problem(Plan(s.state, "p1", s.cards, None), s.state.cards[source.id], elf.id, sba=True)  # (704.5m)

    assert s.state.cards[blessing.id].attached_to == elf.id
    assert problem(mine) is None  # your own red Aura already on it stays (702.16n)
    assert problem(theirs) is not None  # another player's does not
    check(s)


# ---- a card name / type / number a permanent chose as it entered, read by cost changers, prohibitions and prevention (step 4): 201.4, 601.2f, 601.3, 602.5, 615 -----
STEP4 = ["Disruptor Flute", "Council of the Absolute", "Anointed Peacekeeper", "Gideon's Intervention", "Archon of Valor's Reach", "Sanctum Prelate"]


@pytest.mark.parametrize("name", STEP4)
def test_step4_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def name_it(s, text, who="p1"):
    d = s.state.rules.decision
    assert d is not None and d.options[0].id == "__name__" and d.player == who
    act(s, who, type="choose", decision_id=d.id, name=text)


def enter(s, name, *picks, **pool):
    """Cast ``name`` for Alice from her hand with mana added by hand, let it resolve, answer the entering question with the first of ``picks`` (a typed name or an option id)."""
    mana(s, "p1", **pool)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, name).id)
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    if picks:
        d = s.state.rules.decision
        if d.options[0].id == "__name__":
            name_it(s, picks[0])
        else:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[picks[0]])
    return card_named(s, name)


def can_cast(s, name, pid="p1", **pool):
    """None if ``pid`` can cast their ``name`` now with this extra mana; the reason otherwise (nothing is cast then)."""
    from app.game.errors import ActionError

    mana(s, pid, **pool)
    try:
        act(s, pid, type="cast_spell", card_id=to_hand(s, name, pid).id)
    except ActionError as e:
        return str(e)
    return None


def cost_of(s, name, pid="p1"):
    """The total cost of ``pid``'s ``name`` as it would be cast now (601.2f)."""
    from app.rules import characteristics as chars
    from app.rules.casting import spell_cost

    c = card_named(s, name, pid)
    return spell_cost(s.state, c, chars.of(c, s.cards), 0, s.cards, player=pid).text()


def test_disruptor_flute_makes_the_named_spell_cost_three_more_for_everyone(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Disruptor Flute", "Probe Bolt"], ["Probe Bolt", "Probe Charm"])
    enter(s, "Disruptor Flute", "Probe Bolt", C=2)
    assert s.state.cards[card_named(s, "Disruptor Flute").id].choices == {"Chosen card name": "Probe Bolt"}
    assert (cost_of(s, "Probe Bolt"), cost_of(s, "Probe Bolt", "p2"), cost_of(s, "Probe Charm", "p2")) == ("{3}{R}", "{3}{R}", "{U}")
    bolt = to_hand(s, "Probe Bolt")
    mana(s, "p1", R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id)  # {R} doesn't pay {3}{R}
    mana(s, "p1", C=3)
    act(s, "p1", type="cast_spell", card_id=bolt.id)
    check(s)


def test_council_of_the_absolute_stops_the_opponents_and_cheapens_yours(cards):
    from app.rules import cast_limits
    from app.rules import characteristics as chars

    s = build(cards, ["Council of the Absolute", "Probe Gem"], ["Probe Gem"])
    enter(s, "Council of the Absolute", "Probe Gem", W=1, U=1, C=2)
    assert (cost_of(s, "Probe Gem"), cost_of(s, "Probe Gem", "p2")) == ("{2}", "{4}")  # 601.2f: {2} less for the spells you cast, not theirs
    theirs = to_hand(s, "Probe Gem", "p2")
    assert "can't cast" in cast_limits.cast_problem(s.state, "p2", theirs, chars.of(theirs, s.cards), s.cards)
    mine = to_hand(s, "Probe Gem")
    mana(s, "p1", C=2)
    act(s, "p1", type="cast_spell", card_id=mine.id)
    check(s)


def test_anointed_peacekeeper_taxes_the_opponents_spells_and_the_named_sources_abilities(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Anointed Peacekeeper", "Probe Pinger", "Probe Pinger"], ["Probe Pinger"])
    first = on_field(s, "Probe Pinger")[0]
    enter(s, "Anointed Peacekeeper", "Probe Pinger", W=1, C=2)
    assert s.state.cards[card_named(s, "Anointed Peacekeeper").id].choices == {"Chosen card name": "Probe Pinger"}
    # "Spells your opponents cast with the chosen name cost {2} more to cast": Bob's Pinger costs {3}, Alice's own {1}
    assert (cost_of(s, "Probe Pinger", "p2"), cost_of(s, "Probe Pinger")) == ("{3}", "{1}")
    # "Activated abilities of sources with the chosen name cost {2} more to activate unless they're mana abilities"
    before = life(s, "p2")
    mana(s, "p1", C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=first.id, ability=0, targets=["p2"])  # the ping now costs {2}
    mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=first.id, ability=0, targets=["p2"])
    answer(s)
    assert life(s, "p2") == before - 1 and s.state.players["p1"].mana == {}
    second = next(c for c in on_field(s, "Probe Pinger") if c.id != first.id)
    act(s, "p1", type="activate_ability", card_id=second.id, ability=1)  # its mana ability is not charged (605.1a)
    assert s.state.cards[second.id].tapped and s.state.players["p1"].mana == {"C": 1}
    check(s)


def test_gideons_intervention_stops_the_named_spell_for_opponents_and_prevents_its_damage(cards):
    from app.rules import cast_limits
    from app.rules import characteristics as chars

    s = build(cards, ["Gideon's Intervention", "Probe Pinger", "Probe Zapper"], ["Probe Pinger"])
    pinger, zapper = on_field(s, "Probe Pinger")[0], on_field(s, "Probe Zapper")[0]
    enter(s, "Gideon's Intervention", "Probe Pinger", W=2, C=2)
    theirs = to_hand(s, "Probe Pinger", "p2")
    assert "can't cast" in cast_limits.cast_problem(s.state, "p2", theirs, chars.of(theirs, s.cards), s.cards)  # "Your opponents can't cast spells with the chosen name"
    before = life(s, "p1")
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=0, targets=["p1"])
    answer(s)
    assert life(s, "p1") == before  # "Prevent all damage that would be dealt to you … by sources with the chosen name"
    act(s, "p1", type="activate_ability", card_id=zapper.id, ability=0, targets=["p1"])
    answer(s)
    assert life(s, "p1") == before - 1  # (a source with another name)
    check(s)


def test_archon_of_valors_reach_stops_every_spell_of_the_chosen_type(cards):
    s = build(cards, ["Archon of Valor's Reach", "Probe Bolt", "Probe Relic", "Probe Elf"])
    enter(s, "Archon of Valor's Reach", "Instant", G=1, W=1, C=4)
    assert s.state.cards[card_named(s, "Archon of Valor's Reach").id].choices == {"Chosen card type": "Instant"}
    assert "can't cast" in str(can_cast(s, "Probe Bolt", R=1))
    assert can_cast(s, "Probe Relic", C=1) is None and can_cast(s, "Probe Elf", C=1) is None
    check(s)


def test_sanctum_prelate_stops_noncreature_spells_with_the_chosen_mana_value(cards):
    s = build(cards, ["Sanctum Prelate", "Probe Bolt", "Probe Gem", "Probe Elf"])
    mana(s, "p1", W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Sanctum Prelate").id)
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert option_ids(s) == [str(n) for n in range(41)]
    answer(s, "1")
    assert s.state.cards[card_named(s, "Sanctum Prelate").id].choices == {"Chosen number": "1"}
    assert "can't cast" in str(can_cast(s, "Probe Bolt", R=1))  # a noncreature spell with mana value 1
    assert can_cast(s, "Probe Elf", C=1) is None  # a creature spell with mana value 1
    assert can_cast(s, "Probe Gem", C=4) is None  # mana value 4
    check(s)
