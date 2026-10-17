"""Wave 50G: commanders blocked by exactly two lines, real Oracle text (tests/fixtures/wave50g_cards.json, from data/cards.sqlite). Every scenario checks the
replay and a save and a load (tests/wave9c_kit.check).

* Kenessos, Priest of Thassa: 614.1a, 701.22 "If you would scry a number of cards, scry that many cards plus one instead" (the scry itself, one card deeper; scrying 0 is no
  scry, 701.22b); "If it's a Kraken, Leviathan, Octopus, or Serpent creature card" (a list of kinds, the commas don't end the condition).
* Maralen of the Mornsong: 121.2, 101.2 "Players can't draw cards" (also the draw step's turn-based draw and a draw that is a cost or a replacement's); "that player loses 3
  life, searches their library for a card, puts it into their hand, then shuffles" (701.23).
* Tetsuo Umezawa: 115.2 "can't be the target of Aura spells" (an ability still may); "target tapped or blocking creature".
* Valentina Allegra de Fontaine: "Other Villains you control are Heroes in addition to their other types" (613.1d); "Target Hero you control connives" (701.50).
* Anje, Maid of Dishonor: 603.2c "Whenever Anje and/or one or more other Vampires you control enter" is one trigger for a batch; "Sacrifice another creature or a Blood token".
* Hakbal of the Surging Soul: 701.44a "each Merfolk creature you control explores" in the order its controller chooses (2023-11-10 ruling); "If you don't" after a
  "you may put a land card from your hand onto the battlefield" (608.2c, 118.12).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import ch
from tests.test_rules_conditionals import settle, until
from tests.test_rules_wave39b_trigger_damage import attack, finish_turn, to_main1
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50g_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t50g", number=f"G{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Kenessos, Priest of Thassa", "Maralen of the Mornsong", "Tetsuo Umezawa", "Bartel Runeaxe", "Valentina Allegra de Fontaine",
        "Anje, Maid of Dishonor", "Hakbal of the Surging Soul", "Tamiyo, Inquisitive Student // Tamiyo, Seasoned Scholar", "Sneaky Snacker"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_the_promoted_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def stack_top(s, names, pid="p1"):
    """Put these cards on top of the library, the first named on top."""
    for name in reversed(names):
        c = card_named(s, name, pid)
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")


def top(s, pid="p1"):
    return s.state.cards[s.state.zones[f"{pid}:library"][0]].name


def ability(s, c, contains):
    return next(a.index for a in ch(s, c).abilities if a.kind in ("activated", "loyalty") and contains in a.text)


def answer(s, pick=None):
    """Answer the open decision with the option whose label contains ``pick`` (the first option if None); returns its prompt."""
    d = s.state.rules.decision
    ids = [o.id for o in d.options if pick is None or pick in o.label][:1] if pick != [] else []
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    return d.prompt


def on_battlefield(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith(":battlefield")]


# -- Kenessos, Priest of Thassa ----------------------------------------------------------------------------------------------------------------------
def scry_prompt(s, with_kenessos):
    s2 = s
    if with_kenessos:
        put(s2, "Kenessos, Priest of Thassa")
    stack_top(s2, ["Grizzly Bears", "Llanowar Elves", "Holy Strength"])
    mana(s2, "p1", U=1)
    act(s2, "p1", type="cast_spell", card_id=to_hand(s2, "Opt").id)
    d = s2.state.rules.decision
    if d is None:  # (Opt is on the stack; let it resolve)
        act(s2, s2.state.rules.priority, type="pass_priority")
        d = s2.state.rules.decision
    return d


@pytest.mark.parametrize("with_kenessos, looked", [(True, 2), (False, 1)])
def test_kenessos_scries_one_deeper(cards, with_kenessos, looked):
    """Opt's "Scry 1" is a scry of two with Kenessos (the same scry, 701.22), one without."""
    s = build(cards, ["Kenessos, Priest of Thassa", "Opt", "Grizzly Bears", "Llanowar Elves", "Holy Strength"], [])
    d = scry_prompt(s, with_kenessos)
    assert d is not None and d.prompt.startswith(f"Scry {looked}:") and len(d.options) == looked
    answer(s, [])  # (keep both on top)
    settle(s)
    assert top(s) == ("Llanowar Elves" if looked == 2 else "Llanowar Elves")  # (Opt draws the top card: Grizzly Bears)
    check(s)


