"""Wave 38D: the companion keyword (CR 702.139, 116.2g, 103.2b), real Oracle text (tests/fixtures/wave38d_companion_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 702.139a / 103.2b: a card with "Companion — [condition]" may be your companion if your starting deck fulfills the condition; 702.139b: that
  deck is the one before sideboarding, in a Commander game also before the commander is set aside, so the commander counts (Scryfall ruling
  on Lurrus, 2020-04-17). The ten conditions are checked when a deck is validated and again when the special action is taken.
* 116.2g: a player who has chosen a companion may pay {3} to put it into their hand, any time they have priority and the stack is empty
  during a main phase of their turn, once per game. A special action: the card goes from the companion zone to the hand, no stack.
* A companion in the main deck or as the commander does nothing (ruling 2020-04-17): coverage counts the line as supported.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.decks import service as deck_service
from app.decks.models import DeckEntry, DeckIn
from app.game.errors import ActionError
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import PUBLIC_ZONES
from app.game.visibility import SPECTATOR, can_see
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import settle
from tests.test_rules_wave18g_rooms import to_end_step
from tests.wave9c_kit import card_named, check, mana, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave38d_companion_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w38d", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
LURRUS = "Lurrus of the Dream-Den"
ISAMARU = "Isamaru, Hound of Konda"
KRENKO = "Krenko, Mob Boss"
FOREST5 = (5, "Forest")
VALAKUT = "Valakut Awakening // Valakut Stoneforge"


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


# (companion, commander, a legal deck's other cards, the cards that break it)
CASES = {
    LURRUS: (ISAMARU, [(1, "Sol Ring"), (1, "Llanowar Elves"), (1, "Lightning Bolt"), (1, "Counterspell"), (1, "Fire // Ice"), FOREST5],
             [(1, "Solemn Simulacrum")]),
    "Zirda, the Dawnwaker": (KRENKO, [(1, "Sol Ring"), (1, "Llanowar Elves"), (1, "Lightning Bolt"), (1, "Wastes"), FOREST5], [(1, "Grizzly Bears")]),
    "Jegantha, the Wellspring": (ISAMARU, [(1, "Sol Ring"), (1, "Llanowar Elves"), (1, "Grizzly Bears"), (1, "Endless One"), FOREST5],
                                 [(1, "Counterspell")]),
    "Gyruda, Doom of Depths": (KRENKO, [(1, "Counterspell"), (1, "Solemn Simulacrum"), (1, "Fire // Ice"), (1, "Endless One"), FOREST5],
                               [(1, "Sol Ring")]),
    "Kaheera, the Orphanguard": (LURRUS, [(1, "Ravenous Chupacabra"), (1, "Changeling Outcast"), (1, "Sol Ring"), (1, "Lightning Bolt"), FOREST5],
                                 [(1, "Llanowar Elves")]),
    "Keruga, the Macrosage": (KRENKO, [(1, "Solemn Simulacrum"), (1, "Rhystic Study"), (1, "Dryad Arbor"), (1, VALAKUT), (1, "Fire // Ice"),
                                       FOREST5], [(1, "Sol Ring")]),
    "Obosh, the Preypiercer": (ISAMARU, [(1, "Sol Ring"), (1, "Rhystic Study"), (1, "Dryad Arbor"), (1, VALAKUT), FOREST5], [(1, "Counterspell")]),
    "Umori, the Collector": (ISAMARU, [(1, "Llanowar Elves"), (1, "Solemn Simulacrum"), (1, "Grizzly Bears"), (1, "Dryad Arbor"), FOREST5],
                             [(1, "Sol Ring")]),
    "Lutri, the Spellchaser": (ISAMARU, [(1, "Sol Ring"), (1, "Llanowar Elves"), (1, "Counterspell"), FOREST5], [(2, "Sol Ring")]),
}


def entries(cards, companion, commander, spells):
    def entry(section, qty, name):
        return DeckEntry(section=section, quantity=qty, name=name, printing_id=cards.resolve(name)["id"])

    return [entry("commander", 1, commander), *(entry("main", q, n) for q, n in spells), *([entry("companion", 1, companion)] if companion else [])]


def companion_warnings(cards, companion, commander, spells):
    found = deck_service.validate(DeckIn(name="t", format="commander", entries=entries(cards, companion, commander, spells)), cards)
    return [w for w in found if "companion" in w.message.lower()]


ALONE = {LURRUS, "Zirda, the Dawnwaker", "Kaheera, the Orphanguard", "Keruga, the Macrosage", "Lutri, the Spellchaser"}  # the companion line was all they lacked


@pytest.mark.parametrize("name", [*CASES, "Yorion, Sky Nomad"])
def test_the_companion_line_is_supported_for_all_ten(cards, name):
    """It works outside the game (checked with the deck, 116.2g at the table) and does nothing in the deck or as the commander: supported.
    Five of the ten had no other missing line and are FULL; the rest keep theirs (Jegantha's mana restriction, Gyruda's and Yorion's enters
    triggers, Umori's chosen type, Obosh's damage doubling) — those are other families."""
    result = coverage.of_card_data(cards.resolve(name))
    assert next(f for f in result.features if f.id == "keyword:companion").supported
    assert (result.level == "FULL") == (name in ALONE)


@pytest.mark.parametrize("name", CASES)
def test_a_deck_that_fulfills_the_condition_has_no_warning(cards, name):
    commander, ok, _ = CASES[name]
    assert companion_warnings(cards, name, commander, ok) == []


@pytest.mark.parametrize("name", CASES)
def test_a_deck_that_breaks_the_condition_is_reported_as_an_error(cards, name):
    commander, ok, bad = CASES[name]
    found = companion_warnings(cards, name, commander, [*ok, *bad])
    assert [(w.level, w.card) for w in found] == [("error", name)] and found[0].message.startswith(f"{name} can't be your companion:")


def test_the_commander_is_part_of_the_starting_deck(cards):
    """702.139b: "In a Commander game, this is also before you've set aside your commander" — Krenko costs {2}{R}{R}."""
    _, ok, _ = CASES[LURRUS]
    assert companion_warnings(cards, LURRUS, KRENKO, ok)
    assert companion_warnings(cards, "Zirda, the Dawnwaker", ISAMARU, CASES["Zirda, the Dawnwaker"][1])  # Isamaru has no activated ability


def test_yorion_can_never_be_a_commander_companion(cards):
    """903.5a: the minimum deck size is 100, so twenty more is 120; the deck has exactly 100 (ruling 2020-04-17). Even 120 cards don't help."""
    for spells in ([(1, "Sol Ring"), FOREST5], [(119, "Forest")]):
        found = companion_warnings(cards, "Yorion, Sky Nomad", KRENKO, spells)
        assert len(found) == 1 and "never the 120" in found[0].message


