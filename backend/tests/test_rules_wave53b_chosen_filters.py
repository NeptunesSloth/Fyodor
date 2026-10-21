"""Wave 53B: a value chosen as the spell or ability resolves, used as the filter of the instructions after it (CR 608.2c-d, 205.2a, 105.1,
205.3m): "Choose a color. … discards all cards of that color", "Choose a card type, then reveal the top four cards … all cards of the chosen
type revealed this way", "Choose a permanent type. Return all cards of the chosen type from your graveyard". Real Oracle text
(tests/fixtures/wave53b_cards.json, from data/cards.sqlite); every scenario checks the replay and a save and a load.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act, mana_pool
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
    assert life(s, "p2") == before - 1 and mana_pool(s) == {}
    second = next(c for c in on_field(s, "Probe Pinger") if c.id != first.id)
    act(s, "p1", type="activate_ability", card_id=second.id, ability=1)  # its mana ability is not charged (605.1a)
    assert s.state.cards[second.id].tapped and mana_pool(s) == {"C": 1}
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


# ---- more chosen filters (step 5): counters counted with the entering choice, reveal until X of the chosen type, copies of the chosen type, named cards in graveyards ------
STEP5 = ["Kindred Summons", "Kindred Charge", "Renewed Solidarity", "Banner of Kinship", "Life Burst", "Rune Snag", "Growth Cycle"]


@pytest.mark.parametrize("name", STEP5)
def test_step5_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def counters_on(s, card):
    return dict(s.state.cards[card.id].counters)


def test_banner_of_kinship_counts_the_creatures_of_the_type_chosen_as_it_enters(cards):
    s = build(cards, ["Banner of Kinship", "Probe Elf", "Probe Elf Two", "Probe Goblin"])
    for n in ("Probe Elf", "Probe Elf Two", "Probe Goblin"):
        on_field(s, n)
    banner = enter(s, "Banner of Kinship", "Elf", C=5)
    assert counters_on(s, banner) == {"fellowship": 2}  # 614.12a, 614.1c: the two Elves, counted with the answer
    assert s.state.cards[banner.id].choices == {"Chosen creature type": "Elf"}
    plan = Plan(s.state, "p1", s.cards, None)
    elf, elf2, goblin = (card_named(s, n) for n in ("Probe Elf", "Probe Elf Two", "Probe Goblin"))
    assert (plan.ch(elf).pt, plan.ch(elf2).pt, plan.ch(goblin).pt) == ((3, 3), (4, 4), (1, 1))  # +1/+1 for each of the 2 counters, Elves only
    check(s)


def to_graveyard(s, name, pid="p1", n=1):
    """Put the last ``n`` cards named ``name`` of ``pid``'s library into their graveyard (``card_named`` finds the first, which stays for casting)."""
    for c in [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][-n:]:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})


def draw_named(s, name, pid="p1", n=1):
    """Put the first ``n`` cards named ``name`` of ``pid``'s library into their hand."""
    for c in [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]:
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})


