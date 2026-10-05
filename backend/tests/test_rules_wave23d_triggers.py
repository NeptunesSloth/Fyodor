"""Wave 23D: trigger events and ability words (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a
save and a load.

* 702.110: exploit - "When this creature enters, you may sacrifice a creature"; "exploits a creature" is the sacrifice
  made as that ability resolves (702.110b), also of the exploiter itself, and a creature sacrificed any other way is not exploited.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand, zone_of

CARDS = [
    ("Fell Stinger", "{2}{B}", "Creature — Zombie Assassin", "2", "2",
     "Deathtouch\nExploit (When this creature enters, you may sacrifice a creature.)\n"
     "When this creature exploits a creature, target player draws two cards and loses 2 life."),
    ("Sidisi, Undead Vizier", "{3}{B}{B}", "Legendary Creature — Zombie Naga Wizard", "4", "6",
     "Deathtouch\nExploit (When this creature enters, you may sacrifice a creature.)\n"
     "When Sidisi exploits a creature, you may search your library for a card, put it into your hand, then shuffle."),
    ("Skull Skaab", "{2}{B}", "Creature — Zombie Warrior", "2", "3",
     "Exploit (When this creature enters, you may sacrifice a creature.)\n"
     "Whenever a creature you control exploits a nontoken creature, create a 2/2 black Zombie creature token."),
    ("Rakshasa Gravecaller", "{4}{B}", "Creature — Demon Rakshasa Wizard", "5", "5",
     "Exploit (When this creature enters, you may sacrifice a creature.)\n"
     "When this creature exploits a creature, create two 2/2 black Zombie creature tokens."),
    ("Colonel Autumn", "{1}{B}{B}", "Legendary Creature — Human Soldier", "2", "2",
     "Exploit (When this creature enters, you may sacrifice a creature.)\nOther legendary creatures you control have exploit."),
    ("Probe Legend", "{B}", "Legendary Creature — Human", "1", "1", ""),
    ("District Mascot", "{G}", "Creature — Dog Mount", "0", "0",
     "This creature enters with a +1/+1 counter on it.\n{1}{G}, Remove two +1/+1 counters from this creature: Destroy target artifact.\n"
     "Whenever this creature attacks while saddled, put a +1/+1 counter on it.\nSaddle 1"),
    ("Autarch Mammoth", "{4}{G}{G}", "Creature — Elephant Mount", "5", "5",
     "When this creature enters and whenever it attacks while saddled, create a 3/3 green Elephant creature token.\n"
     "Saddle 5 (Tap any number of other creatures you control with total power 5 or more: This Mount becomes saddled until end of turn. "
     "Saddle only as a sorcery.)"),
    ("Deathless Pilot", "{1}{B}", "Creature — Zombie Pilot", "2", "2",
     "This creature saddles Mounts and crews Vehicles as though its power were 2 greater.\n{3}{B}: Return this card from your graveyard to your hand."),
    ("Interface Ace", "{1}{W}", "Artifact Creature — Robot Pilot", "0", "4",
     "This creature saddles Mounts and crews Vehicles using its toughness rather than its power.\n"
     "Whenever this creature becomes tapped during your turn, untap it. This ability triggers only once each turn."),
    ("Roadside Assistance", "{2}{W}", "Enchantment — Aura", None, None,
     "Enchant creature or Vehicle\nWhen this Aura enters, create a 1/1 colorless Pilot creature token with \"This token saddles Mounts and "
     "crews Vehicles as though its power were 2 greater.\"\nEnchanted permanent gets +1/+1 and has lifelink."),
    ("Giant Beaver", "{3}{G}", "Creature — Beaver Mount", "4", "4",
     "Vigilance\nWhenever this creature attacks while saddled, put a +1/+1 counter on target creature that saddled it this turn.\n"
     "Saddle 3 (Tap any number of other creatures you control with total power 3 or more: This Mount becomes saddled until end of turn. "
     "Saddle only as a sorcery.)"),
    ("Getaway Car", "{3}", "Artifact — Vehicle", "4", "3",
     "Haste\nWhenever this Vehicle attacks or blocks, return up to one target creature that crewed it this turn to its owner's hand.\nCrew 1"),
    ("Golden Argosy", "{4}", "Legendary Artifact — Vehicle", "3", "6",
     "Whenever Golden Argosy attacks, exile each creature that crewed it this turn. Return them to the battlefield tapped under their owner's "
     "control at the beginning of the next end step.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This "
     "Vehicle becomes an artifact creature until end of turn.)"),
    ("Speedway Fanatic", "{1}{R}", "Creature — Human Pilot", "2", "1", "Haste\nWhenever this creature crews a Vehicle, that Vehicle gains haste until end of turn."),
    ("Reckless Velocitaur", "{3}{R}", "Creature — Minotaur Pilot", "3", "3",
     "Whenever this creature saddles a Mount or crews a Vehicle during your main phase, that Mount or Vehicle gets +2/+0 and gains trample until end of turn."),
    ("Mobilizer Mech", "{1}{U}", "Artifact — Vehicle", "3", "4",
     "Flying\nWhenever this Vehicle becomes crewed, up to one other target Vehicle you control becomes an artifact creature until end of turn.\n"
     "Crew 3 (Tap any number of creatures you control with total power 3 or more: This Vehicle becomes an artifact creature until end of turn.)"),
    ("Probe Giant", "{W}", "Creature — Giant", "5", "5", ""),
    ("Probe Soldier", "{W}", "Creature — Human Soldier", "1", "1", ""),
]
EXTRA = [card(n, set_code="t23d", number=f"D{i:02d}", mana_cost=mc, cmc=float(sum(1 for _ in mc.split("}")) - 1), type_line=tl,
              colors=["B"], color_identity=["B"], oracle_text=text, power=p, toughness=t)
         for i, (n, mc, tl, p, t, text) in enumerate(CARDS)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def level(name):
    c = next(c for c in EXTRA if c["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


@pytest.mark.parametrize("name", [c[0] for c in CARDS if c[0] not in ("Probe Giant", "Probe Soldier", "Probe Legend")])
def test_exploit_cards_are_full(name):
    assert level(name) == "FULL", name


def hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def play(s, name, *picks):
    """Cast ``name`` and answer each decision from ``picks`` (an option id each), else with its first option."""
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id)
    answer(s, *picks)
    return s


def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.controller == pid and c.zone.endswith(":battlefield")]


def test_exploit_sacrificing_another_creature_triggers_the_exploit_ability(cards):
    s = build(cards, ["Fell Stinger", "Probe Soldier"])
    soldier = put(s, "Probe Soldier")
    to_hand(s, "Fell Stinger")
    mana(s, B=3)
    hand_then, bob_then = hand(s) - 1, hand(s, "p2")
    play(s, "Fell Stinger", "yes", soldier.id, "p2")
    assert zone_of(s, "Probe Soldier") == "p1:graveyard" and zone_of(s, "Fell Stinger") == "p1:battlefield"
    assert hand(s, "p2") == bob_then + 2 and life(s, "p2") == 38 and hand(s) == hand_then and life(s) == 40
    check(s)


def test_declining_the_exploit_sacrifices_nothing(cards):
    s = build(cards, ["Fell Stinger", "Probe Soldier"])
    put(s, "Probe Soldier")
    to_hand(s, "Fell Stinger")
    mana(s, B=3)
    play(s, "Fell Stinger", "no")
    assert zone_of(s, "Probe Soldier") == "p1:battlefield" and life(s, "p2") == 40
    check(s)


def test_a_creature_exploits_itself_and_its_own_exploit_trigger_still_happens(cards):
    s = build(cards, ["Rakshasa Gravecaller"])
    gc = to_hand(s, "Rakshasa Gravecaller")
    mana(s, B=5)
    play(s, "Rakshasa Gravecaller", "yes", gc.id)
    assert zone_of(s, "Rakshasa Gravecaller") == "p1:graveyard"
    assert len(tokens(s, "Zombie")) == 2  # (702.110b: it sacrificed a creature as its exploit ability resolved: itself)
    check(s)


@pytest.mark.parametrize("token_victim,zombies", [(False, 1), (True, 0)])
def test_skull_skaab_wants_a_nontoken_creature_exploited(cards, token_victim, zombies):
    s = build(cards, ["Skull Skaab", "Probe Soldier"])
    if token_victim:
        act(s, "p1", type="create_token", player="p1", token={"name": "Goblin", "type_line": "Token Creature — Goblin", "power": "1",
                                                                "toughness": "1", "text": ""})
        victim = next(c for c in s.state.cards.values() if c.is_token)
    else:
        victim = put(s, "Probe Soldier")
    to_hand(s, "Skull Skaab")
    mana(s, B=3)
    play(s, "Skull Skaab", "yes", victim.id)
    assert victim.id not in s.state.cards or s.state.cards[victim.id].zone != "p1:battlefield"
    assert len(tokens(s, "Zombie")) == zombies
    check(s)


def test_a_granted_exploit_triggers_as_the_creature_enters(cards):
    """Colonel Autumn: "Other legendary creatures you control have exploit" - a legendary creature entering has it (603.6a)."""
    s = build(cards, ["Colonel Autumn", "Probe Legend", "Probe Soldier"])
    put(s, "Colonel Autumn")
    soldier = put(s, "Probe Soldier")
    to_hand(s, "Probe Legend")
    mana(s, B=3)
    play(s, "Probe Legend", "yes", soldier.id)
    assert zone_of(s, "Probe Soldier") == "p1:graveyard" and zone_of(s, "Probe Legend") == "p1:battlefield"
    check(s)


def saddle_index(s, name):
    from app.rules.plan import Plan

    c = card_named(s, name)
    return next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(c).abilities if a.text.lower().startswith("saddle"))


def sick_no_more(s, *names):
    for n in names:
        s.state.rules.controlled_since[card_named(s, n).id].turn = 0


def saddle_up(s, mount, *creatures):
    act(s, "p1", type="activate_ability", card_id=card_named(s, mount).id, ability=saddle_index(s, mount),
        crew=[card_named(s, n).id for n in creatures])
    from tests.test_rules_wave5j_token_copies import drive

    drive(s)


def attack(s, name):
    from tests.test_rules_wave5j_token_copies import drive

    act(s, "p1", type="pass_priority")  # -> declare attackers
    assert s.state.rules.decision.kind == "declare_attackers"
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, name).id, "target": "p2"}])
    drive(s)


@pytest.mark.parametrize("saddled", [True, False])
def test_a_mount_attacking_while_saddled_triggers_only_when_saddled(cards, saddled):
    s = build(cards, ["District Mascot", "Probe Soldier"])
    to_hand(s, "District Mascot")
    put(s, "Probe Soldier")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "District Mascot").id)
    answer(s)
    sick_no_more(s, "District Mascot", "Probe Soldier")
    assert pt(s, "District Mascot") == (1, 1)
    if saddled:
        saddle_up(s, "District Mascot", "Probe Soldier")  # Saddle 1: tap Probe Soldier (702.171a)
        assert card_named(s, "Probe Soldier").tapped or s.state.cards[card_named(s, "Probe Soldier").id].tapped
    attack(s, "District Mascot")
    assert pt(s, "District Mascot") == ((2, 2) if saddled else (1, 1))
    check(s)


def test_saddle_is_a_sorcery_speed_ability_and_needs_enough_power(cards):
    s = build(cards, ["Autarch Mammoth", "Probe Soldier"])
    put(s, "Probe Soldier")
    to_hand(s, "Autarch Mammoth")
    mana(s, G=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Autarch Mammoth").id)
    answer(s)
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == "Elephant"]) == 1  # (its enters trigger)
    with pytest.raises(ActionError, match="total power 5"):  # Saddle 5: a 1-power creature is not enough
        act(s, "p1", type="activate_ability", card_id=card_named(s, "Autarch Mammoth").id, ability=saddle_index(s, "Autarch Mammoth"),
            crew=[card_named(s, "Probe Soldier").id])
    check(s)


@pytest.mark.parametrize("saddled", [True, False])
def test_enters_and_attacks_while_saddled_keeps_its_while(cards, saddled):
    """Autarch Mammoth: "When this creature enters and whenever it attacks while saddled" - the condition belongs to the attack only."""
    s = build(cards, ["Autarch Mammoth", "Probe Giant"])
    put(s, "Probe Giant")
    to_hand(s, "Autarch Mammoth")
    mana(s, G=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Autarch Mammoth").id)
    answer(s)
    sick_no_more(s, "Autarch Mammoth")
    if saddled:
        saddle_up(s, "Autarch Mammoth", "Probe Giant")
    attack(s, "Autarch Mammoth")
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == "Elephant"]) == (2 if saddled else 1)
    check(s)


@pytest.mark.parametrize("helper,others,ok", [("Deathless Pilot", 0, False), ("Deathless Pilot", 1, True), ("Interface Ace", 0, False),
                                                ("Interface Ace", 1, True)])
def test_saddling_counts_the_power_a_creature_saddles_with(cards, helper, others, ok):
    """Saddle 5 (702.171a: total power 5 or greater): Deathless Pilot counts as 2 greater (4), Interface Ace by its toughness (4)."""
    s = build(cards, ["Autarch Mammoth", helper, "Probe Soldier"])
    put(s, helper)
    soldier = put(s, "Probe Soldier")
    to_hand(s, "Autarch Mammoth")
    mana(s, G=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Autarch Mammoth").id)
    answer(s)
    picked = [card_named(s, helper).id, *([soldier.id] if others else [])]
    index = saddle_index(s, "Autarch Mammoth")
    if ok:
        act(s, "p1", type="activate_ability", card_id=card_named(s, "Autarch Mammoth").id, ability=index, crew=picked)
        answer(s)
        assert any(f.kind == "saddled" for f in s.state.rules.turn_log.facts)  # (Interface Ace untaps itself, so tapped is no test)
    else:
        with pytest.raises(ActionError, match="5 total power"):
            act(s, "p1", type="activate_ability", card_id=card_named(s, "Autarch Mammoth").id, ability=index, crew=picked)
    check(s)


def test_a_pilot_token_saddles_and_crews_as_though_its_power_were_two_greater(cards):
    """Roadside Assistance's Pilot token (a quoted static of the token) counts 3 toward Saddle (702.171a)."""
    from app.rules.plan import Plan

    s = build(cards, ["Roadside Assistance", "Probe Soldier"])
    soldier = put(s, "Probe Soldier")
    to_hand(s, "Roadside Assistance")
    mana(s, W=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Roadside Assistance").id, targets=[soldier.id])
    answer(s)
    pilot = next(c for c in s.state.cards.values() if c.is_token and c.name == "Pilot")
    assert "crew_plus:2" in Plan(s.state, "p1", s.cards, None).ch(pilot).imposed
    check(s)


def crew_index(s, name):
    from app.rules.plan import Plan

    return next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(card_named(s, name)).abilities if a.text.lower().startswith("crew"))


