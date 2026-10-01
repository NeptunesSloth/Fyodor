"""Forms earlier waves left manual, now automated (wave 3R2): impulse permissions with a trailing
duration (611.2a), source-of-your-choice shields (609.7, 615.8, 615.9) and damage that can't be
prevented (615.12).

Real Commander-legal cards: their Oracle text (data/cards.sqlite, 2026-09-30 snapshot) is
transcribed below as custom-text permanents named after the card (a line the scenario doesn't use is
left out, and said so). Every scenario checks the final table and that replaying the recorded
history reproduces it.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, scripts
from app.rules.characteristics import Characteristics, parse_abilities
from tests.game_helpers import act
from tests.test_rules_attachments import build, token
from tests.test_rules_combat import attack, automate, table
from tests.test_rules_effects import replay_matches, run_until
from tests.test_rules_replacements2 import (
    URZAS_ARMOR,
    activate,
    answer,
    decision,
    permanent,
    red_creature,
    reload,
    rules,
)
from tests.test_rules_suspend import until

# -- Oracle text (current) --------------------------------------------------------------------------
COP_RED = ("{1}: The next time a red source of your choice would deal damage to you this turn, prevent that "
           "damage.")  # Circle of Protection: Red
PAY_NO_HEED = "Prevent all damage a source of your choice would deal this turn."  # Pay No Heed (as an activated ability below)
CONSULATE = "Prevent all damage that would be dealt to you this turn by a source of your choice."  # Consulate Surveillance ("Pay {E}{E}:")
FORGE_TENDER = ("Protection from red\nSacrifice this creature: Prevent all damage a red source of your choice would deal "
                "this turn.")  # Burrenton Forge-Tender 1/1
LEYLINE = "Damage can't be prevented."  # Leyline of Punishment (its last line; "Players can't gain life." left out)
MALIGNUS = "Damage that would be dealt by this creature can't be prevented."  # Malignus (second line; its P/T CDA left out)
QUESTING_BEAST = "Combat damage that would be dealt by creatures you control can't be prevented."  # Questing Beast (third line)
# "Pinpoint Avalanche deals 4 damage to target creature. The damage can't be prevented." (Pinpoint Avalanche)
AVALANCHE = "{1}: Avalanche deals 4 damage to target creature. The damage can't be prevented."
FLARING_PAIN = "{1}: Damage can't be prevented this turn."  # Flaring Pain's first line, as an activated ability
CLOCKWORK = ("When this creature dies, exile the top card of your library. You may play it until the end of your next "
             "turn.")  # Clockwork Percussionist (its other line: Haste)
PINGER = "{1}: Pinger deals 1 damage to any target."
KILLER = "{1}: Destroy target creature."


def life(s, pid):
    return s.state.players[pid].life


def supported(text, name="Avalanche"):
    ch = Characteristics(name=name, abilities=tuple(parse_abilities(text)))
    defs = scripts.definitions(ch)
    return [bool(defs.get(ab.index)) and coverage.definition_supported(defs[ab.index]) for ab in ch.abilities]


# -- grammar: what is read and what stays manual --------------------------------------------------------
@pytest.mark.parametrize("text", [
    "When this creature dies, exile the top card of your library. You may play it until the end of your next turn.",
    "Whenever you cast an Aura or Equipment spell, exile the top card of your library. You may play that card until the "
    "end of your next turn.",  # Armory Paladin
    "When this creature enters, exile up to one target instant or sorcery card from your graveyard. You may cast that "
    "card until the end of your next turn.",  # Scholar of Combustion (reminder text left out)
    "{T}: Exile the top two cards of your library. You may play them until the end of your next turn.",
    COP_RED, "{W}: The next time a black or red source of your choice would deal damage to you this turn, prevent that damage.",
    "{2}: The next time an artifact source of your choice would deal damage to you this turn, prevent that damage.",
    "Sacrifice this creature: Prevent all damage a red source of your choice would deal this turn.",
    "{W}, Sacrifice this creature: Prevent all damage a source of your choice would deal to you this turn.",
    "Pay {E}{E}: " + CONSULATE,
    LEYLINE, MALIGNUS, QUESTING_BEAST, "Combat damage can't be prevented.", AVALANCHE, FLARING_PAIN,
])
def test_read(text):
    assert all(supported(text)), text


@pytest.mark.parametrize("text", [
    # a rider on the prevented damage (615.5), redirection (614.9), half, a target or no recipient: still manual
    "{1}: The next time a source of your choice would deal damage to you this turn, prevent that damage. If damage is "
    "prevented this way, Deflecting Palm deals that much damage to that source's controller.",
    "{1}: The next time a source of your choice would deal damage this turn, that damage is dealt to that source's "
    "controller instead.",
    "{T}: The next time a source of your choice would deal damage to you this turn, prevent half that damage, rounded down.",
    "Sacrifice a creature: The next time a source of your choice would deal damage to any target this turn, prevent that damage.",
    "{1}: The next time a black or red source of your choice would deal damage this turn, prevent that damage.",
    "{W}: The next time a source of your choice of the chosen color would deal damage to you this turn, prevent that damage.",
    "{1}: The next time an artifact or red source of your choice would deal damage to you this turn, prevent that damage.",
    "{1}: The damage can't be prevented.",
])
def test_refused(text):
    assert not all(supported(text)), text


# -- impulse permissions with a trailing duration (611.2a) ---------------------------------------------
def test_play_it_until_the_end_of_your_next_turn(cards):
    s = build(cards, "Sol Ring")
    percussionist = token(s, "p1", "Clockwork Percussionist", "2/2", CLOCKWORK)
    ring = next(c for c in s.state.cards.values() if c.name == "Sol Ring")
    act(s, "p1", type="move", card_ids=[ring.id], to={"zone": "library"}, position="top")
    killer = token(s, "p1", "Killer", "1/1", KILLER)
    activate(s, killer, targets=[percussionist.id])
    run_until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.cards[ring.id].zone == "p1:exile"
    granted = rules(s).permissions
    assert len(granted) == 1 and granted[0].until == "end_of_next_turn" and granted[0].card == ring.id
    run_until(s, lambda s: s.state.turn.number == 2)  # Bob's turn: still granted
    assert len(rules(s).permissions) == 1
    run_until(s, lambda s: s.state.turn.number == 3)  # Alice's next turn: castable …
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    assert ring.id in s.view("p1")["rules"]["hints"]["castable"]
    run_until(s, lambda s: s.state.turn.number == 4)  # … and gone at the end of it (514.2)
    assert rules(s).permissions == []
    replay_matches(s)


# "{1}, {T}, Sacrifice this artifact: Exile the top two cards of your library. Choose one of them. Until the end of
# your next turn, you may play that card." (Mishra's Research Desk; its cost as {1} here)
RESEARCH_DESK = ("{1}: Exile the top two cards of your library. Choose one of them. Until the end of your next turn, you may "
                 "play that card.")


def test_choose_one_of_them_and_play_only_that_card(cards):
    s = build(cards, "Sol Ring", "Lightning Bolt")
    for name in ("Lightning Bolt", "Sol Ring"):
        card = next(c for c in s.state.cards.values() if c.name == name)
        act(s, "p1", type="move", card_ids=[card.id], to={"zone": "library"}, position="top")
    ring = next(c for c in s.state.cards.values() if c.name == "Sol Ring")
    bolt = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt")
    desk = token(s, "p1", "Mishra's Research Desk", "0/1", RESEARCH_DESK)
    activate(s, desk)
    d = decision(s)
    assert d is not None and d.player == "p1" and d.kind == "choose_one"
    assert sorted(o.label for o in d.options) == ["Lightning Bolt", "Sol Ring"]
    s2 = reload(s, cards)
    _choose(s, "Sol Ring")
    granted = rules(s).permissions
    assert [p.card for p in granted] == [ring.id] and granted[0].until == "end_of_next_turn"
    assert s.state.cards[bolt.id].zone == "p1:exile"
    replay_matches(s)
    _choose(s2, "Lightning Bolt")
    assert [p.card for p in rules(s2).permissions] == [bolt.id]
    replay_matches(s2)


# -- source-of-your-choice shields (609.7, 615.8) --------------------------------------------------------
def _choose(s, label_part):
    d = decision(s)
    assert d is not None and d.kind == "choose_one" and d.player == "p1"
    opt = next(o for o in d.options if label_part in o.label)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[opt.id])


def test_circle_of_protection_prevents_the_next_damage_from_the_chosen_red_source(cards):
    s = build(cards)
    cop = permanent(s, "p1", "Circle of Protection: Red", "Enchantment", COP_RED)
    pinger = red_creature(s, "p1", "Pinger", "1/1", PINGER)
    red_creature(s, "p2", "Raider", "2/2")
    green = token(s, "p1", "Grower", "1/1", "{1}: Grower deals 1 damage to any target.")
    bear = token(s, "p2", "Bear", "2/2")
    activate(s, cop)
    labels = [o.label for o in decision(s).options]
    # only red sources (609.7a): not Grower, not the (colorless) Circle; Krenko is a face-up object in the command zone
    assert sorted(labels) == ["Krenko, Mob Boss", "Pinger", "Raider"], labels
    s2 = reload(s, cards)
    _choose(s, "Pinger")
    activate(s, green, targets=["p1"])  # another source: not prevented
    assert life(s, "p1") == 39
    activate(s, pinger, targets=[bear.id])  # damage to something else: the shield stays (to you only)
    assert s.state.cards[bear.id].damage == 1
    activate(s, pinger, targets=["p1"])  # the next time it would deal damage to you: prevented (615.8) …
    assert life(s, "p1") == 39
    activate(s, pinger, targets=["p1"])  # … once
    assert life(s, "p1") == 38
    assert not [r for r in rules(s).replacements if r.get("kind") == "replace"]
    replay_matches(s)
    _choose(s2, "Raider")  # the save, loaded with the choice open
    activate(s2, pinger, targets=["p1"])
    assert life(s2, "p1") == 39
    replay_matches(s2)


def test_the_shield_checks_the_sources_color_again(cards):
    """609.7b / 615.9: the shield checks the chosen source's color again as it would deal damage (no
    effect the engine automates changes a color yet: the check itself, on the event's source)."""
    from app.rules import replace
    from app.rules.plan import Plan

    s = build(cards)
    plan = Plan(s.state, "p1", s.cards, None)
    c = replace.Candidate(id="r:x", event="damage", match={}, op={}, controller="p1", source_card=None, source_oid=None,
                          seq=(0,), label="Circle of Protection: Red")
    spec = {"oids": ["a.1"], "colors": ["R"]}
    assert replace._source_matches(plan, spec, c, {"source_oid": "a.1", "src": {"colors": ["R"]}})
    assert not replace._source_matches(plan, spec, c, {"source_oid": "a.1", "src": {"colors": ["G"]}})
    assert not replace._source_matches(plan, spec, c, {"source_oid": "b.1", "src": {"colors": ["R"]}})


