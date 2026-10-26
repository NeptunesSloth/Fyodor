"""Wave 110G: single cards read from an exact wording (real Oracle text); each scenario checks replay and save/load.

* Portcullis: 610.3 exile until the artifact leaves; the count includes the entering creature.
* Acquisitions Expert: 700.8 party size sets how many cards the opponent reveals (701.20a).
* Golgari Brownscale: 603.6 / 400.7 the card put into its owner's hand from the graveyard (dredge, 702.52a) triggers from the hand.
* Invasion of the Giants: 603.12 'Then you may reveal a Giant card. When you do' is a reflexive trigger after the draw.
* Distended Mindbender: 701.9 / 701.20a one discard per size class from the revealed hand, chosen by the caster.
* Fugitive of the Judoon: 702.21a a token created with ward {2}; 118.3 the Human and the artifact are exiled together, then a Doctor is searched out.
* Foul Emissary: 702.119a / 701.21a the Eldrazi Horror comes only when it was sacrificed as the emerge cost, not by an effect.
* Blade of the Swarm: 702.185a the second mode puts an exiled card that has warp (any player's) on the bottom of its owner's library; a card without warp is no target.
* Thought Prison: 607.2a / 105.2 / 202.3 imprint; a spell sharing a color or mana value with the exiled card hurts its caster for 2 (a spell with neither does not).
* Total War: 508.1 / 302.6 untapped non-Wall creatures that did not attack and were controlled since the turn began are destroyed.
* Gemini Engine: 508.4 / 111.1 an attacking token with the attacker's power and toughness, sacrificed at end of combat.
* Vizkopa Confessor: 119.4 the life paid sizes the reveal (701.20a); paying 0 reveals nothing.
* Wall of Caltrops: 509.1g / 509.3b banding only when the attacker is blocked by another Wall and by nothing but Walls.
* Henry Wu: 702.110b / 608.2h the Treasure needs the exploited non-Human creature to have had power 3 or greater; Humans give no card.
* Wormfang Crab: 607.2a link; an opponent picks which of the controller's other permanents is exiled; it returns when the Crab leaves.
* Wormfang Drake: 607.2a linked exile as the 'unless' payment; the exiled creature returns when the Drake leaves.
* Carry Away: 701.3d the enchanted Equipment is unattached when the Aura enters; 613.1b / 303.4e the Aura's controller controls it.
* Mindstorm Crown: 500.1 / 503.1a the hand as the turn began (before the upkeep) picks between drawing and the 1 damage.
* Archaic's Agony: 120.10 / 702.34 converge sizes the damage; the excess over lethal sizes the exile (top of library) and those cards are playable.
* Kill-Suit Cultist: 614.1a / 615.8 the next damage to the target this turn is replaced by destroying it; only the next time.
* Beamsplitter Mage: 707.10d / 115.9c one copy for the one other creature its controller chooses, none when there is none.
* Biblioplex Tomekeeper: 722.3a / 722.3b the target creature becomes prepared or unprepared (modes, up to one).
* The Fantastic Four: 700.2 / 603.2 enters and cast triggers; a spell with power, toughness or mana value 4; a mode not chosen yet this turn.
* Casey & Raph: 700.2 / 601.2c one or both modes at different players; the targeted player may play the exiled card free until their next end step.
* Serene Master: 701.12g exchanging two powers sets each to the other's previous value (613.4b), until end of combat.
"""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_review34_head import EXTRA as REVIEW34
from tests.test_rules_review34_head import SIEGE, drive
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100f_control import PREPARED
from tests.wave9c_kit import build, card_named
from tests.wave110b_kit import attack, cast, ch, check, mana, put, settle, through_combat, to_hand

