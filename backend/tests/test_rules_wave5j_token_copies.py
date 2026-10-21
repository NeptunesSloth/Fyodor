"""Token copies, populate and attach on entry (wave 5J), researched against CR 2026-09-25.

* Attach on entry (301.5b, 701.3a-b): "When this Equipment enters, attach it to target creature you control." — the
  Equipment moves onto the target if it could equip it (else it doesn't move); an illegal target (608.2b) or an
  Equipment that left (400.7) means nothing happens. "Whenever an Equipment you control enters, you may attach it …"
  (Sigarda's Aid, Hammer of Nazahn): the object the trigger was about. app/rules/attach_entry.py.
* Populate (701.36a-b): choose a creature token you control (no target), copy it; nothing without one.
* "For each <permanent>, create a token that's a copy of that <permanent>" (Second Harvest, Rhys the Redeemed,
  Multiversal Incursion, Clone Legion, Parallel Evolution "its controller creates"); Kambal's "for each of them".
  app/rules/populate.py over the copy system (app/rules/copying.py: 707.2, 707.3, 707.9).
* "except it's a 1/1 green Frog" (707.9b, 707.9d, 205.1a): P/T, colors and creature types set; changeling not copied.
* A copy of an object that left the battlefield uses its last known information (608.2h, 111.12).
* "Then if you control eight or more artifacts with the same name as one another, you win the game." (104.2b).

Every scenario uses real Commander-legal cards with their current Oracle text (data/cards.sqlite), checks that
replaying the recorded history reproduces the table, and that a save/load round trip keeps it.
"""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from app.rules.characteristics import Characteristics, parse_type_line
from app.rules.oracle import parse_abilities
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import replay_matches

