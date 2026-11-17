"""-- Mystery Booster Commander (wave MBC-B) -- the lines of app/rules/mbc_b.py on real Oracle text (Scryfall / data/cards.sqlite) with the rules
engine on: Rikala, Balefang, Venser, Selenia, Flitwing, Meatsqueak, Ekthi, Elda, The Muckslinger Gang, Jandor, Homer, Massimo, Matoc and Sahir.
Each scenario ends with ``check`` (the replay, and a save and a load)."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act, deck, enable, mana_pool
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import stops, to_phase
from tests.wave9c_kit import check, mana

EXTRA = [
    real("Rikala, Homarid King", "{1}{G}{U}", 3, "Legendary Creature — Lobster Noble", "At the beginning of your upkeep, put a tide counter on Rikala. Then if there are four or more tide counters on Rikala, remove them.\nCreatures you control get +1/+0 for each tide counter on Rikala.\nWhenever you tap an Island for mana, if there are three or more tide counters on Rikala, add an additional {U}.", ("0", "4"), "GU"),  # noqa: E501
    real("Balefang the Unslayable", "{3}{R}{R}", 5, "Legendary Creature — Demon Dragon", "Flying, trample, protection from Angels and from Archons\nPlayers can't gain life.\nWhen Balefang enters, target opponent creates a tapped Baneslayer Angel token. The token is goaded for the rest of the game. (It's a {3}{W}{W} 5/5 Angel creature with flying, first strike, lifelink, and protection from Demons and from Dragons.)", ("5", "5"), "R"),  # noqa: E501
    {**real("Venser, Visionary Traveler", "{3}{W}{U}", 5, "Legendary Planeswalker — Venser", "Each nontoken creature you control that wasn't cast from your hand enters with two additional +1/+1 counters on it.\n+1: Exile up to one other target permanent you control. At the beginning of the next end step, return that card to the battlefield under its owner's control.\n−2: For each opponent, return up to one target nonland permanent that player controls to its owner's hand.\nVenser, Visionary Traveler can be your commander.", None, "UW"), "loyalty": "4"},  # noqa: E501
    real("Selenia, the Cursed Heart", "{4}{W}{B}", 6, "Legendary Creature — Angel Warrior", "Flying, lifelink\nIf you would gain life, you gain twice that much life instead.\nWhen Selenia dies, create a legendary black Aura Curse enchantment token named Selenia's Curse attached to target opponent. The token has enchant player and \"If enchanted player would lose life, they lose twice that much life instead.\"", ("2", "5"), "BW"),  # noqa: E501
    real("Flitwing, Lyev Detective", "{2}{U}", 3, "Legendary Creature — Faerie Detective", "Flying\nIf you would create one or more tokens, you may create that many Clue tokens instead. (They're artifacts with \"{2}, Sacrifice this token: Draw a card.\")", ("1", "1"), "U"),  # noqa: E501
    real("Meatsqueak, Hoard Lord", "{2}{G}", 3, "Legendary Creature — Squirrel", "Whenever another creature dies, create a Food token. This ability triggers only once each turn. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nFor every seven Foods you control, Squirrels you control get +3/+3.", ("2", "3"), "G"),  # noqa: E501
    real("Ekthi, Contaminator Priest", "{3}{W}", 4, "Legendary Creature — Phyrexian Cleric", "Other Phyrexians you control get +1/+1.\nEach Equipment you control has living weapon. (Whenever an Equipment you control enters, create a 0/0 black Phyrexian Germ creature token, then attach that Equipment to it.)", ("3", "3"), "W"),  # noqa: E501
    real("Elda, Conjurer of Spectacle", "{2}{G}{W}", 4, "Legendary Creature — Human Wizard", "The first nonlegendary creature spell you cast each turn has demonstrate. (When you cast that spell, you may copy it. If you do, choose an opponent to also copy it. Each copy becomes a token.)", ("2", "2"), "GW"),  # noqa: E501
    real("The Muckslinger Gang", "{1}{B}{R}{G}", 4, "Legendary Creature — Goblin Lizard Beast", "Each other creature you control gets +3/+3 as long as it's not attacking or blocking.\nCreature spells you control and creature cards you own in any zone other than the battlefield or the stack get +3/+3.", ("3", "3"), "BGR"),  # noqa: E501
    real("Jandor, Fortuned Traveler", "{1}{R}{G}{W}", 4, "Legendary Creature — Human Citizen", "Each Beast, Camel, Horse, Elephant, and Wolf creature you control is a Mount in addition to its other types and has saddle 2. (Tap any number of other creatures you control with total power 2 or more: That Mount becomes saddled until end of turn. Saddle only as a sorcery.)\nWhenever a saddled creature you control attacks, it gets +2/+2 until end of turn. Draw a card. Create a Food token.", ("2", "4"), "GRW"),  # noqa: E501
    real("Homer, the Hermit", "{B}{G}{U}", 3, "Legendary Creature — Crab Druid", "Landfall — Whenever a land you control enters, any number of target players each mill X cards, where X is twice the number of Crabs, Lobsters, Nautiluses, Starfish, and/or Trilobites you control.", ("0", "9"), "BGU"),  # noqa: E501
    real("Massimo, the Magician", "{U}{R}{W}", 3, "Legendary Creature — Cat Wizard", "Whenever Massimo or another creature you control enters, exile up to one target instant or sorcery card with mana value 1 from your graveyard. If a card is exiled this way, that creature gains \"Whenever this creature deals combat damage to a player, copy the exiled card. You may cast the copy without paying its mana cost.\"", ("3", "2"), "RUW"),  # noqa: E501
    real("Matoc, Lavamancer", "{3}{R}", 4, "Legendary Creature — Human Barbarian Wizard", "Whenever a source you control deals damage, if at least one permanent or player was dealt exactly 2 of that damage, exile the top card of your library. You may play it until the end of your next turn.\n{R}, {T}, Exile two cards from your graveyard: Matoc deals 2 damage to any other target.", ("2", "3"), "R"),  # noqa: E501
    real("Sahir, Visitor in Darkness", "{1}{B}{B}", 3, "Legendary Creature — Human Wizard", "Eminence — At the beginning of your upkeep, Sahir deals 1 damage to you. This ability triggers only if Sahir is in the command zone or on the battlefield.\nWhenever a source you control deals exactly 1 damage to you and whenever a spell or ability you control causes you to lose exactly 1 life, put a +1/+1 counter on Sahir. If this is the second time this ability has resolved this turn, draw a card.", ("3", "3"), "B"),  # noqa: E501
    # (helpers, real Oracle text)
    real("Trained Armodon", "{1}{G}{G}", 3, "Creature — Elephant", "", ("3", "3"), "G"),
    real("Fortress Crab", "{3}{U}", 4, "Creature — Crab", "", ("1", "6"), "U"),
    real("Bonesplitter", "{1}", 1, "Artifact — Equipment", "Equipped creature gets +2/+0.\nEquip {1}", None, ""),
    real("Squirrel Sovereign", "{1}{G}", 2, "Creature — Squirrel Noble", "Other Squirrels you control get +1/+1.", ("2", "2"), "G"),
    real("Phyrexian Arena", "{1}{B}{B}", 3, "Enchantment", "At the beginning of your upkeep, you draw a card and you lose 1 life.", None, "B"),
    real("Sign in Blood", "{B}{B}", 2, "Sorcery", "Target player draws two cards and loses 2 life.", None, "B"),
]
CARDS = [c["name"] for c in EXTRA[:14]]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", CARDS)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- table helpers ---------------------------------------------------------------------------------------------------------------------------
def table(cards, mine=(), theirs=(), commander="Krenko, Mob Boss"):
    """Alice (first) and Bob, rules on, Alice's first main phase."""
    alice = deck(cards, commander, [*((1, n) for n in mine), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False, first_player=0)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def put(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def to_zone(s, name, zone, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": zone})
    return s.state.cards[c.id]


def cast(s, card, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=card.id, **kw)


def ch(s, card, pid="p1"):
    return Plan(s.state, pid, s.cards, None).ch(s.state.cards[card.id])


def pt_of(s, card):
    from app.rules import sba

    c = s.state.cards[card.id]
    got = ch(s, c, c.controller)
    return sba.power(c, got), sba.toughness(c, got)


def field(s, pid="p1", name=None):
    return [c for c in s.state.cards.values() if c.zone == f"{pid}:battlefield" and (name is None or c.name == name)]


def answer(s, pick):
    """Answer the open decision with the options ``pick`` returns (from the decision)."""
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=pick(d))


def resolve(s, pick=None, limit=40):
    """Resolve the stack; ``pick(d)`` answers a decision (None: its first options)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = pick(d) if pick is not None else None
            act(s, d.player, type="choose", decision_id=d.id,
                option_ids=ids if ids is not None else [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def opt(d, *words):
    """The ids of the options whose label contains every word."""
    return [o.id for o in d.options if all(w.lower() in (o.label or "").lower() for w in words)]


# -- Rikala ----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("tide", [3, 2])
def test_rikala_adds_an_extra_blue_only_with_three_tide_counters(cards, tide):
    s = table(cards, ["Rikala, Homarid King", "Island"])
    rikala = put(s, "Rikala, Homarid King")
    island = put(s, "Island")
    act(s, "p1", type="set_counter", card_id=rikala.id, kind="tide", value=tide)
    act(s, "p1", type="activate_ability", card_id=island.id, ability=0)
    resolve(s)
    assert mana_pool(s) == {"U": 2 if tide >= 3 else 1}
    check(s)


# -- Balefang --------------------------------------------------------------------------------------------------------------------------------
def test_balefang_gives_the_opponent_a_tapped_goaded_baneslayer_angel(cards):
    from app.rules.keyword_actions import goaded_by

    s = table(cards, ["Balefang the Unslayable"])
    bale = to_zone(s, "Balefang the Unslayable", "hand")
    mana(s, R=5)
    cast(s, bale)
    resolve(s, lambda d: opt(d, "Bob") or None)
    (angel,) = field(s, "p2", "Baneslayer Angel")
    c = ch(s, angel, "p2")
    assert angel.tapped and angel.controller == "p2" and pt_of(s, angel) == (5, 5)
    assert {"flying", "first strike", "lifelink"} <= set(c.keywords) and c.mana_cost == "{3}{W}{W}"
    assert "p1" in goaded_by(c)
    check(s)


# -- Venser ----------------------------------------------------------------------------------------------------------------------------------
def test_venser_counts_a_creature_not_cast_from_your_hand(cards):
    s = table(cards, ["Venser, Visionary Traveler", "Grizzly Bears", "Cloudshift"])
    venser = to_zone(s, "Venser, Visionary Traveler", "hand")
    mana(s, W=1, U=1, C=3)
    cast(s, venser)
    resolve(s)
    assert s.state.cards[venser.id].zone == "p1:battlefield"
    bears = to_zone(s, "Grizzly Bears", "hand")
    mana(s, G=2)
    cast(s, bears)
    resolve(s)
    bears = s.state.cards[bears.id]
    assert bears.zone == "p1:battlefield" and bears.counters.get("+1/+1", 0) == 0  # (cast from Alice's hand)
    shift = to_zone(s, "Cloudshift", "hand")
    mana(s, W=1)
    cast(s, shift, targets=[bears.id])
    resolve(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[bears.id].counters.get("+1/+1", 0) == 2  # (it returned: not cast)
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss" and c.owner == "p1")
    mana(s, R=4)
    cast(s, krenko)  # (cast from the command zone, not from a hand)
    resolve(s)
    assert s.state.cards[krenko.id].zone == "p1:battlefield" and s.state.cards[krenko.id].counters.get("+1/+1", 0) == 2
    check(s)


# -- Selenia ---------------------------------------------------------------------------------------------------------------------------------
def test_selenias_curse_doubles_the_life_its_player_loses(cards):
    s = table(cards, ["Selenia, the Cursed Heart", "Sign in Blood", "Lightning Bolt", "Murder"])
    selenia = put(s, "Selenia, the Cursed Heart")
    murder = to_zone(s, "Murder", "hand")
    mana(s, B=3)
    cast(s, murder, targets=[selenia.id])
    resolve(s, lambda d: opt(d, "Bob") or None)
    assert s.state.cards[selenia.id].zone == "p1:graveyard"
    (curse,) = field(s, "p1", "Selenia's Curse")
    c = ch(s, curse)
    assert curse.attached_player == "p2" and "Legendary" in c.supertypes and {"Aura", "Curse"} <= set(c.subtypes) and set(c.colors) == {"B"}
    sign = to_zone(s, "Sign in Blood", "hand")
    life, mine = s.state.players["p2"].life, s.state.players["p1"].life
    mana(s, B=2)
    cast(s, sign, targets=["p2"])
    resolve(s)
    assert s.state.players["p2"].life == life - 4  # (loses twice 2)
    life = s.state.players["p2"].life
    bolt = to_zone(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    cast(s, bolt, targets=["p2"])
    resolve(s)
    assert s.state.players["p2"].life == life - 6  # (the life damage makes it lose is doubled too, 120.3a)
    assert s.state.players["p1"].life == mine  # (only the enchanted player's)
    check(s)


# -- Flitwing --------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("apply", [True, False])
def test_flitwing_may_make_clues_instead(cards, apply):
    s = table(cards, ["Flitwing, Lyev Detective", "Raise the Alarm"])
    put(s, "Flitwing, Lyev Detective")
    alarm = to_zone(s, "Raise the Alarm", "hand")
    mana(s, W=2)
    cast(s, alarm)
    resolve(s, lambda d: opt(d, "Apply" if apply else "Decline") or None)
    assert len(field(s, "p1", "Clue")) == (2 if apply else 0)
    assert len(field(s, "p1", "Soldier")) == (0 if apply else 2)
    check(s)


# -- Meatsqueak ------------------------------------------------------------------------------------------------------------------------------
FOOD = {"name": "Food", "type_line": "Token Artifact — Food", "text": "{2}, {T}, Sacrifice this token: You gain 3 life.", "colors": []}


@pytest.mark.parametrize("foods,bonus", [(6, 0), (7, 3), (14, 6)])
def test_meatsqueak_counts_every_seven_foods(cards, foods, bonus):
    s = table(cards, ["Meatsqueak, Hoard Lord", "Squirrel Sovereign"])
    squeak = put(s, "Meatsqueak, Hoard Lord")
    sovereign = put(s, "Squirrel Sovereign")
    for _ in range(foods):
        act(s, "p1", type="create_token", player="p1", token=FOOD, stacked=False)
    assert pt_of(s, squeak) == (3 + bonus, 4 + bonus)  # (Squirrel Sovereign's +1/+1 too)
    assert pt_of(s, sovereign) == (2 + bonus, 2 + bonus)
    check(s)


# -- Ekthi -----------------------------------------------------------------------------------------------------------------------------------
def test_ekthi_gives_equipment_living_weapon(cards):
    s = table(cards, ["Ekthi, Contaminator Priest", "Bonesplitter"])
    put(s, "Ekthi, Contaminator Priest")
    splitter = to_zone(s, "Bonesplitter", "hand")
    mana(s, C=1)
    cast(s, splitter)
    resolve(s)
    (germ,) = field(s, "p1", "Phyrexian Germ") or field(s, "p1", "Germ")
    assert s.state.cards[splitter.id].attached_to == germ.id
    assert pt_of(s, germ) == (3, 1)  # (0/0, +2/+0 from Bonesplitter, +1/+1 from Ekthi: a Phyrexian)
    check(s)


# -- Elda ------------------------------------------------------------------------------------------------------------------------------------
def test_elda_demonstrate_on_the_first_nonlegendary_creature_spell(cards):
    s = table(cards, ["Elda, Conjurer of Spectacle", "Grizzly Bears", "Llanowar Elves"])
    put(s, "Elda, Conjurer of Spectacle")
    asked: list[str] = []

    def yes(d):
        asked.append(d.prompt)
        return opt(d, "yes") or None

    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss" and c.owner == "p1")
    mana(s, R=4)
    cast(s, krenko)  # (legendary: not that spell, and it doesn't use it up)
    resolve(s, yes)
    assert not asked and len(field(s, "p1", "Krenko, Mob Boss")) == 1 and not field(s, "p2", "Krenko, Mob Boss")
    bears = to_zone(s, "Grizzly Bears", "hand")
    mana(s, G=2)
    cast(s, bears)
    resolve(s, yes)
    assert any("demonstrate" in p for p in asked)
    assert len(field(s, "p1", "Grizzly Bears")) == 2 and len(field(s, "p2", "Grizzly Bears")) == 1  # (702.144a: a copy each)
    asked.clear()
    elves = to_zone(s, "Llanowar Elves", "hand")
    mana(s, G=1)
    cast(s, elves)
    resolve(s, yes)
    assert not asked and len(field(s, "p1", "Llanowar Elves")) == 1 and not field(s, "p2", "Llanowar Elves")  # (the second this turn)
    check(s)


# -- The Muckslinger Gang --------------------------------------------------------------------------------------------------------------------
def test_muckslinger_pumps_other_creatures_not_attacking_or_blocking(cards):
    s = table(cards, ["The Muckslinger Gang", "Grizzly Bears", "Llanowar Elves"])
    gang = put(s, "The Muckslinger Gang")
    bears = put(s, "Grizzly Bears")
    assert pt_of(s, bears) == (5, 5) and pt_of(s, gang) == (3, 3)
    stops(s, "main1", "declare_attackers", "declare_blockers")
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    assert pt_of(s, bears) == (2, 2)  # (attacking)
    elves = named(s, "Llanowar Elves")
    assert pt_of(s, elves) == (4, 4)  # (a creature card in Alice's library)
    check(s)


# -- Jandor ----------------------------------------------------------------------------------------------------------------------------------
def test_jandor_mounts_saddle_and_the_saddled_attack(cards):
    s = table(cards, ["Jandor, Fortuned Traveler", "Trained Armodon", "Grizzly Bears"])
    put(s, "Jandor, Fortuned Traveler")
    armodon = put(s, "Trained Armodon")
    bears = put(s, "Grizzly Bears")
    assert "Mount" in ch(s, armodon).subtypes and "Mount" not in ch(s, bears).subtypes
    saddle = next(a.index for a in ch(s, armodon).abilities if a.text.lower().startswith("saddle"))
    stops(s, "main1", "declare_attackers", "declare_blockers")
    to_phase(s, "main1", turn=3)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=armodon.id, ability=saddle, crew=[bears.id])
    resolve(s)
    assert s.state.cards[bears.id].tapped
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": armodon.id, "target": "p2"}])
    resolve(s)
    assert pt_of(s, armodon) == (5, 5) and len(s.state.zones["p1:hand"]) == hand + 1 and len(field(s, "p1", "Food")) == 1
    check(s)


def test_jandor_unsaddled_attack_does_nothing(cards):
    s = table(cards, ["Jandor, Fortuned Traveler", "Trained Armodon"])
    put(s, "Jandor, Fortuned Traveler")
    armodon = put(s, "Trained Armodon")
    stops(s, "main1", "declare_attackers", "declare_blockers")
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": armodon.id, "target": "p2"}])
    resolve(s)
    assert pt_of(s, armodon) == (3, 3) and not field(s, "p1", "Food")
    check(s)


# -- Homer -----------------------------------------------------------------------------------------------------------------------------------
def test_homer_mills_twice_the_crustaceans(cards):
    s = table(cards, ["Homer, the Hermit", "Fortress Crab", "Rikala, Homarid King", "Grizzly Bears"])
    put(s, "Homer, the Hermit")
    put(s, "Fortress Crab")
    put(s, "Rikala, Homarid King")  # (a Lobster)
    put(s, "Grizzly Bears")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})
    library = len(s.state.zones["p2:library"])
    act(s, "p1", type="play_land", card_id=forest.id)
    resolve(s, lambda d: opt(d, "Bob") or None)
    assert len(s.state.zones["p2:library"]) == library - 6  # (Homer, the Crab, the Lobster: three, twice)
    check(s)


# -- Massimo ---------------------------------------------------------------------------------------------------------------------------------
def test_massimo_exiles_a_bolt_and_its_creature_casts_a_copy(cards):
    s = table(cards, ["Massimo, the Magician", "Lightning Bolt", "Grizzly Bears"])
    bolt = to_zone(s, "Lightning Bolt", "graveyard")
    massimo = to_zone(s, "Massimo, the Magician", "hand")
    mana(s, U=1, R=1, W=1)
    cast(s, massimo)
    resolve(s, lambda d: [bolt.id] if bolt.id in [o.id for o in d.options] else None)
    assert s.state.cards[bolt.id].zone == "p1:exile"
    assert any("copy the exiled card" in a.text for a in ch(s, massimo).abilities)
    stops(s, "main1", "declare_attackers", "declare_blockers", "combat_damage")
    to_phase(s, "declare_attackers", turn=3)
    life = s.state.players["p2"].life
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": massimo.id, "target": "p2"}])

    def pick(d):
        return opt(d, "cast") or opt(d, "Bob") or opt(d, "yes") or None

    for _ in range(12):
        resolve(s, pick)
        if s.state.turn.phase in ("combat_damage", "end_combat", "main2"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    resolve(s, pick)
    assert s.state.players["p2"].life == life - 3 - 3  # (Massimo's 3 combat damage, the free Bolt copy's 3)
    assert s.state.cards[bolt.id].zone == "p1:exile"  # (the card stays; the copy was cast)
    check(s)


# -- Matoc -----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("spell,hits", [("Firebolt", True), ("Lightning Bolt", False)])
def test_matoc_exiles_the_top_card_when_exactly_two_is_dealt(cards, spell, hits):
    s = table(cards, ["Matoc, Lavamancer", spell])
    put(s, "Matoc, Lavamancer")
    card = to_zone(s, spell, "hand")
    exiled = len(s.state.zones.get("p1:exile", []))
    mana(s, R=1)
    cast(s, card, targets=["p2"])
    resolve(s)
    gone = [c for c in s.state.zones.get("p1:exile", []) if c != card.id]
    assert len(gone) - exiled == (1 if hits else 0)
    check(s)


# -- Sahir -----------------------------------------------------------------------------------------------------------------------------------
def test_sahir_counts_its_own_damage_and_your_own_life_loss(cards):
    s = table(cards, ["Sahir, Visitor in Darkness", "Phyrexian Arena", "Sign in Blood"])
    sahir = put(s, "Sahir, Visitor in Darkness")
    put(s, "Phyrexian Arena")
    stops(s, "upkeep", "main1")
    life = s.state.players["p1"].life
    hand = len(s.state.zones["p1:hand"])
    to_phase(s, "main1", turn=3)
    resolve(s)
    # upkeep: Sahir deals 1 damage to Alice (eminence, on the battlefield), the Arena makes her lose 1: two resolutions, the second draws
    assert s.state.cards[sahir.id].counters.get("+1/+1", 0) == 2
    assert s.state.players["p1"].life == life - 2
    assert len(s.state.zones["p1:hand"]) == hand + 3  # (the Arena's card, Sahir's second resolution, the draw step)
    sign = to_zone(s, "Sign in Blood", "hand")
    mana(s, B=2)
    cast(s, sign, targets=["p1"])  # (2 life: not exactly 1)
    resolve(s)
    assert s.state.cards[sahir.id].counters.get("+1/+1", 0) == 2
    check(s)


def test_sahir_eminence_from_the_command_zone(cards):
    s = table(cards, [], commander="Sahir, Visitor in Darkness")
    sahir = next(c for c in s.state.cards.values() if c.name == "Sahir, Visitor in Darkness" and c.owner == "p1")
    assert sahir.zone == "p1:command"
    stops(s, "upkeep", "main1")
    life = s.state.players["p1"].life
    to_phase(s, "main1", turn=3)
    resolve(s)
    assert s.state.players["p1"].life == life - 1
    check(s)


def test_muckslinger_outside_pt_reads_cards_outside_the_battlefield(cards):
    """``mbc_b.outside_pt`` (applied by layers._derive): +3/+3 for a creature card Alice owns in her library, hand or graveyard, not
    for Bob's, and none once The Muckslinger Gang has left."""
    s = table(cards, ["The Muckslinger Gang", "Grizzly Bears", "Llanowar Elves"], ["Fortress Crab"])
    gang = put(s, "The Muckslinger Gang")
    bears = to_zone(s, "Grizzly Bears", "hand")
    elves = named(s, "Llanowar Elves")
    crab = named(s, "Fortress Crab", "p2")

    assert ch(s, bears).pt == (5, 5) and ch(s, elves).pt == (4, 4)
    assert ch(s, crab, "p2").pt == (1, 6)
    act(s, "p1", type="move", card_ids=[gang.id], to={"player": "p1", "zone": "graveyard"})
    assert ch(s, bears).pt == (2, 2) and ch(s, elves).pt == (1, 1)
    check(s)