def test_split_mdfc_and_adventure_cards_use_their_characteristics_outside_the_game(cards):
    """709.4b: a split card's cost is both halves' (Fire // Ice repeats {1}); 712.8a: a double-faced card is its front face (Valakut Awakening
    costs {2}{R}, not a land); X is 0 off the stack (202.3e)."""
    jeg = "Jegantha, the Wellspring"
    assert companion_warnings(cards, jeg, ISAMARU, [(1, "Fire // Ice")])
    assert companion_warnings(cards, "Gyruda, Doom of Depths", KRENKO, [(1, VALAKUT)])  # mana value 3, odd
    assert not companion_warnings(cards, "Gyruda, Doom of Depths", KRENKO, [(1, "Endless One")])


def test_kaheera_counts_changelings_and_land_creatures(cards):
    k = "Kaheera, the Orphanguard"
    assert not companion_warnings(cards, k, LURRUS, [(1, "Changeling Outcast")])  # 702.73a: every creature type
    assert companion_warnings(cards, k, LURRUS, [(1, "Dryad Arbor")])  # a Land Creature is a creature card (Forest Dryad)


def test_zirda_reads_reminder_text_but_not_a_quoted_ability(cards):
    z = "Zirda, the Dawnwaker"
    assert not companion_warnings(cards, z, KRENKO, [(1, "Swiftfoot Boots")])  # Equip {1} ({1}: Attach …): the colon is in its reminder text
    assert not companion_warnings(cards, z, KRENKO, [(1, "Dryad Arbor")])  # 305.6: its Forest type is the ability (the quoted text is reminder)
    assert companion_warnings(cards, z, KRENKO, [(1, "Cryptolith Rite")])  # it gives creatures an ability; it has none
    assert companion_warnings(cards, z, KRENKO, [(1, "Rhystic Study")])
    assert companion_warnings(cards, z, KRENKO, [(1, "Rhet-Tomb Mystic")])  # "Each creature card in your hand has cycling": it gives it, whose reminder has the colon


