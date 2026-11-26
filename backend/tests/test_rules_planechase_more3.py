"""-- planechase more 3 (wave F2) -- the remaining lines of the Doctor Who planes and phenomena, Morphic Tide and a few promo planes
(app/rules/planar_more3.py), on real Oracle text with the rules engine on, then ``check`` (replay + save/load round trip)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings, PlanarCard
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_planechase import script
from tests.test_rules_conditionals import to_turn, until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check, mana

# Oracle text exactly as in the card database (data/cards.sqlite)
PLANES = {
    'Caught in a Parallel Universe': ('Phenomenon', "When you encounter Caught in a Parallel Universe, each player chooses a creature controlled by the player to their left. Each player creates a token that's a copy of the creature they chose, except it has menace. (Then planeswalk away from this phenomenon.)"),  # noqa: E501
    'Deceptive Divination': ('Plane — Secret Lair', 'Change the text of each sorcery spell and sorcery card not on the stack by replacing "sorcery" with "instant."\nWhenever chaos ensues, choose two target players. Each of them searches their library for a card, then shuffles and puts that card on top.'),  # noqa: E501
    'Finally! Left-Handed Magic Cards': ('Plane — Secret Lair', "Each creature's base power is equal to its printed toughness.\nEach creature's base toughness is equal to its printed power.\nWhenever chaos ensues, draw a card from the bottom of your library."),  # noqa: E501
    'Happy Yargle Day!': ('Plane — Secret Lair', "At the beginning of each player's end step, if that player doesn't control a creature named Yargle, Glutton of Urborg, that player puts a bargle counter on a creature they control. It becomes a copy of Yargle, Glutton of Urborg, except it isn't legendary.\nWhenever chaos ensues, choose Swords to Plowshares, Opt, Fatal Push, Anger of the Gods, or Explore at random. Copy the chosen card. You may cast the copy without paying its mana cost."),  # noqa: E501
    'Human—Time Lord Meta-Crisis': ('Phenomenon', "When you encounter Human—Time Lord Meta-Crisis, each player chooses one or two creatures they control. Each player creates a token that's a copy of the first creature they chose, except it isn't legendary. Then each player who chose a second creature puts a number of +1/+1 counters on the token they created equal to the power of the second creature they chose. (Then planeswalk away from this phenomenon.)"),  # noqa: E501
    'Imaginary Friends (Plane)': ('Plane — Secret Lair', "Players may cast spells as though they were other cards legal in this game's format with the same type and mana cost. (Mana cost includes color.)\nWhenever chaos ensues, exile cards from the top of your library until you reveal a nonland card. You may cast that card without paying its mana cost, but only as another card following this plane's first ability. Put the rest on the bottom of your library in a random order."),  # noqa: E501
    'Math is for Blockers (Plane)': ('Plane — Secret Lair', "Whenever a nontoken creature attacks, exile it. Return it to the battlefield under its owner's control tapped and attacking at the beginning of that player's next declare attackers step.\nWhenever chaos ensues, goad target creature. (Until your next turn, It attacks each combat if able and attacks a player other than you if able.)"),  # noqa: E501
    'Morphic Tide': ('Phenomenon', "When you encounter Morphic Tide, each player shuffles all permanents they own into their library, then reveals that many cards from the top of their library. Each player puts all artifact, creature, land, and planeswalker cards revealed this way onto the battlefield, then does the same for enchantment cards, then puts all cards revealed this way that weren't put onto the battlefield on the bottom of their library in any order. (Then planeswalk away from this phenomenon.)"),  # noqa: E501
    'No Way Out': ('Plane — Duskmourn', "No Way Out enters with three dread counters.\nYou can never leave — If a player would planeswalk while this plane has dread counters, chaos ensues instead.\nWhenever you roll the planar die, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\nWhenever Chaos ensures each player may turn a face-down permanent they control face-up. Remove a dread counter from this plane."),  # noqa: E501
    'Ood Sphere': ('Plane — Horsehead Nebula', "Song of the Ood — Noncreature spells have convoke. (A player's creatures can help cast those spells. Each creature they tap while casting a noncreature spell pays for {1} or one mana of that creature's color.)\nRed-Eye — Whenever chaos ensues, for each opponent, goad up to one target creature that opponent controls. Until your next turn, those creatures can't become tapped unless they're being declared as attackers."),  # noqa: E501
    'Singing Towers of Darillium': ('Plane — Darillium', 'Each nonland card in your hand without foretell has foretell. Its foretell cost is equal to its mana cost reduced by {2}. (During your turn, you may pay {2} and exile it from your hand face down. Cast it on a later turn for its foretell cost.)\nWhenever chaos ensues, you may cast a foretold card you own from exile without paying its mana cost this turn.'),  # noqa: E501
    "The Doctor's Childhood Barn": ('Plane — Gallifrey', "Creatures enter tapped.\nWhenever chaos ensues, for each opponent, choose up to one target nonland permanent that opponent controls. Untap those permanents. They phase out. They can't phase in for as long as The Doctor's Childhood Barn remains face up. When a player planeswalks, those permanents phase in."),  # noqa: E501
    'The Matrix of Time': ('Plane — Gallifrey', "When you planeswalk to The Matrix of Time, each player exiles the top card of their library.\nDuring your turn, you may play lands and cast spells from among cards exiled with The Matrix of Time.\nWhenever you play a land or cast a spell from among cards exiled with The Matrix of Time, that card's owner loses 3 life and exiles the top card of their library.\nWhenever chaos ensues, create two Treasure tokens."),  # noqa: E501
    'The Moonbase': ('Plane — Moon', 'Low Gravity — All creatures have "{2}: This creature gains flying until end of turn. Activate only as a sorcery."\nWhenever chaos ensues, for each opponent, choose up to one target creature card in that player\'s graveyard. Put those cards onto the battlefield face down under your control. They\'re 2/2 Cyberman artifact creatures.'),  # noqa: E501
    'Two Streams Facility': ('Plane — Apalapucia', 'Whenever you planeswalk to Two Streams Facility and at the beginning of the first upkeep of the game, each player chooses green anchor or red waterfall.\nEach player who last chose green anchor may play an additional land during each of their turns.\nCreatures controlled by players who last chose red waterfall get +2/+0 and have haste.\nWhenever chaos ensues, each player who last chose green anchor chooses red waterfall, and vice versa.'),  # noqa: E501
    'sAnS mERcY': ('pLAnE — sECreT LaIR', "wHeN YoU pLAnESWalK tO tHIs pLAnE, eACh pLAyER cHoOSeS a nOnBlACk cREaTuRE tHEy cONtrOl. dEsTRoy tHOsE cREatUReS.\nwHeNEveR cHoAS EnSUEs, pERfoRm tHe foLLowiNG pROceSs X tiMEs, wHErE X iS tHe nUmBEr oF tImeS yOU'vE roLLeD tHe PlaNAr diE tHIs tuRN. eAcH oPPonENt LOseS 3 LiFE uNLeSs tHAt pLAyEr sAcRiFicEs A nOnLaND pErManENt OR diSCaRds a cArD."),  # noqa: E501
    'Academy at Tolaria West': ('Plane — Dominaria', 'At the beginning of your end step, if you have no cards in hand, draw seven cards.\nWhenever chaos ensues, discard your hand.'),  # noqa: E501
}
FILLER = "Academy at Tolaria West"
EXTRA = [card(n, set_code="opca", number=f"PF2-{i}", layout="planar", type_line=t, oracle_text=o) for i, (n, (t, o)) in enumerate(PLANES.items())]
EXTRA += [real("Runeclaw Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
          real("Craw Wurm", "{4}{G}{G}", 6, "Creature — Wurm", "", ("6", "4"), "G"),
          real("Serra Angel", "{3}{W}{W}", 5, "Creature — Angel", "Flying, vigilance", ("4", "4"), "W"),
          real("Isamaru, Hound of Konda", "{W}", 1, "Legendary Creature — Dog", "", ("2", "2"), "W"),
          real("Elvish Mystic", "{G}", 1, "Creature — Elf Druid", "{T}: Add {G}.", ("1", "1"), "G"),
          real("Opt", "{U}", 1, "Instant", "Scry 1.\nDraw a card.", None, "U"),
          real("Divination", "{2}{U}", 3, "Sorcery", "Draw two cards.", None, "U"),
          real("Pacifism", "{1}{W}", 2, "Enchantment — Aura", "Enchant creature\nEnchanted creature can't attack or block.", None, "W"),
          real("Mind Stone", "{2}", 2, "Artifact", "{T}: Add {C}.\n{1}, {T}, Sacrifice Mind Stone: Draw a card.", None, "")]


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


def table(cards, planes: list[str], players: int = 3) -> GameSession:
    alice = deck(cards, "Krenko, Mob Boss", [(3, "Runeclaw Bear"), (1, "Craw Wurm"), (1, "Serra Angel"), (1, "Isamaru, Hound of Konda"), (1, "Opt"),
                                             (1, "Divination"), (1, "Pacifism"), (1, "Mind Stone"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(2, "Runeclaw Bear"), (1, "Craw Wurm"), (1, "Elvish Mystic"), (1, "Opt"), (10, "Island")])
    carol = deck(cards, "Krenko, Mob Boss", [(2, "Runeclaw Bear"), (1, "Serra Angel"), (10, "Forest")])
    pool = [PlanarCard(printing_id=cards.resolve(n)["id"], name=n, phenomenon=PLANES[n][0] == "Phenomenon") for n in planes]
    setups = [PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)][:players]
    state = new_game(setups, shuffle=False, first_player=0, settings=GameSettings(planechase=True, planar_deck_size=len(pool)),
                     planar_pool=lambda: pool, rng=_InOrder())
    enable(state)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def resolve(s, picks=()):
    """Everything resolves; a choice takes the ``picks`` (ids, card ids or labels, in this order of preference) when offered, else the
    fewest it may."""
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            chosen = [o.id for p in picks for o in d.options if p in (o.id, o.card_id, o.label)][: d.max_choices]
            if len(chosen) < d.min_choices:
                chosen = [o.id for o in d.options][: d.min_choices]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def roll(s, monkeypatch, value, picks=()):
    """Alice rolls the planar die for the server's d6 ``value`` (1 planeswalker, 2 chaos, 3-6 blank), paying its cost (901.9)."""
    from app.game.handlers.planechase import roll_cost

    if cost := roll_cost(s.state):
        mana(s, C=cost)
    script(monkeypatch, [value])
    act(s, "p1", type="roll_planar_die")
    resolve(s, picks)


