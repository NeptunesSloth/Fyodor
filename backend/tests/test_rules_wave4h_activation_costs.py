"""Wave 4H: more parts of an activation cost (CR 118, 602.2b → 601.2b-i), app/rules/costs.py and
app/rules/cost_payment.py.

Each part has its legality check before anything is paid (118.3, 601.2h: no partial payments — a refused
activation leaves the table exactly as it was): counters of any kind removed from the source or from a
permanent you choose (122.1), X counters / X permanents / X graveyard cards with X announced as it's
activated (107.3a, 107.3k), counters put on the source or on a creature you control (122.6; blight,
701.68a-b), discarding your hand (an empty hand pays it: Wizards ruling on Bomat Courier, 2016-09-20),
milling and exiling from the top of your library (701.17b; 601.2h: paid last), exiling a permanent you
control, half your life rounded up (107.1a, 119.4), life equal to the number of colors in your commanders'
color identity (903.4, 903.4f), collect evidence (701.59a-b), forage (701.61a), two parts joined by
"and", and boast (702.142a). Mana abilities stay as they were (605: none of these is paid by one).
Every scenario checks the replay and a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import costs as C
from app.rules import coverage
from app.rules.costs import parse_ability_cost
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_attachments import ch
from tests.test_rules_conditionals import attack, creature, on_field, pick, settle, to_turn, until_asked
from tests.test_rules_effects import mana, replay_matches

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Ior Ruin Expedition', set_code="tst", number="H01", mana_cost='{1}{U}', cmc=2.0, type_line='Enchantment', oracle_text='Landfall — Whenever a land you control enters, you may put a quest counter on this enchantment.\nRemove three quest counters from this enchantment and sacrifice it: Draw two cards.', colors=['U'], color_identity=['U'], keywords=['Landfall']),  # noqa: E501
    card('Jarad, Golgari Lich Lord', set_code="tst", number="H02", mana_cost='{B}{B}{G}{G}', cmc=4.0, type_line='Legendary Creature — Zombie Elf', oracle_text="Jarad gets +1/+1 for each creature card in your graveyard.\n{1}{B}{G}, Sacrifice another creature: Each opponent loses life equal to the sacrificed creature's power.\nSacrifice a Swamp and a Forest: Return this card from your graveyard to your hand.", power='2', toughness='2', colors=['B', 'G'], color_identity=['B', 'G']),  # noqa: E501
    card('Loch Mare', set_code="tst", number="H03", mana_cost='{1}{U}', cmc=2.0, type_line='Creature — Horse Serpent', oracle_text='This creature enters with three -1/-1 counters on it.\n{1}{U}, Remove a counter from this creature: Draw a card.\n{2}{U}, Remove two counters from this creature: Tap target creature. Put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)', power='4', toughness='5', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Fain, the Broker', set_code="tst", number="H04", mana_cost='{2}{B}', cmc=3.0, type_line='Legendary Creature — Human Warlock', oracle_text='{T}, Sacrifice a creature: Put two +1/+1 counters on target creature.\n{T}, Remove a counter from a creature you control: Create a Treasure token.\n{T}, Sacrifice an artifact: Create a 2/1 white and black Inkling creature token with flying.\n{3}{B}: Untap Fain.', power='3', toughness='3', colors=['B'], color_identity=['B'], keywords=['Treasure']),  # noqa: E501
    card('Devoted Druid', set_code="tst", number="H05", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Elf Druid', oracle_text='{T}: Add {G}.\nPut a -1/-1 counter on this creature: Untap this creature.', power='0', toughness='2', colors=['G'], color_identity=['G']),  # noqa: E501
    card("Evershrike's Gift", set_code="tst", number="H06", mana_cost='{W}', cmc=1.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature gets +1/+0 and has flying.\n{1}{W}, Blight 2: Return this card from your graveyard to your hand. Activate only as a sorcery. (To blight 2, put two -1/-1 counters on a creature you control.)', colors=['W'], color_identity=['W'], keywords=['Blight', 'Enchant']),  # noqa: E501
    card('Grim Hireling', set_code="tst", number="H07", mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Tiefling Rogue', oracle_text='Whenever one or more creatures you control deal combat damage to a player, create two Treasure tokens.\n{B}, Sacrifice X Treasures: Target creature gets -X/-X until end of turn. Activate only as a sorcery.', power='3', toughness='2', colors=['B'], color_identity=['B'], keywords=['Treasure']),  # noqa: E501
    card('Secluded Starforge', set_code="tst", number="H08", mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{2}, {T}, Tap X untapped artifacts you control: Target creature gets +X/+0 until end of turn. Activate only as a sorcery.\n{5}, {T}: Create a 2/2 colorless Robot artifact creature token.'),  # noqa: E501
    card('Skullmane Baku', set_code="tst", number="H09", mana_cost='{3}{B}{B}', cmc=5.0, type_line='Creature — Spirit', oracle_text='Whenever you cast a Spirit or Arcane spell, you may put a ki counter on this creature.\n{1}, {T}, Remove X ki counters from this creature: Target creature gets -X/-X until end of turn.', power='2', toughness='1', colors=['B'], color_identity=['B']),  # noqa: E501
    card('Slate of Ancestry', set_code="tst", number="H10", mana_cost='{4}', cmc=4.0, type_line='Artifact', oracle_text='{4}, {T}, Discard your hand: Draw a card for each creature you control.'),  # noqa: E501
    card('Sinister Concoction', set_code="tst", number="H11", mana_cost='{B}', cmc=1.0, type_line='Enchantment', oracle_text='{B}, Pay 1 life, Mill a card, Discard a card, Sacrifice this enchantment: Destroy target creature.', colors=['B'], color_identity=['B'], keywords=['Mill']),  # noqa: E501
    card('Royal Herbalist', set_code="tst", number="H12", mana_cost='{W}', cmc=1.0, type_line='Creature — Human Cleric', oracle_text='{2}, Exile the top card of your library: You gain 1 life.', power='1', toughness='1', colors=['W'], color_identity=['W']),  # noqa: E501
    card('City of Shadows', set_code="tst", number="H13", mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}, Exile a creature you control: Put a storage counter on this land.\n{T}: Add {C} for each storage counter on this land.'),  # noqa: E501
    card('Lurking Evil', set_code="tst", number="H14", mana_cost='{B}{B}{B}', cmc=3.0, type_line='Enchantment', oracle_text='Pay half your life, rounded up: This enchantment becomes a 4/4 Phyrexian Horror creature with flying.', colors=['B'], color_identity=['B']),  # noqa: E501
    card('War Room', set_code="tst", number="H15", mana_cost='', cmc=0.0, type_line='Land', oracle_text="{T}: Add {C}.\n{3}, {T}, Pay life equal to the number of colors in your commanders' color identity: Draw a card."),  # noqa: E501
    card('Usher of the Fallen', set_code="tst", number="H16", mana_cost='{W}', cmc=1.0, type_line='Creature — Spirit Warrior', oracle_text='Boast — {1}{W}: Create a 1/1 white Human Warrior creature token. (Activate only if this creature attacked this turn and only once each turn.)', power='2', toughness='1', colors=['W'], color_identity=['W'], keywords=['Boast']),  # noqa: E501
    card('Forensic Researcher', set_code="tst", number="H17", mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Merfolk Detective', oracle_text="{T}: Untap another target permanent you control.\n{T}, Collect evidence 3: Tap target creature you don't control. (To collect evidence 3, exile cards with total mana value 3 or greater from your graveyard.)", power='1', toughness='3', colors=['U'], color_identity=['U'], keywords=['Collect evidence']),  # noqa: E501
    card('Camellia, the Seedmiser', set_code="tst", number="H18", mana_cost='{1}{B}{G}', cmc=3.0, type_line='Legendary Creature — Squirrel Warlock', oracle_text='Menace\nOther Squirrels you control have menace.\nWhenever you sacrifice one or more Foods, create a 1/1 green Squirrel creature token.\n{2}, Forage: Put a +1/+1 counter on each other Squirrel you control. (To forage, exile three cards from your graveyard or sacrifice a Food.)', power='3', toughness='3', colors=['B', 'G'], color_identity=['B', 'G'], keywords=['Forage', 'Menace']),  # noqa: E501
    card('Springjack Pasture', set_code="tst", number="H19", mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{4}, {T}: Create a 0/1 white Goat creature token.\n{T}, Sacrifice X Goats: Add X mana of any one color. You gain X life.'),  # noqa: E501
    card('Mold Folk', set_code="tst", number="H20", mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Fungus Warrior', oracle_text='Lifelink\nMold Harvest — {1}, Sacrifice another creature or an artifact: Put a +1/+1 counter on this creature.', power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=['Lifelink', 'Mold Harvest']),  # noqa: E501
    card('Pride Sovereign', set_code="tst", number="H21", mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Cat', oracle_text="This creature gets +1/+1 for each other Cat you control.\n{W}, {T}, Exert this creature: Create two 1/1 white Cat creature tokens with lifelink. (An exerted creature won't untap during your next untap step.)", power='2', toughness='2', colors=['G'], color_identity=['G', 'W'], keywords=['Exert']),  # noqa: E501
    card('Retribution of the Ancients', set_code="tst", number="H22", mana_cost='{B}', cmc=1.0, type_line='Enchantment', oracle_text='{B}, Remove X +1/+1 counters from among creatures you control: Target creature gets -X/-X until end of turn.', colors=['B'], color_identity=['B']),  # noqa: E501
    card('Tarox Bladewing', set_code="tst", number="H31", mana_cost='{2}{R}{R}{R}', cmc=5.0, type_line='Legendary Creature — Dragon', oracle_text='Flying, haste\nGrandeur — Discard another card named Tarox Bladewing: Tarox Bladewing gets +X/+X until end of turn, where X is its power.', power='4', toughness='3', colors=['R'], color_identity=['R'], keywords=['Flying', 'Grandeur', 'Haste']),  # noqa: E501
    card('Steward of Solidarity', set_code="tst", number="H32", mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Human Warrior', oracle_text="{T}, Exert this creature: Create a 1/1 white Warrior creature token with vigilance. (An exerted creature won't untap during your next untap step.)", power='2', toughness='2', colors=['W'], color_identity=['W'], keywords=['Exert']),  # noqa: E501
    card('Malevolent Noble', set_code="tst", number="H33", mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Human Noble', oracle_text='{2}, Sacrifice an artifact or another creature: Put a +1/+1 counter on this creature.', power='2', toughness='2', colors=['B'], color_identity=['B']),  # noqa: E501
    card('Ice Cream Kitty', set_code="tst", number="H34", mana_cost='{1}{B/G}', cmc=2.0, type_line='Artifact Creature — Food Cat Mutant', oracle_text='{2}, Sacrifice another creature or token: Draw a card. Activate only as a sorcery.\n{2}, {T}, Sacrifice this creature: You gain 3 life.', power='1', toughness='3', colors=['B', 'G'], color_identity=['B', 'G']),  # noqa: E501
    # (the front face only: the test table has no double-faced cards)
    card('Birgi, God of Storytelling', set_code="tst", number="H23", mana_cost='{2}{R}', cmc=3.0, type_line='Legendary Creature — God', oracle_text="Whenever you cast a spell, add {R}. Until end of turn, you don't lose this mana as steps and phases end.\nCreatures you control can boast twice during each of your turns rather than once.", power='3', toughness='3', colors=['R'], color_identity=['R']),  # noqa: E501
]
FULL = ["Ior Ruin Expedition", "Jarad, Golgari Lich Lord", "Loch Mare", "Fain, the Broker", "Devoted Druid", "Evershrike's Gift",
        "Grim Hireling", "Secluded Starforge", "Skullmane Baku", "Slate of Ancestry", "Sinister Concoction", "Royal Herbalist",
        "City of Shadows", "Lurking Evil", "War Room", "Usher of the Fallen", "Forensic Researcher", "Camellia, the Seedmiser",
        "Mold Folk", "Malevolent Noble", "Pride Sovereign", "Steward of Solidarity", "Tarox Bladewing"]
STILL_MANUAL = {  # (card, the line that stays manual)
    "Springjack Pasture": "Sacrifice X Goats",  # a mana ability (605): no X announced, no stack
    "Ice Cream Kitty": "Sacrifice another creature or token",  # (does "another" cover "token" too? not guessed)
    "Retribution of the Ancients": "from among creatures you control",  # (X counters split among several permanents)
}


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, p1=(), p2=()):
    from app.game.factory import PlayerSetup, new_game

    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def roundtrip(s):
    replay_matches(s)  # (the recorded history rebuilds the same table)
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)  # a save, loaded
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def ability(s, c, start):
    """The index of the card's ability whose text starts with ``start``."""
    return next(a.index for a in ch(s, c).abilities if a.text.startswith(start))


