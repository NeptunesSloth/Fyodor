# Milestone plan: spectator side activities (not started)

Requested 2026-10-03, for later. Nothing here is built yet.

**Build it only after these are stable:** the elimination/spectator flow (`ELIMINATION_HUB.md`), the
Practice Table, the persistent pod lobby and the core game-night flow (`GAME_NIGHT_FLOW.md`), and the base
spectator, reconnect and privacy systems.

This extends the elimination hub; it is not a second hub. For eliminated players and spectators.

## Build order

1. Watch + PiP Practice Table
2. Build-the-Next-Game Queue
3. Live Reactions / Emotes
4. Damage Calculator Sandbox
5. Prediction Bets with fake points
6. Spectator Points cosmetic progression (Cosmetics Locker)

The first two give the most practical game-night value.

## Hard boundaries (all five features)

Spectator activities must **never**:

- alter the live authoritative match;
- expose hidden information: hands, library identities, private searches, hidden cards, face-down
  identities, secret choices, private payment options, private WebSocket payloads;
- interfere with priority;
- create rules actions in the live game;
- affect the current match's history, or increment the live game's revision.

An eliminated player does not become an omniscient observer. Every activity works from the same
public-information boundary as normal spectating.

**Separate state domains.**

- **Live match:** authoritative, networked, recorded, controlled by the rules engine.
- **Spectator activity:** private/local or separately scoped, disposable, not authoritative, and unable to
  create live actions.

## Spectator hub (after elimination)

Compact, not a dashboard:

```
ELIMINATED
Game continues
[SPECTATE] [PRACTICE TABLE] [DAMAGE SANDBOX] [NEXT GAME]
smaller: Predictions · Reactions · Game Log · Pod Stats
```

Whatever the spectator is doing, a game end shows **PLAYER 3 WINS**, then the normal pod result flow:
**[REMATCH — SAME DECKS] [RETURN TO LOBBY] [VIEW FINAL BOARD]**.

## 1. Watch + PiP Practice Table (strongest activity)

- **Layout:** the Practice Table fills the large area, and the live game sits in a small corner
  Picture-in-Picture showing the actual public live table.
- **PiP controls:** move it, resize it within sensible limits, minimize, restore, and click it to return to
  full spectator mode.
- **Practice Table actions:** shuffle, draw, mulligan, goldfish, play cards, create tokens, add counters,
  reset and test sequences. Its state is completely separate from the live match.
- **Live event notices:** restrained notices for important public events only, such as PLAYER 2
  ELIMINATED, COMMANDER CAST, FINAL TWO PLAYERS, LARGE STACK — 6 OBJECTS and PLAYER 4 WINS. No notice for
  minor actions.
- **[RETURN TO LIVE GAME]** is available at all times. This is critical.

## 2. Build-the-Next-Game Queue

A lightweight next-game preference tied to the persistent lobby; not a second lobby.

- **Choose:** NEXT GAME: KEEP CURRENT DECK, or CHANGE DECK.
- **When changing:** browse saved decks, choose a deck, choose a commander, pick a saved Deck Lab revision,
  or import if the lobby already supports it.
- **Cosmetics where appropriate:** playmat, sleeves or card back, and table seat preference if allowed.
- **Shown as:** `NEXT GAME — Muldrotha, the Gravetide — READY FOR LOBBY`.
- **Never** modify the current lobby or match configuration immediately. On return to lobby, the queued
  selection becomes that player's proposed lobby deck, and they can still change it before readying:
  `NEXT DECK QUEUED — Yuriko, the Tiger's Shadow — [USE THIS DECK] [CHANGE]`.
- **REMATCH — SAME DECKS:** the existing same-deck rematch rules take precedence unless the pod returns to
  lobby. Never silently force a queued deck into a same-deck rematch.

## 3. Live Reactions / Emotes

- **Initial set:** 👍 😂 😮 🔥 💀 👏.
- **Display:** shown briefly near the spectator's seat/player indicator or near the relevant public event.
  Never cover cards, never interrupt player input, no giant particles or screen-wide effects.
- **Controls:** rate limiting, a reaction cooldown, mute spectator reactions, and disable reactions
  entirely.
- **Presentation only:** reactions can't touch game objects.

## 4. Damage Calculator Sandbox

A private, disconnected combat sandbox ("was that attack actually lethal?", "what if they blocked
differently?").

- **Tools:** add attacker/blocker, set power/toughness, first strike, double strike, trample, deathtouch,
  lifelink, indestructible, damage modifiers, commander designation, player life, commander damage.
- **[COPY CURRENT PUBLIC COMBAT]** copies only publicly visible information. It never copies hidden cards,
  unrevealed effects, private decisions, or cards known only through spectator privileges.
- **Informational only:** it doesn't predict unknown interaction and doesn't alter the real match. It is
  labelled **SANDBOX — DOES NOT AFFECT LIVE GAME**.
- **Reuse Fyodor's deterministic combat/rules primitives** (`backend/app/rules/combat.py` damage
  computation, including the 510.1c–d divisions) instead of a second, contradictory rules implementation.

## 5. Prediction Bets (fake points only)

- **Session-only fake points:** no real money, no purchasable points, no cash value, no carryover economy.
  It is game-night bragging rights.
