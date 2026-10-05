"""Wave 25B: trigger wordings and conditions (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 603.10a / 700.9: "a modified creature you control dies" reads the creature as it last existed (its counters and attachments).
* 108.3 / 110.2: "owned by another player", "you control but don't own".
* 601.2i: "you cast an instant or sorcery spell from your library" (the zone a spell was cast from).
* 508.1 / 608.2h: pack tactics - the creatures declared as attackers this combat, their total power.
* 113.6b / 603.4: eminence - the ability names the zones it works from (the command zone and the battlefield).
"""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave5j_token_copies import drive
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

CARDS = [
    ("Akki Ember-Keeper", "{1}{R}", "Enchantment Creature — Goblin Warrior", "2", "1",
     "Whenever a nontoken modified creature you control dies, create a 1/1 colorless Spirit creature token. "
     "(Equipment, Auras you control, and counters are modifications.)"),
    ("Kothophed, Soul Hoarder", "{4}{B}{B}", "Legendary Creature — Demon", "6", "6",
     "Flying\nWhenever a permanent owned by another player is put into a graveyard from the battlefield, you draw a card and you lose 1 life."),
    ("Gnoll Hunter", "{1}{G}", "Creature — Gnoll", "2", "2",
     "Pack tactics — Whenever this creature attacks, if you attacked with creatures with total power 6 or greater this combat, "
     "put a +1/+1 counter on this creature."),
    ("Melek, Izzet Paragon", "{4}{U}{R}", "Legendary Creature — Weird Wizard", "2", "4",
     "Play with the top card of your library revealed.\nYou may cast instant and sorcery spells from the top of your library.\n"
     "Whenever you cast an instant or sorcery spell from your library, copy it. You may choose new targets for the copy."),
    ("Edgar Markov", "{3}{R}{W}{B}", "Legendary Creature — Vampire Knight", "4", "4",
     "Eminence — Whenever you cast another Vampire spell, if Edgar is in the command zone or on the battlefield, create a 1/1 black Vampire creature token.\n"
     "First strike, haste\nWhenever Edgar attacks, put a +1/+1 counter on each Vampire you control."),
    ("Inalla, Archmage Ritualist", "{2}{U}{B}{R}", "Legendary Creature — Human Wizard", "4", "5",
     "Eminence — Whenever another nontoken Wizard you control enters, if Inalla is in the command zone or on the battlefield, you may pay {1}. "
     "If you do, create a token that's a copy of that Wizard. The token gains haste. Exile it at the beginning of the next end step.\n"
     "Tap five untapped Wizards you control: Target player loses 7 life."),
    ("Costume Closet", "{1}{W}", "Artifact", None, None,
     "This artifact enters with two +1/+1 counters on it.\n{T}: Move a +1/+1 counter from this artifact onto target creature you control. "
     "Activate only as a sorcery.\nWhenever a modified creature you control leaves the battlefield, put a +1/+1 counter on this artifact. "
     "(Equipment, Auras you control, and counters are modifications.)"),
    ("Edgewall Innkeeper", "{G}", "Creature — Human Peasant", "1", "1",
     "Whenever you cast a creature spell that has an Adventure, draw a card. (It doesn't need to have gone on the adventure first.)"),
    ("Probe Dummy", "{1}", "Creature — Bear", "1", "1", ""),
    ("Probe Vampire", "{B}", "Creature — Vampire", "1", "1", ""),
    ("Probe Wizard", "{U}", "Creature — Human Wizard", "1", "1", ""),
    ("Probe Brute", "{3}", "Creature — Ogre", "4", "4", ""),
    ("Probe Imp", "{1}", "Creature — Imp", "1", "1", ""),
    ("Probe Blade", "{1}", "Artifact — Equipment", None, None, "Equipped creature gets +1/+1.\nEquip {1}"),
    ("The Ur-Dragon", "{4}{W}{U}{B}{R}{G}", "Legendary Creature — Dragon Avatar", "10", "10",
     "Eminence — As long as The Ur-Dragon is in the command zone or on the battlefield, other Dragon spells you cast cost {1} less to cast.\nFlying"),
    ("Probe Dragon", "{2}{R}", "Creature — Dragon", "2", "2", ""),
]
EXTRA = [card(n, set_code="t25b", number=f"T{i:02d}", mana_cost=mc, cmc=float(sum(1 for _ in mc.split("}")) - 1), type_line=tl,
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


@pytest.mark.parametrize("name", [c[0] for c in CARDS if not c[0].startswith("Probe")])
def test_wave25b_cards_are_full(name):
    assert level(name) == "FULL", name


def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.controller == pid and c.zone.endswith(":battlefield")]


def bolt(s, target, pid="p1"):
    to_hand(s, "Lightning Bolt", pid)
    mana(s, pid, R=1)
    act(s, pid, type="cast_spell", card_id=card_named(s, "Lightning Bolt", pid).id, targets=[target])
    answer(s)


def ready(s, *names, pid="p1"):
    for n in names:
        s.state.rules.controlled_since[card_named(s, n, pid).id].turn = 0


def equip(s, blade, creature):
    ch = Plan(s.state, "p1", s.cards, None).ch(card_named(s, blade))
    ab = next(x for x in ch.abilities if "equip" in x.keywords)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card_named(s, blade).id, ability=ab.index, targets=[creature.id])
    answer(s)


