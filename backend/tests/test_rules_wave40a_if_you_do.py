"""Wave 40A: "If you do" (second pass, commanders first), CR 2026-09-25, real Oracle text (tests/fixtures/wave40a_cards.json from data/cards.sqlite).
Every scenario checks the replay and a save and a load, and both answers (accept / decline).

* 118.12: "If [a player] [does, doesn't, or can't]" checks whether the player chose to pay an optional cost (or started to pay a mandatory one),
  regardless of what events actually occurred; 118.3: a cost that can't be paid in full isn't offered; 119.4: life can be paid only from a total at least
  that large. Lorcan: "you may pay life equal to its mana value" is that much life, whether or not the clause after "If you do" says so.
* 608.2c, 608.2d: the instructions in order; a "you may" is the player's choice as it is reached. Taborax / Take Out the Trash / Chandra's Defeat: "If [condition],
  you may [A]. If you do, [B]." — the condition gates the pair; Strefan: B is itself a "you may" (a card from the hidden hand, or none).
* 608.2c "this way": Rulik Mons "If you didn't put a card onto the battlefield this way" asks what the optional pick before it did.
* 603.2, 508.4: Gyrus's attack trigger (a "lesser power" than Gyrus's own) and the copy that enters attacking; Moku: one duration for two subjects (611.2a).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, token_of, until
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand
from tests.wave36a_kit import attack, pick, ready, to_gy

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave40a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w40a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = [c["name"] for c in DATA][:17]  # (the rest of the file only sets the table: a Planeswalker, a Vampire, ...)


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_the_if_you_do_cards_are_full(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL", (name, coverage.of_characteristics(chs).manual_parts)


def zone(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].zone


def subtypes(s, name, pid="p1"):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(card_named(s, name, pid)).subtypes


def asked(s, limit=40):
    """Pass priority until a decision comes up (returned), or everything has resolved (None)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            return d
        if not s.state.zones.get("stack"):
            return None
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("still resolving")


def answer(s, option):
    d = asked(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])


# -- Lorcan, Warlock Collector: "you may pay life equal to its mana value. If you do, put it onto the battlefield under your control." ----------------
def lorcan(cards, creature="Twisted Abomination", life_total=40):
    """Lorcan is in play; Alice destroys Bob's ``creature`` with Murder (it dies: a creature card is put into an opponent's graveyard)."""
    s = build(cards, mine=["Lorcan, Warlock Collector", "Murder"], theirs=[creature])
    put(s, "Lorcan, Warlock Collector")
    victim = put(s, creature, "p2")
    to_hand(s, "Murder")
    mana(s, B=3)
    act(s, "p1", type="set_life", player="p1", value=life_total)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[victim.id])
    return s


def test_lorcan_pays_life_equal_to_the_mana_value_and_takes_the_creature_as_a_warlock(cards):
    s = lorcan(cards)
    d = asked(s)
    assert d is not None and [o.id for o in d.options] == ["pay", "decline"]
    answer(s, "pay")
    settle(s)
    assert life(s) == 40 - 6  # Twisted Abomination, mana value 6 (119.4)
    assert zone(s, "Twisted Abomination", "p2") == "p1:battlefield"
    assert "Warlock" in subtypes(s, "Twisted Abomination", "p2")
    check(s)


def test_lorcan_declines_and_nothing_happens(cards):
    s = lorcan(cards)
    answer(s, "decline")
    settle(s)
    assert life(s) == 40 and zone(s, "Twisted Abomination", "p2") == "p2:graveyard"
    check(s)


def test_lorcan_cannot_pay_more_life_than_it_has(cards):
    """118.3 / 119.4: with 5 life the 6 life can't be paid, so it isn't offered and "If you do" is false."""
    s = lorcan(cards, life_total=5)
    assert asked(s) is None
    assert life(s) == 5 and zone(s, "Twisted Abomination", "p2") == "p2:graveyard"
    check(s)


# -- Rulik Mons, Warren Chief: "If it's a land card, you may put it onto the battlefield tapped. If you didn't put a card onto the battlefield this way, ..." ---
def rulik(cards, top):
    s = build(cards, mine=["Rulik Mons, Warren Chief", top], forests=20)
    put(s, "Rulik Mons, Warren Chief")
    ready(s, "Rulik Mons, Warren Chief")
    act(s, "p1", type="move", card_ids=[card_named(s, top).id], to={"zone": "library"})  # on top of the library
    attack(s, card_named(s, "Rulik Mons, Warren Chief"))
    return s


