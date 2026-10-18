"""Review 36 (false-FULL probe of waves 38B, 39A, 40A-D, 41B-D, CR 2026-09-25): pins for behaviors of cards those waves made FULL that their own tests
didn't play, each checked against its official rulings with real Oracle text (tests/fixtures/review36_cards.json, from data/cards.sqlite). Every scenario
checks the replay and a save and a load.

* 118.12a: "return it to your hand unless target opponent pays 3 life" (Athreos, God of Passage): the target opponent decides as it resolves.
* 508.4: "you may have its controller create a 1/1 white Warrior creature token that's tapped and attacking" (Najeela): the token's controller chooses what
  it attacks — Najeela's ruling of 2020-11-10, any player or planeswalker, not necessarily the one the Warrior attacks.
* 603.2, 712: "Whenever this creature enters or transforms into Brigid, Clachan's Heart" triggers on the front face only.
* 400.2, 401.5: "look at the top card of your library. If it's a land card, you may put it …" (Rulik Mons): the looker is asked whatever the card is, so the
  table can't tell from the question whether it was a land.
* 614: Vren's "exile it instead" applies to the creatures that die with Vren (its ruling of 2024-07-26).
* 305.2: a land exiled by Urza is played with the turn's land play (Urza's ruling of 2022-12-08).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.visibility import SPECTATOR
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import until
from tests.wave9c_kit import build, card_named, check, mana, put, reloaded, to_hand
from tests.wave36a_kit import attack, ready, to_turn_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "review36_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r36", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
BRIGID = "Brigid, Clachan's Heart // Brigid, Doun's Mind"


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def settle(s, answer=None, limit=60):
    """Pass priority until a decision ``answer`` doesn't take (returned) or the stack is empty (None). ``answer(d)`` returns the option ids to choose, or
    None to stop there; without it every decision stops."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
            continue
        if d is not None:
            picked = answer(d) if answer is not None else None
            if picked is None:
                return d
            act(s, d.player, type="choose", decision_id=d.id, option_ids=picked)
            continue
        if not s.state.zones.get("stack"):
            return None
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never settled")


def first(d):
    return [o.id for o in d.options][: max(1, d.min_choices)]


def named(s, name):
    return [c for c in s.state.cards.values() if c.name == name]


# -- Athreos, God of Passage: "Whenever another creature you own dies, return it to your hand unless target opponent pays 3 life." ----------------------
@pytest.mark.parametrize("pays", [True, False])
def test_athreos_returns_the_creature_unless_the_target_opponent_pays_3_life(cards, pays):
    s = build(cards, ["Athreos, God of Passage", "Centaur Courser"])
    put(s, "Athreos, God of Passage")
    courser = put(s, "Centaur Courser")
    act(s, "p1", type="set_damage", card_ids=[courser.id], value=99)
    act(s, "p1", type="pass_priority")
    d = settle(s, lambda d: first(d) if d.player == "p1" else None)  # (Alice targets Bob, her one opponent)
    assert d is not None and d.player == "p2" and d.kind == "choose_one"
    s = reloaded(s)
    d = s.state.rules.decision
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith("Pay" if pays else "Don't"))])
    settle(s)
    assert s.state.cards[courser.id].zone == ("p1:graveyard" if pays else "p1:hand")
    assert s.state.players["p2"].life == (37 if pays else 40)
    check(s)


# -- Najeela, the Blade-Blossom: "Whenever a Warrior attacks, you may have its controller create a 1/1 white Warrior creature token that's tapped and
# attacking." --------------------------------------------------------------------------------------------------------------------------------------------
def test_najeela_another_players_warrior_its_controller_makes_the_token_and_chooses_what_it_attacks(cards):
    setups = [PlayerSetup(name, cards=deck(cards, "Krenko, Mob Boss" if i == 0 else "Atraxa, Praetors' Voice", [*spells, (30, "Forest")]))
              for i, (name, spells) in enumerate([("Alice", [(1, "Najeela, the Blade-Blossom")]), ("Bob", [(1, "Centaur Courser")]), ("Carol", [])])]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    put(s, "Najeela, the Blade-Blossom")
    courser = put(s, "Centaur Courser", "p2")  # (a Centaur Warrior)
    to_turn_of(s, "p2")
    s.state.rules.controlled_since[courser.id].turn = 0
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": courser.id, "target": "p3"}])
    d = settle(s)
    assert d.player == "p1" and d.kind == "confirm"  # Alice's "you may"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    d = settle(s)
    assert d.player == "p2" and {o.label for o in d.options} == {"Alice", "Carol"}  # Bob's token: any of his opponents (Carol isn't required)
    assert s.view("p3")["rules"]["decision"]["kind"] == "waiting"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["p1"])
    (token,) = [c for c in named(s, "Warrior") if c.is_token]
    assert token.controller == "p2" and token.tapped and token.attacking is not None and token.attacking.id == "p1"
    check(s)