def face(s):
    return s.state.cards[s.state.planechase.face_id]


def place(s, name, pid="p1"):
    """One more card named ``name`` of ``pid``'s (not on the battlefield yet) onto the battlefield."""
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith((":battlefield", ":command")))
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def to_zone(s, name, zone, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith((f":{zone}", ":command")))
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": zone})
    return c


def on_battlefield(s, name, pid=None):
    return [c for c in s.state.cards.values() if c.name == name and c.zone.endswith(":battlefield") and (pid is None or c.controller == pid)]


def plan(s, pid="p1"):
    return Plan(s.state, pid, s.cards, None)


def stats(s, c):
    from app.rules import sba

    card = s.state.cards[c.id]
    ch = plan(s).ch(card)
    return sba.power(card, ch), sba.toughness(card, ch)


FULL = ["Caught in a Parallel Universe", "Human—Time Lord Meta-Crisis", "Morphic Tide", "The Moonbase", "The Doctor's Childhood Barn",
        "Two Streams Facility", "Singing Towers of Darillium", "The Matrix of Time", "sAnS mERcY", "Math is for Blockers (Plane)", "Ood Sphere"]


@pytest.mark.parametrize("name", FULL)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- Caught in a Parallel Universe: each player copies a creature of the player to their left, with menace --------------------------------
def test_caught_in_a_parallel_universe_each_player_copies_their_left_neighbours_creature(cards, monkeypatch):
    s = table(cards, [FILLER, "Caught in a Parallel Universe"])
    p = plan(s)
    left = {pid: p.left(pid) for pid in ("p1", "p2", "p3")}
    mine = {"p1": place(s, "Isamaru, Hound of Konda", "p1"), "p2": place(s, "Craw Wurm", "p2"), "p3": place(s, "Serra Angel", "p3")}
    extra = place(s, "Runeclaw Bear", left["p1"])  # (Alice's left neighbour has two creatures: she chooses)
    roll(s, monkeypatch, 1, picks=[extra.id])  # 901.8: planeswalk to the phenomenon: encountered (312.5), then away (704.6f)
    tokens = {pid: [c for c in s.state.cards.values() if c.is_token and c.controller == pid and c.zone.endswith(":battlefield")] for pid in left}
    assert [t.name for t in tokens["p1"]] == ["Runeclaw Bear"]
    for pid in ("p2", "p3"):
        assert [t.name for t in tokens[pid]] == [mine[left[pid]].name]
    assert all("menace" in plan(s).ch(t).keywords for ts in tokens.values() for t in ts)
    assert face(s).name == FILLER
    check(s)