def goblins(s):
    return [c for c in s.state.cards.values() if c.name == "Goblin" and c.zone == "p1:battlefield" and c.is_token]


def decline_pick(s):
    d = asked(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[])


def test_rulik_mons_puts_the_land_onto_the_battlefield_tapped_and_makes_no_goblin(cards):
    s = rulik(cards, "Forest")
    d = asked(s)
    top = [o.id for o in d.options]
    assert len(top) == 1
    act(s, d.player, type="choose", decision_id=d.id, option_ids=top)
    settle(s)
    assert s.state.cards[top[0]].zone == "p1:battlefield" and s.state.cards[top[0]].tapped
    assert not goblins(s)
    check(s)


def test_rulik_mons_declining_the_land_makes_a_goblin(cards):
    """608.2c: "If you didn't put a card onto the battlefield this way" is what the optional pick before it did (it put none)."""
    s = rulik(cards, "Forest")
    decline_pick(s)
    settle(s)
    assert len(goblins(s)) == 1
    assert not any(c.zone == "p1:battlefield" and c.name == "Forest" and c.tapped for c in s.state.cards.values())
    check(s)


def gyrus(cards, dead=("Grizzly Bears",), x=3):
    """Gyrus enters with a +1/+1 counter for each mana spent ({X}{B}{R}{G}: X + 3), then attacks; ``dead`` are in Alice's graveyard."""
    s = build(cards, mine=["Gyrus, Waker of Corpses", *dead], forests=20)
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack and in each step)
    for name in dead:
        to_gy(s, name)
    to_hand(s, "Gyrus, Waker of Corpses")
    mana(s, B=1, R=1, G=1 + x)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Gyrus, Waker of Corpses").id, x_value=x)
    settle(s)
    ready(s, "Gyrus, Waker of Corpses")
    attack(s, card_named(s, "Gyrus, Waker of Corpses"))
    return s


def attacking_copies(s, name):
    return [c for c in s.state.cards.values() if c.name == name and c.is_token and c.zone == "p1:battlefield"]


def test_gyrus_exiles_a_creature_card_with_lesser_power_and_a_copy_attacks_until_end_of_combat(cards):
    s = gyrus(cards)
    assert pt(s, "Gyrus, Waker of Corpses") == (6, 6)
    d = asked(s)
    assert [o.label for o in d.options] == ["Grizzly Bears"]  # (a target with power less than Gyrus's)
    pick(s, "Grizzly Bears")
    asked(s)
    pick(s, "Yes")
    assert s.state.turn.phase != "main2" and zone(s, "Grizzly Bears") == "p1:exile"
    (copy,) = attacking_copies(s, "Grizzly Bears")  # (a token copy that's tapped and attacking: 508.4)
    assert copy.tapped
    check(s)
    until(s, lambda s: s.state.turn.phase == "main2", limit=60)
    assert not attacking_copies(s, "Grizzly Bears")  # exiled at end of combat (a token ceases to exist)
    assert zone(s, "Grizzly Bears") == "p1:exile"
    check(s)


def test_gyrus_declining_leaves_the_card_in_the_graveyard_and_makes_no_copy(cards):
    s = gyrus(cards)
    pick(s, "Grizzly Bears")
    asked(s)
    pick(s, "No")
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:graveyard" and not attacking_copies(s, "Grizzly Bears")
    check(s)


def test_gyrus_with_no_card_of_lesser_power_has_nothing_to_exile(cards):
    """Gyrus is 3/3 (X = 0): the 5/3 in the graveyard isn't a legal target, so the ability has no target and never goes on the stack (113.8)."""
    s = gyrus(cards, dead=("Twisted Abomination",), x=0)
    assert pt(s, "Gyrus, Waker of Corpses") == (3, 3)
    assert asked(s) is None
    assert zone(s, "Twisted Abomination") == "p1:graveyard"
    check(s)