EXTRA = [
    card('Embercleave', set_code='t5j', number='J01', mana_cost='{4}{R}{R}', cmc=6.0, type_line='Legendary Artifact — Equipment', oracle_text='Flash\nThis spell costs {1} less to cast for each attacking creature you control.\nWhen Embercleave enters, attach it to target creature you control.\nEquipped creature gets +1/+1 and has double strike and trample.\nEquip {3}', colors=['R'], color_identity=['R'], keywords=['Equip', 'Flash']),  # noqa: E501
    card('Celestial Armor', set_code='t5j', number='J02', mana_cost='{2}{W}', cmc=3.0, type_line='Artifact — Equipment', oracle_text='Flash (You may cast this spell any time you could cast an instant.)\nWhen this Equipment enters, attach it to target creature you control. That creature gains hexproof and indestructible until end of turn.\nEquipped creature gets +2/+0 and has flying.\nEquip {3}{W} ({3}{W}: Attach to target creature you control. Equip only as a sorcery.)', colors=['W'], color_identity=['W'], keywords=['Equip', 'Flash']),  # noqa: E501
    card('Phantom Blade', set_code='t5j', number='J03', mana_cost='{4}{B}', cmc=5.0, type_line='Artifact — Equipment', oracle_text="When this Equipment enters, attach it to up to one target creature you control. Destroy up to one other target creature.\nEquipped creature gets +1/+1 and has menace. (It can't be blocked except by two or more creatures.)\nEquip {2}", colors=['B'], color_identity=['B'], keywords=['Equip']),  # noqa: E501
    card('Hidden Blade', set_code='t5j', number='J04', mana_cost='{2}', cmc=2.0, type_line='Artifact — Equipment', oracle_text='Flash\nWhen this Equipment enters, attach it to target creature you control. If that creature is an Assassin, it gains deathtouch until end of turn.\nEquipped creature gets +1/+0 and has first strike.\nEquip {2}', colors=[], color_identity=[], keywords=['Equip', 'Flash']),  # noqa: E501
    card("Sigarda's Aid", set_code='t5j', number='J05', mana_cost='{W}', cmc=1.0, type_line='Enchantment', oracle_text='You may cast Aura and Equipment spells as though they had flash.\nWhenever an Equipment you control enters, you may attach it to target creature you control.', colors=['W'], color_identity=['W']),  # noqa: E501
    card('Hammer of Nazahn', set_code='t5j', number='J06', mana_cost='{4}', cmc=4.0, type_line='Legendary Artifact — Equipment', oracle_text='Whenever Hammer of Nazahn or another Equipment you control enters, you may attach that Equipment to target creature you control.\nEquipped creature gets +2/+0 and has indestructible.\nEquip {4}', colors=[], color_identity=[], keywords=['Equip']),  # noqa: E501
    card('Rootborn Defenses', set_code='t5j', number='J07', mana_cost='{2}{W}', cmc=3.0, type_line='Instant', oracle_text="Populate. Creatures you control gain indestructible until end of turn. (To populate, create a token that's a copy of a creature token you control.)", colors=['W'], color_identity=['W'], keywords=['Populate']),  # noqa: E501
    card("Trostani, Selesnya's Voice", set_code='t5j', number='J08', mana_cost='{G}{G}{W}{W}', cmc=4.0, type_line='Legendary Creature — Dryad', oracle_text="Whenever another creature you control enters, you gain life equal to that creature's toughness.\n{1}{G}{W}, {T}: Populate. (Create a token that's a copy of a creature token you control.)", power='2', toughness='5', colors=['G', 'W'], color_identity=['G', 'W'], keywords=['Populate']),  # noqa: E501
    card("Horncaller's Chant", set_code='t5j', number='J09', mana_cost='{7}{G}', cmc=8.0, type_line='Sorcery', oracle_text="Create a 4/4 green Rhino creature token with trample, then populate. (Create a token that's a copy of a creature token you control.)", colors=['G'], color_identity=['G'], keywords=['Populate']),  # noqa: E501
    card('Second Harvest', set_code='t5j', number='J10', mana_cost='{2}{G}{G}', cmc=4.0, type_line='Instant', oracle_text="For each token you control, create a token that's a copy of that permanent.", colors=['G'], color_identity=['G']),  # noqa: E501
    card('Rhys the Redeemed', set_code='t5j', number='J11', mana_cost='{G/W}', cmc=1.0, type_line='Legendary Creature — Elf Warrior', oracle_text="{2}{G/W}, {T}: Create a 1/1 green and white Elf Warrior creature token.\n{4}{G/W}{G/W}, {T}: For each creature token you control, create a token that's a copy of that creature.", power='1', toughness='1', colors=['G', 'W'], color_identity=['G', 'W']),  # noqa: E501
    card('Multiversal Incursion', set_code='t5j', number='J12', mana_cost='{5}{U}{U}', cmc=7.0, type_line='Sorcery', oracle_text="For each nontoken creature you control, create a token that's a copy of that creature, except it isn't legendary.", colors=['U'], color_identity=['U']),  # noqa: E501
    card('Clone Legion', set_code='t5j', number='J13', mana_cost='{7}{U}{U}', cmc=9.0, type_line='Sorcery', oracle_text="For each creature target player controls, create a token that's a copy of that creature.", colors=['U'], color_identity=['U']),  # noqa: E501
    card('Parallel Evolution', set_code='t5j', number='J14', mana_cost='{3}{G}{G}', cmc=5.0, type_line='Sorcery', oracle_text="For each creature token on the battlefield, its controller creates a token that's a copy of that creature.\nFlashback {4}{G}{G}{G} (You may cast this card from your graveyard for its flashback cost. Then exile it.)", colors=['G'], color_identity=['G'], keywords=['Flashback']),  # noqa: E501
    card('Kambal, Profiteering Mayor', set_code='t5j', number='J15', mana_cost='{1}{W}{B}', cmc=3.0, type_line='Legendary Creature — Human Advisor', oracle_text="Whenever one or more tokens your opponents control enter, for each of them, create a tapped token that's a copy of it. This ability triggers only once each turn.\nWhenever one or more tokens you control enter, each opponent loses 1 life and you gain 1 life.", power='2', toughness='4', colors=['B', 'W'], color_identity=['B', 'W']),  # noqa: E501
    card('Mechanized Production', set_code='t5j', number='J16', mana_cost='{2}{U}{U}', cmc=4.0, type_line='Enchantment — Aura', oracle_text="Enchant artifact you control\nAt the beginning of your upkeep, create a token that's a copy of enchanted artifact. Then if you control eight or more artifacts with the same name as one another, you win the game.", colors=['U'], color_identity=['U'], keywords=['Enchant']),  # noqa: E501
    card('Croaking Counterpart', set_code='t5j', number='J17', mana_cost='{1}{G}{U}', cmc=3.0, type_line='Sorcery', oracle_text="Create a token that's a copy of target non-Frog creature, except it's a 1/1 green Frog.\nFlashback {3}{G}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)", colors=['G', 'U'], color_identity=['G', 'U'], keywords=['Flashback']),  # noqa: E501
    card('Mist-Syndicate Naga', set_code='t5j', number='J18', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Snake Ninja', oracle_text="Ninjutsu {2}{U} ({2}{U}, Return an unblocked attacker you control to hand: Put this card onto the battlefield from your hand tapped and attacking.)\nWhenever this creature deals combat damage to a player, create a token that's a copy of this creature.", power='3', toughness='1', colors=['U'], color_identity=['U'], keywords=['Ninjutsu']),  # noqa: E501
    card('Miirym, Sentinel Wyrm', set_code='t5j', number='J19', mana_cost='{3}{G}{U}{R}', cmc=6.0, type_line='Legendary Creature — Dragon Spirit', oracle_text="Flying, ward {2}\nWhenever another nontoken Dragon you control enters, create a token that's a copy of it, except the token isn't legendary.", power='6', toughness='6', colors=['G', 'R', 'U'], color_identity=['G', 'R', 'U'], keywords=['Flying', 'Ward']),  # noqa: E501
    card('Shivan Dragon', set_code='t5j', number='J20', mana_cost='{4}{R}{R}', cmc=6.0, type_line='Creature — Dragon', oracle_text='Flying\n{R}: This creature gets +1/+0 until end of turn.', power='5', toughness='5', colors=['R'], color_identity=['R'], keywords=['Flying']),  # noqa: E501
    card('Darksteel Citadel', set_code='t5j', number='J21', mana_cost='', cmc=0.0, type_line='Artifact Land', oracle_text='Indestructible\n{T}: Add {C}.', colors=[], color_identity=[], keywords=['Indestructible']),  # noqa: E501
    card('Changeling Outcast', set_code='t5j', number='J22', mana_cost='{B}', cmc=1.0, type_line='Creature — Shapeshifter', oracle_text="Changeling (This card is every creature type.)\nThis creature can't block and can't be blocked.", power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=['Changeling']),  # noqa: E501
    card('Galadhrim Bow', set_code='t5j', number='J23', mana_cost='{2}{G}', cmc=3.0, type_line='Artifact — Equipment', oracle_text='Flash\nWhen this Equipment enters, attach it to target creature you control. Untap that creature.\nEquipped creature gets +1/+2 and has reach.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)', colors=['G'], color_identity=['G'], keywords=['Equip', 'Flash']),  # noqa: E501
    card("Hunter's Bow", set_code='t5j', number='J24', mana_cost='{1}{G}', cmc=2.0, type_line='Artifact — Equipment', oracle_text="When this Equipment enters, attach it to target creature you control. That creature deals damage equal to its power to up to one target creature you don't control.\nEquipped creature has reach and ward {2}.\nEquip {1}", colors=['G'], color_identity=['G'], keywords=['Equip']),  # noqa: E501
    # putting a card from your hand onto the battlefield
    card('Stoneforge Mystic', set_code='t5j', number='J31', mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Kor Artificer', oracle_text='When this creature enters, you may search your library for an Equipment card, reveal it, put it into your hand, then shuffle.\n{1}{W}, {T}: You may put an Equipment card from your hand onto the battlefield.', power='1', toughness='2', colors=['W'], color_identity=['W']),  # noqa: E501
    card('Elvish Piper', set_code='t5j', number='J32', mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Elf Shaman', oracle_text='{G}, {T}: You may put a creature card from your hand onto the battlefield.', power='1', toughness='1', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Growth Spiral', set_code='t5j', number='J33', mana_cost='{G}{U}', cmc=2.0, type_line='Instant', oracle_text='Draw a card. You may put a land card from your hand onto the battlefield.', colors=['G', 'U'], color_identity=['G', 'U']),  # noqa: E501
    card('Incandescent Soulstoke', set_code='t5j', number='J34', mana_cost='{2}{R}', cmc=3.0, type_line='Creature — Elemental Shaman', oracle_text='Other Elemental creatures you control get +1/+1.\n{1}{R}, {T}: You may put an Elemental creature card from your hand onto the battlefield. That creature gains haste until end of turn. Sacrifice it at the beginning of the next end step.', power='2', toughness='2', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Air Elemental', set_code='t5j', number='J35', mana_cost='{3}{U}{U}', cmc=5.0, type_line='Creature — Elemental', oracle_text='Flying', power='4', toughness='4', colors=['U'], color_identity=['U'], keywords=['Flying']),  # noqa: E501
    card('Kona, Rescue Beastie', set_code='t5j', number='J36', mana_cost='{3}{G}', cmc=4.0, type_line='Legendary Creature — Beast Survivor', oracle_text='Survival — At the beginning of your second main phase, if Kona is tapped, you may put a permanent card from your hand onto the battlefield.', power='4', toughness='3', colors=['G'], color_identity=['G'], keywords=['Survival']),  # noqa: E501
]
NAMES = [c["name"] for c in EXTRA]
HELPERS = ("Darksteel Citadel", "Changeling Outcast", "Shivan Dragon", "Mist-Syndicate Naga", "Miirym, Sentinel Wyrm",
           "Air Elemental")


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


# -- helpers ---------------------------------------------------------------------------------------------------------
def game(cards, alice=(), bob=()):
    """Alice (Krenko) and Bob (Atraxa) with these cards in their decks; Alice's first main phase."""
    from app.game.factory import PlayerSetup, new_game
    from tests.game_helpers import deck, enable

    a = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in alice), (9, "Forest")])
    b = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def find(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.is_token)


