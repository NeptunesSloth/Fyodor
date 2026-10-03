"""Wave 5A: mana-ability riders and untap riders, researched against CR 2026-09-25.

* 605.1a / 605.3b: an activated mana ability resolves as it is activated: its amounts ("for each Elf on the
  battlefield", "where X is …") and its colors ("any color among legendary creatures and planeswalkers you control",
  "for each color among permanents you control") are read then, and its other effects ("You gain 2 life.", "Each
  opponent gains 1 life.") happen in the same resolution. A cost that moves a card to or from a library ("{T}, Mill a
  card: Add {C}.") makes it an ordinary activated ability that uses the stack.

Every scenario uses real Commander-legal cards with their current Oracle text (data/cards.sqlite), checks that
replaying the recorded history reproduces the table, and that a save/load round trip keeps it.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from app.rules.casting import mana_abilities
from app.rules.mana import parse_mana_ability
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches
from tests.test_rules_permissions import build, find, put

EXTRA = [
    card('The Great Henge', set_code="tst", number="A01", mana_cost='{7}{G}{G}', cmc=9.0, type_line='Legendary Artifact', oracle_text='This spell costs {X} less to cast, where X is the greatest power among creatures you control.\n{T}: Add {G}{G}. You gain 2 life.\nWhenever a nontoken creature you control enters, put a +1/+1 counter on it and draw a card.', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Pristine Talisman', set_code="tst", number="A02", mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text='{T}: Add {C}. You gain 1 life.', colors=[], color_identity=[]),  # noqa: E501
    card('Grove of the Burnwillows', set_code="tst", number="A03", mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{T}: Add {R} or {G}. Each opponent gains 1 life.', colors=[], color_identity=['G', 'R']),  # noqa: E501
    card('Mox Amber', set_code="tst", number="A04", mana_cost='{0}', cmc=0.0, type_line='Legendary Artifact', oracle_text='{T}: Add one mana of any color among legendary creatures and planeswalkers you control.', colors=[], color_identity=[]),  # noqa: E501
    card('Plaza of Heroes', set_code="tst", number="A05", mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a legendary spell.\n{T}: Add one mana of any color among legendary permanents you control.\n{3}, {T}, Exile this land: Target legendary creature gains hexproof and indestructible until end of turn.', colors=[], color_identity=[]),  # noqa: E501
    card('The Grey Havens', set_code="tst", number="A06", mana_cost='', cmc=0.0, type_line='Legendary Land', oracle_text='When The Grey Havens enters, scry 1.\n{T}: Add {C}.\n{T}: Add one mana of any color among legendary creature cards in your graveyard.', colors=[], color_identity=[], keywords=['Scry']),  # noqa: E501
    card('Bloom Tender', set_code="tst", number="A07", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Elf Druid', oracle_text='Vivid — {T}: For each color among permanents you control, add one mana of that color.', power='1', toughness='1', colors=['G'], color_identity=['G'], keywords=['Vivid']),  # noqa: E501
    card('Faeburrow Elder', set_code="tst", number="A08", mana_cost='{1}{G}{W}', cmc=3.0, type_line='Creature — Treefolk Druid', oracle_text='Vigilance\nThis creature gets +1/+1 for each color among permanents you control.\n{T}: For each color among permanents you control, add one mana of that color.', power='0', toughness='0', colors=['G', 'W'], color_identity=['G', 'W'], keywords=['Vigilance']),  # noqa: E501
    card('Priest of Titania', set_code="tst", number="A09", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Elf Druid', oracle_text='{T}: Add {G} for each Elf on the battlefield.', power='1', toughness='1', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Cabal Stronghold', set_code="tst", number="A10", mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{3}, {T}: Add {B} for each basic Swamp you control.', colors=[], color_identity=['B']),  # noqa: E501
    card('Crypt of Agadeem', set_code="tst", number="A11", mana_cost='', cmc=0.0, type_line='Land', oracle_text='This land enters tapped.\n{T}: Add {B}.\n{2}, {T}: Add {B} for each black creature card in your graveyard.', colors=[], color_identity=['B']),  # noqa: E501
    card('Overgrown Battlement', set_code="tst", number="A12", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Wall', oracle_text='Defender\n{T}: Add {G} for each creature you control with defender.', power='0', toughness='4', colors=['G'], color_identity=['G'], keywords=['Defender']),  # noqa: E501
    card('Kydele, Chosen of Kruphix', set_code="tst", number="A13", mana_cost='{2}{G}{U}', cmc=4.0, type_line='Legendary Creature — Human Wizard', oracle_text="{T}: Add {C} for each card you've drawn this turn.\nPartner (You can have two commanders if both have partner.)", power='2', toughness='3', colors=['G', 'U'], color_identity=['G', 'U'], keywords=['Partner']),  # noqa: E501
    card('Relic of Sauron', set_code="tst", number="A14", mana_cost='{4}', cmc=4.0, type_line='Artifact', oracle_text='{T}: Add two mana in any combination of {U}, {B}, and/or {R}.\n{3}, {T}: Draw two cards, then discard a card.', colors=[], color_identity=['B', 'R', 'U']),  # noqa: E501
    card('Firemind Vessel', set_code="tst", number="A15", mana_cost='{4}', cmc=4.0, type_line='Artifact', oracle_text='This artifact enters tapped.\n{T}: Add two mana of different colors.', colors=[], color_identity=[]),  # noqa: E501
    card('Wirewood Channeler', set_code="tst", number="A16", mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Elf Druid', oracle_text='{T}: Add X mana of any one color, where X is the number of Elves on the battlefield.', power='2', toughness='2', colors=['G'], color_identity=['G']),  # noqa: E501
    card("Baldur's Gate", set_code="tst", number="A17", mana_cost='', cmc=0.0, type_line='Legendary Land — Gate', oracle_text='{T}: Add {C}.\n{2}, {T}: Add X mana of any one color, where X is the number of other Gates you control.', colors=[], color_identity=[]),  # noqa: E501
    card('Millikin', set_code="tst", number="A18", mana_cost='{2}', cmc=2.0, type_line='Artifact Creature — Construct', oracle_text='{T}, Mill a card: Add {C}. (Activate only as an instant. To mill a card, put the top card of your library into your graveyard.)', power='0', toughness='1', colors=[], color_identity=[], keywords=['Mill']),  # noqa: E501
    card("Karametra's Acolyte", set_code="tst", number="A19", mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Human Druid', oracle_text='{T}: Add an amount of {G} equal to your devotion to green. (Each {G} in the mana costs of permanents you control counts toward your devotion to green.)', power='1', toughness='4', colors=['G'], color_identity=['G']),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    """Replay rebuilds the same table, a save/load round trip keeps it, and a session rebuilt from the history too."""
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))


def next_main(s):
    """Play on to Alice's next first main phase (her permanents are no longer summoning sick); nobody attacks."""
    act(s, "p1", type="pass_priority")
    for _ in range(80):
        if s.state.turn.active_player == "p1" and s.state.turn.phase == "main1" and s.state.turn.number > 1:
            return
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blockers=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority or s.state.turn.active_player, type="pass_priority")
    raise AssertionError("never reached Alice's next main phase")