@pytest.mark.parametrize("saddled", [True, False])
def test_the_creature_that_saddled_it_this_turn_gets_the_counter(cards, saddled):
    s = build(cards, ["Giant Beaver", "Probe Giant"])
    put(s, "Probe Giant")
    put(s, "Giant Beaver")
    sick_no_more(s, "Giant Beaver")
    if saddled:
        saddle_up(s, "Giant Beaver", "Probe Giant")  # Saddle 3: tap the 5-power Giant
    attack(s, "Giant Beaver")
    assert pt(s, "Probe Giant") == ((6, 6) if saddled else (5, 5))
    check(s)


def test_a_creature_that_crewed_the_vehicle_this_turn_is_returned(cards):
    s = build(cards, ["Getaway Car", "Probe Soldier"])
    put(s, "Probe Soldier")
    put(s, "Getaway Car")
    sick_no_more(s, "Getaway Car")
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Getaway Car").id, ability=crew_index(s, "Getaway Car"),
        crew=[card_named(s, "Probe Soldier").id])
    from tests.test_rules_wave5j_token_copies import drive

    drive(s)
    act(s, "p1", type="pass_priority")  # -> declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, "Getaway Car").id, "target": "p2"}])
    drive(s, choose=lambda d: [card_named(s, "Probe Soldier").id] if d.kind == "choose_cards" or "target" in d.prompt else None)
    assert zone_of(s, "Probe Soldier") == "p1:hand"
    check(s)