def test_kenessos_activated_puts_a_serpent_onto_the_battlefield(cards):
    """"{3}{G/U}: Look at the top card of your library. If it's a Kraken, Leviathan, Octopus, or Serpent creature card, you may put it onto the battlefield."""
    s = build(cards, ["Kenessos, Priest of Thassa", "Kraken Hatchling", "Grizzly Bears"], [])
    k = put(s, "Kenessos, Priest of Thassa")
    stack_top(s, ["Kraken Hatchling", "Grizzly Bears"])
    mana(s, "p1", G=4)
    act(s, "p1", type="activate_ability", card_id=k.id, ability=ability(s, k, "Look at the top card"))
    settle_pick(s, "Kraken Hatchling")
    assert on_battlefield(s, "Kraken Hatchling")
    check(s)


def settle_pick(s, pick=None, limit=20):
    """Resolve everything; a decision is answered with the option whose label contains ``pick`` (else its first option)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            answer(s, pick if pick is not None and any(pick in o.label for o in d.options) else None)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def test_kenessos_activated_leaves_a_bear_alone(cards):
    s = build(cards, ["Kenessos, Priest of Thassa", "Kraken Hatchling", "Grizzly Bears"], [])
    k = put(s, "Kenessos, Priest of Thassa")
    stack_top(s, ["Grizzly Bears", "Kraken Hatchling"])
    mana(s, "p1", G=4)
    act(s, "p1", type="activate_ability", card_id=k.id, ability=ability(s, k, "Look at the top card"))
    settle_pick(s, "Keep")
    assert not on_battlefield(s, "Grizzly Bears") and not on_battlefield(s, "Kraken Hatchling")
    check(s)


# -- Maralen of the Mornsong -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("maralen, drawn", [(True, 0), (False, 1)])
def test_maralen_stops_a_spells_draw(cards, maralen, drawn):
    """Opt's "Draw a card" does nothing while Maralen is in play (121.2); the scry still happens."""
    s = build(cards, ["Maralen of the Mornsong", "Opt"], [])
    if maralen:
        put(s, "Maralen of the Mornsong")
    opt = to_hand(s, "Opt")
    before = len(s.state.zones["p1:library"])
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    settle(s)
    assert before - len(s.state.zones["p1:library"]) == drawn
    check(s)


@pytest.mark.parametrize("maralen, loses", [(True, False), (False, True)])
def test_maralen_nobody_loses_for_drawing_from_an_empty_library(cards, maralen, loses):
    """The 2008-04-01 ruling: with Maralen in play a draw from an empty library is no draw, so 704.5b loses nobody the game."""
    from app.rules.plan import live_players

    s = build(cards, ["Maralen of the Mornsong", "Opt"], [])
    if maralen:
        put(s, "Maralen of the Mornsong")
    opt = to_hand(s, "Opt")
    act(s, "p1", type="move", card_ids=list(s.state.zones["p1:library"]), to={"player": "p1", "zone": "exile"})
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    settle(s)
    assert ("p1" not in live_players(s.state)) == loses
    check(s)


def seasoned(s, *names):
    """These cards on the battlefield since before this turn (no summoning sickness): put there, then on to Alice's next turn."""
    for n in names:
        put(s, n)
    finish_turn(s)
    finish_turn(s)


# -- Tetsuo Umezawa ----------------------------------------------------------------------------------------------------------------------------------
def test_tetsuo_cant_be_the_target_of_an_aura_spell(cards):
    s = build(cards, ["Tetsuo Umezawa", "Grizzly Bears", "Holy Strength"], [])
    tetsuo, bears = put(s, "Tetsuo Umezawa"), put(s, "Grizzly Bears")
    aura = to_hand(s, "Holy Strength")
    mana(s, "p1", W=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=aura.id, targets=[tetsuo.id])
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[bears.id])  # (a creature without that text is fine)
    settle(s)
    assert s.state.cards[aura.id].attached_to == bears.id
    check(s)