def options(s, c):
    return dict(mana_abilities(s.state, s.state.cards[c.id], s.cards))


def choose(s, label):
    d = s.state.rules.decision
    assert d is not None, "expected a choice"
    pick = next(o for o in d.options if o.label == label)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick.id])


# -- coverage ------------------------------------------------------------------------------------------------------
def test_the_cards_are_full():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            level = coverage.of_characteristics(characteristics(c["name"], c["type_line"], c["oracle_text"]))
            assert level.level == "FULL", (c["name"], level.manual_parts)


@pytest.mark.parametrize("text", [
    "{T}: Add {C} for each Locus on the battlefield.",  # (a land type the selector grammar doesn't read in the singular)
    "{T}: Add X mana in any combination of colors, where X is the number of creatures you control with defender.",
    "{T}: Add {G} for each creature that entered this turn under target player's control.",
    "{T}: Add X mana of any one color, where X is the number of cards in target opponent's hand.",
    "{T}: Add {R}. You gain 1 life for each creature you control.",
    "{T}: Add one mana of any color among cards in target opponent's graveyard.",
    "{T}: Add one mana of any color among permanents your opponents control or cards in exile.",
])
def test_refused_wordings(text):
    assert parse_mana_ability(text) is None


# -- riders: life gain -----------------------------------------------------------------------------------------------
def test_great_henge_adds_two_green_and_gains_two_life(cards):
    s = build(cards, [(1, "The Great Henge"), (1, "Pristine Talisman"), (8, "Forest")])
    henge = put(s, "The Great Henge", "battlefield")
    talisman = put(s, "Pristine Talisman", "battlefield")
    life = s.state.players["p1"].life
    act(s, "p1", type="activate_ability", card_id=henge.id, ability=1)
    assert s.state.players["p1"].mana == {"G": 2} and s.state.players["p1"].life == life + 2
    assert not s.state.zones.get("stack")  # 605.3b: no stack
    act(s, "p1", type="activate_ability", card_id=talisman.id, ability=0)
    assert s.state.players["p1"].mana == {"G": 2, "C": 1} and s.state.players["p1"].life == life + 3
    roundtrip(s)


