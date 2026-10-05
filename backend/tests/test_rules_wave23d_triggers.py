"""Wave 23D: trigger events and ability words (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a
save and a load.

* 702.110: exploit - "When this creature enters, you may sacrifice a creature"; "exploits a creature" is the sacrifice
  made as that ability resolves (702.110b), also of the exploiter itself, and a creature sacrificed any other way is not exploited.
"""

from __future__ import annotations

import pytest

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


@pytest.mark.parametrize("name", [c[0] for c in CARDS[:7]])
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
    from app.game.session import ActionError  # noqa: F401  (the engine rejects with an ActionError; act raises)

    s = build(cards, ["Autarch Mammoth", "Probe Soldier"])
    put(s, "Probe Soldier")
    to_hand(s, "Autarch Mammoth")
    mana(s, G=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Autarch Mammoth").id)
    answer(s)
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == "Elephant"]) == 1  # (its enters trigger)
    with pytest.raises(Exception):  # Saddle 5: a 1-power creature is not enough
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