def test_prevent_all_damage_a_source_of_your_choice_would_deal_this_turn(cards):
    s = build(cards)
    heed = permanent(s, "p1", "Pay No Heed", "Enchantment", "{1}: " + PAY_NO_HEED)
    pinger = red_creature(s, "p1", "Pinger", "1/1", PINGER)
    token(s, "p1", "Other", "1/1")
    bear = token(s, "p2", "Bear", "2/2")
    activate(s, heed)
    _choose(s, "Pinger")
    activate(s, pinger, targets=["p2"])
    activate(s, pinger, targets=[bear.id])
    activate(s, pinger, targets=["p1"])
    assert life(s, "p2") == 40 and life(s, "p1") == 40 and s.state.cards[bear.id].damage == 0
    assert [r["turn"] for r in rules(s).replacements if r.get("kind") == "replace"] == [1]  # "this turn" (611.2a)
    replay_matches(s)


def test_consulate_surveillance_protects_only_you(cards):
    s = build(cards)
    shield = permanent(s, "p1", "Consulate Surveillance", "Enchantment", "{1}: " + CONSULATE)
    pinger = red_creature(s, "p1", "Pinger", "1/1", PINGER)
    mine = token(s, "p1", "Mine", "2/2")
    activate(s, shield)
    _choose(s, "Pinger")
    activate(s, pinger, targets=["p1"])
    activate(s, pinger, targets=["p1"])
    activate(s, pinger, targets=[mine.id])
    assert life(s, "p1") == 40 and s.state.cards[mine.id].damage == 1
    replay_matches(s)