def test_bartel_runeaxe_cant_be_the_target_of_an_aura_spell(cards):
    s = build(cards, ["Bartel Runeaxe", "Holy Strength"], [])
    bartel = put(s, "Bartel Runeaxe")
    mana(s, "p1", W=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Holy Strength").id, targets=[bartel.id])
    check(s)


def tetsuo_kill(s, tetsuo, target):
    mana(s, "p1", U=1, B=2, R=1)
    act(s, "p1", type="activate_ability", card_id=tetsuo.id, ability=ability(s, tetsuo, "Destroy target"), targets=[target.id])
    settle(s)


def test_tetsuo_destroys_a_tapped_creature_not_an_untapped_one(cards):
    s = build(cards, ["Tetsuo Umezawa"], ["Grizzly Bears"])
    tetsuo, bears = put(s, "Tetsuo Umezawa"), put(s, "Grizzly Bears", "p2")
    finish_turn(s)
    finish_turn(s)
    mana(s, "p1", U=1, B=2, R=1)
    with pytest.raises(ActionError):  # (untapped, not blocking)
        act(s, "p1", type="activate_ability", card_id=tetsuo.id, ability=ability(s, tetsuo, "Destroy target"), targets=[bears.id])
    act(s, "p2", type="tap", card_ids=[bears.id])
    tetsuo_kill(s, tetsuo, bears)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    check(s)


def test_tetsuo_destroys_a_blocking_creature(cards):
    s = build(cards, ["Tetsuo Umezawa", "Llanowar Elves"], ["Grizzly Bears"])
    tetsuo, elves, bears = put(s, "Tetsuo Umezawa"), put(s, "Llanowar Elves"), put(s, "Grizzly Bears", "p2")
    finish_turn(s)
    finish_turn(s)
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "declare_blockers", "main2"])
    attack(s, (elves, "p2"))
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": elves.id}])
    assert s.state.turn.phase == "declare_blockers" and s.state.cards[bears.id].blocking
    tetsuo_kill(s, tetsuo, bears)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    check(s)


# -- Valentina Allegra de Fontaine -------------------------------------------------------------------------------------------------------------------
def test_valentina_makes_your_other_villains_heroes_not_theirs(cards):
    """613.1d: "Other Villains you control are Heroes in addition to their other types" - yours, not an opponent's, and not a creature that isn't a Villain."""
    s = build(cards, ["Valentina Allegra de Fontaine", "Undead Hand Ninja", "Grizzly Bears"], ["Kree Commandos"])
    put(s, "Valentina Allegra de Fontaine")
    ninja, bears, kree = put(s, "Undead Hand Ninja"), put(s, "Grizzly Bears"), put(s, "Kree Commandos", "p2")
    assert "Hero" in ch(s, ninja).subtypes and "Villain" in ch(s, ninja).subtypes
    assert "Hero" not in ch(s, bears).subtypes and "Hero" not in ch(s, kree).subtypes
    check(s)


def test_valentina_connives_a_hero_you_control(cards):
    """"{T}: Target Hero you control connives. Activate only as a sorcery." A Villain of yours is a Hero, an opponent's Hero is no target (701.50)."""
    s = build(cards, ["Valentina Allegra de Fontaine", "Undead Hand Ninja", "Grizzly Bears"], ["Masked Meower"])
    val, ninja, bears, theirs = (put(s, "Valentina Allegra de Fontaine"), put(s, "Undead Hand Ninja"), put(s, "Grizzly Bears"),
                                 put(s, "Masked Meower", "p2"))
    finish_turn(s)
    finish_turn(s)
    for bad in (bears, theirs):
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", card_id=val.id, ability=ability(s, val, "connives"), targets=[bad.id])
    hand, library, yard = len(s.state.zones["p1:hand"]), len(s.state.zones["p1:library"]), len(s.state.zones["p1:graveyard"])
    act(s, "p1", type="activate_ability", card_id=val.id, ability=ability(s, val, "connives"), targets=[ninja.id])
    settle(s)
    assert (len(s.state.zones["p1:hand"]), len(s.state.zones["p1:library"]), len(s.state.zones["p1:graveyard"])) == (hand, library - 1, yard + 1)
    check(s)


# -- Anje, Maid of Dishonor --------------------------------------------------------------------------------------------------------------------------
def bloods(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == "Blood" and c.controller == pid and c.zone.endswith(":battlefield")]


def cast_now(s, name, **m):
    """Cast ``name`` from the hand with this mana and let everything resolve."""
    mana(s, "p1", **m)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, name).id)
    settle(s)


