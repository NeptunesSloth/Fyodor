"""Wave 11A: transforming double-faced cards (CR 2026-09-25).

* "Transform this creature / ~ / this artifact …" (701.27a): the permanent turns over and stays the same object (712.18), with
  its counters and damage; it has only the characteristics of the face that's up (712.8d-e: its mana value is the front face's);
  off the battlefield a double-faced card shows its front face (712.8a).
* 701.27f: an activated or triggered ability that tries to transform the permanent does so only if it hasn't transformed since
  the ability was put onto the stack.
* "Exile it, then return it to the battlefield transformed" and "When this creature dies, return it to the battlefield
  transformed" (712.14a): the card enters with its back face up as a new object (400.7); Saga chapter III.
Refused (kept unsupported): "transform it" / "transform target …", a delayed "transform" (701.27f from creation), "transforms into"
triggers (701.27e), disturb / craft, casting a card transformed, modal and meld cards.

Every scenario checks the replay and a save / load round trip.
"""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, replay_matches, rules, run_until

REAL = [
    card('Kessig Prowler // Sinuous Predator', set_code='tst', number='T1', layout='transform', mana_cost=None, cmc=1.0, type_line='Creature — Werewolf Horror // Creature — Eldrazi Werewolf', colors=['G'], color_identity=['G'], image_uris=None,
         keywords=['Transform'], card_faces=[{'name': 'Kessig Prowler', 'mana_cost': '{G}', 'type_line': 'Creature — Werewolf Horror', 'oracle_text': '{4}{G}: Transform this creature.', 'power': '2', 'toughness': '1', 'colors': ['G']}, {'name': 'Sinuous Predator', 'mana_cost': '', 'type_line': 'Creature — Eldrazi Werewolf', 'oracle_text': "This creature can't be blocked by more than one creature.", 'power': '4', 'toughness': '4', 'colors': []}]),
    card('Thaumatic Compass // Spires of Orazca', set_code='tst', number='T2', layout='transform', mana_cost=None, cmc=2.0, type_line='Artifact // Land', colors=[], color_identity=[], image_uris=None,
         keywords=['Transform'], card_faces=[{'name': 'Thaumatic Compass', 'mana_cost': '{2}', 'type_line': 'Artifact', 'oracle_text': '{3}, {T}: Search your library for a basic land card, reveal it, put it into your hand, then shuffle.\nAt the beginning of your end step, if you control seven or more lands, transform this artifact.', 'colors': []}, {'name': 'Spires of Orazca', 'mana_cost': '', 'type_line': 'Land', 'oracle_text': '(Transforms from Thaumatic Compass.)\n{T}: Add {C}.\n{T}: Untap target attacking creature an opponent controls and remove it from combat.', 'colors': []}]),
    card('Harvest Hand // Scrounged Scythe', set_code='tst', number='T3', layout='transform', mana_cost=None, cmc=3.0, type_line='Artifact Creature — Scarecrow // Artifact — Equipment', colors=[], color_identity=[], image_uris=None,
         keywords=['Transform', 'Equip'], card_faces=[{'name': 'Harvest Hand', 'mana_cost': '{3}', 'type_line': 'Artifact Creature — Scarecrow', 'oracle_text': 'When this creature dies, return it to the battlefield transformed under your control.', 'power': '2', 'toughness': '2', 'colors': []}, {'name': 'Scrounged Scythe', 'mana_cost': '', 'type_line': 'Artifact — Equipment', 'oracle_text': "Equipped creature gets +1/+1.\nAs long as equipped creature is a Human, it has menace. (It can't be blocked except by two or more creatures.)\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)", 'colors': []}]),
    card("Jill, Shiva's Dominant // Shiva, Warden of Ice", set_code='tst', number='T4', layout='transform', mana_cost=None, cmc=3.0, type_line='Legendary Creature — Human Noble Warrior // Legendary Enchantment Creature — Saga Elemental', colors=['U'], color_identity=['U'], image_uris=None,
         keywords=['Transform'], card_faces=[{'name': "Jill, Shiva's Dominant", 'mana_cost': '{2}{U}', 'type_line': 'Legendary Creature — Human Noble Warrior', 'oracle_text': "When Jill enters, return up to one other target nonland permanent to its owner's hand.\n{3}{U}{U}, {T}: Exile Jill, then return it to the battlefield transformed under its owner's control. Activate only as a sorcery.", 'power': '2', 'toughness': '2', 'colors': ['U']}, {'name': 'Shiva, Warden of Ice', 'mana_cost': '', 'type_line': 'Legendary Enchantment Creature — Saga Elemental', 'oracle_text': "(As this Saga enters and after your draw step, add a lore counter.)\nI, II — Mesmerize — Target creature can't be blocked this turn.\nIII — Cold Snap — Tap all lands your opponents control. Exile Shiva, then return it to the battlefield (front face up).", 'power': '4', 'toughness': '5', 'colors': ['U']}]),
    card('Okiba Reckoner Raid // Nezumi Road Captain', set_code='tst', number='T5', layout='transform', mana_cost=None, cmc=1.0, type_line='Enchantment — Saga // Enchantment Creature — Rat Rogue', colors=['B'], color_identity=['B'], image_uris=None,
         keywords=['Transform', 'Menace'], card_faces=[{'name': 'Okiba Reckoner Raid', 'mana_cost': '{B}', 'type_line': 'Enchantment — Saga', 'oracle_text': '(As this Saga enters and after your draw step, add a lore counter.)\nI, II — Each opponent loses 1 life and you gain 1 life.\nIII — Exile this Saga, then return it to the battlefield transformed under your control.', 'colors': ['B']}, {'name': 'Nezumi Road Captain', 'mana_cost': '', 'type_line': 'Enchantment Creature — Rat Rogue', 'oracle_text': "Menace\nVehicles you control have menace. (They can't be blocked except by two or more creatures.)", 'power': '2', 'toughness': '2', 'colors': ['B']}]),
    card('Loyal Cathar // Unhallowed Cathar', set_code='tst', number='T6', layout='transform', mana_cost=None, cmc=2.0, type_line='Creature — Human Soldier // Creature — Zombie Soldier', colors=['B', 'W'], color_identity=['B', 'W'], image_uris=None,
         keywords=['Vigilance', 'Transform'], card_faces=[{'name': 'Loyal Cathar', 'mana_cost': '{W}{W}', 'type_line': 'Creature — Human Soldier', 'oracle_text': 'Vigilance\nWhen this creature dies, return it to the battlefield transformed under your control at the beginning of the next end step.', 'power': '2', 'toughness': '2', 'colors': ['W']}, {'name': 'Unhallowed Cathar', 'mana_cost': '', 'type_line': 'Creature — Zombie Soldier', 'oracle_text': "This creature can't block.", 'power': '2', 'toughness': '1', 'colors': ['B']}]),
    card("Conqueror's Galleon // Conqueror's Foothold", set_code='tst', number='T7', layout='transform', mana_cost=None, cmc=4.0, type_line='Artifact — Vehicle // Land', colors=[], color_identity=[], image_uris=None,
         keywords=['Transform', 'Crew'], card_faces=[{'name': "Conqueror's Galleon", 'mana_cost': '{4}', 'type_line': 'Artifact — Vehicle', 'oracle_text': 'When this Vehicle attacks, exile it at end of combat, then return it to the battlefield transformed under your control.\nCrew 4 (Tap any number of creatures you control with total power 4 or more: This Vehicle becomes an artifact creature until end of turn.)', 'power': '2', 'toughness': '10', 'colors': []}, {'name': "Conqueror's Foothold", 'mana_cost': '', 'type_line': 'Land', 'oracle_text': "(Transforms from Conqueror's Galleon.)\n{T}: Add {C}.\n{2}, {T}: Draw a card, then discard a card.\n{4}, {T}: Draw a card.\n{6}, {T}: Return target card from your graveyard to your hand.", 'colors': []}]),
    card('Dowsing Dagger // Lost Vale', set_code='tst', number='T8', layout='transform', mana_cost=None, cmc=2.0, type_line='Artifact — Equipment // Land', colors=[], color_identity=[], image_uris=None,
         keywords=['Transform', 'Equip'], card_faces=[{'name': 'Dowsing Dagger', 'mana_cost': '{2}', 'type_line': 'Artifact — Equipment', 'oracle_text': 'When this Equipment enters, target opponent creates two 0/2 green Plant creature tokens with defender.\nEquipped creature gets +2/+1.\nWhenever equipped creature deals combat damage to a player, you may transform this Equipment.\nEquip {2}', 'colors': []}, {'name': 'Lost Vale', 'mana_cost': '', 'type_line': 'Land', 'oracle_text': '(Transforms from Dowsing Dagger.)\n{T}: Add three mana of any one color.', 'colors': []}]),
]
NAMES = [c["name"] for c in REAL]
PROWLER, COMPASS, HAND, JILL, SAGA, CATHAR, GALLEON, DAGGER = NAMES