PYRULEA = "Invasion of Pyrulea // Gargantuan Slabhorn"
_FACES = [
    {"object": "card_face", "name": "Invasion of Pyrulea", "mana_cost": "{G}{U}", "type_line": "Battle \u2014 Siege", "defense": "4",
     "oracle_text": "(As a Siege enters, choose an opponent to protect it. You and others can attack it. When it's defeated, exile it, then cast it transformed.)\nWhen this Siege enters, scry 3, then reveal the top card of your library. If it's a land or double-faced card, draw a card."},
    {"object": "card_face", "name": "Gargantuan Slabhorn", "mana_cost": "", "type_line": "Creature \u2014 Beast", "power": "4", "toughness": "4",
     "oracle_text": "Trample, ward {2}\nOther transformed permanents you control have trample and ward {2}."},
]
EXTRA = [
    card(PYRULEA, set_code="tst", number="110G-P", layout="transform", mana_cost="{G}{U} // ", cmc=2.0, type_line="Battle \u2014 Siege // Creature \u2014 Beast",
         colors=["G", "U"], color_identity=["G", "U"], card_faces=_FACES,
         oracle_text="\n//\n".join(f["oracle_text"] for f in _FACES), keywords=["Transform", "Trample", "Ward", "Scry"]),
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
    real('Fugitive of the Judoon', '{4}{G}', 5, 'Enchantment \u2014 Saga',
         '(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI \u2014 Create a 1/1 white Human creature token with ward {2} and a 4/4 white Alien Rhino creature token.\nII \u2014 Investigate.\nIII \u2014 You may exile a Human you control and an artifact you control. If you do, search your library for a Doctor card, put it onto the battlefield, then shuffle.', None, 'G'),
    real('Test Doctor', '{G}', 1, 'Creature \u2014 Time Lord Doctor', '', ('1', '1'), 'G'),
    real('Foul Emissary', '{2}{G}', 3, 'Creature \u2014 Human Horror',
         'When this creature enters, look at the top four cards of your library. You may reveal a creature card from among them and put it into your hand. Put the rest on the bottom of your library in any order.\nWhen you sacrifice this creature while casting a spell with emerge, create a 3/2 colorless Eldrazi Horror creature token.', ('1', '1'), 'G'),
    real('Blade of the Swarm', '{3}{B}', 4, 'Creature \u2014 Insect Assassin',
         "When this creature enters, choose one \u2014\n\u2022 Put two +1/+1 counters on this creature.\n\u2022 Put target exiled card with warp on the bottom of its owner's library.", ('3', '1'), 'B'),
    real('Test Warper', '{2}{R}', 3, 'Creature \u2014 Human', 'Warp {1}{R} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)', ('3', '2'), 'R'),
    real('Thought Prison', '{5}', 5, 'Artifact',
         'Imprint \u2014 When this artifact enters, you may have target player reveal their hand. If you do, choose a nonland card from it and exile that card.\nWhenever a player casts a spell that shares a color or mana value with the exiled card, this artifact deals 2 damage to that player.', None),
    real('Test Red Two', '{1}{R}', 2, 'Creature \u2014 Goblin', '', ('2', '2'), 'R'),
    real('Total War', '{3}{R}', 4, 'Enchantment',
         "Whenever a player attacks with one or more creatures, destroy all untapped non-Wall creatures that player controls that didn't attack, except for creatures the player hasn't controlled continuously since the beginning of the turn.", None, 'R'),
    real('Gemini Engine', '{6}', 6, 'Artifact Creature — Construct',
         "Whenever this creature attacks, create a colorless Construct artifact creature token named Twin that's attacking. Its power is equal to this creature's power and its toughness is equal to this creature's toughness. Sacrifice the token at end of combat.", ('3', '4'), ''),
    real('Vizkopa Confessor', '{3}{W}{B}', 5, 'Creature — Human Cleric',
         'Extort (Whenever you cast a spell, you may pay {W/B}. If you do, each opponent loses 1 life and you gain that much life.)\nWhen this creature enters, pay any amount of life. Target opponent reveals that many cards from their hand. You choose one of them and exile it.', ('1', '3'), 'BW'),
    real('Wall of Caltrops', '{1}{W}', 2, 'Creature — Wall',
         "Defender (This creature can't attack.)\nWhenever this creature blocks a creature, if at least one other Wall creature is blocking that creature and no non-Wall creatures are blocking that creature, this creature gains banding until end of turn. (If any creatures with banding you control are blocking a creature, you divide that creature's combat damage, not its controller, among any of the creatures it's being blocked by.)", ('2', '1'), 'W'),
    real('Relentless Assault', '{2}{R}{R}', 4, 'Sorcery', 'Untap all creatures that attacked this turn. After this main phase, there is an additional combat phase followed by an additional main phase.', None, 'R'),
    real('Test Vigil', '{1}', 1, 'Creature — Human', 'Vigilance', ('1', '1'), ''),
    real('Joyful Stormsculptor', '{2}{U}{R}', 4, 'Creature — Faerie Wizard', 'When this creature enters, create two 1/1 blue and red Elemental creature tokens.\nWhenever you cast a spell that has convoke, this creature deals 1 damage to each opponent and each battle they protect.', ('3', '3'), 'RU'),
    real('Test Convoke', '{1}', 1, 'Sorcery', 'Convoke', None, ''),
    real('Psychogenic Probe', '{2}', 2, 'Artifact', 'Whenever a spell or ability causes a player to shuffle their library, this artifact deals 2 damage to that player.', None, ''),
    real('Test Shuffle', '{1}', 1, 'Sorcery', 'Target player shuffles their library.', None, ''),
    real('Widespread Panic', '{2}{R}', 3, 'Enchantment', 'Whenever a spell or ability causes its controller to shuffle their library, that player puts a card from their hand on top of their library.', None, 'R'),
    real('Etched Host Doombringer', '{4}{B}', 5, 'Creature — Phyrexian Demon', 'When this creature enters, choose one —\n• Target opponent loses 2 life and you gain 2 life.\n• Choose target battle. If an opponent protects it, remove three defense counters from it. Otherwise, put three defense counters on it.', ('3', '5'), 'B'),
    real('Virtual Assistant', '{2}', 2, 'Artifact Creature — Robot', 'Defender\nWhenever you cast a spell using teamwork, create a 1/1 colorless Robot Hero artifact creature token with flying.', ('0', '3'), ''),
    real('Test Teamwork', '{1}', 1, 'Sorcery', 'Teamwork 1 (As an additional cost to cast this spell, you may tap any number of creatures you control with total power 1 or more.)\nYou gain 1 life.', None, ''),
    real('Test Wall', '{1}', 1, 'Creature — Wall', '', ('0', '4'), ''),
    real('Loxodon Peacekeeper', '{2}{W}{W}', 4, 'Creature — Elephant Soldier',
         'At the beginning of your upkeep, the player with the lowest life total gains control of this creature. If two or more players are tied for lowest life total, you choose one of them, and that player gains control of this creature.', ('4', '4'), 'W'),
    real('War Barge', '{4}', 4, 'Artifact',
         "{3}: Target creature gains islandwalk until end of turn. When this artifact leaves the battlefield this turn, destroy that creature. A creature destroyed this way can't be regenerated. (A creature with islandwalk can't be blocked as long as defending player controls an Island.)", None, ''),
    real('Infernal Offering', '{4}{B}', 5, 'Sorcery',
         'Choose an opponent. You and that player each sacrifice a creature. Each player who sacrificed a creature this way draws two cards.\nChoose an opponent. Return a creature card from your graveyard to the battlefield, then that player returns a creature card from their graveyard to the battlefield.', None, 'B'),
    real('Sands of Time', '{4}', 4, 'Artifact',
         "Each player skips their untap step.\nAt the beginning of each player's upkeep, that player simultaneously untaps each tapped artifact, creature, and land they control and taps each untapped artifact, creature, and land they control.", None, ''),
    real('Henry Wu, InGen Geneticist', '{1}{G}', 2, 'Legendary Creature — Human Scientist',
         "Henry Wu and other Human creatures you control have exploit. (When a creature with exploit enters, you may sacrifice a creature.)\nWhenever a creature you control exploits a non-Human creature, draw a card. If the exploited creature had power 3 or greater, create a Treasure token.", ('2', '2'), 'G'),
    real('Test Human', '{1}', 1, 'Creature — Human', '', ('1', '1'), ''),
    real('Wormfang Crab', '{2}{U}', 3, 'Creature — Crab Horror', "This creature can't be blocked.\nWhen this creature enters, an opponent chooses a permanent you control other than this creature and exiles it.\nWhen this creature leaves the battlefield, return the exiled card to the battlefield under its owner's control.", ('3', '3'), 'U'),
    real('Test Doom', '{1}', 1, 'Instant', 'Destroy target creature.', None, ''),
    real('Wormfang Drake', '{1}{U}', 2, 'Creature — Drake Horror', 'Flying\nWhen this creature enters, sacrifice it unless you exile a creature you control other than this creature.\nWhen this creature leaves the battlefield, return the exiled card to the battlefield under its owner\'s control.', ('3', '3'), 'U'),
    real('Carry Away', '{1}{U}', 2, 'Enchantment — Aura', 'Enchant Equipment\nWhen this Aura enters, unattach enchanted Equipment.\nYou control enchanted Equipment.', None, 'U'),
    real('Test Blade', '{1}', 1, 'Artifact — Equipment', 'Equipped creature gets +1/+1.\nEquip {1}', None, ''),
    real('Mindstorm Crown', '{3}', 3, 'Artifact', 'At the beginning of your upkeep, draw a card if you had no cards in hand at the beginning of this turn. If you had a card in hand, this artifact deals 1 damage to you.', None, ''),
    real('Archaic\'s Agony', '{4}{R}', 5, 'Sorcery', 'Converge \u2014 Archaic\'s Agony deals X damage to target creature, where X is the number of colors of mana spent to cast this spell. Exile cards from the top of your library equal to the excess damage dealt to that creature this way. You may play those cards until the end of your next turn.', None, 'R'),
    real('Kill-Suit Cultist', '{B}', 1, 'Creature \u2014 Human Cleric', 'This creature attacks each combat if able.\n{B}, Sacrifice this creature: The next time damage would be dealt to target creature this turn, destroy that creature instead.', ('1', '1'), 'B'),
    real('Touch of Moonglove', '{B}', 1, 'Instant',
         "Target creature you control gets +1/+0 and gains deathtouch until end of turn. Whenever a creature dealt damage by that creature dies this turn, its controller loses 2 life. (Any amount of damage a creature with deathtouch deals to a creature is enough to destroy it.)", None, 'B'),
    real('Eye for an Eye', '{W}{W}', 2, 'Instant',
         "The next time a source of your choice would deal damage to you this turn, instead that source deals that much damage to you and Eye for an Eye deals that much damage to that source's controller.", None, 'W'),
    real('Phyrexian Ingester', '{6}{U}', 7, 'Creature \u2014 Phyrexian Beast',
         "Imprint \u2014 When this creature enters, you may exile target nontoken creature.\nThis creature gets +X/+Y, where X is the exiled creature card's power and Y is its toughness.", ('3', '3'), 'U'),
    real('The Fallen', '{1}{B}{B}{B}', 4, 'Creature \u2014 Zombie',
         'At the beginning of your upkeep, this creature deals 1 damage to each opponent and planeswalker it has dealt damage to this game.', ('2', '3'), 'B'),
    real('Gelatinous Cube', '{2}{B}{B}', 4, 'Creature \u2014 Ooze',
         "Engulf \u2014 When this creature enters, exile target non-Ooze creature an opponent controls until this creature leaves the battlefield.\nDissolve \u2014 {X}{B}: Put target creature card with mana value X exiled with this creature into its owner's graveyard.", ('4', '3'), 'B'),
    real('Suncleanser', '{1}{W}', 2, 'Creature \u2014 Human Cleric',
         "When this creature enters, choose one \u2014\n\u2022 Remove all counters from target creature. It can't have counters put on it for as long as this creature remains on the battlefield.\n\u2022 Target opponent loses all counters. That player can't get counters for as long as this creature remains on the battlefield.", ('1', '4'), 'W'),
    real('Test Grow', '{G}', 1, 'Instant', 'Put a +1/+1 counter on target creature.', None, 'G'),
    real('Test Venom', '{B}', 1, 'Instant', 'Target player gets two poison counters.', None, 'B'),
    real('Elkin Lair', '{3}{R}', 4, 'World Enchantment',
         "At the beginning of each player's upkeep, that player exiles a card at random from their hand. The player may play that card this turn. At the beginning of the next end step, if the player hasn't played the card, they put it into their graveyard.", None, 'R'),
    real("Ertai's Familiar", '{1}{U}', 2, 'Creature \u2014 Illusion',
         "Phasing (This phases in or out before you untap during each of your untap steps. While it's phased out, it's treated as though it doesn't exist.)\nWhen this creature phases out or leaves the battlefield, mill three cards.\n{U}: Until your next upkeep, this creature can't phase out.", ('2', '2'), 'U'),
    real('Test Zap', '{R}', 1, 'Instant', 'Test Zap deals 1 damage to target creature.', None, 'R'),
    real('Beamsplitter Mage', '{1}{R}', 2, 'Creature \u2014 Human Wizard', 'Whenever you cast an instant or sorcery spell that targets only this creature, if you control one or more other creatures that spell could target, choose one of those creatures. Copy that spell. The copy targets the chosen creature.', ('1', '3'), 'R'),
    real('Biblioplex Tomekeeper', '{4}', 4, 'Artifact Creature \u2014 Construct', 'When this creature enters, choose up to one \u2014\n\u2022 Target creature becomes prepared.\n\u2022 Target creature becomes unprepared.', ('3', '4'), ''),
    real('The Fantastic Four', '{2}{U}{R}{W}', 5, 'Legendary Creature \u2014 Human Hero', "When The Fantastic Four enter and whenever you cast a spell with power, toughness, or mana value 4, choose one that hasn't been chosen this turn.\n\u2022 Create a 0/4 colorless Wall creature token with defender.\n\u2022 The Fantastic Four deal 3 damage to each opponent.\n\u2022 Put two +1/+1 counters on target creature.\n\u2022 Draw a card.", ('4', '4'), 'RUW'),
    real('Test Four Power', '{1}', 1, 'Creature \u2014 Human', '', ('4', '1'), ''),
    real('Casey & Raph, Hotheads', '{3}{R}', 4, 'Legendary Creature \u2014 Mutant Ninja Turtle', "When Casey & Raph enter, choose one or both. Each mode must target a different player.\n\u2022 Target player exiles the top card of their library. Until that player's next end step, they may play that card without paying its mana cost.\n\u2022 Target player creates two Treasure tokens.", ('4', '3'), 'R'),
    real('Hill Giant', '{3}{R}', 4, 'Creature — Giant', '', ('3', '3'), 'R'),
    real('Divination', '{2}{U}', 3, 'Sorcery', 'Draw two cards.', None, 'U'),
]
NAMES = [c["name"] for c in EXTRA if c["name"] not in ("Divination", "Test Zap", "Test Four Power", "Hill Giant", "Test Wall", "Test Human", "Test Doom", "Test Blade", "Relentless Assault", "Test Vigil", "Test Convoke", "Test Shuffle", "Test Teamwork")]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REVIEW34, *EXTRA, PREPARED], settings.cards_db_path, meta={"bulk_type": "test"})
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


