"""Wave 110G: single cards read from an exact wording (real Oracle text); each scenario checks replay and save/load.

* Portcullis: 610.3 exile until the artifact leaves; the count includes the entering creature.
* Acquisitions Expert: 700.8 party size sets how many cards the opponent reveals (701.20a).
* Golgari Brownscale: 603.6 / 400.7 the card put into its owner's hand from the graveyard (dredge, 702.52a) triggers from the hand.
* Invasion of the Giants: 603.12 'Then you may reveal a Giant card. When you do' is a reflexive trigger after the draw.
* Distended Mindbender: 701.9 / 701.20a one discard per size class from the revealed hand, chosen by the caster.
* Total War: 508.1 / 302.6 untapped non-Wall creatures that did not attack and were controlled since the turn began are destroyed.
* Gemini Engine: 508.4 / 111.1 an attacking token with the attacker's power and toughness, sacrificed at end of combat.
* Vizkopa Confessor: 119.4 the life paid sizes the reveal (701.20a); paying 0 reveals nothing.
* Serene Master: 701.12g exchanging two powers sets each to the other's previous value (613.4b), until end of combat.
"""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build
from tests.wave110b_kit import attack, cast, ch, check, mana, put, settle, through_combat, to_hand

EXTRA = [
    real('Serene Master', '{1}{W}', 2, 'Creature — Human Monk',
         "Whenever this creature blocks, exchange its power and the power of target creature it's blocking until end of combat.", ('0', '2'), 'W'),
    real('Portcullis', '{4}', 4, 'Artifact',
         "Whenever a creature enters, if there are two or more other creatures on the battlefield, exile that creature. Return that card to the battlefield under its owner's control when this artifact leaves the battlefield.", None, ''),
    real('Acquisitions Expert', '{1}{B}', 2, 'Creature — Human Rogue',
         'When this creature enters, target opponent reveals a number of cards from their hand equal to the number of creatures in your party. You choose one of those cards. That player discards that card. (Your party consists of up to one each of Cleric, Rogue, Warrior, and Wizard.)', ('1', '2'), 'B'),
    real('Golgari Brownscale', '{1}{G}{G}', 3, 'Creature — Lizard',
         'When this card is put into your hand from your graveyard, you gain 2 life.\nDredge 2 (If you would draw a card, you may mill two cards instead. If you do, return this card from your graveyard to your hand.)', ('2', '3'), 'G'),
    real('Invasion of the Giants', '{U}{R}', 2, 'Enchantment — Saga',
         '(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Scry 2.\nII — Draw a card. Then you may reveal a Giant card from your hand. When you do, this Saga deals 2 damage to target opponent or planeswalker.\nIII — The next Giant spell you cast this turn costs {2} less to cast.', None, 'RU'),
    real('Distended Mindbender', '{8}', 8, 'Creature — Eldrazi Insect',
         "Emerge {5}{B}{B} (You may cast this spell by sacrificing a creature and paying the emerge cost reduced by that creature's mana value.)\nWhen you cast this spell, target opponent reveals their hand. You choose from it a nonland card with mana value 3 or less and a card with mana value 4 or greater. That player discards those cards.", ('5', '5'), ''),
    real('Total War', '{3}{R}', 4, 'Enchantment',
         "Whenever a player attacks with one or more creatures, destroy all untapped non-Wall creatures that player controls that didn't attack, except for creatures the player hasn't controlled continuously since the beginning of the turn.", None, 'R'),
    real('Gemini Engine', '{6}', 6, 'Artifact Creature — Construct',
         "Whenever this creature attacks, create a colorless Construct artifact creature token named Twin that's attacking. Its power is equal to this creature's power and its toughness is equal to this creature's toughness. Sacrifice the token at end of combat.", ('3', '4'), ''),
    real('Vizkopa Confessor', '{3}{W}{B}', 5, 'Creature — Human Cleric',
         'Extort (Whenever you cast a spell, you may pay {W/B}. If you do, each opponent loses 1 life and you gain that much life.)\nWhen this creature enters, pay any amount of life. Target opponent reveals that many cards from their hand. You choose one of them and exile it.', ('1', '3'), 'BW'),
    real('Test Wall', '{1}', 1, 'Creature — Wall', '', ('0', '4'), ''),
    real('Hill Giant', '{3}{R}', 4, 'Creature — Giant', '', ('3', '3'), 'R'),
    real('Divination', '{2}{U}', 3, 'Sorcery', 'Draw two cards.', None, 'U'),
]
NAMES = [c["name"] for c in EXTRA if c["name"] not in ("Divination", "Hill Giant", "Test Wall")]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_serene_master_exchanges_powers(cards):
    s = build(cards, ["Grizzly Bears"], ["Serene Master"])
    master = put(s, "Serene Master", "p2")
    bears = put(s, "Grizzly Bears")
    attack(s, bears)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": master.id, "attacker_id": bears.id}])
    for _ in range(10):
        if s.state.rules.decision is not None:
            d = s.state.rules.decision
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    # Master 0/2 blocks Bears 2/2: powers swap, so Bears (power 0) dies to 2 damage and Master lives
    assert s.state.cards[bears.id].zone == "p1:graveyard" and s.state.cards[master.id].zone == "p2:battlefield"
    check(s)