# -- Bob, Reluctant HYDRA Agent: "return him to his owner's hand. If you do, each opponent loses 2 life and you gain 2 life." ----------------------------------
def bob_table(cards, others=()):
    s = build(cards, mine=["Bob, Reluctant HYDRA Agent", *others], theirs=["Murder"])
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    for name in ("Bob, Reluctant HYDRA Agent", *others):
        put(s, name)
        ready(s, name)
    return s


def test_bob_returns_himself_when_he_attacks_alone_and_the_drain_follows(cards):
    s = bob_table(cards)
    attack(s, card_named(s, "Bob, Reluctant HYDRA Agent"))
    settle(s)
    assert zone(s, "Bob, Reluctant HYDRA Agent") == "p1:hand"
    assert (life(s), life(s, "p2")) == (42, 38)
    check(s)


def test_bob_does_nothing_when_he_attacks_with_another_creature(cards):
    s = bob_table(cards, others=("Grizzly Bears",))
    attack(s, card_named(s, "Bob, Reluctant HYDRA Agent"), card_named(s, "Grizzly Bears"))
    settle(s)
    assert zone(s, "Bob, Reluctant HYDRA Agent") == "p1:battlefield" and (life(s), life(s, "p2")) == (40, 40)
    check(s)


def test_bob_cannot_return_himself_after_he_died_in_response_so_the_drain_does_not_happen(cards):
    """118.12: "If you do" is false when the instruction can't be done — Bob is no longer on the battlefield (400.7), nothing is returned."""
    s = bob_table(cards)
    attack(s, card_named(s, "Bob, Reluctant HYDRA Agent"))
    murder = to_hand(s, "Murder", "p2")
    mana(s, "p2", B=3)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=murder.id, targets=[card_named(s, "Bob, Reluctant HYDRA Agent").id])
    settle(s)
    assert zone(s, "Bob, Reluctant HYDRA Agent") == "p1:graveyard"
    assert (life(s), life(s, "p2")) == (40, 40)
    check(s)


# -- Moku, Meandering Drummer: "you may pay {1}. If you do, Moku gets +2/+1 and creatures you control gain haste until end of turn." --------------------------
def keywords(s, name, pid="p1"):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(card_named(s, name, pid)).keywords


def moku(cards, spare):
    s = build(cards, mine=["Moku, Meandering Drummer", "Grizzly Bears", "Giant Growth"])
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    put(s, "Moku, Meandering Drummer")
    put(s, "Grizzly Bears")
    to_hand(s, "Giant Growth")
    mana(s, G=1 + spare)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Giant Growth").id, targets=[card_named(s, "Grizzly Bears").id])
    return s


def test_moku_pays_one_and_he_and_the_team_get_the_boost(cards):
    s = moku(cards, spare=1)
    d = asked(s)
    assert [o.id for o in d.options] == ["pay", "decline"]
    answer(s, "pay")
    assert pt(s, "Moku, Meandering Drummer") == (4, 3)  # +2/+1 until end of turn (the Giant Growth is on Grizzly Bears)
    assert "haste" in keywords(s, "Moku, Meandering Drummer") and "haste" in keywords(s, "Grizzly Bears")
    check(s)


def test_moku_declining_changes_nothing(cards):
    s = moku(cards, spare=1)
    answer(s, "decline")
    assert pt(s, "Moku, Meandering Drummer") == (2, 2)
    assert "haste" not in keywords(s, "Moku, Meandering Drummer") and "haste" not in keywords(s, "Grizzly Bears")
    check(s)


def test_moku_cannot_pay_with_no_mana_left_so_nothing_is_asked(cards):
    """118.3: the Giant Growth took all the mana, so the {1} can't be paid: it isn't offered and "If you do" is false."""
    s = moku(cards, spare=0)
    d = asked(s)
    assert d is None or d.kind != "choose_one"
    settle(s)
    assert pt(s, "Moku, Meandering Drummer") == (2, 2) and "haste" not in keywords(s, "Grizzly Bears")
    check(s)


# -- Taborax, Hope's Demise: "put a +1/+1 counter on Taborax. If that creature was a Cleric, you may draw a card. If you do, you lose 1 life." -------------------
def taborax(cards, victim):
    s = build(cards, mine=["Taborax, Hope's Demise", victim, "Murder"])
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    put(s, victim)
    put(s, "Taborax, Hope's Demise")
    to_hand(s, "Murder")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[card_named(s, victim).id])
    return s


