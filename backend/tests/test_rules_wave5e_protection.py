"""Wave 5E: protection granted until end of turn (a quality chosen as it resolves: app/rules/protection_grants.py) and
a player's hexproof, shroud and protection (app/rules/player_shields.py).

* 702.16b/e: a creature that gained protection from red can't be targeted by red spells, red damage is prevented.
* 608.2: "of your choice" is chosen as the effect resolves; "colorless or from the color of your choice" offers
  colorless too.
* 702.11c: a player with hexproof can't be targeted by opponents' spells (their own can); 702.16j: protection from
  everything — no spell or ability targets that player, all damage to them is prevented, an Aura can't enchant them
  (704.5m), until their next turn (500.4).
Every scenario checks the replay and a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, scripts
from app.rules.plan import Plan
from app.rules.player_shields import static_definition
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, to_hand, to_turn
from tests.test_rules_effects import mana
from tests.test_rules_wave5b_stack_interaction import build as _build
from tests.test_rules_wave5b_stack_interaction import roundtrip

EXTRA = [
    card('Mother of Runes', set_code="tst", number="Z520", mana_cost='{W}', cmc=1.0, type_line='Creature — Human Cleric', oracle_text='{T}: Target creature you control gains protection from the color of your choice until end of turn.', power='1', toughness='1', colors=['W'], color_identity=['W']),
    card('Giver of Runes', set_code="tst", number="Z521", mana_cost='{W}', cmc=1.0, type_line='Creature — Kor Cleric', oracle_text='{T}: Another target creature you control gains protection from colorless or from the color of your choice until end of turn.', power='1', toughness='2', colors=['W'], color_identity=['W']),
    card('Gods Willing', set_code="tst", number="Z522", mana_cost='{W}', cmc=1.0, type_line='Instant', oracle_text="Target creature you control gains protection from the color of your choice until end of turn. (It can't be blocked, targeted, dealt damage, enchanted, or equipped by anything of that color.)\nScry 1.", colors=['W'], color_identity=['W'], keywords=['Scry']),
    card('Tower of the Magistrate', set_code="tst", number="Z523", cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{1}, {T}: Target creature gains protection from artifacts until end of turn.'),
    card('Crystal Barricade', set_code="tst", number="Z525", mana_cost='{1}{W}', cmc=2.0, type_line='Artifact Creature — Wall', oracle_text="Defender (This creature can't attack.)\nYou have hexproof. (You can't be the target of spells or abilities your opponents control.)\nPrevent all noncombat damage that would be dealt to other creatures you control.", power='0', toughness='4', colors=['W'], color_identity=['W'], keywords=['Defender']),
    card('Shalai, Voice of Plenty', set_code="tst", number="Z526", mana_cost='{3}{W}', cmc=4.0, type_line='Legendary Creature — Angel', oracle_text='Flying\nYou, planeswalkers you control, and other creatures you control have hexproof.\n{4}{G}{G}: Put a +1/+1 counter on each creature you control.', power='3', toughness='4', colors=['W'], color_identity=['G', 'W'], keywords=['Flying']),
    card('The One Ring', set_code="tst", number="Z527", mana_cost='{4}', cmc=4.0, type_line='Legendary Artifact', oracle_text='Indestructible\nWhen The One Ring enters, if you cast it, you gain protection from everything until your next turn.\nAt the beginning of your upkeep, you lose 1 life for each burden counter on The One Ring.\n{T}: Put a burden counter on The One Ring, then draw a card for each burden counter on The One Ring.', keywords=['Indestructible']),
    card('The Stasis Coffin', set_code="tst", number="Z528", mana_cost='{3}', cmc=3.0, type_line='Legendary Artifact', oracle_text='{2}, {T}, Exile The Stasis Coffin: You gain protection from everything until your next turn.'),
    card("Seht's Tiger", set_code="tst", number="Z529", mana_cost='{2}{W}{W}', cmc=4.0, type_line='Creature — Cat', oracle_text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this creature enters, you gain protection from the color of your choice until end of turn. (You can't be targeted, dealt damage, or enchanted by anything of the chosen color.)", power='3', toughness='3', colors=['W'], color_identity=['W'], keywords=['Flash']),
    card('Curse of Opulence', set_code="tst", number="Z532", mana_cost='{R}', cmc=1.0, type_line='Enchantment — Aura Curse', oracle_text='Enchant player\nWhenever enchanted player is attacked, create a Gold token. Each opponent attacking that player does the same. (A Gold token is an artifact with "Sacrifice this token: Add one mana of any color.")', colors=['R'], color_identity=['R'], keywords=['Enchant']),
    card('Earthquake', set_code="tst", number="Z533", mana_cost='{X}{R}', cmc=1.0, type_line='Sorcery', oracle_text='Earthquake deals X damage to each creature without flying and each player.', colors=['R'], color_identity=['R']),
    card("Apostle's Blessing", set_code="tst", number="Z534", mana_cost='{1}{W/P}', cmc=2.0, type_line='Instant', oracle_text='({W/P} can be paid with either {W} or 2 life.)\nTarget artifact or creature you control gains protection from artifacts or from the color of your choice until end of turn.', colors=['W'], color_identity=['W']),
]
FULL = ["Mother of Runes", "Giver of Runes", "Gods Willing", "Tower of the Magistrate", "Crystal Barricade",
        "Shalai, Voice of Plenty", "The One Ring", "The Stasis Coffin", "Seht's Tiger", "Apostle's Blessing"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, p1=(), p2=()):
    s = _build(cards, p1=p1, p2=p2)
    act(s, "p1", type="set_prefs", hold_priority=True)
    return s


def field(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def answer(s, option):
    d = s.state.rules.decision
    assert d is not None and option in [o.id for o in d.options], d and [o.id for o in d.options]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])


def resolve_with(s, option, limit=10):
    """Pass priority until the choice comes up, answer it, then let everything resolve."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            answer(s, option)
            settle(s)
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never asked")


