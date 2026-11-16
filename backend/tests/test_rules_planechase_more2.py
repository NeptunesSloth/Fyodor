"""-- planechase more 2 (wave F1) -- the face-up plane's remaining grants and triggers (app/rules/planar_more2.py), each on its real Oracle
text with the face-up plane as the rules object ("you" is the planar controller, 311.5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings, PlanarCard
from app.rules import alt_costs, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import settle, to_turn, until
from tests.test_rules_planechase_plumbing import PLANES as BASE
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check, mana

# Oracle text exactly as in the card database (data/cards.sqlite)
PLANES = {
    'Grixis': ('Plane — Alara', "Blue, black, and/or red creature cards in your graveyard have unearth. The unearth cost is equal to the card's mana cost. (Pay the card's mana cost: Return it to the battlefield. The creature gains haste. Exile it at the beginning of the next end step or if it would leave the battlefield. Unearth only as a sorcery.)\nWhenever chaos ensues, put target creature card from a graveyard onto the battlefield under your control."),  # noqa: E501
    'Otaria': ('Plane — Dominaria', "Instant and sorcery cards in graveyards have flashback. The flashback cost is equal to the card's mana cost. (Its owner may cast the card from their graveyard for its mana cost. Then they exile it.)\nWhenever chaos ensues, take an extra turn after this one."),  # noqa: E501
    'Strixhaven': ('Plane — Arcavios', "Instant and sorcery spells players cast have demonstrate. (Whenever a player casts an instant or sorcery spell, they may copy it. If they do, they choose an opponent to also copy it. Players may choose new targets for their copies.)\nWhenever chaos ensues, return up to one target instant or sorcery card from a graveyard to its owner's hand."),  # noqa: E501
    'Trail of the Mage-Rings': ('Plane — Vryn', "Instant and sorcery spells have rebound. (The spell's controller exiles the spell as it resolves if they cast it from their hand. At the beginning of that player's next upkeep, they may cast that card from exile without paying its mana cost.)\nWhenever chaos ensues, you may search your library for an instant or sorcery card, reveal it, put it into your hand, then shuffle."),  # noqa: E501
    'The Caldaia': ('Plane — Capenna', 'Creature spells you cast from your hand have blitz {3}. (If you cast a spell for its blitz cost, it gains haste and "When this creature dies, draw a card." Sacrifice it at the beginning of the next end step.)\nWhenever chaos ensues, return target creature card from your graveyard to your hand.'),  # noqa: E501
    'The Golden City of Orazca': ('Plane — Ixalan', "Ascend (If you control ten or more permanents, you get the city's blessing for the rest of the game.)\nWhenever one or more creatures you control deal combat damage to a player, create a Treasure token. Then draw a card if you have the city's blessing.\nWhenever chaos ensues, you may put a permanent card from your hand onto the battlefield tapped."),  # noqa: E501
    'Ghirapur': ('Plane — Avishkar', 'At the beginning of combat on your turn, until end of turn, each noncreature, non-Vehicle artifact you control becomes a 5/3 Vehicle in addition to its other types and gains trample, haste, and crew 2.\nWhenever chaos ensues, return target noncreature artifact card from your graveyard to your hand.'),  # noqa: E501
    'New New York': ('Plane — New Earth', 'At the beginning of combat on your turn, until end of turn, noncreature artifacts you control become 3/3 Vehicles in addition to their other types and gain flying, haste, and crew 1.\nWhenever chaos ensues, create a Treasure token and a 2/2 white Alien creature token.'),  # noqa: E501
    'Talon Gates': ('Plane — Dominaria', "Any time you could cast a sorcery, you may exile a nonland card from your hand with X time counters on it, where X is its mana value. If the exiled card doesn't have suspend, it gains suspend. (At the beginning of its owner's upkeep, they remove a time counter. When the last is removed, the player may cast it without paying its mana cost. If it's a creature, it has haste.)\nWhenever chaos ensues, remove two time counters from each suspended card you own."),  # noqa: E501
    'Windriddle Palaces': ('Plane — Belenon', "Players play with the top card of their libraries revealed.\nYou may play lands and cast spells from the top of any player's library.\nWhenever chaos ensues, each player mills a card."),  # noqa: E501
    'Glimmervoid Basin': ('Plane — Mirrodin', "Whenever a player casts an instant or sorcery spell with a single target, that player copies that spell for each other spell, permanent, card not on the battlefield, and/or player the spell could target. Each copy targets a different one of them.\nWhenever chaos ensues, choose target creature. Each player except that creature's controller creates a token that's a copy of that creature."),  # noqa: E501
    'Glen Elendra': ('Plane — Lorwyn', 'At end of combat, you may exchange control of target creature you control that dealt combat damage to a player this combat and target creature that player controls.\nWhenever chaos ensues, gain control of target creature you own.'),  # noqa: E501
    'Furnace Layer': ('Plane — New Phyrexia', 'When you planeswalk to Furnace Layer and at the beginning of your upkeep, select target player at random. That player discards a card. If that player discards a land card this way, they lose 3 life.\nWhenever chaos ensues, you may destroy target nonland permanent.'),  # noqa: E501
    'Grand Ossuary': ('Plane — Ravnica', 'Whenever a creature dies, its controller distributes a number of +1/+1 counters equal to its power among any number of target creatures they control.\nWhenever chaos ensues, each player exiles all creatures they control and creates X 1/1 green Saproling creature tokens, where X is the total power of the creatures they exiled this way. Then planeswalk.'),  # noqa: E501
    'Kharasha Foothills': ('Plane — Mongseng', "Whenever a creature you control attacks a player, for each other opponent, you may create a token that's a copy of that creature, tapped and attacking that opponent. Exile those tokens at the beginning of the next end step.\nWhenever chaos ensues, you may sacrifice any number of creatures. If you do, Kharasha Foothills deals that much damage to target creature."),  # noqa: E501
}
FULL = list(PLANES)
ALL = {**PLANES, "Krosa": BASE["Krosa"]}
EXTRA = [card(n, set_code="opca", number=f"PLF-{i}", layout="planar", type_line=t, oracle_text=o) for i, (n, (t, o)) in enumerate(ALL.items())]
EXTRA += [real("Runeclaw Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
          real("Typhoid Rats", "{B}", 1, "Creature — Rat", "Deathtouch", ("1", "1"), "B"),
          real("Battlegrowth", "{G}", 1, "Instant", "Put a +1/+1 counter on target creature.", None, "G"),
          real("Shock", "{R}", 1, "Instant", "Shock deals 2 damage to any target.", None, "R"),
          real("Mind Stone", "{2}", 2, "Artifact", "{T}: Add {C}.\n{1}, {T}, Sacrifice this artifact: Draw a card.", None, ""),
          real("Smuggler's Copter", "{2}", 2, "Artifact — Vehicle", "Flying\nCrew 1", ("3", "3"), ""),
          real("Shield Sphere", "{0}", 0, "Artifact Creature — Wall", "Defender\nWhenever this creature blocks, put a -0/-1 counter on it.", ("0", "1"), ""),
          real("Twin Bolt", "{1}{R}", 2, "Instant", "Twin Bolt deals 2 damage divided as you choose among one or two targets.", None, "R")]


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

    def choice(self, items: list):
        return items[0]


MINE = ((1, "Runeclaw Bear"), (1, "Typhoid Rats"), (1, "Battlegrowth"), (1, "Shock"), (1, "Mind Stone"), (1, "Smuggler's Copter"), (1, "Shield Sphere"),
        (1, "Twin Bolt"), (20, "Forest"))


def table(cards, planes: list[str], *, mine=MINE, bob=((2, "Runeclaw Bear"), (1, "Shock"), (10, "Island")), players=2) -> GameSession:
    alice = deck(cards, "Krenko, Mob Boss", list(mine))
    bob_deck = deck(cards, "Atraxa, Praetors' Voice", list(bob))
    carol = deck(cards, "Atraxa, Praetors' Voice", [(1, "Runeclaw Bear"), (12, "Island")])
    pool = [PlanarCard(printing_id=cards.resolve(n)["id"], name=n, phenomenon=ALL[n][0] == "Phenomenon") for n in planes]
    setups = [PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob_deck), PlayerSetup("Carol", cards=carol)][:players]
    state = new_game(setups, shuffle=False, first_player=0,
                     settings=GameSettings(planechase=True, planar_deck_size=len(pool)), planar_pool=lambda: pool, rng=_InOrder())
    enable(state)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def to_zone(s, c, zone, pid="p1"):
    act(s, pid, type="move", card_ids=[c.id], to={"player": c.owner, "zone": zone})
    return c


def plan(s, pid="p1"):
    return Plan(s.state, pid, s.cards, None)


def answer(s, pick=None, limit=40):
    """Resolve every decision (the first option, or ``pick(decision)``'s ids when it returns some) and pass until the stack is empty."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            return
        ids = pick(d) if pick is not None else None
        if ids is None:
            ids = [o.id for o in d.options[:max(1, d.min_choices or 1)]] if d.options else []
        act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


@pytest.mark.parametrize("name", FULL)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- Grixis: blue, black and/or red creature cards in your graveyard have unearth (702.84a) ------------------------------------------------
def test_grixis_unearth(cards):
    s = table(cards, ["Grixis", "Krosa"])
    rats = to_zone(s, named(s, "Typhoid Rats"), "graveyard")
    bear = to_zone(s, named(s, "Runeclaw Bear"), "graveyard")
    granted = next(a for a in plan(s).ch(rats).abilities if "unearth" in a.keywords)
    assert granted.text == "Unearth {B}"
    assert not any("unearth" in a.keywords for a in plan(s).ch(bear).abilities)  # (green)
    mana(s, B=1)
    act(s, "p1", type="activate_ability", card_id=rats.id, ability=granted.index, sources=[])
    settle(s)
    assert rats.zone == "p1:battlefield" and "haste" in plan(s).ch(rats).keywords
    check(s)


# -- Otaria: instant and sorcery cards in graveyards have flashback (702.34a) --------------------------------------------------------------
def test_otaria_flashback_for_each_owner(cards):
    from app.rules import graveyard_grants

    s = table(cards, ["Otaria", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    growth = to_zone(s, named(s, "Battlegrowth"), "graveyard")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id], sources=[])
    settle(s)
    assert bear.counters.get("+1/+1") == 1 and growth.zone == "p1:exile"  # (flashback: exiled, 702.34a)
    shock = to_zone(s, named(s, "Shock", "p2"), "graveyard", "p2")  # ("in graveyards": Bob's too; its owner casts it)
    assert graveyard_grants.flashback_costs(s.state, shock, plan(s, "p2").ch(shock), s.cards) == ["{R}"]
    check(s)


# -- Strixhaven: instant and sorcery spells players cast have demonstrate (702.144a) --------------------------------------------------------
def test_strixhaven_demonstrate_for_every_caster(cards):
    from app.rules import cast_limits

    s = table(cards, ["Strixhaven", "Krosa"])
    shock = to_zone(s, named(s, "Shock", "p2"), "hand", "p2")
    p2 = plan(s, "p2")
    assert cast_limits.granted_cascade(p2, shock.id, p2.ch(shock), "hand", "demonstrate") == 1  # (Bob is not the planar controller)
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    growth = to_zone(s, named(s, "Battlegrowth"), "hand")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id], sources=[])
    answer(s)  # (Alice copies it, Bob copies it too: three +1/+1 counters)
    assert bear.counters.get("+1/+1") == 3
    check(s)


