"""-- Teach Fyodor -- how much of Magic the block builder can say: every keyword action (CR 701), every keyword ability (CR 702) and
every ability word (CR 207.2c), each rebuilt from its reminder text under a made-up name with nothing but the builder's pieces.

Each row is either an entry (a taught keyword or action that stands for the mechanic) or the reason it can't be one (``why``: the
piece that is missing). The status is derived, not hand-labelled: ``tests/test_teach_coverage.py`` runs every entry through
``taught.check`` (the engine reads every line FULL), and an entry counts as "before" the expressiveness sweep only when it uses no
piece or option that sweep added (``NEW_PIECES`` / ``NEW_OPTIONS``). ``python -m tests.teach_coverage`` writes
docs/TEACH_FYODOR_COVERAGE.md from these rows (the test checks the file is current).

The criterion: a mechanic counts only if its pieces don't *include* the mechanic. "It has flying" doesn't teach flying; "it can't be
blocked except by creatures with flying or reach" does (the attacking half of it). So:

* ``primitive``: a rules primitive no Oracle sentence spells out (deathtouch, first strike, haste …). A taught keyword can still
  *grant* it ("It has a keyword"), but can't rebuild it.
* ``piece``: the mechanic is itself one of the pieces (the verbs destroy, exile, scry … and the Kicker and Flashback pieces, whose
  words are the engine's own keyword): usable in any taught ability, not rebuilt from others.
* ``partial``: an entry that reads FULL but leaves part of the mechanic out (``partial`` says what).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# What the expressiveness sweep added (taught_vocab.py, docs/TEACH_FYODOR_COVERAGE.md "After").
NEW_PIECES = frozenset({
    "becomes_blocked", "blocks_or_blocked", "dealt_damage", "attacks_alone", "you_attack", "creature_dies", "if_this_turn", "if_state",
    "if_no_counters", "cost_discard_self", "cost_exile_self_gy", "limit_attacked", "sac_self", "sac_unless_mana", "sac_unless_life",
    "sac_unless", "return_dead", "counter_unless", "counter_unless_life", "exalt", "rally_attackers", "gy_return_self", "combat_rule",
    "evasion", "evasion_by", "landwalk", "would_die", "prevent_to_self", "uncounterable", "self_discount", "extra_cost", "alt_cost",
    "gy_cast", "gy_cast_exile", "gy_retrace", "kicker", "flashback",
})
NEW_OPTIONS = frozenset({("exile", "t_self"), ("bounce", "t_self"), ("creature_token", "color_white_black")})


def b(pid: str, **values: Any) -> dict[str, Any]:
    return {"id": pid, **({"values": values} if values else {})}


def may(block: dict[str, Any]) -> dict[str, Any]:
    return {"id": "may", "body": [block]}


def T(hat: str, *body: dict[str, Any], **values: Any) -> dict[str, Any]:  # noqa: N802 -- a When-piece ability
    return {"hat": b(hat, **values), "body": list(body)}


def S(piece: str, cond: dict[str, Any] | None = None, **values: Any) -> dict[str, Any]:  # noqa: N802 -- an Always ability
    return {"hat": b("static"), "body": [*([cond] if cond else []), b(piece, **values)]}


def A(*body: dict[str, Any]) -> dict[str, Any]:  # noqa: N802 -- a Pay-to-use ability
    return {"hat": b("activated"), "body": list(body)}


def X(*body: dict[str, Any]) -> dict[str, Any]:  # noqa: N802 -- what a taught action does
    return {"hat": b("action"), "body": list(body)}


DRAW = b("draw")
GROW = b("counters", n=1, on="t_self")


@dataclass
class Row:
    cr: str  # "702.9" / "701.22" / "207.2c"
    name: str  # as the CR names it
    kind: str  # "keyword" (702), "action" (701), "word" (207.2c)
    abilities: list[dict[str, Any]] | None = None  # the taught entry's abilities (None: not teachable)
    param: bool = False  # a keyword / action with a number ("Afflict N")
    partial: str = ""  # what the entry leaves out
    why: str = ""  # why there is no entry: the missing piece
    status: str = ""  # "primitive" / "piece" when it isn't rebuilt (see the module docstring)
    pieces: tuple[str, ...] = field(default=())  # for "piece": the pieces that are the mechanic

    @property
    def made_up(self) -> str:
        """The made-up name it is taught under ("Neoprowess", "neoconnive")."""
        name = self.name.lower().replace("cycling", "cycler").replace("walk", "stride").replace("4", "four").replace("8", "eight")
        letters = re.sub(r"[^a-z]", "", name)[:20]  # ("Neocycling" would read as a typecycling, "Neolandwalk" as a landwalk)
        return f"neo{letters}" if self.kind == "action" else f"Neo{letters}"

    def entry(self) -> dict[str, Any] | None:
        if self.abilities is None:
            return None
        kind = "action" if self.kind == "action" else "keyword"
        return {"kind": kind, "name": self.made_up, "param": self.param, "reminder": "", "abilities": self.abilities}


P = "primitive"
PRIM = "a rules primitive: no Oracle sentence spells it out (a taught keyword can grant it with \"It has a keyword\")"
DECK = "a deckbuilding rule, not an ability of play"


def K(cr: str, name: str, *abilities: dict[str, Any], **kw: Any) -> Row:  # noqa: N802
    return Row(cr, name, "keyword", list(abilities) if abilities else None, **kw)


def V(cr: str, name: str, *abilities: dict[str, Any], **kw: Any) -> Row:  # noqa: N802
    return Row(cr, name, "action", list(abilities) if abilities else None, **kw)


def W(name: str, *abilities: dict[str, Any], **kw: Any) -> Row:  # noqa: N802
    return Row("207.2c", name, "word", list(abilities) if abilities else None, **kw)


def piece(cr: str, name: str, *ids: str, kind: str = "action") -> Row:
    return Row(cr, name, kind, None, status="piece", pieces=ids)


# ---------------------------------------------------------------------------------------------------------- 701: keyword actions
ACTIONS: list[Row] = [
    V("701.2", "Activate", status=P, why="a game action (activating an ability), not something a card does to an object"),
    V("701.3", "Attach", why="no piece attaches an Aura or Equipment"),
    V("701.4", "Behold", why="no piece reveals a card of a quality from your hand or chooses a permanent of it"),
    V("701.5", "Cast", why="no piece casts a card (\"you may cast …\")"),
    piece("701.6", "Counter", "counter_spell", "counter_unless", "counter_unless_life"),
    piece("701.7", "Create", "token", "creature_token"),
    piece("701.8", "Destroy", "destroy"),
    piece("701.9", "Discard", "discard", "opp_discard", "cost_discard"),
    V("701.10", "Double", why="no piece doubles a number (power, counters, life)"),
    V("701.11", "Triple", why="no piece triples a number"),
    V("701.12", "Exchange", why="no piece exchanges control, life totals or zones"),
    piece("701.13", "Exile", "exile", "cost_exile_gy"),
    V("701.14", "Fight", why="no piece makes two creatures fight"),
    V("701.15", "Goad", why="no piece says \"attacks each combat if able and attacks a player other than you\" of another creature"),
    V("701.16", "Investigate", X(b("token", n=1, kind="tok_clue"))),
    piece("701.17", "Mill", "mill", "player_mills"),
    V("701.18", "Play", status=P, why="a game action (playing a land or casting a spell)"),
    V("701.19", "Regenerate", why="no piece makes a regeneration shield (\"the next time it would be destroyed this turn …\")"),
    V("701.20", "Reveal", why="no piece reveals on its own (only as part of Search your library)"),
    piece("701.21", "Sacrifice", "sac_self", "opp_sacrifice", "cost_sac", "cost_sac_self"),
    piece("701.22", "Scry", "scry"),
    piece("701.23", "Search", "search", "search_land"),
    V("701.24", "Shuffle", why="no piece shuffles on its own (only as part of Search your library)"),
    piece("701.25", "Surveil", "surveil"),
    piece("701.26", "Tap and Untap", "tap", "untap"),
    V("701.27", "Transform", why="double-faced cards: no piece turns a permanent over"),
    V("701.28", "Convert", why="double-faced cards: no piece turns a permanent over"),
    V("701.29", "Fateseal", why="no piece looks at an opponent's library"),
    V("701.30", "Clash", why="no piece reveals both players' top cards and compares mana values"),
    V("701.31", "Planeswalk", status=P, why="Planechase: a game action of the planar deck"),
    V("701.32", "Set in Motion", status=P, why="Archenemy: a game action of the scheme deck"),
    V("701.33", "Abandon", status=P, why="Archenemy: a game action of the scheme deck"),
    piece("701.34", "Proliferate", "proliferate"),
    V("701.35", "Detain", why="no piece says \"can't attack or block and its activated abilities can't be activated\" of a target"),
    V("701.36", "Populate", why="no piece copies a token"),
    V("701.37", "Monstrosity", X(b("counters", n="N", on="t_self")), param=True,
      partial="no \"if it isn't monstrous\" / \"it becomes monstrous\" designation: it can grow again"),
    V("701.38", "Vote", why="no piece asks each player to vote"),
    V("701.39", "Bolster", why="no piece chooses \"the creature with the least toughness among creatures you control\""),
    V("701.40", "Manifest", why="no piece puts a card onto the battlefield face down"),
    V("701.41", "Support", why="no piece puts counters on \"each of up to N other target creatures\""),
    V("701.42", "Meld", why="meld pairs: no piece exiles two permanents and melds them"),
    V("701.43", "Exert", why="no piece exerts (\"it won't untap during your next untap step\")"),
    V("701.44", "Explore", why="no piece reveals the top card and branches on whether it's a land"),
    V("701.45", "Assemble", status=P, why="Contraptions: a game action of the contraption deck"),
    V("701.46", "Adapt", X(b("counters", n="N", on="t_self")), param=True,
      partial="an action takes no If piece: \"if it has no +1/+1 counters on it\" is left out"),
    V("701.47", "Amass", why="no piece makes an Army token or grows the one you have"),
    V("701.48", "Learn", why="no piece reaches outside the game (Lesson cards)"),
    V("701.49", "Venture into the Dungeon", why="no piece ventures (dungeon cards)"),
    V("701.50", "Connive", X(DRAW, b("then"), b("discard")),
      partial="the +1/+1 counter for a discarded nonland card is left out (no If piece reads what was discarded)"),
    V("701.51", "Open an Attraction", status=P, why="Attractions: a game action of the attraction deck"),
    V("701.52", "Roll to Visit Your Attractions", status=P, why="Attractions: a game action of the attraction deck"),
    V("701.53", "Incubate", why="no piece makes an Incubator token with counters"),
    V("701.54", "The Ring Tempts You", why="no piece chooses a Ring-bearer or grows the Ring's emblem"),
    V("701.55", "Face a Villainous Choice", why="no piece offers an opponent a choice of two effects"),
    V("701.56", "Time Travel", why="no piece adds or removes time counters"),
    V("701.57", "Discover", why="no piece exiles cards until a nonland card with mana value N or less and casts it"),
    V("701.58", "Cloak", why="no piece puts a card onto the battlefield face down"),
    V("701.59", "Collect Evidence", why="no piece exiles cards with a total mana value from your graveyard"),
    V("701.60", "Suspect", why="no piece gives a lasting \"menace and can't block\" designation"),
    V("701.61", "Forage", why="no piece offers \"exile three cards from your graveyard or sacrifice a Food\""),
    V("701.62", "Manifest Dread", why="no piece puts a card onto the battlefield face down"),
    V("701.63", "Endure", X(b("counters", n="N", on="t_self")), param=True,
      partial="the other choice, an N/N white Spirit token, is left out (no piece makes a token of size N/N)"),
    V("701.64", "Harness", why="no piece harnesses (an Infinity designation)"),
    V("701.65", "Airbend", why="no piece exiles a permanent and lets its owner cast it for {2}"),
    V("701.66", "Earthbend", why="no piece turns a land into a creature with counters"),
    V("701.67", "Waterbend", why="no cost piece taps artifacts and creatures to pay generic mana"),
    V("701.68", "Blight", why="the counters piece puts +1/+1 counters only; no -1/-1 counters on a creature you control"),
    V("701.69", "Heal", why="no piece removes damage already marked on a permanent"),
    V("701.70", "Recruit", X(DRAW, b("then"), b("discard")),
      partial="the 1/1 Human Soldier for a discarded nonland card is left out (no If piece reads what was discarded)"),
    V("701.71", "Empower Jace", why="no piece makes a planeswalker token"),
]

# ---------------------------------------------------------------------------------------------------------- 702: keyword abilities
KEYWORDS: list[Row] = [
    K("702.2", "Deathtouch", status=P, why=PRIM),
    K("702.3", "Defender", S("combat_rule", rule="cr_cant_attack")),
    K("702.4", "Double Strike", status=P, why=PRIM),
    K("702.5", "Enchant", why="no piece makes an Aura or says what it may enchant"),
    K("702.6", "Equip", why="no piece attaches an Equipment"),
    K("702.7", "First Strike", status=P, why=PRIM),
    K("702.8", "Flash", status=P, why=PRIM),
    K("702.9", "Flying", S("evasion", who="ev_flying_reach"),
      partial="the attacking half only: a creature with it can't block a flier the way a flier can"),
    K("702.10", "Haste", status=P, why=PRIM),
    K("702.11", "Hexproof", S("untargetable")),
    K("702.12", "Indestructible", status=P, why=PRIM),
    K("702.13", "Intimidate", why="\"except by artifact creatures and/or creatures that share a color with it\" doesn't read yet"),
    K("702.14", "Landwalk", S("landwalk", land="land_island")),
    K("702.15", "Lifelink", status=P, why=PRIM),
    K("702.16", "Protection", why="no piece says \"protection from a quality\" (damage, enchanting, blocking and targeting at once)"),
    K("702.17", "Reach", status=P, why=PRIM),
    K("702.18", "Shroud", S("untargetable"), partial="only opponents can't target it (\"can't be the target of spells or abilities\" doesn't read yet)"),
    K("702.19", "Trample", status=P, why=PRIM),
    K("702.20", "Vigilance", status=P, why=PRIM),
    K("702.21", "Ward", T("targeted", b("counter_unless", mana="{N}")), param=True),
    K("702.22", "Banding", status=P, why=PRIM),
    K("702.23", "Rampage", T("becomes_blocked", b("pump", who="t_self", p="N", t="N", dur="dur_eot")), param=True,
      partial="+N/+N once, not for each creature blocking it beyond the first"),
    K("702.24", "Cumulative Upkeep", why="no piece puts age counters and asks for the cost once per counter"),
    K("702.25", "Flanking", why="no piece names \"the blocking creature\" or a creature without the keyword"),
    K("702.26", "Phasing", status=P, why=PRIM),
    K("702.27", "Buyback", why="no piece returns a spell to its owner's hand as it resolves"),
    K("702.28", "Shadow", why="it names itself (\"can be blocked only by creatures with shadow\"): a made-up keyword can't be named in a piece"),
    K("702.29", "Cycling", A(b("cost_mana", mana="{N}"), b("cost_discard_self"), DRAW), param=True),
    K("702.30", "Echo", T("upkeep", b("sac_unless_mana", mana="{N}")), param=True,
      partial="asks every upkeep, not only the first after it came under your control"),
    K("702.31", "Horsemanship", why="it names itself (\"can't be blocked except by creatures with horsemanship\")"),
    K("702.32", "Fading", why="no piece removes fade counters (\"If you can't, sacrifice it\")"),
    piece("702.33", "Kicker", "kicker", kind="keyword"),
    piece("702.34", "Flashback", "flashback", kind="keyword"),
    K("702.35", "Madness", why="no piece casts a card as it is discarded"),
    K("702.36", "Fear", S("evasion", who="ev_fear")),
    K("702.37", "Morph", why="no piece casts a card face down"),
    K("702.38", "Amplify", why="no piece reveals cards from your hand as it enters"),
    K("702.39", "Provoke", why="no piece makes another creature block"),
    K("702.40", "Storm", why="no piece copies a spell for each spell cast before it"),
    K("702.41", "Affinity", S("self_discount", n=1, why="why_each_artifact")),
    K("702.42", "Entwine", why="modal spells: no piece makes modes"),
    K("702.43", "Modular", why="no piece moves counters from a dying creature"),
    K("702.44", "Sunburst", why="no piece counts the colors of mana spent"),
    K("702.45", "Bushido", T("blocks_or_blocked", b("pump", who="t_self", p="N", t="N", dur="dur_eot")), param=True),
    K("702.46", "Soulshift", why="Return from your graveyard can't ask for \"a Spirit card with mana value N or less\""),
    K("702.47", "Splice", why="no piece adds one spell's text to another"),
    K("702.48", "Offering", why="no piece sacrifices a creature type to cast a spell for less"),
    K("702.49", "Ninjutsu", why="no piece returns an unblocked attacker to put a card onto the battlefield"),
    K("702.50", "Epic", why="no piece copies a spell each upkeep or stops you casting spells"),
    K("702.51", "Convoke", why="no cost piece taps creatures to pay mana"),
    K("702.52", "Dredge", why="no piece replaces a draw"),
    K("702.53", "Transmute", why="Search your library can't ask for \"the same mana value\""),
    K("702.54", "Bloodthirst", why="Enters with +1/+1 counters takes no If piece (\"if an opponent was dealt damage this turn\")"),
    K("702.55", "Haunt", why="no piece exiles a card haunting a creature"),
    K("702.56", "Replicate", why="no piece copies a spell for each time a cost was paid"),
    K("702.57", "Forecast", why="no limit piece reads \"activate only during your upkeep\" from your hand"),
    K("702.58", "Graft", why="no piece moves counters between creatures"),
    K("702.59", "Recover", why="no piece triggers from your graveyard"),
    K("702.60", "Ripple", why="no piece reveals cards and casts ones with the same name"),
    K("702.61", "Split Second", status=P, why=PRIM),
    K("702.62", "Suspend", why="no piece exiles a card with time counters"),
    K("702.63", "Vanishing", why="no piece removes time counters (\"when the last is removed, sacrifice it\")"),
    K("702.64", "Absorb", why="Prevent damage to it prevents all of it, not N"),
    K("702.65", "Aura Swap", why="no piece exchanges an Aura with one in your hand"),
    K("702.66", "Delve", why="no cost piece exiles cards from your graveyard to pay generic mana"),
    K("702.67", "Fortify", why="no piece attaches a Fortification"),
    K("702.68", "Frenzy", why="no When piece reads \"attacks and isn't blocked\""),
    K("702.69", "Gravestorm", why="no piece copies a spell for each permanent put into a graveyard this turn"),
    K("702.70", "Poisonous", why="no piece gives poison counters"),
    K("702.71", "Transfigure", why="Search your library can't ask for \"the same mana value\""),
    K("702.72", "Champion", why="no piece exiles a creature until this leaves the battlefield"),
    K("702.73", "Changeling", status=P, why=PRIM),
    K("702.74", "Evoke", S("alt_cost", when="ac_always", mana="{N}"), param=True,
      partial="the alternative cost only: \"when it enters, if its evoke cost was paid, sacrifice it\" has no If piece"),
    K("702.75", "Hideaway", why="no piece exiles a card face down to play later"),
    K("702.76", "Prowl", why="no condition reads \"a creature of the same type dealt combat damage this turn\""),
    K("702.77", "Reinforce", why="no piece puts counters on a creature from your hand"),
    K("702.78", "Conspire", why="no piece copies a spell for tapping creatures"),
    K("702.79", "Persist", T("dies", b("if_no_counters", kind="cnt_m1"), b("return_dead", to="rd_bf_m1"))),
    K("702.80", "Wither", status=P, why=PRIM),
    K("702.81", "Retrace", S("gy_retrace")),
    K("702.82", "Devour", why="no piece sacrifices any number of creatures as it enters"),
    K("702.83", "Exalted", T("attacks_alone", b("exalt", p=1, t=1))),
    K("702.84", "Unearth", why="returning from the graveyard reads, but not \"exile it at the beginning of the next end step or if it would leave\""),
    K("702.85", "Cascade", why="no piece exiles cards until a cheaper nonland card and casts it"),
    K("702.86", "Annihilator", why="no piece makes the defending player sacrifice N permanents"),
    K("702.87", "Level Up", why="level up cards: no piece adds level counters with their own abilities"),
    K("702.88", "Rebound", why="no piece exiles a spell as it resolves to cast it next upkeep"),
    K("702.89", "Umbra Armor", why="no piece replaces the enchanted creature's destruction"),
    K("702.90", "Infect", status=P, why=PRIM),
    K("702.91", "Battle Cry", T("attacks", b("rally_attackers", p=1, t=0))),
    K("702.92", "Living Weapon", why="no piece attaches an Equipment to a token"),
    K("702.93", "Undying", T("dies", b("if_no_counters", kind="cnt_p1"), b("return_dead", to="rd_bf_p1"))),
    K("702.94", "Miracle", why="no piece reveals a card as you draw it"),
    K("702.95", "Soulbond", why="no piece pairs two creatures"),
    K("702.96", "Overload", why="no piece changes \"target\" to \"each\""),
    K("702.97", "Scavenge", A(b("cost_mana", mana="{N}"), b("cost_exile_self_gy"), b("counters", n=1, on="t_creature"), b("limit_sorcery")),
      param=True, partial="one +1/+1 counter, not \"a number equal to its power\""),
    K("702.98", "Unleash", why="no piece offers \"you may have it enter with a +1/+1 counter\" or \"can't block as long as it has one\""),
    K("702.99", "Cipher", why="no piece encodes a spell on a creature"),
    K("702.100", "Evolve", why="no If piece compares the entering creature's power and toughness with this one's"),
    K("702.101", "Extort", T("cast", {"id": "pay_mana", "values": {"mana": "{W/B}"}, "body": [b("drain", n=1)]}, spell="spell_any")),
    K("702.102", "Fuse", why="split cards: no piece casts both halves"),
    K("702.103", "Bestow", why="no piece casts a creature as an Aura"),
    K("702.104", "Tribute", why="no piece lets an opponent choose"),
    K("702.105", "Dethrone", why="no When piece reads \"attacks the player with the most life\""),
    K("702.106", "Hidden Agenda", status=P, why="Conspiracy draft: a card face down in the command zone"),
    K("702.107", "Outlast", A(b("cost_mana", mana="{N}"), b("cost_tap"), GROW, b("limit_sorcery")), param=True),
    K("702.108", "Prowess", T("cast", b("pump", who="t_self", p=1, t=1, dur="dur_eot"), spell="spell_noncreature")),
    K("702.109", "Dash", why="\"if you do, it gains haste … return it to its owner's hand\" after an alternative cost doesn't read yet"),
    K("702.110", "Exploit", T("etb", {"id": "pay_sac", "values": {"what": "sac_another_creature"}, "body": [DRAW]}),
      partial="the payoff goes in the same ability (\"if you do\"), not a separate \"when it exploits a creature\""),
    K("702.111", "Menace", S("evasion", who="ev_two")),
    K("702.112", "Renown", T("combat_damage", b("counters", n="N", on="t_self")), param=True,
      partial="every time: no \"if it isn't renowned\" designation"),
    K("702.113", "Awaken", why="no piece turns a land into a creature"),
    K("702.114", "Devoid", status=P, why=PRIM),
    K("702.115", "Ingest", why="no piece exiles the top card of a player's library"),
    K("702.116", "Myriad", why="no piece copies an attacker for each other opponent"),
    K("702.117", "Surge", S("alt_cost", when="ac_another", mana="{N}"), param=True),
    K("702.118", "Skulk", S("evasion_by", who="eb_greater")),
    K("702.119", "Emerge", why="no cost piece sacrifices a creature to reduce the cost by its mana value"),
    K("702.120", "Escalate", why="modal spells: no piece makes modes"),
    K("702.121", "Melee", why="no piece counts the opponents you attacked"),
    K("702.122", "Crew", why="no piece turns a Vehicle into a creature"),
    K("702.123", "Fabricate", T("etb", b("counters", n="N", on="t_self")), param=True,
      partial="the other choice, N 1/1 Servo artifact tokens, is left out (no piece offers a choice of effects)"),
    K("702.124", "Partner", status=P, why=DECK),
    K("702.125", "Undaunted", S("self_discount", n=1, why="why_each_opponent")),
    K("702.126", "Improvise", why="no cost piece taps artifacts to pay generic mana"),
    K("702.127", "Aftermath", why="split cards: no piece casts a half from the graveyard"),
    K("702.128", "Embalm", why="no piece makes a token copy of a card"),
    K("702.129", "Eternalize", why="no piece makes a token copy of a card"),
    K("702.130", "Afflict", T("becomes_blocked", b("lose", who="t_each_opponent", n="N")), param=True,
      partial="\"each opponent\" for \"defending player\" (the same in a two-player game)"),
    K("702.131", "Ascend", why="no piece gives the city's blessing"),
    K("702.132", "Assist", why="no piece lets another player pay"),
    K("702.133", "Jump-Start", why="no piece casts an instant or sorcery from the graveyard (the graveyard-casting pieces read on permanents)"),
    K("702.134", "Mentor", why="no piece targets \"an attacking creature with lesser power\""),
    K("702.135", "Afterlife", T("dies", b("creature_token", n="N", p=1, t=1, color="color_white_black", type="type_spirit", kw="tokkw_flying")),
      param=True),
    K("702.136", "Riot", why="no piece offers a choice of a counter or haste"),
    K("702.137", "Spectacle", S("alt_cost", when="ac_opp_lost", mana="{N}"), param=True),
    K("702.138", "Escape", S("gy_cast_exile", mana="{N}", n=3), param=True,
      partial="a permanent card: an instant's or sorcery's escape from the graveyard doesn't read"),
    K("702.139", "Companion", status=P, why=DECK),
    K("702.140", "Mutate", why="no piece merges a creature spell with a creature"),
    K("702.141", "Encore", why="no piece makes token copies for each opponent"),
    K("702.142", "Boast", A(b("cost_mana", mana="{N}"), DRAW, b("limit_attacked")), param=True),
    K("702.143", "Foretell", why="no piece exiles a card from your hand face down to cast later"),
    K("702.144", "Demonstrate", why="no piece copies a spell for an opponent"),
    K("702.145", "Daybound and Nightbound", why="no piece turns day and night"),
    K("702.146", "Disturb", why="no piece casts a card transformed"),
    K("702.147", "Decayed", S("cant_block"), partial="\"when it attacks, sacrifice it at end of combat\" is left out (no delayed sacrifice)"),
    K("702.148", "Cleave", why="no piece removes the words in square brackets"),
    K("702.149", "Training", why="no When piece reads \"attacks with another creature with greater power\""),
    K("702.150", "Compleated", why="no piece reads Phyrexian mana paid with life"),
    K("702.151", "Reconfigure", why="no piece attaches an Equipment creature"),
    K("702.152", "Blitz", why="\"it gains haste and 'When it dies, draw a card'; sacrifice it at end step\" after an alternative cost doesn't read"),
    K("702.153", "Casualty", why="no piece copies a spell for a sacrifice"),
    K("702.154", "Enlist", why="no piece taps a creature to add its power"),
    K("702.155", "Read Ahead", why="Sagas: no piece chooses a chapter"),
    K("702.156", "Ravenous", why="no piece reads X"),
    K("702.157", "Squad", why="no piece makes token copies for each time a cost was paid"),
    K("702.158", "Space Sculptor", why="no piece makes sectors"),
    K("702.159", "Visit", status=P, why="Attractions: a game action of the attraction deck"),
    K("702.160", "Prototype", why="no piece casts a card with other characteristics"),
    K("702.161", "Living Metal", why="no piece makes a Vehicle a creature"),
    K("702.162", "More Than Meets the Eye", why="no piece casts a card transformed"),
    K("702.163", "For Mirrodin!", why="no piece attaches an Equipment to a token"),
    K("702.164", "Toxic", why="no piece gives poison counters"),
    K("702.165", "Backup", why="no piece gives another creature this one's abilities"),
    K("702.166", "Bargain", why="no piece offers an optional sacrifice as you cast it (and \"if it was bargained\")"),
    K("702.167", "Craft", why="no piece exiles materials to transform"),
    K("702.168", "Disguise", why="no piece casts a card face down"),
    K("702.169", "Solved", why="Cases: no piece solves a Case"),
    K("702.170", "Plot", why="no piece exiles a card to cast later for free"),
    K("702.171", "Saddle", why="no piece taps creatures to saddle a Mount"),
    K("702.172", "Spree", why="modal spells: no piece makes modes"),
    K("702.173", "Freerunning", why="no condition reads \"an Assassin or a commander dealt combat damage this turn\""),
    K("702.174", "Gift", why="no piece lets an opponent receive a gift"),
    K("702.175", "Offspring", why="no piece makes a 1/1 token copy"),
    K("702.176", "Impending", why="no piece casts a card as a non-creature with time counters"),
    K("702.177", "Exhaust", A(b("cost_mana", mana="{N}"), DRAW, b("limit_once")), param=True,
      partial="once each turn, not once ever"),
    K("702.178", "Max Speed", why="no condition reads your speed"),
    K("702.179", "Start Your Engines!", why="no piece gives speed"),
    K("702.180", "Harmonize", why="no cost piece taps a creature to reduce the cost by its power"),
    K("702.181", "Mobilize", why="no piece makes tokens tapped and attacking"),
    K("702.182", "Job Select", why="no piece attaches an Equipment to a token"),
    K("702.183", "Tiered", why="modal spells: no piece makes modes"),
    K("702.184", "Station", why="no piece puts charge counters equal to a tapped creature's power"),
    K("702.185", "Warp", S("alt_cost", when="ac_always", mana="{N}"), param=True,
      partial="the alternative cost only: \"exile it at the next end step, and you may cast it later from exile\" is left out"),
    K("702.186", "∞ (Infinity)", why="Infinity cards: no piece reads the harnessed designation"),
    K("702.187", "Mayhem", why="no piece casts a card from the graveyard \"if you discarded it this turn\""),
    K("702.188", "Web-slinging", why="no cost piece returns a tapped creature to your hand"),
    K("702.189", "Firebending", T("attacks", b("add_mana", mana="{R}")),
      partial="one {R} (an Add mana piece takes no N), and it empties as steps end instead of lasting until end of combat"),
    K("702.190", "Sneak", why="no piece casts a spell during the declare blockers step for returning an unblocked creature"),
    K("702.191", "Increment", why="no If piece compares the mana spent on a spell with this creature's power or toughness"),
    K("702.192", "Paradigm", why="no piece copies a spell in exile each turn"),
    K("702.193", "Power-up", why="no cost piece is reduced by the permanent's mana cost"),
    K("702.194", "Teamwork", why="no cost piece taps creatures with a total power"),
    K("702.195", "Storied", why="no piece gives an enduring story"),
]

# ------------------------------------------------------------------------------------------------------- 207.2c: ability words
_LAND = T("landfall", DRAW)
WORDS: list[Row] = [
    W("adamant", why="no If piece reads the colors of mana spent"),
    W("addendum", why="no If piece reads \"if you cast it during your main phase\""),
    W("alliance", T("ally_enters", GROW)),
    W("battalion", why="no When piece reads \"attacks with at least two other creatures\""),
    W("bloodrush", why="no cost piece discards this card to pump an attacker"),
    W("celebration", why="no If piece reads \"two or more nonland permanents entered this turn\""),
    W("channel", A(b("cost_mana", mana="{N}"), b("cost_discard_self"), DRAW), param=True),
    W("chroma", why="no piece counts mana symbols"),
    W("cohort", why="no cost piece taps another untapped Ally"),
    W("constellation", why="no When piece reads \"an enchantment you control enters\""),
    W("converge", why="no piece counts the colors of mana spent"),
    W("council's dilemma", why="no piece asks each player to vote"),
    W("coven", why="no If piece reads \"three or more different powers\""),
    W("delirium", T("etb", b("if_state", what="st_delirium"), DRAW)),
    W("descend 4", why="no If piece reads \"four or more permanent cards in your graveyard\""),
    W("descend 8", why="no If piece reads \"eight or more permanent cards in your graveyard\""),
    W("disappear", T("end_step", b("if_this_turn", what="tt_left"), DRAW)),
    W("domain", why="no piece counts basic land types"),
    W("eerie", why="no When piece reads \"an enchantment you control enters or you unlock a Room\""),
    W("eminence", why="no piece works from the command zone"),
    W("enrage", T("dealt_damage", DRAW)),
    W("fateful hour", why="the life If piece reads \"N or more\", not \"5 or less\""),
    W("fathomless descent", why="no piece counts permanent cards in your graveyard"),
    W("ferocious", T("etb", b("if_state", what="st_power4"), DRAW)),
    W("flurry", why="no When piece reads \"you cast your second spell each turn\""),
    W("formidable", why="no If piece reads \"creatures with total power 8 or greater\""),
    W("grandeur", why="no cost piece discards another card with this name"),
    W("hellbent", T("etb", b("if_state", what="st_no_hand"), DRAW)),
    W("heroic", why="no When piece reads \"becomes the target of a spell you control\""),
    W("imprint", why="no piece exiles a card linked to this one"),
    W("infusion", T("etb", b("if_this_turn", what="tt_gained"), DRAW)),
    W("inspired", why="no When piece reads \"becomes untapped\""),
    W("join forces", why="no piece lets each player pay"),
    W("kinship", why="no piece reveals the top card for a shared creature type"),
    W("landfall", _LAND),
    W("lieutenant", T("attacks", b("if_state", what="st_commander"), DRAW)),
    W("magecraft", T("cast", DRAW, spell="spell_instant_sorcery"), partial="casting only: \"or copy\" is left out"),
    W("metalcraft", S("self_pt", b("if_control", n=3, what="count_artifacts"), p=2, t=2)),
    W("morbid", T("end_step", b("if_this_turn", what="tt_died"), DRAW)),
    W("opus", why="no If piece reads the mana spent on a spell"),
    W("pack tactics", why="no If piece reads \"attacking creatures with total power 6 or greater\""),
    W("paradox", why="no If piece reads \"cast from anywhere other than your hand\""),
    W("parley", why="no piece reveals each player's top card"),
    W("radiance", why="no piece affects \"each creature that shares a color with it\""),
    W("raid", T("end_step", b("if_this_turn", what="tt_attacked"), DRAW)),
    W("rally", T("ally_enters", b("pump", who="t_creatures_yours", p=1, t=1, dur="dur_eot")),
      partial="\"another creature\" for \"this or another Ally\" (no creature-type filter)"),
    W("renew", A(b("cost_mana", mana="{N}"), b("cost_exile_self_gy"), b("counters", n=1, on="t_creature"), b("limit_sorcery")), param=True),
    W("repartee", why="no When piece reads \"cast an instant or sorcery spell that targets a creature\""),
    W("revolt", T("end_step", b("if_this_turn", what="tt_left"), DRAW)),
    W("secret council", why="no piece asks each player to vote secretly"),
    W("spell mastery", why="no If piece reads \"two or more instant and/or sorcery cards in your graveyard\""),
    W("strive", why="no piece makes a spell cost more for each extra target"),
    W("survival", why="no When piece reads \"your second main phase, if this creature is tapped\""),
    W("sweep", why="no piece returns lands of a type to your hand"),
    W("tempting offer", why="no piece lets each opponent copy the effect"),
    W("threshold", S("self_pt", b("if_graveyard", n=7), p=1, t=1)),
    W("undergrowth", why="no piece counts creature cards in your graveyard"),
    W("valiant", why="no When piece reads \"becomes the target of a spell or ability you control for the first time each turn\""),
    W("vivid", why="no piece counts colors among permanents you control"),
    W("void", why="no If piece reads \"a nonland permanent left the battlefield or a spell was warped this turn\""),
    W("will of the council", why="no piece asks each player to vote"),
]

ROWS: list[Row] = [*ACTIONS, *KEYWORDS, *WORDS]

ICONS = {"full": "✅", "piece": "🧩", "partial": "⚠️", "none": "❌", "primitive": "❌"}
PLAYED_MARK = "▶"  # (after the icon: played at the table side by side with the native mechanic)


def _uses(abilities: list[dict[str, Any]]) -> tuple[set[str], set[tuple[str, str]]]:
    ids: set[str] = set()
    opts: set[tuple[str, str]] = set()

    def walk(block: dict[str, Any]) -> None:
        ids.add(block["id"])
        for v in (block.get("values") or {}).values():
            if isinstance(v, str):
                opts.add((block["id"], v))
        for kid in block.get("body") or []:
            walk(kid)

    for a in abilities:
        walk(a["hat"])
        for blk in a["body"]:
            walk(blk)
    return ids, opts


def needs_new(row: Row) -> list[str]:
    """The pieces (and piece settings) the sweep added that this row's entry needs ([]: it was teachable before)."""
    if row.status == "piece":  # (a mechanic that is several pieces was one before if any of them was there)
        return sorted(row.pieces) if set(row.pieces) <= NEW_PIECES else []
    if row.abilities is None:
        return []
    ids, opts = _uses(row.abilities)
    return sorted((ids & NEW_PIECES) | {f"{p}:{o}" for p, o in opts & NEW_OPTIONS})