def test_taborax_draws_when_a_cleric_died_and_loses_one_life(cards):
    s = taborax(cards, "Soul Warden")
    before, cards_before = life(s), len(s.state.zones["p1:hand"])
    d = asked(s)
    assert [o.id for o in d.options] == ["yes", "no"]
    answer(s, "yes")
    assert pt(s, "Taborax, Hope's Demise") == (3, 3)
    assert len(s.state.zones["p1:hand"]) == cards_before + 1 and life(s) == before - 1
    check(s)


def test_taborax_declining_the_draw_loses_no_life(cards):
    s = taborax(cards, "Soul Warden")
    before, cards_before = life(s), len(s.state.zones["p1:hand"])
    answer(s, "no")
    assert pt(s, "Taborax, Hope's Demise") == (3, 3)
    assert len(s.state.zones["p1:hand"]) == cards_before and life(s) == before
    check(s)


def test_taborax_asks_nothing_when_the_creature_was_not_a_cleric(cards):
    s = taborax(cards, "Grizzly Bears")
    before, cards_before = life(s), len(s.state.zones["p1:hand"])
    assert asked(s) is None
    assert pt(s, "Taborax, Hope's Demise") == (3, 3) and len(s.state.zones["p1:hand"]) == cards_before and life(s) == before
    check(s)


# -- Strefan, Maurer Progenitor: "you may sacrifice two Blood tokens. If you do, you may put a Vampire card from your hand onto the battlefield tapped and attacking." ----
def blood(s, n):
    for _ in range(n):
        token_of(s, "p1", "Blood", "Token Artifact — Blood", pt="0/0", text="{1}, {T}, Discard a card, Sacrifice this artifact: Draw a card.")


def strefan(cards, tokens=2):
    s = build(cards, mine=["Strefan, Maurer Progenitor", "Vampire Nighthawk"])
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    put(s, "Strefan, Maurer Progenitor")
    ready(s, "Strefan, Maurer Progenitor")
    to_hand(s, "Vampire Nighthawk")
    blood(s, tokens)
    attack(s, card_named(s, "Strefan, Maurer Progenitor"))
    return s


def bloods(s):
    return [c for c in s.state.cards.values() if c.name == "Blood" and c.zone == "p1:battlefield"]


def test_strefan_sacrifices_two_blood_tokens_and_puts_a_vampire_in_attacking_with_indestructible(cards):
    s = strefan(cards)
    d = asked(s)
    assert [o.id for o in d.options] == ["pay", "decline"]
    answer(s, "pay")
    assert not bloods(s)
    d = asked(s)  # the hand is hidden: a "you may" is asked whenever the hand holds cards
    assert [o.label for o in d.options] == ["Vampire Nighthawk"]
    pick(s, "Vampire Nighthawk")
    assert zone(s, "Vampire Nighthawk") == "p1:battlefield"
    assert "indestructible" in keywords(s, "Vampire Nighthawk")
    check(s)


def test_strefan_pays_but_puts_no_vampire_and_the_blood_is_still_gone(cards):
    """118.12: the sacrifice was paid — "If you do" is true — and the second "you may" is its own choice (none)."""
    s = strefan(cards)
    answer(s, "pay")
    decline_pick(s)
    settle(s)
    assert not bloods(s) and zone(s, "Vampire Nighthawk") == "p1:hand"
    check(s)


def test_strefan_declining_the_sacrifice_keeps_the_blood_and_asks_nothing_more(cards):
    s = strefan(cards)
    answer(s, "decline")
    assert asked(s) is None
    assert len(bloods(s)) == 2 and zone(s, "Vampire Nighthawk") == "p1:hand"
    check(s)


def test_strefan_cannot_sacrifice_two_blood_tokens_with_only_one(cards):
    """118.3: one Blood token can't pay for two, so the sacrifice is not offered and "If you do" is false."""
    s = strefan(cards, tokens=1)
    assert asked(s) is None
    assert len(bloods(s)) == 1 and zone(s, "Vampire Nighthawk") == "p1:hand"
    check(s)


