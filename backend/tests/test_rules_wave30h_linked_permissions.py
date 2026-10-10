"""Wave 30H: static permissions over "cards exiled with ~" and replacement effects that exile them (CR 2026-09-25), real Oracle text
(tests/fixtures/wave30h_linked_exile_cards.json). Every scenario checks the replay and a save and a load.

* 607.2a/b: the cards a linked ability (Rona's triggers, Hedonist's Trove's, Pick Up the Pace's) or a linked replacement effect (Valgavoth's)
  put in exile are the ones "exiled with" the permanent, each while it is still that object there (400.7); a permanent that left and
  came back is a new object with none of them.
* 601.3, 305.1: the permission is only to cast or play them, with the normal timing; "cast spells" is not "play lands".
* Rulings: Hedonist's Trove's one spell a turn; Pick Up the Pace's "as long as you attacked this turn"; Valgavoth's life payment is an
  alternative cost (118.9, 119.4) the permission always requires.
"""

from __future__ import annotations

from app.rules import view

import pytest

from app.game.errors import ActionError
from app.rules.casting import castable, free_castable
from tests.game_helpers import act
from tests.test_rules_wave30h_linked_exile import card_db, put_in, settle, to_turn, zone  # noqa: F401
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand


def cast(s, name, pid="p1", owner=None, **kw):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, owner or pid).id, **kw)
    settle(s)


def test_rona_may_cast_spells_but_not_play_lands_from_among_the_cards_exiled_with_it(cards):
    """"You may cast spells from among cards exiled with Rona." Its ETB trigger exiles a historic card from the graveyard and its {4},{T}
    ability the top card of the library; only those (not Bonesplitter, exiled some other way) can be cast, and a land among them can't be played."""
    s = build(cards, ["Rona, Disciple of Gix", "Sol Ring", "Bonesplitter", "Rampant Growth", "Command Tower"])
    put_in(s, "Sol Ring", "graveyard")
    put_in(s, "Bonesplitter", "exile")
    to_hand(s, "Rona, Disciple of Gix")
    mana(s, U=1, B=1, C=1)
    cast(s, "Rona, Disciple of Gix")
    settle(s, prefer=("Sol Ring", "yes"))
    ring, rona = card_named(s, "Sol Ring"), card_named(s, "Rona, Disciple of Gix")
    assert ring.zone == "p1:exile" and not castable(s.state, "p1", ring, cards)  # (no mana yet: {1})
    to_turn(s, 3)
    put_in(s, "Command Tower", "library", position="top")
    mana(s, C=5)
    act(s, "p1", type="activate_ability", card_id=rona.id, ability=2)
    settle(s)
    tower = card_named(s, "Command Tower")
    assert tower.zone == "p1:exile"
    assert castable(s.state, "p1", ring, cards) and not castable(s.state, "p1", card_named(s, "Bonesplitter"), cards)
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=tower.id)  # (spells only: 305.1 isn't granted)
    check(s)
    # 607.2a + 400.7: the Rona that left and came back is a new object; nothing is exiled with it
    put_in(s, "Rona, Disciple of Gix", "hand")
    put_in(s, "Rona, Disciple of Gix", "battlefield")
    assert not castable(s.state, "p1", ring, cards)
    check(s)