def _portcullis(cards, others):
    s = build(cards, ["Portcullis", "Grizzly Bears", "Benalish Hero", "Llanowar Elves", "Test Shatter Charm"], [])
    port = put(s, "Portcullis")
    for name in ["Grizzly Bears", "Benalish Hero"][:others]:
        put(s, name)
    mana(s, "p1", G=1)
    return s, port


def _elves(s):
    return next(c for c in s.state.cards.values() if c.name == "Llanowar Elves")


@pytest.mark.parametrize("others,exiled", [(1, False), (2, True)])
def test_portcullis_exiles_the_third_creature(cards, others, exiled):
    """Two or more other creatures must already be on the battlefield."""
    s, port = _portcullis(cards, others)
    cast(s, "Llanowar Elves")
    settle(s)
    assert _elves(s).zone.endswith("exile") == exiled
    check(s)


def test_portcullis_leaving_returns_the_card(cards):
    s, port = _portcullis(cards, 2)
    cast(s, "Llanowar Elves")
    settle(s)
    assert _elves(s).zone.endswith("exile")
    mana(s, "p1", R=1)
    cast(s, "Test Shatter Charm", [port.id])
    assert _elves(s).zone == "p1:battlefield"
    check(s)


def test_acquisitions_expert_reveals_party_size_cards(cards):
    seen = []
    s = build(cards, ["Acquisitions Expert", "Soul Warden"], ["Grizzly Bears", "Llanowar Elves", "Goblin"])
    put(s, "Soul Warden")
    for name in ("Grizzly Bears", "Llanowar Elves", "Goblin"):
        to_hand(s, name, "p2")
    mana(s, "p1", B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Acquisitions Expert").id, targets=[])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            seen.append((d.player, d.kind, len(d.options), d.min_choices))
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert ("p2", "choose_cards", 3, 2) in seen and seen[-1] == ("p1", "choose_cards", 2, 1), seen  # Cleric + Rogue: reveals two
    assert len(s.state.zones["p2:hand"]) == 2
    check(s)


@pytest.mark.parametrize("dredge,life", [(True, 42), (False, 40)])
def test_golgari_brownscale_gains_life_when_dredged_back(cards, dredge, life):
    s = build(cards, ["Golgari Brownscale", "Divination"], [])
    scale = to_hand(s, "Golgari Brownscale")
    act(s, "p1", type="move", card_ids=[scale.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, "p1", U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Divination").id, targets=[])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            pick = ("decline" if "decline" in ids and not dredge else next(i for i in ids if i != "decline"))
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert (s.state.cards[scale.id].zone == "p1:hand") == dredge
    assert s.state.players["p1"].life == life
    check(s)


@pytest.mark.parametrize("giant,life", [(True, 38), (False, 40)])
def test_invasion_of_the_giants_chapter_two(cards, giant, life):
    s = build(cards, ["Invasion of the Giants", "Hill Giant"] if giant else ["Invasion of the Giants"], [])
    mana(s, "p1", U=1, R=1)
    saga = to_hand(s, "Invasion of the Giants")
    act(s, "p1", type="cast_spell", card_id=saga.id, targets=[])
    if giant:
        to_hand(s, "Hill Giant")
    for _ in range(300):
        d = s.state.rules.decision
        if s.state.cards[saga.id].counters.get("lore") == 2 and d is None and not s.state.zones.get("stack"):
            break
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((i for i in ids if i in ("yes", "o0", "p2")), ids[0])])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p2"].life == life, s.state.players["p2"].life
    check(s)


def test_distended_mindbender_discards_one_cheap_nonland_and_one_expensive(cards):
    s = build(cards, ["Distended Mindbender"], ["Grizzly Bears", "Llanowar Elves", "Forest", "Hill Giant"])
    for name in ("Grizzly Bears", "Llanowar Elves", "Forest", "Hill Giant"):
        to_hand(s, name, "p2")
    mana(s, "p1", C=8)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Distended Mindbender").id, targets=["p2"])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    # first nonland <=3 option and first >=4 option are discarded: Forest (land) and one of the cheap cards stay
    hand = [s.state.cards[c].name for c in s.state.zones["p2:hand"]]
    assert "Hill Giant" not in hand and "Forest" in hand and len(hand) == 2, hand
    check(s)


def test_total_war_destroys_idle_old_non_walls(cards):
    s = build(cards, ["Grizzly Bears", "Llanowar Elves", "Test Wall", "Hill Giant", "Benalish Hero"], ["Total War", "Goblin"])
    put(s, "Total War", "p2")
    bob = put(s, "Goblin", "p2")
    bears, elves, wall, giant = (put(s, n) for n in ("Grizzly Bears", "Llanowar Elves", "Test Wall", "Hill Giant"))
    hero = put(s, "Benalish Hero")
    act(s, "p1", type="tap", card_ids=[hero.id])
    for c in (elves, wall, hero):
        s.state.rules.controlled_since[c.id].turn = 0
        s.state.rules.controlled_since[c.id].observed_from_turn = 0  # controlled since before this turn
    attack(s, bears)
    act(s, "p2", type="declare_blockers", blocks=[])
    z = {c.name: c.zone for c in s.state.cards.values()}
    assert z["Llanowar Elves"] == "p1:graveyard"  # idle, untapped, old
    assert z["Test Wall"] == "p1:battlefield" and z["Hill Giant"] == "p1:battlefield"  # Wall; new this turn
    assert z["Benalish Hero"] == "p1:battlefield" and z["Grizzly Bears"] == "p1:battlefield"  # tapped; attacker
    assert s.state.cards[bob.id].zone == "p2:battlefield"
    check(s)


def test_gemini_engine_twin_attacks_and_is_sacrificed(cards):
    s = build(cards, ["Gemini Engine"], ["Goblin"])
    put(s, "Goblin", "p2")
    gem = put(s, "Gemini Engine")
    attack(s, gem)
    twin = next(c for c in s.state.cards.values() if c.name == "Twin")
    assert (twin.zone, ch(s, twin).pt) == ("p1:battlefield", (3, 4)), twin
    act(s, "p2", type="declare_blockers", blocks=[])
    through_combat(s)
    assert twin.id not in s.state.zones["p1:battlefield"] and s.state.players["p2"].life == 34
    check(s)


@pytest.mark.parametrize("pay,exiled,life", [(2, 1, 38), (0, 0, 40)])
def test_vizkopa_confessor_life_sizes_the_reveal(cards, pay, exiled, life):
    s = build(cards, ["Vizkopa Confessor"], ["Grizzly Bears", "Llanowar Elves", "Goblin"])
    for name in ("Grizzly Bears", "Llanowar Elves", "Goblin"):
        to_hand(s, name, "p2")
    mana(s, "p1", W=1, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Vizkopa Confessor").id, targets=[])
    seen = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            seen.append((d.player, d.kind, [o.label for o in d.options], d.min_choices, d.max_choices))
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids[: d.min_choices] if d.kind == "choose_cards" else ids[:1] if len(ids) < 3 else ids[pay:pay + 1])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert len(s.state.zones["p2:hand"]) == 3 - exiled and len(s.state.zones["p2:exile"]) == exiled
    assert s.state.players["p1"].life == life
    check(s)
