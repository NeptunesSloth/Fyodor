"""Wave 111R2: two engine capabilities around mana and activations (app/rules/wave111r2_mana.py). Real Oracle text; every scenario checks the
replay and a save and a load.

* "Spend this mana only to cast your commander." (Queen's Diamond, Jeweled Lotus; 106.6, 903.3, 903.3d, 702.124e): the spell is a commander the
  payer owns, read from the card (an attribute, not a characteristic); its whole total cost (601.2f: commander tax included); nothing else.
* "Whenever an opponent casts a spell with the chosen name or activates an ability of a source with the chosen name, that player loses 3 life."
  (Kai Winn; 109.2c, 602.1c, 605.1a, 603.2c, 603.3): a source in any zone, mana abilities included; the trigger uses the stack, after the spell
  being paid for is cast.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import casting, coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import card_named, check, life, put, to_hand

EXTRA = [
    real("Queen's Diamond", "{4}", 4, "Legendary Artifact — Spacecraft",
         "{T}: Choose a color. Add one mana of that color for each charge counter on Queen's Diamond. Spend this mana only to cast your commander.\n"
         "Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an "
         "artifact creature at 8+.)\n8+ | Flying, vigilance, haste", ("5", "5"), ""),
    real("Kai Winn, Faithless Leader", "{1}{B}", 2, "Legendary Creature — Bajoran Cleric",
         "As Kai Winn enters, choose a nonland card name.\nWhenever an opponent casts a spell with the chosen name or activates an ability of a "
         "source with the chosen name, that player loses 3 life.", ("3", "1"), "B"),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [
    real("Jeweled Lotus", "{0}", 0, "Artifact",
         "{T}, Sacrifice this artifact: Add three mana of any one color. Spend this mana only to cast your commander.", None, ""),
    real("Simian Spirit Guide", "{2}{R}", 3, "Creature — Ape Spirit", "Exile this card from your hand: Add {R}.", ("2", "2"), "R"),
    real("Lotus Petal", "{0}", 0, "Artifact", "{T}, Sacrifice this artifact: Add one mana of any color.", None, ""),
    real("Krosan Tusker", "{5}{G}{G}", 7, "Creature — Boar Beast",
         "Cycling {2}{G} ({2}{G}, Discard this card: Draw a card.)\nWhen you cycle this card, you may search your library for a basic land card, "
         "reveal that card, put it into your hand, then shuffle. (Do this before you draw.)", ("6", "5"), "G"),
    real("Zr Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Zr Giant", "{3}{R}", 4, "Creature — Giant", "", ("5", "5"), "R"),
    real("Zr Sage", "{1}", 1, "Artifact", "{1}: You gain 1 life.", None, ""),
    real("Zr Duo One", "{1}{R}", 2, "Legendary Creature — Human Warrior", "Partner (You can have two commanders if both have partner.)",
         ("2", "2"), "R"),
    real("Zr Duo Two", "{1}{G}", 2, "Legendary Creature — Elf Warrior", "Partner (You can have two commanders if both have partner.)",
         ("2", "2"), "G"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [*NAMES, "Jeweled Lotus"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- helpers ----------------------------------------------------------------------------------------------------------------------------------
def three(cards, mine=(), bobs=(), carols=(), *, commanders=("Krenko, Mob Boss",)):
    """Alice, Bob and Carol; rules on, Alice's first main phase. ``commanders``: Alice's (two: partners)."""
    from app.game.factory import DeckCard, PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, commanders[0], [*((1, n) for n in mine), (10, "Mountain"), (10, "Forest")])
    for extra in commanders[1:]:
        c = cards.resolve(extra)
        alice.insert(1, DeckCard("commander", 1, c["name"], c["id"]))
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bobs), (10, "Island")])
    carol = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in carols), (10, "Island")])
    game = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)], shuffle=False)
    s = GameSession(enable(game), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


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


def decide(s, *wants, limit=60):
    """Resolve everything; each decision takes the options named in ``wants`` (ids or labels) that it offers, else its first option(s)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options if o.id in wants or o.label in wants][: max(1, d.max_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def commander(s, name="Krenko, Mob Boss", pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.commander_key)


def mana_index(s, card):
    return next(i for i, _ in casting.mana_abilities(s.state, s.state.cards[card.id], s.cards))


def pool(s, pid="p1"):
    p = s.state.players[pid]
    out = dict(p.mana)
    for u in p.mana_units:
        out[u.sym] = out.get(u.sym, 0) + 1
    return {k: v for k, v in out.items() if v}


def diamond(s, counters, pid="p1"):
    d = put(s, "Queen's Diamond", pid)
    if counters:
        act(s, pid, type="counter", card_ids=[d.id], kind="charge", delta=counters)
    return d


def tap_diamond(s, d, color="R", pid="p1"):
    act(s, pid, type="activate_ability", card_id=d.id, ability=mana_index(s, d))
    dec = s.state.rules.decision
    if dec is not None:
        act(s, dec.player, type="choose", decision_id=dec.id, option_ids=[next(o.id for o in dec.options if f"{{{color}}}" in o.label)])


# -- Queen's Diamond ----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("casts", [0, 1])
def test_diamond_mana_casts_the_commander_and_pays_its_tax(cards, casts):
    """903.3d: casting your commander is casting a spell that is your commander; 601.2f: the tax is part of its total cost."""
    s = three(cards, ["Queen's Diamond"])
    krenko = commander(s)
    for _ in range(casts):  # (an earlier cast from the command zone: {2} more, 903.8)
        act(s, "p1", type="add_mana", player="p1", mana={"R": 4})
        act(s, "p1", type="cast_spell", card_id=krenko.id)
        answer(s)
        act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "command"})
    d = diamond(s, 4 + 2 * casts)
    tap_diamond(s, d, "R")
    assert pool(s) == {"R": 4 + 2 * casts} and all(u.only == "commander" for u in s.state.players["p1"].mana_units)
    act(s, "p1", type="cast_spell", card_id=krenko.id)
    answer(s)
    assert s.state.cards[krenko.id].zone == "p1:battlefield" and pool(s) == {}
    check(s)


