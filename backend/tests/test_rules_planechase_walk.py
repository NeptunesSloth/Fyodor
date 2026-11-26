"""-- planechase walk (wave C) -- "When you planeswalk to ~" / "When you planeswalk away from ~" / "When you encounter ~" lines read by
exact wording (app/rules/planar_walk.py; 701.31d, 312.5), on real Oracle text: the table planeswalks with the rules engine on, the
trigger (controlled by the planar controller, 901.6) resolves, the effect is checked, then ``check`` (replay + save/load round trip)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings, PlanarCard
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_planechase import script
from tests.test_rules_conditionals import to_turn
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import card_named, check, mana, put

# Oracle text exactly as in the card database (data/cards.sqlite)
PLANES = {
    "Krosa": ("Plane — Dominaria", "All creatures get +2/+2.\nWhenever chaos ensues, you may add {W}{U}{B}{R}{G}."),
    "Pompeii": ("Plane — Earth", "When you planeswalk to Pompeii and at the beginning of your upkeep, put an eruption counter on it.\nWhenever "
                "you roll a blank on the planar die, scry 2. Then put an eruption counter on Pompeii.\nWhen chaos ensues, Pompeii deals damage "
                "to each creature and each player equal to the number of eruption counters on Pompeii. Each player sacrifices a land of their "
                "choice. Then planeswalk."),
    "The Maelstrom": ("Plane — Alara", "When you planeswalk to The Maelstrom and at the beginning of your upkeep, you may reveal the top card of "
                      "your library. If a permanent card is revealed this way, you may put it onto the battlefield. If you revealed a card but "
                      "didn't put it onto the battlefield, put it on the bottom of your library.\nWhenever chaos ensues, return target "
                      "permanent card from your graveyard to the battlefield."),
    "Kilnspire District": ("Plane — Ravnica", "When you planeswalk to Kilnspire District and at the beginning of your first main phase, put a "
                           "charge counter on Kilnspire District, then add {R} for each charge counter on it.\nWhenever chaos ensues, you may "
                           "pay {X}. If you do, Kilnspire District deals X damage to any target."),
    "Sky Deck": ("Plane — Chicago", "Whenever you planeswalk here, at the beginning of your upkeep, or whenever chaos ensues, put a glass counter "
                 "on up to one target nonland permanent.\nWhen you planeswalk away from here, destroy all permanents with glass counters on "
                 "them."),
    "Asmoranomardicadaistinaculdacar's Kitchen": ("Plane — Hell", "Whenever you planeswalk here and whenever a creature enters under your "
                                                  "control, create a Food token.\nWhenever you gain life, target opponent loses that much "
                                                  "life.\nWhenever Chaos ensues, you may sacrifice any number of artifacts or creatures. Draw "
                                                  "that many cards and lose that much life."),
    "Oteclán": ("Plane — Ixalan", "When you planeswalk to Oteclán and at the beginning of your upkeep, chaos ensues.\nWhenever chaos ensues, "
                "discover 3. (Exile cards from the top of your library until you exile a nonland card with that mana value or less. Cast it "
                "without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)"),
    "Norn's Seedcore": ("Plane — New Phyrexia", "When you planeswalk to Norn's Seedcore, chaos ensues.\nWhenever chaos ensues, reveal cards from "
                        "the top of your planar deck until you reveal a plane card. Planeswalk to it, except don't planeswalk away from any "
                        "plane. Put the rest of the revealed cards on the bottom of your planar deck in any order."),
    'City Hall': ('Plane — Chicago',
        'When you planeswalk here, you become the Monarch.\nWhenever Chaos ensues, each player may create two tapped '
        "treasure tokens. Each player who does can't attack you during their next turn."),
    'The Aether Flues': ('Plane — Iquatana',
        'When you planeswalk to The Aether Flues and at the beginning of your upkeep, you may sacrifice a creature. If '
        'you do, reveal cards from the top of your library until you reveal a creature card, put that card onto the '
        'battlefield, then shuffle all other cards revealed this way into your library.\nWhenever chaos ensues, you may '
        'put a creature card from your hand onto the battlefield.'),
    'The Pit': ('Plane — The Abyss',
        'When you planeswalk to The Pit, each player creates their choice of a 3/3 white Angel creature token with '
        'flying or a 6/6 black Demon creature token with flying, trample, and "At the beginning of your upkeep, '
        'sacrifice another creature. If you can\'t, this token deals 6 damage to you."\nWhenever chaos ensues, each '
        'player sacrifices a nonartifact creature of their choice.'),
    'Bowie Base One': ('Plane — Mars',
        'At the beginning of your end step, goad target creature controlled by the player to your left. (Until your '
        'next turn, that creature attacks each combat if able and attacks a player other than you if able.)\nWhenever '
        "chaos ensues, target creature gains islandwalk until end of turn. (It can't be blocked as long as defending "
        'player controls an Island.)'),
    "Prime Minister's Cabinet Room": ('Plane — Earth',
        'At the beginning of combat on your turn, up to one target creature you control becomes a copy of target '
        'creature an opponent controls.\nWill of the council — Whenever chaos ensues, starting with you, each player '
        "votes for a creature you don't control. Exile each creature with the most votes or tied for most votes."),
    'Chaotic Aether': ('Phenomenon',
        'When you encounter Chaotic Aether, each blank roll of the planar die is a {CHAOS} roll until a player '
        'planeswalks away from a plane. (Then planeswalk away from this phenomenon.)'),
    'Fixed Point in Time': ('Phenomenon',
        'When you encounter Fixed Point in Time, until your next turn, if a player would planeswalk as a result of '
        'rolling the planar die, chaos ensues instead. (Then planeswalk away from this phenomenon.)'),
    'Unleash the Flux': ('Phenomenon',
        'When you encounter Unleash the Flux, each player sacrifices a nonland permanent of their choice, then you flip'
        ' a coin. If you lose the flip, repeat this process. (Then planeswalk away from this phenomenon.)'),
    "Time Distortion": ("Phenomenon", "When you encounter Time Distortion, reverse the game's turn order. (For example, if play had proceeded "
                        "clockwise around the table, it now goes counterclockwise. Then planeswalk away from this phenomenon.)"),
    "Reality Shaping": ("Phenomenon", "When you encounter Reality Shaping, starting with you, each player may put a permanent card from their "
                        "hand onto the battlefield. (Then planeswalk away from this phenomenon.)"),
}
EXTRA = [card(n, set_code="opca", number=f"PW-{i}", layout="planar", type_line=t, oracle_text=o) for i, (n, (t, o)) in enumerate(PLANES.items())]
EXTRA += [real("Runeclaw Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
          real("Craw Wurm", "{4}{G}{G}", 6, "Creature — Wurm", "", ("6", "4"), "G"),
          real("Opt", "{U}", 1, "Instant", "Scry 1.\nDraw a card.", None, "U")]
FULL = ["Unleash the Flux", "Chaotic Aether", "Fixed Point in Time", "The Aether Flues", "The Pit", "Bowie Base One", "Prime Minister's Cabinet Room", "The Maelstrom", "Kilnspire District", "Sky Deck", "Asmoranomardicadaistinaculdacar's Kitchen", "Oteclán", "Time Distortion",
        "Reality Shaping"]
LINES = {"Pompeii": 0, "Norn's Seedcore": 0, "City Hall": 0}  # (their other lines: other work)


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


class _InOrder:
    def shuffle(self, items: list) -> None:
        pass

    def randint(self, lo: int, hi: int) -> int:
        return lo


def table(cards, planes: list[str], players: int = 2) -> GameSession:
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Runeclaw Bear"), (1, "Opt"), (1, "Craw Wurm"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Runeclaw Bear"), (1, "Craw Wurm"), (10, "Island")])
    carol = deck(cards, "Krenko, Mob Boss", [(1, "Runeclaw Bear"), (10, "Forest")])
    pool = [PlanarCard(printing_id=cards.resolve(n)["id"], name=n, phenomenon=PLANES[n][0] == "Phenomenon") for n in planes]
    setups = [PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)][:players]
    state = new_game(setups, shuffle=False, first_player=0, settings=GameSettings(planechase=True, planar_deck_size=len(pool)),
                     planar_pool=lambda: pool, rng=_InOrder())
    assert [c.name for c in state.planechase.deck] == planes
    enable(state)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def resolve(s, picks=(), seen=None):
    """Everything resolves; a choice takes the ``picks`` (ids, card ids or labels, in this order of preference) when offered, else the
    fewest it may. ``seen`` collects (player, face-up card name) as each decision comes up."""
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            if seen is not None:
                seen.append((d.player, face(s).name))
            chosen = [o.id for p in picks for o in d.options if p in (o.id, o.card_id, o.label)][: d.max_choices]
            if len(chosen) < d.min_choices:
                chosen = [o.id for o in d.options][: d.min_choices]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def walk(s, monkeypatch, picks=(), seen=None):
    """Alice rolls the planeswalker symbol (901.8: the planeswalking ability; a hand-made planeswalk is a manual event, no trigger)."""
    from app.game.handlers.planechase import roll_cost

    if cost := roll_cost(s.state):
        mana(s, C=cost)
    script(monkeypatch, [1])
    act(s, "p1", type="roll_planar_die")
    resolve(s, picks, seen)


def face(s):
    pc = s.state.planechase
    return s.state.cards[pc.face_id]


def red(s, pid):
    p = s.state.players[pid]
    return p.mana.get("R", 0) + sum(u.sym == "R" for u in p.mana_units)


def library(s, pid="p1"):
    return [s.state.cards[c].name for c in s.state.zones[f"{pid}:library"]]


def to_top(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "library"}, position="top")
    return c


@pytest.mark.parametrize("name", FULL)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", list(LINES))
def test_the_line_is_read(cards, name):
    cov = coverage.of_card_data(cards.resolve(name))
    assert next(f for f in cov.features if f.id == f"text:{LINES[name]}").supported


def test_pompeii_eruption_counter_on_the_plane_when_planeswalked_to_and_each_upkeep(cards, monkeypatch):
    s = table(cards, ["Krosa", "Pompeii"])
    walk(s, monkeypatch)
    assert face(s).name == "Pompeii" and face(s).counters.get("eruption") == 1
    to_turn(s, 2)  # (Bob's upkeep: he is the planar controller now, 311.5)
    assert face(s).counters.get("eruption") == 2
    check(s)


@pytest.mark.parametrize("top,take,where", [("Runeclaw Bear", True, "battlefield"), ("Runeclaw Bear", False, "bottom"),
                                            ("Opt", True, "bottom"), ("Runeclaw Bear", None, "top")])
def test_the_maelstrom_reveal_put_or_bottom(cards, top, take, where, monkeypatch):
    s = table(cards, ["Krosa", "The Maelstrom"])
    c = to_top(s, top)
    picks = ["Yes", "yes"] if take is not None else ["No", "no"]
    if take:
        picks += [c.id]
    walk(s, monkeypatch, picks=picks)
    zone = s.state.cards[c.id].zone
    lib = s.state.zones["p1:library"]
    assert {"battlefield": zone == "p1:battlefield", "bottom": zone == "p1:library" and lib[-1] == c.id,
            "top": zone == "p1:library" and lib[0] == c.id}[where], (zone, library(s)[:2], library(s)[-2:])
    check(s)


def test_kilnspire_district_charge_counter_then_red_mana_for_each(cards, monkeypatch):
    s = table(cards, ["Krosa", "Kilnspire District"])
    walk(s, monkeypatch)
    assert face(s).counters.get("charge") == 1 and red(s, "p1") == 1
    to_turn(s, 2)  # Bob's first main phase: the second counter, two red
    assert face(s).counters.get("charge") == 2 and red(s, "p2") == 2
    check(s)


def test_sky_deck_glass_counter_then_planeswalking_away_destroys(cards, monkeypatch):
    s = table(cards, ["Krosa", "Sky Deck"])
    bear, forest = put(s, "Runeclaw Bear"), put(s, "Forest")
    walk(s, monkeypatch, picks=[bear.id])
    assert s.state.cards[bear.id].counters.get("glass") == 1
    mana(s, C=1)  # (the second roll this turn costs {1}, 901.9)
    script(monkeypatch, [2])  # chaos ensues (901.9b): the same ability's chaos half
    act(s, "p1", type="roll_planar_die")
    resolve(s, picks=[bear.id])
    assert s.state.cards[bear.id].counters.get("glass") == 2
    walk(s, monkeypatch)  # (away from Sky Deck: its trigger is from the gone plane, 701.31d)
    assert face(s).name == "Krosa"
    assert s.state.cards[bear.id].zone == "p1:graveyard" and s.state.cards[forest.id].zone == "p1:battlefield"
    check(s)


def test_kitchen_food_when_planeswalked_to_and_when_a_creature_enters(cards, monkeypatch):
    s = table(cards, ["Krosa", "Asmoranomardicadaistinaculdacar's Kitchen"])
    walk(s, monkeypatch)

    def foods(pid="p1"):
        return sum(c.name == "Food" and c.zone == f"{pid}:battlefield" for c in s.state.cards.values())

    assert foods() == 1
    act(s, "p1", type="move", card_ids=[card_named(s, "Runeclaw Bear").id], to={"zone": "hand"})
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Runeclaw Bear").id)
    resolve(s)
    assert foods() == 2 and foods("p2") == 0
    check(s)


def test_oteclan_chaos_ensues_when_planeswalked_to(cards, monkeypatch):
    s = table(cards, ["Krosa", "Oteclán"])
    bear = to_top(s, "Runeclaw Bear")
    walk(s, monkeypatch, picks=["Put it into your hand", "hand", "Hand"])  # 311.7: chaos ensues → discover 3 hits the Bear (mana value 2)
    assert s.state.cards[bear.id].zone in ("p1:hand", "p1:battlefield", "stack")
    check(s)


def test_time_distortion_reverses_the_turn_order_then_the_table_planeswalks_on(cards, monkeypatch):
    s = table(cards, ["Krosa", "Time Distortion"], players=3)
    before = s.state.turn_order()
    walk(s, monkeypatch)
    assert s.state.rules.turn_reversed110m and s.state.turn_order() != before
    assert face(s).name == "Krosa"  # 704.6f: after the encounter ability resolved
    check(s)


def test_reality_shaping_starting_with_you_each_player_may_put_then_planeswalk(cards, monkeypatch):
    s = table(cards, ["Krosa", "Reality Shaping"])
    bear = card_named(s, "Runeclaw Bear")
    wurm = card_named(s, "Craw Wurm", "p2")
    for c, pid in ((bear, "p1"), (wurm, "p2")):
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    seen: list = []
    walk(s, monkeypatch, picks=[bear.id, wurm.id], seen=seen)
    assert [p for p, _ in seen] == ["p1", "p2"] and {n for _, n in seen} == {"Reality Shaping"}  # (no planeswalk before the choices)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[wurm.id].zone == "p2:battlefield"
    assert face(s).name == "Krosa"
    check(s)



def test_city_hall_you_become_the_monarch(cards, monkeypatch):
    s = table(cards, ["Krosa", "City Hall"])
    walk(s, monkeypatch)
    assert s.state.table.monarch == "p1"
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_the_aether_flues_sacrifice_then_reveal_until_a_creature(cards, monkeypatch, pay):
    s = table(cards, ["Krosa", "The Aether Flues"])
    bear = put(s, "Runeclaw Bear")
    wurm = card_named(s, "Craw Wurm")
    before = list(s.state.zones["p1:library"])
    seen: list = []
    walk(s, monkeypatch, picks=["Yes", "yes", "Pay", bear.id] if pay else ["No", "no", "Don't pay", "Decline"], seen=seen)
    assert seen, "the optional sacrifice is asked"
    if pay:
        assert s.state.cards[bear.id].zone == "p1:graveyard" and s.state.cards[wurm.id].zone == "p1:battlefield"
    else:  # (no sacrifice: nothing is revealed, put or shuffled, 608.2c)
        assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.zones["p1:library"] == before
    check(s)


def test_the_pit_each_player_chooses_angel_or_demon(cards, monkeypatch):
    s = table(cards, ["Krosa", "The Pit"])
    seen: list = []
    picks = iter(["0", "1"])

    def answer(s):
        d = s.state.rules.decision
        seen.append(d.player)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(picks)])

    from app.game.handlers.planechase import roll_cost

    assert roll_cost(s.state) == 0
    script(monkeypatch, [1])
    act(s, "p1", type="roll_planar_die")
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            answer(s)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert seen == ["p1", "p2"]
    made = {(c.controller, c.name) for c in s.state.cards.values() if c.is_token and c.zone.endswith(":battlefield")}
    assert made == {("p1", "Angel"), ("p2", "Demon")}
    demon = next(c for c in s.state.cards.values() if c.name == "Demon")
    assert "sacrifice another creature" in demon.token.text and "Trample" in demon.token.text
    check(s)


@pytest.mark.parametrize("mine", [True, False])
def test_prime_ministers_cabinet_room_up_to_one_of_yours_becomes_a_copy(cards, monkeypatch, mine):
    from app.rules.plan import Plan

    s = table(cards, ["Prime Minister's Cabinet Room", "Krosa"])
    bear = put(s, "Runeclaw Bear") if mine else None
    wurm = put(s, "Craw Wurm", "p2")
    act(s, "p1", type="pass_priority")  # → the beginning of combat: the starting plane's trigger (901.5 only spares its own planeswalk trigger)
    resolve(s, picks=[c.id for c in (bear, wurm) if c is not None])
    if mine:
        assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id]).name == "Craw Wurm"
    assert s.state.cards[wurm.id].zone == "p2:battlefield"
    check(s)


def test_bowie_base_one_goads_a_creature_of_the_player_to_your_left(cards, monkeypatch):
    from app.rules.keyword_actions import goaded_by
    from app.rules.plan import Plan
    from tests.test_rules_conditionals import until

    s = table(cards, ["Bowie Base One", "Krosa"], players=3)
    wurm = put(s, "Craw Wurm", "p2")
    carols = put(s, "Runeclaw Bear", "p3")  # (the player to Alice's left is Bob, the next in turn order)
    offered: list = []

    def at_target(s):
        d = s.state.rules.decision
        if d is not None and any(o.card_id == wurm.id or o.id == wurm.id for o in d.options):
            offered.extend(o.card_id or o.id for o in d.options)
            return True
        return False

    until(s, at_target)
    assert wurm.id in offered and carols.id not in offered
    resolve(s, picks=[wurm.id])
    assert goaded_by(Plan(s.state, "p1", s.cards, None).ch(s.state.cards[wurm.id])) == {"p1"}
    check(s)


def roll_face(s, monkeypatch, value, picks=()):
    """Alice rolls the planar die for the server's d6 ``value`` (1 planeswalker, 2 chaos, 3-6 blank), paying its cost (901.9)."""
    from app.game.handlers.planechase import roll_cost

    if cost := roll_cost(s.state):
        mana(s, C=cost)
    script(monkeypatch, [value])
    act(s, "p1", type="roll_planar_die")
    resolve(s, picks)