def test_a_single_choice_is_made_without_asking(cards):
    s = build(cards)
    tender = token(s, "p1", "Burrenton Forge-Tender", "1/1", FORGE_TENDER)
    act(s, "p1", type="activate_ability", card_id=tender.id, ability=1)
    run_until(s, lambda s: not s.state.zones.get("stack"))
    assert decision(s) is None  # no red source at all: nothing to choose, nothing prevented
    assert tender.id not in s.state.cards
    replay_matches(s)


def test_prevent_the_next_damage_to_you_and_to_a_target_legendary_creature(cards):
    """615.7 shields: "{W}, {T}: Prevent the next 2 damage that would be dealt to you this turn." (Esper
    Battlemage) and "{W}, {T}: Prevent the next 2 damage that would be dealt to target legendary creature
    this turn." (Eiganjo Castle) — their costs as {1} here."""
    s = build(cards)
    battlemage = token(s, "p1", "Esper Battlemage", "2/2", "{1}: Prevent the next 2 damage that would be dealt to you this turn.")
    castle = token(s, "p1", "Eiganjo Castle", "0/1",
                   "{1}: Prevent the next 2 damage that would be dealt to target legendary creature this turn.")
    act(s, "p2", type="create_token", player="p2", token={"name": "Hero", "type_line": "Legendary Token Creature — Test",
                                                          "power": "3", "toughness": "3"})
    hero = next(c for c in s.state.cards.values() if c.name == "Hero")
    pinger = token(s, "p1", "Pinger", "1/1", PINGER)
    activate(s, battlemage)
    activate(s, castle, targets=[hero.id])
    for _ in range(3):
        activate(s, pinger, targets=["p1"])
    activate(s, pinger, targets=[hero.id])
    assert life(s, "p1") == 39 and s.state.cards[hero.id].damage == 0
    with pytest.raises(ActionError):  # (not a legendary creature: not a legal target)
        activate(s, castle, targets=[pinger.id])
    replay_matches(s)


