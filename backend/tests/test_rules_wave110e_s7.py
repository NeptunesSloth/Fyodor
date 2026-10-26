"""Wave 110E session 7: untested branches of Mirror Match and Coward.

* Mirror Match: 508.5 / 509.4 an attacker of a planeswalker the caster controls gets a blocking copy too; 509.3d each copy that is put onto the
  battlefield blocking triggers "becomes blocked by a creature" of its original; "blocks" abilities do not (509.3b).
* Coward: 509.1b the target cannot be declared as a blocker.
"""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
import tests.test_rules_wave110e_s6  # noqa: F401  (registers the cards)
from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import card_db  # noqa: F401  (the fixture)

TARDIS = real("Start the TARDIS", "{1}{U}", 2, "Instant",
              "Surveil 2, then draw a card. You may planeswalk. (To surveil 2, look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\n"
              "Jump-start (You may cast this card from your graveyard by discarding a card in addition to paying its other costs. Then exile this card.)", None, "U")
GAMBIT = real("Decoy Gambit", "{1}{1}{U}", 3, "Instant",
              "For each opponent, choose up to one target creature that player controls, then return that creature to its owner's hand unless its controller has you draw a card.", None, "U")
SUPPER = real("Supper for Spiders", "{1}{B}", 2, "Instant",
              "Put onto the battlefield under your control all creature cards in your opponents' graveyards that were put there from the battlefield this turn. "
              "They are Food artifacts with \"{2}, {T}, Sacrifice this artifact: You gain 3 life.\" (They lose all other types and subtypes.)", None, "B")
DELIVER = real("Deliver Unto Evil", "{2}{B}", 3, "Sorcery",
               "Choose up to four target cards in your graveyard. If you control a Bolas planeswalker, return those cards to your hand. Otherwise, an opponent chooses two of them. "
               "Leave the chosen cards in your graveyard and put the rest into your hand.\nExile Deliver Unto Evil.", None, "B")
BOLAS = real("Test Bolas", "{2}", 2, "Legendary Planeswalker — Bolas", "+1: You gain 1 life.", None, "")
HEAD = real("Head Games", "{3}{B}{B}", 5, "Sorcery",
            "Target opponent puts the cards from their hand on top of their library. Search that player's library for that many cards. "
            "The player puts those cards into their hand, then shuffles.", None, "B")
BRAWL = real("Barroom Brawl", "{1}{G}", 2, "Sorcery",
             "Target creature you control fights target creature the opponent to your left controls. Then that player may copy this spell and may choose new targets for the copy.", None, "G")
WALKER = real("Test Walker", "{2}", 2, "Planeswalker — Test", "+1: You gain 1 life.", None, "")
base.EXTRA.extend([WALKER, TARDIS, GAMBIT, SUPPER, DELIVER, BOLAS, HEAD, BRAWL])


def _setup(cards, mm=True):
    from tests.wave53c_kit import sandbox

    return sandbox(cards, p2=("Mirror Match", "Test Walker") if mm else ("Coward", "Test Walker"))


def _cast_mirror(s):
    from tests.wave53c_kit import in_play, pool, priority_to, settle

    mm = in_play(s, "Mirror Match", "p2")
    act(s, "p2", type="move", card_ids=[mm.id], to={"zone": "hand"})
    pool(s, "p2", U=2, C=4)
    priority_to(s, "p2")
    act(s, "p2", type="cast_spell", card_id=mm.id)
    settle(s)


@pytest.mark.parametrize("at_walker", [False, True])
def test_mirror_match_copies_attackers_of_a_planeswalker_you_control(cards, at_walker):
    """508.5: an attacker of Bob's planeswalker is "attacking a planeswalker you control": copied; with 0 blockers declared, the walker is not hurt."""
    from tests.test_rules_conditionals import creature
    from tests.test_rules_group_unblocked import finish_combat
    from tests.wave53c_kit import combat_step, in_play, swing

    s = _setup(cards)
    pw = in_play(s, "Test Walker", "p2")
    act(s, "p2", type="move", card_ids=[pw.id], to={"zone": "battlefield"})
    act(s, "p2", type="set_counter", card_id=pw.id, kind="loyalty", value=5)
    a = creature(s, "p1", "Aaa", "3/9")
    creature(s, "p2", "Guard", "0/9")
    combat_step(s)
    swing(s, [a], [], target=pw.id if at_walker else "p2", before=None)
    _cast_mirror(s)
    copies = [c for c in s.state.cards.values() if c.name == "Aaa" and c.controller == "p2" and c.zone == "p2:battlefield"]
    assert len(copies) == 1 and copies[0].blocking is not None
    finish_combat(s)
    assert s.state.players["p2"].life == 40 and s.state.cards[pw.id].counters.get("loyalty") == 5
    from tests.wave9c_kit import check
    check(s)