# -- Trail of the Mage-Rings: instant and sorcery spells have rebound (702.88a) ------------------------------------------------------------
def test_trail_of_the_mage_rings_rebound(cards):
    s = table(cards, ["Trail of the Mage-Rings", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    growth = to_zone(s, named(s, "Battlegrowth"), "hand")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id], sources=[])
    settle(s)
    assert bear.counters.get("+1/+1") == 1 and growth.zone == "p1:exile" and growth.id in s.state.rules.rebounding
    act(s, "p1", type="planeswalk")  # (ruling 2013-04-15: the upkeep cast still happens after the plane is gone)
    to_turn(s, 3, phase="upkeep")
    answer(s)
    assert bear.counters.get("+1/+1") == 2 and growth.zone == "p1:graveyard"
    check(s)


# -- The Caldaia: creature spells you cast from your hand have blitz {3} (702.152a) ----------------------------------------------------------
def test_the_caldaia_blitz_three(cards):
    s = table(cards, ["The Caldaia", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "hand")
    offers = alt_costs.offers(s.state, "p1", bear, plan(s).ch(bear), s.cards)
    blitz = next(o for o in offers if o.tag == "blitz")
    assert blitz.alt.mana_cost.text() == "{3}"
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=bear.id, alt_cost=blitz.key, sources=[])
    settle(s)
    assert bear.zone == "p1:battlefield" and "haste" in plan(s).ch(bear).keywords
    hand = len(s.state.zones["p1:hand"])
    until(s, lambda cur: cur.state.cards[bear.id].zone == "p1:graveyard")  # (sacrificed at the next end step; it died: draw a card)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_the_caldaia_is_the_planar_controllers_only(cards):
    s = table(cards, ["The Caldaia", "Krosa"])
    bob_bear = to_zone(s, named(s, "Runeclaw Bear", "p2"), "hand", "p2")  # ("you": the planar controller only)
    assert not any(o.tag == "blitz" for o in alt_costs.offers(s.state, "p2", bob_bear, plan(s, "p2").ch(bob_bear), s.cards))


