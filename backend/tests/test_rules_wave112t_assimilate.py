"""Wave 112T: assimilate (Star Trek), a keyword action from the Star Trek release notes
(https://magic.wizards.com/en/news/feature/star-trek-release-notes): the Comprehensive Rules (2026-09-25) don't define it yet. Real Oracle
text (Scryfall, 2026-10-30); every scenario checks the replay and a save and a load.
# Star Trek release notes (2026-11): re-check against the CR when it defines assimilate

* Assimilate: gain control of a creature or put a creature card onto the battlefield under your control; either way a +1/+1 counter, and it
  is a Borg artifact creature that loses its other creature types, keeping other supertypes, types and subtypes (Dryad Arbor: Artifact Land
  Creature — Forest Borg). Control is layer 2, the type change layer 4, both for good (611.2a).
* The Best of Both Worlds III exiles and returns "the Borg assimilated with this Saga" (607.2a), whatever it is now (its rulings).
"""

from __future__ import annotations

import pytest

from app.rules import coverage, sba
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave111e_trek import build3
from tests.wave9c_kit import build, card_named, check, mana, put

EXTRA = [
    real('Assimilate the Wounded', '{2}{B}', 3, 'Instant',
         "For each opponent, assimilate up to one target creature card from that player's graveyard that was put there from the battlefield this turn. (Put it onto the battlefield under your control with a +1/+1 counter. It's a Borg artifact creature and loses all other creature types.)", None, 'B'),
    real('Assimilation Assessor', '{4}{B}', 5, 'Artifact Creature — Borg',
         "When this creature enters, exile target opponent's graveyard.\nWhenever this creature attacks, assimilate a creature card exiled with it. (Put it onto the battlefield under your control with a +1/+1 counter. It's a Borg artifact creature and loses all other creature types.)", ("5", "5"), 'B'),
    real('Borg Cube', '{5}{W}{B}', 7, 'Artifact — Spacecraft',
         "Affinity for artifact creatures\nWhenever this Spacecraft enters or attacks, assimilate a creature card exiled with it. If you can't, exile up to one target creature. (To assimilate a card, put it onto the battlefield under your control with a +1/+1 counter. It's a Borg artifact creature and loses all other creature types.)\nStation\n12+ | Artifact creatures you control have flying.", ("6", "6"), 'WB'),
    real('Borg Queen, Perfection Manifest', '{4}{B}{B}', 6, 'Legendary Artifact Creature — Borg Noble',
         "Artifact creatures you control get +2/+0.\nWhen Borg Queen enters, assimilate target creature card from an opponent's graveyard. (Put it onto the battlefield under your control with a +1/+1 counter. It's a Borg artifact creature and loses all other creature types.)", ("1", "4"), 'B'),
    real('Death Is Irrelevant', '{6}{B}{B}', 8, 'Enchantment',
         "Artifact creatures you control have indestructible.\nAt the beginning of your end step, assimilate target creature card from a graveyard. (Put it onto the battlefield under your control with a +1/+1 counter. It's a Borg artifact creature and loses all other creature types.)", None, 'B'),
    real('Gift of Perfection', '{4}{U}', 5, 'Sorcery',
         "Each opponent reveals cards from the top of their library until they reveal a creature card. Assimilate one of the creature cards revealed this way. Then each opponent puts the other cards they revealed this way on the bottom of their library in a random order. (To assimilate a card, put it onto the battlefield under your control with a +1/+1 counter. It's a Borg artifact creature and loses all other creature types.)", None, 'U'),
    real('The Best of Both Worlds', '{4}{W}{U}', 6, 'Enchantment — Saga',
         "(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Assimilate target nonartifact creature an opponent controls. (Gain control of it and put a +1/+1 counter on it. It's a Borg artifact creature and loses all other creature types.)\nII — Artifact creatures you control get +2/+2 until end of turn.\nIII — Exile the Borg assimilated with this Saga, then return it to the battlefield under its owner's control.", None, 'WU'),
    real('The Borg Queen', '{4}{W}{U}{B}', 7, 'Legendary Artifact Creature — Borg Noble',
         "Artifact creatures you control get +2/+2.\nWhenever The Borg Queen enters or attacks, target opponent exiles cards from the top of their library until they exile a creature card. Assimilate that card. They put the rest on the bottom in a random order. (To assimilate a card, put it onto the battlefield under your control with a +1/+1 counter. It's a Borg artifact creature and loses all other creature types.)", ("4", "4"), 'WUB'),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [
    real("Dryad Arbor", "", 0, "Land Creature — Forest Dryad",
         "(This land isn't a spell, it's affected by summoning sickness, and it has \"{T}: Add {G}.\")", ("1", "1"), "G"),
    real("Test Proliferate 111E", "{U}", 1, "Instant", "Proliferate.", None, "U"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn (a list: several options), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            if any(i not in {o.id for o in d.options} for i in ids):
                raise AssertionError(f"{d.prompt}: {[(o.id, o.label) for o in d.options]}")
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def stats(s, c):
    card = s.state.cards[c.id]
    return sba.power(card, ch(s, c)), sba.toughness(card, ch(s, c))


def on_top(s, pid, names):
    """Put the named cards of ``pid``'s library on top, in this order (the first on top), as moves (replayed)."""
    ids = [card_named(s, n, pid).id for n in names]
    for cid in reversed(ids):
        act(s, pid, type="move", card_ids=[cid], to={"player": pid, "zone": "library"}, position="top")
    assert s.state.zones[f"{pid}:library"][:len(ids)] == ids
    return ids


def next_turn_attack(s, attacker):
    """To Alice's next turn: declare ``attacker`` against Bob."""
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.active_player == "p1" and s.state.turn.number > turn and s.state.turn.phase == "main1")
    act(s, "p1", type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_attackers"
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": attacker.id, "target": "p2"}])


def zone(s, c):
    return s.state.cards[c.id].zone


def to(s, c, z, pid=None):
    act(s, pid or c.owner, type="move", card_ids=[c.id], to={"player": pid or c.owner, "zone": z})


def borg(s, c, pid="p1", counters=1):
    """Assimilated: on the battlefield under ``pid``, with the +1/+1 counter(s), a Borg artifact creature with no other creature type."""
    card = s.state.cards[c.id]
    x = ch(s, c)
    assert card.zone.endswith(":battlefield") and card.controller == pid
    assert card.counters.get("+1/+1") == counters
    assert {"Artifact", "Creature"} <= set(x.types) and "Borg" in x.subtypes and not ({"Bear", "Dryad", "Elf", "Druid"} & set(x.subtypes))
    return x


def chapter(s, saga, n, *picks):
    """Chapter ``n`` of ``saga``: n - 1 lore counters by hand, then a real proliferate adds the n-th (714.2b)."""
    if n > 1:
        act(s, "p1", type="counter", card_ids=[saga.id], kind="lore", delta=n - 1 - s.state.cards[saga.id].counters.get("lore", 0))
    mana(s, U=1)
    c = card_named(s, "Test Proliferate 111E")
    to(s, c, "hand")
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s, [saga.id], *picks)


# -- from a graveyard -------------------------------------------------------------------------------------------------------------------
def test_borg_queen_perfection_manifest_assimilates_from_an_opponents_graveyard(cards):
    s = build(cards, ["Borg Queen, Perfection Manifest"], ["Grizzly Bears"])
    bears = card_named(s, "Grizzly Bears", "p2")
    to(s, bears, "graveyard")
    queen = card_named(s, "Borg Queen, Perfection Manifest")
    to(s, queen, "hand")
    mana(s, B=2, C=4)
    act(s, "p1", type="cast_spell", card_id=queen.id)
    answer(s)
    x = borg(s, bears)
    assert x.subtypes == {"Borg"} and stats(s, bears) == (5, 3)  # 2/2, the counter, the Queen's +2/+0 for artifact creatures
    check(s)


def test_death_is_irrelevant_keeps_other_types_dryad_arbor(cards):
    s = build(cards, ["Death Is Irrelevant", "Dryad Arbor"])
    put(s, "Death Is Irrelevant")
    arbor = card_named(s, "Dryad Arbor")
    to(s, arbor, "graveyard")
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            answer(s)
        elif s.state.zones.get("stack") or s.state.turn.phase != "end":
            act(s, s.state.rules.priority, type="pass_priority")
        if zone(s, arbor) == "p1:battlefield":
            break
    answer(s)
    x = borg(s, arbor)
    assert x.subtypes == {"Forest", "Borg"} and set(x.types) == {"Artifact", "Land", "Creature"}  # "Artifact Land Creature – Forest Borg"
    assert "indestructible" in x.keywords  # Death Is Irrelevant: artifact creatures you control have indestructible
    check(s)


def test_assimilate_the_wounded_one_per_opponent_only_creatures_that_died_this_turn(cards):
    s = build3(cards, ["Assimilate the Wounded", "Lightning Bolt"], ["Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    bob_bears, bob_elves = card_named(s, "Grizzly Bears", "p2"), card_named(s, "Llanowar Elves", "p2")
    carol_bears = card_named(s, "Grizzly Bears", "p3")
    to(s, bob_elves, "graveyard")  # put there from the library, not from the battlefield
    for c in (bob_bears, carol_bears):
        to(s, c, "battlefield")
        to(s, c, "graveyard")  # died this turn (put there from the battlefield)
    wounded = card_named(s, "Assimilate the Wounded")
    to(s, wounded, "hand")
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=wounded.id)
    d = s.state.rules.decision  # "up to one target … from that player's graveyard that was put there from the battlefield this turn", per opponent
    assert [o.id for o in d.options] == [bob_bears.id]  # not the Elves (milled from the library)
    answer(s, [bob_bears.id], [carol_bears.id])
    borg(s, bob_bears)
    borg(s, carol_bears)
    assert zone(s, bob_elves) == "p2:graveyard"
    check(s)


# -- cards exiled with it ---------------------------------------------------------------------------------------------------------------
def test_assimilation_assessor_assimilates_a_card_it_exiled(cards):
    s = build(cards, ["Assimilation Assessor"], ["Grizzly Bears"])
    bears = card_named(s, "Grizzly Bears", "p2")
    to(s, bears, "graveyard")
    assessor = card_named(s, "Assimilation Assessor")
    to(s, assessor, "hand")
    mana(s, B=1, C=4)
    act(s, "p1", type="cast_spell", card_id=assessor.id)
    answer(s, "p2")
    assert zone(s, bears) == "p2:exile"
    next_turn_attack(s, assessor)
    answer(s)
    borg(s, bears)
    check(s)


def test_borg_cube_exiles_when_it_cant_assimilate_then_assimilates_that_card(cards):
    s = build(cards, ["Borg Cube"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    cube = card_named(s, "Borg Cube")
    to(s, cube, "hand")
    mana(s, W=1, B=1, C=5)
    act(s, "p1", type="cast_spell", card_id=cube.id)
    answer(s, [bears.id])  # nothing exiled with it: "If you can't, exile up to one target creature."
    assert zone(s, bears) == "p2:exile"
    act(s, "p1", type="counter", card_ids=[cube.id], kind="charge", delta=12)  # 12+: a 6/6 artifact creature
    next_turn_attack(s, cube)
    answer(s)
    borg(s, bears)
    check(s)


# -- an opponent's library --------------------------------------------------------------------------------------------------------------
def test_the_borg_queen_assimilates_the_creature_card_exiled_and_bottoms_the_rest(cards):
    s = build(cards, ["The Borg Queen"], ["Grizzly Bears", "Lightning Bolt"], islands=3)
    bears, bolt = card_named(s, "Grizzly Bears", "p2"), card_named(s, "Lightning Bolt", "p2")
    on_top(s, "p2", ["Lightning Bolt", "Grizzly Bears"])
    queen = card_named(s, "The Borg Queen")
    to(s, queen, "hand")
    mana(s, W=1, U=1, B=1, C=4)
    act(s, "p1", type="cast_spell", card_id=queen.id)
    answer(s, "p2")
    borg(s, bears)
    assert s.state.zones["p2:library"][-1] == bolt.id  # the rest: on the bottom
    check(s)


@pytest.mark.parametrize("pick", ["p2", "p3"])
def test_gift_of_perfection_assimilates_one_revealed_creature_card(cards, pick):
    s = build3(cards, ["Gift of Perfection"], ["Grizzly Bears", "Lightning Bolt"], ["Llanowar Elves"])
    tops = {"p2": on_top(s, "p2", ["Lightning Bolt", "Grizzly Bears"]), "p3": on_top(s, "p3", ["Llanowar Elves"])}
    gift = card_named(s, "Gift of Perfection")
    to(s, gift, "hand")
    mana(s, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=gift.id)
    chosen = tops[pick][-1]
    answer(s, chosen)
    borg(s, s.state.cards[chosen])
    other = tops["p3" if pick == "p2" else "p2"][-1]
    assert s.state.zones[f"{s.state.cards[other].owner}:library"][-1] == other or s.state.cards[other].zone.endswith(":library")
    assert s.state.zones["p2:library"][-1] in tops["p2"]  # Bob's other revealed cards went to the bottom
    check(s)


# -- The Best of Both Worlds --------------------------------------------------------------------------------------------------------------
def test_the_best_of_both_worlds_assimilates_then_returns_the_borg_to_its_owner(cards):
    s = build(cards, ["The Best of Both Worlds", "Test Proliferate 111E"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    saga = card_named(s, "The Best of Both Worlds")
    to(s, saga, "hand")
    mana(s, W=1, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=saga.id)
    answer(s, bears.id)  # chapter I
    borg(s, bears)
    assert stats(s, bears) == (3, 3)
    chapter(s, saga, 2)
    assert stats(s, bears) == (5, 5)  # artifact creatures you control get +2/+2
    chapter(s, saga, 3)
    card = s.state.cards[bears.id]
    assert card.zone == "p2:battlefield" and card.controller == "p2" and not card.counters.get("+1/+1")
    assert ch(s, bears).subtypes == {"Bear"} and "Artifact" not in ch(s, bears).types  # a new object (400.7)
    check(s)
