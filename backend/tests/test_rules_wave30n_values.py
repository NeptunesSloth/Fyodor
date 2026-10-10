"""Wave 30N: value grammar - counts that name a player, the sum of two stats, "the difference" (CR 2026-09-25), real Oracle text
(tests/fixtures/wave30n_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 608.2h: an amount is determined once, as the effect is carried out - "the number of creatures they control" is read when Villainous
  Wrath resolves (not when it was cast), "its power plus its toughness" as the creature last existed, the cards in hand after the draw.
* 603.2c / 603.7: "that player" / "they" in a trigger's amount is the player the event was about (the damaged player), not the controller
  and not another opponent: three players play the scenarios that tell the two apart.
* 115.1 / 608.2b: "target opponent ... they control" is that target's count.
* 708.2: a face-down permanent is a 2/2 creature with no name, so it counts as a creature and a 2/2 body.
* 108.3: "cards your opponents own in exile" counts the cards owned by opponents, wherever they came from, face up or down.
* Kept manual (pinned below): an amount read per recipient of "each player" for anything but damage / life loss, a difference against
  another player's hand ("Sandstone Oracle"), a count of what "defending player" has.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import settle, until
from tests.test_rules_wave5j_token_copies import ok
from tests.wave9c_kit import card_named, check, life, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30n_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t30n", number=f"N{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def three(cards, alice=(), bob=(), carol=()):
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in alice), (20, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (20, "Island")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in carol), (20, "Island")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # -> Alice's main phase
    return s


def zone_move(s, name, pid, zone, **extra):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": zone}, **extra)
    return s.state.cards[c.id]


def cast(s, name, targets=(), pid="p1"):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **({"targets": list(targets)} if targets else {}))


def unready(s, *cs):
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0


def attack(s, attacker, target):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": attacker.id, "target": target}])
    until(s, lambda s: life(s, target) < 40 or s.state.rules.priority is None, limit=80)
    settle(s)


# -- a count of what the target opponent controls ("they control") ----------------------------------------------------------------------

def pass_to(s, pid):
    """Pass priority (for whoever holds it) until ``pid`` holds it, with the spell still on the stack."""
    for _ in range(6):
        if s.state.rules.priority == pid:
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"{pid} never got priority")


def wrath_table(cards, carol_extra=()):
    s = three(cards, alice=("Villainous Wrath", "Grizzly Bears"), bob=("Llanowar Elves", "Merfolk Looter"),
              carol=("Monastery Swiftspear", "Grizzly Bears", "Llanowar Elves", "Merfolk Looter", *carol_extra))
    put(s, "Grizzly Bears")
    for n in ("Llanowar Elves", "Merfolk Looter"):
        put(s, n, "p2")
    for n in ("Monastery Swiftspear", "Grizzly Bears", "Llanowar Elves", "Merfolk Looter"):
        put(s, n, "p3")
    to_hand(s, "Villainous Wrath")
    mana(s, B=5)
    return s


@pytest.mark.parametrize(("target", "lost"), [("p2", 2), ("p3", 4)])
def test_villainous_wrath_counts_the_target_opponents_creatures(cards, target, lost):
    s = wrath_table(cards)
    cast(s, "Villainous Wrath", [target])
    settle(s)
    assert {p: life(s, p) for p in ("p1", "p2", "p3")} == {p: 40 - (lost if p == target else 0) for p in ("p1", "p2", "p3")}
    assert not [c for c in s.state.cards.values() if c.zone.endswith(":battlefield") and c.name in ("Grizzly Bears", "Llanowar Elves", "Merfolk Looter")]
    check(s)  # ("Then destroy all creatures": the count was read before they died)


def test_villainous_wrath_reads_the_count_as_it_resolves(cards):
    s = wrath_table(cards, carol_extra=("Murder",))
    to_hand(s, "Murder", "p3")
    mana(s, "p3", B=3)
    cast(s, "Villainous Wrath", ["p2"])
    pass_to(s, "p3")  # Carol answers with Wrath on the stack: one of Bob's two creatures dies before it resolves (608.2h)
    act(s, "p3", type="cast_spell", card_id=card_named(s, "Murder", "p3").id, targets=[card_named(s, "Merfolk Looter", "p2").id])
    settle(s)
    assert life(s, "p2") == 39
    check(s)


def test_villainous_wrath_counts_a_face_down_creature_and_nothing_for_none(cards):
    s = wrath_table(cards)
    zone_move(s, "Llanowar Elves", "p2", "graveyard")
    zone_move(s, "Merfolk Looter", "p2", "hand")
    zone_move(s, "Merfolk Looter", "p2", "battlefield", face_down=True, face_down_kind="morph")  # a face-down 2/2 creature is still a creature (708.2)
    cast(s, "Villainous Wrath", ["p2"])
    settle(s)
    assert life(s, "p2") == 39
    check(s)
    t = wrath_table(cards)  # X = 0: the target controls no creature
    for n in ("Llanowar Elves", "Merfolk Looter"):
        zone_move(t, n, "p2", "graveyard")
    cast(t, "Villainous Wrath", ["p2"])
    settle(t)
    assert life(t, "p2") == 40
    check(t)


# -- a count of what the player a trigger is about controls ("that player controls") -----------------------------------------------------

@pytest.mark.parametrize(("target", "gained"), [("p2", 3), ("p3", 2)])
def test_emissary_of_hope_counts_the_damaged_players_artifacts(cards, target, gained):
    s = three(cards, alice=("Emissary of Hope", "Sol Ring"), bob=("Sol Ring", "Arcane Signet", "Sol Grail"), carol=("Sol Ring", "Arcane Signet"))
    emissary = put(s, "Emissary of Hope")
    put(s, "Sol Ring")  # (Alice's own artifacts never count)
    for n in ("Sol Ring", "Arcane Signet", "Sol Grail"):
        put(s, n, "p2")
    for n in ("Sol Ring", "Arcane Signet"):
        put(s, n, "p3")
    unready(s, emissary)
    attack(s, emissary, target)
    assert life(s, target) == 38
    assert life(s, "p1") == 40 + gained
    check(s)


# -- a count of what the opponents own in exile -----------------------------------------------------------------------------------------

def test_umbris_counts_the_cards_the_opponents_own_in_exile(cards):
    s = three(cards, alice=("Umbris, Fear Manifest", "Grizzly Bears"), bob=("Llanowar Elves", "Merfolk Looter"), carol=("Monastery Swiftspear",))
    umbris = put(s, "Umbris, Fear Manifest")
    settle(s)  # (its own enter trigger exiles cards from the top of an opponent's library)
    base = len([c for c in s.state.cards.values() if c.zone.endswith(":exile") and c.owner != "p1"])
    zone_move(s, "Grizzly Bears", "p1", "exile")  # (Alice's own: not counted)
    zone_move(s, "Llanowar Elves", "p2", "exile")
    zone_move(s, "Merfolk Looter", "p2", "exile", face_down=True)  # (face down: still a card its owner owns)
    zone_move(s, "Monastery Swiftspear", "p3", "exile")
    assert pt(s, "Umbris, Fear Manifest") == (1 + base + 3, 1 + base + 3)
    zone_move(s, "Monastery Swiftspear", "p3", "graveyard")  # (the count is read continuously: 613)
    assert pt(s, "Umbris, Fear Manifest") == (1 + base + 2, 1 + base + 2)
    assert umbris.id in s.state.cards
    check(s)


# -- the sum of two stats ---------------------------------------------------------------------------------------------------------------

def test_phthisis_reads_power_plus_toughness_as_the_creature_last_existed(cards):
    s = three(cards, alice=("Phthisis",), bob=("Grizzly Bears",), carol=("Merfolk Looter",))
    bears = put(s, "Grizzly Bears", "p2")
    put(s, "Merfolk Looter", "p3")
    act(s, "p2", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)  # 3/3 when the spell resolves
    to_hand(s, "Phthisis")
    mana(s, B=7)
    cast(s, "Phthisis", [bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone.endswith(":graveyard")
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (40, 34, 40)  # its controller, not the caster, loses 3 + 3
    check(s)


def test_phthisis_on_a_face_down_creature_loses_four(cards):
    s = three(cards, alice=("Phthisis",), bob=("Merfolk Looter",))
    wolf = zone_move(s, "Merfolk Looter", "p2", "battlefield", face_down=True, face_down_kind="morph")  # a face-down 2/2 (708.2)
    to_hand(s, "Phthisis")
    mana(s, B=7)
    cast(s, "Phthisis", [wolf.id])
    settle(s)
    assert life(s, "p2") == 36
    check(s)


def test_predators_rapport_reads_the_creature_as_the_spell_resolves(cards):
    s = three(cards, alice=("Predator's Rapport", "Grizzly Bears"), bob=("Giant Growth",))
    bears = put(s, "Grizzly Bears")
    to_hand(s, "Predator's Rapport")
    to_hand(s, "Giant Growth", "p2")
    mana(s, G=3)
    mana(s, "p2", G=1)
    cast(s, "Predator's Rapport", [bears.id])
    pass_to(s, "p2")  # Bob pumps Alice's creature in response: 5/5 when the spell resolves (608.2h)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Giant Growth", "p2").id, targets=[bears.id])
    settle(s)
    assert life(s, "p1") == 50
    check(s)


# -- "the difference" against the number of cards it fell short of ----------------------------------------------------------------------

@pytest.mark.parametrize(("hand", "final"), [(0, 3), (1, 3), (2, 3), (3, 4), (6, 7)])
def test_iymrith_draws_up_to_three_cards(cards, hand, final):
    s = three(cards, alice=("Iymrith, Desert Doom",))
    iymrith = put(s, "Iymrith, Desert Doom")
    for c in [c for c in s.state.cards.values() if c.zone == "p1:hand"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    for c in [c for c in s.state.cards.values() if c.zone == "p1:library"][:hand]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    assert len(s.state.zones["p1:hand"]) == hand
    unready(s, iymrith)
    attack(s, iymrith, "p2")
    assert life(s, "p2") == 35
    assert len(s.state.zones["p1:hand"]) == final
    check(s)


# -- a count read for the target player / the player whose step it is -------------------------------------------------------------------

def answer(s, prefer=(), limit=40):
    """Resolve the stack; a decision is answered with the first option whose id or label has a ``prefer`` word in it, else the first."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            want = [o.id for o in d.options if any(w in o.id.lower() or w in (o.label or "").lower() for w in prefer)]
            ids = want or [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


@pytest.mark.parametrize(("bob", "drawn"), [(("Island", "Island", "Mountain"), 2), (("Breeding Pool",), 2), (("Mountain", "Forest", "Island"), 3), ((), 0)])
def test_allied_strategies_counts_the_basic_land_types_the_target_controls(cards, bob, drawn):
    s = three(cards, alice=("Allied Strategies", "Forest"), bob=tuple(dict.fromkeys(bob)), carol=("Island",))
    put(s, "Forest")  # (Alice's own land types are not Bob's)
    put(s, "Island", "p3")
    for name in bob:
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p2" and c.zone == "p2:library")
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    to_hand(s, "Allied Strategies")
    mana(s, U=5)
    before = len(s.state.zones["p2:hand"])
    cast(s, "Allied Strategies", ["p2"])
    settle(s)
    assert len(s.state.zones["p2:hand"]) == before + drawn  # (domain: types, not lands - and a Forest Island counts for both)
    check(s)


def test_collapsing_borders_reads_the_land_types_of_the_player_whose_upkeep_it_is(cards):
    s = three(cards, alice=("Collapsing Borders", "Forest"), bob=("Mountain", "Island"))
    put(s, "Collapsing Borders")
    put(s, "Forest")
    for n in ("Mountain", "Island"):
        zone_move(s, n, "p2", "battlefield")
    until(s, lambda s: life(s, "p2") != 40)
    settle(s)
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (40, 39, 40)  # Bob: +2 (two basic land types) then 3 damage
    check(s)


def test_whispering_specter_discards_one_card_for_each_poison_counter_they_have(cards):
    s = three(cards, alice=("Whispering Specter",), bob=("Sol Ring",))
    specter = put(s, "Whispering Specter")
    unready(s, specter)
    act(s, "p1", type="resource", player="p2", key="poison", delta=2)  # (two already: infect damage makes it three)
    for c in [c for c in s.state.cards.values() if c.zone == "p2:library"][:5]:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})
    hand = len(s.state.zones["p2:hand"])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": specter.id, "target": "p2"}])
    until(s, lambda s: s.state.players["p2"].resources["poison"] >= 3, limit=80)
    answer(s, prefer=("yes",))
    assert s.state.cards[specter.id].zone.endswith(":graveyard")  # (sacrificed)
    assert len(s.state.zones["p2:hand"]) == hand - 3
    check(s)