def test_golden_argosy_sends_the_creatures_that_crewed_it_away_and_back_tapped(cards):
    from tests.test_rules_conditionals import until
    from tests.test_rules_wave5j_token_copies import drive

    s = build(cards, ["Golden Argosy", "Probe Soldier"])
    put(s, "Probe Soldier")
    put(s, "Golden Argosy")
    sick_no_more(s, "Golden Argosy")
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Golden Argosy").id, ability=crew_index(s, "Golden Argosy"),
        crew=[card_named(s, "Probe Soldier").id])
    drive(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, "Golden Argosy").id, "target": "p2"}])
    drive(s)
    assert zone_of(s, "Probe Soldier") == "p1:exile"
    until(s, lambda s: s.state.turn.phase == "end" or s.state.turn.number > 1, limit=200)
    drive(s)
    assert zone_of(s, "Probe Soldier") == "p1:battlefield" and s.state.cards[card_named(s, "Probe Soldier").id].tapped
    check(s)


def crewed(s, vehicle, *creatures, picks=()):
    from tests.test_rules_wave5j_token_copies import drive

    act(s, "p1", type="activate_ability", card_id=card_named(s, vehicle).id, ability=crew_index(s, vehicle),
        crew=[card_named(s, n).id for n in creatures])
    drive(s, choose=lambda d: list(picks) or None)