# -- damage that can't be prevented (615.12) -----------------------------------------------------------
def test_leyline_of_punishment_stops_prevention_and_shields_arent_used_up(cards):
    s = build(cards)
    permanent(s, "p1", "Urza's Armor", "Artifact", URZAS_ARMOR)
    cop = permanent(s, "p1", "Circle of Protection: Red", "Enchantment", COP_RED)
    pinger = red_creature(s, "p1", "Pinger", "1/1", PINGER)
    activate(s, pinger, targets=["p1"])
    assert life(s, "p1") == 40  # Urza's Armor prevents 1 of it
    activate(s, cop)
    _choose(s, "Pinger")
    leyline = permanent(s, "p2", "Leyline of Punishment", "Enchantment", LEYLINE)
    activate(s, pinger, targets=["p1"])
    assert life(s, "p1") == 39  # neither prevents any of it
    act(s, "p2", type="move", card_ids=[leyline.id], to={"zone": "graveyard"})
    # the shield wasn't used up (615.12): now both apply, and which one first decides whether the Circle's
    # shield is spent — the affected player chooses (616.1)
    assert [r["op"] for r in rules(s).replacements if r.get("kind") == "replace"] == [
        {"do": "prevent_all", "prevention": True, "once": True}]
    activate(s, pinger, targets=["p1"])
    d = decision(s)
    assert d is not None and d.player == "p1" and d.kind == "confirm"
    armor_first = "yes" if "Urza's Armor first" in {o.id: o.label for o in d.options}["yes"] else "no"
    answer(s, armor_first)
    assert life(s, "p1") == 39
    assert [r for r in rules(s).replacements if r.get("kind") == "replace"]  # the Circle's shield is still there
    activate(s, pinger, targets=["p1"])
    d = decision(s)
    answer(s, "no" if armor_first == "yes" else "yes")  # the Circle first: it prevents the 1 and is used up
    assert life(s, "p1") == 39 and not [r for r in rules(s).replacements if r.get("kind") == "replace"]
    replay_matches(s)


def test_the_spells_own_damage_cant_be_prevented(cards):
    s = build(cards)
    avalanche = token(s, "p1", "Avalanche", "0/9", AVALANCHE)
    sheltered = token(s, "p2", "Sheltered", "5/5", "Prevent all damage that would be dealt to Sheltered.")
    pinger = token(s, "p1", "Pinger", "1/1", PINGER)
    activate(s, pinger, targets=[sheltered.id])
    assert s.state.cards[sheltered.id].damage == 0
    activate(s, avalanche, targets=[sheltered.id])
    assert s.state.cards[sheltered.id].damage == 4
    replay_matches(s)


def test_damage_cant_be_prevented_this_turn_also_beats_protection(cards):
    s = build(cards)
    pain = token(s, "p1", "Flaring Pain", "0/1", FLARING_PAIN)
    warded = token(s, "p2", "Warded", "3/3", "Protection from red")
    burner = red_creature(s, "p1", "Burner", "1/1", "{1}: Burner deals 1 damage to each creature your opponents control.")
    activate(s, burner)
    assert s.state.cards[warded.id].damage == 0  # protection prevents it (702.16e)
    activate(s, pain)
    activate(s, burner)
    assert s.state.cards[warded.id].damage == 1  # … not this turn (615.12)
    run_until(s, lambda s: s.state.turn.number == 2)
    act(s, "p2", type="pass_priority")
    burner2 = s.state.cards[burner.id]
    assert burner2.zone == "p1:battlefield"
    replay_matches(s)


def test_combat_damage_from_creatures_you_control_cant_be_prevented(cards):
    s = table(cards)
    beast = red_creature(s, "p1", "Questing Beast", "4/4", QUESTING_BEAST)
    act(s, "p2", type="create_token", player="p2", token={"name": "Urza's Armor", "type_line": "Token Artifact — Test",
                                                          "text": URZAS_ARMOR})
    automate(s)
    attack(s, (beast, "p2"))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert life(s, "p2") == 36
    replay_matches(s)


def test_malignus_damage_cant_be_prevented_but_others_can(cards):
    s = table(cards)
    malignus = red_creature(s, "p1", "Malignus", "3/3", MALIGNUS)
    other = red_creature(s, "p1", "Other", "2/2")
    act(s, "p2", type="create_token", player="p2", token={"name": "Urza's Armor", "type_line": "Token Artifact — Test",
                                                          "text": URZAS_ARMOR})
    automate(s)
    attack(s, (malignus, "p2"), (other, "p2"))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert life(s, "p2") == 40 - 3 - 1
    replay_matches(s)


# -- redirection statics (614.9) ----------------------------------------------------------------------------
PARIAH = "Enchant creature\nAll damage that would be dealt to you is dealt to enchanted creature instead."  # Pariah
EMPYRIAL = "Flying\nAll damage that would be dealt to you is dealt to this creature instead."  # Empyrial Archangel 5/8 (shroud left out)
PALISADE = "All damage that would be dealt to you and other permanents you control is dealt to this creature instead."  # Palisade Giant 2/7
TREACHEROUS_LINK = "Enchant creature\nAll damage that would be dealt to enchanted creature is dealt to its controller instead."