# -- Windriddle Palaces: play lands and cast spells from the top of any player's library ---------------------------------------------------
def test_windriddle_palaces_cast_from_another_players_library(cards):
    s = table(cards, ["Windriddle Palaces", "Krosa"])
    shock = named(s, "Shock", "p2")
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    to_zone(s, island, "library", "p2")
    to_zone(s, shock, "library", "p2")
    assert s.state.zones["p2:library"][0] == shock.id
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=shock.id, targets=["p2"], sources=[])
    settle(s)
    assert shock.zone == "p2:graveyard" and s.state.players["p2"].life == 38
    assert s.state.zones["p2:library"][0] == island.id
    act(s, "p1", type="play_land", card_id=island.id)  # (a land from Bob's library: Alice's land for the turn)
    assert island.zone.endswith(":battlefield") and island.controller == "p1"
    check(s)


def test_windriddle_palaces_only_the_planar_controller(cards):
    s = table(cards, ["Windriddle Palaces", "Krosa"])
    top = s.state.cards[s.state.zones["p1:library"][0]]
    act(s, "p1", type="pass_priority")
    with pytest.raises(ActionError):
        act(s, "p2", type="play_land", card_id=top.id)


# -- The Golden City of Orazca: ascend on a plane (702.131b, ruling 2023-04-14) ------------------------------------------------------------
def test_golden_city_ascend(cards):
    s = table(cards, ["The Golden City of Orazca", "Krosa"])
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"]
    for f in forests[:9]:
        to_zone(s, f, "battlefield")
    settle(s)
    assert not s.state.players["p1"].city_blessing
    act(s, "p1", type="play_land", card_id=to_zone(s, forests[9], "hand").id)  # (the tenth permanent: the blessing at once, no stack)
    assert s.state.players["p1"].city_blessing and not s.state.players["p2"].city_blessing
    check(s)


