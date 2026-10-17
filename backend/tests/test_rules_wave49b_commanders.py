"""Wave 49B: commanders with two blocking lines (CR 2026-09-25), real Oracle text (tests/fixtures/wave49b_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 201.5c: "King Darien XLVIII" is "King Darien" in its own text (a trailing numeral is no part of how the card names itself).
* 614.1d, 611.3a: "As long as Archelos is tapped, other permanents enter tapped." / "… untapped, other permanents enter untapped." (the verdict is read as each permanent enters).
* 601.2c, 601.2f: "Spells you cast cost {1} less to cast for each target." (Hinata, Dawn-Crowned): the distinct targets chosen, read once they are; none before.
* 704.5j: "The "legend rule" doesn't apply to Slivers you control." (Sliver Gravemother); 702.141a, 113.6m: "Each Sliver creature card in your graveyard has encore {X}, where X is its mana value."
* 700.11, 107.1: "creatures you control that are Fungi and/or Saprolings" (The Mycotyrant), "permanents you control that are Spirits and/or enchantments" (Katilda), and the
  number of times you descended this turn (a permanent card put into your graveyard from anywhere).
* 509.1b, 508.1c: "Survivors your opponents control can't block, and they can't attack you or planeswalkers you control." and "that player creates that many 1/1 red Survivor creature tokens" (Varchild).
* 122.1, 107.1: "can't attack or block unless it has an even number of counters on it" and "if it has an odd number of counters on it" (Sab-Sunen: zero is even).
* 107.1a, 702.86a: "target opponent exiles the top half of their library, rounded up" and "annihilator X, where X is the number of +1/+1 counters on it" (Ulamog, the Defiler).
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
from tests.test_rules_wave34b_activated import activate, ask, attack, next_turn, settle, stops, to_phase
from tests.test_rules_wave35d_as_long_as import through_combat
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
HINATA, DARIEN, ARCHELOS, GRAVEMOTHER = "Hinata, Dawn-Crowned", "King Darien XLVIII", "Archelos, Lagoon Mystic", "Sliver Gravemother"
KATILDA, MYCOTYRANT, ULAMOG, STOMP = "Katilda, Dawnhart Martyr // Katilda's Rising Dawn", "The Mycotyrant", "Ulamog, the Defiler", "Savage Stomp"
VARCHILD, SABSUNEN, MIRRI, MORAUG, SARKHAN = "Varchild, Betrayer of Kjeldor", "Sab-Sunen, Luxa Embodied", "Mirri, Weatherlight Duelist", "Moraug, Fury of Akoum", "Sarkhan, Dragon Ascendant"
NAMES = [HINATA, DARIEN, ARCHELOS, GRAVEMOTHER, KATILDA, MYCOTYRANT, ULAMOG, VARCHILD, SABSUNEN, MIRRI, MORAUG, SARKHAN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", NAMES)
def test_every_commander_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def token(s, pid, name, type_line, power="1", toughness="1"):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": power, "toughness": toughness, "text": ""})
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid][-1]


# ---- 201.5c: King Darien XLVIII ------------------------------------------------------------------------------------------------------------------
def test_king_darien_names_itself_without_its_numeral(cards):
    s = build(cards, [DARIEN])
    darien = put(s, DARIEN)
    mana(s, G=1, W=1)
    with pytest.raises(ActionError):  # {3}{G}{W} with two mana
        activate(s, "p1", darien, "Put a +1/+1 counter")
    mana(s, C=3)
    activate(s, "p1", darien, "Put a +1/+1 counter")
    settle(s)
    assert s.state.cards[darien.id].counters.get("+1/+1") == 1
    assert any(c.is_token and c.name == "Soldier" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    activate(s, "p1", darien, "Sacrifice King Darien")
    settle(s)
    assert zone_of(s, DARIEN) == "p1:graveyard"
    check(s)


# ---- 614.1d: Archelos, Lagoon Mystic -------------------------------------------------------------------------------------------------------------
def land(s, name, pid="p1"):
    c = to_hand(s, name, pid)
    act(s, pid, type="play_land", card_id=c.id)
    return s.state.cards[c.id]


def test_archelos_makes_other_permanents_enter_as_it_is_tapped_or_untapped(cards):
    s = build(cards, [ARCHELOS, "Grizzly Bears", "Test Guildgate"])
    archelos = put(s, ARCHELOS)
    assert not s.state.cards[archelos.id].tapped
    assert not land(s, "Test Guildgate").tapped  # its own "enters tapped" against an untapped Archelos: untapped (its controller's choice, ruling 2020-11-10)
    act(s, "p1", type="tap", card_ids=[archelos.id], tapped=True)
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Grizzly Bears").id)
    settle(s)
    assert s.state.cards[card_named(s, "Grizzly Bears").id].tapped and zone_of(s, "Grizzly Bears") == "p1:battlefield"  # a tapped Archelos: other permanents enter tapped
    assert s.state.cards[archelos.id].tapped
    check(s)


def test_a_guildgate_enters_tapped_without_archelos(cards):
    s = build(cards, ["Archelos, Lagoon Mystic", "Test Guildgate"], [])
    assert land(s, "Test Guildgate").tapped  # the ordinary rule: Archelos is still in the library
    check(s)


# ---- 601.2f: Hinata, Dawn-Crowned ----------------------------------------------------------------------------------------------------------------
def test_hinata_takes_a_generic_off_for_each_distinct_target(cards):
    s = build(cards, [HINATA, STOMP, "Grizzly Bears"], ["Llanowar Elves"])
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Llanowar Elves", "p2")
    mana(s, G=1)  # {2}{G} for two targets: {G} with Hinata
    with pytest.raises(ActionError):  # no Hinata yet: the full price
        act(s, "p1", type="cast_spell", card_id=to_hand(s, STOMP).id, targets=[mine.id, theirs.id], target_counts=[1, 1])
    put(s, HINATA)
    act(s, "p1", type="cast_spell", card_id=card_named(s, STOMP).id, targets=[mine.id, theirs.id], target_counts=[1, 1])
    settle(s)
    assert s.state.cards[mine.id].counters.get("+1/+1") == 1
    assert not s.state.players["p1"].mana
    check(s)


def test_hinata_one_target_costs_one_less_and_no_target_costs_full(cards):
    s = build(cards, [HINATA, "Staggershock"], [])
    put(s, HINATA)
    mana(s, R=1, C=1)  # {2}{R} less 1 = {1}{R}
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Staggershock").id, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 38
    assert not s.state.players["p1"].mana
    check(s)


def test_hinata_makes_the_opponents_spells_cost_more_for_each_target(cards):
    s = build(cards, [HINATA, "Grizzly Bears"], ["Lightning Bolt"])
    stops(s)
    bears = put(s, "Grizzly Bears")
    put(s, HINATA)
    to_phase(s, "main1", turn=2)
    mana(s, "p2", R=1)  # {R} plus {1} for its target
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=[bears.id])
    mana(s, "p2", C=1)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Lightning Bolt", "p2").id, targets=[bears.id])
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard"
    check(s)


# ---- 704.5j, 702.141a: Sliver Gravemother --------------------------------------------------------------------------------------------------------
def settle_legends(s):
    asked = 0
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        assert "Legend rule" in d.prompt
        asked += 1
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    return asked


def test_sliver_gravemother_exempts_only_its_controllers_slivers_from_the_legend_rule(cards):
    s = build(cards, [GRAVEMOTHER], ["Llanowar Elves"])
    put(s, GRAVEMOTHER)
    slivers = [token(s, "p1", "Hero", "Token Legendary Creature — Sliver") for _ in range(2)]
    elves = [token(s, "p1", "Villain", "Token Legendary Creature — Elf") for _ in range(2)]
    theirs = [token(s, "p2", "Hero", "Token Legendary Creature — Sliver") for _ in range(2)]
    act(s, "p1", type="pass_priority")
    assert settle_legends(s) == 2  # the Elves, and Bob's Slivers (Gravemother says "you control")
    on = {c.id for c in s.state.cards.values() if c.zone.endswith(":battlefield")}
    assert all(c.id in on for c in slivers) and sum(c.id in on for c in elves) == 1 and sum(c.id in on for c in theirs) == 1
    check(s)


def test_sliver_gravemother_gives_a_sliver_card_encore_for_its_mana_value(cards):
    s = build(cards, [GRAVEMOTHER, "Muscle Sliver", "Grizzly Bears"], [])
    put(s, GRAVEMOTHER)
    sliver = card_named(s, "Muscle Sliver")
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[sliver.id, bears.id], to={"zone": "graveyard"})
    mana(s, C=1)
    with pytest.raises(ActionError):  # encore {2}: one mana is short
        act(s, "p1", type="activate_ability", card_id=sliver.id, ability=100)
    with pytest.raises(ActionError):  # a Bear is no Sliver
        act(s, "p1", type="activate_ability", card_id=bears.id, ability=100)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=sliver.id, ability=100)
    settle(s)
    assert zone_of(s, "Muscle Sliver") == "p1:exile"
    assert any(c.is_token and c.name == "Muscle Sliver" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    check(s)


# ---- 107.1: The Mycotyrant, Katilda --------------------------------------------------------------------------------------------------------------
def test_the_mycotyrant_counts_fungi_and_saprolings_and_makes_a_fungus_for_each_descent(cards):
    s = build(cards, [MYCOTYRANT, "Grizzly Bears", "Llanowar Elves", "Lightning Bolt"], [])
    myco = put(s, MYCOTYRANT)
    assert pt(s, MYCOTYRANT) == (1, 1)  # it is a Fungus itself
    token(s, "p1", "Saproling", "Token Creature — Saproling")
    token(s, "p1", "Goblin", "Token Creature — Goblin")
    assert pt(s, MYCOTYRANT) == (2, 2)  # the Goblin is neither
    stops(s)
    for name in ("Grizzly Bears", "Llanowar Elves", "Lightning Bolt"):  # two permanent cards and an instant: descended twice
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"zone": "graveyard"})
    to_phase(s, "end")
    settle(s)
    fungi = [c for c in s.state.cards.values() if c.is_token and c.name == "Fungus" and c.zone == "p1:battlefield"]
    assert len(fungi) == 2 and pt(s, MYCOTYRANT) == (4, 4)
    assert s.state.cards[myco.id].zone == "p1:battlefield"
    check(s)


def test_the_mycotyrant_makes_nothing_when_you_did_not_descend(cards):
    s = build(cards, [MYCOTYRANT, "Lightning Bolt"], [])
    put(s, MYCOTYRANT)
    stops(s)
    act(s, "p1", type="move", card_ids=[card_named(s, "Lightning Bolt").id], to={"zone": "graveyard"})
    to_phase(s, "end")
    settle(s)
    assert not [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    check(s)


def test_katilda_counts_spirits_and_enchantments_you_control(cards):
    s = build(cards, [KATILDA, "Grizzly Bears"], [])
    put(s, KATILDA)
    assert pt(s, KATILDA) == (1, 1)  # itself, a Spirit
    put(s, "Grizzly Bears")
    token(s, "p2", "Their Wish", "Token Enchantment")
    assert pt(s, KATILDA) == (1, 1)  # a Bear is neither, and Bob's enchantment isn't yours
    token(s, "p1", "My Wish", "Token Enchantment")
    token(s, "p1", "My Ghost", "Token Creature — Spirit")
    assert pt(s, KATILDA) == (3, 3)
    check(s)


def test_katildas_rising_dawn_gives_the_enchanted_creature_the_same_count(cards):
    s = build(cards, [KATILDA, "Grizzly Bears"], [])
    bears = put(s, "Grizzly Bears")
    katilda = card_named(s, KATILDA)
    act(s, "p1", type="move", card_ids=[katilda.id], to={"zone": "graveyard"})
    mana(s, W=2, C=3)
    act(s, "p1", type="cast_spell", card_id=katilda.id, alt_cost=f"{katilda.id}:2", targets=[bears.id])  # disturb {3}{W}{W}: the Aura, an enchantment you control
    settle(s)
    assert s.state.cards[katilda.id].attached_to == bears.id
    assert pt(s, "Grizzly Bears") == (3, 3)  # 2/2 and +1/+1: the Aura itself is the one enchantment
    token(s, "p1", "My Wish", "Token Enchantment")
    assert pt(s, "Grizzly Bears") == (4, 4)
    check(s)


# ---- 107.1a, 702.86a: Ulamog, the Defiler --------------------------------------------------------------------------------------------------------
def test_ulamog_exiles_half_of_a_library_rounded_up_when_cast(cards):
    s = build(cards, [ULAMOG], [])
    before = len(s.state.zones["p2:library"])
    mana(s, C=10)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, ULAMOG).id)
    for _ in range(12):  # the cast trigger targets the opponent (the only one) and resolves before Ulamog does
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    exiled = [c for c in s.state.cards.values() if c.zone == "p2:exile"]
    assert len(exiled) == (before + 1) // 2 and len(s.state.zones["p2:library"]) == before // 2
    check(s)


def test_ulamog_annihilator_is_its_counters_as_the_trigger_resolves(cards):
    s = build(cards, [ULAMOG], ["Grizzly Bears", "Llanowar Elves", "Lightning Bolt"])
    ulamog = put(s, ULAMOG)
    act(s, "p1", type="counter", card_ids=[ulamog.id], kind="+1/+1", delta=2)
    for name in ("Grizzly Bears", "Llanowar Elves", "Lightning Bolt"):
        put(s, name, "p2")
    next_turn(s)
    attack(s, ulamog)
    for _ in range(20):  # Bob chooses what to sacrifice: his first options
        d = s.state.rules.decision
        if d is not None and d.kind != "declare_blockers":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif d is not None or not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    gone = [c for c in s.state.cards.values() if c.owner == "p2" and c.name in ("Grizzly Bears", "Llanowar Elves", "Lightning Bolt") and c.zone == "p2:graveyard"]
    assert len(gone) == 2  # two +1/+1 counters: two permanents
    check(s)


# ---- Varchild, Betrayer of Kjeldor -------------------------------------------------------------------------------------------------------------
def test_varchild_survivors_cannot_block_and_the_damaged_player_creates_that_many(cards):
    s = build(cards, [VARCHILD], ["Llanowar Elves"])
    varchild = put(s, VARCHILD)
    survivor = token(s, "p2", "Survivor", "Token Creature — Survivor")
    next_turn(s)
    attack(s, varchild)
    d = ask(s)
    assert d.kind == "declare_blockers" and d.player == "p2"
    with pytest.raises(ActionError):  # Survivors your opponents control can't block
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": survivor.id, "attacker_id": varchild.id}])
    through_combat(s)
    mine = [c for c in s.state.cards.values() if c.name == "Survivor" and c.owner == "p2" and c.zone == "p2:battlefield"]
    assert len(mine) == 1 + 3 and s.state.players["p2"].life == 37  # Bob creates three more
    check(s)


def test_varchild_deals_no_damage_to_a_blocker_so_nothing_is_created(cards):
    s = build(cards, [VARCHILD], ["Llanowar Elves"])
    varchild = put(s, VARCHILD)
    elves = put(s, "Llanowar Elves", "p2")
    next_turn(s)
    attack(s, varchild)
    ask(s)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": elves.id, "attacker_id": varchild.id}])  # an Elf is no Survivor: it may block
    through_combat(s)
    assert not [c for c in s.state.cards.values() if c.name == "Survivor"] and s.state.players["p2"].life == 40
    check(s)


# ---- Sarkhan, Dragon Ascendant -------------------------------------------------------------------------------------------------------------------
def cast_sarkhan(s):
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, SARKHAN).id)
    settle(s)


def treasures(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Treasure" and c.zone == "p1:battlefield"]


def test_sarkhan_beholds_a_dragon_card_from_the_hand_for_a_treasure(cards):
    s = build(cards, [SARKHAN, "Shivan Dragon"], [])
    dragon = to_hand(s, "Shivan Dragon")
    cast_sarkhan(s)
    assert len(treasures(s)) == 1 and s.state.cards[dragon.id].zone == "p1:hand"  # revealed, not moved (701.4a)
    check(s)


def test_sarkhan_beholds_a_dragon_you_control(cards):
    s = build(cards, [SARKHAN], [])
    token(s, "p1", "Drake", "Token Creature — Dragon")
    cast_sarkhan(s)
    assert len(treasures(s)) == 1
    check(s)


def test_sarkhan_makes_no_treasure_without_a_dragon_to_behold(cards):
    s = build(cards, [SARKHAN, "Grizzly Bears"], [])
    to_hand(s, "Grizzly Bears")
    cast_sarkhan(s)
    assert zone_of(s, SARKHAN) == "p1:battlefield" and not treasures(s)
    check(s)


def test_sarkhan_grows_and_becomes_a_dragon_when_a_dragon_enters(cards):
    s = build(cards, [SARKHAN, "Shivan Dragon", "Grizzly Bears"], [])
    sarkhan = put(s, SARKHAN)
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Grizzly Bears").id)  # a Bear is no Dragon
    settle(s)
    assert not s.state.cards[sarkhan.id].counters
    mana(s, R=2, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Shivan Dragon").id)
    settle(s)
    now = s.state.cards[sarkhan.id]
    assert now.counters.get("+1/+1") == 1
    from app.rules.plan import Plan

    here = Plan(s.state, "p1", s.cards, None).ch(now)
    assert "Dragon" in here.subtypes and "flying" in here.keywords
    check(s)


# ---- Moraug, Fury of Akoum -----------------------------------------------------------------------------------------------------------------------
def test_moraug_pumps_for_each_attack_and_untaps_as_the_added_combat_begins(cards):
    s = build(cards, [MORAUG, "Grizzly Bears", "Forest"], [])
    put(s, MORAUG)
    bears = put(s, "Grizzly Bears")
    stops(s)
    next_turn(s)
    assert pt(s, "Grizzly Bears") == (2, 2)  # it hasn't attacked
    attack(s, bears)
    assert pt(s, "Grizzly Bears") == (3, 2)  # once
    through_combat(s)
    assert s.state.cards[bears.id].tapped and s.state.players["p2"].life == 37
    land(s, "Forest")  # a main phase: landfall adds a combat phase after this one
    settle(s)
    to_phase(s, "declare_attackers", turn=3)
    assert not s.state.cards[bears.id].tapped  # "At the beginning of that combat, untap all creatures you control."
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    assert pt(s, "Grizzly Bears") == (4, 2)  # twice
    to_phase(s, "end", turn=3)
    assert s.state.players["p2"].life == 33
    check(s)


def test_moraugs_untap_belongs_to_the_combat_it_added_not_the_next_one(cards):
    s = build(cards, [MORAUG, "Grizzly Bears", "Forest"], [])
    put(s, MORAUG)
    bears = put(s, "Grizzly Bears")
    stops(s)
    next_turn(s)
    act(s, "p1", type="tap", card_ids=[bears.id], tapped=True)
    land(s, "Forest")  # the first main phase: the added combat comes before the turn's own
    settle(s)
    assert attackers_asked(s, 3)
    assert not s.state.cards[bears.id].tapped  # untapped as the added combat began
    act(s, "p1", type="declare_attackers", attackers=[])
    act(s, "p1", type="tap", card_ids=[bears.id], tapped=True)
    assert attackers_asked(s, 3)  # the turn's own combat
    assert s.state.cards[bears.id].tapped  # the delayed trigger is spent: nothing untaps now
    check(s)


# ---- Mirri, Weatherlight Duelist -----------------------------------------------------------------------------------------------------------------
def test_mirri_attacking_lets_each_opponent_block_with_one_creature_only(cards):
    s = build(cards, [MIRRI, "Grizzly Bears"], ["Llanowar Elves", "Young Wolf"])
    mirri = put(s, MIRRI)
    e1, e2 = put(s, "Llanowar Elves", "p2"), put(s, "Young Wolf", "p2")
    next_turn(s)
    attack(s, mirri)
    ask(s)
    with pytest.raises(ActionError, match="more than 1 creature"):  # two blockers on Mirri this combat
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": e1.id, "attacker_id": mirri.id}, {"blocker_id": e2.id, "attacker_id": mirri.id}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": e1.id, "attacker_id": mirri.id}])
    through_combat(s)
    assert zone_of(s, "Llanowar Elves", "p2") == "p2:graveyard"  # (first strike)
    check(s)


def test_without_mirri_attacking_two_blockers_are_allowed(cards):
    s = build(cards, [MIRRI, "Grizzly Bears"], ["Llanowar Elves", "Young Wolf"])
    put(s, MIRRI)
    bears = put(s, "Grizzly Bears")
    e1, e2 = put(s, "Llanowar Elves", "p2"), put(s, "Young Wolf", "p2")
    next_turn(s)
    attack(s, bears)
    ask(s)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": e1.id, "attacker_id": bears.id}, {"blocker_id": e2.id, "attacker_id": bears.id}])
    assert s.state.cards[e1.id].blocking and s.state.cards[e2.id].blocking  # accepted: Alice is asked how Bears divide their damage
    check(s)


def test_a_tapped_mirri_lets_only_one_creature_attack_its_controller(cards):
    s = build(cards, [MIRRI], ["Llanowar Elves", "Young Wolf"])
    mirri = put(s, MIRRI)
    e1, e2 = put(s, "Llanowar Elves", "p2"), put(s, "Young Wolf", "p2")
    next_turn(s)
    attack(s, mirri)
    ask(s)
    act(s, "p2", type="declare_blockers", blocks=[])
    through_combat(s)
    assert s.state.cards[mirri.id].tapped
    assert attackers_asked(s, 4)  # Bob's combat: Mirri is still tapped
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": e1.id, "target": "p1"}, {"card_id": e2.id, "target": "p1"}])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": e1.id, "target": "p1"}])
    check(s)


def test_an_untapped_mirri_limits_nothing_on_the_attack(cards):
    s = build(cards, [MIRRI], ["Llanowar Elves", "Young Wolf"])
    put(s, MIRRI)
    e1, e2 = put(s, "Llanowar Elves", "p2"), put(s, "Young Wolf", "p2")
    stops(s)
    assert attackers_asked(s, 2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": e1.id, "target": "p1"}, {"card_id": e2.id, "target": "p1"}])
    check(s)


# ---- Sab-Sunen, Luxa Embodied --------------------------------------------------------------------------------------------------------------------
def test_sab_sunen_attacks_only_with_an_even_number_of_counters(cards):
    s = build(cards, [SABSUNEN], [], forests=20)
    sab = put(s, SABSUNEN)
    stops(s)
    to_phase(s, "main1", turn=3)  # its first main phase trigger: one counter, an odd number, so two cards are drawn
    settle(s)
    assert s.state.cards[sab.id].counters.get("+1/+1") == 1
    hand = len(s.state.zones["p1:hand"])
    assert not attackers_asked(s, 3)  # one counter is odd: it can't attack, so nothing is declared
    to_phase(s, "main1", turn=5)  # two counters: even, and nothing is drawn
    settle(s)
    assert s.state.cards[sab.id].counters.get("+1/+1") == 2 and len(s.state.zones["p1:hand"]) == hand + 1  # (only the draw step's card)
    assert attackers_asked(s, 5)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": sab.id, "target": "p2"}])
    check(s)


def attackers_asked(s, turn):
    """Is the active player asked to declare attackers in this turn's combat (stopping at that decision)?"""
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            return True
        if s.state.turn.number > turn or (s.state.turn.number == turn and s.state.turn.phase == "main2"):
            return False
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never settled")