def test_mirror_match_ignores_attackers_of_a_third_player(cards):
    """Attackers that attack neither Bob nor his planeswalkers are not copied."""
    from tests.test_rules_conditionals import creature, sandbox
    from tests.wave53c_kit import combat_step, swing

    s = sandbox(cards, p2=("Mirror Match",), players=3)
    a = creature(s, "p1", "Aaa", "3/9")
    creature(s, "p3", "Guard", "0/9")
    combat_step(s)
    swing(s, [a], [], opp="p3", before=None)
    _cast_mirror(s)
    assert not [c for c in s.state.cards.values() if c.name == "Aaa" and c.controller == "p2"]


def test_mirror_match_copy_putting_onto_battlefield_blocking_triggers_becomes_blocked_by_a_creature(cards):
    """509.3d: the original's "becomes blocked by a creature" triggers once for the copy put onto the battlefield blocking it."""
    from tests.test_rules_conditionals import creature
    from tests.test_rules_group_unblocked import finish_combat
    from tests.wave53c_kit import combat_step, swing

    s = _setup(cards)
    a = creature(s, "p1", "Aaa", "3/9", text="Whenever Aaa becomes blocked by a creature, you gain 1 life.\nWhenever Aaa blocks a creature, you gain 10 life.")
    creature(s, "p2", "Guard", "0/9")
    combat_step(s)
    swing(s, [a], [], before=None)
    life = s.state.players["p1"].life
    _cast_mirror(s)
    assert s.state.players["p1"].life == life + 1  # (the copy's own "blocks" ability does not trigger, 509.3b)
    finish_combat(s)