# -- Bebop, Skull & Crossbones: "you may draw X cards, where X is the number of counters on Bebop. If you do, you lose X life." ---------------------------------
def bebop(cards, counters):
    s = build(cards, mine=["Bebop, Skull & Crossbones"], theirs=["Grizzly Bears"])
    put(s, "Bebop, Skull & Crossbones")
    ready(s, "Bebop, Skull & Crossbones")
    act(s, "p1", type="counter", card_ids=[card_named(s, "Bebop, Skull & Crossbones").id], kind="+1/+1", delta=counters)
    attack(s, card_named(s, "Bebop, Skull & Crossbones"))
    for _ in range(40):  # no blockers: on to the combat damage and its trigger
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            return s
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no trigger")


def test_bebop_draws_x_cards_and_loses_x_life(cards):
    s = bebop(cards, 2)
    hand = len(s.state.zones["p1:hand"])
    answer(s, "yes")
    assert len(s.state.zones["p1:hand"]) == hand + 2 and life(s) == 38
    check(s)


def test_bebop_declining_draws_nothing_and_loses_no_life(cards):
    s = bebop(cards, 2)
    hand = len(s.state.zones["p1:hand"])
    answer(s, "no")
    assert len(s.state.zones["p1:hand"]) == hand and life(s) == 40
    check(s)


# -- Amber Gristle O'Maul / Apothecary White: "for each player being attacked" (506.2, 506.6: a player attacked, not a planeswalker they control) -------------------
def three(cards, mine, bob=()):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (20, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (20, "Island")]), deck(cards, "Atraxa, Praetors' Voice", [(20, "Swamp")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)], shuffle=False)), cards=cards)
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="set_prefs", response="on")
    until(s, lambda s: s.state.turn.phase == "main1" and s.state.rules.decision is None)
    return s


def attack_two(s, first, second):
    """``first`` attacks Bob (p2) and ``second`` attacks Carol (p3)."""
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, first).id, "target": "p2"},
                                                      {"card_id": card_named(s, second).id, "target": "p3"}])


def test_amber_gristle_draws_a_card_for_each_player_being_attacked(cards):
    s = three(cards, ["Amber Gristle O'Maul", "Grizzly Bears"])
    for n in ("Amber Gristle O'Maul", "Grizzly Bears"):
        put(s, n)
        ready(s, n)
    attack_two(s, "Amber Gristle O'Maul", "Grizzly Bears")
    d = asked(s)
    assert [o.id for o in d.options] == ["pay", "decline"]
    answer(s, "pay")
    assert len(s.state.zones["p1:hand"]) == 2  # the hand was discarded, then one card for Bob and one for Carol
    check(s)


def test_amber_gristle_declining_keeps_the_hand(cards):
    s = three(cards, ["Amber Gristle O'Maul", "Grizzly Bears"])
    for n in ("Amber Gristle O'Maul", "Grizzly Bears"):
        put(s, n)
        ready(s, n)
    hand = len(s.state.zones["p1:hand"])
    attack_two(s, "Amber Gristle O'Maul", "Grizzly Bears")
    answer(s, "decline")
    assert len(s.state.zones["p1:hand"]) == hand
    check(s)


def test_amber_gristle_attacking_one_player_draws_one_card(cards):
    s = three(cards, ["Amber Gristle O'Maul", "Grizzly Bears"])
    for n in ("Amber Gristle O'Maul", "Grizzly Bears"):
        put(s, n)
        ready(s, n)
    attack(s, card_named(s, "Amber Gristle O'Maul"), card_named(s, "Grizzly Bears"))  # (both attack Bob)
    answer(s, "pay")
    assert len(s.state.zones["p1:hand"]) == 1
    check(s)


def test_apothecary_white_makes_a_food_for_each_player_being_attacked(cards):
    s = three(cards, ["Apothecary White", "Grizzly Bears"])
    for n in ("Apothecary White", "Grizzly Bears"):
        put(s, n)
        ready(s, n)
    attack_two(s, "Apothecary White", "Grizzly Bears")
    settle(s)
    assert len([c for c in s.state.cards.values() if c.name == "Food" and c.zone == "p1:battlefield"]) == 2
    check(s)