def put(s, name, where="battlefield", pid="p1"):
    c = find(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": where})
    return s.state.cards[c.id]


def token(s, pid, name, pt="2/2", type_line="Token Creature — Test"):
    before = set(s.state.cards)
    p, t = pt.split("/") if pt else (None, None)
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": p, "toughness": t,
                                                        "text": ""})
    return next(c for cid, c in s.state.cards.items() if cid not in before)


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def tokens(s, pid=None):
    return [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(":battlefield")
            and (pid is None or c.controller == pid)]


def drive(s, choose=None, limit=40):
    """Resolve the stack; ``choose(decision)`` answers each decision (None: the first options)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            picked = choose(d) if choose else None
            if picked is None:
                picked = [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=picked)
            continue
        if not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("the stack never emptied")


def picks(*ids):
    """Answer each decision offering one of these ids with the first such id still unused; else the plain way."""
    queue = list(ids)

    def choose(d):
        wanted = [i for i in queue if i in {o.id for o in d.options}]
        if wanted:
            queue.remove(wanted[0])
            return [wanted[0]]
        return None
    return choose


def cast(s, name, pid="p1", targets=None, **pool):
    c = put(s, name, "hand", pid)
    mana(s, pid, **pool)
    act(s, pid, type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}))
    return s.state.cards[c.id]


def trigger_waiting(s, permanent):
    """Pass until ``permanent`` is on the battlefield and its trigger waits on the stack (decisions answered the plain
    way); ``responsive`` first."""
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.cards[permanent.id].zone.endswith(":battlefield") and s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no trigger waited")


def responsive(s):
    """Everyone stops at each object on the stack."""
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")


def own_next_turn(s):
    """On to Alice's next turn (her upkeep triggers resolved), or until someone won."""
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.rules.winner is not None or (s.state.turn.number == 3 and s.state.turn.phase == "main1"),
          limit=400)