COUNTERPART = card("Cackling Counterpart", set_code="tst", number="T9", mana_cost="{1}{U}{U}", cmc=3.0, type_line="Instant", colors=["U"],
                   color_identity=["U"], oracle_text="Create a token that's a copy of target creature you control.\nFlashback {5}{U}{U} "
                   "(You may cast this card from your graveyard for its flashback cost. Then exile it.)", keywords=["Flashback"])


@pytest.fixture()
def cards(settings, card_db):
    build_database(fixture_cards() + REAL + [COUNTERPART], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(card_db, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def find(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def put(s, name, where, pid="p1"):
    c = find(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": where})
    return s.state.cards[c.id]


def table(cards, mine=(), hand=()):
    a = deck(cards, "Krenko, Mob Boss", [(1, n) for n in (*mine, *hand)] + [(10, "Forest")])
    b = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b)], shuffle=False)), cards=cards)
    for n in mine:
        c = put(s, n, "battlefield")
        rules(s).controlled_since[c.id].turn = 0  # (there since before the turn: no summoning sickness)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    act(s, "p1", type="set_prefs", response="on")  # (Alice stops at each object on the stack)
    return s


def settle(s, *answers):
    """Resolve the stack: each decision is answered with the next answer (an option id or the start of its label)."""
    queue = list(answers)
    for _ in range(80):
        d = rules(s).decision
        if d is not None and d.kind == "order":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
        elif d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        elif d is not None:
            assert queue, (d.prompt, [o.label for o in d.options])
            want = queue.pop(0)
            ids = [next(o.id for o in d.options if o.id == want or o.label.lower().startswith(want)) ]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, rules(s).priority, type="pass_priority")
        else:
            break
    assert not queue, queue


