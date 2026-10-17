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
from tests.test_rules_conditionals import settle
from tests.test_rules_wave39b_trigger_damage import attack, finish_turn, to_main1
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50g_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t50g", number=f"G{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Kenessos, Priest of Thassa", "Maralen of the Mornsong", "Tetsuo Umezawa", "Bartel Runeaxe", "Valentina Allegra de Fontaine",
        "Anje, Maid of Dishonor", "Hakbal of the Surging Soul"]


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
            answer(s, pick if any(pick in o.label for o in d.options) else None)
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


def test_maralen_replaces_the_draw_step_with_a_tutor(cards):
    """Bob's draw step: no draw; he loses 3 life, searches his library for a card, puts it into his hand and shuffles."""
    s = build(cards, ["Maralen of the Mornsong"], ["Counterspell"], islands=6)
    put(s, "Maralen of the Mornsong")
    hand, library = len(s.state.zones["p2:hand"]), len(s.state.zones["p2:library"])
    to_main1(s, 2)
    assert life(s, "p2") == 37
    assert len(s.state.zones["p2:hand"]) == hand + 1 and len(s.state.zones["p2:library"]) == library - 1
    check(s)
