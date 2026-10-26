"""Wave 110G session 16."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100f_attached import next_turn
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

ELEVENTH = ("(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\n"
            "I — Search your library for a Doctor card, reveal it, put it into your hand, then shuffle.\n"
            "II — Create a Food token and a 1/1 white Human creature token with \"Doctor spells you cast cost {1} less to cast.\"\n"
            "III — Create a token that's a copy of target creature, except it's a legendary Alien named Prisoner Zero.")
EXTRA = [real("The Eleventh Hour", "{3}{W}", 4, "Enchantment — Saga", ELEVENTH, None, "W"),
         real("Test Doctor", "{2}", 2, "Creature \u2014 Time Lord Doctor", "", ("1", "1"), ""),
         real("Guile", "{3}{U}{U}", 5, "Creature \u2014 Elemental Incarnation", "This creature can't be blocked except by three or more creatures.\nIf a spell or ability you control would counter a spell, instead exile that spell and you may play that card without paying its mana cost.\nWhen Guile is put into a graveyard from anywhere, shuffle it into its owner's library.", ("3", "3"), "U"),
         real("Test Nope", "{U}", 1, "Instant", "Counter target spell.", None, "U"),
         real("Test Boon", "{U}", 1, "Instant", "You gain 5 life.", None, "U"),
         real("Curse of Inertia", "{2}{U}", 3, "Enchantment \u2014 Aura Curse", "Enchant player\nWhenever a player attacks enchanted player with one or more creatures, that attacking player may tap or untap target permanent of their choice.", None, "U"),
         real("Extraordinary Journey", "{X}{G}{W}", 2, "Enchantment", "When this enchantment enters, exile up to X target creatures. For each of those cards, its owner may play it for as long as it remains exiled.\nWhenever one or more nontoken creatures enter, if one or more of them entered from exile or was cast from exile, you draw a card. This ability triggers only once each turn.", None, "GW"),
         real("Test Elf", "{1}{G}", 2, "Creature — Elf Warrior", "Vigilance", ("2", "3"), "G")]


@pytest.fixture
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def answer(s, limit=40):
    for _ in range(limit):
        if (d := s.state.rules.decision) is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


@pytest.mark.parametrize("name", ["The Eleventh Hour", "Guile", "Curse of Inertia", "Extraordinary Journey"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _chapter(cards, lore):
    """The Saga with ``lore`` counters, then Alice's next precombat main adds the next one: that chapter triggers and resolves."""
    s = build(cards, ["The Eleventh Hour", "Test Elf", "Test Doctor"], [], forests=12, islands=20)
    elf = put(s, "Test Elf")
    saga = put(s, "The Eleventh Hour")
    if lore:
        act(s, "p1", type="counter", card_ids=[saga.id], kind="lore", delta=lore)
    next_turn(s, until=lambda x: x.state.turn.number == 3 and x.state.turn.phase == "main1")
    answer(s)
    return s, elf


def test_eleventh_hour_ii_food_and_a_human_that_cheapens_doctors(cards):
    """The Eleventh Hour II (111.10, 601.2f): a Food and a 1/1 Human; Doctor spells cost {1} less while it is out."""
    s, _ = _chapter(cards, 1)
    toks = {c.name for c in s.state.cards.values() if c.zone == "p1:battlefield"}
    assert {"Food", "Human"} <= toks
    mana(s, C=1)  # the Doctor costs {2}, one less with the Human
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Doctor").id)
    answer(s)
    assert card_named(s, "Test Doctor").zone == "p1:battlefield"
    check(s)


def test_eleventh_hour_iii_prisoner_zero(cards):
    """The Eleventh Hour III (707.9b, 205.1a): a legendary Alien named Prisoner Zero copy of the Elf; its creature types are replaced, its abilities copied."""
    from tests.wave110b_kit import ch

    s, elf = _chapter(cards, 2)
    zero = next(c for c in s.state.cards.values() if c.zone == "p1:battlefield" and ch(s, c).name == "Prisoner Zero")
    z = ch(s, zero)
    assert (z.subtypes, "Legendary" in z.supertypes, z.pt, "vigilance" in {k.lower() for k in z.keywords}) == ({"Alien"}, True, (2, 3), True)
    assert ch(s, s.state.cards[elf.id]).subtypes == {"Elf", "Warrior"}
    check(s)