def test_coward_target_cannot_be_declared_as_a_blocker(cards):
    """509.1b: a creature that can't block is not a legal blocker."""
    from tests.test_rules_conditionals import creature
    from tests.wave53c_kit import combat_step, in_play, pool, priority_to, settle

    s = _setup(cards, mm=False)
    a = creature(s, "p1", "Aaa", "3/3")
    guard = creature(s, "p2", "Guard", "0/9")
    combat_step(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"}])
    cw = in_play(s, "Coward", "p2")
    act(s, "p2", type="move", card_ids=[cw.id], to={"zone": "hand"})
    pool(s, "p2", R=1, C=1)
    priority_to(s, "p2")
    act(s, "p2", type="cast_spell", card_id=cw.id, targets=[guard.id])
    settle(s)
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            with pytest.raises(ActionError):
                act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": guard.id, "attacker_id": a.id}])
            act(s, "p2", type="declare_blockers", blocks=[])
            return
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no blockers asked")


def _answer(s, picks):
    """Resolve everything; ``picks`` maps a player to the option id ("pay" = Yes) they choose, else the first option."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[picks.get(d.player, d.options[0].id)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def _gambit(cards, p2_draw, p3_draw):
    """Decoy Gambit with one creature of each opponent; each controller answers whether the caster draws (608.2c, 608.2d)."""
    from tests.game_helpers import turn_on
    from tests.test_rules_conditionals import creature, sandbox
    from tests.wave53c_kit import in_play, pool, priority_to

    s = sandbox(cards, "Decoy Gambit", players=3)
    turn_on(s)
    a, b = creature(s, "p2", "Aaa", "1/1"), creature(s, "p3", "Bbb", "1/1")
    g = in_play(s, "Decoy Gambit", "p1")
    act(s, "p1", type="move", card_ids=[g.id], to={"zone": "hand"})
    pool(s, "p1", U=1, C=2)
    priority_to(s, "p1")
    act(s, "p1", type="cast_spell", card_id=g.id, targets=[a.id, b.id], target_counts=[1, 1])
    _answer(s, {"p2": "pay" if p2_draw else "decline", "p3": "pay" if p3_draw else "decline"})
    return s, a, b, sum(1 for l in s.state.log if l.phase != "draw" and any("drew" in (p.t or "") for p in l.parts))


@pytest.mark.parametrize("p2_draw,p3_draw", [(True, False), (False, True), (True, True), (False, False)])
def test_decoy_gambit_each_controller_chooses_between_the_draw_and_the_bounce(cards, p2_draw, p3_draw):
    """608.2c: each chosen creature returns unless its own controller has the caster draw; one draw per such answer."""
    from tests.wave9c_kit import check

    s, a, b, drawn = _gambit(cards, p2_draw, p3_draw)
    alive = lambda c: c.id in s.state.cards and s.state.cards[c.id].zone.endswith(":battlefield")  # noqa: E731  (a bounced token ceases to exist, 111.7)
    assert (alive(a), alive(b)) == (p2_draw, p3_draw), drawn
    assert drawn == p2_draw + p3_draw
    check(s)


def test_start_the_tardis_surveils_then_draws_and_planeswalking_does_nothing(cards):
    """701.31a: no Planechase game, so "you may planeswalk" is nothing; 701.25 surveil 2 then 121.2 draw."""
    from tests.test_rules_wave110e_cards import answer, cast
    from tests.wave9c_kit import build, check, mana

    s = build(cards, ["Start the TARDIS"], forests=30, islands=30)
    mana(s, U=1, C=3)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Start the TARDIS")
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (the card was cast from a hand it was put in: +1 -1 +1)
    check(s)


def test_supper_for_spiders_takes_only_creatures_that_died_this_turn_as_food_artifacts(cards):
    """400.7 + 205.1a/613.1d: creature cards put into an opponent's graveyard from the battlefield this turn come back under your control as
    Food artifacts that are no longer creatures (nor Bears); a creature card that was not on the battlefield stays; the granted ability works."""
    from app.rules.plan import Plan
    from tests.test_rules_wave110e_cards import answer, cast
    from tests.wave9c_kit import build, check, mana, put

    s = build(cards, ["Supper for Spiders"], ["Grizzly Bears", "Test Shifter"], forests=30, islands=30)
    bears, crow = put(s, "Grizzly Bears", "p2"), next(c for c in s.state.cards.values() if c.name == "Test Shifter" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[crow.id], to={"player": "p2", "zone": "graveyard"})  # (from the library: not from the battlefield)
    mana(s, B=1, C=1)
    cast(s, "Supper for Spiders")
    answer(s)
    c = s.state.cards[bears.id] if s.state.cards[bears.id].zone.endswith(":battlefield") else next(x for x in s.state.cards.values() if x.name == "Grizzly Bears" and x.zone.endswith(":battlefield"))
    ch = Plan(s.state, "p1", s.cards, None).ch(c)
    assert c.controller == "p1" and ch.types == {"Artifact"} and ch.subtypes == {"Food"} and not ch.is_creature
    assert s.state.cards[crow.id].zone == "p2:graveyard"
    life = s.state.players["p1"].life
    mana(s, C=2)
    ab = next(a.index for a in ch.abilities if "Sacrifice this artifact" in a.text)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ab)
    answer(s)
    assert s.state.players["p1"].life == life + 3
    check(s)


@pytest.mark.parametrize("bolas,n", [(True, 4), (False, 4), (False, 1)])
def test_deliver_unto_evil_all_return_with_a_bolas_otherwise_an_opponent_keeps_two_in_the_graveyard(cards, bolas, n):
    """608.2c: Bolas planeswalker: all targeted cards go to hand; otherwise the opponent chooses two (fewer targeted: all of them) that stay;
    the rest go to hand. The spell is exiled (it never reaches the graveyard)."""
    from tests.test_rules_wave110e_cards import answer, cast
    from tests.wave9c_kit import build, check, mana, put

    s = build(cards, ["Deliver Unto Evil", "Test Bolas"], forests=30, islands=30)
    if bolas:
        w = put(s, "Test Bolas")
        act(s, "p1", type="set_counter", card_id=w.id, kind="loyalty", value=3)
    gy_cards = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:4]
    act(s, "p1", type="move", card_ids=[c.id for c in gy_cards], to={"player": "p1", "zone": "graveyard"})
    targets = [c.id for c in gy_cards[:n]]
    mana(s, B=1, C=2)
    spell = cast(s, "Deliver Unto Evil", targets, target_counts=[n])
    keep = [] if bolas else targets[:2]
    d = None
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        assert d.player == "p2"
        act(s, "p2", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.id in keep] or [o.id for o in d.options][: max(1, d.min_choices)])
    answer(s)
    where = [s.state.cards[t].zone for t in targets]
    assert where.count("p1:graveyard") == (0 if bolas else min(2, n)) and where.count("p1:hand") == (n if bolas else n - min(2, n))
    assert s.state.cards[spell.id].zone == "p1:exile"
    check(s)


@pytest.mark.parametrize("n", [0, 2])
def test_head_games_the_hand_goes_on_top_and_you_choose_that_many_cards_into_their_hand(cards, n):
    """701.23/608.2c: the target's hand (n cards) goes on top of their library, you search it for that many cards, which they put in their hand; then it is shuffled."""
    from tests.test_rules_wave110e_cards import answer, cast
    from tests.wave9c_kit import build, check, mana

    s = build(cards, ["Head Games"], ["Grizzly Bears", "Test Shifter"], forests=30, islands=30)
    assert not s.state.zones.get("p2:hand")
    islands = [c for c in s.state.zones["p2:library"] if s.state.cards[c].name == "Island"][:n]
    if n:
        act(s, "p2", type="move", card_ids=islands, to={"player": "p2", "zone": "hand"})
    want = [c.id for c in s.state.cards.values() if c.owner == "p2" and c.name in ("Grizzly Bears", "Test Shifter")][:n]
    mana(s, B=2, C=3)
    cast(s, "Head Games", ["p2"])
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        pick = [o.id for o in d.options if o.id in want] if d.player == "p1" else [o.id for o in d.options]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick if d.player == "p1" else pick or [d.options[0].id])
    answer(s)
    names = sorted(s.state.cards[c].name for c in s.state.zones["p2:hand"])
    assert names == (["Grizzly Bears", "Test Shifter"] if n else []) and sum(s.state.cards[c].name == "Island" for c in s.state.zones["p2:library"]) == 30
    check(s)