# -- Brigid, Clachan's Heart: "Whenever this creature enters or transforms into Brigid, Clachan's Heart, create a 1/1 green and white Kithkin creature
# token. At the beginning of your first main phase, you may pay {G}. If you do, transform Brigid." (back: "… you may pay {W}. If you do, transform Brigid.")
def test_brigid_makes_a_kithkin_as_it_enters_and_as_it_transforms_back_not_as_it_transforms_away(cards):
    s = build(cards, [BRIGID], forests=12)
    brigid = to_hand(s, BRIGID)
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=brigid.id)
    settle(s, first)
    for forest in [c for c in named(s, "Forest") if c.zone == "p1:library"][:3]:
        act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    seen = [len(named(s, "Kithkin"))]
    for turn in (3, 5):  # Alice's next two turns: pay {G} (Forest), then {W} (Doun's Mind's own mana, X = the one other creature)
        until(s, lambda s, turn=turn: s.state.turn.number == turn and s.state.rules.decision is not None and s.state.rules.decision.player == "p1"
              and s.state.rules.decision.kind == "choose_one", limit=400)
        if turn == 5:
            s = reloaded(s)
        d = s.state.rules.decision
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])  # pay
        settle(s, first)
        seen.append(len(named(s, "Kithkin")))
    assert seen == [1, 1, 2]
    check(s)


# -- Rulik Mons, Warren Chief: "look at the top card of your library. If it's a land card, you may put it onto the battlefield tapped. If you didn't put a
# card onto the battlefield this way, create a 1/1 red Goblin creature token." ----------------------------------------------------------------------------
def test_rulik_mons_asks_whatever_the_top_card_is(cards):
    s = build(cards, ["Rulik Mons, Warren Chief", "Shock"], forests=20)
    rulik = put(s, "Rulik Mons, Warren Chief")
    ready(s, "Rulik Mons, Warren Chief")
    act(s, "p1", type="move", card_ids=[card_named(s, "Shock").id], to={"zone": "library"})  # (on top)
    attack(s, rulik)
    d = settle(s)
    assert d is not None and d.player == "p1" and d.options == []  # a nonland: asked all the same, nothing to choose
    for viewer in ("p2", SPECTATOR):
        assert s.view(viewer)["rules"]["decision"]["kind"] == "waiting"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert len([c for c in named(s, "Goblin") if c.is_token]) == 1 and card_named(s, "Shock").zone == "p1:library"
    check(s)


# -- Vren, the Relentless: "If a creature an opponent controls would die, exile it instead." -------------------------------------------------------------
def test_vren_exiles_the_creatures_that_die_with_it(cards):
    s = build(cards, ["Vren, the Relentless", "Wrath of God"], ["Centaur Courser"])
    put(s, "Vren, the Relentless")
    courser = put(s, "Centaur Courser", "p2")
    wrath = to_hand(s, "Wrath of God")
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=wrath.id)
    settle(s, first)
    assert card_named(s, "Vren, the Relentless").zone == "p1:graveyard" and s.state.cards[courser.id].zone == "p2:exile"
    check(s)


# -- Urza, Lord High Artificer: "{5}: Shuffle your library, then exile the top card. Until end of turn, you may play that card without paying its mana
# cost." --------------------------------------------------------------------------------------------------------------------------------------------------
def test_urza_an_exiled_land_needs_the_turns_land_play(cards):
    s = build(cards, ["Urza, Lord High Artificer", "Command Tower"], forests=1)
    put(s, "Urza, Lord High Artificer")
    forest = card_named(s, "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forest.id)
    for cid in [c for c in s.state.zones["p1:library"] if s.state.cards[c].name != "Command Tower"]:
        act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "graveyard"})  # (Command Tower alone: the shuffle keeps it on top)
    mana(s, C=5)
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Urza, Lord High Artificer").id, ability=2)
    settle(s)
    tower = card_named(s, "Command Tower")
    assert tower.zone == "p1:exile"
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=tower.id)
    check(s)