def test_diamond_mana_cant_pay_for_another_spell_or_an_ability(cards):
    """106.6: it pays for nothing but your commander's casting: not another spell, not an activated ability (602.2b), not the commander's own."""
    s = three(cards, ["Queen's Diamond", "Zr Giant", "Zr Sage"])
    sage = put(s, "Zr Sage")
    d = diamond(s, 4)
    tap_diamond(s, d, "R")
    giant = to_hand(s, "Zr Giant")
    assert casting.castable(s.state, "p1", commander(s), s.cards) and not casting.castable(s.state, "p1", giant, s.cards)  # (the hint agrees)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=giant.id)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=sage.id, ability=next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(sage).abilities
                                                                              if a.kind == "activated"))
    assert pool(s) == {"R": 4} and s.state.cards[giant.id].zone == "p1:hand" and life(s) == 40
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1})  # (a plain mana does pay for it: the gain happens)
    act(s, "p1", type="activate_ability", card_id=sage.id, ability=next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(sage).abilities
                                                                          if a.kind == "activated"))
    answer(s)
    assert life(s) == 41 and pool(s) == {"R": 4}
    act(s, "p1", type="cast_spell", card_id=commander(s).id)  # (still there for the commander)
    answer(s)
    assert s.state.cards[commander(s).id].zone == "p1:battlefield"
    check(s)