def status(row: Row, *, before: bool = False) -> str:
    """"full" / "piece" / "partial" / "none" / "primitive" (before the sweep: what the old pieces could say)."""
    if row.status == "primitive":
        return "primitive"
    if before and needs_new(row):
        return "none"
    if row.status == "piece":
        return "piece"
    if row.abilities is None:
        return "none"
    return "partial" if row.partial else "full"


def counts(*, before: bool = False, rows: list[Row] | None = None) -> dict[str, int]:
    out = {k: 0 for k in ICONS}
    for r in ROWS if rows is None else rows:
        out[status(r, before=before)] += 1
    return out


# ------------------------------------------------------------------------------------------------------------------- the doc
DOC = "../docs/TEACH_FYODOR_COVERAGE.md"


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def doc() -> str:
    """docs/TEACH_FYODOR_COVERAGE.md, from the rows (``python -m tests.teach_coverage``)."""
    from app.rules import taught
    from app.rules.taught_vocab import PIECE
    from tests.test_teach_playtests import PLAYED

    played = frozenset(PLAYED)
    after, before = counts(), counts(before=True)
    total = len(ROWS)
    n_played = sum(1 for r in ROWS if r.name in played)
    lines = [
        "# Teach Fyodor — what the block builder can say",
        "",
        "Every keyword action (CR 701), keyword ability (CR 702) and ability word (CR 207.2c), rebuilt from its reminder text under a",
        "made-up name (\"Neoprowess\", \"neoconnive\") with nothing but the builder's pieces. Generated by `python -m tests.teach_coverage`",
        "from `backend/tests/teach_coverage.py`; `tests/test_teach_coverage.py` re-checks every entry with the engine (`taught.check`: every",
        "line reads FULL) and that this file is current. Play tests: `tests/test_teach_playtests.py` plays a card with the taught name and a",
        "card with the native keyword side by side and compares the table (with a replay and a save/load).",
        "",
        "**The criterion.** A mechanic counts only if its pieces don't include the mechanic itself: \"It has flying\" doesn't teach flying, \"it",
        "can't be blocked except by creatures with flying or reach\" does (the attacking half). So:",
        "",
        "* ✅ teachable (every line reads FULL) — ⚠️ partial (reads FULL, leaves out what the note says) — ▶ after an icon: play-tested",
        "* 🧩 a piece: the mechanic is itself one of the pieces (the verbs, and the Kicker and Flashback pieces, whose words are the engine's",
        "  own keyword for an optional additional cost and for \"exile it as it leaves the stack\"; a new mechanic built on them is the",
        "  player's own, e.g. \"Rekindle N\" = Flashback {N} plus a When piece)",
        "* ❌ not teachable (the missing piece) — ❌ primitive: a rules primitive no Oracle sentence spells out (deathtouch, haste …) or a",
        "  game action of a supplemental format; a taught keyword can still *grant* the evergreen ones",
        "",
        "## Counts",
        "",
        f"{total} mechanics: {len(ACTIONS)} keyword actions, {len(KEYWORDS)} keyword abilities, {len(WORDS)} ability words.",
        "",
        "| | Before the sweep | After |",
        "|---|---:|---:|",
        f"| ✅ teachable (FULL) | {before['full']} | {after['full']} |",
        f"| ⚠️ partial | {before['partial']} | {after['partial']} |",
        f"| 🧩 a piece | {before['piece']} | {after['piece']} |",
        f"| ❌ not teachable | {before['none']} | {after['none']} |",
        f"| ❌ primitive / format action | {before['primitive']} | {after['primitive']} |",
        f"| ▶ play-tested (of ✅ ⚠️ 🧩) | — | {n_played} |",
        "",
        "Per section (after): " + "; ".join(
            f"{label} — " + ", ".join(f"{ICONS[k]}{' primitive' if k == 'primitive' else ''} {n}" for k, n in counts(rows=rows).items() if n)
            for label, rows in (("701", ACTIONS), ("702", KEYWORDS), ("207.2c", WORDS))) + ".",
        "",
        "## What the sweep added",
        "",
        "Pieces (each reads FULL in every setting, `tests/test_teach_matrix.py`):",
        "",
    ]
    by_cat: dict[str, list[str]] = {}
    for pid in sorted(NEW_PIECES, key=lambda p: list(PIECE).index(p)):
        by_cat.setdefault(PIECE[pid]["cat"], []).append(f"{PIECE[pid]['label']} (`{pid}`)")
    for cat, labels in by_cat.items():
        lines.append(f"* **{cat.capitalize()}**: " + "; ".join(labels))
    lines += [
        "* Settings: Exile and Return to hand may name the card itself; Create creature tokens may make white and black ones.",
        "* \"hats\": a piece may name the only When pieces it reads under (\"Counter it unless they pay\" under \"Becomes a target\", \"Return",
        "  it\" under \"Dies\"); the backend, the matrix and the page's snap rules all keep to it.",
        "",
        "Still out of reach (the most common missing pieces): modes and choices of effects, face-down cards, copies of spells and tokens,",
        "attaching, poison and -1/-1 counters on a chosen creature, X and \"for each\" amounts in effects, delayed triggers (\"at end of",
        "combat\", \"at the next end step\"), the defending player, and conditions inside an action.",
        "",
    ]
    for title, rows in (("Keyword actions (CR 701)", ACTIONS), ("Keyword abilities (CR 702)", KEYWORDS), ("Ability words (CR 207.2c)", WORDS)):
        lines += [f"## {title}", "", "| CR | Mechanic | Before | After | Taught as | Note |", "|---|---|:-:|:-:|---|---|"]
        for r in rows:
            st, was = status(r), status(r, before=True)
            entry = r.entry()
            if r.status == "piece":
                said = ", ".join(f"{PIECE[p]['label']}" for p in r.pieces)
            elif entry is not None:
                clean = taught.clean_entry(entry)
                head = (taught.action_phrase(clean, n=2 if r.param else None) if r.kind == "action"
                        else f"{r.made_up}{' 2' if r.param else ''}")
                said = f"{head}: " + (taught.action_sentences(clean, n=2 if r.param else None) + "."
                                       if r.kind == "action" else " ".join(taught.compile_entry(clean, n=2 if r.param else None)))
            else:
                said = ""
            note = r.partial or r.why
            if was == "none" and st != "none" and needs_new(r):
                note = (note + " — " if note else "") + "needed: " + ", ".join(
                    PIECE[n.split(":")[0]]["label"] + (f" ({n.split(':')[1]})" if ":" in n else "") for n in needs_new(r))
            name = r.name if r.kind != "word" else r.name.capitalize()
            mark = PLAYED_MARK if r.name in played else ""
            lines.append(f"| {r.cr} | {_cell(name)} | {ICONS[was]} | {ICONS[st]}{mark} | {_cell(said)} | {_cell(note)} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":  # python -m tests.teach_coverage  (rewrites docs/TEACH_FYODOR_COVERAGE.md)
    from pathlib import Path

    path = (Path(__file__).resolve().parent.parent / DOC).resolve()
    path.write_text(doc(), "utf-8")
    print(f"wrote {path}")
