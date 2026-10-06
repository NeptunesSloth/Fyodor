"""Wave 26B: trigger wordings. Real Oracle text; every scenario checks the replay and a save and a load.

* 508.1d / 611.2: "That token gains haste until end of turn and attacks this combat if able." (Legion Warboss): the requirement ends with the combat.
* 508.5: "deals 1 damage to the player or planeswalker it's attacking" (Hellrider): the one the triggering attacker attacks.
* 118.12a: "That player may <cost>. If they don't, <effect>." read as "<effect> unless that player <pays the cost>".
* 701.20a: "reveal that many cards from the top of your library" after combat damage (Ojer Kaslem): the damage dealt.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave5j_token_copies import drive
from tests.wave9c_kit import build, card_named, check, life, mana, put

CARDS = [
    ("Legion Warboss", "{2}{R}", "Creature — Goblin Warrior", "2", "2",
     "Mentor\nAt the beginning of combat on your turn, create a 1/1 red Goblin creature token. That token gains haste until end of turn "
     "and attacks this combat if able."),
    ("Hellrider", "{2}{R}{R}", "Creature — Devil", "3", "3",
     "Haste\nWhenever a creature you control attacks, Hellrider deals 1 damage to the player or planeswalker it's attacking."),
    ("Raid Bombardment", "{2}{R}", "Enchantment", None, None,
     "Whenever a creature you control with power 2 or less attacks, this enchantment deals 1 damage to the player or planeswalker that "
     "creature is attacking."),
    ("Ojer Kaslem, Deepest Growth", "{3}{G}{G}", "Legendary Creature — God", "6", "6",
     "Trample\nWhenever Ojer Kaslem deals combat damage to a player, reveal that many cards from the top of your library. You may put a "
     "creature card and/or a land card from among them onto the battlefield. Put the rest on the bottom in a random order."),
    ("Probe Web", "{2}", "Enchantment", None, None,
     "At the beginning of each player's upkeep, that player may sacrifice a creature of their choice. If that player doesn't, you draw a card."),
    ("Probe Tomb", "{2}", "Enchantment", None, None,
     "At the beginning of each player's upkeep, that player may pay 2 life. If they don't, they lose 3 life."),
    ("Banishment", "{2}{W}{W}", "Enchantment", None, None,
     "When this enchantment enters, exile target nonland permanent an opponent controls and all other nonland permanents your opponents "
     "control with the same name as that permanent until this enchantment leaves the battlefield."),
    ("Hunted Horror", "{1}{B}{B}", "Creature — Horror", "4", "4",
     "Menace\nWhen this creature enters, target opponent creates two 3/3 green Centaur creature tokens with protection from black."),
    ("Probe Smash", "{W}", "Instant", None, None, "Destroy target enchantment."),
    ("Probe Imp", "{1}", "Creature — Imp", "1", "1", ""),
    ("Probe Brute", "{3}", "Creature — Ogre", "4", "4", ""),
]
EXTRA = [card(n, set_code="t26b", number=f"T{i:02d}", mana_cost=mc, cmc=float(sum(1 for _ in mc.split("}")) - 1), type_line=tl,
              colors=["B"] if "{B}" in mc else ["R"], color_identity=["R"], oracle_text=text, power=p, toughness=t)
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


@pytest.mark.parametrize("name", [c[0] for c in CARDS if c[5]])
def test_wave26b_cards_are_full(name):
    assert level(name) == "FULL", name


def ready(s, *names, pid="p1"):
    for n in names:
        s.state.rules.controlled_since[card_named(s, n, pid).id].turn = 0


def to_declare_attackers(s):
    act(s, "p1", type="pass_priority")  # -> beginning of combat: the triggers go on the stack
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"


def attack(s, *names, target="p2"):
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, n).id, "target": target} for n in names])
    drive(s)


def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.controller == pid and c.zone.endswith(":battlefield")]


def test_legion_warboss_token_has_haste_and_must_attack_this_combat(cards):
    s = build(cards, ["Legion Warboss"])
    put(s, "Legion Warboss")
    ready(s, "Legion Warboss")
    to_declare_attackers(s)
    [gob] = tokens(s, "Goblin")
    ch = Plan(s.state, "p1", s.cards, None).ch(gob)
    assert "haste" in ch.keywords and "must_attack" in ch.imposed
    assert s.state.rules.decision.kind == "declare_attackers"
    # a declaration without the token is illegal (508.1d)
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, "Legion Warboss").id, "target": "p2"}])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": gob.id, "target": "p2"}])
    drive(s)
    check(s)


def test_hellrider_damages_the_player_each_attacker_attacks(cards):
    s = build(cards, ["Hellrider", "Probe Imp", "Probe Brute"])
    put(s, "Hellrider")
    put(s, "Probe Imp")
    put(s, "Probe Brute")
    ready(s, "Hellrider", "Probe Imp", "Probe Brute")
    before = life(s, "p2")
    to_declare_attackers(s)
    attack(s, "Hellrider", "Probe Imp", "Probe Brute")
    # three attackers: three triggers of 1, then combat damage 3 + 1 + 4 (no blockers)
    assert life(s, "p2") == before - 3 - 8
    check(s)


def test_hellrider_damages_the_planeswalker_it_attacks_not_its_controller(cards):
    s = build(cards, ["Hellrider"], ["Test Walker Card"])
    put(s, "Hellrider")
    ready(s, "Hellrider")
    walker = put(s, "Test Walker Card", "p2")
    act(s, "p2", type="counter", card_ids=[walker.id], kind="loyalty", delta=5)
    before = life(s, "p2")
    to_declare_attackers(s)
    attack(s, "Hellrider", target=walker.id)
    assert life(s, "p2") == before  # (the trigger's 1 and the combat damage 3 both went to the planeswalker)
    assert s.state.cards[walker.id].counters.get("loyalty") == 1
    check(s)


def test_raid_bombardment_only_counts_small_attackers(cards):
    s = build(cards, ["Raid Bombardment", "Probe Imp", "Probe Brute"])
    put(s, "Raid Bombardment")
    put(s, "Probe Imp")
    put(s, "Probe Brute")
    ready(s, "Probe Imp", "Probe Brute")
    before = life(s, "p2")
    to_declare_attackers(s)
    attack(s, "Probe Imp", "Probe Brute")
    assert life(s, "p2") == before - 1 - 5  # (one trigger, for the Imp only)
    check(s)


def test_ojer_reveals_as_many_cards_as_damage_dealt(cards):
    s = build(cards, ["Ojer Kaslem, Deepest Growth"])
    put(s, "Ojer Kaslem, Deepest Growth")
    ready(s, "Ojer Kaslem, Deepest Growth")
    library, field = len(s.state.zones["p1:library"]), len(s.state.zones["p1:battlefield"])
    to_declare_attackers(s)
    attack(s, "Ojer Kaslem, Deepest Growth")
    assert life(s, "p2") == 40 - 6
    # six cards were revealed (the library is all Forests and a few spells): at most one creature and one land come out, the rest go to the bottom
    gained = len(s.state.zones["p1:battlefield"]) - field
    assert 1 <= gained <= 2 and len(s.state.zones["p1:library"]) == library - gained
    check(s)


def test_banishment_exiles_every_same_named_permanent_of_the_opponents_until_it_leaves(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Banishment"), (1, "Probe Smash"), (1, "Probe Imp"), (8, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(2, "Probe Imp"), (1, "Probe Brute"), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    mine = put(s, "Probe Imp")
    theirs = [c for c in s.state.cards.values() if c.name == "Probe Imp" and c.owner == "p2"]
    assert len(theirs) == 2
    for c in theirs:
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    brute = put(s, "Probe Brute", "p2")
    banishment = card_named(s, "Banishment")
    act(s, "p1", type="move", card_ids=[banishment.id], to={"zone": "hand"})
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=banishment.id)
    drive(s, choose=lambda d: [theirs[0].id] if any(o.id == theirs[0].id for o in d.options) else None)
    assert all(s.state.cards[c.id].zone == "p2:exile" for c in theirs)
    assert s.state.cards[mine.id].zone == "p1:battlefield" and s.state.cards[brute.id].zone == "p2:battlefield"
    check(s)
    smash = card_named(s, "Probe Smash")
    act(s, "p1", type="move", card_ids=[smash.id], to={"zone": "hand"})
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=smash.id, targets=[banishment.id])
    drive(s)
    assert s.state.cards[banishment.id].zone == "p1:graveyard"
    assert all(s.state.cards[c.id].zone == "p2:battlefield" for c in theirs)
    check(s)


def test_target_opponent_creates_tokens_with_protection(cards):
    from app.rules import protection

    s = build(cards, ["Hunted Horror"])
    horror = card_named(s, "Hunted Horror")
    act(s, "p1", type="move", card_ids=[horror.id], to={"zone": "hand"})
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=horror.id)
    drive(s)
    centaurs = tokens(s, "Centaur", "p2")
    assert len(centaurs) == 2
    plan = Plan(s.state, "p1", s.cards, None)
    assert all(protection.protected_from(plan.ch(c), plan.ch(horror)) for c in centaurs)
    check(s)