@pytest.mark.parametrize("which", ["Zr Duo One", "Zr Duo Two"])
def test_diamond_mana_casts_either_of_two_commanders(cards, which):
    """702.124e: with two commanders, "your commander" is either one."""
    s = three(cards, ["Queen's Diamond"], commanders=("Zr Duo One", "Zr Duo Two"))
    d = diamond(s, 2)
    tap_diamond(s, d, "R" if which == "Zr Duo One" else "G")
    c = commander(s, which)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert s.state.cards[c.id].zone == "p1:battlefield" and pool(s) == {}
    check(s)


def test_diamond_mana_casts_the_commander_from_the_hand(cards):
    """903.3: the designation is the card's, kept in every zone: a commander cast from the hand is still your commander."""
    s = three(cards, ["Queen's Diamond"])
    krenko = commander(s)
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "hand"})
    d = diamond(s, 4)
    tap_diamond(s, d, "R")
    act(s, "p1", type="cast_spell", card_id=krenko.id)
    answer(s)
    assert s.state.cards[krenko.id].zone == "p1:battlefield" and pool(s) == {}
    check(s)


def test_your_commander_is_the_payers_own(cards):
    """903.3, 108.3: "your commander" is a commander the player spending the mana owns; another player's commander, or a card that is no
    commander, isn't (and a caller that can't tell the payer never lets it through)."""
    from app.game.rules_state import ObjectRef
    from app.rules import characteristics as chars

    s = three(cards, ["Zr Giant"])
    for owner, name in (("p1", "Krenko, Mob Boss"), ("p2", "Atraxa, Praetors' Voice"), ("p1", "Zr Giant")):
        card = commander(s, name, owner) if name != "Zr Giant" else card_named(s, name)
        purpose = casting.Purpose(spell=chars.of(card, s.cards), zone=card.zone, player="p1",
                                  spell_object=ObjectRef(card=card.id, object_id=s.state.rules.object_id(card.id), zone=card.zone))
        mine = name != "Zr Giant" and owner == "p1"
        assert casting.spend_allowed("commander", purpose, state=s.state, payer="p1") is mine
        assert casting.spend_allowed("commander", purpose, state=s.state, payer="p2") is (owner == "p2" and name != "Zr Giant")
        assert casting.spend_allowed("commander", purpose) is False
    assert casting.spend_allowed("commander", casting.Purpose(ability_of=chars.of(commander(s), s.cards)), state=s.state, payer="p1") is False


def test_diamond_paid_while_casting_the_commander(cards):
    """605.3a: tapped while the commander's cost is being paid (601.2g), the mana then pays it (601.2h)."""
    s = three(cards, ["Queen's Diamond"])
    act(s, "p1", type="set_prefs", payment="self")
    d = diamond(s, 4)
    krenko = commander(s)
    act(s, "p1", type="cast_spell", card_id=krenko.id)
    assert s.state.rules.decision is not None
    tap_diamond(s, d, "R")
    if s.state.cards[krenko.id].zone == "p1:command":
        dec = s.state.rules.decision
        act(s, dec.player, type="choose", decision_id=dec.id, option_ids=["pay"])
    answer(s)
    assert s.state.cards[krenko.id].zone == "p1:battlefield" and pool(s) == {}
    check(s)


@pytest.mark.parametrize("counters", [5, 8])
def test_diamond_stations_then_taps_for_one_mana_per_charge_counter(cards, counters):
    """702.184a: station puts charge counters equal to the tapped creature's power; at 8+ it is an artifact creature with haste (721.2b), so it
    taps for mana the turn it became one (302.6, 702.10b)."""
    s = three(cards, ["Queen's Diamond", "Zr Giant", "Zr Bear"])
    d = put(s, "Queen's Diamond")
    giant = put(s, "Zr Giant")
    index = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(d).abilities if a.text.startswith("Tap another untapped creature"))
    act(s, "p1", type="activate_ability", card_id=d.id, ability=index)
    decide(s, giant.id)
    assert s.state.cards[d.id].counters.get("charge") == 5 and s.state.cards[giant.id].tapped
    if counters == 8:
        act(s, "p1", type="counter", card_ids=[d.id], kind="charge", delta=3)
        dch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[d.id])
        assert dch.is_creature and {"flying", "vigilance", "haste"} <= set(dch.keywords) and dch.pt == (5, 5)
    tap_diamond(s, d, "G")
    assert pool(s) == {"G": counters}
    check(s)