def ch(s, c, cards):
    return Plan(s.state, "p1", cards, None).ch(s.state.cards[c.id])


def check(s):
    replay_matches(s)  # (the history rebuilds the same table)
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))  # (a save and a load)
    assert GameState.model_validate(s.state.model_dump(mode="json")).model_dump(mode="json") == s.state.model_dump(mode="json")


def kill(s, c):
    """Lethal damage, then the state-based actions (704.5g): the engine moves it, so it dies (not moved by hand)."""
    act(s, "p1", type="set_damage", card_ids=[c.id], delta=99)
    act(s, rules(s).priority or "p1", type="pass_priority")


def ability(s, c, cards, word):
    """The index of the activated ability of ``c`` whose text has ``word``."""
    return next(a.index for a in ch(s, c, cards).abilities if a.kind in ("activated", "keywords") and word in a.text)


def level(name):
    c = next(c for c in REAL if c["name"] == name)
    return coverage.of_card_data({**c, "faces": c["card_faces"]}).level


def test_the_wordings_are_read_and_the_rest_refused():
    for text in ("Transform this creature.", "Transform ~.", "Transform this artifact."):
        assert scripts.parse_effects(text)[0] == [{"do": "transform", "who": "self"}]
    done = scripts.parse_effects("Return it to the battlefield tapped and transformed under its owner's control.")
    assert done is None or "transform" not in str(done)  # (no antecedent for "it" outside a trigger)
    assert scripts.parse_effects("Transform target creature.")[0] == [{"do": "transform", "who": "target"}]  # (wave 48A: a chosen permanent turns over too, 701.27a; one that can't transform does nothing, 701.27c)
    for text in ("Transform it.", "Transform all Humans you control.",
                 "Transform up to one other target double-faced artifact you control."):
        assert scripts.parse_effects(text) is None, text
    for name in NAMES:
        assert level(name) == "FULL", name


def test_activated_transform_keeps_the_object_and_the_second_activation_is_ignored(cards):
    """701.27a, 712.18, 712.8d-e, 701.27f: two activations on the stack, the first to resolve transforms it; the other does nothing."""
    s = table(cards, mine=(PROWLER,))
    k = find(s, PROWLER)
    act(s, "p1", type="counter", card_ids=[k.id], kind="+1/+1", delta=1)
    oid = rules(s).object_id(k.id)
    assert ch(s, k, cards).pt == (3, 2) and ch(s, k, cards).mana_value == 1
    mana(s, G=2, C=8)
    i = ability(s, k, cards, "Transform")
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=k.id, ability=i)
    act(s, "p1", type="activate_ability", card_id=k.id, ability=i)
    act(s, "p1", type="set_prefs", hold_priority=False)
    assert len(s.state.zones["stack"]) == 2
    settle(s)
    now = s.state.cards[k.id]
    assert now.face == 1 and rules(s).object_id(k.id) == oid and now.counters.get("+1/+1") == 1  # same object, counters kept
    back = ch(s, k, cards)
    assert back.name == "Sinuous Predator" and back.mana_value == 1 and back.mana_cost == ""  # 712.8e
    assert rules(s).transformed[k.id] > 0
    check(s)
    act(s, "p1", type="move", card_ids=[k.id], to={"player": "p1", "zone": "graveyard"})
    assert s.state.cards[k.id].face == 0 and ch(s, k, cards).name == "Kessig Prowler"  # 712.8a: front face off the battlefield
    assert k.id not in rules(s).transformed
    check(s)