# -- Human—Time Lord Meta-Crisis: a non-legendary copy of the first, counters equal to the second's power ----------------------------------
def test_meta_crisis_copies_the_first_and_counts_the_second(cards, monkeypatch):
    s = table(cards, [FILLER, "Human—Time Lord Meta-Crisis"], players=2)
    isamaru = place(s, "Isamaru, Hound of Konda")
    wurm = place(s, "Craw Wurm")
    bear = place(s, "Runeclaw Bear", "p2")
    roll(s, monkeypatch, 1, picks=[isamaru.id, wurm.id])
    alice = [c for c in on_battlefield(s, "Isamaru, Hound of Konda", "p1") if c.is_token]
    assert len(alice) == 1 and "Legendary" not in plan(s).ch(alice[0]).supertypes
    assert alice[0].counters.get("+1/+1") == 6  # (Craw Wurm's power)
    bob = [c for c in on_battlefield(s, "Runeclaw Bear", "p2") if c.is_token]
    assert len(bob) == 1 and not bob[0].counters.get("+1/+1")  # (Bob had one creature: no second)
    assert isamaru.zone == "p1:battlefield" and bear.zone == "p2:battlefield"
    check(s)


# -- Morphic Tide: Warp World with planeswalkers ---------------------------------------------------------------------------------------------
def test_morphic_tide_reshuffles_every_players_permanents(cards, monkeypatch):
    s = table(cards, [FILLER, "Morphic Tide"], players=2)
    for name in ("Runeclaw Bear", "Mind Stone", "Forest"):
        place(s, name)
    place(s, "Island", "p2")
    before = {pid: sum(1 for c in s.state.cards.values() if c.owner == pid and c.zone.endswith(":battlefield")) for pid in ("p1", "p2")}
    roll(s, monkeypatch, 1)
    after = {pid: [c for c in s.state.cards.values() if c.owner == pid and c.zone.endswith(":battlefield")] for pid in ("p1", "p2")}
    assert before == {"p1": 3, "p2": 1}
    assert all(0 < len(after[p]) <= before[p] for p in after)  # (that many revealed; the permanent cards among them enter)
    assert all(not ({"Instant", "Sorcery"} & set(plan(s).ch(c).types)) for cs in after.values() for c in cs)
    assert face(s).name == FILLER
    check(s)