def test_pristine_talisman_used_by_the_payer_gains_life(cards):
    """The auto-payer taps it for {C} — the life gain rides along (one resolution)."""
    s = build(cards, [(1, "Pristine Talisman"), (1, "Millikin"), (8, "Forest")])
    talisman = put(s, "Pristine Talisman", "battlefield")
    life = s.state.players["p1"].life
    millikin = find(s, "Millikin")
    act(s, "p1", type="move", card_ids=[millikin.id], to={"player": "p1", "zone": "hand"})
    forest = put(s, "Forest", "battlefield")
    act(s, "p1", type="cast_spell", card_id=millikin.id)  # {2}: the Forest and the Talisman
    assert s.state.cards[talisman.id].tapped and s.state.cards[forest.id].tapped
    assert s.state.players["p1"].life == life + 1
    roundtrip(s)


def test_grove_of_the_burnwillows_each_opponent_gains_one(cards):
    s = build(cards, [(1, "Grove of the Burnwillows"), (9, "Forest")])
    grove = put(s, "Grove of the Burnwillows", "battlefield")
    mine, theirs = s.state.players["p1"].life, s.state.players["p2"].life
    act(s, "p1", type="activate_ability", card_id=grove.id, ability=1, mana_choice="R")
    assert s.state.players["p1"].mana == {"R": 1}
    assert s.state.players["p2"].life == theirs + 1 and s.state.players["p1"].life == mine
    roundtrip(s)


# -- counted mana -----------------------------------------------------------------------------------------------------
def test_priest_of_titania_counts_every_elf_on_the_battlefield(cards):
    s = build(cards, [(1, "Priest of Titania"), (1, "Llanowar Elves"), (8, "Forest")], bob=[(1, "Wirewood Channeler"), (9, "Island")])
    priest = put(s, "Priest of Titania", "battlefield")
    put(s, "Llanowar Elves", "battlefield")
    put(s, "Wirewood Channeler", "battlefield", pid="p2")
    next_main(s)
    assert options(s, priest)[0].options == (("G", "G", "G"),)  # its own, Alice's other Elf and Bob's (Priest ruling)
    act(s, "p1", type="activate_ability", card_id=priest.id, ability=0)
    assert s.state.players["p1"].mana == {"G": 3}
    roundtrip(s)