def test_triggered_transform_with_an_intervening_if(cards):
    """Thaumatic Compass: at the beginning of your end step, if you control seven or more lands, transform this artifact."""
    s = table(cards, mine=(COMPASS,))
    lands = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"]
    for land in lands[:6]:
        put(s, "Forest", "battlefield") if False else act(s, "p1", type="move", card_ids=[land.id], to={"player": "p1", "zone": "battlefield"})
    compass = find(s, COMPASS)
    run_until(s, lambda s: s.state.turn.phase == "end")
    settle(s)
    assert s.state.cards[compass.id].face == 0  # six lands: no trigger (603.4)
    act(s, "p1", type="move", card_ids=[lands[6].id], to={"player": "p1", "zone": "battlefield"})
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "end")
    settle(s)
    assert s.state.cards[compass.id].face == 1
    back = ch(s, compass, cards)
    assert back.name == "Spires of Orazca" and back.types == frozenset({"Land"}) and back.mana_value == 2
    check(s)


def test_dies_return_transformed_is_a_new_object_with_its_back_face(cards):
    """Harvest Hand: when this creature dies, return it to the battlefield transformed under your control (712.14a, 400.7)."""
    s = table(cards, mine=(HAND,))
    hand = find(s, HAND)
    old = rules(s).object_id(hand.id)
    act(s, "p1", type="counter", card_ids=[hand.id], kind="+1/+1", delta=2)
    kill(s, hand)
    settle(s)
    now = s.state.cards[hand.id]
    assert now.zone == "p1:battlefield" and now.face == 1 and rules(s).object_id(hand.id) != old and not now.counters
    back = ch(s, hand, cards)
    assert back.name == "Scrounged Scythe" and "Equipment" in back.subtypes and back.mana_value == 3
    check(s)


def test_exile_then_return_transformed_from_an_activated_ability(cards):
    """Jill, Shiva's Dominant: {3}{U}{U}, {T}: Exile Jill, then return it to the battlefield transformed under its owner's control."""
    s = table(cards, mine=(JILL,))
    jill = find(s, JILL)
    old = rules(s).object_id(jill.id)
    act(s, "p1", type="counter", card_ids=[jill.id], kind="+1/+1", delta=1)
    mana(s, U=2, C=3)
    act(s, "p1", type="activate_ability", card_id=jill.id, ability=ability(s, jill, cards, "Exile"))
    settle(s, "jill")  # (Shiva is a Saga creature: its chapter I targets as it enters, 714.3a)
    now = s.state.cards[jill.id]
    assert now.zone == "p1:battlefield" and now.face == 1 and rules(s).object_id(jill.id) != old and set(now.counters) == {"lore"}
    assert not now.tapped and ch(s, jill, cards).name == "Shiva, Warden of Ice"
    check(s)


def test_saga_chapter_three_exiles_and_returns_it_transformed(cards):
    """Okiba Reckoner Raid: III — Exile this Saga, then return it to the battlefield transformed under your control."""
    s = table(cards, hand=(SAGA,))
    saga = put(s, SAGA, "hand")
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=saga.id)
    settle(s)
    assert s.state.cards[saga.id].zone == "p1:battlefield" and s.state.cards[saga.id].counters.get("lore") == 1
    run_until(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == "main1")
    settle(s)
    now = s.state.cards[saga.id]
    assert now.zone == "p1:battlefield" and now.face == 1 and not now.counters.get("lore")  # a creature now, not sacrificed
    assert ch(s, saga, cards).name == "Nezumi Road Captain" and ch(s, saga, cards).is_creature
    assert s.state.players["p2"].life == 38 and s.state.players["p1"].life == 42  # I and II: 1 life each, twice
    check(s)