def test_molten_psyche_hurts_each_opponent_by_the_cards_that_player_drew(cards):
    s = three(cards, alice=("Molten Psyche", "Sol Ring", "Arcane Signet", "Sol Grail"))
    for n in ("Sol Ring", "Arcane Signet", "Sol Grail"):
        put(s, n)
    for pid, n in (("p2", 5), ("p3", 3)):  # (Bob holds five cards, Carol three: each draws as many again)
        for c in [c for c in s.state.cards.values() if c.zone == f"{pid}:library"][:n]:
            act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    bob_hand, carol_hand = len(s.state.zones["p2:hand"]), len(s.state.zones["p3:hand"])
    assert (bob_hand, carol_hand) == (5, 3)
    to_hand(s, "Molten Psyche")
    mana(s, R=3)
    cast(s, "Molten Psyche")
    settle(s)
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (40, 40 - bob_hand, 40 - carol_hand)  # each opponent's own draws, not one shared number
    check(s)


def test_mjolnir_hurts_each_opponent_by_their_own_tapped_creatures(cards):
    s = three(cards, alice=("Mjölnir, Storm Hammer", "Grizzly Bears"), bob=("Llanowar Elves", "Merfolk Looter"), carol=("Grizzly Bears", "Llanowar Elves"))
    krenko = put(s, "Krenko, Mob Boss")
    unready(s, krenko)
    for n, pid in (("Llanowar Elves", "p2"), ("Merfolk Looter", "p2"), ("Grizzly Bears", "p3"), ("Llanowar Elves", "p3")):
        put(s, n, pid)
    act(s, "p2", type="tap", card_ids=[card_named(s, "Merfolk Looter", "p2").id])
    act(s, "p3", type="tap", card_ids=[card_named(s, "Grizzly Bears", "p3").id])
    hammer = put(s, "Mjölnir, Storm Hammer")
    answer(s)  # (its enter trigger: attach it to Krenko, the one legendary creature)
    if s.state.cards[hammer.id].attached_to != krenko.id:
        act(s, "p1", type="attach", card_ids=[hammer.id], to=krenko.id)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": krenko.id, "target": "p2"}])
    elves = card_named(s, "Llanowar Elves", "p2")
    until(s, lambda s: life(s, "p2") < 40, limit=80)
    settle(s)
    assert s.state.cards[elves.id].tapped  # (the attack trigger's target: Bob then had two tapped creatures, Carol one)
    assert (life(s, "p3"), life(s, "p2")) == (39, 40 - 2 - 3)  # Mjölnir: 2 and 1; Krenko's combat damage to Bob: 3
    check(s)