# -- The Moonbase: per opponent, a creature card from their graveyard face down as a 2/2 Cyberman -------------------------------------------
def test_the_moonbase_chaos_returns_graveyard_creatures_face_down_as_cybermen(cards, monkeypatch):
    s = table(cards, ["The Moonbase", FILLER])
    wurm = to_zone(s, "Craw Wurm", "graveyard", "p2")
    angel = to_zone(s, "Serra Angel", "graveyard", "p3")
    roll(s, monkeypatch, 2, picks=[wurm.id, angel.id])
    for c in (wurm, angel):
        c = s.state.cards[c.id]
        assert c.zone == "p1:battlefield" and c.controller == "p1" and c.face_down
        ch = plan(s).ch(c)
        assert stats(s, c) == (2, 2) and {"Artifact", "Creature"} <= set(ch.types) and "Cyberman" in ch.subtypes
    check(s)


# -- The Doctor's Childhood Barn: phased out while it is face up; a planeswalk's delayed trigger phases them in -----------------------------
def test_the_doctors_childhood_barn_phases_out_until_a_planeswalk(cards, monkeypatch):
    s = table(cards, ["The Doctor's Childhood Barn", FILLER])
    wurm = place(s, "Craw Wurm", "p2")
    act(s, "p2", type="tap", card_ids=[wurm.id], tapped=True)
    angel = place(s, "Serra Angel", "p3")
    roll(s, monkeypatch, 2, picks=[wurm.id, angel.id])
    assert s.state.cards[wurm.id].zone == "p2:phased" and not s.state.cards[wurm.id].tapped  # (untapped, then phased out)
    assert s.state.cards[angel.id].zone == "p3:phased"
    to_turn(s, 2)  # Bob's untap step: the Barn is still face up, his Wurm stays phased out
    assert s.state.cards[wurm.id].zone == "p2:phased"
    to_turn(s, 4)
    until(s, lambda s: s.state.turn.phase == "main1")
    roll(s, monkeypatch, 1)  # Alice planeswalks: the delayed trigger phases them in
    assert s.state.cards[wurm.id].zone == "p2:battlefield" and s.state.cards[angel.id].zone == "p3:battlefield"
    check(s)