def test_only_one_companion(cards):
    _, ok, _ = CASES[LURRUS]
    spec = entries(cards, LURRUS, ISAMARU, ok) + entries(cards, "Lutri, the Spellchaser", ISAMARU, [])[-1:]
    found = deck_service.validate(DeckIn(name="t", format="commander", entries=spec), cards)
    assert [w.message for w in found if "companion" in w.message] == ["Only one card may be your companion (103.2b): none of them can be used."]


def test_a_companion_in_the_deck_asks_nothing_of_it(cards):
    """The ability functions only outside the game: no warning for Lurrus as the commander or a main-deck card."""
    spells = [(1, LURRUS), (1, "Solemn Simulacrum"), FOREST5]
    assert companion_warnings(cards, None, KRENKO, spells) == []
    assert companion_warnings(cards, None, LURRUS, spells) == []


# ---- the special action ------------------------------------------------------------------------------------------------------------


def build38(cards, companion=LURRUS, commander=ISAMARU, spells=((1, "Sol Ring"), (9, "Forest")), extra=(), bob_companion=None):
    alice = deck(cards, commander, list(spells))
    alice += [DeckCard("companion", 1, n, cards.resolve(n)["id"]) for n in (companion, *extra)]
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    bob += [DeckCard("companion", 1, n, cards.resolve(n)["id"]) for n in ([bob_companion] if bob_companion else [])]
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def take(s, name=LURRUS, pid="p1", actor=None, **kw):
    act(s, actor or pid, type="activate_ability", card_id=card_named(s, name, pid).id, ability=0, **kw)


def pool(s, pid="p1"):
    return sum(s.state.players[pid].mana.values())


def test_pay_three_to_put_the_companion_into_your_hand(cards):
    s = build38(cards)
    c = card_named(s, LURRUS)
    assert c.zone == "p1:companion" and s.state.turn.phase == "main1"
    mana(s, "p1", G=3)
    take(s)
    c = s.state.cards[c.id]
    assert c.zone == "p1:hand" and pool(s) == 0 and not s.state.zones.get("stack")  # 116.2g: a special action, no stack
    assert any(LURRUS in str(e) and "companion" in str(e) for e in s.view("p2")["log"])
    check(s)


def test_it_works_in_the_second_main_phase_and_the_card_is_then_castable(cards):
    s = build38(cards)
    for _ in range(40):  # to the second main phase
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif s.state.turn.phase == "main2":
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority", until="next_step")
    assert s.state.turn.phase == "main2"
    mana(s, "p1", G=3)
    take(s)
    mana(s, "p1", W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, LURRUS).id)  # (a companion in hand is an ordinary card)
    settle(s)
    assert card_named(s, LURRUS).zone == "p1:battlefield"
    check(s)


def test_refused_at_instant_timing_and_nothing_is_paid(cards):
    s = build38(cards)
    to_end_step(s)  # (the pool empties between steps: add the mana at the step)
    mana(s, "p1", G=3)
    with pytest.raises(ActionError, match="main phase"):
        take(s)
    assert card_named(s, LURRUS).zone == "p1:companion" and pool(s) == 3
    check(s)


def test_refused_with_a_spell_on_the_stack(cards):
    s = build38(cards)
    spell = to_hand(s, "Sol Ring")
    mana(s, "p1", G=3)
    act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "stack"})
    with pytest.raises(ActionError, match="stack is empty"):
        take(s)
    assert card_named(s, LURRUS).zone == "p1:companion" and pool(s) == 3
    check(s)


def test_refused_for_a_companion_that_is_not_yours(cards):
    s = build38(cards, bob_companion="Lutri, the Spellchaser")
    mana(s, "p1", G=3)
    mana(s, "p2", U=3)
    with pytest.raises(ActionError):  # Alice's: Bob can't take it
        take(s, actor="p2")
    with pytest.raises(ActionError):  # Bob's: Alice can't take it, in her main phase with the stack empty
        take(s, "Lutri, the Spellchaser", "p2", actor="p1")
    assert card_named(s, LURRUS).zone == "p1:companion" and card_named(s, "Lutri, the Spellchaser", "p2").zone == "p2:companion"
    assert pool(s) == 3 and pool(s, "p2") == 3
    check(s)