@pytest.mark.parametrize(("sacrifice", "lost"), [(False, 2), (True, 0)])
def test_tomb_blade_costs_the_damaged_player_a_life_for_each_creature_they_control(cards, sacrifice, lost):
    s = three(cards, alice=("Tomb Blade",), bob=("Llanowar Elves", "Merfolk Looter"), carol=("Grizzly Bears",))
    blade = put(s, "Tomb Blade")
    unready(s, blade)
    for n in ("Llanowar Elves", "Merfolk Looter"):
        put(s, n, "p2")
    put(s, "Grizzly Bears", "p3")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": blade.id, "target": "p2"}])
    until(s, lambda s: life(s, "p2") < 40, limit=80)
    answer(s, prefer=("sacrifice",) if sacrifice else ("no", "decline"))
    assert life(s, "p2") == 40 - 5 - lost  # (5 combat damage; then the creatures they control, unless they sacrificed one)
    assert life(s, "p3") == 40
    check(s)


# -- what stays manual --------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("text", "type_line"), [
    ("Each player draws a card for each creature card in their graveyard.", "Sorcery"),  # an amount per recipient: damage and life loss only
    ("Each opponent mills cards equal to the number of cards in their hand.", "Sorcery"),
    ("When this creature enters, choose an opponent. If that player has more cards in hand than you, draw cards equal to the difference.",
     "Creature — Human"),  # the other player's hand: not read
    ("Whenever this creature attacks, defending player loses life equal to the number of artifacts they control.", "Creature — Human"),
    ("Whenever you attack a player, you gain 1 life for each creature that player controls.", "Creature — Human"),  # (the event's player is the attacker, not "that player")
])
def test_unread_wordings_stay_manual(text, type_line):
    assert not ok(text, type_line=type_line)