def test_pack_attack_gives_each_attacker_plus_x_for_the_players_being_attacked(cards):
    s = three(cards, ["Grizzly Bears", "Llanowar Elves", "Pack Attack"])
    for n in ("Grizzly Bears", "Llanowar Elves"):
        put(s, n)
        ready(s, n)
    to_hand(s, "Pack Attack")
    attack_two(s, "Grizzly Bears", "Llanowar Elves")
    mana(s, R=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Pack Attack").id)
    settle(s)
    assert pt(s, "Grizzly Bears") == (4, 2) and pt(s, "Llanowar Elves")[0] == 3  # X = 2: Bob and Carol
    check(s)


def test_apothecary_white_attacking_only_a_planeswalker_attacks_no_player(cards):
    """506.2, 506.6; Commander Liara Portyr's ruling of 2022-06-10: Bob's planeswalker is attacked, Bob is not — no player is being attacked, so no Food."""
    s = three(cards, ["Apothecary White"], bob=["Chandra, Torch of Defiance"])
    walker = put(s, "Chandra, Torch of Defiance", "p2")
    act(s, "p2", type="counter", card_ids=[walker.id], kind="loyalty", delta=4)
    put(s, "Apothecary White")
    ready(s, "Apothecary White")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, "Apothecary White").id, "target": walker.id}])
    settle(s)
    assert not [c for c in s.state.cards.values() if c.name == "Food" and c.zone == "p1:battlefield"]
    check(s)


# -- Kellan, the Kid: "you may cast a permanent spell with equal or lesser mana value from your hand without paying its mana cost. If you don't, you may put a land card ..." --
def kellan(cards, hand):
    s = build(cards, mine=["Kellan, the Kid", *hand])
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    put(s, "Kellan, the Kid")
    for c in list(s.state.zones["p1:hand"]):
        act(s, "p1", type="move", card_ids=[c], to={"zone": "library"})  # (the hand is exactly what the scenario needs)
    for name in hand:
        to_hand(s, name)
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss").id)  # from the command zone (Krenko, mana value 4)
    return s


def test_kellan_casts_a_permanent_spell_of_equal_or_lesser_value_for_free_and_no_land_follows(cards):
    s = kellan(cards, ["Grizzly Bears", "Twisted Abomination", "Forest"])
    d = asked(s)
    assert sorted(o.label for o in d.options) == ["Grizzly Bears"]  # (mana value 2 ≤ 4; the 6 is too much; a land isn't cast)
    pick(s, "Grizzly Bears")
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:battlefield" and zone(s, "Forest") == "p1:hand"
    check(s)


def test_kellan_casting_nothing_lets_him_put_a_land_onto_the_battlefield(cards):
    s = kellan(cards, ["Grizzly Bears", "Forest"])
    decline_pick(s)  # no spell cast: "If you don't"
    d = asked(s)
    assert sorted(o.label for o in d.options) == ["Forest"]
    pick(s, "Forest")
    settle(s)
    assert zone(s, "Forest") == "p1:battlefield" and zone(s, "Grizzly Bears") == "p1:hand"
    check(s)


def test_kellan_with_nothing_cheap_enough_to_cast_still_gets_the_land(cards):
    s = kellan(cards, ["Twisted Abomination", "Forest"])
    assert asked(s) is not None  # (asked whenever the hand holds cards: it must not tell what the hand is)
    decline_pick(s)
    pick(s, "Forest")
    settle(s)
    assert zone(s, "Forest") == "p1:battlefield" and zone(s, "Twisted Abomination") == "p1:hand"
    check(s)


# -- Baral and Kari Zev: "you may cast a spell with lesser mana value that shares a card type with it from your hand without paying its mana cost. If you don't, create ..." --
def baral(cards, hand):
    s = build(cards, mine=["Baral and Kari Zev", "Murder", *hand], theirs=["Grizzly Bears"])
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    put(s, "Baral and Kari Zev")
    victim = put(s, "Grizzly Bears", "p2")
    for c in list(s.state.zones["p1:hand"]):
        act(s, "p1", type="move", card_ids=[c], to={"zone": "library"})
    to_hand(s, "Murder")
    for name in hand:
        to_hand(s, name)
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[victim.id])  # Alice's first instant or sorcery spell this turn (mana value 3)
    return s