# -- Ood Sphere: every player's noncreature spells have convoke --------------------------------------------------------------------------
def test_ood_sphere_noncreature_spells_have_convoke(cards):
    from app.rules import cast_limits

    s = table(cards, ["Ood Sphere", FILLER], players=2)
    opt = to_zone(s, "Opt", "hand", "p2")
    creature = to_zone(s, "Craw Wurm", "hand", "p2")
    p = plan(s, "p2")
    assert "convoke" in cast_limits.granted_helpers(s.state, "p2", opt.id, p.ch(opt), s.cards)
    assert "convoke" not in cast_limits.granted_helpers(s.state, "p2", creature.id, p.ch(creature), s.cards)
    check(s)


# -- Singing Towers of Darillium: chaos lets you cast a foretold card for free this turn -----------------------------------------------------
def test_singing_towers_chaos_casts_a_foretold_card_free(cards, monkeypatch):
    s = table(cards, ["Singing Towers of Darillium", FILLER], players=2)
    wurm = to_zone(s, "Craw Wurm", "hand")
    ability = next(a for a in plan(s).ch(wurm).abilities if "foretell" in a.keywords)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=wurm.id, ability=ability.index, sources=[])
    resolve(s)
    assert s.state.cards[wurm.id].zone == "p1:foretell"
    roll(s, monkeypatch, 2)
    act(s, "p1", type="cast_spell", card_id=wurm.id, sources=[], free=True)  # (this turn, though foretold this turn; no mana)
    resolve(s)
    assert s.state.cards[wurm.id].zone == "p1:battlefield"
    check(s)


# -- Two Streams Facility: green anchor or red waterfall --------------------------------------------------------------------------------
def test_two_streams_facility_choices_lands_pump_and_chaos_swap(cards, monkeypatch):
    from app.rules import land_plays

    s = table(cards, [FILLER, "Two Streams Facility"], players=2)
    bear = place(s, "Runeclaw Bear")
    bobs = place(s, "Runeclaw Bear", "p2")
    roll(s, monkeypatch, 1, picks=["red waterfall"])  # planeswalk to it: Alice chooses red waterfall; Bob too (the same pick), then …
    assert face(s).name == "Two Streams Facility"
    assert s.state.rules.planar_more3_f2["streams"]["choices"] == {"p1": "waterfall", "p2": "waterfall"}
    assert stats(s, bear) == (4, 2) and "haste" in plan(s).ch(bear).keywords and stats(s, bobs) == (4, 2)
    assert land_plays.allowed(s.state, "p1", s.cards) == 1
    roll(s, monkeypatch, 2)  # chaos: each choice flips
    assert stats(s, bear) == (2, 2) and "haste" not in plan(s).ch(bear).keywords
    assert land_plays.allowed(s.state, "p1", s.cards) == 2 and land_plays.allowed(s.state, "p2", s.cards) == 2
    check(s)


def test_two_streams_facility_first_upkeep_of_the_game(cards):
    s = table(cards, ["Two Streams Facility", FILLER], players=2)  # (face up as the game begins: its first upkeep asks)
    resolve(s, picks=["green anchor"])
    s2 = s.state.rules.planar_more3_f2.get("streams")
    assert s2 is not None and set(s2["choices"]) == {"p1", "p2"}
    check(s)


