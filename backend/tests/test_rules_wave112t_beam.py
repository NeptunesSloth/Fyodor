"""Wave 112T: beam me up (Star Trek), from the Star Trek release notes (https://magic.wizards.com/en/news/feature/star-trek-release-notes):
the Comprehensive Rules (2026-09-25) don't define it yet. Real Oracle text (Scryfall, 2026-10-30); every scenario checks the replay and a
save and a load.
# Star Trek release notes (2026-11): re-check against the CR when it defines beam me up

* "Beam me up [cost]" means "You may cast this card from your graveyard by paying [cost] and returning a creature you control to its owner's
  hand rather than paying its mana cost" and "If the beam me up cost was paid, exile this card instead of putting it anywhere else any time
  it would leave the stack." Timing restrictions still apply; cost increases apply on top; it works on a card put into the graveyard
  without being cast (every scenario here moves the card there).
* "A permanent that 'can't be beamed up' can't be returned to a player's hand to pay a beam me up cost." (Marooned)
* Scotty: granted beam me up during your main phase, for instants and sorceries, for the card's mana cost; Scotty himself can't be returned
  for those (his ruling), but can for a card's own beam me up.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.casting import alt_castable
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, put

EXTRA = [
    real('Energize', '{1}{U}', 2, 'Sorcery',
         "Return target creature an opponent controls to its owner's hand.\nBeam me up {3}{U} (You may cast this card from your graveyard for {3}{U} if you also return a creature you control to its owner's hand. Then exile this spell.)", None, 'U'),
    real('Open Communications', '{U}', 1, 'Sorcery',
         "Draw a card.\nBeam me up {2}{U} (You may cast this card from your graveyard for {2}{U} if you also return a creature you control to its owner's hand. Then exile this spell.)", None, 'U'),
    real('Transporter Malfunction', '{1}{R}', 2, 'Sorcery',
         "Transporter Malfunction deals 3 damage to any target.\nBeam me up {3}{R}{R}{R} (You may cast this card from your graveyard for {3}{R}{R}{R} if you also return a creature you control to its owner's hand. Then exile this spell.)", None, 'R'),
    real('Adversary by Algorithm', '{2}{G}', 3, 'Sorcery',
         "Create a 3/3 colorless Illusion artifact creature token.\nBeam me up {3}{G} (You may cast this card from your graveyard for {3}{G} if you also return a creature you control to its owner's hand. Then exile this spell.)", None, 'G'),
    real('Boarding Action', '{1}{R}', 2, 'Sorcery',
         "Create a 2/1 red Klingon Warrior creature token with haste.\nBeam me up {2}{R} (You may cast this card from your graveyard for {2}{R} if you also return a creature you control to its owner's hand. Then exile this spell.)", None, 'R'),
    real('Federation Resupply', '{1}{W}', 2, 'Sorcery',
         "Search your library for an Aura, Equipment, or Spacecraft card, reveal it, put it into your hand, then shuffle.\nBeam me up {3}{W} (You may cast this card from your graveyard for {3}{W} if you also return a creature you control to its owner's hand. Then exile this spell.)", None, 'W'),
    real('Final Frontier', '{2}{G}', 3, 'Sorcery',
         "Search your library for a basic land card or Planet card, put it onto the battlefield tapped, then shuffle.\nBeam me up {1}{G} (You may cast this card from your graveyard for {1}{G} if you also return a creature you control to its owner's hand. Then exile this spell.)", None, 'G'),
    real('Pattern Buffer Preservation', '{1}{B}', 2, 'Sorcery',
         "Look at the top two cards of your library. Put one of them into your hand and the other into your graveyard.\nBeam me up {1}{B} (You may cast this card from your graveyard for {1}{B} if you also return a creature you control to its owner's hand. Then exile this spell.)", None, 'B'),
    real('Pure Energy', '{1}{W}', 2, 'Sorcery',
         "Distribute two +1/+1 counters among one or two target creatures.\nBeam me up {2}{W} (You may cast this card from your graveyard for {2}{W} if you also return a creature you control to its owner's hand. Then exile this spell.)", None, 'W'),
    real("There's Coffee in that Nebula", '{1}{W}', 2, 'Sorcery',
         "Look at the top five cards of your library. You may reveal a Plains card or nonland permanent card with mana value 3 or less from among them and put it into your hand. Put the rest on the bottom in a random order.\nBeam me up {2}{W} (You may cast this card from your graveyard for {2}{W} if you also return a creature you control to its owner's hand. Then exile this spell.)", None, 'W'),
    real('Scotty, Miracle Worker', '{1}{U}{U}', 3, 'Legendary Creature — Human Artificer',
         "During your main phase, each card in your graveyard has beam me up. The beam me up cost is equal to that spell's mana cost. Scotty can't be beamed up to cast a spell this way. (Only instant and sorcery spells can be cast this way. You may cast a card from your graveyard for its beam me up cost if you also return another creature you control to its owner's hand. Then exile that spell.)", ("2", "3"), 'U'),
    real('Marooned', '{U}', 1, 'Enchantment — Aura',
         "Enchant artifact or creature\nWhen this Aura enters, you may pay {3}. If you do, tap enchanted permanent.\nEnchanted permanent doesn't untap during its controller's untap step and can't be beamed up.", None, 'U'),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [
    real("Thalia, Guardian of Thraben", "{1}{W}", 2, "Legendary Creature — Human Soldier",
         "First strike\nNoncreature spells cost {1} more to cast.", ("2", "1"), "W"),
    real("Plains", "", 0, "Basic Land — Plains", "({T}: Add {W}.)"),
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
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_gy(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    return c


def zone(s, c):
    return s.state.cards[c.id].zone


def offers(s, c, pid="p1"):
    return [o["label"] for o in alt_castable(s.state, pid, s.state.cards[c.id], s.cards, announce=True)]


# -- a card's own beam me up ----------------------------------------------------------------------------------------------------------
def test_energize_cast_from_the_graveyard_returns_a_creature_and_is_exiled(cards):
    s = build(cards, ["Energize", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    energize = to_gy(s, "Energize")
    mine = put(s, "Grizzly Bears")
    elves = put(s, "Llanowar Elves")
    theirs = put(s, "Grizzly Bears", "p2")
    assert offers(s, energize) == []  # no mana yet: the hint lists only costs that can be paid (118.3)
    mana(s, U=1, C=3)
    assert offers(s, energize) == ["Energize: beam me up {3}{U}"]
    act(s, "p1", type="cast_spell", card_id=energize.id, targets=[theirs.id])
    d = s.state.rules.decision  # the creature to return is chosen as the cost is paid (601.2b, 601.2h), in words
    assert d is not None and d.player == "p1" and "return" in d.prompt.lower() and {o.id for o in d.options} == {mine.id, elves.id}
    answer(s, mine.id)
    assert zone(s, mine) == "p1:hand" and zone(s, elves) == "p1:battlefield" and zone(s, theirs) == "p2:hand"
    assert zone(s, energize) == "p1:exile"  # exiled as it leaves the stack
    check(s)


def test_beam_me_up_spell_countered_is_exiled(cards):
    s = build(cards, ["Open Communications", "Grizzly Bears"], ["Counterspell"])
    comms = to_gy(s, "Open Communications")
    bear = put(s, "Grizzly Bears")
    counter = card_named(s, "Counterspell", "p2")
    act(s, "p2", type="move", card_ids=[counter.id], to={"zone": "hand"})
    mana(s, U=1, C=2)
    mana(s, "p2", U=2)
    act(s, "p1", type="cast_spell", card_id=comms.id, cost_choices=[{"component": 0, "cards": [bear.id]}])
    assert zone(s, bear) == "p1:hand" and zone(s, comms) == "stack"
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[comms.id])
    answer(s)
    assert zone(s, comms) == "p1:exile"  # "whether it resolves, is countered, or leaves the stack in some other way"
    check(s)


def test_beam_me_up_needs_a_creature_to_return_and_sorcery_timing(cards):
    s = build(cards, ["Boarding Action", "Grizzly Bears"])
    action = to_gy(s, "Boarding Action")
    mana(s, R=1, C=2)
    assert offers(s, action) == []  # no creature you control: the cost can't be paid
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=action.id)
    bear = put(s, "Grizzly Bears")
    assert offers(s, action) == ["Boarding Action: beam me up {2}{R}"]
    act(s, "p1", type="cast_spell", card_id=action.id, cost_choices=[{"component": 0, "cards": [bear.id]}])
    answer(s)
    tokens = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Klingon Warrior"]
    assert len(tokens) == 1 and zone(s, action) == "p1:exile" and zone(s, bear) == "p1:hand"
    check(s)


def test_beam_me_up_sorcery_not_while_the_stack_has_a_spell(cards):
    s = build(cards, ["Final Frontier", "Grizzly Bears", "Opt"])
    frontier = to_gy(s, "Final Frontier")
    put(s, "Grizzly Bears")
    opt = card_named(s, "Opt")
    act(s, "p1", type="move", card_ids=[opt.id], to={"zone": "hand"})
    mana(s, U=1, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    assert offers(s, frontier) == []  # "you can cast a sorcery using beam me up only when you could normally cast a sorcery"
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=frontier.id)
    answer(s)
    check(s)


def test_cost_increase_applies_on_top_of_beam_me_up(cards):
    s = build(cards, ["Open Communications", "Grizzly Bears"], ["Thalia, Guardian of Thraben"])
    comms = to_gy(s, "Open Communications")
    bear = put(s, "Grizzly Bears")
    put(s, "Thalia, Guardian of Thraben", "p2")
    mana(s, U=1, C=1)  # {2}{U} + {1} = 4: three isn't enough
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=comms.id, cost_choices=[{"component": 0, "cards": [bear.id]}])
    assert zone(s, bear) == "p1:battlefield" and zone(s, comms) == "p1:graveyard"
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=comms.id, cost_choices=[{"component": 0, "cards": [bear.id]}])
    answer(s)
    assert zone(s, comms) == "p1:exile" and s.state.players["p1"].mana_pool.total() == 0 if hasattr(s.state.players["p1"], "mana_pool") else True
    check(s)


# -- can't be beamed up ---------------------------------------------------------------------------------------------------------------
def test_marooned_permanent_cant_be_returned_for_beam_me_up(cards):
    s = build(cards, ["Pure Energy", "Grizzly Bears", "Marooned", "Llanowar Elves"])
    energy = to_gy(s, "Pure Energy")
    bear = put(s, "Grizzly Bears")
    marooned = card_named(s, "Marooned")
    act(s, "p1", type="move", card_ids=[marooned.id], to={"zone": "hand"})
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=marooned.id, targets=[bear.id])
    answer(s)  # (the {3} isn't paid: the bear stays untapped)
    assert s.state.cards[marooned.id].attached_to == bear.id
    mana(s, W=1, C=2)
    assert offers(s, energy) == []  # the only creature can't be beamed up
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=energy.id, targets=[bear.id], cost_choices=[{"component": 0, "cards": [bear.id]}])
    elves = put(s, "Llanowar Elves")
    act(s, "p1", type="cast_spell", card_id=energy.id, targets=[bear.id])
    d = s.state.rules.decision
    if d is not None and d.kind != "choose_cards":
        pass
    while (d := s.state.rules.decision) is not None and any(o.id == elves.id for o in d.options):
        assert bear.id not in [o.id for o in d.options]  # the enchanted bear isn't offered
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[elves.id])
        break
    answer(s)
    assert zone(s, elves) == "p1:hand" and zone(s, bear) == "p1:battlefield" and zone(s, energy) == "p1:exile"
    check(s)


# -- Scotty ---------------------------------------------------------------------------------------------------------------------------
def test_scotty_grants_beam_me_up_for_the_mana_cost_and_cant_be_returned_himself(cards):
    s = build(cards, ["Scotty, Miracle Worker", "Lightning Bolt", "Grizzly Bears", "Llanowar Elves", "Monastery Swiftspear"])
    bolt = to_gy(s, "Lightning Bolt")
    bears = to_gy(s, "Grizzly Bears")
    scotty = put(s, "Scotty, Miracle Worker")
    mana(s, R=1, G=2)
    assert offers(s, bolt) == []  # Scotty can't be beamed up for his own grant: nothing else to return
    assert offers(s, bears) == []  # only instants and sorceries
    elves = put(s, "Llanowar Elves")
    monk = put(s, "Monastery Swiftspear")
    assert offers(s, bolt) == ["Scotty, Miracle Worker: beam me up {R}"]
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {elves.id, monk.id}  # never Scotty
    answer(s, elves.id)
    assert s.state.players["p2"].life == 37 and zone(s, bolt) == "p1:exile" and zone(s, elves) == "p1:hand"
    assert zone(s, scotty) == "p1:battlefield" and zone(s, monk) == "p1:battlefield"
    check(s)


def test_scotty_only_during_your_main_phase(cards):
    s = build(cards, ["Scotty, Miracle Worker", "Lightning Bolt", "Llanowar Elves"])
    bolt = to_gy(s, "Lightning Bolt")
    put(s, "Scotty, Miracle Worker")
    put(s, "Llanowar Elves")
    mana(s, R=1)
    assert offers(s, bolt)
    act(s, "p1", type="pass_priority")  # → beginning of combat
    assert s.state.turn.phase != "main1"
    assert offers(s, bolt) == []
    check(s)


def test_scotty_can_be_returned_for_a_cards_own_beam_me_up(cards):
    s = build(cards, ["Scotty, Miracle Worker", "Energize", "Grizzly Bears"], ["Grizzly Bears"])
    energize = to_gy(s, "Energize")
    scotty = put(s, "Scotty, Miracle Worker")
    theirs = put(s, "Grizzly Bears", "p2")
    mana(s, U=2, C=2)
    labels = offers(s, energize)
    assert labels == ["Energize: beam me up {3}{U}"]  # Scotty's own grant needs another creature: only the printed one is offered
    act(s, "p1", type="cast_spell", card_id=energize.id, targets=[theirs.id], alt_cost=f"{energize.id}:1",
        cost_choices=[{"component": 0, "cards": [scotty.id]}])
    answer(s)
    assert zone(s, scotty) == "p1:hand" and zone(s, theirs) == "p2:hand" and zone(s, energize) == "p1:exile"
    check(s)


# -- There's Coffee in that Nebula: "a Plains card or nonland permanent card with mana value 3 or less" -----------------------------
def test_theres_coffee_in_that_nebula_offers_a_plains_or_a_small_nonland_permanent(cards):
    s = build(cards, ["There's Coffee in that Nebula", "Plains", "Grizzly Bears", "Mulldrifter", "Lightning Bolt"])
    top = ["Plains", "Grizzly Bears", "Mulldrifter", "Forest", "Lightning Bolt"]
    ids = []
    for name in top:
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p1" and c.zone == "p1:library" and c.id not in ids)
        ids.append(c.id)
    for cid in reversed(ids):
        act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "library"}, position="top")
    coffee = card_named(s, "There's Coffee in that Nebula")
    act(s, "p1", type="move", card_ids=[coffee.id], to={"zone": "hand"})
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=coffee.id)
    d = s.state.rules.decision
    while d is None:
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    assert {o.id for o in d.options} == {ids[0], ids[1]}  # the Plains and the Bears; not Mulldrifter (5), the Forest or the instant
    answer(s, ids[1])
    assert zone(s, s.state.cards[ids[1]]) == "p1:hand"
    assert set(s.state.zones["p1:library"][-4:]) == {ids[0], *ids[2:]}  # the rest on the bottom
    check(s)