def monkeys(s):
    return [c for c in s.state.cards.values() if c.name == "First Mate Ragavan" and c.zone == "p1:battlefield"]


def test_baral_casts_a_cheaper_spell_sharing_a_type_for_free_and_no_monkey_follows(cards):
    s = baral(cards, ["Giant Growth", "Grizzly Bears"])
    d = asked(s)
    assert sorted(o.label for o in d.options) == ["Giant Growth"]  # (mana value 1 < 3 and an instant; the creature shares no type)
    pick(s, "Giant Growth")
    d = asked(s)  # its target
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
    settle(s)
    assert zone(s, "Giant Growth") == "p1:graveyard" and not monkeys(s)
    check(s)


def test_baral_casting_nothing_creates_the_monkey_pirate_with_haste(cards):
    s = baral(cards, ["Giant Growth", "Grizzly Bears"])
    decline_pick(s)
    settle(s)
    (monkey,) = monkeys(s)
    assert "haste" in keywords(s, "First Mate Ragavan") and pt(s, "First Mate Ragavan") == (2, 1) and monkey.is_token
    check(s)


def test_baral_with_nothing_cheaper_to_cast_makes_the_monkey(cards):
    """Another Murder isn't cheaper (3 is not less than 3): nothing can be cast, so the answer is no and the token follows."""
    s = baral(cards, ["Twisted Abomination"])
    if asked(s) is not None:
        decline_pick(s)
    settle(s)
    assert len(monkeys(s)) == 1
    check(s)


# -- Take Out the Trash / Chandra's Defeat: "If [condition], you may discard a card. If you do, draw a card." ---------------------------------------------------
def trash(cards, raccoon, hand_cards=1):
    s = build(cards, mine=["Take Out the Trash", "Grizzly Bears", "Llanowar Elves"], theirs=["Grizzly Bears"])
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    victim = put(s, "Grizzly Bears", "p2")
    if raccoon:
        token_of(s, "p1", "Raccoon", "Token Creature — Raccoon", pt="1/1")
    for c in list(s.state.zones["p1:hand"]):
        act(s, "p1", type="move", card_ids=[c], to={"zone": "library"})  # (an empty hand, then exactly what the scenario needs)
    to_hand(s, "Take Out the Trash")
    if hand_cards:
        to_hand(s, "Llanowar Elves")
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Take Out the Trash").id, targets=[victim.id])
    return s


def test_take_out_the_trash_with_a_raccoon_discards_and_draws(cards):
    s = trash(cards, raccoon=True)
    d = asked(s)
    assert [o.id for o in d.options] == ["pay", "decline"]
    answer(s, "pay")
    assert zone(s, "Llanowar Elves") == "p1:graveyard" and len(s.state.zones["p1:hand"]) == 1
    assert zone(s, "Grizzly Bears", "p2") == "p2:graveyard"  # the 3 damage was dealt first
    check(s)


def test_take_out_the_trash_declined_keeps_the_hand(cards):
    s = trash(cards, raccoon=True)
    answer(s, "decline")
    assert zone(s, "Llanowar Elves") == "p1:hand" and len(s.state.zones["p1:hand"]) == 1
    check(s)


def test_take_out_the_trash_without_a_raccoon_asks_nothing(cards):
    s = trash(cards, raccoon=False)
    assert asked(s) is None and zone(s, "Llanowar Elves") == "p1:hand"
    check(s)


def test_take_out_the_trash_with_no_card_to_discard_cannot_pay(cards):
    """118.3: an empty hand can't discard a card, so it isn't offered (and nothing is drawn)."""
    s = trash(cards, raccoon=True, hand_cards=0)
    assert asked(s) is None
    assert len(s.state.zones["p1:hand"]) == 0
    check(s)


def defeat(cards, victim):
    s = build(cards, mine=["Chandra's Defeat", "Llanowar Elves"], theirs=[victim])
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    target = put(s, victim, "p2")
    if victim.startswith("Chandra"):
        act(s, "p2", type="counter", card_ids=[target.id], kind="loyalty", delta=4)
    for c in list(s.state.zones["p1:hand"]):
        act(s, "p1", type="move", card_ids=[c], to={"zone": "library"})
    to_hand(s, "Chandra's Defeat")
    to_hand(s, "Llanowar Elves")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Chandra's Defeat").id, targets=[target.id])
    return s