def test_total_war_didnt_attack_means_this_combat(cards):
    """Total War (508.1, 500.8): in an additional combat, a creature that attacked only in the first combat 'didn't attack' in this one and dies."""
    s = build(cards, ["Test Vigil", "Grizzly Bears", "Relentless Assault", "Total War"], ["Goblin"])
    vig, bears = put(s, "Test Vigil"), put(s, "Grizzly Bears")
    for c in (vig, bears):
        s.state.rules.controlled_since[c.id].turn = s.state.rules.controlled_since[c.id].observed_from_turn = 0
    attack(s, vig)
    through_combat(s)
    assert s.state.cards[vig.id].zone == "p1:battlefield"
    put(s, "Total War", "p1")
    to_hand(s, "Relentless Assault")
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Relentless Assault").id)
    settle(s)
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.combats == 2
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    settle(s)
    assert s.state.cards[vig.id].zone == "p1:graveyard" and s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def test_joyful_stormsculptor_hits_opponent_and_their_battle_only(cards):
    """Joyful Stormsculptor (310.8, 120.3): a convoke spell pings each opponent and each battle an opponent protects, not a battle I protect."""
    s = build(cards, ["Joyful Stormsculptor", "Test Convoke", SIEGE], [SIEGE])
    put(s, "Joyful Stormsculptor")
    mine, theirs = put(s, SIEGE), put(s, SIEGE, "p2")
    for b in (mine, theirs):
        act(s, "p1", type="counter", card_ids=[b.id], kind="defense", delta=4)
    drive(s, lambda d: "p2" if "p2" in [o.id for o in d.options] else None)
    protectors = dict(s.state.rules.protectors)  # (shown on failure)
    cast(s, "Test Convoke")
    assert s.state.players["p2"].life == 39
    defense = {b.id: next((n for k, n in s.state.cards[b.id].counters.items() if k == "defense"), 0) for b in (mine, theirs)}
    assert (defense[mine.id], defense[theirs.id]) == (3, 4), (defense, protectors)  # mine is protected by Bob, Bob's by me
    check(s)


@pytest.mark.parametrize("target", ["p1", "p2"])
def test_psychogenic_probe_damages_whoever_shuffles(cards, target):
    """Psychogenic Probe (701.24): 2 damage to the shuffling player, the Probe's controller included."""
    s = build(cards, ["Psychogenic Probe", "Test Shuffle"], [])
    put(s, "Psychogenic Probe")
    mana(s, C=1)
    cast(s, "Test Shuffle", [target])
    assert s.state.players[target].life == 38 and s.state.players["p2" if target == "p1" else "p1"].life == 40
    check(s)


def test_manual_table_shuffle_does_not_trigger_probe_or_panic(cards):
    """701.24: only a spell or ability shuffle triggers Psychogenic Probe / Widespread Panic; a manual table Shuffle does not."""
    s = build(cards, ["Psychogenic Probe", "Widespread Panic"], [])
    put(s, "Psychogenic Probe")
    put(s, "Widespread Panic")
    act(s, "p1", type="shuffle", player="p1", zone="library")
    settle(s)
    assert s.state.rules.decision is None and s.state.players["p1"].life == 40
    check(s)