def test_cabal_stronghold_counts_basic_swamps_and_pays_its_activation(cards):
    s = build(cards, [(1, "Cabal Stronghold"), (2, "Swamp"), (3, "Forest")])
    stronghold = put(s, "Cabal Stronghold", "battlefield")
    for c in [c for c in s.state.cards.values() if c.name == "Swamp" and c.owner == "p1"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    assert options(s, stronghold)[1].options == (("B", "B"),)
    mana(s, G=3)
    act(s, "p1", type="activate_ability", card_id=stronghold.id, ability=1)
    assert s.state.players["p1"].mana == {"B": 2}
    roundtrip(s)


def test_crypt_of_agadeem_counts_black_creature_cards_in_your_graveyard(cards):
    s = build(cards, [(1, "Crypt of Agadeem"), (2, "Twisted Abomination"), (7, "Forest")], bob=[(9, "Island")])
    crypt = put(s, "Crypt of Agadeem", "battlefield")
    assert 2 not in options(s, crypt)  # none: it would add no mana (605.2)
    act(s, "p1", type="create_token", player="p1", token={"name": "Shade", "type_line": "Token Creature — Shade",
                                                         "power": "1", "toughness": "1", "colors": ["B"], "text": ""})
    assert 2 not in options(s, crypt)  # a token on the battlefield isn't a card in your graveyard
    for c in [c for c in s.state.cards.values() if c.name == "Twisted Abomination"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    assert options(s, crypt)[2].options == (("B", "B"),)
    mana(s, R=2)
    act(s, "p1", type="activate_ability", card_id=crypt.id, ability=2)
    assert s.state.players["p1"].mana == {"B": 2}
    roundtrip(s)


def test_kydele_counts_the_cards_you_drew_this_turn(cards):
    s = build(cards, [(1, "Kydele, Chosen of Kruphix"), (9, "Forest")])
    kydele = put(s, "Kydele, Chosen of Kruphix", "battlefield")
    next_main(s)  # Alice drew one card in her draw step
    assert options(s, kydele)[0].options == (("C",),)
    roundtrip(s)


def test_wirewood_channeler_x_of_one_color(cards):
    s = build(cards, [(1, "Wirewood Channeler"), (1, "Llanowar Elves"), (8, "Forest")])
    channeler = put(s, "Wirewood Channeler", "battlefield")
    put(s, "Llanowar Elves", "battlefield")
    next_main(s)
    act(s, "p1", type="activate_ability", card_id=channeler.id, ability=0, mana_choice=None)
    choose(s, "{U}{U}")
    assert s.state.players["p1"].mana == {"U": 2}
    roundtrip(s)


def test_baldurs_gate_counts_other_gates(cards):
    s = build(cards, [(1, "Baldur's Gate"), (9, "Forest")])
    gate = put(s, "Baldur's Gate", "battlefield")
    assert 1 not in options(s, gate)  # no other Gates: it would add no mana
    roundtrip(s)


def test_karametras_acolyte_devotion(cards):
    s = build(cards, [(1, "Karametra's Acolyte"), (1, "Priest of Titania"), (8, "Forest")])
    acolyte = put(s, "Karametra's Acolyte", "battlefield")
    put(s, "Priest of Titania", "battlefield")
    assert options(s, acolyte)[0].options == (("G", "G"),)  # {3}{G} and {1}{G}: devotion 2 (700.5)
    roundtrip(s)


# -- colors among -----------------------------------------------------------------------------------------------------
def test_mox_amber_and_plaza_of_heroes_read_legendary_permanents(cards):
    s = build(cards, [(1, "Mox Amber"), (1, "Plaza of Heroes"), (1, "Kydele, Chosen of Kruphix"), (7, "Forest")])
    mox = put(s, "Mox Amber", "battlefield")
    plaza = put(s, "Plaza of Heroes", "battlefield")
    assert not options(s, mox)  # only itself: a colorless legendary artifact (ruling 2018-04-27)
    assert 2 not in options(s, plaza)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=mox.id, ability=0)
    put(s, "Kydele, Chosen of Kruphix", "battlefield")
    assert options(s, mox)[0].options == (("U",), ("G",))
    assert options(s, plaza)[2].options == (("U",), ("G",))
    act(s, "p1", type="activate_ability", card_id=mox.id, ability=0, mana_choice="U")
    assert s.state.players["p1"].mana == {"U": 1}
    roundtrip(s)


def test_the_grey_havens_reads_legendary_creature_cards_in_your_graveyard(cards):
    s = build(cards, [(1, "The Grey Havens"), (1, "Kydele, Chosen of Kruphix"), (8, "Forest")])
    havens = put(s, "The Grey Havens", "battlefield")
    pass_until_stack_empty(s)  # (its scry 1)
    if s.state.rules.decision is not None:
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert 2 not in options(s, havens)
    put(s, "Kydele, Chosen of Kruphix", "graveyard")
    assert options(s, havens)[2].options == (("U",), ("G",))
    roundtrip(s)


def test_bloom_tender_adds_one_of_each_color_among_your_permanents(cards):
    s = build(cards, [(1, "Bloom Tender"), (1, "Faeburrow Elder"), (1, "Kydele, Chosen of Kruphix"), (7, "Forest")])
    tender = put(s, "Bloom Tender", "battlefield")
    put(s, "Forest", "battlefield")  # (a land is colorless: no {C}, ruling 2025-11-17)
    next_main(s)
    assert options(s, tender)[0].options == (("G",),)
    put(s, "Kydele, Chosen of Kruphix", "battlefield")
    put(s, "Faeburrow Elder", "battlefield")
    act(s, "p1", type="activate_ability", card_id=tender.id, ability=0)
    assert s.state.players["p1"].mana == {"W": 1, "U": 1, "G": 1}
    roundtrip(s)


# -- fixed combinations ---------------------------------------------------------------------------------------------------
def test_relic_of_sauron_and_firemind_vessel(cards):
    s = build(cards, [(1, "Relic of Sauron"), (1, "Firemind Vessel"), (8, "Forest")])
    relic = put(s, "Relic of Sauron", "battlefield")
    vessel = put(s, "Firemind Vessel", "battlefield")
    assert set(options(s, relic)[0].options) == {("U", "U"), ("U", "B"), ("U", "R"), ("B", "B"), ("B", "R"), ("R", "R")}
    found = options(s, vessel)[1].options
    assert len(found) == 10 and all(a != b for a, b in found)  # two different colors
    act(s, "p1", type="activate_ability", card_id=relic.id, ability=0)
    choose(s, "{B}{R}")
    assert s.state.players["p1"].mana == {"B": 1, "R": 1}
    roundtrip(s)


# -- 605.1a: a library-moving cost is not a mana ability --------------------------------------------------------------------
def test_millikin_uses_the_stack(cards):
    s = build(cards, [(1, "Millikin"), (9, "Forest")])
    millikin = put(s, "Millikin", "battlefield")
    next_main(s)
    library = len(s.state.zones["p1:library"])
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="activate_ability", card_id=millikin.id, ability=0)
    assert len(s.state.zones["p1:library"]) == library - 1  # milled as a cost
    assert s.state.zones.get("stack")  # 605.1a: not a mana ability, so it waits on the stack
    pass_until_stack_empty(s)
    assert s.state.players["p1"].mana.get("C") == 1
    roundtrip(s)