def bolt_can_target(s, pid, target):
    """Could ``pid``'s Lightning Bolt target this now (the legal targets the engine offers, 601.2c)?"""
    from app.rules import characteristics as chars
    from app.rules.targets import legal_targets

    bolt = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == pid)
    ch = chars.of(bolt, s.cards)
    return target in legal_targets(Plan.view(s.state, pid, s.cards), scripts.spell_definition(ch)["target"]["what"], pid, ch)


def bob_bolts(s, target):
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[target])
    return bolt


# -- the wording ------------------------------------------------------------------------------------
def test_wordings():
    mother = scripts.parse_effects("Target creature you control gains protection from the color of your choice until end of turn.")
    assert mother is not None and mother[0][0]["do"] == "protection_choice" and len(mother[0][0]["options"]) == 5
    giver = scripts.parse_effects("Another target creature you control gains protection from colorless or from the color of your "
                                  "choice until end of turn.")
    assert giver is not None and giver[0][0]["options"][0] == "Colorless"
    tower = scripts.parse_effects("Target creature gains protection from artifacts until end of turn.")
    assert tower is not None and tower[0][0] == {"do": "grant", "who": "target", "keywords": [], "abilities": ["Protection from artifacts"]}
    ring = scripts.parse_effects("You gain protection from everything until your next turn.")
    assert ring is not None and ring[0][0] == {"do": "player_shield", "shield": "protection", "quality": "everything",
                                                "until": "next_turn"}
    assert static_definition("You have hexproof.")["shield"] == "hexproof"
    assert static_definition("You, planeswalkers you control, and other creatures you control have hexproof.")["player_shield"]


@pytest.mark.parametrize("text", [
    "Target creature gains protection from the card type of your choice until end of turn.",
    "You gain protection from that player until your next turn.",
    "Target creature gains protection from the color of your choice until your next turn.",
])
def test_refused(text):
    assert scripts.parse_effects(text) is None


@pytest.mark.parametrize("text", ["During your turn, you and this creature have hexproof.", "You have hexproof from blue."])
def test_refused_statics(text):
    assert static_definition(text) is None


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- protection until end of turn -------------------------------------------------------------------
def test_mother_of_runes_protection_from_the_chosen_color(cards):
    s = build(cards, p1=("Mother of Runes", "Grizzly Bears", "Earthquake"), p2=("Lightning Bolt",))
    mother = field(s, "Mother of Runes")
    bears = field(s, "Grizzly Bears")
    to_turn(s, 3)  # (Mother isn't summoning sick any more)
    act(s, "p1", type="activate_ability", card_id=mother.id, ability=0, targets=[bears.id])
    resolve_with(s, "Red")
    view = Plan.view(s.state, "p1", s.cards)
    assert "protection" in view.ch(s.state.cards[bears.id]).keywords
    assert not bolt_can_target(s, "p2", bears.id) and bolt_can_target(s, "p2", mother.id)  # (702.16b: not by a red spell)
    quake = to_hand(s, "Earthquake")
    mana(s, R=3)
    act(s, "p1", type="cast_spell", card_id=quake.id, x_value=2)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[mother.id].zone == "p1:graveyard"
    assert s.state.players["p1"].life == 38  # (the player has no protection)
    roundtrip(s)