def activate(s, c, start, **kw):
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, start), **kw)


def refused(s, match, c, start, **kw):
    """Refused, and nothing at all changed (118.3, 601.2h)."""
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match=match):
        activate(s, c, start, **kw)
    assert s.state.model_dump(mode="json") == before


def counters(s, c, kind):
    return s.state.cards[c.id].counters.get(kind, 0)


def set_counters(s, c, kind, n):
    act(s, "p1", type="set_counter", card_id=c.id, kind=kind, value=n)


def gone(s, c):
    return c.id not in s.state.cards or not s.state.cards[c.id].zone.endswith(":battlefield")


def life(s, pid="p1"):
    return s.state.players[pid].life


def hand(s, pid="p1"):
    return zone(s.state, pid, "hand")


def to_graveyard(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def draw(s, n, pid="p1"):
    act(s, pid, type="move", card_ids=list(s.state.zones[f"{pid}:library"][:n]), to={"zone": "hand"})


def artifact(s, name, pid="p1", subtype="Test"):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": f"Token Artifact — {subtype}", "text": ""})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


# -- the grammar -------------------------------------------------------------------------------------
def test_parsing():
    def kinds(text, name="Test Card"):
        cost = parse_ability_cost(text, card_name=name)
        assert not cost.unsupported, text
        return [(c.kind, c.amount, c.counter, c.x) for c in cost.components if c.kind != C.MANA]

    assert kinds("Remove three quest counters from this enchantment and sacrifice it") == [
        (C.REMOVE_COUNTER, 3, "quest", False), (C.SACRIFICE, 1, None, False)]
    assert kinds("{T}, Sacrifice two lands and this artifact")[1:] == [(C.SACRIFICE, 2, None, False), (C.SACRIFICE, 1, None, False)]
    assert kinds("Remove two counters from this creature") == [(C.REMOVE_COUNTER, 2, C.ANY_COUNTER, False)]
    assert kinds("{1}, Remove X ki counters from this creature") == [(C.REMOVE_COUNTER, 0, "ki", True)]
    assert kinds("Put a -1/-1 counter on this creature") == [(C.PUT_COUNTER, 1, "-1/-1", False)]
    assert kinds("{1}{W}, Blight 2") == [(C.PUT_COUNTER, 2, "-1/-1", False)]
    assert kinds("{B}, Sacrifice X Treasures") == [(C.SACRIFICE, 0, None, True)]
    assert kinds("Mill a card") == [(C.MILL, 1, None, False)] and kinds("Exile the top ten cards of your library") == [
        (C.EXILE_LIBRARY, 10, None, False)]
    assert kinds("Exile seven cards from your graveyard")[0][:2] == (C.EXILE_FROM_GRAVEYARD, 7)
    assert kinds("Pay half your life, rounded up") == [(C.PAY_LIFE, 0, None, False)]
    assert kinds("Collect evidence 3") == [(C.COLLECT_EVIDENCE, 3, None, False)] and kinds("Forage") == [(C.FORAGE, 3, None, False)]
    # each of these only an activated ability's own activation pays: never a mana ability's (605), an optional payment's
    for text in ("Sacrifice X Goats", "Remove a counter from this creature", "Discard your hand", "Mill a card", "Blight 1"):
        assert parse_ability_cost(text).activation_only and not parse_ability_cost(text).basic
    assert parse_ability_cost("Sacrifice a creature").basic is False and not parse_ability_cost("Sacrifice a creature").activation_only
    # refused: an "or" between objects, exert, snow mana, counters among several permanents, "a black and red creature"
    for text in ("Sacrifice another creature or token", "Exert another creature", "{S}",
                 "Remove X +1/+1 counters from among creatures you control", "Sacrifice a black and red creature",
                 "Remove a counter from an artifact, creature, land, or planeswalker you control"):
        assert parse_ability_cost(text).unsupported, text


def test_optional_payments_and_mana_abilities_never_take_these_parts():
    from app.rules import mana, optional_payment

    assert optional_payment.parse("Sacrifice X Treasures") is None
    # -- if you do (wave 6F) -- "you may discard your hand. If you do, …" is paid as it resolves (tests/
    # test_rules_wave6f_if_you_do.py); the other activation-only parts still aren't
    assert optional_payment.parse("Discard your hand") is not None
    assert optional_payment.parse("Mill two cards") is not None  # (wave 8C: "you may mill four cards. If you do, …", 701.17b)
    assert optional_payment.parse("Forage") is None
    assert mana.parse_mana_ability("{T}, Sacrifice X Goats: Add X mana of any one color. You gain X life.") is None or \
        not parse_ability_cost("{T}, Sacrifice X Goats").basic


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", list(STILL_MANUAL))
def test_still_manual(cards, name):
    cov = coverage.of_card_data(cards.resolve(name))
    assert any(not f.supported and STILL_MANUAL[name] in f.label for f in cov.features)


# -- two parts joined by "and" -----------------------------------------------------------------------
def test_remove_quest_counters_and_sacrifice_it(cards):
    s = build(cards, p1=("Ior Ruin Expedition",))
    quest = on_field(s, "Ior Ruin Expedition")
    set_counters(s, quest, "quest", 2)
    refused(s, "doesn't have 3 quest counters", quest, "Remove three")  # 118.3
    set_counters(s, quest, "quest", 3)
    before = len(hand(s))
    activate(s, quest, "Remove three")
    settle(s)
    assert gone(s, quest) and len(hand(s)) == before + 2
    roundtrip(s)


def test_sacrifice_a_swamp_and_a_forest_from_the_graveyard(cards):
    s = build(cards, p1=("Jarad, Golgari Lich Lord",))
    jarad = to_graveyard(s, "Jarad, Golgari Lich Lord")
    forest = on_field(s, "Forest")
    refused(s, "can't pay", jarad, "Sacrifice a Swamp")  # (no Swamp)
    act(s, "p1", type="create_token", player="p1", token={"name": "Swamp Token", "type_line": "Token Land — Swamp", "text": ""})
    swamp = next(c for c in s.state.cards.values() if c.name == "Swamp Token")
    activate(s, jarad, "Sacrifice a Swamp")
    settle(s)
    assert gone(s, forest) and swamp.id not in s.state.cards and s.state.cards[jarad.id].zone == "p1:hand"
    roundtrip(s)


# -- counters of any kind ---------------------------------------------------------------------------------
def test_remove_counters_of_the_payers_choice(cards):
    s = build(cards, p1=("Loch Mare",), p2=("Grizzly Bears",))
    mare = on_field(s, "Loch Mare")
    set_counters(s, mare, "-1/-1", 3)
    mana(s, U=1, C=1)
    before = len(hand(s))
    activate(s, mare, "{1}{U}")  # (one kind only: no choice to make)
    settle(s)
    assert counters(s, mare, "-1/-1") == 2 and len(hand(s)) == before + 1
    set_counters(s, mare, "stun", 1)
    bear = on_field(s, "Grizzly Bears", "p2")
    mana(s, U=1, C=2)
    activate(s, mare, "{2}{U}", targets=[bear.id])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.max_choices == 2 and len(d.options) == 3  # (each counter, by kind)
    assert s.state.players["p1"].mana.get("U") == 1  # nothing paid yet
    stun = next(o.id for o in d.options if o.label.startswith("stun"))
    minus = next(o.id for o in d.options if o.label.startswith("-1/-1"))
    pick(s, stun, minus)
    settle(s)
    assert counters(s, mare, "stun") == 0 and counters(s, mare, "-1/-1") == 1
    assert s.state.cards[bear.id].tapped and counters(s, bear, "stun") == 1
    roundtrip(s)


def test_remove_counters_choice_given_up_front_must_be_on_the_source(cards):
    s = build(cards, p1=("Loch Mare",))
    mare = on_field(s, "Loch Mare")
    set_counters(s, mare, "-1/-1", 1)
    mana(s, U=1, C=2)
    refused(s, "doesn't have 2 counters", mare, "{2}{U}", targets=[mare.id])


def test_remove_a_counter_from_a_creature_you_control(cards):
    s = build(cards, p1=("Fain, the Broker",))
    fain = on_field(s, "Fain, the Broker")
    to_turn(s, 3)  # (no longer summoning sick)
    bear = creature(s, "p1", "Bear")
    creature(s, "p1", "Wolf")
    refused(s, "can't pay", fain, "{T}, Remove a counter")  # (no creature you control has a counter)
    set_counters(s, bear, "+1/+1", 1)
    activate(s, fain, "{T}, Remove a counter")  # (one counter on one creature: no question)
    settle(s)
    assert counters(s, bear, "+1/+1") == 0 and any(c.name == "Treasure" for c in s.state.cards.values())
    roundtrip(s)


# -- counters put as a cost (122.6; blight 701.68a) ----------------------------------------------------
def test_devoted_druid_untaps_until_it_dies(cards):
    s = build(cards, p1=("Devoted Druid",))
    druid = on_field(s, "Devoted Druid")
    act(s, "p1", type="tap", card_ids=[druid.id], tapped=True)
    activate(s, druid, "Put a -1/-1")
    settle(s)
    assert counters(s, druid, "-1/-1") == 1 and not s.state.cards[druid.id].tapped
    activate(s, druid, "Put a -1/-1")  # 0/0: it dies (704.5f) before the ability resolves
    settle(s)
    assert gone(s, druid)
    roundtrip(s)


def test_blight_from_the_graveyard(cards):
    s = build(cards, p1=("Evershrike's Gift",))
    gift = to_graveyard(s, "Evershrike's Gift")
    mana(s, W=1, C=1)
    refused(s, "can't pay", gift, "{1}{W}, Blight 2")  # 701.68b: no creature to blight
    bear = creature(s, "p1", "Bear", "3/3")
    activate(s, gift, "{1}{W}, Blight 2")
    settle(s)
    assert counters(s, bear, "-1/-1") == 2 and s.state.cards[gift.id].zone == "p1:hand"
    roundtrip(s)


# -- X announced as it's activated (107.3a) ----------------------------------------------------------
def test_sacrifice_x_treasures(cards):
    s = build(cards, p1=("Grim Hireling",), p2=("Grizzly Bears",))
    hireling = on_field(s, "Grim Hireling")
    t1, t2 = artifact(s, "T1", subtype="Treasure"), artifact(s, "T2", subtype="Treasure")
    bear = on_field(s, "Grizzly Bears", "p2")
    mana(s, B=1)
    refused(s, "value for X", hireling, "{B}, Sacrifice X", targets=[bear.id])
    refused(s, "can't pay", hireling, "{B}, Sacrifice X", targets=[bear.id], x_value=3)  # (two Treasures)
    activate(s, hireling, "{B}, Sacrifice X", targets=[bear.id], x_value=2)
    settle(s)
    assert t1.id not in s.state.cards and t2.id not in s.state.cards and gone(s, bear)
    roundtrip(s)


def test_sacrifice_x_treasures_with_x_zero_sacrifices_nothing(cards):
    """-- review (Codex) -- X = 0 is a legal announcement (107.3a): with Treasures around, nothing is chosen or asked."""
    s = build(cards, p1=("Grim Hireling",), p2=("Grizzly Bears",))
    hireling = on_field(s, "Grim Hireling")
    t1 = artifact(s, "T1", subtype="Treasure")
    bear = on_field(s, "Grizzly Bears", "p2")
    mana(s, B=1)
    activate(s, hireling, "{B}, Sacrifice X", targets=[bear.id], x_value=0)
    assert s.state.rules.decision is None or s.state.rules.decision.kind != "choose_cards"
    settle(s)
    assert s.state.cards[t1.id].zone.endswith(":battlefield") and not gone(s, bear)
    roundtrip(s)


def test_tap_x_untapped_artifacts(cards):
    s = build(cards, p1=("Secluded Starforge",))
    forge = on_field(s, "Secluded Starforge")
    arts = [artifact(s, f"A{i}") for i in range(3)]
    bear = creature(s, "p1", "Bear")
    mana(s, C=2)
    activate(s, forge, "{2}, {T}, Tap X", targets=[bear.id], x_value=2)
    d = s.state.rules.decision
    assert d is not None and d.max_choices == 2 and {o.id for o in d.options} == {a.id for a in arts}
    assert "options" not in s.view("p2")["rules"]["decision"]  # (the payer's own choice)
    pick(s, arts[0].id, arts[2].id)
    settle(s)
    assert [s.state.cards[a.id].tapped for a in arts] == [True, False, True]
    assert ch(s, bear).pt == (4, 2)
    roundtrip(s)


def test_remove_x_ki_counters(cards):
    s = build(cards, p1=("Skullmane Baku",), p2=("Grizzly Bears",))
    baku = on_field(s, "Skullmane Baku")
    to_turn(s, 3)
    bear = on_field(s, "Grizzly Bears", "p2")
    set_counters(s, baku, "ki", 3)
    mana(s, C=1)
    refused(s, "doesn't have 4 ki counters", baku, "{1}, {T}, Remove X", targets=[bear.id], x_value=4)
    activate(s, baku, "{1}, {T}, Remove X", targets=[bear.id], x_value=2)
    settle(s)
    assert counters(s, baku, "ki") == 1 and gone(s, bear)
    roundtrip(s)


# -- your hand, your library, your life ----------------------------------------------------------------
def test_discard_your_hand_even_an_empty_one(cards):
    s = build(cards, p1=("Slate of Ancestry",))
    slate = on_field(s, "Slate of Ancestry")
    creature(s, "p1", "Bear")
    creature(s, "p1", "Wolf")
    draw(s, 3)
    old = list(hand(s))
    mana(s, C=4)
    activate(s, slate, "{4}, {T}, Discard")
    settle(s)
    assert all(s.state.cards[c].zone == "p1:graveyard" for c in old) and len(hand(s)) == 2
    act(s, "p1", type="move", card_ids=list(hand(s)), to={"zone": "graveyard"})
    act(s, "p1", type="tap", card_ids=[slate.id], tapped=False)
    mana(s, C=4)
    activate(s, slate, "{4}, {T}, Discard")  # (an empty hand pays "discard your hand")
    settle(s)
    assert len(hand(s)) == 2
    roundtrip(s)


def test_sinister_concoction_pays_five_parts_at_once(cards):
    s = build(cards, p1=("Sinister Concoction",), p2=("Grizzly Bears",))
    potion = on_field(s, "Sinister Concoction")
    bear = on_field(s, "Grizzly Bears", "p2")
    draw(s, 2)
    top = s.state.zones["p1:library"][0]
    cards_in_hand = list(hand(s))
    mana(s, B=1)
    activate(s, potion, "{B}", targets=[bear.id])
    d = s.state.rules.decision  # which card to discard: the payer's private choice
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == set(cards_in_hand)
    assert "options" not in s.view("p2")["rules"]["decision"]
    assert s.state.zones["p1:library"][0] == top and life(s) == 40  # nothing paid yet
    pick(s, cards_in_hand[0])
    settle(s)
    assert life(s) == 39 and s.state.cards[top].zone == "p1:graveyard"
    assert s.state.cards[cards_in_hand[0]].zone == "p1:graveyard" and gone(s, potion) and gone(s, bear)
    roundtrip(s)


def test_exile_the_top_card_of_your_library(cards):
    s = build(cards, p1=("Royal Herbalist",))
    herbalist = on_field(s, "Royal Herbalist")
    top = s.state.zones["p1:library"][0]
    mana(s, C=2)
    activate(s, herbalist, "{2}, Exile")
    settle(s)
    assert s.state.cards[top].zone.endswith("exile") and life(s) == 41
    act(s, "p1", type="move", card_ids=list(s.state.zones["p1:library"]), to={"zone": "graveyard"})
    mana(s, C=2)
    refused(s, "1 card in your library", herbalist, "{2}, Exile")  # 118.3
    roundtrip(s)


def test_exile_a_creature_you_control(cards):
    s = build(cards, p1=("City of Shadows",))
    city = on_field(s, "City of Shadows")
    refused(s, "can't pay", city, "{T}, Exile")
    bear = creature(s, "p1", "Bear")
    activate(s, city, "{T}, Exile")
    settle(s)
    assert bear.id not in s.state.cards or s.state.cards[bear.id].zone.endswith("exile")
    assert counters(s, city, "storage") == 1
    roundtrip(s)


def test_pay_half_your_life_rounded_up(cards):
    s = build(cards, p1=("Lurking Evil",))
    evil = on_field(s, "Lurking Evil")
    act(s, "p1", type="set_life", player="p1", value=7)
    activate(s, evil, "Pay half")
    settle(s)
    assert life(s) == 3 and ch(s, evil).is_creature and ch(s, evil).pt == (4, 4)  # (7 → pays 4: 107.1a)
    roundtrip(s)


def test_war_room_pays_the_commanders_colors(cards):
    s = build(cards, p1=("War Room",))
    room = on_field(s, "War Room")
    mana(s, C=3)
    before = len(hand(s))
    activate(s, room, "{3}, {T}, Pay life")
    settle(s)
    assert life(s) == 39 and len(hand(s)) == before + 1  # (Krenko: one color, 903.4)
    roundtrip(s)


def test_war_room_without_a_commander_is_unpayable(cards):
    s = build(cards, p1=("War Room",))
    room = on_field(s, "War Room")
    for c in s.state.cards.values():
        if c.owner == "p1" and c.commander_key:
            c.commander_key = None  # (a table with no commander for Alice)
    mana(s, C=3)
    refused(s, "903.4f", room, "{3}, {T}, Pay life")


# -- collect evidence (701.59) and forage (701.61) --------------------------------------------------------
def test_collect_evidence(cards):
    s = build(cards, p1=("Forensic Researcher", "Grim Hireling", "Devoted Druid"), p2=("Grizzly Bears",))
    researcher = on_field(s, "Forensic Researcher")
    to_turn(s, 3)
    bear = on_field(s, "Grizzly Bears", "p2")
    druid = to_graveyard(s, "Devoted Druid")  # (mana value 2: not enough alone, 701.59b)
    refused(s, "can't pay", researcher, "{T}, Collect", targets=[bear.id])
    hireling = to_graveyard(s, "Grim Hireling")
    refused(s, "don't pay", researcher, "{T}, Collect", targets=[bear.id], cost_choices=[{"component": 1, "cards": [druid.id]}])
    activate(s, researcher, "{T}, Collect", targets=[bear.id])
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {druid.id, hireling.id}
    pick(s, hireling.id)
    settle(s)
    assert s.state.cards[hireling.id].zone.endswith("exile") and s.state.cards[druid.id].zone == "p1:graveyard"
    assert s.state.cards[bear.id].tapped
    roundtrip(s)


def test_forage_sacrificing_a_food(cards):
    s = build(cards, p1=("Camellia, the Seedmiser", "Grim Hireling", "Devoted Druid"))
    camellia = on_field(s, "Camellia, the Seedmiser")
    mana(s, C=2)
    refused(s, "can't pay", camellia, "{2}, Forage")  # (two graveyard cards, no Food)
    gy = [to_graveyard(s, "Grim Hireling"), to_graveyard(s, "Devoted Druid")]
    food = artifact(s, "Snack", subtype="Food")
    activate(s, camellia, "{2}, Forage")
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {food.id, *(c.id for c in gy)}
    with pytest.raises(ActionError):
        pick(s, gy[0].id)  # (one graveyard card pays nothing)
    pick(s, food.id)
    settle(s)
    assert food.id not in s.state.cards and all(s.state.cards[c.id].zone == "p1:graveyard" for c in gy)
    assert any(c.name == "Squirrel" for c in s.state.cards.values())  # (Camellia: "Whenever you sacrifice one or more Foods")
    roundtrip(s)


# -- boast (702.142a) ---------------------------------------------------------------------------------
def test_boast_only_after_attacking_and_once_each_turn(cards):
    s = build(cards, p1=("Usher of the Fallen", "Birgi, God of Storytelling"))
    usher = on_field(s, "Usher of the Fallen")
    to_turn(s, 3)
    mana(s, W=1, C=1)
    refused(s, "attacked this turn", usher, "Boast")
    act(s, "p1", type="pass_priority")  # → declare attackers
    attack(s, (usher, "p2"))
    mana(s, W=1, C=1)  # (the pool emptied as the step ended)
    activate(s, usher, "Boast")
    until_asked(s)
    warriors = [c for c in s.state.cards.values() if c.name.startswith("Human Warrior")]
    assert len(warriors) == 1
    mana(s, W=1, C=1)
    refused(s, "once each turn", usher, "Boast")
    on_field(s, "Birgi, God of Storytelling")  # "Creatures you control can boast twice during each of your turns"
    activate(s, usher, "Boast")
    until_asked(s)
    assert len([c for c in s.state.cards.values() if c.name.startswith("Human Warrior")]) == 2
    roundtrip(s)


# -- "or" between two nouns, grandeur, exert (701.43) -------------------------------------------------------
def test_sacrifice_another_creature_or_an_artifact(cards):
    s = build(cards, p1=("Mold Folk", "Malevolent Noble"))
    folk = on_field(s, "Mold Folk")
    mana(s, C=1)
    refused(s, "can't pay", folk, "Mold Harvest")  # (not itself: "another" creature)
    snack = artifact(s, "Snack", subtype="Food")
    bear = creature(s, "p1", "Bear")
    activate(s, folk, "Mold Harvest")
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {snack.id, bear.id}
    pick(s, snack.id)
    settle(s)
    assert snack.id not in s.state.cards and counters(s, folk, "+1/+1") == 1
    noble = on_field(s, "Malevolent Noble")  # "Sacrifice an artifact or another creature"
    mana(s, C=2)
    activate(s, noble, "{2}", cost_choices=[{"component": 1, "cards": [bear.id]}])
    settle(s)
    assert bear.id not in s.state.cards and counters(s, noble, "+1/+1") == 1
    roundtrip(s)


def test_grandeur_discards_another_card_with_the_same_name(cards):
    s = build(cards, p1=("Tarox Bladewing", "Tarox Bladewing"))
    tarox, other = [c for c in s.state.cards.values() if c.name == "Tarox Bladewing"]
    act(s, "p1", type="move", card_ids=[tarox.id], to={"player": "p1", "zone": "battlefield"})
    draw(s, 2)
    act(s, "p1", type="move", card_ids=[other.id], to={"zone": "graveyard"})
    refused(s, "can't pay", tarox, "Grandeur")  # (no other Tarox in hand)
    act(s, "p1", type="move", card_ids=[other.id], to={"zone": "hand"})
    before = len(hand(s))
    assert before >= 2
    activate(s, tarox, "Grandeur")  # (the only card of that name: no question, the rest of the hand stays)
    settle(s)
    assert s.state.cards[other.id].zone == "p1:graveyard" and len(hand(s)) == before - 1
    assert ch(s, tarox).pt == (8, 7)
    roundtrip(s)


def test_an_exerted_creature_skips_its_controllers_next_untap_step(cards):
    s = build(cards, p1=("Steward of Solidarity",))
    steward = on_field(s, "Steward of Solidarity")
    to_turn(s, 3)
    activate(s, steward, "{T}, Exert")
    settle(s)
    assert s.state.cards[steward.id].tapped and any(c.name.startswith("Warrior") for c in s.state.cards.values())
    assert s.state.rules.exerted
    roundtrip(s)
    to_turn(s, 4)  # (Bob's untap step: not Alice's)
    assert s.state.cards[steward.id].tapped
    to_turn(s, 5)  # Alice's next untap step: it doesn't untap (701.43a)
    assert s.state.cards[steward.id].tapped and not s.state.rules.exerted
    to_turn(s, 7)  # … and the one after, it does
    assert not s.state.cards[steward.id].tapped
    roundtrip(s)