def test_hedonists_trove_plays_lands_and_casts_one_spell_a_turn_from_the_opponents_exiled_graveyard(cards):
    """Two statics over the cards the ETB trigger exiled from Bob's graveyard: "You may play lands …" and "You may cast spells … You can't cast
    more than one spell this way each turn." Bob's cards, cast by Alice; the land is still playable the turn a spell was cast."""
    s = build(cards, ["Hedonist's Trove", "Mountain"], ["Grizzly Bears", "Rampant Growth", "Murder"])
    for name in ("Grizzly Bears", "Rampant Growth", "Island"):
        put_in(s, name, "graveyard", "p2")
    to_hand(s, "Hedonist's Trove")
    mana(s, B=2, C=5)
    cast(s, "Hedonist's Trove")
    settle(s, prefer=("p2",))
    assert zone(s, "p2", "exile") == ["Grizzly Bears", "Island", "Rampant Growth"] and not zone(s, "p2", "graveyard")
    bears, growth, island = card_named(s, "Grizzly Bears", "p2"), card_named(s, "Rampant Growth", "p2"), card_named(s, "Island", "p2")
    mana(s, G=2)
    assert castable(s.state, "p1", bears, cards) and castable(s.state, "p1", growth, cards)
    cast(s, "Grizzly Bears", owner="p2")
    assert card_named(s, "Grizzly Bears", "p2").zone == "p1:battlefield"  # (under Alice's control, it is Bob's card)
    mana(s, G=2)
    assert not castable(s.state, "p1", growth, cards)  # one spell this way each turn
    act(s, "p1", type="play_land", card_id=island.id)  # (the land is a different permission)
    assert card_named(s, "Island", "p2").zone == "p1:battlefield"
    check(s)
    to_turn(s, 3)
    mana(s, G=2)
    assert castable(s.state, "p1", growth, cards)  # a new turn
    check(s)
    # 607.2a + 400.7: the Trove that left and came back has exiled nothing
    put_in(s, "Hedonist's Trove", "hand")
    put_in(s, "Hedonist's Trove", "battlefield")
    assert not castable(s.state, "p1", growth, cards)
    check(s)


def test_pick_up_the_pace_plays_the_exiled_cards_only_in_a_turn_you_attacked(cards):
    """"You may play cards exiled with this enchantment as long as you attacked this turn." (611.3a: read whenever the play is offered.)
    The haste creature that entered this turn attacks, the trigger exiles the top card; it can be cast after the attack, not before it, and
    not in a turn without one."""
    s = build(cards, ["Pick Up the Pace", "Monastery Swiftspear", "Rampant Growth", "Mountain"])
    put(s, "Pick Up the Pace")
    put_in(s, "Rampant Growth", "library", position="top")
    spear = put(s, "Monastery Swiftspear")
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": spear.id, "target": "p2"}])
    settle(s)
    growth = card_named(s, "Rampant Growth")
    assert growth.zone == "p1:exile"
    to_turn_main2(s)
    mana(s, G=2)
    assert castable(s.state, "p1", growth, cards)  # (it attacked this turn)
    check(s)
    to_turn(s, 3)
    mana(s, G=2)
    assert not castable(s.state, "p1", card_named(s, "Rampant Growth"), cards)  # no attack yet this turn
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": spear.id, "target": "p2"}])
    settle(s)
    to_turn_main2(s)
    mana(s, G=2)
    assert castable(s.state, "p1", card_named(s, "Rampant Growth"), cards)
    check(s)
    # 607.2a + 400.7: the Rampant Growth put into exile again is a new object
    put_in(s, "Rampant Growth", "graveyard")
    put_in(s, "Rampant Growth", "exile")
    assert not castable(s.state, "p1", card_named(s, "Rampant Growth"), cards)
    check(s)


def to_turn_main2(s):
    """Pass priority until the second main phase of this turn."""
    for _ in range(40):
        if s.state.turn.phase == "main2" and not s.state.rules.decision:
            return
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got there")


def valgavoth_game(cards):
    s = build(cards, ["Valgavoth, Terror Eater", "Lightning Bolt", "Llanowar Elves", "Mountain"], ["Grizzly Bears", "Merfolk Looter", "Giant Growth", "Island"])
    put(s, "Valgavoth, Terror Eater")
    return s