def test_pariah_sends_damage_to_you_to_the_enchanted_creature(cards):
    s = build(cards)
    bear = token(s, "p1", "Bear", "2/2")
    pariah = permanent(s, "p1", "Pariah", "Enchantment — Aura", PARIAH)
    act(s, "p1", type="attach", card_ids=[pariah.id], to=bear.id)
    pinger = token(s, "p2", "Pinger", "1/1", PINGER)
    activate(s, token(s, "p1", "Mine", "1/1", "{1}: Mine deals 1 damage to any target."), targets=["p1"])
    assert life(s, "p1") == 40 and s.state.cards[bear.id].damage == 1
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    activate(s, s.state.cards[next(c for c in s.state.cards if s.state.cards[c].name == "Mine")], targets=["p1"])
    assert life(s, "p1") == 39  # 614.9: the creature is gone — the effect does nothing
    assert pinger.id in s.state.cards
    replay_matches(s)


def test_palisade_giant_and_a_prevention_effect_the_player_orders(cards):
    s = build(cards)
    giant = token(s, "p1", "Palisade Giant", "2/7", PALISADE)
    bear = token(s, "p1", "Bear", "2/2")
    pinger = token(s, "p1", "Pinger", "1/1", PINGER)
    activate(s, pinger, targets=[bear.id])
    activate(s, pinger, targets=["p1"])
    activate(s, pinger, targets=[giant.id])  # (its own damage isn't redirected: "other permanents")
    assert s.state.cards[bear.id].damage == 0 and life(s, "p1") == 40 and s.state.cards[giant.id].damage == 3
    permanent(s, "p1", "Urza's Armor", "Artifact", URZAS_ARMOR)
    activate(s, pinger, targets=["p1"])
    d = decision(s)  # redirect first or prevent 1 first: the affected player chooses (616.1)
    assert d is not None and d.player == "p1"
    redirect_first = "yes" if "Palisade Giant first" in {o.id: o.label for o in d.options}["yes"] else "no"
    answer(s, redirect_first)  # (redirected first, the Armor no longer applies: it protects only you)
    assert life(s, "p1") == 40 and s.state.cards[giant.id].damage == 4
    replay_matches(s)


def test_empyrial_archangel_takes_combat_damage_and_no_commander_damage_is_dealt(cards):
    s = table(cards)
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    angel = token(s, "p2", "Empyrial Archangel", "5/8", EMPYRIAL)
    automate(s)
    attack(s, (krenko, "p2"))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert life(s, "p2") == 40 and s.state.cards[angel.id].damage == 3
    assert not s.state.players["p2"].commander_damage
    replay_matches(s)


def test_treacherous_link_sends_the_damage_to_its_controller(cards):
    s = build(cards)
    bear = token(s, "p2", "Bear", "2/2")
    link = permanent(s, "p1", "Treacherous Link", "Enchantment — Aura", TREACHEROUS_LINK)
    act(s, "p1", type="attach", card_ids=[link.id], to=bear.id)
    pinger = token(s, "p1", "Pinger", "1/1", "{1}: Pinger deals 2 damage to any target.")
    activate(s, pinger, targets=[bear.id])
    assert life(s, "p2") == 38 and s.state.cards[bear.id].damage == 0
    replay_matches(s)


# -- token creation adding a different token (614.16, 616.1) -------------------------------------------------
PEREGRIN = ("If one or more tokens would be created under your control, those tokens plus an additional Food token are "
            "created instead.")  # Peregrin Took (first line; its sacrifice ability left out)
CHATTERFANG = ("Forestwalk\nIf one or more tokens would be created under your control, those tokens plus that many 1/1 green "
               "Squirrel creature tokens are created instead.")  # Chatterfang, Squirrel General (first two lines)
TREASURER = "{1}: Create a Treasure token."
TAPPED_TREASURER = "{1}: Create a tapped Treasure token."


def count(s, name):
    return len([c for c in s.state.cards.values() if c.name == name and c.zone.endswith(":battlefield")])


def test_peregrin_took_adds_a_food_and_two_add_two(cards):
    s = build(cards)
    token(s, "p1", "Peregrin Took", "2/3", PEREGRIN)
    maker = token(s, "p1", "Maker", "1/1", TAPPED_TREASURER)
    activate(s, maker)
    assert count(s, "Treasure") == 1 and count(s, "Food") == 1
    food = next(c for c in s.state.cards.values() if c.name == "Food")
    assert not food.tapped  # (only the Treasure is created tapped)
    token(s, "p1", "Peregrin Took Two", "2/3", PEREGRIN)
    activate(s, maker)
    assert decision(s) is None  # (the two commute: no question)
    assert count(s, "Treasure") == 2 and count(s, "Food") == 3  # one more Food each, once per event (614.5)
    replay_matches(s)


