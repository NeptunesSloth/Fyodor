# Batch34 proposal: qualified relative/attached tutors (15)

Implemented using `qualified_attached_tutors.py` and native search/attachment continuations. Full classification requires canonical successful movement and edge-case verification.
Canonical complete fixtures: `tests/fixtures/qualified_attached_tutor_cards.json`.
Official Scryfall rulings retrieved from card named endpoint followed by each `rulings_uri` (2026-10-20). Relevant constraints are transcribed below.
All fifteen independently confirmed PARTIAL in batch33 inventory.

## Shared implementation
Use one new leaf `qualified_attached_tutors.py`, narrow scripts hook and opt-in native search metadata. Compile typed query descriptors; preserve standard `ref:` namespaces. Resolve relative values once when the instruction starts, from CURRENT derived characteristics or exact event/cost/discard object LKI. Search candidates always use plan.ch (including Grist library CDA, faces, all names). Existing qualified search packets/native Agent, Mindcensor, search bans, reveal/privacy/shuffle, replay and CPS remain authoritative.

Aura could-enchant predicate should reuse attachments.host_problem including enchant restrictions and protection, excluding targeting restrictions. Auratouched's departed source requires the source's final battlefield snapshot, not its graveyard characteristics. Build bounded prospective host probe using exact LKI, never mutate real state or activate its global effects; alternatively add explicit host-characteristics parameter to shared host legality helper. Sovereigns departed host is NOT a findable LKI host (official ruling says shuffle only). Source new-object reentry must not receive old trigger's Aura.

For Equipment instructions order is search -> ENTER -> choose legal controlled creature -> attach -> shuffle. Do NOT reuse pre-entry host_choice, which chooses before entry and is observably wrong. Bind actual entered Equipment object, inject nontarget native legal-host choice continuation after all as-enters choices, preserve equipment unattached if no host or entry redirected. ETB triggers wait until ability finishes. Actual replacement outcomes determine whether attach is attempted, not original selected ID.

## Cards/adapters
1 Light-Paws: event Aura mana value cap and exclude names of ALL current controlled Auras; event was cast predicate; native host self. Illegal attachment remains library.
2 Auratouched Mage: could-enchant current/final-LKI source query; if exact source remains BF, native attached entry; otherwise reveal to hand.
3 Sovereigns of Lost Alara: attacks-alone event; could-enchant event creature; if departed allow search+shuffle but no eligible Aura; attach exact event object.
4 Curse of Misfortunes: current curses attached to enchanted player name exclusion; persist exact enchanted PLAYER through source departure; native player host path.
5 Stonehewer Giant: post-entry non-target Equipment host choice.
6 Quest for Holy Relic: same post-entry adapter; native five quest counters+sacrifice cost; source may be gone before search.
7 Tallowisp: exact enchant creature keyword, excluding enchant creature you control / restricted enchant creature clauses; trigger Spirit OR Arcane native union.
8 Phantom Carriage: flashback OR disturb keyword candidate query; native graveyard destination.
9 Mwonvuli Beast Tracker: creature plus OR of four keywords; native reveal/shuffle/top.
10 Forging Tyrite Sword: fixed name Halvar, God of Battle OR Equipment; Saga chapter native. Preserve named literal under copy/source rename.
11 Wild Pair: current event power+toughness sum or final battlefield LKI; library candidates same actual derived total; cast-from-hand intervening condition, native original-only cast semantics.
12 Evolving Door: sacrificed cost-LKI color count +1, exact color-count query; native exile->shuffle->optional cast immediately PAYING costs. No six-color find for five-colored sacrifice. No permission for later turns or source-OID reuse.
13 Disciple Deceit: native optional nonland discard, bind actual discarded card MV; then equal MV native search/reveal/hand; decline does not search/shuffle.
14 Vivien Monsters Advocate: native delayed next-creature-cast watch, current actual cast face MV incl X -> strictly lesser library MV; copied spell does not trigger; creature need not resolve, source departure irrelevant.
15 Hiveheart Shaman: current controlled land subtype union, basic card land types must have empty intersection; existing unrelated insect activation remains untouched.