def stack_library(s, *names, pid="p1"):
    """Put these cards (still in the library, a name repeated is another copy) on top of it, the first named on top."""
    picked: list[str] = []
    for name in names:
        picked.append(next(c.id for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library" and c.id not in picked))
    for cid in reversed(picked):
        act(s, pid, type="move", card_ids=[cid], to={"player": pid, "zone": "library"})


def test_kindred_summons_reveals_until_x_creatures_of_the_chosen_type(cards):
    s = build(cards, ["Kindred Summons", "Probe Elf", "Probe Elf", "Probe Elf Two", "Probe Elf Two", "Probe Goblin", "Probe Relic"])
    on_field(s, "Probe Elf")
    on_field(s, "Probe Elf Two")
    stack_library(s, "Probe Goblin", "Probe Elf", "Probe Relic", "Probe Elf Two")  # X is 2: down to the second Elf
    cast(s, "Kindred Summons", G=2, C=5)
    answer(s, "Elf")
    on_bf = sorted(c.name for c in s.state.cards.values() if c.zone == "p1:battlefield")
    assert on_bf == ["Probe Elf", "Probe Elf", "Probe Elf Two", "Probe Elf Two"]  # the two found came in; Goblin and Relic, revealed, did not
    assert s.state.cards[card_named(s, "Probe Goblin").id].zone == "p1:library" and s.state.cards[card_named(s, "Probe Relic").id].zone == "p1:library"
    check(s)


def test_kindred_summons_with_no_creature_of_the_type_reveals_nothing(cards):
    s = build(cards, ["Kindred Summons", "Probe Elf", "Probe Goblin"])
    on_field(s, "Probe Goblin")
    stack_library(s, "Probe Elf")
    cast(s, "Kindred Summons", G=2, C=5)
    answer(s, "Elf")  # X is 0: no card is revealed
    assert zone_of(s, "Probe Elf") == "p1:library"
    check(s)


def test_kindred_charge_copies_each_creature_of_the_type_and_exiles_the_copies_at_end_step(cards):
    s = build(cards, ["Kindred Charge", "Probe Elf", "Probe Elf Two", "Probe Goblin"])
    for n in ("Probe Elf", "Probe Elf Two", "Probe Goblin"):
        on_field(s, n)
    cast(s, "Kindred Charge", R=2, C=4)
    answer(s, "Elf")
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert sorted(t.name for t in tokens) == ["Probe Elf", "Probe Elf Two"]  # the Goblin isn't copied
    plan = Plan(s.state, "p1", s.cards, None)
    assert all("haste" in plan.ch(t).keywords for t in tokens)
    until(s, lambda s: not [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"] and s.state.turn.phase in ("end", "cleanup", "main2"), limit=60)
    check(s)


def test_renewed_solidarity_copies_the_tokens_of_the_chosen_type_that_entered_this_turn(cards):
    s = build(cards, ["Renewed Solidarity", "Probe Elf", "Krenko, Mob Boss"])
    krenko = on_field(s, "Krenko, Mob Boss")[0]
    enter(s, "Renewed Solidarity", "Goblin", W=1, C=2)
    s.state.rules.controlled_since[krenko.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=krenko.id, ability=0)  # Krenko: create X 1/1 Goblin tokens, X the Goblins you control (one)
    answer(s)
    goblins = lambda: [c for c in s.state.cards.values() if c.is_token and c.name == "Goblin" and c.zone == "p1:battlefield"]  # noqa: E731
    assert len(goblins()) == 1
    until(s, lambda s: len(goblins()) > 1 or s.state.turn.number > 1, limit=60)
    assert len(goblins()) == 2  # the end step: a copy of the token that entered this turn (the Goblin Krenko isn't a token)
    check(s)


def test_life_burst_counts_the_cards_with_its_name_in_every_graveyard(cards):
    s = build(cards, ["Life Burst", "Life Burst", "Life Burst"], ["Life Burst"])
    to_graveyard(s, "Life Burst", "p1")
    to_graveyard(s, "Life Burst", "p2")
    before = life(s, "p1")
    cast(s, "Life Burst", targets=["p1"], W=1, C=1)
    answer(s)
    assert life(s, "p1") == before + 4 + 4 * 2  # 4 life, then 4 for each of the two in graveyards (the one resolving is on the stack)
    check(s)


@pytest.mark.parametrize("extra,countered", [(5, True), (6, False)])
def test_rune_snag_asks_two_more_for_each_copy_in_a_graveyard(cards, extra, countered):
    s = build(cards, ["Rune Snag", "Rune Snag", "Rune Snag", "Probe Gem"])
    to_graveyard(s, "Rune Snag", "p1", 2)  # {2} plus {2} for each of the two: {6}
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, "p1", C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Probe Gem").id)
    snag = to_hand(s, "Rune Snag")
    mana(s, "p1", U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=snag.id, targets=[card_named(s, "Probe Gem").id])
    mana(s, "p1", C=extra)  # the six it asks, or one short
    answer(s)
    assert zone_of(s, "Probe Gem") == ("p1:graveyard" if countered else "p1:battlefield")
    check(s)


def test_growth_cycle_adds_two_for_each_copy_in_your_graveyard(cards):
    s = build(cards, ["Growth Cycle", "Growth Cycle", "Growth Cycle", "Probe Elf"])
    elf = on_field(s, "Probe Elf")[0]
    to_graveyard(s, "Growth Cycle", "p1", 2)
    cast(s, "Growth Cycle", targets=[elf.id], G=1, C=1)
    answer(s)
    assert Plan(s.state, "p1", s.cards, None).ch(elf).pt == (1 + 3 + 2 * 2, 1 + 3 + 2 * 2)
    check(s)


def test_season_of_gathering_chooses_a_type_each_time_the_mode_is_chosen(cards):
    s = build(cards, ["Season of Gathering", "Probe Relic", "Probe Charm", "Probe Elf"], ["Probe Relic"])
    for n in ("Probe Relic", "Probe Charm", "Probe Elf"):
        on_field(s, n)
    on_field(s, "Probe Relic", "p2")
    mana(s, "p1", G=2, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Season of Gathering").id, modes=[1, 1])  # {P}{P} twice
    assert option_ids(s) == ["Artifact", "Enchantment"]
    answer(s, "Artifact", "Enchantment")  # each time its own answer: the first destroys artifacts, the second enchantments (608.2c)
    assert [zone_of(s, "Probe Relic"), zone_of(s, "Probe Charm"), zone_of(s, "Probe Elf")] == ["p1:graveyard", "p1:graveyard", "p1:battlefield"]
    assert zone_of(s, "Probe Relic", "p2") == "p2:graveyard"
    check(s)


def test_season_of_gathering_one_mode_chooses_only_once(cards):
    s = build(cards, ["Season of Gathering", "Probe Relic", "Probe Charm"])
    for n in ("Probe Relic", "Probe Charm"):
        on_field(s, n)
    mana(s, "p1", G=2, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Season of Gathering").id, modes=[1])
    answer(s, "Enchantment")
    assert [zone_of(s, "Probe Relic"), zone_of(s, "Probe Charm")] == ["p1:battlefield", "p1:graveyard"]
    check(s)


@pytest.mark.parametrize("named,found", [("Probe Bolt", True), ("Probe Land", False)])
def test_isperia_searches_only_when_the_chosen_name_is_in_the_revealed_hand(cards, named, found):
    s = build(cards, ["Isperia the Inscrutable", "Probe Bird", "Probe Elf"], ["Probe Bolt", "Probe Charm"])
    for n in ("Probe Bolt", "Probe Charm"):
        to_hand(s, n, "p2")
    isperia = put(s, "Isperia the Inscrutable")
    s.state.rules.controlled_since[isperia.id].turn = 0
    act(s, "p1", type="pass_priority")  # → combat
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": isperia.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.options[0].id == "__name__")
    name_it(s, named)
    answer(s)
    assert zone_of(s, "Probe Bolt", "p2") == "p2:hand"  # revealing moves nothing
    assert zone_of(s, "Probe Bird") == ("p1:hand" if found else "p1:library") and zone_of(s, "Probe Elf") == "p1:library"
    check(s)


# ---- a card name chosen as the spell resolves, then used on a hand, a library, a graveyard (step 6): 201.4, 701.20, 701.23, 701.9 ---------------------------------------
STEP6 = ["Spoils of the Vault", "Desperate Research", "Brain Pry", "Thought Hemorrhage", "Cabal Therapist"]


@pytest.mark.parametrize("name", STEP6)
def test_step6_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_spoils_of_the_vault_takes_the_named_card_and_exiles_the_rest_for_life(cards):
    s = build(cards, ["Spoils of the Vault", "Probe Goblin", "Probe Elf", "Probe Relic", "Probe Land"])
    stack_library(s, "Probe Goblin", "Probe Elf", "Probe Relic", "Probe Land")
    before = life(s)
    cast(s, "Spoils of the Vault", B=1)
    name_it(s, "Probe Relic")
    answer(s)
    assert zone_of(s, "Probe Relic") == "p1:hand" and zone_of(s, "Probe Land") == "p1:library"
    assert (zone_of(s, "Probe Goblin"), zone_of(s, "Probe Elf")) == ("p1:exile", "p1:exile") and life(s) == before - 2  # 1 life for each exiled card
    check(s)


def test_spoils_of_the_vault_with_no_such_card_reveals_and_exiles_the_whole_library(cards):
    s = build(cards, ["Spoils of the Vault"], forests=3)
    to_hand(s, "Spoils of the Vault")
    n = len(s.state.zones["p1:library"])
    before = life(s)
    cast(s, "Spoils of the Vault", B=1)
    name_it(s, "Probe Bird")  # not in the library
    answer(s)
    assert not s.state.zones["p1:library"] and life(s) == before - n
    check(s)


def test_desperate_research_takes_the_named_cards_of_the_top_seven_and_exiles_the_rest(cards):
    s = build(cards, ["Desperate Research", "Probe Elf", "Probe Elf", "Probe Goblin", "Probe Relic", "Probe Land", "Probe Bolt", "Probe Gem", "Probe Hex"])
    stack_library(s, "Probe Goblin", "Probe Elf", "Probe Relic", "Probe Elf", "Probe Land", "Probe Bolt", "Probe Gem", "Probe Hex")
    cast(s, "Desperate Research", B=1, C=1)
    name_it(s, "Probe Elf")
    answer(s)
    assert sorted(c.name for c in s.state.cards.values() if c.zone == "p1:hand") == ["Probe Elf", "Probe Elf"]
    assert sorted(c.zone for c in s.state.cards.values() if c.owner == "p1" and c.name in ("Probe Goblin", "Probe Relic", "Probe Land", "Probe Bolt", "Probe Gem")) == ["p1:exile"] * 5
    assert zone_of(s, "Probe Hex") == "p1:library"  # the eighth card was not revealed
    check(s)


@pytest.mark.parametrize("named,discarded", [("Probe Bolt", True), ("Probe Charm", False)])
def test_brain_pry_discards_one_named_card_or_draws(cards, named, discarded):
    s = build(cards, ["Brain Pry"], ["Probe Bolt", "Probe Bolt", "Probe Elf"])
    draw_named(s, "Probe Bolt", "p2", 2)
    draw_named(s, "Probe Elf", "p2")
    cast(s, "Brain Pry", targets=["p2"], B=1, C=1)
    name_it(s, named)
    answer(s)
    mine = len(s.state.zones["p1:hand"])
    if discarded:
        assert sorted(c.name for c in s.state.cards.values() if c.zone == "p2:graveyard") == ["Probe Bolt"]  # one card with that name, not both
        assert mine == 0  # no draw
    else:
        assert not [c for c in s.state.cards.values() if c.zone == "p2:graveyard"]
        assert mine == 1  # "If they can't, you draw a card"
    check(s)


def test_thought_hemorrhage_hits_for_the_hand_and_exiles_every_copy(cards):
    s = build(cards, ["Thought Hemorrhage"], ["Probe Bolt", "Probe Bolt", "Probe Bolt", "Probe Bolt", "Probe Elf"])
    draw_named(s, "Probe Bolt", "p2", 2)
    to_graveyard(s, "Probe Bolt", "p2")  # the fourth stays in the library
    before = life(s, "p2")
    cast(s, "Thought Hemorrhage", targets=["p2"], B=1, R=1, C=2)
    name_it(s, "Probe Bolt")
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d.player == "p1" and d.kind == "choose_cards" and len(d.options) == 4  # the searcher sees the copies in the graveyard, hand and library
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    answer(s)
    assert before - life(s, "p2") == 6  # 3 damage for each of the two in the revealed hand
    assert sorted(c.zone for c in s.state.cards.values() if c.name == "Probe Bolt" and c.owner == "p2") == ["p2:exile"] * 4
    assert zone_of(s, "Probe Elf", "p2") in ("p2:library", "p2:hand")
    check(s)


def test_cabal_therapist_names_a_card_when_a_creature_is_sacrificed(cards):
    s = build(cards, ["Cabal Therapist", "Probe Elf"], ["Probe Bolt", "Probe Bolt", "Probe Elf"])
    on_field(s, "Cabal Therapist")
    on_field(s, "Probe Elf")
    draw_named(s, "Probe Bolt", "p2", 2)
    draw_named(s, "Probe Elf", "p2")
    for _ in range(300):
        d = s.state.rules.decision
        if zone_of(s, "Probe Bolt", "p2") == "p2:graveyard" and d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d.options and d.options[0].id == "__name__":
            name_it(s, "Probe Bolt", who=d.player)
        else:
            ids = [o.id for o in d.options]
            labels = {o.label: o.id for o in d.options}
            pick = "p2" if "p2" in ids else "pay" if "pay" in ids else "yes" if "yes" in ids else labels.get("Probe Elf") or ids[0]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    assert sorted(c.zone for c in s.state.cards.values() if c.owner == "p2" and c.name == "Probe Bolt") == ["p2:graveyard"] * 2 and zone_of(s, "Probe Elf", "p2") == "p2:hand"  # every card with that name, no other
    assert zone_of(s, "Probe Elf") == "p1:graveyard"  # the sacrifice that made the reflexive ability
    check(s)


# ---- a color chosen as it entered, counted by its own permanent (step 7): 614.12a, 604.3 (characteristic-defining), 603.8 (state trigger) --------------------------------
STEP7 = ["Chameleon Spirit", "Psychic Allergy", "Lurebound Scarecrow"]


@pytest.mark.parametrize("name", STEP7)
def test_step7_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_chameleon_spirit_counts_the_opponents_permanents_of_the_chosen_color(cards):
    s = build(cards, ["Chameleon Spirit", "Probe Elf Two"], ["Probe Elf", "Probe Elf", "Probe Goblin"])
    on_field(s, "Probe Elf Two")  # (its own green creature is no opponent's)
    on_field(s, "Probe Elf", "p2")
    on_field(s, "Probe Goblin", "p2")
    spirit = enter(s, "Chameleon Spirit", "Green", U=1, C=3)
    plan = lambda: Plan(s.state, "p1", s.cards, None)  # noqa: E731
    assert plan().ch(spirit).pt == (1, 1)  # only Bob's one green permanent
    second = next(c for c in s.state.cards.values() if c.name == "Probe Elf" and c.owner == "p2" and c.zone == "p2:library")
    act(s, "p2", type="move", card_ids=[second.id], to={"player": "p2", "zone": "battlefield"})
    assert plan().ch(spirit).pt == (2, 2)
    check(s)


def test_psychic_allergy_hurts_each_opponent_for_their_own_permanents_of_the_chosen_color(cards):
    s = build(cards, ["Psychic Allergy", "Probe Goblin"], ["Probe Goblin", "Probe Goblin", "Probe Elf"])
    on_field(s, "Probe Goblin")  # (Alice's own red permanent isn't counted: "they control")
    on_field(s, "Probe Goblin", "p2", 2)
    on_field(s, "Probe Elf", "p2")
    enter(s, "Psychic Allergy", "Red", U=2, C=3)
    before = life(s, "p2")
    for _ in range(80):
        if life(s, "p2") < before:
            break
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((o.id for o in d.options if o.id == "decline"), d.options[0].id)])
    assert before - life(s, "p2") == 2  # the two red permanents Bob controls
    check(s)


def test_lurebound_scarecrow_is_sacrificed_when_nothing_of_the_chosen_color_is_left(cards):
    s = build(cards, ["Lurebound Scarecrow", "Probe Elf", "Murder"])
    elf = on_field(s, "Probe Elf")[0]
    scarecrow = enter(s, "Lurebound Scarecrow", "Green", C=3)
    assert zone_of(s, "Lurebound Scarecrow") == "p1:battlefield"
    cast(s, "Murder", targets=[elf.id], B=2, C=1)
    answer(s)
    assert zone_of(s, "Probe Elf") == "p1:graveyard" and s.state.cards[scarecrow.id].zone == "p1:graveyard"
    check(s)


def test_lurebound_scarecrow_with_no_permanent_of_the_color_at_all_goes_at_once(cards):
    s = build(cards, ["Lurebound Scarecrow"])
    scarecrow = enter(s, "Lurebound Scarecrow", "Red", C=3)
    answer(s)
    assert s.state.cards[scarecrow.id].zone == "p1:graveyard"
    check(s)


# ---- a color and a creature type chosen together as it enters, then a token of both (step 8): 614.12a, 111.4 --------------------------------------------------------------
STEP8 = ["Riptide Replicator", "Volrath's Laboratory"]


@pytest.mark.parametrize("name", STEP8)
def test_step8_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def tokens(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.is_token and c.controller == pid and c.zone == f"{pid}:battlefield"]


def test_volraths_laboratory_makes_a_token_of_the_color_and_type_it_chose(cards):
    s = build(cards, ["Volrath's Laboratory"])
    mana(s, "p1", C=5)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Volrath's Laboratory").id)
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert option_ids(s) == ["White", "Blue", "Black", "Red", "Green"]
    answer(s, "Blue", "Elf")  # the color first, then the creature type
    lab = card_named(s, "Volrath's Laboratory")
    assert lab.choices == {"Chosen color": "Blue", "Chosen creature type": "Elf"}
    mana(s, "p1", C=5)
    act(s, "p1", type="activate_ability", card_id=lab.id, ability=1)
    answer(s)
    token = tokens(s)[0]
    ch = Plan(s.state, "p1", s.cards, None).ch(token)
    assert (token.name, ch.colors, ch.subtypes, ch.pt) == ("Elf", frozenset({"U"}), frozenset({"Elf"}), (2, 2))
    check(s)


def test_riptide_replicator_makes_a_token_as_big_as_its_charge_counters(cards):
    s = build(cards, ["Riptide Replicator"])
    mana(s, "p1", C=6)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Riptide Replicator").id, x_value=2)
    answer(s, "Red", "Goblin")
    rep = card_named(s, "Riptide Replicator")
    assert counters_on(s, rep) == {"charge": 2}
    mana(s, "p1", C=4)
    act(s, "p1", type="activate_ability", card_id=rep.id, ability=2)
    answer(s)
    token = tokens(s)[0]
    ch = Plan(s.state, "p1", s.cards, None).ch(token)
    assert (token.name, ch.colors, ch.subtypes, ch.pt) == ("Goblin", frozenset({"R"}), frozenset({"Goblin"}), (2, 2))
    check(s)


# ---- the creature type chosen as it entered, written into the types of a group (step 9): 205.1a-b, 613.1d, 611.3 -----------------------------------------------------------
STEP9 = ["Conspiracy", "Lifecraft Engine"]


@pytest.mark.parametrize("name", STEP9)
def test_step9_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def kinds(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(card_named(s, name, pid)).subtypes


def test_conspiracy_makes_your_creatures_and_creature_cards_only_the_chosen_type(cards):
    s = build(cards, ["Conspiracy", "Probe Elf", "Probe Elf Two", "Probe Rock"], ["Probe Elf"])
    on_field(s, "Probe Elf")
    on_field(s, "Probe Rock")
    on_field(s, "Probe Elf", "p2")
    to_hand(s, "Probe Elf Two")  # a creature card you own that isn't on the battlefield
    assert kinds(s, "Probe Elf") == frozenset({"Elf", "Druid"})
    enter(s, "Conspiracy", "Goblin", B=2, C=3)
    assert kinds(s, "Probe Elf") == frozenset({"Goblin"})  # 205.1a: its other creature types are gone
    assert kinds(s, "Probe Rock") == frozenset({"Goblin"})  # (an artifact creature: Golem is a creature type, the Artifact card type stays)
    assert kinds(s, "Probe Elf Two") == frozenset({"Goblin"})  # "The same is true for … creature cards you own that aren't on the battlefield"
    assert kinds(s, "Probe Elf", "p2") == frozenset({"Elf", "Druid"})  # (only yours)
    check(s)


def test_lifecraft_engine_gives_the_chosen_type_to_vehicle_creatures_only(cards):
    s = build(cards, ["Lifecraft Engine", "Probe Wagon", "Probe Elf"])
    on_field(s, "Probe Wagon")
    on_field(s, "Probe Elf")
    enter(s, "Lifecraft Engine", "Elf", C=4)
    assert kinds(s, "Probe Wagon") == frozenset({"Vehicle", "Elf"})  # in addition to its other types (205.1b)
    assert kinds(s, "Probe Elf") == frozenset({"Elf", "Druid"})
    plan = Plan(s.state, "p1", s.cards, None)
    assert (plan.ch(card_named(s, "Probe Wagon")).pt, plan.ch(card_named(s, "Probe Elf")).pt) == ((3, 3), (2, 2))  # its second line: +1/+1 to each creature of the chosen type, the Wagon (an Elf now) too
    check(s)


# ---- a basic land type or a color chosen as it entered, set on the land it enchants, itself or the table (step 10): 305.7, 105.3, 613.1d-e ----------------------------------
STEP10 = ["Phantasmal Terrain", "Convincing Mirage", "Shimmerwilds Growth", "Alloy Golem", "Shifting Sky"]


@pytest.mark.parametrize("name", STEP10)
def test_step10_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def enchant(s, aura, host, *picks, **pool):
    """Cast the Aura ``aura`` on ``host`` and answer its entering choice."""
    mana(s, "p1", **pool)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="cast_spell", card_id=to_hand(s, aura).id, targets=[host.id])
    answer(s, *picks)
    return card_named(s, aura)


@pytest.mark.parametrize("aura,cost", [("Phantasmal Terrain", dict(U=2)), ("Convincing Mirage", dict(U=2, C=1))])
def test_the_land_aura_sets_the_land_type_it_chose(cards, aura, cost):
    s = build(cards, [aura, "Probe Land"], forests=3)
    forest = on_field(s, "Forest")[0]
    assert kinds(s, "Forest") == frozenset({"Forest"})
    enchant(s, aura, forest, "Island", **cost)
    assert kinds(s, "Forest") == frozenset({"Island"})  # 305.7: the old land type is gone
    assert card_named(s, aura).choices == {"Chosen basic land type": "Island"}
    check(s)


def test_shimmerwilds_growth_makes_the_land_the_chosen_color(cards):
    s = build(cards, ["Shimmerwilds Growth"], forests=3)
    forest = on_field(s, "Forest")[0]
    assert Plan(s.state, "p1", s.cards, None).ch(forest).colors == frozenset()
    enchant(s, "Shimmerwilds Growth", forest, "Blue", G=2)
    assert Plan(s.state, "p1", s.cards, None).ch(forest).colors == frozenset({"U"})
    check(s)


def test_alloy_golem_is_the_chosen_color(cards):
    s = build(cards, ["Alloy Golem"])
    golem = enter(s, "Alloy Golem", "Red", C=6)
    assert Plan(s.state, "p1", s.cards, None).ch(golem).colors == frozenset({"R"})
    check(s)


def test_shifting_sky_makes_every_nonland_permanent_the_chosen_color(cards):
    s = build(cards, ["Shifting Sky", "Probe Elf", "Probe Relic"], ["Probe Goblin"])
    on_field(s, "Probe Elf")
    on_field(s, "Probe Relic")
    on_field(s, "Probe Goblin", "p2")
    forest = on_field(s, "Forest")[0]
    enter(s, "Shifting Sky", "White", U=1, C=2)
    plan = Plan(s.state, "p1", s.cards, None)
    assert [plan.ch(card_named(s, n, p)).colors for n, p in (("Probe Elf", "p1"), ("Probe Relic", "p1"), ("Probe Goblin", "p2"))] == [frozenset({"W"})] * 3
    assert plan.ch(forest).colors == frozenset()  # (lands are left alone)
    check(s)


# ---- a creature type or a basic land type chosen as it entered, filtering a hand card / a land that became tapped (step 11): 608.2c, 603.2 ----------------------------------
STEP11 = ["Belbe's Portal", "Roots of Life"]


@pytest.mark.parametrize("name", STEP11)
def test_step11_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def portal_offer(s, portal):
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=portal.id, ability=1)  # (0 is the entering choice)
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    return s.state.rules.decision


def test_belbes_portal_puts_only_a_creature_card_of_the_chosen_type_from_hand(cards):
    s = build(cards, ["Belbe's Portal", "Probe Elf", "Probe Goblin"])
    portal = enter(s, "Belbe's Portal", "Elf", C=5)
    elf, goblin = to_hand(s, "Probe Elf"), to_hand(s, "Probe Goblin")
    assert [o.label for o in portal_offer(s, portal).options] == ["Probe Elf"]  # the Goblin card is not offered
    answer(s)
    assert (s.state.cards[elf.id].zone, s.state.cards[goblin.id].zone) == ("p1:battlefield", "p1:hand")
    assert s.state.cards[portal.id].tapped
    check(s)


def test_belbes_portal_with_no_card_of_the_type_in_hand_puts_nothing(cards):
    s = build(cards, ["Belbe's Portal", "Probe Elf", "Probe Goblin"])
    portal = enter(s, "Belbe's Portal", "Elf", C=5)
    goblin = to_hand(s, "Probe Goblin")
    assert not portal_offer(s, portal).options  # nothing to pick: the Goblin card is not of the chosen type
    answer(s)
    assert s.state.cards[goblin.id].zone == "p1:hand"
    check(s)


def test_roots_of_life_gains_life_when_an_opponents_land_of_the_chosen_type_becomes_tapped(cards):
    s = build(cards, ["Roots of Life", "Probe Freeze"], ["Probe Swamp", "Island"])
    isle, swamp = on_field(s, "Island", "p2")[0], on_field(s, "Probe Swamp", "p2")[0]
    enter(s, "Roots of Life", "Swamp", G=3)
    assert s.state.cards[card_named(s, "Roots of Life").id].choices == {"Chosen basic land type": "Swamp"}
    before = life(s)
    for land in (isle, swamp):
        mana(s, "p1", U=1)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Probe Freeze").id, targets=[land.id])
        answer(s)
        act(s, "p1", type="move", card_ids=[card_named(s, "Probe Freeze").id], to={"player": "p1", "zone": "library"})
        gained = life(s) - before
        assert gained == (1 if land is swamp else 0), (land.name, gained)  # 603.2: only the chosen type, 1 life each time
    check(s)


# ---- the chosen creature type given to the creature cards in a graveyard (step 12): 205.1b, 611.3 ----------------------------------
def test_ashes_of_the_fallen_gives_the_chosen_type_to_the_creature_cards_in_your_graveyard_only(cards):
    s = build(cards, ["Ashes of the Fallen", "Probe Elf", "Probe Elf Two", "Probe Relic"], ["Probe Elf"])
    assert coverage.of_card_data(cards.resolve("Ashes of the Fallen")).level == "FULL"
    on_field(s, "Probe Elf Two")
    to_graveyard(s, "Probe Elf")
    to_graveyard(s, "Probe Relic")
    to_graveyard(s, "Probe Elf", "p2")
    enter(s, "Ashes of the Fallen", "Goblin", C=2)
    assert kinds(s, "Probe Elf") == frozenset({"Elf", "Druid", "Goblin"})  # in addition to its other types (205.1b)
    assert kinds(s, "Probe Elf", "p2") == frozenset({"Elf", "Druid"})  # (only your graveyard)
    assert kinds(s, "Probe Elf Two") == frozenset({"Elf", "Warrior"})  # (on the battlefield it is not a card in a graveyard)
    assert kinds(s, "Probe Relic") == frozenset()
    check(s)


# ---- "they also have" after a pump of the chosen type (step 13): 604.2, 611.3a, 702.131 ----------------------------------
def test_radiant_destiny_pumps_the_chosen_type_and_gives_vigilance_with_the_citys_blessing(cards):
    s = build(cards, ["Radiant Destiny", "Probe Elf", "Probe Goblin"], forests=8)
    assert coverage.of_card_data(cards.resolve("Radiant Destiny")).level == "FULL"
    on_field(s, "Probe Elf")
    on_field(s, "Probe Goblin")
    on_field(s, "Forest", n=6)
    enter(s, "Radiant Destiny", "Elf", W=1, C=2)
    plan = Plan(s.state, "p1", s.cards, None)
    elf, goblin = plan.ch(card_named(s, "Probe Elf")), plan.ch(card_named(s, "Probe Goblin"))
    assert (elf.pt, goblin.pt) == ((2, 2), (1, 1)) and not s.state.players["p1"].city_blessing  # 9 permanents: no blessing yet
    assert "vigilance" not in elf.keywords
    on_field(s, "Forest")
    plan = Plan(s.state, "p1", s.cards, None)
    elf, goblin = plan.ch(card_named(s, "Probe Elf")), plan.ch(card_named(s, "Probe Goblin"))
    assert "vigilance" in elf.keywords and "vigilance" not in goblin.keywords  # 10 permanents: Ascend gives the blessing
    check(s)


# ---- a card name chosen as an Aura enters, taxing the spells of the player it enchants (step 14): 601.2f, 614.12a ----------------------------------
def test_curse_of_silence_taxes_the_named_spell_of_the_enchanted_player_only(cards):
    s = build(cards, ["Curse of Silence", "Probe Bolt"], ["Probe Bolt", "Probe Elf"])
    assert coverage.of_card_data(cards.resolve("Curse of Silence")).level == "FULL"
    mana(s, "p1", W=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Curse of Silence").id, targets=["p2"])
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    name_it(s, "Probe Bolt")
    curse = card_named(s, "Curse of Silence")
    assert (s.state.cards[curse.id].attached_player, s.state.cards[curse.id].choices) == ("p2", {"Chosen card name": "Probe Bolt"})
    assert (cost_of(s, "Probe Bolt", "p2"), cost_of(s, "Probe Bolt")) == ("{2}{R}", "{R}")  # {2} more for the enchanted player's named spell only
    assert cost_of(s, "Probe Elf", "p2") == "{1}"
    check(s)


def test_curse_of_silence_lets_you_sacrifice_it_to_draw_when_the_enchanted_player_casts_the_named_spell(cards):
    s = build(cards, ["Curse of Silence", "Probe Bolt", "Probe Relic"], ["Probe Bolt", "Probe Elf"])
    mana(s, "p1", W=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Curse of Silence").id, targets=["p2"])
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    name_it(s, "Probe Bolt")
    curse = card_named(s, "Curse of Silence")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")  # Bob's turn: he has priority
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1, "C": 2})
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Probe Bolt", "p2").id)
    hand = len(s.state.zones["p1:hand"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"  # 603.2: Alice's trigger asks her, not Bob
    answer(s, "pay")
    assert s.state.cards[curse.id].zone == "p1:graveyard" and len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


# ---- a card type chosen, then tap or untap its permanents of that type (step 15): 608.2c-d, 701.26 ----------------------------------
def turnabout(s, kind, option):
    mana(s, "p1", U=2, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Turnabout").id, targets=["p2"])
    answer(s, kind, option)


def tapped(s, name, pid="p2"):
    return s.state.cards[card_named(s, name, pid).id].tapped


def test_turnabout_taps_only_the_untapped_permanents_of_the_chosen_type(cards):
    s = build(cards, ["Turnabout"], ["Probe Elf", "Probe Relic", "Probe Goblin"])
    assert coverage.of_card_data(cards.resolve("Turnabout")).level == "FULL"
    for n in ("Probe Elf", "Probe Relic", "Probe Goblin"):
        on_field(s, n, "p2")
    turnabout(s, "Creature", "0")
    assert (tapped(s, "Probe Elf"), tapped(s, "Probe Goblin"), tapped(s, "Probe Relic")) == (True, True, False)  # (an artifact, not a creature)
    check(s)


def test_turnabout_untaps_only_the_tapped_permanents_of_the_chosen_type(cards):
    s = build(cards, ["Turnabout", "Probe Relic"], ["Probe Elf", "Probe Relic", "Probe Gem"])
    for n in ("Probe Elf", "Probe Relic", "Probe Gem"):
        c = on_field(s, n, "p2")[0]
        act(s, "p2", type="tap", card_ids=[c.id], tapped=True)
    mine = on_field(s, "Probe Relic")[0]
    act(s, "p1", type="tap", card_ids=[mine.id], tapped=True)
    turnabout(s, "Artifact", "1")
    assert (tapped(s, "Probe Relic"), tapped(s, "Probe Gem"), tapped(s, "Probe Elf")) == (False, False, True)
    assert s.state.cards[mine.id].tapped  # (only the permanents of the targeted player)
    check(s)


# ---- the next spell of the chosen type, cast with flash (step 16): 601.3b, 601.2i ----------------------------------
def flash_icon(s):
    """Progenitor's Icon in play choosing Elf, its flash ability used, and Alice's own Probe Gain on the stack (so only flash lets her cast a creature)."""
    icon = enter(s, "Progenitor's Icon", "Elf", C=3)
    act(s, "p1", type="activate_ability", card_id=icon.id, ability=2)
    answer(s)
    act(s, "p1", type="set_prefs", hold_priority=True)  # (Alice keeps priority after casting: the spell stays on the stack)
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Probe Gain").id)


def test_progenitors_icon_lets_the_next_spell_of_the_chosen_type_be_cast_with_flash(cards):
    s = build(cards, ["Progenitor's Icon", "Probe Gain", "Probe Elf", "Probe Elf Two", "Probe Goblin"])
    assert coverage.of_card_data(cards.resolve("Progenitor's Icon")).level == "FULL"
    flash_icon(s)
    assert can_cast(s, "Probe Goblin", C=1) is not None  # (not of the chosen type)
    assert can_cast(s, "Probe Elf", C=1) is None  # an Elf spell with a spell on the stack: flash
    assert can_cast(s, "Probe Elf Two", G=1, C=1) is not None  # the permission was for the next one only
    check(s)


def test_progenitors_icon_is_used_up_by_the_next_spell_of_the_type_even_cast_without_flash(cards):
    s = build(cards, ["Progenitor's Icon", "Probe Gain", "Probe Elf", "Probe Elf Two"])
    icon = enter(s, "Progenitor's Icon", "Elf", C=3)
    act(s, "p1", type="activate_ability", card_id=icon.id, ability=2)
    answer(s)
    enter(s, "Probe Elf", C=1)  # the next Elf spell: at sorcery speed it needed no flash, and it was the one
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Probe Gain").id)
    assert s.state.zones.get("stack")
    assert can_cast(s, "Probe Elf Two", G=1, C=1) is not None
    check(s)


# ---- hexproof from the chosen color and evasion from creatures of it (step 17): 702.11d, 509.1b ----------------------------------
def test_sungold_sentinel_gains_hexproof_from_the_color_and_cant_be_blocked_by_creatures_of_it(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Sungold Sentinel", "Probe Elf", "Probe Elf Two"], ["Probe Goblin", "Probe Elf"])
    assert coverage.of_card_data(cards.resolve("Sungold Sentinel")).level == "FULL"
    sentinel = put(s, "Sungold Sentinel")
    s.state.rules.controlled_since[sentinel.id].turn = 0
    put(s, "Probe Elf")
    goblin, elf = put(s, "Probe Goblin", "p2"), put(s, "Probe Elf", "p2")
    mana(s, "p1", W=1, C=1)
    with pytest.raises(ActionError):  # Coven: only two different powers (3 and 1)
        act(s, "p1", type="activate_ability", card_id=sentinel.id, ability=1)
    put(s, "Probe Elf Two")  # (powers 3, 1 and 2: three different)
    act(s, "p1", type="activate_ability", card_id=sentinel.id, ability=1)
    answer(s, "Red")
    got = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[sentinel.id])
    assert any(a.text.lower().startswith("hexproof from red") for a in got.abilities)
    act(s, "p1", type="pass_priority")  # → combat
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": sentinel.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    with pytest.raises(ActionError):  # (a red creature can't block it)
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": goblin.id, "attacker_id": sentinel.id}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": elf.id, "attacker_id": sentinel.id}])  # a green one can
    check(s)


# ---- a card name chosen as an ability resolves, cheapening the named spells for the turn (step 18): 601.2f, 611.2a ----------------------------------
def test_cheering_fanatic_makes_every_spell_with_the_chosen_name_cost_one_less_this_turn(cards):
    s = build(cards, ["Cheering Fanatic", "Probe Gem", "Probe Relic"], ["Probe Gem"])
    assert coverage.of_card_data(cards.resolve("Cheering Fanatic")).level == "FULL"
    fanatic = put(s, "Cheering Fanatic")
    s.state.rules.controlled_since[fanatic.id].turn = 0
    assert (cost_of(s, "Probe Gem"), cost_of(s, "Probe Gem", "p2")) == ("{4}", "{4}")
    act(s, "p1", type="pass_priority")  # → combat
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": fanatic.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.options[0].id == "__name__")
    name_it(s, "Probe Gem")
    assert (cost_of(s, "Probe Gem"), cost_of(s, "Probe Gem", "p2")) == ("{3}", "{3}")  # both players' spells with that name
    assert cost_of(s, "Probe Relic") == "{1}"  # (other names are not cheaper)
    check(s)


def test_pucas_eye_draws_then_becomes_the_color_chosen(cards):
    s = build(cards, ["Puca's Eye", "Probe Elf"])
    assert coverage.of_card_data(cards.resolve("Puca's Eye")).level == "FULL"
    eye = card_named(s, "Puca's Eye")
    assert Plan(s.state, "p1", s.cards, None).ch(eye).colors == frozenset()
    hand = len(s.state.zones["p1:hand"])
    mana(s, "p1", C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Puca's Eye").id)
    answer(s, "Blue")
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (the card to hand, and the draw)
    assert Plan(s.state, "p1", s.cards, None).ch(card_named(s, "Puca's Eye")).colors == frozenset({"U"})  # 611.2a: no duration stated, so for the rest of the game
    check(s)


# ---- damage from a source of the color its enchantment chose as it entered (step 19): 603.2, 105.2 ----------------------------------
def test_circle_of_affliction_triggers_only_for_damage_from_a_source_of_the_chosen_color(cards):
    s = build(cards, ["Circle of Affliction", "Probe Burner", "Probe Sting"])
    assert coverage.of_card_data(cards.resolve("Circle of Affliction")).level == "FULL"
    enter(s, "Circle of Affliction", "Red", B=1, C=1)
    assert s.state.cards[card_named(s, "Circle of Affliction").id].choices == {"Chosen color": "Red"}
    # a green source hurts Alice: no trigger
    mana(s, "p1", G=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Probe Sting").id, targets=["p1"])
    answer(s)
    assert life(s, "p1") == 38 and life(s, "p2") == 40
    # a red one: the trigger, a payment of {1}, and the drain
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Probe Burner").id, targets=["p1"])
    mana(s, "p1", C=1)
    answer(s, "p2", "pay")  # the trigger's target, then the {1}
    assert (life(s, "p1"), life(s, "p2")) == (37, 39)  # 38 - 2 + 1 for the drain; Bob loses 1
    check(s)


def test_harsh_judgment_sends_the_damage_of_a_spell_of_the_chosen_color_back_to_its_controller(cards):
    s = build(cards, ["Harsh Judgment", "Probe Gain"], ["Probe Burner", "Probe Sting"])
    assert coverage.of_card_data(cards.resolve("Harsh Judgment")).level == "FULL"
    enter(s, "Harsh Judgment", "Red", W=2, C=2)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"  # (each player stops to respond)
    for spell, cost in (("Probe Sting", dict(G=1)), ("Probe Burner", dict(R=1))):
        mana(s, "p1", R=1)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Probe Gain").id)  # Bob responds with his burn spell at Alice
        mana(s, "p2", **cost)
        act(s, "p2", type="cast_spell", card_id=to_hand(s, spell, "p2").id, targets=["p1"])
        answer(s)
        act(s, "p1", type="move", card_ids=[card_named(s, "Probe Gain").id], to={"player": "p1", "zone": "library"})
    # the green spell hurt Alice (2) and the red one hurt Bob (2) instead; Alice gained 1 twice
    assert (life(s, "p1"), life(s, "p2")) == (40 - 2 + 2, 40 - 2)
    check(s)


# ---- a card type chosen after looking at an opponent's hand, taxing the spells of that type (step 20): 701.20e, 614.12a, 601.2f ----------------------------------
def test_arachne_looks_at_the_opponents_hand_then_taxes_the_spells_of_the_chosen_card_type(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Arachne, Psionic Weaver", "Probe Gain", "Probe Elf"], ["Probe Bolt", "Probe Gem"])
    assert coverage.of_card_data(cards.resolve("Arachne, Psionic Weaver")).level == "FULL"
    to_hand(s, "Probe Bolt", "p2")
    to_hand(s, "Probe Gem", "p2")
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Arachne, Psionic Weaver").id)
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.player == "p1" and sorted(o.label for o in d.options if o.group == "seen") == ["Probe Bolt", "Probe Gem"]  # Alice sees Bob's whole hand (and only she is asked)
    assert "Creature" not in [o.id for o in d.options] and "Instant" in [o.id for o in d.options]
    seen = next(o.id for o in d.options if o.group == "seen")
    with pytest.raises(ActionError):  # a card she looked at is not an answer
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[seen])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Instant"])
    arachne = card_named(s, "Arachne, Psionic Weaver")
    assert s.state.cards[arachne.id].choices == {"Chosen card type": "Instant"}
    assert (cost_of(s, "Probe Gain"), cost_of(s, "Probe Bolt", "p2")) == ("{1}{R}", "{1}{R}")  # {1} more for everyone's instants
    assert (cost_of(s, "Probe Elf"), cost_of(s, "Probe Gem", "p2")) == ("{1}", "{4}")  # (creatures and artifacts are not taxed)
    check(s)


# ---- a card name chosen as a spell resolves, banning spells and lands of that name until the caster's next turn (step 21): 601.3, 305.1 ----------------------------------
def ban(s, name):
    mana(s, "p1", W=1, B=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Conjurer's Ban").id)
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    name_it(s, name)


def test_conjurers_ban_stops_the_named_spell_for_every_player_until_your_next_turn(cards):
    s = build(cards, ["Conjurer's Ban", "Probe Gem", "Probe Gem", "Probe Relic"], ["Probe Gem", "Probe Gem"])
    assert coverage.of_card_data(cards.resolve("Conjurer's Ban")).level == "FULL"
    hand = len(s.state.zones["p1:hand"])
    ban(s, "Probe Gem")
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (the Ban was added to the hand and cast; "Draw a card")
    assert can_cast(s, "Probe Gem", C=4) is not None and can_cast(s, "Probe Gem", "p2", C=4) is not None  # nobody can cast it
    assert can_cast(s, "Probe Relic", C=1) is None  # (another name)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")  # Alice's next turn
    assert can_cast(s, "Probe Gem", C=4) is None  # it ended as that turn began
    check(s)


def test_conjurers_ban_stops_the_named_land_from_being_played(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Conjurer's Ban", "Probe Land", "Probe Swamp"])
    ban(s, "Probe Land")
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=to_hand(s, "Probe Land").id)
    act(s, "p1", type="play_land", card_id=to_hand(s, "Probe Swamp").id)  # (another name is fine)
    assert zone_of(s, "Probe Swamp") == "p1:battlefield" and zone_of(s, "Probe Land") == "p1:hand"
    check(s)


# ---- a card name chosen from the nonland cards an opponent revealed as the permanent entered (step 22): 701.20a, 201.4, 614.12a ----------------------------------
def test_alhammarret_names_a_revealed_nonland_card_and_stops_the_opponents_from_casting_it(cards):
    s = build(cards, ["Alhammarret, High Arbiter", "Probe Gem"], ["Probe Bolt", "Probe Gem", "Probe Land"])
    assert coverage.of_card_data(cards.resolve("Alhammarret, High Arbiter")).level == "FULL"
    for n in ("Probe Bolt", "Probe Gem", "Probe Land"):
        to_hand(s, n, "p2")
    mana(s, "p1", U=2, C=5)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Alhammarret, High Arbiter").id)
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.player == "p1" and sorted(o.id for o in d.options) == ["Probe Bolt", "Probe Gem"]  # the nonland cards revealed: the Land is not one
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Probe Gem"])
    assert s.state.cards[card_named(s, "Alhammarret, High Arbiter").id].choices == {"Chosen card name": "Probe Gem"}
    from app.rules import cast_limits
    from app.rules import characteristics as chars

    def problem(name, pid):
        c = card_named(s, name, pid)
        return cast_limits.cast_problem(s.state, pid, c, chars.of(c, s.cards), s.cards)

    assert "can't cast" in problem("Probe Gem", "p2")  # your opponents can't cast it
    assert problem("Probe Bolt", "p2") is None and problem("Probe Gem", "p1") is None  # (another name; you can)
    check(s)


# ---- one answer that is both a color and a creature type (step 23): 614.12a, 111.4 ----------------------------------
def test_sarpadian_empires_makes_a_token_of_the_color_and_type_of_the_one_answer(cards):
    s = build(cards, ["Sarpadian Empires, Vol. VII"])
    assert coverage.of_card_data(cards.resolve("Sarpadian Empires, Vol. VII")).level == "FULL"
    mana(s, "p1", C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Sarpadian Empires, Vol. VII").id)
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert option_ids(s) == ["White Citizen", "Blue Camarid", "Black Thrull", "Red Goblin", "Green Saproling"]  # the five pairs the card lists
    answer(s, "Black Thrull")
    book = card_named(s, "Sarpadian Empires, Vol. VII")
    assert book.choices == {"Chosen color": "Black", "Chosen creature type": "Thrull"}
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=book.id, ability=1)
    answer(s)
    token = tokens(s)[0]
    ch = Plan(s.state, "p1", s.cards, None).ch(token)
    assert (token.name, ch.colors, ch.subtypes, ch.pt) == ("Thrull", frozenset({"B"}), frozenset({"Thrull"}), (1, 1))
    check(s)


# ---- a land card name chosen as a trigger resolves, kept by the land for its linked statics (step 24): 608.2d, 607.2a, 602.5, 613.1f ----------------------------------
def test_petrified_hamlet_names_a_land_that_loses_its_activated_abilities_but_taps_for_colorless(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Petrified Hamlet", "Probe Fort", "Probe Land"])
    assert coverage.of_card_data(cards.resolve("Petrified Hamlet")).level == "FULL"
    fort, plain = put(s, "Probe Fort"), put(s, "Probe Land")
    act(s, "p1", type="play_land", card_id=to_hand(s, "Petrified Hamlet").id)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.options[0].id == "__name__")
    name_it(s, "Probe Fort")
    assert s.state.cards[card_named(s, "Petrified Hamlet").id].choices == {"Chosen card name": "Probe Fort"}
    got = Plan(s.state, "p1", s.cards, None).ch(fort)
    assert any("Add {C}" in a.text for a in got.abilities)  # "Lands with the chosen name have "{T}: Add {C}.""
    assert not any("Add {C}" in a.text for a in Plan(s.state, "p1", s.cards, None).ch(plain).abilities)
    mana(s, "p1", C=1)
    with pytest.raises(ActionError, match="can.t be activated"):  # its own ping is a non-mana ability of a source with the chosen name (602.5)
        act(s, "p1", type="activate_ability", card_id=fort.id, ability=0, targets=["p2"])
    check(s)


# ---- the chosen type for two groups at once (step 25): 205.1b, 613.1d, 611.3 ----------------------------------
def test_rukarumel_gives_the_chosen_type_to_slivers_and_nontoken_creatures_you_control(cards):
    s = build(cards, ["Rukarumel, Biologist", "Probe Goblin", "Probe Knight", "Probe Relic"], ["Probe Goblin"])
    assert coverage.of_card_data(cards.resolve("Rukarumel, Biologist")).level == "FULL"
    on_field(s, "Probe Goblin")
    on_field(s, "Probe Goblin", "p2")
    to_graveyard(s, "Probe Knight")
    rukarumel = enter(s, "Rukarumel, Biologist", "Elf", W=1, U=1, B=1, R=1, G=1)
    assert kinds(s, "Probe Goblin") == frozenset({"Goblin", "Elf"})  # in addition to its other types
    assert kinds(s, "Rukarumel, Biologist") >= {"Elf", "Human", "Wizard"}  # (he is a nontoken creature you control too)
    assert kinds(s, "Probe Goblin", "p2") == frozenset({"Goblin"})  # (not an opponent's)
    assert kinds(s, "Probe Knight") == frozenset({"Human", "Knight", "Elf"})  # "creature cards you own that aren't on the battlefield"
    s.state.rules.controlled_since[rukarumel.id].turn = 0
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=rukarumel.id, ability=2)
    answer(s)
    sliver = tokens(s)[0]
    assert Plan(s.state, "p1", s.cards, None).ch(sliver).subtypes == frozenset({"Sliver", "Elf"})  # a token Sliver is one of the first group
    check(s)


# ---- as many coin flips as the number chosen, counted (step 26): 705.2, 608.2c, 118.9 ----------------------------------
def rigged(monkeypatch, *results):
    """The next coins come up as asked (heads wins, 705.2); the iterator left over shows how many were flipped."""
    left = iter(results)
    monkeypatch.setattr("app.game.resolve._rng_int", lambda rng, lo, hi: 1 if next(left) else 0)
    return left


def test_squees_revenge_draws_two_cards_for_each_flip_when_every_flip_is_won(cards, monkeypatch):
    s = build(cards, ["Squee's Revenge", *["Probe Land"] * 9])
    assert coverage.of_card_data(cards.resolve("Squee's Revenge")).level == "FULL"
    left = rigged(monkeypatch, True, True, True)
    hand = len(s.state.zones["p1:hand"])
    mana(s, "p1", U=1, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Squee's Revenge").id)
    answer(s, "3")
    assert len(s.state.zones["p1:hand"]) == hand + 6 and list(left) == []  # three flips won: 2 cards for each of the 3 flips
    check(s)


def test_squees_revenge_stops_at_the_first_lost_flip_and_draws_nothing(cards, monkeypatch):
    s = build(cards, ["Squee's Revenge", *["Probe Land"] * 9])
    left = rigged(monkeypatch, True, False, True, True)
    hand = len(s.state.zones["p1:hand"])
    mana(s, "p1", U=1, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Squee's Revenge").id)
    answer(s, "4")
    assert len(s.state.zones["p1:hand"]) == hand and list(left) == [True, True]  # (the third and fourth coins were never flipped: "or until you lose a flip")
    check(s)


def yusri_attacks(cards, monkeypatch, number, *results):
    s = build(cards, ["Yusri, Fortune's Flame", "Probe Gain", *["Probe Land"] * 9])
    left = rigged(monkeypatch, *results)
    yusri = put(s, "Yusri, Fortune's Flame")
    s.state.rules.controlled_since[yusri.id].turn = 0
    to_hand(s, "Probe Gain")
    act(s, "p1", type="pass_priority")  # → combat
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": yusri.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_one")
    hand = len(s.state.zones["p1:hand"])
    answer(s, number)
    return s, left, hand


def test_yusri_draws_for_each_flip_won_and_five_won_lets_you_cast_from_hand_free(cards, monkeypatch):
    s, left, hand = yusri_attacks(cards, monkeypatch, "5", True, True, True, True, True)
    assert coverage.of_card_data(cards.resolve("Yusri, Fortune's Flame")).level == "FULL"
    assert len(s.state.zones["p1:hand"]) == hand + 5 and life(s) == 40 and list(left) == []
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Probe Gain").id, free=True)  # {R} paid by nothing: the spell from the hand is free this turn
    answer(s)
    assert life(s) == 41 and zone_of(s, "Probe Gain") == "p1:graveyard"
    check(s)


def test_yusri_deals_two_damage_to_you_for_each_flip_lost_and_four_wins_is_not_enough(cards, monkeypatch):
    from app.game.errors import ActionError

    s, left, hand = yusri_attacks(cards, monkeypatch, "4", True, False, True, False)
    assert len(s.state.zones["p1:hand"]) == hand + 2 and life(s) == 40 - 4 and list(left) == []  # two won, two lost
    with pytest.raises(ActionError):  # (no free casts)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Probe Gain").id, free=True)
    check(s)


# ---- two basic land types chosen as it enters: the basic lands of the first are the second (step 27): 305.7, 613.1d ----------------------------------
def test_illusionary_terrain_turns_the_basic_lands_of_the_first_type_into_the_second(cards):
    s = build(cards, ["Illusionary Terrain"], forests=3)
    assert coverage.of_card_data(cards.resolve("Illusionary Terrain")).level == "FULL"
    on_field(s, "Forest", n=2)
    on_field(s, "Island", "p2", n=2)
    mana(s, "p1", U=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Illusionary Terrain").id)
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert option_ids(s) == ["Plains", "Island", "Swamp", "Mountain", "Forest"]
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["Island"])
    assert option_ids(s) == ["Plains", "Swamp", "Mountain", "Forest"]  # two different basic land types: the first is not offered again
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["Swamp"])
    assert card_named(s, "Illusionary Terrain").choices == {"Chosen basic land type": "Island", "Chosen second basic land type": "Swamp"}
    assert kinds(s, "Island", "p2") == frozenset({"Swamp"})  # 305.7: the old land type is gone
    assert kinds(s, "Forest") == frozenset({"Forest"})  # (another type is left alone)
    check(s)


def test_darigaaz_deals_damage_for_each_card_of_the_chosen_color_in_the_revealed_hand(cards):
    s = build(cards, ["Darigaaz, the Igniter", "Probe Peak", "Probe Swamp", "Probe Swamp"], ["Probe Elf", "Probe Goblin", "Probe Bolt", "Probe Knight"])
    darigaaz = put(s, "Darigaaz, the Igniter")
    s.state.rules.controlled_since[darigaaz.id].turn = 0
    for c in [c for c in s.state.cards.values() if c.owner == "p1" and c.name in ("Probe Peak", "Probe Swamp")]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})  # {2}{R} for the trigger
    for n in ("Probe Elf", "Probe Goblin", "Probe Bolt", "Probe Knight"):
        to_hand(s, n, "p2")
    act(s, "p1", type="pass_priority")  # → combat
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": darigaaz.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_one")
    assert life(s, "p2") == 40 - 6  # (the combat damage first)
    answer(s, "pay", "Red")
    assert life(s, "p2") == 40 - 6 - 2  # the two red cards of Bob's revealed hand (the green and the white one are not)
    check(s)