def test_peregrin_took_and_parallel_lives_the_creating_player_orders(cards):
    from tests.test_rules_replacements2 import PARALLEL_LIVES

    s = build(cards)
    token(s, "p1", "Peregrin Took", "2/3", PEREGRIN)
    permanent(s, "p1", "Parallel Lives", "Enchantment", PARALLEL_LIVES)
    maker = token(s, "p1", "Maker", "1/1", TREASURER)
    activate(s, maker)
    d = decision(s)
    assert d is not None and d.player == "p1" and d.kind == "confirm"
    labels = {o.id: o.label for o in d.options}
    lives_first = "yes" if "Parallel Lives first" in labels["yes"] else "no"
    s2 = reload(s, cards)
    answer(s, lives_first)  # 2 Treasures, then a Food
    assert count(s, "Treasure") == 2 and count(s, "Food") == 1
    replay_matches(s)
    act(s2, "p1", type="choose", decision_id=d.id, option_ids=["no" if lives_first == "yes" else "yes"])
    assert count(s2, "Treasure") == 2 and count(s2, "Food") == 2  # the Food is part of the event Parallel Lives doubles
    replay_matches(s2)


def test_chatterfang_counts_every_token_of_the_event(cards):
    s = build(cards)
    token(s, "p1", "Peregrin Took", "2/3", PEREGRIN)
    token(s, "p1", "Chatterfang, Squirrel General", "3/3", CHATTERFANG)
    maker = token(s, "p1", "Maker", "1/1", TREASURER)
    activate(s, maker)
    d = decision(s)
    assert d is not None and d.player == "p1"
    peregrin_first = "yes" if "Peregrin Took first" in {o.id: o.label for o in d.options}["yes"] else "no"
    answer(s, peregrin_first)  # Treasure + Food, then a Squirrel for each
    assert (count(s, "Treasure"), count(s, "Food"), count(s, "Squirrel")) == (1, 1, 2)
    replay_matches(s)


# -- "can't gain life" (614.17, 119.7) ---------------------------------------------------------------------
PLAYERS_CANT_GAIN = "Players can't gain life."  # Rampaging Ferocidon / Leyline of Punishment (that line)
OPPONENTS_CANT_GAIN = "Your opponents can't gain life."  # Erebos, God of the Dead (that line)
SKULLCRACK = "{1}: Players can't gain life this turn."  # Skullcrack's first sentence, as an activated ability
STIGMA_LASHER = ("Wither\nWhenever this creature deals damage to a player, that player can't gain life for the rest of the "
                 "game.\n{1}: Stigma Lasher deals 1 damage to any target.")  # Stigma Lasher 2/1 (the ping is the test's)
FEAST = "{1}: Each player gains 2 life."


def test_players_cant_gain_life_and_tainted_remedy_cant_replace_it(cards):
    from tests.test_rules_replacements2 import TAINTED_REMEDY

    s = build(cards)
    permanent(s, "p2", "Tainted Remedy", "Enchantment", TAINTED_REMEDY)
    feast = token(s, "p1", "Feast", "0/1", FEAST)
    activate(s, feast)
    assert life(s, "p1") == 38 and life(s, "p2") == 42  # (the Remedy turns Alice's gain into a loss)
    ferocidon = token(s, "p1", "Rampaging Ferocidon", "3/3", PLAYERS_CANT_GAIN)
    activate(s, feast)
    assert life(s, "p1") == 38 and life(s, "p2") == 42  # 614.17c: a gain that can't happen isn't replaced either
    leech = token(s, "p1", "Leech", "1/1", "Lifelink\n{1}: Leech deals 1 damage to any target.")
    activate(s, leech, index=1, targets=["p2"])
    assert life(s, "p2") == 41 and life(s, "p1") == 38  # the damage is dealt, its lifelink gain isn't
    act(s, "p1", type="move", card_ids=[ferocidon.id], to={"zone": "graveyard"})
    activate(s, feast)
    assert life(s, "p2") == 43
    replay_matches(s)


def test_your_opponents_cant_gain_life(cards):
    s = build(cards)
    token(s, "p1", "Erebos, God of the Dead", "5/7", OPPONENTS_CANT_GAIN)
    activate(s, token(s, "p1", "Feast", "0/1", FEAST))
    assert life(s, "p1") == 42 and life(s, "p2") == 40
    replay_matches(s)


def test_cant_gain_life_this_turn_and_for_the_rest_of_the_game(cards):
    s = build(cards)
    crack = token(s, "p1", "Skullcrack", "0/1", SKULLCRACK)
    feast = token(s, "p1", "Feast", "0/1", FEAST)
    lasher = token(s, "p1", "Stigma Lasher", "2/1", STIGMA_LASHER)
    activate(s, crack)
    activate(s, feast)
    assert life(s, "p1") == 40 and life(s, "p2") == 40
    activate(s, lasher, index=2, targets=["p2"])
    run_until(s, lambda s: not s.state.zones.get("stack"))
    assert life(s, "p2") == 39
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    activate(s, feast)
    assert life(s, "p1") == 42 and life(s, "p2") == 39  # "this turn" ended; "the rest of the game" didn't
    replay_matches(s)