@pytest.mark.parametrize("guile,cast_it,life,zone", [(True, True, 45, "p1:graveyard"), (True, False, 40, "p1:exile"), (False, True, 40, "p1:graveyard")])
def test_guile_exiles_a_countered_spell_and_offers_a_free_cast(cards, guile, cast_it, life, zone):
    """Guile (614.1a, ruling 2007-10-01): the spell is exiled instead of countered and its countering player may cast it free at once (it is theirs then);
    declining leaves it exiled; without Guile it is countered."""
    s = build(cards, ["Test Boon"], ["Guile", "Test Nope"])
    if guile:
        put(s, "Guile", "p2")
    mana(s, "p1", U=1)
    mana(s, "p2", U=1)
    for p in ("p1", "p2"):
        act(s, p, type="configure", automation_options={"auto_priority_pass": False})
    boon = to_hand(s, "Test Boon")
    act(s, "p1", type="cast_spell", card_id=boon.id)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Test Nope", "p2").id, targets=[boon.id])
    asked = False
    for _ in range(14):
        if (d := s.state.rules.decision) is not None:
            asked = True
            assert d.player == "p2" and guile and "Guile" in d.prompt
            act(s, "p2", type="choose", decision_id=d.id, option_ids=["yes" if cast_it else "no"])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert asked is guile
    assert s.state.players["p2"].life == life and s.state.players["p1"].life == 40
    assert s.state.cards[boon.id].zone == zone
    check(s)


@pytest.mark.parametrize("choice,before,after", [("tap", False, True), ("untap", True, False), ("none", True, True)])
def test_curse_of_inertia_attacker_chooses(cards, choice, before, after):
    """Curse of Inertia (115.1, 603.3d, ruling 2013-10-17): the attacking player (not the Curse's controller) picks the target and may tap or untap it."""
    s = build(cards, ["Curse of Inertia", "Test Elf"], ["Test Elf"])
    elf = put(s, "Test Elf")  # Alice's tapped Elf
    if before:
        act(s, "p1", type="tap", card_ids=[elf.id])
    mana(s, U=1, C=2)
    curse = to_hand(s, "Curse of Inertia")
    act(s, "p1", type="cast_spell", card_id=curse.id, targets=["p1"])
    answer(s)
    assert s.state.cards[curse.id].zone == "p1:battlefield"
    next_turn(s)
    bob = put(s, "Test Elf", "p2")
    s.state.rules.controlled_since[bob.id].turn = 0
    for p in ("p1", "p2"):
        act(s, p, type="configure", automation_options={"auto_priority_pass": False})
    for _ in range(6):
        if s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bob.id, "target": "p1"}])
    for _ in range(8):
        if (d := s.state.rules.decision) is not None:
            assert d.player == "p2"
            act(s, "p2", type="choose", decision_id=d.id, option_ids=[elf.id if d.prompt.endswith("target") else choice])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[elf.id].tapped is after
    check(s)


def _hand(s, pid="p1"):
    return len([c for c in s.state.cards.values() if c.zone == f"{pid}:hand"])


def _journey(cards, x):
    s = build(cards, ["Extraordinary Journey", "Test Elf", "Test Elf"], ["Test Elf"], forests=12, islands=20)
    mine, theirs = put(s, "Test Elf"), put(s, "Test Elf", "p2")
    mana(s, G=1, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Extraordinary Journey").id, x_value=x)
    for _ in range(30):
        if (d := s.state.rules.decision) is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.max_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s, mine, theirs


def test_extraordinary_journey_exiles_up_to_x_and_owners_play_them(cards):
    """Extraordinary Journey (607.2, 113.6, 400.7): up to X creatures exiled; the owner (not the controller) may play each, and entering from exile or cast from exile draws once a turn."""
    s, mine, theirs = _journey(cards, 2)
    assert s.state.cards[mine.id].zone == "p1:exile" and s.state.cards[theirs.id].zone == "p2:exile"
    before = _hand(s)
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=mine.id)  # cast from exile by its owner
    for _ in range(8):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[mine.id].zone == "p1:battlefield" and _hand(s) == before + 1
    check(s)


def test_extraordinary_journey_x_is_the_most(cards):
    s, mine, theirs = _journey(cards, 1)
    assert sorted([s.state.cards[mine.id].zone, s.state.cards[theirs.id].zone]).count("p1:exile") + sorted([s.state.cards[mine.id].zone, s.state.cards[theirs.id].zone]).count("p2:exile") == 1
    check(s)


def test_extraordinary_journey_no_draw_for_a_creature_cast_from_hand(cards):
    s, *_ = _journey(cards, 0)
    elf = to_hand(s, "Test Elf")
    before = _hand(s)
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=elf.id)
    for _ in range(8):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[elf.id].zone == "p1:battlefield" and _hand(s) == before - 1
    check(s)


def test_extraordinary_journey_opponent_plays_theirs_and_you_draw(cards):
    """Its owner may play an opponent's exiled creature (on their turn); the Journey's controller draws when it enters from exile."""
    s, mine, theirs = _journey(cards, 2)
    next_turn(s)
    before = _hand(s)
    mana(s, "p2", G=1, C=1)
    act(s, "p2", type="cast_spell", card_id=theirs.id)
    for _ in range(8):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[theirs.id].zone == "p2:battlefield" and _hand(s) == before + 1
    check(s)