# -- The Matrix of Time: casting one of its exiled cards costs that card's owner 3 life and exiles their next card --------------------------
def test_the_matrix_of_time_a_card_cast_from_its_exile_costs_its_owner(cards, monkeypatch):
    s = table(cards, [FILLER, "The Matrix of Time"], players=2)
    roll(s, monkeypatch, 1)  # planeswalk to it: each player exiles the top card of their library (both Runeclaw Bears)
    assert face(s).name == "The Matrix of Time"
    bobs = next(c for c in s.state.cards.values() if c.zone == "p2:exile")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bobs.id, sources=[])
    resolve(s)
    assert s.state.cards[bobs.id].zone == "p1:battlefield"
    assert s.state.players["p2"].life == 37 and s.state.players["p1"].life == 40  # (the card's owner: Bob)
    nxt = [c for c in s.state.cards.values() if c.zone == "p2:exile"]
    assert len(nxt) == 1 and nxt[0].id != bobs.id
    mana(s, G=1, C=1)  # (Bob's second exiled card is linked to the plane too, 607.2a: Alice may cast it)
    act(s, "p1", type="cast_spell", card_id=nxt[0].id, sources=[])
    resolve(s)
    assert s.state.players["p2"].life == 34
    check(s)


# -- sAnS mERcY: its odd case is only flavor --------------------------------------------------------------------------------------------
def test_sans_mercy_destroys_a_chosen_nonblack_creature_each_then_chaos_repeats_per_roll(cards, monkeypatch):
    from app.game.handlers import planechase

    assert planechase.is_planar(PLANES["sAnS mERcY"][0])
    s = table(cards, [FILLER, "sAnS mERcY"], players=2)
    bear = place(s, "Runeclaw Bear")
    wurm = place(s, "Craw Wurm", "p2")
    roll(s, monkeypatch, 1)  # planeswalk to it: each player's only nonblack creature is destroyed
    assert face(s).name == "sAnS mERcY"
    assert s.state.cards[bear.id].zone == "p1:graveyard" and s.state.cards[wurm.id].zone == "p2:graveyard"
    for c in [c for c in s.state.cards.values() if c.zone == "p2:hand"]:
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "library"})
    roll(s, monkeypatch, 2)  # chaos on the second roll this turn: the process twice; Bob has nothing to sacrifice or discard
    assert s.state.players["p2"].life == 34 and s.state.players["p1"].life == 40
    check(s)


# -- Math is for Blockers: an attacking nontoken creature is exiled, back tapped and attacking at its owner's next declare attackers step -----
def test_math_is_for_blockers_exiles_attackers_until_the_next_declare_attackers_step(cards):
    s = table(cards, ["Math is for Blockers (Plane)", FILLER], players=2)
    bear = place(s, "Runeclaw Bear")
    wurm = place(s, "Craw Wurm")  # (it stays home on turn 3; Alice attacks with it on turn 5)
    to_turn(s, 3)

    def attackers_step(s):
        return s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"

    until(s, attackers_step)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    resolve(s)
    assert s.state.cards[bear.id].zone == "p1:exile"
    to_turn(s, 5)
    until(s, attackers_step)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": wurm.id, "target": "p2"}])  # (the Wurm is exiled in turn too)
    resolve(s, picks=["p2"])
    back = s.state.cards[bear.id]
    assert back.zone == "p1:battlefield" and back.tapped
    assert s.state.players["p2"].life == 38  # (it came back attacking, 508.4, and dealt its combat damage; the Wurm was exiled)
    assert s.state.cards[wurm.id].zone == "p1:exile"
    check(s)


# -- Ood Sphere (Red-Eye): goaded, and can't become tapped unless declared as an attacker until your next turn ----------------------------------
def test_ood_sphere_red_eye_goads_and_stops_tapping_but_attacking(cards, monkeypatch):
    from app.game.errors import ActionError

    s = table(cards, ["Ood Sphere", FILLER], players=2)
    elf = place(s, "Elvish Mystic", "p2")
    roll(s, monkeypatch, 2, picks=[elf.id])
    assert s.state.rules.planar_more3_f2.get("ood")
    to_turn(s, 2)
    until(s, lambda s: s.state.turn.phase == "main1")
    with pytest.raises(ActionError, match="Ood Sphere"):  # (a cost: its own {T} mana ability, ruling 2023-10-13)
        act(s, "p2", type="activate_ability", card_id=elf.id, ability=0)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": elf.id, "target": "p1"}])  # (goaded: it must attack; declared, it taps)
    assert s.state.cards[elf.id].tapped
    to_turn(s, 3)  # Alice's next turn: the restriction is over
    assert not s.state.rules.planar_more3_f2.get("ood")
    check(s)