def test_anje_triggers_for_anje_or_another_vampire_once_each_turn(cards):
    """Anje entering uses the turn's trigger up (603.2c: one trigger, however many Vampires entered); a Vampire a turn later makes a Blood, one that is no Vampire never does."""
    s = build(cards, ["Anje, Maid of Dishonor", "Vampire Interloper", "Bishop's Soldier", "Grizzly Bears"], [])
    cast_now(s, "Anje, Maid of Dishonor", R=2, B=1, G=3)
    assert len(bloods(s)) == 1  # (Anje herself)
    cast_now(s, "Vampire Interloper", B=2)
    assert len(bloods(s)) == 1  # (only once each turn)
    finish_turn(s)
    finish_turn(s)
    cast_now(s, "Grizzly Bears", G=2)
    assert len(bloods(s)) == 1  # (not a Vampire)
    cast_now(s, "Bishop's Soldier", W=2)
    assert len(bloods(s)) == 2
    check(s)


@pytest.mark.parametrize("pay", ["Blood", "Grizzly Bears"])
def test_anje_sacrifices_another_creature_or_a_blood_token(cards, pay):
    s = build(cards, ["Anje, Maid of Dishonor", "Grizzly Bears"], [])
    cast_now(s, "Anje, Maid of Dishonor", R=2, B=1, G=3)
    anje = card_named(s, "Anje, Maid of Dishonor")
    bears = put(s, "Grizzly Bears")
    finish_turn(s)
    finish_turn(s)
    paid = bloods(s)[0] if pay == "Blood" else bears
    mana(s, "p1", G=2)
    act(s, "p1", type="activate_ability", card_id=anje.id, ability=ability(s, anje, "Each opponent loses 2 life"),
        cost_choices=[{"component": 1, "cards": [paid.id]}])
    settle(s)
    assert (life(s, "p2"), life(s, "p1")) == (38, 42) and paid.id not in on_battlefield_ids(s)
    check(s)


def test_anje_cant_sacrifice_herself_for_her_ability(cards):
    s = build(cards, ["Anje, Maid of Dishonor"], [])
    cast_now(s, "Anje, Maid of Dishonor", R=2, B=1, G=3)
    anje = card_named(s, "Anje, Maid of Dishonor")
    finish_turn(s)
    finish_turn(s)
    mana(s, "p1", G=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=anje.id, ability=ability(s, anje, "Each opponent loses 2 life"),
            cost_choices=[{"component": 1, "cards": [anje.id]}])
    check(s)


def on_battlefield_ids(s):
    return {c.id for c in s.state.cards.values() if c.zone.endswith(":battlefield")}


def test_maralen_replaces_the_draw_step_with_a_tutor(cards):
    """Bob's draw step: no draw; he loses 3 life, searches his library for a card, puts it into his hand and shuffles."""
    s = build(cards, ["Maralen of the Mornsong"], ["Counterspell"], islands=6)
    put(s, "Maralen of the Mornsong")
    hand, library = len(s.state.zones["p2:hand"]), len(s.state.zones["p2:library"])
    to_main1(s, 2)
    assert life(s, "p2") == 37
    assert len(s.state.zones["p2:hand"]) == hand + 1 and len(s.state.zones["p2:library"]) == library - 1
    check(s)


# -- Hakbal of the Surging Soul ----------------------------------------------------------------------------------------------------------------------
def drive(s, picks, done, limit=60):
    """Pass priority until ``done(s)``; a decision is answered by the first of ``picks`` (substrings of an option's label or of the prompt) that fits, else its first option."""
    for _ in range(limit):
        if done(s):
            return
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        if d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
            continue
        if "<none>" in picks and d.min_choices == 0:  # (decline an optional choice)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
            continue
        want = next((o for p in picks for o in d.options if p in o.label or p in d.prompt), d.options[0])
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[want.id])
    raise AssertionError("never got there")


def counters(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].counters.get("+1/+1", 0)


def merfolk_table(cards, theirs=()):
    s = build(cards, ["Hakbal of the Surging Soul", "Merfolk Looter", "Merfolk Branchwalker", "Grizzly Bears", "Llanowar Elves"], list(theirs))
    seasoned(s, "Hakbal of the Surging Soul", "Merfolk Looter", "Merfolk Branchwalker", "Grizzly Bears")
    return s