def _brawl(cards, targets_of, copy):
    """Alice (p1), Bob (p2, to her left), Carol (p3): Alice's Aaa 3/3 fights; ``copy`` = what Bob answers (None: declines)."""
    from tests.game_helpers import turn_on
    from tests.test_rules_conditionals import creature, sandbox
    from tests.wave53c_kit import in_play, pool, priority_to

    s = sandbox(cards, "Barroom Brawl", players=3)
    turn_on(s)
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "main1", 1)
    a, b, c = creature(s, "p1", "Aaa", "3/3"), creature(s, "p2", "Bbb", "1/9"), creature(s, "p3", "Ccc", "1/9")
    g = in_play(s, "Barroom Brawl", "p1")
    act(s, "p1", type="move", card_ids=[g.id], to={"zone": "hand"})
    pool(s, "p1", G=1, C=1)
    priority_to(s, "p1")
    act(s, "p1", type="cast_spell", card_id=g.id, targets=[a.id, {"b": b.id, "c": c.id}[targets_of]], target_counts=[1, 1])
    return s, a, b, c


def test_barroom_brawl_only_the_creature_of_the_opponent_to_the_left_is_a_legal_second_target(cards):
    """Turn order goes to the left: Bob follows Alice, so Carol's creature is not a legal target."""
    with pytest.raises(ActionError):
        _brawl(cards, "c", None)


@pytest.mark.parametrize("copy", [False, True])
def test_barroom_brawl_fights_then_the_player_to_the_left_may_copy_it_with_new_targets(cards, copy):
    """701.14 fight; 707.10 the copy is Bob's: his creature fights the creature of the opponent to HIS left (Carol's); he may decline."""
    from tests.wave9c_kit import check

    s, a, b, c = _brawl(cards, "b", None)
    for _ in range(30):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        pick = [o.id for o in d.options if o.id == ("pay" if copy and d.player == "p2" else "decline")] or [o.id for o in d.options if o.id != "keep"]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick or [d.options[0].id])
    # (Aaa deals 3 to Bbb and takes 1; the copy: Bbb deals 1 to Ccc and takes 1 from it)
    assert (s.state.cards[b.id].damage, s.state.cards[c.id].damage, s.state.cards[a.id].damage) == ((4, 1, 1) if copy else (3, 0, 1))
    check(s)