def test_giver_of_runes_offers_colorless(cards):
    s = build(cards, p1=("Giver of Runes", "Grizzly Bears"))
    giver = field(s, "Giver of Runes")
    bears = field(s, "Grizzly Bears")
    to_turn(s, 3)
    act(s, "p1", type="activate_ability", card_id=giver.id, ability=0, targets=[bears.id])
    for _ in range(5):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    options = [o.id for o in s.state.rules.decision.options]
    assert options == ["Colorless", "White", "Blue", "Black", "Red", "Green"]
    answer(s, "Colorless")
    settle(s)
    roundtrip(s)


def test_the_protection_ends_at_cleanup(cards):
    s = build(cards, p1=("Gods Willing", "Grizzly Bears"), p2=("Lightning Bolt",))
    bears = field(s, "Grizzly Bears")
    willing = to_hand(s, "Gods Willing")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=willing.id, targets=[bears.id])
    resolve_with(s, "Red")
    settle(s)  # (Scry 1)
    assert not bolt_can_target(s, "p2", bears.id)
    to_turn(s, 2)
    bob_bolts(s, bears.id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    roundtrip(s)


# -- a player's shields -----------------------------------------------------------------------------
def test_you_have_hexproof_stops_opponents_only(cards):
    s = build(cards, p1=("Crystal Barricade", "Lightning Bolt"), p2=("Lightning Bolt",))
    field(s, "Crystal Barricade")
    to_turn(s, 2)
    with pytest.raises(ActionError, match="legal target"):
        bob_bolts(s, "p1")
    to_turn(s, 3)
    mine = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=mine.id, targets=["p1"])  # (hexproof: only opponents are stopped)
    settle(s)
    assert s.state.players["p1"].life == 37
    roundtrip(s)


def test_shalai_shields_you_and_other_creatures_but_not_itself(cards):
    s = build(cards, p1=("Shalai, Voice of Plenty", "Grizzly Bears"), p2=("Lightning Bolt",))
    shalai = field(s, "Shalai, Voice of Plenty")
    bears = field(s, "Grizzly Bears")
    to_turn(s, 2)
    for target in ("p1", bears.id):
        with pytest.raises(ActionError, match="legal target"):
            bob_bolts(s, target)
    bob_bolts(s, shalai.id)
    settle(s)
    assert s.state.cards[shalai.id].damage == 3
    roundtrip(s)


def test_stasis_coffin_protection_from_everything_until_your_next_turn(cards):
    s = build(cards, p1=("The Stasis Coffin", "Curse of Opulence", "Lightning Bolt"), p2=("Lightning Bolt", "Earthquake"))
    coffin = field(s, "The Stasis Coffin")
    curse = to_hand(s, "Curse of Opulence")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=curse.id, targets=["p1"])
    settle(s)
    assert s.state.cards[curse.id].attached_player == "p1"
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=coffin.id, ability=0)
    settle(s)
    assert s.state.cards[curse.id].zone == "p1:graveyard"  # (704.5m: it can't enchant a player with protection from it)
    mine = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="cast_spell", card_id=mine.id, targets=["p1"])  # (702.16j: not even by your own spells)
    to_turn(s, 2)
    with pytest.raises(ActionError, match="legal target"):
        bob_bolts(s, "p1")
    quake = to_hand(s, "Earthquake", "p2")
    mana(s, "p2", R=2)
    act(s, "p2", type="cast_spell", card_id=quake.id, x_value=1)
    settle(s)
    assert s.state.players["p1"].life == 40 and s.state.players["p2"].life == 39
    to_turn(s, 3)  # Alice's next turn: it's over
    assert not s.state.rules.player_shields
    roundtrip(s)


def test_seht_s_tiger_protection_from_the_chosen_color(cards):
    s = build(cards, p1=("Seht's Tiger",), p2=("Lightning Bolt", "Earthquake"))
    tiger = to_hand(s, "Seht's Tiger")
    mana(s, W=4)
    act(s, "p1", type="cast_spell", card_id=tiger.id)
    resolve_with(s, "Red", limit=20)
    assert not bolt_can_target(s, "p2", "p1") and bolt_can_target(s, "p2", "p2")
    roundtrip(s)


def test_the_one_ring_only_when_cast(cards):
    s = build(cards, p1=("The One Ring",), p2=("Lightning Bolt",))
    ring = to_hand(s, "The One Ring")
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=ring.id)
    settle(s)
    assert [x["quality"] for x in s.state.rules.player_shields] == ["everything"]
    assert not bolt_can_target(s, "p2", "p1")
    roundtrip(s)


def test_the_one_ring_put_onto_the_battlefield_gives_nothing(cards):
    s = build(cards, p1=("The One Ring",))
    field(s, "The One Ring")
    settle(s)
    assert not s.state.rules.player_shields