def test_jeweled_lotus_mana_casts_the_commander_only(cards):
    """The same restriction on Jeweled Lotus (banned in Commander; read alike): three mana for the commander, not for another spell."""
    s = three(cards, ["Jeweled Lotus", "Zr Giant"])
    lotus = put(s, "Jeweled Lotus")
    act(s, "p1", type="activate_ability", card_id=lotus.id, ability=mana_index(s, lotus))
    dec = s.state.rules.decision
    if dec is not None:
        act(s, dec.player, type="choose", decision_id=dec.id, option_ids=[next(o.id for o in dec.options if "{R}" in o.label)])
    assert s.state.cards[lotus.id].zone == "p1:graveyard" and pool(s) == {"R": 3}
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    giant = to_hand(s, "Zr Giant")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=giant.id)
    act(s, "p1", type="cast_spell", card_id=commander(s).id)
    answer(s)
    assert s.state.cards[commander(s).id].zone == "p1:battlefield" and pool(s) == {}
    check(s)


# -- Kai Winn ---------------------------------------------------------------------------------------------------------------------------------
def kai(s, named):
    """Alice casts Kai Winn and names ``named`` as it enters (614.12a)."""
    k = to_hand(s, "Kai Winn, Faithless Leader")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 1, "C": 1})
    act(s, "p1", type="cast_spell", card_id=k.id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.options and d.options[0].id == "__name__":
            act(s, "p1", type="choose", decision_id=d.id, name=named)
            break
        act(s, s.state.rules.priority, type="pass_priority")
    answer(s)
    assert s.state.cards[k.id].choices["Chosen card name"] == named
    return k


def watch(s):
    """Every player stops at every priority (so a trigger can be seen on the stack before it resolves)."""
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="set_prefs", response="on", auto_resolve_own_triggers="off")


def turn_of(s, pid):
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "main1", {"p1": 4, "p2": 2, "p3": 3}[pid])
    watch(s)
    assert s.state.rules.priority == pid and s.state.turn.active_player == pid


def lives(s):
    return tuple(life(s, p) for p in ("p1", "p2", "p3"))


def lost(s, before, pid, n=3):
    """The life totals after ``pid`` (alone) lost ``n``."""
    return tuple(v - n if p == pid else v for p, v in zip(("p1", "p2", "p3"), before, strict=True))


def activate(s, card, pid):
    act(s, pid, type="activate_ability", card_id=card.id, ability=mana_index(s, card))


@pytest.mark.parametrize("who", ["p2", "p3"])
def test_kai_winn_a_mana_ability_of_a_named_source_costs_that_opponent_three_life(cards, who):
    """605.1a: a mana ability is activated too (602.1c: "activates an ability", any kind). The trigger isn't a mana ability (605.1b: it adds
    no mana), so it waits until a player would receive priority, then uses the stack (603.3; 605.4a is for triggered mana abilities only).
    "That player" is the one who activated it, not every opponent."""
    s = three(cards, ["Kai Winn, Faithless Leader"], ["Sol Ring"], ["Sol Ring"])
    kai(s, "Sol Ring")
    ring = put(s, "Sol Ring", who)
    turn_of(s, who)
    before = lives(s)
    activate(s, ring, who)
    assert pool(s, who) == {"C": 2} and lives(s) == before
    assert [s.state.rules.stack[i].kind for i in s.state.zones["stack"]] == ["trigger"]
    answer(s)
    assert lives(s) == lost(s, before, who)
    check(s)