# -- abilities granted to graveyard cards (611.2c, 702.34) ------------------------------------------------
# "When Snapcaster Mage enters, target instant or sorcery card in your graveyard gains flashback until end of turn. The
# flashback cost is equal to its mana cost." (Snapcaster Mage) — as an activated ability of a custom permanent
SNAPCASTER = ("{1}: Target instant or sorcery card in your graveyard gains flashback until end of turn. The flashback cost "
              "is equal to its mana cost.")
PAST_IN_FLAMES = ("{1}: Each instant and sorcery card in your graveyard gains flashback until end of turn. The flashback "
                  "cost is equal to its mana cost.")  # Past in Flames (its own flashback {4}{R} left out)
KETHIS = ("{1}: Until end of turn, each legendary card in your graveyard gains \"You may play this card from your "
          "graveyard.\"")  # Kethis, the Hidden Hand (cost "Exile two legendary cards from your graveyard" replaced)


def to_graveyard(s, name, pid="p1"):
    card = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[card.id], to={"zone": "graveyard"})
    return s.state.cards[card.id]


def test_snapcaster_gives_flashback_until_end_of_turn_and_the_card_is_exiled(cards):
    s = build(cards, "Lightning Bolt")
    bolt = to_graveyard(s, "Lightning Bolt")
    mage = token(s, "p1", "Snapcaster Mage", "2/1", SNAPCASTER)
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    assert bolt.id not in s.view("p1")["rules"]["hints"]["castable"]
    activate(s, mage, targets=[bolt.id])
    assert bolt.id in s.view("p1")["rules"]["hints"]["castable"]
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    run_until(s, lambda s: not s.state.zones.get("stack"))
    assert life(s, "p2") == 37 and s.state.cards[bolt.id].zone == "p1:exile"  # 702.34a
    replay_matches(s)


def test_granted_flashback_ends_with_the_turn_and_follows_the_object(cards):
    s = build(cards, "Lightning Bolt", "Counterspell")
    bolt = to_graveyard(s, "Lightning Bolt")
    flames = token(s, "p1", "Past in Flames", "0/1", PAST_IN_FLAMES)
    activate(s, flames)
    counter = to_graveyard(s, "Counterspell")  # put there after it resolved: not affected (611.2c)
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1, "U": 2})
    castable = s.view("p1")["rules"]["hints"]["castable"]
    assert bolt.id in castable and counter.id not in castable
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "graveyard"})  # a new object (400.7)
    assert bolt.id not in s.view("p1")["rules"]["hints"]["castable"]
    replay_matches(s)


def test_kethis_lets_you_play_legendary_cards_from_your_graveyard_this_turn(cards):
    s = build(cards, "Honest Rutstein")
    rutstein = to_graveyard(s, "Honest Rutstein")
    kethis = token(s, "p1", "Kethis, the Hidden Hand", "3/4", KETHIS)
    activate(s, kethis)
    granted = rules(s).permissions
    assert len(granted) == 1 and granted[0].card == rutstein.id and granted[0].until == "end_of_turn"
    run_until(s, lambda s: s.state.turn.number == 2)
    assert rules(s).permissions == []
    replay_matches(s)


# -- skipping steps, phases and turns (614.10) ------------------------------------------------------------
WILD_WASTELAND = "Skip your draw step."  # Wild Wasteland (first line; its upkeep trigger left out)
STASIS = "Players skip their untap steps."  # Stasis (first line; its upkeep trigger left out)
EON_HUB = "Players skip their upkeep steps."  # Eon Hub
STONEHORN = "{1}: Target opponent skips their next combat phase."  # Stonehorn Dignitary's enters effect, activated
CHRONATOG = "{0}: This creature gets +3/+3 until end of turn. You skip your next turn. Activate only once each turn."  # Chronatog 1/2
FATIGUE = "{1}: Target player skips their next draw step."  # Fatigue, as an activated ability
YOSEI = "{1}: Target player skips their next untap step."  # Yosei's dies effect (first sentence), activated


def hand_size(s, pid):
    return len(s.state.zones.get(f"{pid}:hand", []))


def phases_until(s, done):
    """Pass along (no attacks, no blocks) until ``done``: the (turn, phase) pairs the game stopped in."""
    seen = []
    for _ in range(300):
        seen.append((s.state.turn.number, s.state.turn.phase))
        if done(s):
            return seen
        d = decision(s)
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        else:
            act(s, rules(s).priority, type="pass_priority")
    raise AssertionError("never got there")


def test_skip_your_draw_step(cards):
    s = build(cards)
    permanent(s, "p1", "Wild Wasteland", "Enchantment", WILD_WASTELAND)
    token(s, "p1", "Watcher", "1/1", "At the beginning of your draw step, you gain 1 life.")
    alice, bob = hand_size(s, "p1"), hand_size(s, "p2")
    phases_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert hand_size(s, "p2") == bob + 1  # Bob draws (the static skips its controller's draw step only)
    assert hand_size(s, "p1") == alice and life(s, "p1") == 40  # no draw, no "beginning of your draw step" (614.10a)
    replay_matches(s)