def test_widespread_panic_shuffler_puts_a_hand_card_on_top(cards):
    """Widespread Panic (701.24): the player whose library was shuffled (here Bob, via Test Shuffle) puts a hand card on top of it."""
    s = build(cards, ["Widespread Panic", "Test Shuffle"], ["Grizzly Bears"])
    put(s, "Widespread Panic")
    mana(s, C=1)
    to_hand(s, "Grizzly Bears", "p2")
    cast(s, "Test Shuffle", ["p2"])
    for _ in range(5):
        d = s.state.rules.decision
        if d is None:
            break
        assert d.player == "p2", d.player
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        settle(s)
    assert s.state.zones["p2:library"][0] == card_named(s, "Grizzly Bears", "p2").id and not s.state.zones["p2:hand"]
    check(s)


@pytest.mark.parametrize("owner, expected", [("p1", 1), ("p2", 7)])  # a Siege is protected by an opponent of its controller
def test_etched_host_doombringer_battle_mode_follows_the_protector(cards, owner, expected):
    """Etched Host Doombringer (310.4, 310.8): a battle an opponent protects loses three defense counters, any other gains three (starts at 4)."""
    s = build(cards, ["Etched Host Doombringer", SIEGE], [SIEGE])
    battle = put(s, SIEGE, owner)
    act(s, owner, type="counter", card_ids=[battle.id], kind="defense", delta=4)
    settle(s)  # state-based actions: the Siege's protector is chosen (310.11)
    mana(s, C=1, B=1)
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Etched Host Doombringer").id)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        pick = next((o.id for o in d.options if "battle" in (o.label or "").lower() or o.id == battle.id), d.options[0].id)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    assert s.state.cards[battle.id].counters.get("defense", 0) == expected, s.state.cards[battle.id].counters
    check(s)


@pytest.mark.parametrize("teamwork", [False, True])
def test_virtual_assistant_makes_a_robot_only_for_a_teamwork_spell(cards, teamwork):
    """Virtual Assistant (702.194b): casting a spell using teamwork (tapping creatures, total power 1+) creates a 1/1 flying Robot Hero."""
    s = build(cards, ["Virtual Assistant", "Test Teamwork", "Grizzly Bears"], [])
    put(s, "Virtual Assistant")
    helper = put(s, "Grizzly Bears")
    s.state.rules.controlled_since[helper.id].turn = s.state.rules.controlled_since[helper.id].observed_from_turn = 0
    mana(s, C=1)
    spell = to_hand(s, "Test Teamwork")
    extra = {"optional_costs": [f"{spell.id}:teamwork"], "cost_choices": [{"component": 0, "cards": [helper.id]}]} if teamwork else {}
    act(s, "p1", type="cast_spell", card_id=spell.id, **extra)
    settle(s)
    assert any(c.name == "Robot Hero" for c in s.state.cards.values()) == teamwork
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


@pytest.mark.parametrize("extra,banding", [("Test Wall", True), ("Goblin", False), (None, False)])
def test_wall_of_caltrops_banding_needs_walls_only(cards, extra, banding):
    s = build(cards, ["Grizzly Bears"], ["Wall of Caltrops", "Test Wall", "Goblin"])
    caltrops = put(s, "Wall of Caltrops", "p2")
    blockers = [caltrops]
    if extra:
        blockers.append(put(s, extra, "p2"))
    bears = put(s, "Grizzly Bears")
    attack(s, bears)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": bears.id} for b in blockers])
    for _ in range(6):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    assert ("banding" in ch(s, caltrops).keywords) is banding
    check(s)


@pytest.mark.parametrize("p1, p2, pick, owner", [(30, 10, None, "p2"), (10, 30, None, "p1"), (20, 20, "p2", "p2"), (20, 20, "p1", "p1")])
def test_loxodon_peacekeeper_goes_to_the_lowest_life(cards, p1, p2, pick, owner):
    """Loxodon Peacekeeper (119.1, 613.1b): the lowest life total gains control at the controller's upkeep; the controller chooses among ties."""
    s = build(cards, ["Loxodon Peacekeeper"], [])
    peace = put(s, "Loxodon Peacekeeper")
    act(s, "p1", type="set_life", player="p1", value=p1)
    act(s, "p2", type="set_life", player="p2", value=p2)
    asked = []
    for _ in range(60):  # on to Alice's turn 3 main phase; the upkeep trigger resolves on the way
        if s.state.turn.number == 3 and s.state.turn.phase == "main1":
            break
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            asked.append(d.player)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick or d.options[0].id])
    assert s.state.cards[peace.id].controller == owner and asked == (["p1"] if pick else [])
    check(s)


@pytest.mark.parametrize("leaves", [True, False])
def test_war_barge_destroys_its_target_when_the_barge_leaves(cards, leaves):
    """War Barge (603.7c): the delayed trigger is the artifact's; it destroys the creature the activation targeted, and only this turn."""
    s = build(cards, ["War Barge", "Grizzly Bears", "Test Shatter Charm"], [])
    barge = put(s, "War Barge")
    bears = put(s, "Grizzly Bears")
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=barge.id, ability=0, targets=[bears.id], target_counts=[1])
    settle(s)
    assert "islandwalk" in ch(s, bears).keywords
    if leaves:
        mana(s, "p1", R=1)
        cast(s, "Test Shatter Charm", [barge.id])
    settle(s)
    assert s.state.cards[bears.id].zone == ("p1:graveyard" if leaves else "p1:battlefield")
    check(s)


@pytest.mark.parametrize("theirs", [1, 0])
def test_infernal_offering_both_sacrifice_draw_then_both_reanimate(cards, theirs):
    """Infernal Offering (101.4, 701.21a): you and the chosen opponent sacrifice together; only a player who sacrificed draws two; then each returns a creature card."""
    s = build(cards, ["Infernal Offering", "Grizzly Bears", "Llanowar Elves"], ["Goblin", "Benalish Hero"])
    put(s, "Grizzly Bears")
    if theirs:
        put(s, "Goblin", "p2")
    hand = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2")}
    mana(s, "p1", B=1, C=4)
    cast(s, "Infernal Offering")
    drive(s)
    gy = lambda p: sorted(s.state.cards[c].name for c in s.state.zones[f"{p}:graveyard"])  # noqa: E731
    bf = lambda p: sorted(s.state.cards[c].name for c in s.state.zones[f"{p}:battlefield"] if "Creature" in ch(s, s.state.cards[c]).types)  # noqa: E731
    assert bf("p1") == ["Grizzly Bears"] and gy("p1") == ["Infernal Offering"]  # the only creature card in the graveyard came back
    assert len(s.state.zones["p1:hand"]) == hand["p1"] + 2
    assert len(s.state.zones["p2:hand"]) == hand["p2"] + (2 if theirs else 0) and bf("p2") == (["Goblin"] if theirs else [])
    check(s)


DELVER = "Delver of Secrets // Insectile Aberration"


def test_invasion_of_pyrulea_back_face_grants_trample_and_ward_to_other_transformed_permanents(cards):
    """Gargantuan Slabhorn (701.27g): other transformed permanents you control have trample and ward {2}; not untransformed ones, nor an opponent's."""
    s = build(cards, [PYRULEA, DELVER, "Grizzly Bears"], [DELVER])
    slab = put(s, PYRULEA)
    act(s, "p1", type="set_face", card_id=slab.id, face=1)
    mine, plain, theirs = put(s, DELVER), put(s, "Grizzly Bears"), put(s, DELVER, "p2")
    for c in (mine, theirs):
        act(s, c.controller, type="set_face", card_id=c.id, face=1)
    kw = lambda c: set(ch(s, c).keywords)  # noqa: E731
    assert "trample" in kw(mine) and any("ward" in k for k in kw(mine))
    assert "trample" not in kw(plain) and "trample" not in kw(theirs)
    check(s)