def test_refused_for_a_card_that_is_not_a_companion(cards):
    s = build38(cards)
    ring = card_named(s, "Sol Ring")
    act(s, "p1", type="move", card_ids=[ring.id], to={"zone": "companion"})
    mana(s, "p1", G=3)
    with pytest.raises(ActionError, match="companion ability"):
        act(s, "p1", type="activate_ability", card_id=ring.id, ability=0)
    assert s.state.cards[ring.id].zone == "p1:companion"


def test_refused_without_three_mana(cards):
    s = build38(cards)
    mana(s, "p1", G=2)
    with pytest.raises(ActionError):
        take(s)
    assert card_named(s, LURRUS).zone == "p1:companion" and pool(s) == 2
    check(s)


def test_refused_when_the_starting_deck_does_not_fulfill_the_condition(cards):
    """103.2b: a companion whose condition the deck fails can't be used — the server checks the deck at the table, not the client."""
    s = build38(cards, spells=((1, "Solemn Simulacrum"), (9, "Forest")))
    mana(s, "p1", G=3)
    with pytest.raises(ActionError, match="can't be your companion"):
        take(s)
    assert card_named(s, LURRUS).zone == "p1:companion" and pool(s) == 3
    check(s)


def test_the_commander_counts_at_the_table_too(cards):
    s = build38(cards, commander=KRENKO)  # {2}{R}{R}
    mana(s, "p1", G=3)
    with pytest.raises(ActionError, match="can't be your companion"):
        take(s)


def test_yorion_is_refused_at_the_table(cards):
    s = build38(cards, companion="Yorion, Sky Nomad", commander=KRENKO)
    mana(s, "p1", G=3)
    with pytest.raises(ActionError, match="never the 120"):
        take(s, "Yorion, Sky Nomad")


def test_two_companions_are_refused(cards):
    s = build38(cards, extra=("Lutri, the Spellchaser",))
    mana(s, "p1", G=3)
    for name in (LURRUS, "Lutri, the Spellchaser"):
        with pytest.raises(ActionError, match="no more than one companion"):
            take(s, name)


def test_only_once_per_game(cards):
    s = build38(cards)
    mana(s, "p1", G=6)
    take(s)
    with pytest.raises(ActionError):  # it is in the hand now, not outside the game
        take(s)
    assert card_named(s, LURRUS).zone == "p1:hand" and pool(s) == 3
    check(s)


@pytest.mark.parametrize("name", list(CASES))
def test_each_companion_is_taken_with_its_legal_deck(cards, name):
    commander, ok, _ = CASES[name]
    s = build38(cards, companion=name, commander=commander, spells=ok)
    mana(s, "p1", G=3)
    take(s, name)
    assert card_named(s, name).zone == "p1:hand"
    check(s)


@pytest.mark.parametrize("name", list(CASES))
def test_each_companion_is_refused_with_its_illegal_deck(cards, name):
    commander, ok, bad = CASES[name]
    s = build38(cards, companion=name, commander=commander, spells=[*ok, *bad])
    mana(s, "p1", G=3)
    with pytest.raises(ActionError, match="can't be your companion"):
        take(s, name)
    assert card_named(s, name).zone == "p1:companion"


def test_the_companion_zone_is_public_and_the_library_is_not(cards):
    assert "companion" in PUBLIC_ZONES and "library" not in PUBLIC_ZONES
    s = build38(cards, spells=((1, "Lightning Bolt"), (1, "Sol Ring"), (8, "Forest")))
    c = card_named(s, LURRUS)
    secret = card_named(s, "Lightning Bolt")
    for viewer in ("p2", SPECTATOR):
        assert can_see(s.state, c, viewer) and not can_see(s.state, secret, viewer)
        assert LURRUS in json.dumps(s.view(viewer)) and "Lightning Bolt" not in json.dumps(s.view(viewer))
    mana(s, "p1", G=3)
    take(s)
    for viewer in ("p2", SPECTATOR):
        assert "Lightning Bolt" not in json.dumps(s.view(viewer))  # the special action and its log line name only the companion
    check(s)