- **Predefined safe templates only:** who gets eliminated next, does this spell resolve, will Player 3
  survive this combat, who wins the game. Spectators never type arbitrary markets.
- **Public game state only:** never generate a prediction from hidden information.
- **Points:** a small starting session balance (for example 500), with fixed stakes (10/25/50/100) or a
  simple confidence selector.
- **Do not build:** odds markets, house edge, real-money mechanics, purchasable currency, or a persistent
  economy.
- **Resolution:** award points when the public outcome resolves, and reset or archive them when the pod
  session ends.
- **Session recap:** `SPECTATOR PREDICTIONS — Alex 740 · Chris 610 · Jordan 425`, optionally Best
  Prediction, Biggest Miss and Longest Streak. Keep it casual: nothing that looks like money or competitive
  rankings.

## 6. Spectator Points cosmetic progression (extends 5; build after it)

Requested 2026-10-03. Prediction points become a lightweight, earn-only cosmetic currency.

**Spectator Points are not money.** No cash value, no real-money purchases, no player-to-player
trading, no withdrawals, no gameplay advantages, and no effect on card draws, dice results, rules,
priority, matchmaking or outcomes.

- **Earning:** modest amounts from correct predictions, from taking part in a full pod session, from
  optional session achievements, and later from other light game-night activities. No odds or exchange
  system.
- **Persistence:** unlike the per-session prediction stakes, the earned balance, unlocked cosmetic IDs and
  equipped cosmetic IDs persist across pod sessions. They are stored per player profile and never tied to
  live match state.
- **Server authority:** the server stores the balance, the unlock transactions and the owned cosmetics. A
  client can never submit `balance = 999999`; it only requests an unlock, and the server checks the
  balance. Cosmetic state is completely separate from rules/gameplay authority.

### Cosmetics Locker

Opened from PROFILE → COSMETICS or LOBBY → COSMETICS.

- **Dice (visual only):** standard acrylic, marble, obsidian, brass, gemstone, holographic, galaxy, fire,
  ice, arcane/rune. Every roll still uses the same server-authoritative RNG, and a pricier die never has
  better odds.
- **Dice effects (subtle and cheap to render):** a small spark on landing, a restrained trail, a rune flash,
  a tiny smoke puff, metallic sound variations.
- **Card/table cosmetics:** sleeve and card-back styles, playmat accents, counter styles, token frames,
  commander pedestals, table trinkets, dice trays, spectator seat decorations, profile frames,
  reaction/emote packs, victory/elimination effects. None may hurt card readability.
- **Equipping:** per category (for example Dice: Obsidian D20; Sleeves: Black Lotus Pattern; Counters:
  Brass; Reaction pack: Commander Chaos). Selections persist between games.
- **Listing:** shows the balance ("Spectator Points: 1,240"), each item as Owned or its price (Obsidian D20
  500 SP, Arcane Rune Set 900 SP, Galaxy Set 1,500 SP), [PREVIEW], [UNLOCK], then [EQUIP].
- **Preview before spending:** dice get a small interactive 3D preview (rotate, roll, inspect
  material/effect). Preview rolls are cosmetic and unrelated to live-game RNG.
- **Forgiving purchases:** a simple confirmation ("Unlock Obsidian Dice for 500 SP? [UNLOCK] [CANCEL]"),
  and ideally an undo/refund until the player leaves the locker.
- **Look:** part of the tabletop aesthetic, with dark wood, felt, brass and a physical display case.
- **Never like a store:** not a mobile cash shop, loot-box screen, battle pass, casino or urgency-driven
  storefront. No limited-time FOMO, random boxes, premium currency or sale timers.
- **Casual progression:** "I've played with this pod a lot, so I have cool dice", not "I need to grind
  currency".

### Session recap (optional, subtle)

`+75 Spectator Points · Predictions 3 correct / 5 · New balance 1,240 SP`, plus a quiet "Obsidian Dice
now available" when something becomes affordable.

### Design notes

- **Generic catalog:** cosmetics are data-driven (id, category, name, price, preview asset/parameters), so a
  new category doesn't mean hardcoding items into UI logic. Not a marketplace: this is a simple local/LAN
  unlock system.
- **Tests:** the server rejects a client-set balance; an unlock debits exactly once and is refused when
  unaffordable; undo restores the balance; equipped cosmetics persist across sessions; dice cosmetics never
  change RNG or results; cosmetic state never touches the live game revision or history.

## End-of-session spectator stats (optional, secondary)

Prediction points, correct predictions, reaction count, most-used reaction. Keep these secondary to the
actual game statistics.

## Required tests

- An eliminated player enters the spectator hub.
- Predictions use public state only; fake points can't affect game state; a resolved prediction awards
  points correctly; prediction state survives spectator navigation.
- Emote cooldown/rate limiting; emotes can't modify game objects; spectator reactions can be muted.
- The damage sandbox can't mutate live state; copying current combat includes only public information.
- The next-game queue doesn't alter the current game; the queued deck appears on return to lobby; a
  same-deck rematch ignores the queued deck until the lobby flow.
- The Practice Table stays isolated from live state; the PiP shows the current public live state; the
  spectator can return from PiP to the live table; the game-end notification appears while using the
  Practice Table.
- Hidden information never appears in spectator payloads.