def test_delayed_return_transformed_at_the_next_end_step(cards):
    """Loyal Cathar: when this creature dies, return it to the battlefield transformed under your control at the beginning of
    the next end step."""
    s = table(cards, mine=(CATHAR,))
    cathar = find(s, CATHAR)
    kill(s, cathar)
    settle(s)
    assert s.state.cards[cathar.id].zone == "p1:graveyard"
    run_until(s, lambda s: s.state.turn.phase == "end")
    settle(s)
    now = s.state.cards[cathar.id]
    assert now.zone == "p1:battlefield" and now.face == 1 and ch(s, cathar, cards).name == "Unhallowed Cathar"
    check(s)


def test_transforming_an_equipment_into_a_land_unattaches_it(cards):
    """Dowsing Dagger: whenever equipped creature deals combat damage to a player, you may transform this Equipment: the land
    isn't an Equipment, so it becomes unattached (704.5n)."""
    s = table(cards, mine=(DAGGER, "Grizzly Bears"))
    dagger, bear = find(s, DAGGER), find(s, "Grizzly Bears")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=dagger.id, ability=ability(s, dagger, cards, "Equip {"), targets=[bear.id])
    settle(s)
    assert s.state.cards[dagger.id].attached_to == bear.id
    run_until(s, lambda s: rules(s).decision is not None and rules(s).decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    for _ in range(40):  # (no blockers; the "you may" is accepted)
        d = rules(s).decision
        if s.state.cards[dagger.id].face == 1:
            break
        if d is None:
            act(s, rules(s).priority, type="pass_priority")
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id == "yes")])
    assert s.state.cards[dagger.id].attached_to is None and ch(s, dagger, cards).name == "Lost Vale"
    check(s)


def test_vehicle_exiles_at_end_of_combat_and_returns_transformed(cards):
    """Conqueror's Galleon: when this Vehicle attacks, exile it at end of combat, then return it to the battlefield transformed."""
    s = table(cards, mine=(GALLEON,))
    galleon = find(s, GALLEON)
    old = rules(s).object_id(galleon.id)
    act(s, "p1", type="create_token", player="p1", token={"name": "Brute", "type_line": "Token Creature — Test", "power": "4",
                                                          "toughness": "4", "text": ""})
    brute = next(c for c in s.state.cards.values() if c.name == "Brute")
    rules(s).controlled_since[brute.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=galleon.id, ability=ability(s, galleon, cards, "Crew"))
    settle(s, "brute")
    assert ch(s, galleon, cards).is_creature
    run_until(s, lambda s: rules(s).decision is not None and rules(s).decision.kind == "declare_attackers")
    print("DBG0", s.state.turn.number, s.state.turn.phase, ch(s, galleon, cards).is_creature, s.state.cards[galleon.id].tapped)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": galleon.id, "target": "p2"}])
    print("DBG1", s.state.cards[galleon.id].attacking, s.state.zones.get("stack"), rules(s).decision)
    for _ in range(60):
        d = rules(s).decision
        print("DBG2", s.state.turn.number, s.state.turn.phase, s.state.cards[galleon.id].zone, s.state.cards[galleon.id].face, len(rules(s).delayed))
        if s.state.cards[galleon.id].face == 1 and s.state.cards[galleon.id].zone == "p1:battlefield":
            break
        if d is None:
            act(s, rules(s).priority, type="pass_priority")
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            print("DBG", d.kind, d.prompt, s.state.turn.number, s.state.turn.phase, s.state.cards[galleon.id].attacking)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    now = s.state.cards[galleon.id]
    assert now.zone == "p1:battlefield" and now.face == 1 and rules(s).object_id(galleon.id) != old
    assert ch(s, galleon, cards).name == "Conqueror's Foothold"
    check(s)


# -- review (casting) -- 202.3b / 712.8e: the card's back face has its front face's mana value; a copy of that back face has 0
def test_a_token_copy_of_a_back_face_has_mana_value_zero(cards):
    s = table(cards, mine=(PROWLER,), hand=("Cackling Counterpart",))
    k = find(s, PROWLER)
    mana(s, G=1, C=4)
    act(s, "p1", type="activate_ability", card_id=k.id, ability=ability(s, k, cards, "Transform"))
    settle(s)
    assert ch(s, k, cards).name == "Sinuous Predator" and ch(s, k, cards).mana_value == 1  # 712.8e
    counterpart = put(s, "Cackling Counterpart", "hand")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=counterpart.id, targets=[k.id])
    settle(s)
    tok = next(c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield")
    assert tok.face == 1 and ch(s, tok, cards).name == "Sinuous Predator"  # 707.8a: a double-faced token with its back face up
    assert ch(s, tok, cards).mana_value == 0 and ch(s, k, cards).mana_value == 1  # 202.3b
    check(s)