def test_stasis_skips_every_untap_step_and_a_one_shot_skip_waits(cards):
    s = build(cards)
    yosei = token(s, "p1", "Yosei", "2/2", YOSEI)
    activate(s, yosei, targets=["p2"])  # Bob skips his next untap step …
    permanent(s, "p1", "Stasis", "Enchantment", STASIS)
    forest = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    act(s, "p2", type="tap", card_ids=[forest.id])
    phases_until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    assert s.state.cards[forest.id].tapped  # Stasis skipped it …
    assert [r["player"] for r in rules(s).skips] == ["p2"]  # … and Yosei's waits for one that isn't (614.10a)
    replay_matches(s)


def test_eon_hub_skips_upkeep_and_its_triggers(cards):
    s = build(cards)
    permanent(s, "p2", "Eon Hub", "Artifact", EON_HUB)
    token(s, "p2", "Keeper", "1/1", "At the beginning of your upkeep, you gain 1 life.")
    phases_until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    assert life(s, "p2") == 40  # no upkeep: its trigger never triggered (614.10a)
    replay_matches(s)


def test_target_opponent_skips_their_next_combat_phase(cards):
    s = build(cards)
    dignitary = token(s, "p1", "Stonehorn Dignitary", "1/4", STONEHORN)
    activate(s, dignitary, targets=["p2"])
    assert [r["what"] for r in rules(s).skips] == ["combat"]
    token(s, "p1", "Drummer", "1/1", "At the beginning of combat on your turn, you gain 1 life.")
    token(s, "p2", "Drummer Two", "1/1", "At the beginning of combat on your turn, you gain 1 life.")
    phases_until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main2")
    assert life(s, "p1") == 41  # (Alice's own combat isn't skipped)
    assert life(s, "p2") == 40 and rules(s).skips == []  # Bob's was: no beginning of combat (614.10a)
    phases_until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main2")
    assert life(s, "p2") == 41  # only the next one
    replay_matches(s)


def test_you_skip_your_next_turn(cards):
    s = build(cards)
    chronatog = token(s, "p1", "Chronatog", "1/2", CHRONATOG)
    act(s, "p1", type="activate_ability", card_id=chronatog.id, ability=0)
    run_until(s, lambda s: not s.state.zones.get("stack"))
    run_until(s, lambda s: s.state.turn.number == 3)
    assert s.state.turn.active_player == "p2"  # Alice's turn (it would have been turn 3) never began
    run_until(s, lambda s: s.state.turn.number == 4)
    assert s.state.turn.active_player == "p1"
    replay_matches(s)


def test_target_player_skips_their_next_draw_step(cards):
    s = build(cards)
    fatigue = token(s, "p1", "Fatigue", "0/1", FATIGUE)
    activate(s, fatigue, targets=["p2"])
    bob = hand_size(s, "p2")
    run_until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    assert hand_size(s, "p2") == bob
    run_until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1")
    assert hand_size(s, "p2") == bob + 1  # only the next one
    replay_matches(s)


@pytest.mark.parametrize("text", [
    "Skip your upkeep step if you have no cards in hand.",  # Gibbering Descent (conditional)
    "{1}: Target player skips their next combat phase this turn.",  # Moment of Silence ("this turn")
    "{1}: Target opponent skips their next X turns.",
])
def test_skip_wordings_left_manual(text):
    assert not all(supported(text)), text


def test_a_shield_on_a_permanent_spell_covers_the_permanent_it_becomes(cards):
    """609.7a / 400.7: a permanent spell chosen as the source covers the permanent it becomes. Object numbers
    come from one table-wide counter, so the new object's id is bound as it enters, not predicted (other zone
    changes in between, such as the shield ability's own, take numbers too)."""
    from app.rules import source_shields

    s = build(cards)
    heed = permanent(s, "p1", "Pay No Heed", "Enchantment", "{1}: " + PAY_NO_HEED)
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss")
    act(s, krenko.owner, type="move", card_ids=[krenko.id], to={"zone": "stack"})
    spell_oid = rules(s).object_id(krenko.id)
    activate(s, heed)
    _choose(s, "Krenko")
    # the spell resolved after the shield's ability (the ability's own zone changes took numbers first)
    assert s.state.cards[krenko.id].zone.endswith(":battlefield")
    new_oid = rules(s).object_id(krenko.id)
    assert new_oid != f"{krenko.id}.{int(spell_oid.rsplit('.', 1)[1]) + 1}"
    shield = next(r for r in rules(s).replacements if r.get("kind") == "replace")
    assert shield["match"]["source"]["oids"] == [spell_oid, source_shields.BECOMES + spell_oid, new_oid]
    replay_matches(s)