def test_hakbal_explores_each_merfolk_in_the_order_you_choose(cards):
    """At the beginning of combat each Merfolk you control explores, one after another in the order you pick (the 2023-11-10 ruling): the Bears on top gives +1/+1 to
    whoever explores first, then two lands go to the hand. Your other creatures, and an opponent's Merfolk, don't explore."""
    s = merfolk_table(cards, ["Merfolk Looter"])
    put(s, "Merfolk Looter", "p2")
    stack_top(s, ["Llanowar Elves", "Forest", "Forest"])
    hand = len(s.state.zones["p1:hand"])
    base = {n: counters(s, n) for n in ("Merfolk Branchwalker", "Merfolk Looter", "Hakbal of the Surging Soul", "Grizzly Bears")}  # (turns 1 and 2 had combats too)
    asked = []

    def ordered(s):
        d = s.state.rules.decision
        if d is not None:
            asked.append(d.prompt)
        return bool(asked) and d is None and not s.state.zones.get("stack")

    drive(s, ["Merfolk Branchwalker", "Put it into your graveyard"], ordered)
    assert asked.count("Choose the creature that explores next") == 2  # (three Merfolk: asked while two or more are left)
    assert {n: counters(s, n) - b for n, b in base.items()} == {"Merfolk Branchwalker": 1, "Merfolk Looter": 0, "Hakbal of the Surging Soul": 0, "Grizzly Bears": 0}
    assert counters(s, "Merfolk Looter", "p2") == 0
    assert len(s.state.zones["p1:hand"]) == hand + 2 and "Llanowar Elves" in [s.state.cards[c].name for c in s.state.zones["p1:graveyard"]]
    check(s)


@pytest.mark.parametrize("mode, lands, drawn", [("put", 1, 0), ("decline", 0, 1), ("no land", 0, 1)])
def test_hakbal_puts_a_land_from_your_hand_or_draws(cards, mode, lands, drawn):
    """"Whenever Hakbal attacks, you may put a land card from your hand onto the battlefield. If you don't, draw a card."  A land put: no draw; declined, or no land in
    the hand to put: a draw (608.2c, 118.12)."""
    s = build(cards, ["Hakbal of the Surging Soul"], [])
    hakbal = put(s, "Hakbal of the Surging Soul")
    finish_turn(s)
    finish_turn(s)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    if mode == "no land":
        act(s, "p1", type="move", card_ids=[c for c in s.state.zones["p1:hand"]], to={"zone": "exile"})
    in_hand = len(s.state.zones["p1:hand"])
    forests, library = len(on_battlefield(s, "Forest")), len(s.state.zones["p1:library"])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": hakbal.id, "target": "p2"}])
    drive(s, {"put": ["Forest"], "decline": ["<none>"], "no land": []}[mode], lambda s: s.state.rules.decision is None and not s.state.zones.get("stack"))
    assert len(on_battlefield(s, "Forest")) - forests == lands and library - len(s.state.zones["p1:library"]) == drawn
    assert len(s.state.zones["p1:hand"]) == in_hand - lands + drawn
    check(s)


# -- Tamiyo, Inquisitive Student ---------------------------------------------------------------------------------------------------------------------
TAMIYO = "Tamiyo, Inquisitive Student // Tamiyo, Seasoned Scholar"


def three_opts(s, n=3):
    """Alice casts Opt ``n`` times this turn: one draw each."""
    for _ in range(n):
        mana(s, "p1", U=1)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Opt").id)
        settle(s)


@pytest.mark.parametrize("draws, flipped", [(3, True), (2, False)])
def test_tamiyo_transforms_on_the_third_card_drawn_in_a_turn(cards, draws, flipped):
    """"When you draw your third card in a turn, exile Tamiyo, then return her to the battlefield transformed" (701.28): the third card, not the second."""
    s = build(cards, [TAMIYO, "Opt", "Opt", "Opt"], [])
    put(s, TAMIYO)
    three_opts(s, draws)
    now = s.state.cards[card_named(s, TAMIYO).id]
    assert (now.zone == "p1:battlefield" and now.face == 1) == flipped
    check(s)