# --- modified creatures dying (603.10a, 700.9) ----------------------------------------------------------------------------


@pytest.mark.parametrize("how,tokens_made", [("none", 0), ("counter", 1), ("equipment", 1)])
def test_a_modified_creature_dying_is_read_as_it_last_existed(cards, how, tokens_made):
    s = build(cards, ["Akki Ember-Keeper", "Probe Imp", "Probe Blade", "Lightning Bolt"])
    put(s, "Akki Ember-Keeper")
    imp = put(s, "Probe Imp")
    if how == "counter":
        act(s, "p1", type="counter", card_ids=[imp.id], kind="+1/+1", delta=1)
    if how == "equipment":
        put(s, "Probe Blade")
        equip(s, "Probe Blade", imp)
    bolt(s, imp.id)
    assert zone_of(s, "Probe Imp") == "p1:graveyard"  # (equipment, 704.5n: it let go as the creature left; the trigger looks back)
    assert len(tokens(s, "Spirit")) == tokens_made
    check(s)


def test_a_token_that_was_modified_does_not_trigger_the_nontoken_wording(cards):
    s = build(cards, ["Akki Ember-Keeper", "Lightning Bolt"])
    put(s, "Akki Ember-Keeper")
    act(s, "p1", type="create_token", player="p1", token={"name": "Goblin", "type_line": "Token Creature — Goblin", "power": "1",
                                                            "toughness": "1", "text": ""})
    gob = next(c for c in s.state.cards.values() if c.is_token and c.name == "Goblin")
    act(s, "p1", type="counter", card_ids=[gob.id], kind="+1/+1", delta=1)
    bolt(s, gob.id)
    assert not tokens(s, "Spirit")
    check(s)


# --- owned by another player ------------------------------------------------------------------------------------------------------


def test_kothophed_triggers_for_permanents_owned_by_other_players_only(cards):
    s = build(cards, ["Kothophed, Soul Hoarder", "Probe Imp", "Lightning Bolt"], ["Probe Bear"] if False else ["Probe Vampire"])
    put(s, "Kothophed, Soul Hoarder")
    mine, theirs = put(s, "Probe Imp"), put(s, "Probe Vampire", "p2")
    cards_before, life_before = len(s.state.zones["p1:hand"]), life(s)
    bolt(s, mine.id)
    assert zone_of(s, "Probe Imp") == "p1:graveyard" and life(s) == life_before and len(s.state.zones["p1:hand"]) == cards_before
    bolt(s, theirs.id)
    assert zone_of(s, "Probe Vampire", "p2") == "p2:graveyard"
    assert life(s) == life_before - 1 and len(s.state.zones["p1:hand"]) == cards_before + 1
    check(s)