def roundtrip(s):
    """Replay rebuilds the same table, and a save/load round trip keeps it."""
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


def ok(text, name="Card", type_line="Creature — Test"):
    sup, types, sub = parse_type_line(type_line)
    feats = coverage.features_of(Characteristics(name=name, supertypes=sup, types=types, subtypes=sub, oracle_text=text,
                                                 abilities=tuple(parse_abilities(text, spell=bool(types & {"Instant", "Sorcery"})))))
    return all(f.supported for f in feats if f.id.startswith("text:"))


# -- coverage ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", [n for n in NAMES if n not in HELPERS])
def test_the_family_is_covered(name):
    data = next(c for c in EXTRA if c["name"] == name)
    sup, types, sub = parse_type_line(data["type_line"])
    feats = coverage.features_of(Characteristics(name=name, supertypes=sup, types=types, subtypes=sub,
                                                 oracle_text=data["oracle_text"],
                                                 abilities=tuple(parse_abilities(data["oracle_text"], spell=bool(types & {"Instant", "Sorcery"})))))
    assert [f.label for f in feats if not f.supported] == []


def test_wordings_still_refused():
    # Repeated populate is now supported; unrelated attachment and mismatched-noun forms stay refused.
    assert ok("Populate X times.", "Full Flowering", "Sorcery")
    assert not ok("Return target Equipment card from your graveyard to the battlefield. Attach it to target creature you "
                  "control.", "Card", "Sorcery")
    assert not ok("For each other creature you control, create a token that's a copy of that creature.", "Card", "Sorcery")
    assert not ok("For each creature you control, create a token that's a copy of that artifact.", "Card", "Sorcery")