def test_valgavoth_exiles_what_would_go_to_an_opponents_graveyard_and_lets_you_play_it_for_life(cards):
    """607.2b: "If a card you didn't control would be put into an opponent's graveyard from anywhere, exile it instead." links to "During your
    turn, you may play cards exiled with Valgavoth. If you cast a spell this way, pay life equal to its mana value rather than pay its mana
    cost." (118.9, 119.4: an alternative cost the permission always requires - the mana cost can't be paid instead.)"""
    s = valgavoth_game(cards)
    bears = put(s, "Grizzly Bears", "p2")
    put(s, "Merfolk Looter", "p2")
    elves = put(s, "Llanowar Elves")
    to_hand(s, "Lightning Bolt")
    to_hand(s, "Island", "p2")
    for victim in (bears.id, elves.id):  # Bob's creature dies; so does Alice's own
        mana(s, R=1)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=[victim])
        settle(s)
        to_hand(s, "Lightning Bolt") if victim == bears.id else None  # (the same Bolt again)
    assert zone(s, "p2", "exile") == ["Grizzly Bears"] and zone(s, "p2", "graveyard") == []  # (a card Bob owns and controlled, exiled instead)
    assert zone(s, "p1", "graveyard") == ["Lightning Bolt", "Llanowar Elves"]  # (Alice's own cards go to her own graveyard as ever)
    check(s)
    to_turn(s, 2)  # Bob's turn: his Looter discards the Island (from a hand: "from anywhere")
    act(s, "p2", type="activate_ability", card_id=card_named(s, "Merfolk Looter", "p2").id, ability=0)
    settle(s, prefer=("Island",))
    assert zone(s, "p2", "exile") == ["Grizzly Bears", "Island"], zone(s, "p2", "exile")
    assert not free_castable(s.state, "p1", card_named(s, "Grizzly Bears", "p2"), cards)  # (not during Alice's turn)
    to_turn(s, 3)
    bears = card_named(s, "Grizzly Bears", "p2")
    assert free_castable(s.state, "p1", bears, cards) and not castable(s.state, "p1", bears, cards)  # (never for its mana cost)
    # (review 30: the hints of the player allowed to cast it list it, though it is in Bob's exile; Bob's don't)
    assert bears.id in view.hints(s.state, "p1", cards).get("free_castable", []) and "Island" in [
        s.state.cards[c].name for c in view.hints(s.state, "p1", cards).get("playable_lands", [])]
    life = s.state.players["p1"].life
    check(s)
    act(s, "p1", type="cast_spell", card_id=bears.id, free=True)
    settle(s)
    assert card_named(s, "Grizzly Bears", "p2").zone == "p1:battlefield" and s.state.players["p1"].life == life - 2  # (mana value 2)
    act(s, "p1", type="play_land", card_id=card_named(s, "Island", "p2").id)  # a land: just played
    assert card_named(s, "Island", "p2").zone == "p1:battlefield"
    check(s)
    # 607.2b + 400.7: the Valgavoth that left and came back is a new object; what the old one exiled is not exiled with it
    put_in(s, "Giant Growth", "exile", "p2")
    put_in(s, "Valgavoth, Terror Eater", "hand")
    put_in(s, "Valgavoth, Terror Eater", "battlefield")
    assert not free_castable(s.state, "p1", card_named(s, "Giant Growth", "p2"), cards)
    check(s)


# -- reading the names of the exiled cards: Circu, Exclusion Ritual ----------------------------------------------------------------------------------
def prohibited(s, cards, pid, name, owner=None):
    """Why a rule or effect forbids ``pid`` to cast that card now (601.3), or None."""
    from app.rules import cast_limits
    from app.rules.characteristics import of

    c = card_named(s, name, owner or pid)
    return cast_limits.cast_problem(s.state, pid, c, of(c, cards), cards)