# -- Talon Gates: the special action (ruling 2012-06-01) ------------------------------------------------------------------------------------
def test_talon_gates_exile_with_time_counters(cards):
    s = table(cards, ["Talon Gates", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "hand")
    line = next(a for a in plan(s).ch(bear).abilities if a.index >= 100 and a.text.startswith("Talon Gates"))
    forest = to_zone(s, named(s, "Forest"), "hand")
    assert not any(a.text.startswith("Talon Gates") for a in plan(s).ch(forest).abilities)  # (nonland only)
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=line.index, sources=[])
    settle(s)
    assert bear.zone == "p1:exile" and bear.counters.get("time") == 2 and bear.id in s.state.rules.suspended
    rats = to_zone(s, named(s, "Typhoid Rats"), "hand")
    line = next(a for a in plan(s).ch(rats).abilities if a.text.startswith("Talon Gates"))
    act(s, "p1", type="set_stops", own=["main1", "end"], others=[], smart_pass=False)
    to_turn(s, 1, phase="end")
    with pytest.raises(ActionError):  # (any time you could cast a sorcery: not in the end step)
        act(s, "p1", type="activate_ability", card_id=rats.id, ability=line.index, sources=[])
    assert rats.zone == "p1:hand"
    check(s)


def to_attacks(s):
    until(s, lambda cur: cur.state.rules.decision is not None and cur.state.rules.decision.kind == "declare_attackers")


def stops(s, *steps):
    act(s, "p1", type="set_stops", own=list(steps), others=[], smart_pass=False)