@pytest.mark.parametrize("top, draws", [("Forest", 1), (DELVER, 1), ("Grizzly Bears", 0)])
def test_invasion_of_pyrulea_draws_for_a_land_or_double_faced_top_card(cards, top, draws):
    """Invasion of Pyrulea (701.22, 701.20a): scry 3 then reveal the top card; a land or double-faced card draws a card."""
    s = build(cards, [PYRULEA, top] if top != "Forest" else [PYRULEA], [], forests=9 if top == "Forest" else 0)
    mana(s, "p1", G=1, U=1)
    hand = len(s.state.zones["p1:hand"])
    cast(s, PYRULEA)
    drive(s, lambda d: "p2" if "p2" in [o.id for o in d.options] else None)
    assert len(s.state.zones["p1:hand"]) == hand + draws, [s.state.cards[c].name for c in s.state.zones["p1:hand"]]
    check(s)


def test_sands_of_time_swaps_tapped_and_untapped_on_the_upkeep_players_permanents_only(cards):
    """Sands of Time (502.1, 603.2): at each player's upkeep that player's tapped artifacts/creatures/lands untap while the untapped ones tap; others are left alone."""
    s = build(cards, ["Sands of Time", "Grizzly Bears", "Forest"], ["Goblin"])
    sands, bears, theirs = put(s, "Sands of Time"), put(s, "Grizzly Bears"), put(s, "Goblin", "p2")
    forest = put(s, "Forest")
    act(s, "p1", type="tap", card_ids=[bears.id], tapped=True)
    for _ in range(80):  # to Alice's turn 3 main phase, answering what is asked
        if s.state.turn.number == 3 and s.state.turn.phase == "main1":
            break
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    tapped = lambda c: s.state.cards[c.id].tapped  # noqa: E731
    assert (tapped(bears), tapped(forest), tapped(sands)) == (False, True, True)  # Alice's upkeep swapped hers
    assert tapped(theirs)  # Bob's upkeep (turn 2) tapped his untapped Goblin; Alice's upkeep left it alone
    check(s)


@pytest.mark.parametrize(("victim", "cards_drawn", "treasure"), [("Hill Giant", 1, 1), ("Grizzly Bears", 1, 0), ("Test Human", 0, 0)])
def test_henry_wu_treasure_needs_power_three_exploited_non_human(cards, victim, cards_drawn, treasure):
    """Henry Wu (702.110b, 608.2h): draw for a non-Human exploited; Treasure only when its power was 3+."""
    from tests.test_rules_wave12a_counters_keywords import answer

    s = build(cards, ["Henry Wu, InGen Geneticist", "Test Human", victim, "Forest"])
    put(s, "Henry Wu, InGen Geneticist")
    sac = put(s, victim)
    to_hand(s, "Test Human")
    mana(s, C=1)
    hand = len(s.state.zones["p1:hand"]) - 1
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Test Human").id)
    answer(s, "yes", sac.id)
    assert s.state.cards[sac.id].zone == "p1:graveyard"
    assert len(s.state.zones["p1:hand"]) == hand + cards_drawn
    assert sum(1 for c in s.state.cards.values() if c.is_token and c.name == "Treasure" and c.zone.endswith(":battlefield")) == treasure
    check(s)


def test_wormfang_crab_opponent_picks_and_the_card_returns_when_the_crab_leaves(cards):
    """Wormfang Crab (607.2a): Bob chooses which of Alice's other permanents is exiled; it comes back when the Crab leaves."""
    s = build(cards, ["Wormfang Crab", "Grizzly Bears", "Hill Giant", "Test Doom"])
    bears, giant = put(s, "Grizzly Bears"), put(s, "Hill Giant")
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Wormfang Crab").id)
    from tests.test_rules_wave12a_counters_keywords import answer

    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.decision.player == "p2"  # the opponent chooses, among Alice's permanents
    answer(s, giant.id)
    assert s.state.cards[giant.id].zone == "p1:exile" and s.state.cards[bears.id].zone == "p1:battlefield"
    crab = card_named(s, "Wormfang Crab")
    mana(s, C=1)
    cast(s, "Test Doom", [crab.id])
    assert s.state.cards[crab.id].zone == "p1:graveyard" and s.state.cards[giant.id].zone == "p1:battlefield"
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_wormfang_drake_exiles_another_creature_or_is_sacrificed(cards, pay):
    """Wormfang Drake (702.. champion-style payment, 607.2a): exile another creature or sacrifice the Drake; the creature returns when the Drake leaves."""
    from tests.test_rules_wave12a_counters_keywords import answer

    s = build(cards, ["Wormfang Drake", "Grizzly Bears", "Test Doom"])
    bears = put(s, "Grizzly Bears")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Wormfang Drake").id)
    answer(s, *(["pay", bears.id] if pay else ["decline"]))
    drake = card_named(s, "Wormfang Drake")
    if not pay:
        assert s.state.cards[drake.id].zone == "p1:graveyard" and s.state.cards[bears.id].zone == "p1:battlefield"
        return check(s)
    assert s.state.cards[drake.id].zone == "p1:battlefield" and s.state.cards[bears.id].zone == "p1:exile"
    mana(s, C=1)
    cast(s, "Test Doom", [drake.id])
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def test_carry_away_steals_the_equipment_and_unattaches_it(cards):
    """Carry Away (701.3d, 303.4e): Bob's equipped Equipment is unattached from his creature and Alice controls it."""
    s = build(cards, ["Carry Away"], ["Test Blade", "Goblin"])
    blade, goblin = put(s, "Test Blade", "p2"), put(s, "Goblin", "p2")
    act(s, "p1", type="attach", card_ids=[blade.id], to=goblin.id)
    assert s.state.cards[blade.id].attached_to == goblin.id
    mana(s, U=1, C=1)
    cast(s, "Carry Away", [blade.id])
    got = s.state.cards[blade.id]
    assert got.attached_to is None and got.controller == "p1" and got.owner == "p2"
    check(s)


@pytest.mark.parametrize(("holding", "life_after"), [(False, 40), (True, 39)])
def test_mindstorm_crown_draws_on_an_empty_hand_else_hurts(cards, holding, life_after):
    """Mindstorm Crown: Alice's turn-3 upkeep compares her hand as the turn began; a draw on an empty hand, 1 damage otherwise."""
    s = build(cards, ["Mindstorm Crown", "Divination"])
    put(s, "Mindstorm Crown")
    if holding:
        to_hand(s, "Divination")
    for _ in range(80):
        if s.state.turn.number == 3 and s.state.turn.phase == "main1":
            break
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert s.state.players["p1"].life == life_after
    assert len(s.state.zones["p1:hand"]) == 2  # the draw step's card plus the Crown's draw, or the held card
    check(s)


@pytest.mark.parametrize("colors,exiled", [(2, 1), (1, 0)])
def test_archaics_agony_excess_sizes_exile(cards, colors, exiled):
    """Archaic's Agony (120.10, 702.34 converge): X = colors spent; excess damage over the 1/1's lethal exiles that many cards from the library top."""
    s = build(cards, ["Archaic's Agony"], ["Test Human"])
    human = put(s, "Test Human", "p2")
    lib = len(s.state.zones["p1:library"])
    mana(s, "p1", **({"R": 1, "G": 1, "C": 3} if colors == 2 else {"R": 1, "C": 4}))
    cast(s, "Archaic's Agony", [human.id])
    drive(s)
    assert s.state.cards[human.id].zone == "p2:graveyard"
    assert len(s.state.zones["p1:library"]) == lib - 1 - exiled and len(s.state.zones["p1:exile"]) == exiled
    check(s)