## Official ruling constraints
Auratouched: current host characteristics, or last battlefield existence if departed (artifact transformation matters).
Sovereigns: protection affects could-enchant; shroud does not; departed attacker means search permitted but no Aura can enter.
Quest: host chosen only at attachment time, no target; no legal creature leaves Equipment BF unattached.
Stonehewer: same legality/no-host behavior.
Wild Pair: battlefield current PT can differ from printed (Triskelion), response changes count, departed creature final LKI.
Evolving Door: colors as last BF (copy/DFC changes), unrelated color identities acceptable, all costs paid, cast during resolution only.
Curse: exclusion recomputed on each resolution, including previously entered curses.
Vivien: next cast X included; library X=0; tutor occurs before triggering spell resolves.

## Verification gates before FULL claims
All15 actual successful found/moved effects early; mandatory exact selected result asserts (never only empty options assertions). Wrong qualifiers/candidate negatives per adapter. At least cold suspended search, cold post-entry attachment, cold paid cast, source-departure exact-OID, actual copy/renamed source cases. Native Agent/Mindcensor/top4 and search bans remain original pipeline; entry Priest/Cage/prohibition, aura protection/shroud, equipment dynamic as-enters choice, no-host, and replacement redirects. Public/owner/opponent/spectator REST/WS and replay privacy reuse proven native adapters, with new host choice private scope checked. Do not promote if additional unfounded activation/event gap emerges; report bounded missing mechanic rather than fake manual support.

Expected source touches: new leaf +scripts hook; selectors opt-in candidate descriptor OR use local packet match hook; effects._finish_search exact opt-in continuation before/after attachments entry with saved metadata; attachments.host_problem optional explicit host face/LKI only if needed. Coordinate all shared search changes with palantir foreign/same-name family. Steel cost-LKI support is read-only dependency, no cost-core edits planned.

## Implemented and verified

All fifteen canonical cards have successful actual gameplay movement proofs and native replay/JSON checks. Forty focused cases passed, followed by three additional independent REST/WebSocket and actual Cloudshift identity cases (43 unique own cases total).

The Equipment continuation runs after native `attachments.enter` has completed and before the library shuffle. Batterskull enters before the host decision; its Living Weapon trigger waits until the resolving ability finishes. A saved pending attachment choice resumes in a new GameSession. With no legal host, the Equipment remains unattached and the library is still shuffled.

Auratouched Mage's actual Liquimetal Coating -> Unsummon response demonstrates that its final battlefield Artifact characteristic still permits finding Ensoul Artifact, which goes to hand. Actual Cloudshift creates two distinct triggers: the new object's trigger enters its Aura attached; the original departed object's trigger sends its selected Aura to hand. Sovereigns' Cloudshifted attacker is a new object and cannot receive an Aura from the old attack trigger. The native search may still be accepted and fail to find.

Additional proofs cover Light-Paws' cast-only gate and same-name exclusion, Tallowisp's exact enchant-creature restriction and Spirit/Arcane triggers, Wild Pair's current Triskelion counter-modified 4/4 total rather than printed 1/1, creature entry blocked by Grafdigger's Cage, native Agent chooser/exile/permission authority with cold save, original top-four Mindcensor restriction, and protection from white excluding Pacifism while allowing Rancor. Evolving Door's immediate cast actually pays the chosen two-color creature's two mana; it grants no later permission.

Explicit event and sacrificed-cost reference metadata leaves native unbound-reference validation intact. The lesser-MV and discarded-MV forms are accepted only inside their bound compound watch/payment adapters, not as standalone unbound tutor sentences. The Curse's printed subtype words are parsed from the original compound body because generic short-self-name substitution would otherwise turn its own subtype `Curse` into `~`; no global name substitution behavior was weakened.