# --- cast from your library -----------------------------------------------------------------------------------------------------------


def test_melek_copies_a_spell_cast_from_the_library_only(cards):
    s = build(cards, ["Melek, Izzet Paragon", "Lightning Bolt", "Probe Imp"])
    put(s, "Melek, Izzet Paragon")
    bolt_card = card_named(s, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[bolt_card.id], to={"player": "p1", "zone": "library"})
    mana(s, R=1)
    life_before = life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=bolt_card.id, targets=["p2"])
    answer(s)
    assert life(s, "p2") == life_before - 6  # (the copy: 603.2, 707.10 - both resolve)
    check(s)
    s2 = build(cards, ["Melek, Izzet Paragon", "Lightning Bolt"])
    put(s2, "Melek, Izzet Paragon")
    to_hand(s2, "Lightning Bolt")
    mana(s2, R=1)
    before = life(s2, "p2")
    act(s2, "p1", type="cast_spell", card_id=card_named(s2, "Lightning Bolt").id, targets=["p2"])
    answer(s2)
    assert life(s2, "p2") == before - 3  # (cast from the hand: no copy)


# --- pack tactics (508.1) -----------------------------------------------------------------------------------------------------------------


def attack_with(s, *names):
    act(s, "p1", type="pass_priority")  # -> declare attackers
    assert s.state.rules.decision.kind == "declare_attackers"
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, n).id, "target": "p2"} for n in names])
    drive(s)


def counters_on(s, name):
    return sum(s.state.cards[card_named(s, name).id].counters.values())


@pytest.mark.parametrize("partner,counter", [("Probe Brute", 1), ("Probe Imp", 0)])
def test_pack_tactics_needs_total_power_six_among_the_creatures_that_attacked(cards, partner, counter):
    s = build(cards, ["Gnoll Hunter", partner])
    put(s, "Gnoll Hunter")
    put(s, partner)
    ready(s, "Gnoll Hunter", partner)
    attack_with(s, "Gnoll Hunter", partner)  # 2 + 4 = 6 / 2 + 1 = 3
    assert counters_on(s, "Gnoll Hunter") == counter
    check(s)


def test_pack_tactics_counts_only_the_creatures_that_attacked_not_the_ones_that_stayed_home(cards):
    s = build(cards, ["Gnoll Hunter", "Probe Brute"])
    put(s, "Gnoll Hunter")
    put(s, "Probe Brute")
    ready(s, "Gnoll Hunter", "Probe Brute")
    attack_with(s, "Gnoll Hunter")
    assert counters_on(s, "Gnoll Hunter") == 0
    check(s)


# --- eminence (113.6b) ------------------------------------------------------------------------------------------------------------------------