def test_kai_winn_ignores_its_controller_and_other_names(cards):
    """"An opponent" (Alice's own named source: nothing); a source with another name: nothing."""
    s = three(cards, ["Kai Winn, Faithless Leader", "Sol Ring"], ["Arcane Signet"])
    kai(s, "Sol Ring")
    watch(s)
    mine = put(s, "Sol Ring")
    signet = put(s, "Arcane Signet", "p2")
    before = lives(s)
    activate(s, mine, "p1")
    assert not s.state.zones.get("stack")
    answer(s)
    turn_of(s, "p2")
    activate(s, signet, "p2")
    assert not s.state.zones.get("stack")
    answer(s)
    assert lives(s) == before
    check(s)


def test_kai_winn_casting_and_activating_are_two_events(cards):
    """603.2c: casting a spell with the chosen name triggers it, and so does each activation of that permanent's ability later."""
    s = three(cards, ["Kai Winn, Faithless Leader"], ["Sol Ring", "Zr Bear"])
    kai(s, "Sol Ring")
    turn_of(s, "p2")
    before = lives(s)
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1})
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Sol Ring", "p2").id)
    answer(s)
    ring = card_named(s, "Sol Ring", "p2")
    assert s.state.cards[ring.id].zone == "p2:battlefield" and lives(s) == lost(s, before, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1, "G": 1})
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Zr Bear", "p2").id)  # (another name: nothing)
    answer(s)
    assert lives(s) == lost(s, before, "p2")
    activate(s, ring, "p2")
    answer(s)
    assert lives(s) == lost(s, before, "p2", 6)
    check(s)


@pytest.mark.parametrize("payment", ["auto", "self"])
def test_kai_winn_mana_tapped_to_cast_a_spell_triggers_once_the_spell_is_cast(cards, payment):
    """601.2g-i: the mana ability is activated while the spell's cost is paid; its trigger waits until the spell has become cast and goes on the
    stack above it (603.3), so it resolves first."""
    s = three(cards, ["Kai Winn, Faithless Leader", "Llanowar Elves"], ["Llanowar Elves", "Zr Bear"])
    kai(s, "Llanowar Elves")
    elves = put(s, "Llanowar Elves", "p2")
    turn_of(s, "p2")
    if payment == "self":
        act(s, "p2", type="set_prefs", payment="self")
    before = lives(s)
    bear = to_hand(s, "Zr Bear", "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1})
    act(s, "p2", type="cast_spell", card_id=bear.id)
    if payment == "self":
        assert s.state.rules.decision is not None and not s.state.zones.get("stack")
        activate(s, elves, "p2")
        if s.state.cards[bear.id].zone == "p2:hand":
            dec = s.state.rules.decision
            act(s, dec.player, type="choose", decision_id=dec.id, option_ids=["pay"])
    assert s.state.cards[elves.id].tapped and lives(s) == before
    stack = s.state.zones["stack"]
    assert stack[0] == bear.id and s.state.rules.stack[stack[-1]].kind == "trigger"
    for _ in range(3):  # (the trigger resolves first: the Bear is still on the stack)
        act(s, s.state.rules.priority, type="pass_priority")
    assert lives(s) == lost(s, before, "p2") and s.state.zones["stack"] == [bear.id]
    answer(s)
    assert s.state.cards[bear.id].zone == "p2:battlefield"
    check(s)


@pytest.mark.parametrize("name", ["Simian Spirit Guide", "Krosan Tusker"])
def test_kai_winn_sees_abilities_of_cards_in_a_hand(cards, name):
    """109.2c: "a source" is in any zone: a Spirit Guide's mana ability (113.6m, 605.3a) and cycling (702.29a) are abilities of a card in a hand."""
    s = three(cards, ["Kai Winn, Faithless Leader"], [name])
    kai(s, name)
    turn_of(s, "p2")
    card = to_hand(s, name, "p2")
    before = lives(s)
    if name == "Simian Spirit Guide":
        index = next(a.index for a in Plan(s.state, "p2", s.cards, None).ch(card).abilities if a.kind == "mana")
        act(s, "p2", type="activate_ability", card_id=card.id, ability=index)
        assert s.state.cards[card.id].zone == "p2:exile" and pool(s, "p2") == {"R": 1}
    else:
        act(s, "p2", type="add_mana", player="p2", mana={"C": 2, "G": 1})
        index = next(a.index for a in Plan(s.state, "p2", s.cards, None).ch(card).abilities if "Cycling" in a.text or "cycling" in a.text)
        act(s, "p2", type="activate_ability", card_id=card.id, ability=index)
        assert s.state.cards[card.id].zone == "p2:graveyard"
    assert any(s.state.rules.stack[i].kind == "trigger" and s.state.rules.stack[i].source_card == card_named(s, "Kai Winn, Faithless Leader").id
               for i in s.state.zones["stack"])
    answer(s)
    assert lives(s) == lost(s, before, "p2")
    check(s)


def test_kai_winn_sees_an_ability_of_a_card_in_a_graveyard(cards):
    """109.2c: unearth (702.84a) is an ability of the card in its owner's graveyard."""
    s = three(cards, ["Kai Winn, Faithless Leader"], ["Test Unearth Golem"])
    kai(s, "Test Unearth Golem")
    turn_of(s, "p2")
    golem = card_named(s, "Test Unearth Golem", "p2")
    act(s, "p2", type="move", card_ids=[golem.id], to={"player": "p2", "zone": "graveyard"})
    before = lives(s)
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1})
    act(s, "p2", type="activate_ability", card_id=golem.id, ability=1)  # (unearth {1})
    answer(s)
    assert s.state.cards[golem.id].zone == "p2:battlefield" and lives(s) == lost(s, before, "p2")
    check(s)