# -- Furnace Layer: a target player selected at random (Scab-Clan Giant ruling 2013-04-15; Furnace Layer ruling 2012-06-01: you too) ---------
def test_furnace_layer_random_player_discards(cards, monkeypatch):
    from tests.test_rules_planechase_deck import roll

    s = table(cards, ["Krosa", "Furnace Layer"])
    to_zone(s, named(s, "Forest"), "hand")
    to_zone(s, next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"), "hand", "p2")
    hands = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2")}
    asked = []
    roll(s, monkeypatch, 1, seen=asked)  # (the planeswalker symbol: to Furnace Layer, its planeswalk trigger)
    assert s.state.cards[s.state.planechase.face_id].name == "Furnace Layer"
    assert not [d for d in asked if "target" in (d.kind or "")]  # (nobody chooses the target)
    after = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2")}
    assert sum(after.values()) == sum(hands.values()) - 1
    victim = next(p for p in after if after[p] == hands[p] - 1)
    gy = [s.state.cards[c] for c in s.state.zones[f"{victim}:graveyard"]]
    land = any("Land" in plan(s).ch(c).types for c in gy)
    assert s.state.players[victim].life == (37 if land else 40)
    check(s)


# -- Ghirapur / New New York: noncreature artifacts become Vehicles with P/T and crew until end of turn ------------------------------------------
@pytest.mark.parametrize("name, pt, keywords, crew, copter", [("Ghirapur", (5, 3), {"trample", "haste"}, 2, False),
                                                               ("New New York", (3, 3), {"flying", "haste"}, 1, True)])
def test_artifacts_become_vehicles(cards, name, pt, keywords, crew, copter):
    s = table(cards, [name, "Krosa"])
    stone = to_zone(s, named(s, "Mind Stone"), "battlefield")
    vehicle = to_zone(s, named(s, "Smuggler's Copter"), "battlefield")
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    stops(s, "main1", "begin_combat")
    to_turn(s, 1, phase="begin_combat")
    settle(s)
    ch = plan(s).ch(stone)
    assert "Vehicle" in ch.subtypes and "Artifact" in ch.types and not ch.is_creature and keywords <= set(ch.keywords)
    line = next(a for a in ch.abilities if "crew" in a.keywords)
    assert line.text.rstrip(".") == f"Crew {crew}"
    assert "trample" not in plan(s).ch(vehicle).keywords
    assert any(a.text.rstrip(".") == "Crew 1" and a.index >= 100 for a in plan(s).ch(vehicle).abilities) is copter  # (Ghirapur: not a Vehicle already)
    act(s, "p1", type="activate_ability", card_id=stone.id, ability=line.index, sources=[])
    settle(s)
    ch = plan(s).ch(stone)
    assert bear.tapped and ch.is_creature and ch.pt == pt
    check(s)


# -- Grand Ossuary: the ability's controller targets and divides (ruling 2012-06-01) among the dead creature's controller's creatures --------------
def test_grand_ossuary_counters_on_the_dead_creatures_controllers_creatures(cards):
    s = table(cards, ["Grand Ossuary", "Krosa"])
    mine = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    dead, other = [to_zone(s, b, "battlefield", "p2") for b in s.state.cards.values() if b.name == "Runeclaw Bear" and b.owner == "p2"]
    shock = to_zone(s, named(s, "Shock"), "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=shock.id, targets=[dead.id], sources=[])
    asked = []
    answer(s, pick=lambda d: asked.append(d) or None)
    assert dead.zone == "p2:graveyard"
    picks = [d for d in asked if any(o.id == other.id for o in d.options)]
    assert picks and all(d.player == "p1" for d in picks) and not any(o.id == mine.id for d in picks for o in d.options)
    assert other.counters.get("+1/+1") == 2 and not mine.counters.get("+1/+1")
    check(s)


# -- Kharasha Foothills: a copy for each other opponent, each optional, attacking that opponent ------------------------------------------------
def test_kharasha_foothills_copies_attack_the_other_opponents(cards):
    s = table(cards, ["Kharasha Foothills", "Krosa"], players=3)
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    to_turn(s, 4)  # (Alice's next turn: the bear can attack)
    to_attacks(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    asked = []

    def pick(d):
        asked.append(d)
        return [next(o.id for o in d.options if o.id != "none")] if d.kind == "choose_one" else None

    answer(s, pick=pick)
    assert [d.player for d in asked if d.kind == "choose_one"] == ["p1"]  # (Carol only: Bob is the attacked player)
    tokens = [c for c in s.state.cards.values() if c.token and c.name == "Runeclaw Bear"]
    assert len(tokens) == 1 and tokens[0].tapped
    until(s, lambda cur: cur.state.turn.number > 4)
    assert s.state.players["p3"].life == 38 and s.state.players["p2"].life == 38  # (the copy attacked Carol, the bear Bob)
    assert not any((c := s.state.cards.get(t.id)) is not None and c.zone.endswith(":battlefield") for t in tokens)  # (exiled at the end step)
    check(s)


# -- Glen Elendra: exchange with a creature of the player the first creature dealt combat damage to ----------------------------------------------
def test_glen_elendra_exchanges_with_the_damaged_players_creature(cards):
    s = table(cards, ["Glen Elendra", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    theirs = to_zone(s, named(s, "Runeclaw Bear", "p2"), "battlefield", "p2")
    to_turn(s, 3)  # (Alice's next turn: the bear can attack)
    to_attacks(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    asked = []

    def pick(d):
        asked.append(d)
        ids = [o.id for o in d.options]
        if bear.id in ids and theirs.id not in ids:
            return [bear.id]
        if theirs.id in ids:
            return [theirs.id]
        return None

    until(s, lambda cur: cur.state.players["p2"].life == 38 or cur.state.turn.phase == "end_combat")
    answer(s, pick=pick)
    assert s.state.players["p2"].life == 38
    assert bear.controller == "p2" and theirs.controller == "p1"
    check(s)


# -- Glimmervoid Basin: a copy for each other legal target, controlled by the caster ----------------------------------------------------------------
def test_glimmervoid_basin_copies_for_each_other_target(cards):
    s = table(cards, ["Glimmervoid Basin", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    theirs = to_zone(s, named(s, "Runeclaw Bear", "p2"), "battlefield", "p2")
    shock = to_zone(s, named(s, "Shock"), "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=shock.id, targets=["p2"], sources=[])
    answer(s)
    assert s.state.players["p2"].life == 38 and s.state.players["p1"].life == 38  # (the original to Bob, a copy to Alice)
    assert bear.zone == "p1:graveyard" and theirs.zone == "p2:graveyard"
    check(s)


def test_glimmervoid_basin_only_one_legal_target_no_copy(cards):
    s = table(cards, ["Glimmervoid Basin", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    growth = to_zone(s, named(s, "Battlegrowth"), "hand")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id], sources=[])
    answer(s)
    assert bear.counters.get("+1/+1") == 1
    check(s)


def test_glen_elendra_no_legal_target_is_no_question(cards):
    s = table(cards, ["Glen Elendra", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    theirs = to_zone(s, named(s, "Runeclaw Bear", "p2"), "battlefield", "p2")
    stops(s, "main1", "end_combat", "main2")
    to_turn(s, 3)
    to_attacks(s)
    act(s, "p1", type="declare_attackers", attackers=[])  # (no combat damage this combat: no legal first target, 603.3d)
    asked = []
    until(s, lambda cur: cur.state.turn.phase == "main2" or bool(asked.append(cur.state.rules.decision)) and False)
    assert not [d for d in asked if d is not None]
    assert bear.controller == "p1" and theirs.controller == "p2"
    check(s)


def test_glen_elendra_the_damaged_player_has_no_creature(cards):
    s = table(cards, ["Glen Elendra", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    to_turn(s, 3)
    to_attacks(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    until(s, lambda cur: cur.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 38 and bear.controller == "p1"
    check(s)


def test_grand_ossuary_a_zero_power_creature_dies(cards):
    s = table(cards, ["Grand Ossuary", "Krosa"])
    sphere = to_zone(s, named(s, "Shield Sphere"), "battlefield")
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    shock = to_zone(s, named(s, "Shock"), "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=shock.id, targets=[sphere.id], sources=[])
    answer(s)  # (its power was 0: no counters to distribute, no target needed)
    assert sphere.zone == "p1:graveyard" and not bear.counters.get("+1/+1")
    check(s)


def test_kharasha_foothills_declined_copy(cards):
    s = table(cards, ["Kharasha Foothills", "Krosa"], players=3)
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    to_turn(s, 4)
    to_attacks(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    answer(s, pick=lambda d: ["none"] if d.kind == "choose_one" and any(o.id == "none" for o in d.options) else None)
    assert not [c for c in s.state.cards.values() if c.token and c.name == "Runeclaw Bear"]
    check(s)


def test_glimmervoid_basin_two_targets_no_trigger(cards):
    s = table(cards, ["Glimmervoid Basin", "Krosa"])
    bear = to_zone(s, named(s, "Runeclaw Bear"), "battlefield")
    theirs = to_zone(s, named(s, "Runeclaw Bear", "p2"), "battlefield", "p2")
    pair = to_zone(s, named(s, "Twin Bolt"), "hand")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=pair.id, targets=[bear.id, theirs.id], division=[1, 1], sources=[])
    answer(s)
    assert s.state.players["p1"].life == 40 and s.state.players["p2"].life == 40  # (two targets: no copies)
    assert bear.damage == 1 and theirs.damage == 1
    check(s)