@pytest.mark.parametrize("armed", [True, False])
def test_kill_suit_cultist_destroys_instead_of_damage(cards, armed):
    """Kill-Suit Cultist (614.1a): the first damage to the target is never dealt; the creature is destroyed instead. Without the shield 1 damage is harmless."""
    s = build(cards, ["Kill-Suit Cultist", "Grizzly Bears", "Test Zap"], [])
    cultist = put(s, "Kill-Suit Cultist")
    bears = put(s, "Grizzly Bears")
    if armed:
        mana(s, "p1", B=1)
        act(s, "p1", type="activate_ability", card_id=cultist.id, ability=1, targets=[bears.id], target_counts=[1])
        settle(s)
        assert s.state.cards[cultist.id].zone == "p1:graveyard"
    mana(s, "p1", R=1)
    cast(s, "Test Zap", [bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == ("p1:graveyard" if armed else "p1:battlefield")
    check(s)


@pytest.mark.parametrize("others", [2, 0])
def test_beamsplitter_mage_copies_for_one_chosen_creature(cards, others):
    """Beamsplitter Mage (707.10d): the copy targets only the creature the controller chooses among the other legal ones; with none there is no copy."""
    s = build(cards, ["Beamsplitter Mage", "Grizzly Bears", "Hill Giant", "Test Zap"], [])
    mage = put(s, "Beamsplitter Mage")
    bears, giant = (put(s, "Grizzly Bears"), put(s, "Hill Giant")) if others else (None, None)
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Zap").id, targets=[mage.id])
    assert len(s.state.zones["stack"]) == (2 if others else 0)  # 603.4: without another creature to target there is no trigger (the spell has resolved)
    for _ in range(12):
        if (d := s.state.rules.decision) is not None:
            pick = [giant.id] if giant and giant.id in [o.id for o in d.options] else [d.options[0].id]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    hurt = lambda c: s.state.cards[c.id].damage  # noqa: E731
    assert hurt(mage) == 1
    if others:
        assert (hurt(bears), hurt(giant)) == (0, 1)
    check(s)


@pytest.mark.parametrize("mode,prepared", [("unprepared", 0), ("becomes prepared", 1)])
def test_biblioplex_tomekeeper_prepares_or_unprepares(cards, mode, prepared):
    """Biblioplex Tomekeeper (722.3a, 722.3b): the chosen mode gives or removes the prepared designation of the target creature."""
    s = build(cards, ["Biblioplex Tomekeeper", "Studious First-Year // Rampant Growth"], [])
    if mode == "unprepared":  # it enters prepared (cast it); otherwise it is just put onto the battlefield, not prepared
        first = to_hand(s, "Studious First-Year // Rampant Growth")
        mana(s, "p1", G=1)
        act(s, "p1", type="cast_spell", card_id=first.id)
        settle(s)
        assert len(s.state.rules.prepared) == 1
    else:
        first = put(s, "Studious First-Year // Rampant Growth")
    mana(s, "p1", C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Biblioplex Tomekeeper").id)
    for _ in range(14):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        pick = next((o.id for o in d.options if mode in (o.label or "").lower() or o.id == first.id), d.options[0].id)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    assert len(s.state.rules.prepared) == prepared
    check(s)


def _modes(s, pick):
    """Drive decisions; ``pick`` is a mode-label word. Returns the labels offered at each mode decision."""
    offered = []
    for _ in range(16):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        labels = [(o.label or "").lower() for o in d.options]
        if any("wall" in x for x in labels):
            offered.append(labels)
        choice = next((o.id for o in d.options if pick in (o.label or "").lower()), d.options[0].id)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[choice])
    return offered


@pytest.mark.parametrize("second,triggers", [("Hill Giant", True), ("Test Four Power", True), ("Grizzly Bears", False)])
def test_fantastic_four_modes_not_repeated_in_a_turn(cards, second, triggers):
    """The Fantastic Four: entering and casting a spell with power, toughness or mana value 4 each choose a mode not yet chosen this turn."""
    s = build(cards, ["The Fantastic Four", second], [])
    mana(s, "p1", C=2, U=1, R=1, W=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "The Fantastic Four").id)
    _modes(s, "3 damage")
    assert s.state.players["p2"].life == 37
    mana(s, "p1", C=4, R=1, G=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, second).id)
    offered = _modes(s, "wall")
    if triggers:
        assert offered and all(not any("3 damage" in x for x in labels) for labels in offered)
        assert any(c.name == "Wall" or "Wall" in c.name for c in s.state.cards.values() if c.zone == "p1:battlefield")
    else:
        assert not offered
    check(s)


def test_casey_and_raph_two_modes_two_players(cards):
    """Casey & Raph (700.2d, 601.2c): both modes, each at a different player; the exile's player (owner) may play the card free until their next end step."""
    s = build(cards, ["Casey & Raph, Hotheads"], [])
    mana(s, "p1", C=3, R=1)
    lib = len(s.state.zones["p2:library"])
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Casey & Raph, Hotheads").id)
    first = True
    for _ in range(12):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        if d.kind == "choose_cards":
            pick = [o.id for o in d.options]
        else:
            pick = ["p2"] if first and "p2" in [o.id for o in d.options] else [d.options[0].id]
            first = False
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
    assert len(s.state.zones["p2:library"]) == lib - 1 and len(s.state.zones["p2:exile"]) == 1
    assert sum(1 for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield") == 2
    perms = s.state.rules.permissions
    assert [(p.player, p.until) for p in perms] == [("p2", "next_end_step")]
    check(s)


def test_beamsplitter_mage_rechecks_if_on_resolution(cards):
    """Beamsplitter Mage (603.4): the other creature is gone when the ability resolves, so it does nothing."""
    s = build(cards, ["Beamsplitter Mage", "Grizzly Bears", "Test Zap"], ["Lightning Bolt"])
    mage = put(s, "Beamsplitter Mage")
    bears = put(s, "Grizzly Bears")
    mana(s, "p1", R=1)
    mana(s, "p2", R=1)
    act(s, "p1", type="configure", automation_options={"auto_priority_pass": False})  # stop for responses
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Zap").id, targets=[mage.id])
    assert len(s.state.zones["stack"]) == 2 and s.state.rules.priority == "p2"
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    assert s.state.rules.decision is None and not s.state.zones["stack"]
    assert s.state.cards[mage.id].damage == 1
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_fugitive_of_the_judoon_token_has_ward_and_chapter_three_exiles_both(cards, pay):
    """Fugitive of the Judoon (702.21a, 118.3): the Human token has ward {2}; chapter III exiles the Human and a Clue together to fetch a Doctor."""
    s = build(cards, ["Fugitive of the Judoon", *["Forest"] * 20, "Test Doctor"], [], forests=0, islands=40)  # (the Doctor stays deep in the library)
    mana(s, "p1", G=1, C=4)
    saga = to_hand(s, "Fugitive of the Judoon")
    act(s, "p1", type="cast_spell", card_id=saga.id)
    seen = False
    for _ in range(400):
        d = s.state.rules.decision
        human = next((c for c in s.state.cards.values() if c.name == "Human" and c.zone == "p1:battlefield"), None)
        if human is not None and not seen:
            seen = True
            assert any("ward" in k for k in ch(s, human).keywords)
        if s.state.cards[saga.id].zone == "p1:graveyard" and d is None and not s.state.zones.get("stack"):
            break  # sacrificed after chapter III
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            ids = [o.id for o in d.options]
            yes = "pay" if pay else "decline"
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((i for i in ids if i in (yes, "p2")), ids[0])])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert seen
    on = lambda n, z: [c for c in s.state.cards.values() if c.name == n and c.zone == z]  # noqa: E731
    assert bool(on("Test Doctor", "p1:battlefield")) == pay
    assert len(on("Human", "p1:battlefield")) == (0 if pay else 1) and len(on("Clue", "p1:battlefield")) == (0 if pay else 1)
    check(s)