def test_chandras_defeat_on_a_chandra_planeswalker_may_discard_to_draw(cards):
    s = defeat(cards, "Chandra, Torch of Defiance")
    answer(s, "pay")
    assert zone(s, "Llanowar Elves") == "p1:graveyard" and len(s.state.zones["p1:hand"]) == 1
    assert zone(s, "Chandra, Torch of Defiance", "p2") == "p2:graveyard"
    check(s)


def test_chandras_defeat_on_a_chandra_planeswalker_declined(cards):
    s = defeat(cards, "Chandra, Torch of Defiance")
    answer(s, "decline")
    assert zone(s, "Llanowar Elves") == "p1:hand"
    check(s)


def test_chandras_defeat_on_a_red_creature_asks_nothing(cards):
    s = defeat(cards, "Young Pyromancer")
    assert asked(s) is None and zone(s, "Llanowar Elves") == "p1:hand" and zone(s, "Young Pyromancer", "p2") == "p2:graveyard"
    check(s)


def ferocious(cards, big):
    s = build(cards, mine=["Force Away", "Twisted Abomination", "Grizzly Bears", "Llanowar Elves"], theirs=["Grizzly Bears"])
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    put(s, "Twisted Abomination" if big else "Grizzly Bears")
    target = put(s, "Grizzly Bears", "p2")
    for c in list(s.state.zones["p1:hand"]):
        act(s, "p1", type="move", card_ids=[c], to={"zone": "library"})
    to_hand(s, "Force Away")
    to_hand(s, "Llanowar Elves")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Force Away").id, targets=[target.id])
    return s


def test_force_away_with_a_power_four_creature_may_draw_and_then_discard(cards):
    """Ferocious: "If you control a creature with power 4 or greater, you may draw a card. If you do, discard a card." — checked after the bounce (608.2c)."""
    s = ferocious(cards, big=True)
    d = asked(s)
    assert [o.id for o in d.options] == ["yes", "no"]
    answer(s, "yes")
    asked(s)  # which card to discard
    pick(s, "Llanowar Elves")
    assert zone(s, "Grizzly Bears", "p2") == "p2:hand" and zone(s, "Llanowar Elves") == "p1:graveyard"
    check(s)


def test_force_away_declining_the_draw_discards_nothing(cards):
    s = ferocious(cards, big=True)
    hand = len(s.state.zones["p1:hand"])
    answer(s, "no")
    assert len(s.state.zones["p1:hand"]) == hand and zone(s, "Llanowar Elves") == "p1:hand"
    check(s)


def test_force_away_without_a_power_four_creature_asks_nothing(cards):
    s = ferocious(cards, big=False)
    assert asked(s) is None and zone(s, "Llanowar Elves") == "p1:hand"
    check(s)


def venom(cards, victim):
    s = build(cards, mine=["Venom, Eddie Brock", "Murder"], theirs=[victim])
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    put(s, "Venom, Eddie Brock")
    target = put(s, victim, "p2")
    to_hand(s, "Murder")
    mana(s, B=3)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[target.id])
    settle(s)
    return s, hand - 1  # (the Murder left the hand)


def test_venom_draws_only_when_the_creature_that_died_was_a_villain(cards):
    """"If that creature was a Villain" is the creature that died, not Venom (who is a Villain himself): 608.2h, as it last existed."""
    s, hand = venom(cards, "Bob, Reluctant HYDRA Agent")
    assert pt(s, "Venom, Eddie Brock") == (7, 5) and len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_venom_does_not_draw_when_the_creature_that_died_was_no_villain(cards):
    s, hand = venom(cards, "Grizzly Bears")
    assert pt(s, "Venom, Eddie Brock") == (7, 5) and len(s.state.zones["p1:hand"]) == hand
    check(s)


def test_rulik_mons_a_nonland_top_card_makes_a_goblin_too(cards):
    s = rulik(cards, "Grizzly Bears")
    d = asked(s)
    if d is not None:  # (the question is asked whether or not a card qualifies, so it tells nothing about the library)
        assert not d.options
        decline_pick(s)
    settle(s)
    assert len(goblins(s)) == 1 and zone(s, "Grizzly Bears") == "p1:library"
    check(s)