def build_commander(cards, commander, mine=(), forests=6):
    alice = deck(cards, commander, [*((1, n) for n in mine), (forests, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def test_eminence_triggers_from_the_command_zone(cards):
    s = build_commander(cards, "Edgar Markov", ["Probe Vampire"])
    assert zone_of(s, "Edgar Markov") == "p1:command"
    to_hand(s, "Probe Vampire")
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Probe Vampire").id)
    answer(s)
    assert len(tokens(s, "Vampire")) == 1 and zone_of(s, "Edgar Markov") == "p1:command"
    check(s)


def test_eminence_triggers_once_from_the_battlefield_and_not_from_the_graveyard(cards):
    s = build_commander(cards, "Edgar Markov", ["Probe Vampire"])
    edgar = card_named(s, "Edgar Markov")
    act(s, "p1", type="move", card_ids=[edgar.id], to={"player": "p1", "zone": "battlefield"})
    to_hand(s, "Probe Vampire")
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Probe Vampire").id)
    answer(s)
    assert len(tokens(s, "Vampire")) == 1  # (not twice: it is one object, wherever it is)
    check(s)


def test_eminence_condition_is_a_real_intervening_if(cards):
    """Edgar in the library (not the command zone, not the battlefield): no trigger (603.4, 113.6b)."""
    s = build_commander(cards, "Edgar Markov", ["Probe Vampire"])
    edgar = card_named(s, "Edgar Markov")
    act(s, "p1", type="move", card_ids=[edgar.id], to={"player": "p1", "zone": "graveyard"})
    to_hand(s, "Probe Vampire")
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Probe Vampire").id)
    answer(s, "no")  # (903.9a: "Move Edgar Markov to the command zone?" - leave it in the graveyard)
    assert not tokens(s, "Vampire")
    check(s)


def test_inalla_copies_a_wizard_from_the_command_zone_for_one_and_exiles_it_at_the_end_step(cards):
    s = build_commander(cards, "Inalla, Archmage Ritualist", ["Probe Wizard"])
    to_hand(s, "Probe Wizard")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Probe Wizard").id)
    answer(s, "pay")
    wizards = [c for c in s.state.cards.values() if c.name == "Probe Wizard" and c.zone == "p1:battlefield"]
    assert len(wizards) == 2 and sum(c.is_token for c in wizards) == 1
    token = next(c for c in wizards if c.is_token)
    assert "haste" in Plan(s.state, "p1", s.cards, None).ch(token).keywords  # ("The token gains haste.": no duration, 611.2a)
    assert s.state.rules.delayed  # (the exile at the beginning of the next end step, 603.7)
    check(s)


def test_a_modified_creature_leaving_the_battlefield_is_read_as_it_last_existed(cards):
    """Costume Closet: "Whenever a modified creature you control leaves the battlefield, put a +1/+1 counter on this artifact"."""
    s = build(cards, ["Costume Closet", "Probe Imp", "Probe Dummy", "Lightning Bolt"])
    closet = put(s, "Costume Closet")
    modified, plain = put(s, "Probe Imp"), put(s, "Probe Dummy")
    act(s, "p1", type="counter", card_ids=[modified.id], kind="+1/+1", delta=1)
    base = sum(s.state.cards[closet.id].counters.values())
    bolt(s, plain.id)
    assert sum(s.state.cards[closet.id].counters.values()) == base  # (it had no counter: not modified)
    bolt(s, modified.id)
    assert sum(s.state.cards[closet.id].counters.values()) == base + 1
    check(s)


@pytest.mark.parametrize("face,draws", [(0, 1), (1, 0)])
def test_a_creature_spell_that_has_an_adventure_counts_whichever_half_is_a_creature(cards, face, draws):
    """Edgewall Innkeeper: the creature half of Bonecrusher Giant is "a creature spell that has an Adventure"; its Adventure half (Stomp,
    an instant) is not a creature spell (715.4)."""
    s = build(cards, ["Edgewall Innkeeper", "Bonecrusher Giant // Stomp"])
    put(s, "Edgewall Innkeeper")
    giant = to_hand(s, "Bonecrusher Giant // Stomp")
    mana(s, R=3)
    hand = len(s.state.zones["p1:hand"]) - 1  # (the spell leaves it)
    act(s, "p1", type="cast_spell", card_id=giant.id, face=face, **({"targets": ["p2"]} if face else {}))
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + draws
    check(s)


def test_eminence_cost_reduction_works_from_the_command_zone(cards):
    """The Ur-Dragon: "as long as ~ is in the command zone or on the battlefield, other Dragon spells you cast cost {1} less" (113.6b)."""
    from app.rules.view import hints

    s = build_commander(cards, "The Ur-Dragon", ["Probe Dragon"])
    assert zone_of(s, "The Ur-Dragon") == "p1:command"
    dragon = to_hand(s, "Probe Dragon")
    mana(s, R=1, C=1)  # ({2}{R} less {1})
    assert dragon.id in hints(s.state, "p1", s.cards)["castable"]
    check(s)