def test_chaotic_aether_blank_rolls_are_chaos_until_a_player_planeswalks_away_from_a_plane(cards, monkeypatch):
    s = table(cards, ["Krosa", "Chaotic Aether", "Sky Deck"])
    bear = put(s, "Runeclaw Bear")
    walk(s, monkeypatch, picks=[bear.id])  # the encounter resolves, then the table planeswalks on (704.6f) to Sky Deck
    assert face(s).name == "Sky Deck" and s.state.cards[bear.id].counters.get("glass") == 1
    assert s.state.rules.planar_walk_pcw == [{"kind": "blank_chaos"}]  # (planeswalking away from the phenomenon doesn't end it)
    roll_face(s, monkeypatch, 3, picks=[bear.id])  # a blank roll: chaos ensues (Sky Deck's chaos half)
    assert s.state.planechase.last_roll.face == "blank" and s.state.cards[bear.id].counters.get("glass") == 2
    walk(s, monkeypatch)  # away from a plane: it ends
    assert face(s).name == "Krosa" and s.state.rules.planar_walk_pcw == []
    roll_face(s, monkeypatch, 4)
    assert not s.state.zones.get("stack") and s.state.rules.decision is None
    check(s)


def test_fixed_point_in_time_a_rolled_planeswalk_is_chaos_until_your_next_turn(cards, monkeypatch):
    s = table(cards, ["Krosa", "Fixed Point in Time", "Sky Deck"])
    bear = put(s, "Runeclaw Bear")
    walk(s, monkeypatch, picks=[bear.id])  # (704.6f's planeswalk isn't a roll: the table moves on to Sky Deck)
    assert face(s).name == "Sky Deck" and s.state.cards[bear.id].counters.get("glass") == 1
    roll_face(s, monkeypatch, 1, picks=[bear.id])  # the planeswalker symbol: chaos ensues instead
    assert face(s).name == "Sky Deck" and s.state.cards[bear.id].counters.get("glass") == 2
    to_turn(s, 2)
    assert [x["kind"] for x in s.state.rules.planar_walk_pcw] == ["fixed_point"]
    to_turn(s, 3)  # Alice's next turn: it ends (500.4)
    assert s.state.rules.planar_walk_pcw == []
    check(s)


@pytest.mark.parametrize("coins,rounds", [([1], 1), ([0, 1], 2)])
def test_unleash_the_flux_sacrifice_then_flip_repeat_on_a_loss(cards, monkeypatch, coins, rounds):
    s = table(cards, ["Krosa", "Unleash the Flux"])
    for pid in ("p1", "p2"):
        put(s, "Runeclaw Bear", pid)
        put(s, "Craw Wurm", pid)
    script(monkeypatch, [1, *coins])  # the planeswalker symbol, then the coins (1: won)
    act(s, "p1", type="roll_planar_die")
    seen: list = []
    resolve(s, seen=seen)
    for pid in ("p1", "p2"):
        left = [c for c in s.state.cards.values() if c.zone == f"{pid}:battlefield" and c.name in ("Runeclaw Bear", "Craw Wurm")]
        assert len(left) == 2 - rounds, (pid, [c.name for c in left])
    assert {n for _, n in seen} == {"Unleash the Flux"} and face(s).name == "Krosa"  # (704.6f: only after the last flip)
    check(s)