def test_circu_stops_opponents_casting_the_names_of_the_cards_it_exiled_from_any_library(cards):
    """201.2a + 607.2a: "Your opponents can't cast spells with the same name as a card exiled with Circu." Its two triggers feed one set (the
    Rona ruling's shape), the card may come from any player's library, and a Circu that came back has exiled nothing."""
    s = build(cards, ["Circu, Dimir Lobotomist", "Opt", "Lightning Bolt", "Counterspell"], ["Lightning Bolt", "Counterspell", "Murder"])
    put(s, "Circu, Dimir Lobotomist")
    assert prohibited(s, cards, "p2", "Lightning Bolt") is None
    for who, name in (("p1", "Lightning Bolt"), ("p2", "Counterspell")):  # a blue spell, aimed at a library
        put_in(s, name, "library", who, position="top")
        put_in(s, "Opt", "hand")
        mana(s, U=1)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Opt").id)
        settle(s, prefer=(who,))
        assert zone(s, who, "exile") == [name]
    assert "Circu" in prohibited(s, cards, "p2", "Lightning Bolt") and "Circu" in prohibited(s, cards, "p2", "Counterspell")
    assert prohibited(s, cards, "p2", "Murder") is None  # (another name)
    assert prohibited(s, cards, "p1", "Counterspell") is None and prohibited(s, cards, "p1", "Lightning Bolt") is None  # (only her opponents)
    check(s)
    put_in(s, "Circu, Dimir Lobotomist", "hand")
    put_in(s, "Circu, Dimir Lobotomist", "battlefield")
    assert prohibited(s, cards, "p2", "Lightning Bolt") is None and prohibited(s, cards, "p2", "Counterspell") is None
    check(s)


def test_exclusion_ritual_stops_every_player_casting_the_exiled_cards_name(cards):
    """"Players can't cast spells with the same name as the exiled card." While the Sol Ring is exiled with the Ritual, both players are barred
    from its name; put into a hand it is a new object (400.7), no longer exiled with the Ritual, and the name is free again."""
    s = build(cards, ["Exclusion Ritual", "Sol Ring", "Lightning Bolt"], ["Sol Ring", "Lightning Bolt"])
    ring = put(s, "Sol Ring")
    to_hand(s, "Exclusion Ritual")
    mana(s, W=2, C=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Exclusion Ritual").id)
    settle(s, prefer=(ring.id,))
    assert zone(s, "p1", "exile") == ["Sol Ring"]
    assert "Exclusion Ritual" in prohibited(s, cards, "p2", "Sol Ring") and prohibited(s, cards, "p2", "Lightning Bolt") is None
    check(s)
    put_in(s, "Sol Ring", "hand")  # (the exiled card left exile: a new object, no longer exiled with the Ritual)
    assert prohibited(s, cards, "p2", "Sol Ring") is None and prohibited(s, cards, "p1", "Sol Ring") is None
    check(s)


@pytest.mark.parametrize("pick", ["Valgavoth, Terror Eater", "Rest in Peace"])
def test_the_replacement_that_applies_decides_whether_the_card_is_exiled_with_valgavoth(cards, pick):
    """607.2b + 616.1: with Rest in Peace also on the table, Bob (the creature's controller) chooses which "exile it instead" applies. Only the card
    Valgavoth's own effect exiled is "exiled with" it (the Gisa ruling: "If the creature is exiled due to some other replacement effect, it
    will not be returned")."""
    s = build(cards, ["Valgavoth, Terror Eater", "Rest in Peace", "Lightning Bolt"], ["Grizzly Bears"])
    put(s, "Valgavoth, Terror Eater")
    put(s, "Rest in Peace")
    bears = put(s, "Grizzly Bears", "p2")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=[bears.id])
    for _ in range(20):  # (Bob is asked which replacement effect applies first: the options are "<source>: Exile it")
        d = s.state.rules.decision
        if d is not None:
            assert d.player == "p2" and "which replacement effect applies first" in d.prompt, d
            act(s, "p2", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.label.startswith(pick)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.rules.decision is None and zone(s, "p2", "exile") == ["Grizzly Bears"], zone(s, "p2", "graveyard")
    assert free_castable(s.state, "p1", card_named(s, "Grizzly Bears", "p2"), cards) is (pick == "Valgavoth, Terror Eater")
    check(s)