def test_kai_winn_sees_a_source_sacrificed_for_mana(cards):
    """113.7a: the ability is activated though its cost sacrificed the source; the source is read as it last existed (Lotus Petal)."""
    s = three(cards, ["Kai Winn, Faithless Leader"], ["Lotus Petal"])
    kai(s, "Lotus Petal")
    petal = put(s, "Lotus Petal", "p2")
    turn_of(s, "p2")
    before = lives(s)
    act(s, "p2", type="activate_ability", card_id=petal.id, ability=mana_index(s, petal))
    answer(s)
    assert s.state.cards[petal.id].zone == "p2:graveyard" and lives(s) == lost(s, before, "p2")
    check(s)


def test_kai_winn_a_special_action_is_no_activation_but_the_later_cast_is_a_cast(cards):
    """116.2f: suspending a card is a special action, not an ability's activation (nothing); 702.62a: casting it as the last time counter is
    removed is casting a spell with that name (603.2: that triggers it)."""
    from tests.test_rules_conditionals import until

    s = three(cards, ["Kai Winn, Faithless Leader"], ["Rift Bolt"])
    kai(s, "Rift Bolt")
    turn_of(s, "p2")
    bolt = to_hand(s, "Rift Bolt", "p2")
    before = lives(s)
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1})
    act(s, "p2", type="activate_ability", card_id=bolt.id, ability=1)  # "Suspend 1—{R}"
    assert s.state.cards[bolt.id].zone == "p2:exile" and not s.state.zones.get("stack")
    answer(s)
    assert lives(s) == before
    until(s, lambda s: (d := s.state.rules.decision) is not None and (d.resume or {}).get("step") == "suspend_cast", limit=400)  # (Bob's next upkeep)
    assert s.state.turn.number == 5
    d = s.state.rules.decision
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["yes"])
    d = s.state.rules.decision
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["p3"])
    answer(s)
    assert s.state.cards[bolt.id].zone == "p2:graveyard" and lives(s) == (before[0], before[1] - 3, before[2] - 3)
    check(s)