@pytest.mark.parametrize("emerge", [True, False])
def test_foul_emissary_makes_a_horror_only_when_sacrificed_to_emerge(cards, emerge):
    """Foul Emissary (702.119a): sacrificed to cast a spell with emerge it makes a 3/2 Eldrazi Horror; sacrificed by an effect it does not."""
    s = build(cards, ["Foul Emissary", "Distended Mindbender" if emerge else "Infernal Offering"], ["Goblin"])
    put(s, "Foul Emissary")
    mana(s, "p1", B=2, C=8)
    if emerge:
        mind = to_hand(s, "Distended Mindbender")
        emissary = card_named(s, "Foul Emissary")
        act(s, "p1", type="cast_spell", card_id=mind.id, alt_cost=f"{mind.id}:0", cost_choices=[{"component": 0, "cards": [emissary.id]}], targets=["p2"])
    else:
        cast(s, "Infernal Offering")
    drive(s)
    horrors = [c for c in s.state.cards.values() if c.name == "Eldrazi Horror" and c.zone == "p1:battlefield"]
    assert len(horrors) == (1 if emerge else 0)
    assert emerge or card_named(s, "Infernal Offering").zone == "p1:graveyard"  # it resolved: the Emissary was sacrificed there (and came back with mode 2)
    check(s)


@pytest.mark.parametrize("target", ["Test Warper", "Grizzly Bears"])
def test_blade_of_the_swarm_bottoms_only_an_exiled_card_with_warp(cards, target):
    """Blade of the Swarm (702.185a): mode two targets an exiled card with warp and puts it on the bottom of its owner's library."""
    s = build(cards, ["Blade of the Swarm", target], [])
    foe = card_named(s, target)
    act(s, "p1", type="move", card_ids=[foe.id], to={"player": "p1", "zone": "exile"})
    mana(s, "p1", B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Blade of the Swarm").id)
    _modes(s, "bottom")
    zone = s.state.cards[foe.id].zone
    assert zone == ("p1:library" if target == "Test Warper" else "p1:exile")
    if target == "Test Warper":
        assert s.state.zones["p1:library"][-1] == foe.id
    check(s)


@pytest.mark.parametrize("spell,hurt", [("Llanowar Elves", 2), ("Test Red Two", 2), ("Hill Giant", 0)])
def test_thought_prison_hurts_casters_of_spells_sharing_color_or_mana_value(cards, spell, hurt):
    """Thought Prison: the exiled Grizzly Bears (green, mana value 2) is shared by a green spell (Llanowar Elves) and by a mana value 2 one (Test Red Two), not by a red 4."""
    s = build(cards, ["Thought Prison", spell], ["Grizzly Bears"])
    mana(s, "p1", C=5)
    bears = to_hand(s, "Grizzly Bears", "p2")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Thought Prison").id)
    drive(s, lambda d: "p2" if "p2" in [o.id for o in d.options] else bears.id if bears.id in [o.id for o in d.options] else "yes" if "yes" in [o.id for o in d.options] else None)
    assert s.state.cards[bears.id].zone == "p2:exile"
    life = s.state.players["p1"].life
    mana(s, "p1", C=4, R=1, G=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, spell).id)
    drive(s)
    assert s.state.players["p1"].life == life - hurt
    check(s)


def test_thought_prison_declined_reveal_exiles_nothing_and_never_hurts(cards):
    """Thought Prison: "you may have target player reveal" declined (603.5): nothing exiled, so no spell shares anything with it."""
    s = build(cards, ["Thought Prison", "Llanowar Elves"], ["Grizzly Bears"])
    mana(s, "p1", C=5)
    bears = to_hand(s, "Grizzly Bears", "p2")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Thought Prison").id)
    drive(s, lambda d: "p2" if "p2" in [o.id for o in d.options] else "no" if "no" in [o.id for o in d.options] else None)
    assert s.state.cards[bears.id].zone == "p2:hand"
    life = s.state.players["p1"].life
    mana(s, "p1", G=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Llanowar Elves").id)
    drive(s)
    assert s.state.players["p1"].life == life
    check(s)


def test_touch_of_moonglove_blocker_dies_and_controller_loses_2(cards):
    """Touch of Moonglove (120.3, 603.7c): the blocker Bears hit with deathtouch dies, its controller loses 2; a creature Bears never damaged does not."""
    s = build(cards, ["Grizzly Bears", "Touch of Moonglove", "Test Zap"], ["Hill Giant", "Goblin"])
    bears = put(s, "Grizzly Bears")
    giant = put(s, "Hill Giant", "p2")
    goblin = put(s, "Goblin", "p2")
    mana(s, "p1", B=1)
    cast(s, "Touch of Moonglove", [bears.id])
    life = s.state.players["p2"].life
    mana(s, "p1", R=1)
    cast(s, "Test Zap", [goblin.id])
    assert s.state.cards[goblin.id].zone == "p2:graveyard" and s.state.players["p2"].life == life
    attack(s, bears)
    through_combat(s, [(giant, bears)])
    assert s.state.cards[giant.id].zone == "p2:graveyard"
    assert s.state.players["p2"].life == life - 2
    check(s)


def test_eye_for_an_eye_deals_the_same_damage_to_the_sources_controller(cards):
    """Eye for an Eye (609.7a, 614.1): Bob's Bolt is the chosen source; its 3 damage to Alice is still dealt and Eye deals 3 to Bob. A second Bolt is a different source."""
    from tests.test_rules_wave35a_one_shot_shields import (
        bobs_turn,
        bolt,
        choose,
        stops,
        until_asked,
    )

    s = build(cards, ["Eye for an Eye"], ["Lightning Bolt", "Lightning Bolt"])
    stops(s)
    bobs_turn(s)
    bolt(s, "p1")
    mana(s, "p1", W=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Eye for an Eye").id)
    until_asked(s)
    choose(s, "Lightning Bolt")
    for _ in range(12):
        if not s.state.zones.get("stack") and s.state.rules.decision is None:
            break
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1]) if d else act(s, s.state.rules.priority, type="pass_priority")
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (37, 37)
    assert not s.state.rules.replacements
    bolt(s, "p1")  # the shield is used up (615.8): the second Bolt hurts Alice alone
    for _ in range(6):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (34, 37)
    check(s)