# -- attach on entry (301.5b, 701.3) -----------------------------------------------------------------------------------
def test_embercleave_attaches_to_the_target_as_its_trigger_resolves(cards):
    s = game(cards, ["Embercleave", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    cleave = cast(s, "Embercleave", R=2, C=4)
    drive(s, picks(bears.id))
    assert s.state.cards[cleave.id].zone == "p1:battlefield" and s.state.cards[cleave.id].attached_to == bears.id
    got = ch(s, bears)
    assert got.pt == (3, 3) and {"double strike", "trample"} <= got.keywords
    roundtrip(s)


def test_celestial_armor_attaches_and_the_creature_gains_hexproof_and_indestructible(cards):
    s = game(cards, ["Celestial Armor", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    armor = cast(s, "Celestial Armor", W=1, C=2)
    drive(s, picks(bears.id))
    assert s.state.cards[armor.id].attached_to == bears.id
    got = ch(s, bears)
    assert got.pt == (4, 2) and {"flying", "hexproof", "indestructible"} <= got.keywords
    roundtrip(s)
    s2 = GameSession(s.history.rebuild(), cards=s.cards)  # a saved game, loaded
    assert s2.state.cards[armor.id].attached_to == bears.id


def test_an_equipment_that_left_before_its_trigger_resolved_attaches_nothing(cards):
    """400.7: "it" is the Equipment that entered; once it left the battlefield there is nothing to attach."""
    s = game(cards, ["Galadhrim Bow", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    responsive(s)
    bow = cast(s, "Galadhrim Bow", G=1, C=2)
    trigger_waiting(s, bow)  # the Bow resolved; its trigger is on the stack, targeting the Bears
    assert s.state.cards[bow.id].attached_to is None
    act(s, "p1", type="tap", card_ids=[bears.id])
    act(s, "p1", type="move", card_ids=[bow.id], to={"player": "p1", "zone": "hand"})
    drive(s)
    assert s.state.cards[bow.id].zone == "p1:hand" and s.state.cards[bow.id].attached_to is None
    assert not s.state.cards[bears.id].tapped  # "Untap that creature." still happens (the target is legal)
    roundtrip(s)


def test_phantom_blade_attaches_and_destroys_another_target(cards):
    s = game(cards, ["Phantom Blade", "Grizzly Bears"], ["Grizzly Bears"])
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", pid="p2")
    blade = cast(s, "Phantom Blade", B=1, C=4)
    drive(s, picks(mine.id, theirs.id))
    assert s.state.cards[blade.id].attached_to == mine.id
    assert s.state.cards[theirs.id].zone == "p2:graveyard"
    assert ch(s, mine).pt == (3, 3) and "menace" in ch(s, mine).keywords
    roundtrip(s)


def test_hidden_blade_gives_deathtouch_only_to_an_assassin(cards):
    s = game(cards, ["Hidden Blade", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    blade = cast(s, "Hidden Blade", C=2)
    drive(s, picks(bears.id))
    assert s.state.cards[blade.id].attached_to == bears.id
    assert "deathtouch" not in ch(s, bears).keywords and "first strike" in ch(s, bears).keywords
    roundtrip(s)


def test_hunters_bow_attaches_then_the_creature_deals_damage_equal_to_its_power(cards):
    s = game(cards, ["Hunter's Bow", "Grizzly Bears"], ["Grizzly Bears"])
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", pid="p2")
    bow = cast(s, "Hunter's Bow", G=1, C=1)
    drive(s, picks(mine.id, theirs.id))
    assert s.state.cards[bow.id].attached_to == mine.id and s.state.cards[theirs.id].zone == "p2:graveyard"
    roundtrip(s)


def test_sigardas_aid_may_attach_an_equipment_that_enters(cards):
    s = game(cards, ["Sigarda's Aid", "Bonesplitter", "Grizzly Bears"])
    put(s, "Sigarda's Aid")
    bears = put(s, "Grizzly Bears")
    splitter = cast(s, "Bonesplitter", C=1)
    drive(s, picks(bears.id))
    assert s.state.cards[splitter.id].attached_to == bears.id and ch(s, bears).pt == (4, 2)
    roundtrip(s)


def test_hammer_of_nazahn_attaches_itself_and_another_equipment(cards):
    s = game(cards, ["Hammer of Nazahn", "Bonesplitter", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    hammer = cast(s, "Hammer of Nazahn", C=4)
    drive(s, picks(bears.id))
    assert s.state.cards[hammer.id].attached_to == bears.id
    splitter = cast(s, "Bonesplitter", C=1)
    drive(s, picks(bears.id))
    assert s.state.cards[splitter.id].attached_to == bears.id
    assert ch(s, bears).pt == (6, 2) and "indestructible" in ch(s, bears).keywords
    roundtrip(s)


# -- populate (701.36) -------------------------------------------------------------------------------------------------
def test_populate_with_no_creature_token_creates_nothing(cards):
    s = game(cards, ["Rootborn Defenses", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    token(s, "p1", "Treasure", pt="", type_line="Token Artifact — Treasure")
    cast(s, "Rootborn Defenses", W=1, C=2)
    drive(s)
    assert [t.name for t in tokens(s)] == ["Treasure"]  # 701.36b (a Treasure isn't a creature token)
    assert "indestructible" in ch(s, bears).keywords
    roundtrip(s)


def test_populate_chooses_among_creature_tokens_and_copies_the_chosen_one(cards):
    s = game(cards, ["Rootborn Defenses"], ["Grizzly Bears"])
    token(s, "p1", "Soldier", "1/1")
    wolf = token(s, "p1", "Wolf", "2/2")
    token(s, "p2", "Ogre", "3/3")  # (an opponent's token is never a choice)
    cast(s, "Rootborn Defenses", W=1, C=2)
    asked = []

    def choose(d):
        if d.prompt.startswith("Populate"):
            asked.append(sorted(o.label for o in d.options))
            return [wolf.id]
        return None
    drive(s, choose)
    assert asked == [["Soldier", "Wolf"]]
    assert sorted(t.name for t in tokens(s, "p1")) == ["Soldier", "Wolf", "Wolf"]
    copy = next(t for t in tokens(s, "p1") if t.name == "Wolf" and t.id != wolf.id)
    assert ch(s, copy).pt == (2, 2) and "indestructible" in ch(s, copy).keywords  # (it was there for the second sentence)
    roundtrip(s)


def test_trostani_populates_a_copy_of_a_token_copy(cards):
    """707.3: a token copy of a token that is itself a copy copies what that token copies."""
    s = game(cards, ["Trostani, Selesnya's Voice", "Croaking Counterpart", "Grizzly Bears"])
    trostani = put(s, "Trostani, Selesnya's Voice")
    own_next_turn(s)  # (no longer summoning sick: its ability has {T} in its cost)
    bears = put(s, "Grizzly Bears")
    cast(s, "Croaking Counterpart", targets=[bears.id], G=1, U=1, C=1)
    drive(s)
    [frog] = tokens(s, "p1")
    life = s.state.players["p1"].life
    mana(s, G=1, W=1, C=1)
    act(s, "p1", type="activate_ability", card_id=trostani.id, ability=1)
    drive(s)
    copies = [t for t in tokens(s, "p1") if t.id != frog.id]
    assert len(copies) == 1
    got = ch(s, copies[0])
    assert got.name == "Grizzly Bears" and got.pt == (1, 1) and got.colors == frozenset({"G"}) and got.subtypes == {"Frog"}
    assert s.state.players["p1"].life == life + 1  # Trostani: the copy's toughness
    roundtrip(s)


def test_horncallers_chant_populates_the_rhino_it_just_made(cards):
    s = game(cards, ["Horncaller's Chant"])
    cast(s, "Horncaller's Chant", G=1, C=7)
    drive(s)
    rhinos = tokens(s, "p1")
    assert [t.name for t in rhinos] == ["Rhino", "Rhino"] and all(ch(s, t).pt == (4, 4) for t in rhinos)
    assert all("trample" in ch(s, t).keywords for t in rhinos)
    roundtrip(s)


# -- "for each …, create a token that's a copy of that …" --------------------------------------------------------------
def test_second_harvest_copies_every_token_you_control(cards):
    s = game(cards, ["Second Harvest"])
    token(s, "p1", "Soldier", "1/1")
    token(s, "p1", "Treasure", pt="", type_line="Token Artifact — Treasure")
    token(s, "p2", "Ogre", "3/3")
    cast(s, "Second Harvest", G=2, C=2)
    drive(s)
    assert sorted(t.name for t in tokens(s, "p1")) == ["Soldier", "Soldier", "Treasure", "Treasure"]
    assert [t.name for t in tokens(s, "p2")] == ["Ogre"]
    roundtrip(s)


def test_rhys_copies_each_creature_token(cards):
    s = game(cards, ["Rhys the Redeemed"])
    rhys = put(s, "Rhys the Redeemed")
    own_next_turn(s)
    token(s, "p1", "Elf Warrior", "1/1")
    token(s, "p1", "Treasure", pt="", type_line="Token Artifact — Treasure")
    mana(s, G=3, C=4)
    act(s, "p1", type="activate_ability", card_id=rhys.id, ability=1)
    drive(s)
    assert sorted(t.name for t in tokens(s, "p1")) == ["Elf Warrior", "Elf Warrior", "Treasure"]
    roundtrip(s)


def test_multiversal_incursion_copies_nontoken_creatures_as_nonlegendary(cards):
    s = game(cards, ["Multiversal Incursion", "Rhys the Redeemed", "Grizzly Bears"])
    put(s, "Rhys the Redeemed")
    put(s, "Grizzly Bears")
    token(s, "p1", "Soldier", "1/1")
    cast(s, "Multiversal Incursion", U=2, C=5)
    drive(s)
    made = [t for t in tokens(s, "p1") if t.name != "Soldier"]
    assert sorted(t.name for t in made) == ["Grizzly Bears", "Rhys the Redeemed"]
    assert all("Legendary" not in ch(s, t).supertypes for t in made)
    roundtrip(s)


def test_clone_legion_copies_the_target_players_creatures_for_you(cards):
    s = game(cards, ["Clone Legion"], ["Grizzly Bears", "Shivan Dragon"])
    put(s, "Grizzly Bears", pid="p2")
    put(s, "Shivan Dragon", pid="p2")
    cast(s, "Clone Legion", targets=["p2"], U=2, C=7)
    drive(s)
    assert sorted(t.name for t in tokens(s, "p1")) == ["Grizzly Bears", "Shivan Dragon"]
    roundtrip(s)


def test_parallel_evolution_each_controller_copies_their_own_tokens_and_kambal_copies_the_opponents(cards):
    s = game(cards, ["Parallel Evolution", "Kambal, Profiteering Mayor"])
    put(s, "Kambal, Profiteering Mayor")
    token(s, "p1", "Soldier", "1/1")
    token(s, "p2", "Ogre", "3/3")
    life = (s.state.players["p1"].life, s.state.players["p2"].life)
    cast(s, "Parallel Evolution", G=2, C=3)
    drive(s)
    assert sorted(t.name for t in tokens(s, "p2")) == ["Ogre", "Ogre"]
    mine = sorted((t.name, t.tapped) for t in tokens(s, "p1"))
    # Bob's new Ogre entered: Kambal makes a tapped copy of it for Alice; Alice's tokens entering drain Bob
    assert mine == [("Ogre", True), ("Soldier", False), ("Soldier", False)]
    assert s.state.players["p1"].life > life[0] and s.state.players["p2"].life < life[1]
    roundtrip(s)


# -- copies with exceptions (707.9) --------------------------------------------------------------------------------------
def test_croaking_counterpart_is_a_1_1_green_frog(cards):
    """707.9b/d, 205.1a: P/T, colors and creature types set; the copy keeps the rest of the copied values."""
    s = game(cards, ["Croaking Counterpart", "Shivan Dragon"])
    dragon = put(s, "Shivan Dragon")
    cast(s, "Croaking Counterpart", targets=[dragon.id], G=1, U=1, C=1)
    drive(s)
    [frog] = tokens(s, "p1")
    got = ch(s, frog)
    assert got.name == "Shivan Dragon" and got.pt == (1, 1) and got.colors == frozenset({"G"})
    assert got.subtypes == {"Frog"} and "flying" in got.keywords and got.is_creature
    roundtrip(s)


def test_a_frog_copy_of_a_changeling_isnt_every_creature_type(cards):
    """707.9d: changeling defines the creature types the exception sets, so it isn't copied (Croaking Counterpart can't
    target one — it's a Frog — but the same exception on another copy of it reads the same)."""
    from app.game.rules_state import CopyRecipe
    from app.rules import copying

    s = game(cards, ["Changeling Outcast"])
    outcast = find(s, "Changeling Outcast")
    ex = copying.parse_excepts("it's a 1/1 green Frog")
    got = copying.characteristics(CopyRecipe(printing=outcast.card_id, excepts=[ex]), s.cards)
    assert got.subtypes == {"Frog"} and "changeling" not in got.keywords and (got.power, got.toughness) == ("1", "1")
    assert any("can't block" in a.text for a in got.abilities)
    assert copying.parse_excepts("it's a 4/4 black Zombie").set_creature_types == ["Zombie"]
    assert copying.parse_excepts("it's a 1/1 green Elk Frog") is not None
    assert copying.parse_excepts("it's a 1/1 green Forest") is None  # (not a creature type: manual)


# -- a copy of an object that left the battlefield (608.2h, 111.12) ----------------------------------------------------
def test_miirym_copies_a_dragon_that_left_before_the_trigger_resolved(cards):
    s = game(cards, ["Miirym, Sentinel Wyrm", "Shivan Dragon"])
    put(s, "Miirym, Sentinel Wyrm")
    responsive(s)
    dragon = cast(s, "Shivan Dragon", R=2, C=4)
    trigger_waiting(s, dragon)
    assert not tokens(s)
    act(s, "p1", type="move", card_ids=[dragon.id], to={"player": "p1", "zone": "graveyard"})
    drive(s)
    [copy] = tokens(s, "p1")
    assert ch(s, copy).name == "Shivan Dragon" and ch(s, copy).pt == (5, 5) and "flying" in ch(s, copy).keywords
    roundtrip(s)


# -- Mechanized Production (104.2b) ------------------------------------------------------------------------------------
def thopters(s, n):
    return [token(s, "p1", "Thopter", "1/1", "Token Artifact Creature — Thopter") for _ in range(n)]


def test_mechanized_production_copies_and_wins_with_eight_of_a_name(cards):
    s = game(cards, ["Mechanized Production"])
    made = thopters(s, 7)
    aura = put(s, "Mechanized Production")
    act(s, "p1", type="attach", card_ids=[aura.id], to=made[0].id)
    own_next_turn(s)
    assert len([t for t in tokens(s, "p1") if t.name == "Thopter"]) == 8
    assert s.state.rules.winner == "p1"
    roundtrip(s)


def test_mechanized_production_short_of_eight_only_copies(cards):
    s = game(cards, ["Mechanized Production"])
    made = thopters(s, 5)
    aura = put(s, "Mechanized Production")
    act(s, "p1", type="attach", card_ids=[aura.id], to=made[0].id)
    own_next_turn(s)
    assert len([t for t in tokens(s, "p1") if t.name == "Thopter"]) == 6 and s.state.rules.winner is None
    roundtrip(s)


# -- putting a card from your hand onto the battlefield (305.4, 303.4f, 301.5b) -----------------------------------------
def hand_choice(pick):
    """Answer the hand choice with ``pick`` (a card id, or None for no card); anything else the plain way."""
    def choose(d):
        if "from your hand onto the battlefield" in d.prompt:
            return [pick] if pick else []
        return None
    return choose


def test_stoneforge_mystic_puts_an_equipment_onto_the_battlefield_unattached(cards):
    s = game(cards, ["Stoneforge Mystic", "Bonesplitter", "Grizzly Bears"])
    mystic = put(s, "Stoneforge Mystic")
    own_next_turn(s)
    splitter = put(s, "Bonesplitter", "hand")
    bears = put(s, "Grizzly Bears", "hand")  # (not an Equipment: never offered)
    mana(s, W=1, C=1)
    act(s, "p1", type="activate_ability", card_id=mystic.id, ability=1)
    asked = []

    def choose(d):
        if "from your hand" in d.prompt:
            asked.append({o.id for o in d.options})
            # the choice is private (400.2): the opponent sees only that a choice is being made
            other = s.view("p2")["rules"]["decision"]
            assert "options" not in other and "Bonesplitter" not in str(other)
            return [splitter.id]
        return None
    drive(s, choose)
    assert asked == [{splitter.id}]
    sp = s.state.cards[splitter.id]
    assert sp.zone == "p1:battlefield" and sp.attached_to is None and s.state.cards[bears.id].zone == "p1:hand"
    roundtrip(s)


def test_elvish_piper_may_put_nothing_and_a_creature_put_in_has_its_enters_trigger(cards):
    s = game(cards, ["Elvish Piper", "Elvish Visionary"])
    piper = put(s, "Elvish Piper")
    own_next_turn(s)
    visionary = put(s, "Elvish Visionary", "hand")
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=piper.id, ability=0)
    drive(s, hand_choice(None))
    assert s.state.cards[visionary.id].zone == "p1:hand"
    act(s, "p1", type="tap", card_ids=[piper.id], tapped=False)
    hand = len(s.state.zones["p1:hand"])
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=piper.id, ability=0)
    drive(s, hand_choice(visionary.id))
    assert s.state.cards[visionary.id].zone == "p1:battlefield"
    assert len(s.state.zones["p1:hand"]) == hand  # it left the hand, and its enters trigger drew a card (not cast)
    roundtrip(s)


def test_growth_spiral_land_isnt_a_land_play(cards):
    """305.4: a land put onto the battlefield by an effect isn't played; the player may still play a land."""
    s = game(cards, ["Growth Spiral", "Mountain", "Island"])
    mountain = put(s, "Mountain", "hand")
    cast(s, "Growth Spiral", G=1, U=1)
    drive(s, hand_choice(mountain.id))
    assert s.state.cards[mountain.id].zone == "p1:battlefield"
    island = put(s, "Island", "hand")
    act(s, "p1", type="play_land", card_id=island.id)
    assert s.state.cards[island.id].zone == "p1:battlefield"
    roundtrip(s)


def test_incandescent_soulstoke_puts_a_hasty_elemental_sacrificed_at_the_end_step(cards):
    s = game(cards, ["Incandescent Soulstoke", "Air Elemental"])
    stoke = put(s, "Incandescent Soulstoke")
    own_next_turn(s)
    air = put(s, "Air Elemental", "hand")
    mana(s, R=1, C=1)
    act(s, "p1", type="activate_ability", card_id=stoke.id, ability=1)
    drive(s, hand_choice(air.id))
    got = ch(s, air)
    assert s.state.cards[air.id].zone == "p1:battlefield" and "haste" in got.keywords and got.pt == (5, 5)
    roundtrip(s)
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.turn.number == 4)
    assert s.state.cards[air.id].zone == "p1:graveyard"
    roundtrip(s)


def test_put_from_hand_wordings():
    assert ok("{G}, {T}: You may put a creature card from your hand onto the battlefield.", "Elvish Piper")
    assert ok("When this creature enters, you may put a land card from your hand onto the battlefield tapped.")
    # Refused: an instant or sorcery could be chosen ("a card"), or unsupported "and/or" combinations.
    assert not ok("{T}: You may put a card from your hand onto the battlefield.")
    assert ok("When this creature enters, you may put an Aura card from your hand onto the battlefield attached to "
                  "this creature.")
    assert ok("Whenever this creature attacks, you may put a creature card from your hand onto the battlefield tapped "
              "and attacking.")  # (wave 15B: 508.4, its controller chooses what it attacks)
    assert not ok("Whenever this creature attacks, you may put a creature card and/or a land card "
                  "from your hand onto the battlefield.")  # (wave 44B: only Michelangelo's "deals combat damage to a player" wording is read, two optional puts)
    assert ok("Whenever this creature deals combat damage to a player, you may put a creature card and/or a land card "
              "from your hand onto the battlefield.")