def test_a_creature_that_crews_gives_the_vehicle_haste(cards):
    """Speedway Fanatic: "Whenever this creature crews a Vehicle, that Vehicle gains haste until end of turn" (702.122b)."""
    s = build(cards, ["Speedway Fanatic", "Golden Argosy"])
    put(s, "Speedway Fanatic")
    put(s, "Golden Argosy")  # (just arrived: summoning sick, 302.6)
    crewed(s, "Golden Argosy", "Speedway Fanatic")
    assert "Haste" in {k.title() for k in ch_of(s, "Golden Argosy").keywords}
    check(s)


def ch_of(s, name):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(card_named(s, name))


def test_crewing_during_your_main_phase_pumps_the_vehicle(cards):
    s = build(cards, ["Reckless Velocitaur", "Golden Argosy"])
    put(s, "Reckless Velocitaur")
    put(s, "Golden Argosy")
    crewed(s, "Golden Argosy", "Reckless Velocitaur")
    assert pt(s, "Golden Argosy") == (5, 6)
    assert "Trample" in {k.title() for k in ch_of(s, "Golden Argosy").keywords}
    check(s)


def test_during_your_main_phase_is_part_of_the_event():
    from app.rules import events

    cond = events.parse_condition("~ saddles a Mount or crews a Vehicle during your main phase")
    assert cond["during"] == "you" and all(c["main_phase"] for c in cond["conds"]) and {c["event"] for c in cond["conds"]} == {"crew", "saddle"}


def test_becomes_crewed_triggers_when_the_crew_ability_resolves(cards):
    """Mobilizer Mech (702.122e): another Vehicle becomes an artifact creature too."""
    s = build(cards, ["Mobilizer Mech", "Golden Argosy", "Probe Giant"])
    put(s, "Mobilizer Mech")
    put(s, "Golden Argosy")
    put(s, "Probe Giant")
    assert "Creature" not in ch_of(s, "Golden Argosy").types
    crewed(s, "Mobilizer Mech", "Probe Giant", picks=[card_named(s, "Golden Argosy").id])
    assert "Creature" in ch_of(s, "Golden Argosy").types and "Creature" in ch_of(s, "Mobilizer Mech").types
    check(s)