def test_tamiyo_seasoned_scholar_shrinks_attackers_until_your_next_turn(cards):
    """+2: "Until your next turn, whenever a creature attacks you or a planeswalker you control, it gets -1/-0 until end of turn." Bob's Bears hit for 1 on his turn;
    the watch is gone when Alice's next turn begins (500.4)."""
    s = build(cards, [TAMIYO, "Opt", "Opt", "Opt"], ["Grizzly Bears"])
    put(s, TAMIYO)
    bears = put(s, "Grizzly Bears", "p2")
    three_opts(s)
    scholar = card_named(s, TAMIYO)
    act(s, "p1", type="activate_ability", card_id=scholar.id, ability=ability(s, scholar, "+2"))
    settle(s)
    assert [t for t in s.state.rules.delayed if t.until_player == "p1"]
    until(s, lambda s: s.state.turn.number == 2 and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    before = life(s, "p1")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    until(s, lambda s: s.state.turn.phase == "main2" and s.state.rules.decision is None)
    assert before - life(s, "p1") == 1
    finish_turn(s)
    assert s.state.turn.number == 3 and not [t for t in s.state.rules.delayed if t.until_player == "p1"]
    check(s)


# -- Sneaky Snacker (the same "third card in a turn" wording, read from the graveyard) -------------------------------------------------------------
@pytest.mark.parametrize("draws, returns", [(3, True), (2, False)])
def test_sneaky_snacker_returns_from_the_graveyard_on_the_third_draw(cards, draws, returns):
    s = build(cards, ["Sneaky Snacker", "Opt", "Opt", "Opt"], [])
    snacker = card_named(s, "Sneaky Snacker")
    act(s, "p1", type="move", card_ids=[snacker.id], to={"player": "p1", "zone": "graveyard"})
    three_opts(s, draws)
    now = s.state.cards[snacker.id]
    assert (now.zone == "p1:battlefield") == returns and (not returns or now.tapped)
    check(s)


# -- Ketramose, the New Dawn -------------------------------------------------------------------------------------------------------------------------
def exile_cards(s, n, pid="p1"):
    """``n`` cards off the top of ``pid``'s library into exile (a manual move: no trigger reads it)."""
    act(s, pid, type="move", card_ids=list(s.state.zones[f"{pid}:library"])[:n], to={"player": pid, "zone": "exile"})


@pytest.mark.parametrize("exiled, can", [(6, False), (7, True)])
def test_ketramose_attacks_only_with_seven_cards_in_exile(cards, exiled, can):
    """"Ketramose can't attack or block unless there are seven or more cards in exile": cards in every player's exile zone count (400.1). Alice is asked who attacks only
    when someone can."""
    s = build(cards, ["Ketramose, the New Dawn"], [])
    ketramose = put(s, "Ketramose, the New Dawn")
    finish_turn(s)
    finish_turn(s)
    exile_cards(s, exiled - 2)
    exile_cards(s, 2, "p2")
    for _ in range(30):
        d = s.state.rules.decision
        if (d is not None and d.kind == "declare_attackers") or s.state.turn.phase == "main2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    asked = s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"
    assert asked == can
    if can:
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": ketramose.id, "target": "p2"}])
    check(s)


def test_ketramose_draws_when_cards_are_exiled_from_the_battlefield_or_a_graveyard(cards):
    """On your turn: Swords to Plowshares exiling Bob's Bears from the battlefield, Relic of Progenitus exiling a card from a graveyard - one card and 1 life each."""
    s = build(cards, ["Ketramose, the New Dawn", "Swords to Plowshares", "Relic of Progenitus", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Ketramose, the New Dawn")
    bears, relic = put(s, "Grizzly Bears", "p2"), put(s, "Relic of Progenitus")
    mana(s, "p1", W=1)
    lib, hp = len(s.state.zones["p1:library"]), life(s, "p1")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Swords to Plowshares").id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:exile"
    assert (len(s.state.zones["p1:library"]), life(s, "p1")) == (lib - 2, hp - 1)  # (Swords left the library for the hand, Ketramose drew one; Alice lost 1)
    act(s, "p1", type="move", card_ids=[card_named(s, "Grizzly Bears").id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="activate_ability", card_id=relic.id, ability=ability(s, relic, "exiles a card"), targets=["p1"])
    settle_pick(s)
    assert (len(s.state.zones["p1:library"]), life(s, "p1")) == (lib - 3, hp - 2)
    check(s)


def test_ketramose_ignores_a_token_exiled_from_the_battlefield(cards):
    s = build(cards, ["Ketramose, the New Dawn", "Swords to Plowshares", "Raise the Alarm"], [])
    put(s, "Ketramose, the New Dawn")
    mana(s, "p1", W=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Raise the Alarm").id)
    settle(s)
    token = next(c for c in s.state.cards.values() if c.name == "Soldier" and c.zone == "p1:battlefield")
    hp, lib = life(s, "p1"), len(s.state.zones["p1:library"])
    mana(s, "p1", W=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Swords to Plowshares").id, targets=[token.id])
    settle(s)
    assert len(s.state.zones["p1:library"]) == lib - 1 and life(s, "p1") == hp + 1  # (the Swords went to the hand; a token is no card: nothing drawn, no life lost, the 1 life is Swords')
    check(s)