@pytest.mark.parametrize("exile", [True, False])
def test_phyrexian_ingester_gets_the_imprinted_creatures_power_and_toughness(cards, exile):
    """Phyrexian Ingester (607.2a, 613.4c): 3/3 plus the exiled Hill Giant's 3/3; with nothing exiled it stays 3/3."""
    s = build(cards, ["Phyrexian Ingester"], ["Hill Giant"])
    giant = put(s, "Hill Giant", "p2")
    mana(s, "p1", U=1, C=6)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Phyrexian Ingester").id)
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            labels = {o.label: o.id for o in d.options}
            want = "Hill Giant" if "Hill Giant" in labels else "Yes" if exile else "No"
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[labels.get(want, d.options[0].id)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    ing = next(c for c in s.state.cards.values() if c.name == "Phyrexian Ingester")
    assert (s.state.cards[giant.id].zone == "p2:exile") is exile
    assert ch(s, ing).pt == ((6, 6) if exile else (3, 3))
    check(s)


@pytest.mark.parametrize("target, p2_life, walker_loyalty", [("p2", 37, None), ("walker", 40, 3), ("blocked", 40, None)])
def test_the_fallen_pings_only_what_it_has_dealt_damage_to_this_game(cards, target, p2_life, walker_loyalty):
    """The Fallen (120.3, 400.7): hit Bob -> pinged on every later upkeep; hit a planeswalker -> that walker pinged (2 combat + 1 = loyalty 0 from 3); blocked by a creature -> nobody pinged."""
    from tests.test_rules_conditionals import until

    s = build(cards, ["The Fallen"], ["Hill Giant", "Test Walker Card"])
    fallen = put(s, "The Fallen")
    walker = put(s, "Test Walker Card", "p2") if target == "walker" else None
    if walker is not None:
        act(s, "p2", type="counter", card_ids=[walker.id], kind="loyalty", delta=3)
    giant = put(s, "Hill Giant", "p2") if target == "blocked" else None
    attack(s, fallen, target=walker.id if walker is not None else "p2")
    through_combat(s, [(giant, fallen)] if giant is not None else None)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    assert s.state.players["p2"].life == p2_life
    if walker is not None:
        assert s.state.cards[walker.id].zone == "p2:graveyard"  # 3 - 2 combat - 1 from the upkeep ping = 0
    check(s)


@pytest.mark.parametrize("x, ok", [(4, True), (3, False)])
def test_gelatinous_cube_dissolve_needs_the_exiled_creature_with_mana_value_x(cards, x, ok):
    """Gelatinous Cube (607.2a): Hill Giant (mana value 4) exiled by the Engulf is a legal Dissolve target only for X=4; it goes to its owner's graveyard."""
    s = build(cards, ["Gelatinous Cube"], ["Hill Giant"])
    giant = put(s, "Hill Giant", "p2")
    mana(s, "p1", B=2, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Gelatinous Cube").id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((o.id for o in d.options if o.label == "Hill Giant"), d.options[0].id)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[giant.id].zone == "p2:exile"
    cube = next(c for c in s.state.cards.values() if c.name == "Gelatinous Cube")
    mana(s, "p1", B=1, C=x)
    if not ok:
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", card_id=cube.id, ability=1, x_value=x, targets=[giant.id], target_counts=[1])
        return
    act(s, "p1", type="activate_ability", card_id=cube.id, ability=1, x_value=x, targets=[giant.id], target_counts=[1])
    for _ in range(4):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[giant.id].zone == "p2:graveyard"
    check(s)


def test_suncleanser_creature_mode_strips_counters_and_bars_new_ones_until_it_leaves(cards):
    """Suncleanser (122.1, 614.17): Bears lose their counters and cannot get one while Suncleanser stays; once it dies they can; another creature is unaffected."""
    s = build(cards, ["Suncleanser", "Grizzly Bears", "Llanowar Elves", "Test Grow", "Test Shatter Charm"], [])
    bears = put(s, "Grizzly Bears")
    elves = put(s, "Llanowar Elves")
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=2)
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Suncleanser").id)
    for _ in range(16):
        d = s.state.rules.decision
        if d is not None:
            labels = {(o.label or "").lower(): o.id for o in d.options}
            pick = next((i for t, i in labels.items() if "remove all" in t), None) or next((i for t, i in labels.items() if "bears" in t), d.options[0].id)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[bears.id].counters.get("+1/+1", 0) == 0
    for target, grown in ((bears, 0), (elves, 1)):
        mana(s, "p1", G=1)
        cast(s, "Test Grow", [target.id])
        assert s.state.cards[target.id].counters.get("+1/+1", 0) == grown
    sun = next(c for c in s.state.cards.values() if c.name == "Suncleanser")
    act(s, "p1", type="move", card_ids=[sun.id], to={"zone": "graveyard"})  # it leaves: the bar ends (a new object, 400.7)
    mana(s, "p1", G=1)
    cast(s, "Test Grow", [bears.id])
    assert s.state.cards[bears.id].counters.get("+1/+1", 0) == 1
    check(s)


def test_suncleanser_opponent_mode_clears_their_counters_and_bars_new_ones(cards):
    """Suncleanser (122.1, 614.17): Bob's poison counters go; he cannot get more while it stays; Alice still can."""
    s = build(cards, ["Suncleanser", "Test Venom"], [])
    act(s, "p2", type="set_resource", key="poison", value=3)
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Suncleanser").id)
    for _ in range(16):
        d = s.state.rules.decision
        if d is not None:
            pick = next((o.id for o in d.options if "opponent" in (o.label or "").lower()), d.options[0].id)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.players["p2"].resources.get("poison", 0) == 0
    for who, got in (("p2", 0), ("p1", 2)):
        mana(s, "p1", B=1)
        cast(s, "Test Venom", [who])
        assert s.state.players[who].resources.get("poison", 0) == got
    check(s)


@pytest.mark.parametrize("play", [True, False])
def test_elkin_lair_exiles_the_upkeeping_players_card_and_buries_it_unless_played(cards, play):
    """Elkin Lair (400.3, 601.2a): Bob's only hand card is exiled at his upkeep and he may play it; at the next end step it goes to his graveyard unless played."""
    from tests.test_rules_conditionals import until

    s = build(cards, ["Elkin Lair"], ["Grizzly Bears"])
    put(s, "Elkin Lair")
    bears = to_hand(s, "Grizzly Bears", "p2")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    assert s.state.cards[bears.id].zone == "p2:exile"
    if play:
        mana(s, "p2", C=1, G=1)
        act(s, "p2", type="cast_spell", card_id=bears.id)
        until(s, lambda s: not s.state.zones.get("stack"))
    until(s, lambda s: s.state.turn.number == 3)
    assert s.state.cards[bears.id].zone == ("p2:battlefield" if play else "p2:graveyard")
    check(s)


@pytest.mark.parametrize("held", [False, True])
def test_ertais_familiar_mills_when_it_phases_out_unless_held_in(cards, held):
    """Ertai's Familiar (702.26b, 702.26d): it phases out in its controller's next untap step and mills three; {U} first (until their next upkeep) stops that."""
    from tests.test_rules_conditionals import until

    s = build(cards, ["Ertai's Familiar"], [], forests=40)
    fam = put(s, "Ertai's Familiar")
    if held:
        mana(s, "p1", U=1)
        act(s, "p1", type="activate_ability", card_id=fam.id, ability=3)
        until(s, lambda s: not s.state.zones.get("stack"))
    before = len(s.state.zones["p1:graveyard"])
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    assert s.state.cards[fam.id].zone == ("p1:battlefield" if held else "p1:phased")
    assert len(s.state.zones["p1:graveyard"]) == before + (0 if held else 3)
    check(s)


def test_ertais_familiar_mills_when_it_leaves_the_battlefield(cards):
    """Ertai's Familiar (603.10a): dying mills three cards."""
    s = build(cards, ["Ertai's Familiar", "Test Doom"], [], forests=40)
    fam = put(s, "Ertai's Familiar")
    before = len(s.state.zones["p1:graveyard"])
    mana(s, "p1", C=1)
    cast(s, "Test Doom", [fam.id])
    assert len(s.state.zones["p1:graveyard"]) == before + 1 + 1 + 3  # the Familiar, Test Doom, three milled
    check(s)
