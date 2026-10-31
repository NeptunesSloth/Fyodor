# Fyodor UI Reference Study: Tabletop Simulator, MTG Arena and MTG-in-TTS

*Draft v1, 2026-10-31. A research document only. No application code was changed.*

Fyodor is a private four-player Commander tabletop with a plain three.js 3D table, a first-class 2D
fallback, a server-authoritative rules engine and a dark card-room look (walnut, felt, blackened steel,
restrained brass). This study collects interaction lessons from **Tabletop Simulator (TTS)**, **MTG Arena
(MTGA)** and **real MTG tables built inside TTS**. It borrows behaviour, not styling.

Fyodor's position: TTS-like freedom (free positioning, manual override) plus an Arena-like rules engine,
for **four seats around one table**. Two things follow from that:

- **MTGA's battlefield geometry does not transfer.** Arena is built for two players facing each other. No
  fetched source shows a four-player Arena mode. Arena's Brawl is 1v1. See M7.
- **TTS's freedom transfers, but its UX does not.** TTS documents dozens of controls (its own tutorial admits they "may seem overwhelming at
  first"), and its MTG tables layer community scripts on top. Fyodor should keep the freedom and drop the sprawl.

Related Fyodor documents this study maps onto (repository paths): `PRODUCT.md`,
`docs/UI_REDESIGN_BRIEF.md`, `docs/TTS_QOL_RESEARCH.md`, `docs/AUTOMATION_UX.md`,
`docs/RESPONSE_HELPER.md`, `docs/3D_DIRECTION.md`, `.claude/skills/fyodor-ui-design/SKILL.md`.

---

## 0. Method, evidence rules and limits

- **Fetched and read:** the TTS Knowledge Base (KB) pages listed in Appendix A. The KB's source repository
  (`github.com/Berserk-Games/Tabletop-Simulator-Knowledge-Base`) was also cloned so that quotes could be
  checked word for word. That includes the transcripts of Berserk Games' official tutorial videos, which
  live on the KB "Video Tutorials" page. Also fetched: tabletopsimulator.com, the MTGA product and
  Alchemy pages, three MTGA developer articles (quotes checked against the page HTML), community MTGA
  guides, the Steam Workshop pages of the MTG tables named in the reference pack, the TeamDman and
  Draftsim guides, and the SpellTable and TableCommander pages, which are four-player Commander references
  used for comparison.
- **Videos:** YouTube playback and transcripts were blocked (a login/bot check). Titles and channels were
  confirmed through YouTube's oEmbed endpoint. **Timestamps given here are the creators' own chapter
  markers from the video descriptions.** I did not watch the footage, so each one says what the chapter
  covers, not what it shows. Berserk Games' tutorials are the exception: their full transcripts are on the
  KB.
- **Images:** none are embedded or downloaded. Screenshots are linked. Most Steam gallery links come from
  the user's reference pack, and I confirmed that they appear on the fetched Workshop pages.
- **User-supplied screenshots:** these were described by the coordinator. I did not view them. They are
  recorded in §16 and cited as **[US-n]**.
- **Steam note:** every fetched Workshop page contains the text "This item has been removed from the
  community…". It is a **hidden template** (`style="display: none"` in the HTML), not a real notice. The
  items are live. Anyone re-running this research with a text scraper should ignore that text.
- **Could not fetch (HTTP 403 or private):** the MTGA support-site patch notes, the TTS feedback board
  (nolt.io), an AetherHub MTGA hotkey article and the Wizards feedback forum. Claims that would rest only on
  those pages are left out.
- **Not found:** an official Wizards help page for stops, auto-pass or the auto-tapper. MTGA details on
  those come from community guides (dated in each entry) and from one developer interview (chapter marker
  only). I also found no fetched source for MTGA's victory/defeat screens or its targeting-arrow visuals.
  For those, only [US-1] applies.

**Entry format.** Each entry gives the source, its URL (and a timestamp where one exists), what it
demonstrates, why it works, what Fyodor should borrow and what Fyodor should avoid. IDs such as `T1` and
`K4` are used for cross-references.

---

## 1. Physical table

**T1. TTS: hand zones double as seats**
- **Source:** TTS KB, *Player Hands* https://kb.tabletopsimulator.com/host-guides/player-hands/ ; *Zone Tools* https://kb.tabletopsimulator.com/game-tools/zone-tools/ ; *Tables* https://kb.tabletopsimulator.com/host-guides/tables/
- **Demonstrates:** A hand zone acts as the player's "seat", shows the player's name, holds and receives dealt cards, hides them from other players, and is "Invisible unless a held object is moved into it". Seat count is set by adding or removing hand zones. Per the Tables page, the default tables seat 1–4 (Square), 1–6 (Hexagon) and 1–8 (most others).
- **Why it works:** One spatial object answers three questions: where you sit, where your private cards go, and who owns what. Because it is invisible until it is used, it doesn't clutter the table.
- **Borrow:** Make each seat a single spatial anchor that owns the player's name plate, private hand, command zone and counters. Show seat outlines only while dragging toward them.
- **Avoid:** Seats defined by free-floating zones that can overlap. The TTS Tools tutorial transcript warns that hand zones in the middle of the table "can 'grab' cards" being dealt to someone else. Fyodor seats should be fixed by layout presets, never drawn by hand.

**T2. TTS: snap points and grid**
- **Source:** TTS KB, *Snap Point Tool* https://kb.tabletopsimulator.com/game-tools/snap-point-tool/ ; *Grids* https://kb.tabletopsimulator.com/host-guides/grids/
- **Demonstrates:** Snap points attract dropped objects. Rotation snaps also set facing. Grids snap to cell corners or centres. Each object can opt out of snapping from its context menu. Snap points are visible only while the Snap Point tool is active.
- **Why it works:** Placement is forgiving without being forced. The per-object opt-out keeps freedom.
- **Borrow:** Light "magnetic" alignment toward sensible rows (lands, creatures, other permanents) and the command zone. Show it as a faint ghost slot **during drag only**. Fyodor's QoL plan already lists Off / Light / Normal with Alt to disable (`docs/TTS_QOL_RESEARCH.md`).
- **Avoid:** Invisible snap targets. In TTS a player only discovers a snap point when a card jumps. Fyodor should always preview the landing spot.

**T3. TTS: layout zones (automatic arrangement)**
- **Source:** TTS KB, *Zone Tools → Layout Zone* https://kb.tabletopsimulator.com/game-tools/zone-tools/
- **Demonstrates:** A zone that groups dropped objects, with options for direction, padding, sort (name, value and others), objects per group, "Instant Refill" to close gaps, "Manual Only", and "Allow Swapping".
- **Why it works:** Tidying is declarative. Players drop cards and the zone arranges them.
- **Borrow:** The **behaviours**: refill gaps when a card leaves a row, group identical cards, and an optional sort. Offer them as one-shot "Arrange lands / Arrange creatures" commands plus an optional auto-tidy for the land row only (see T6).
- **Avoid:** Exposing about 15 layout settings to players. In Fyodor these are fixed design decisions, not user configuration.

**T4. MTG-in-TTS: Lenc's walnut-style EDH table**
- **Source:** Steam Workshop, *Magic the Gathering Table - MTG EDH* by Lenc https://steamcommunity.com/sharedfiles/filedetails/?id=2425949312 . Gallery examples: [wooden table angle](https://images.steamusercontent.com/ugc/1735548673614196017/A0184293AA24AC5E4D1A95366762A2D9EA234958/), [four quadrant mats](https://images.steamusercontent.com/ugc/1735548673614197124/C27D555810C25F2220F4C38CC8CEC15281AA0D3A/), [counters close-up](https://images.steamusercontent.com/ugc/1735548673614196649/8C360A3F8C107FBB0B2B83427103779DB43A9868/)
- **Demonstrates:** Four player mats on a real-looking table, deckboxes, a draw button and an untap button per player, URL playmats, and a turn tracker. The change notes say mat space was increased, players were moved "a distance of 10px of each other from the center", and the commander counter colour was "Fixed and improved … for each respective player according to table position."
- **Why it works:** The change notes are design lessons in their own right. Players needed **more room per mat**, and **colour had to agree with seat position**.
- **Borrow:** Generous mat space (cards, not chrome, fill it), a per-seat colour system that is consistent everywhere, and physical deck and graveyard objects on the mat.
- **Avoid:** Decor and spare objects (bags, toys) living in the play space. Seat colour as the *only* identifier.

**T5. MTG-in-TTS: Oops I Baked a Pie, four-player scripted table**
- **Source:** Steam Workshop, *MTG 4 player table - scripted* https://steamcommunity.com/sharedfiles/filedetails/?id=2296042369 . Gallery: [overhead four-seat layout](https://images.steamusercontent.com/ugc/1780589749097002508/E2F2EC0683DE824C14BD016B790997E5FF271C12/), [angled controls view](https://images.steamusercontent.com/ugc/1780589749097007053/B25B3ED2DDD46AD034BC5BFB3B9CE5F0641A3F4C/). Video walkthrough: UberGuitarDude, *MTG Commander Online!? (Full Tutorial)*, chapters [1:56 The Table](https://www.youtube.com/watch?v=QJEqKZZ42K4&t=116s), [2:37 Table Interactables](https://www.youtube.com/watch?v=QJEqKZZ42K4&t=157s), [9:50 Field Zones](https://www.youtube.com/watch?v=QJEqKZZ42K4&t=590s)
- **Demonstrates:** The most-subscribed of the tables reviewed here: 385,691 current subscribers when fetched, against 123,932 for Lenc's and 26,114 for Xilisys's. It has four seats, per-seat scripted buttons, context-menu card actions and numpad hotkeys (details in §15).
- **Why it works:** It turns repetitive paper chores (untap, draw, scry, mill, reveal) into one action each, while cards stay physical.
- **Borrow:** The **set** of per-seat chores it chose to automate. They are a good signal of what Commander players do most.
- **Avoid:** The page's own troubleshooting advice is to close "the instruction panels on the blackboard" for less clutter, and to restart TTS because it "sometimes … loads in 'ghost cache scripts' from a previous game". Permanent instruction boards and a stack of fragile scripts are what Fyodor must not reproduce.

**T6. MTG-in-TTS: Portable Playmat (auto lands, manual battlefield)**
- **Source:** Steam Workshop, *MTG Portable Playmat [scripted]* by V https://steamcommunity.com/sharedfiles/filedetails/?id=3651317655
- **Demonstrates:** A per-player mat with zones that spawn automatically. The library is centred and face down. **Lands auto-arrange in a line, face up, stacked to the left on top, with smart tap.** The life zone centres dice. **The battlefield uses manual placement with tap support.** Hovering a card and pressing a script key taps or untaps it. A token menu toggles a grid of token spawners.
- **Why it works:** It splits automation by zone. The low-judgement zone (lands) is organised for you. The high-judgement zone (creatures and other permanents, where position carries meaning such as attacking or attached) stays free.
- **Borrow:** This split exactly. Auto-tidy the land row, with identical lands collapsed (see C6), and leave the battlefield free. Also borrow the "hover + one key" tap.
- **Avoid:** Its one-shot scale correction on load, which the page says to let finish before rotating the board. Fyodor's layout must be deterministic, with no settling period.

**T7. MTG-in-TTS: Minimal MTG (fewer tools, clearer mat)**
- **Source:** Steam Workshop, *Minimal MTG* by OTTOREIKU https://steamcommunity.com/sharedfiles/filedetails/?id=2066242375
- **Demonstrates:** Four seats plus a Game Master and spectators. The author "wanted something that was clean and easy to use without needing all of the bells and whistles". The mat gives every Commander number a home. In the Workshop comments (2021-11-08), a player had to ask what the markers meant, and the author explained: coloured circles hold the turn pawn, "The three 0's are commander damage markers for each other player on the board", 40 is starting life, a circled 0 counts how many times the commander has entered from the command zone, an empty card space takes a partner, and "C is for your Commander". Snap points cover lands, the companion, the turn marker and the City's Blessing.
- **Why it works:** Every Commander-specific number has a fixed home on the mat, so nothing needs a menu. But the markers were **not self-explanatory**. The author replied "I need to maybe rename all of the card zones … or change them to some icons".
- **Borrow:** On each player's mat, a compact commander-damage row with one marker per opponent, identified by seat colour **and** name or initial, plus commander tax and cast count next to the command zone. Every marker carries a label or tooltip.
- **Avoid:** Bare numbers and letters as labels. Also avoid half-automation. Of the scry zone the author wrote "it's sorta broken to begin with sadly. Basically it's just a button to pull the card into that zone however you have to manually move the cards from there". Another player asked "How do send the cards to the bottom?". A feature that stops halfway is worse than a manual one. This matches Fyodor's "Correct or manual" principle.

**T8. User screenshot: six-seat top-down TTS table [US-3]**
- **Source:** User-supplied screenshot (§16).
- **Demonstrates:** Three mats per side, each **outlined in its seat colour**, a **column of per-seat counter icons (life, poison and so on) along each mat's edge**, and deck boxes plus a dice/token tray at the table ends.
- **Why it works:** Ownership reads from the top-down view without labels. Counters sit on the mat edge, so they never cover cards.
- **Borrow:** Counters in a slim strip along the **outer** edge of each seat (the edge nearest the player), with the seat outline as a thin brass-and-colour inlay rather than a bright rectangle.
- **Avoid:** Six seats as a design target. Optimise for four first, as the reference pack also says. Also avoid trays and props sitting in the shared centre, which Fyodor needs for the stack and combat.

**T9. MTGA: battlefield rows (two-player)**
- **Source:** David McCoy, *How To Play MTG Arena: The In-Match Screen*, Hipsters of the Coast, 2018-03-23 https://www.hipstersofthecoast.com/2018/03/how-to-play-mtg-arena-the-in-match-screen/ ; [US-1]
- **Demonstrates:** Lands line up in a row near your library and hand. Creatures sit closer to the centre. Non-creature artifacts and enchantments go to the right of the lands. Planeswalkers are on the far right. [US-1] confirms the current client still puts lands in a back row and creatures in front.
- **Why it works:** Distance from the centre encodes threat. The things that fight are closest to the enemy.
- **Borrow:** The **ordering principle** inside each seat: lands at the back (nearest the player), creatures toward the table centre, others to the side. Make it a default, not a rule.
- **Avoid:** Arena's mirrored two-sided geometry and its automatic placement of every permanent. In a four-seat layout "toward the enemy" means "toward the centre", and players must stay free to move cards.

**T10. TTS: host lighting and LUTs**
- **Source:** TTS KB, *Lighting* https://kb.tabletopsimulator.com/host-guides/lighting/
- **Demonstrates:** Sliders for light intensity, colour, ambient and reflection, plus 115 LUT choices and custom LUT upload.
- **Why it works:** Hosts can set a mood.
- **Borrow:** Nothing beyond a single brightness or exposure accessibility slider.
- **Avoid:** Making the look a host configuration problem. Fyodor's walnut, felt, steel and brass look should be one curated lighting rig tuned for card legibility.

---

## 2. Cards

**C1. TTS: Alt hover-zoom and peek**
- **Source:** TTS KB, *Controls & Movement* https://kb.tabletopsimulator.com/player-guides/basic-controls/ and *Advanced Controls* https://kb.tabletopsimulator.com/player-guides/advanced-controls/ ; Berserk Games, *Tabletop Simulator Tutorials Part 2 - Advanced Controls (2017)* https://www.youtube.com/watch?v=n5JfRMava7w (transcript on https://kb.tabletopsimulator.com/getting-started/video-tutorials/)
- **Demonstrates:** Holding Alt over an object shows a zoomed preview ("this works best for cards"). The scroll wheel resizes it and Q/E rotates it. Alt+Shift **peeks** at the underside, and according to the transcript "an eye symbol of your color is shown on the card you are looking at, so others know you are peeking".
- **Why it works:** Inspection never moves the camera or the card. The peek indicator makes a private action socially visible, which deters cheating without blocking the action.
- **Borrow:** A hold-to-inspect overlay with a resizable preview (Fyodor plans hold Space; see K10 on key conflicts). For any **legal** private look (scry, surveil, looking at a face-down card you control), show other players a small seat-coloured eye-and-name marker on the object. Never show the content.
- **Avoid:** TTS's image-only preview. Fyodor's inspector should add Oracle text, counters, owner and controller, and attachments, as already planned in `docs/TTS_QOL_RESEARCH.md`. Also avoid peek as an always-available cheat that is merely announced. Fyodor's server should only allow peeks that the rules or the table settings permit.

**C2. TTS: object toggles (Sticky, Auto Raise, Hide Face Down)**
- **Source:** TTS KB, *Context Menu* https://kb.tabletopsimulator.com/player-guides/context-menu/ ; Berserk Games, *UI Overview Tutorial Part 2: Contextual Menu* https://www.youtube.com/watch?v=4QKE0N9eRpo (transcript on the KB Video Tutorials page)
- **Demonstrates:** **Sticky**: objects on top move with the object below. **Auto Raise**: held objects lift over others to avoid collisions. **Hide Face Down**: a face-down object hides its name. **Tooltip**: name on hover, with the description shown after a delay.
- **Why it works:** These are the physical behaviours that make cards feel right: counters ride on cards, dragged cards float above the board, and face-down cards don't leak their names.
- **Borrow:** All four as **fixed behaviours**, not toggles. Counters and attachments ride with their card. A dragged card always lifts and casts a shadow. Face-down cards expose nothing, enforced on the server. Tooltip text appears after a short delay.
- **Avoid:** Per-object toggles in the player-facing menu.

**C3. MTG-in-TTS: Encoder modules (state attached to the card)**
- **Source:** Steam Workshop, *Easy Modules for MTG Encoder* by Tipsy Hobbit and Tyrant https://steamcommunity.com/sharedfiles/filedetails/?id=2246039633 ; video *Easy Modules for MTG Encoder (Steam Workshop Video)*, TyrantNomad https://www.youtube.com/watch?v=5cwPxnI1Enw ; UberGuitarDude chapter [13:44 Card Buttons](https://www.youtube.com/watch?v=QJEqKZZ42K4&t=824s) ; [US-2]
- **Demonstrates:** Buttons attached to the card for power/toughness, +1/+1 and -1/-1 counters, numbered counters, planeswalker loyalty **with each loyalty ability as a button**, double-faced card flipping, and a **colour-coded ownership gem**. A sidebar offers Exact Copy, Re-import and Tokens & Emblems. The modules have "no expanded menus": **left-click increments, right-click decrements.**
- **Why it works:** State and its controls live on the object they describe. Adjusting a counter is one click on the card, with no menu trip.
- **Borrow:** Card-attached state chips (P/T, counters, loyalty, owner marker) that are **readable at rest** and **become steppers only on hover or selection**. Planeswalker abilities can be offered as inline actions on hover. Exact Copy (which keeps counters) is a better default than plain copy, as the TeamDman guide also notes.
- **Avoid:** Permanent button rings around every card, which [US-2] shows appearing on hover. Also avoid dependence on an external importer for oracle data. The Workshop comments report broken re-import and token spawning after an importer was disabled, and the Lenc page records a Scryfall statement that it blocked UnityPlayer traffic because importers did not cache. Fyodor's offline Scryfall cache already avoids this.

**C4. MTGA: on-card status language**
- **Source:** *Playing a Match*, MTG Arena Zone, 2022-08-24 https://mtgazone.com/playing-a-match/ ; ASAP beginner's guide https://sites.google.com/view/asap-bg-to-mtga/playing-a-match ; MTGA 2023.25.00 patch notes summary, MTG Arena Zone https://mtgazone.com/2023-25-00-patch-notes/ ; [US-1]
- **Demonstrates:** Power/toughness boxes and **ability glyph badges on the lower card frame**, with an ellipsis when there are too many (right-click shows all). A red aura marks "can't" and prevention effects. Altered costs get a halo. Battles and planeswalkers gained an "icon tray" for Hexproof and Indestructible. Damage is shown as **lowered toughness**, which the guides warn is misleading because damage doesn't reduce toughness.
- **Why it works:** Key rules state is legible on the card without reading Oracle text, and overflow is handled with an ellipsis.
- **Borrow:** A small fixed **icon tray** (keyword glyphs) and a **P/T box** that shows modified values in a distinct state (for example brass for buffed, muted red for reduced). The ellipsis-to-inspect overflow rule.
- **Avoid:** Showing damage as reduced toughness. Show marked damage as its own small marker ("2 dmg") so the rules stay truthful. Also avoid red auras and halos (glow effects). Use flat chips that fit the brass and steel palette.

**C5. MTGA: designing for unusual card shapes (battles)**
- **Source:** Ian Adams, *We Put Battles on MTG Arena: What Was That Like?*, Wizards, 2023-05-29 https://magic.wizards.com/en/news/mtg-arena/we-put-battles-on-mtg-arena-what-was-that-like
- **Demonstrates:** "Fully horizontal all the time is a nonstarter on MTG Arena." Battles became horizontal in hand, on the battlefield and in decks, and vertical only in browsers, because "being horizontal was an important part of the identity of battles." Adding them meant "Card-side VFX like indestructible and hexproof didn't fit. Many VFX weren't centered correctly because of the new ratio." The planeswalker zone had to be rebuilt so planeswalkers wouldn't "page off the screen."
- **Why it works:** Shape carries meaning, but each context (hand, stack, browser) gets the orientation that is readable there.
- **Borrow:** Write every card-attached overlay (chips, outlines, selection, targeting anchors) against an **oriented bounding box**, so it works for tapped, sideways (battles, Planes), flipped and double-faced cards. Use the most readable orientation in the inspector and choice browsers, whatever the card's orientation on the table.
- **Avoid:** Overlays positioned in screen space assuming an upright card. Seat layouts that overflow when a player has many wide permanents.

**C6. Identical-permanent stacking and counts (MTGA) and token piles**
- **Source:** [US-1] (lands stacked with an "x4" count) ; MTG Arena Zone *Playing a Match* https://mtgazone.com/playing-a-match/ , with the same text in the ASAP guide https://sites.google.com/view/asap-bg-to-mtga/playing-a-match ("You can assign a big stack of creatures to attack or block by clicking on the number. You even can assign a stack to block another stack in this way.")
- **Demonstrates:** Identical permanents collapse into one visual stack with a count. In combat, the stack's number acts as a bulk selector.
- **Why it works:** A Commander board with 9 Forests or 27 Treasures stays readable, and acting on the group takes one click.
- **Borrow:** Logical piles for identical lands and tokens. Fyodor's plan already has "Treasure ×27" as one logical stack (`docs/TTS_QOL_RESEARCH.md`). Add **split on divergence**: a pile splits automatically when one member becomes tapped differently or gains a counter. Show a tapped/untapped split as "×6 · 3 tapped". Make the count clickable for bulk selection.
- **Avoid:** Stacks that hide which member is which, or that make a specific member hard to target.

**C7. MTGA Alchemy: marking modified cards**
- **Source:** MTGA Alchemy page https://magic.wizards.com/en/mtgarena/alchemy
- **Demonstrates:** Rebalanced Alchemy cards carry an "A" next to the card name and an "A" foil stamp.
- **Why it works:** A tiny, consistent mark tells you that this card differs from the printed one.
- **Borrow:** A consistent small mark whenever a card's displayed state differs from its printed card. Examples: X / KICKED / MODE / CHOSEN chips, copied-card markers, and manually edited notes (kept distinct from engine-derived status, as `docs/UI_REDESIGN_BRIEF.md` requires).
- **Avoid:** Changing the card art or frame itself to show modifications.

---

## 3. Hands

**H1. TTS: private hand zone with an on-screen hand**
- **Source:** TTS KB, *Player Hands* https://kb.tabletopsimulator.com/host-guides/player-hands/ ; *Teams* https://kb.tabletopsimulator.com/player-guides/teams/ ; TeamDman guide https://github.com/TeamDman/Guides/blob/master/MTG/TabletopSimulator.md
- **Demonstrates:** Hand hiding modes are Default ("visible to owner, hidden to rest"), Reversed and Disabled. The zone can display its contents on the player's screen. TeamDman notes **H** hides your on-screen hand. Teammates see each other's hands, and TeamDman describes "change team" as a way to show your hand to one player.
- **Why it works:** The hand is a real place on the table (opponents see card backs and the count) and a screen-space strip for the owner.
- **Borrow:** The dual presentation: a screen-space fan for the owner (On / Off / Auto, as Fyodor plans) **and** a count of card backs at the seat for everyone else. Add a deliberate **"Reveal hand to…"** action (one player or all) with a visible "revealed" state and an automatic end.
- **Avoid:** Using teams as a hand-reveal workaround, which shares *all* hidden zones both ways. Also avoid the "Disabled" and "Reversed" hiding modes.

**H2. MTGA: hand at the screen edge**
- **Source:** Hipsters of the Coast 2018 (T9 URL) ; [US-1]
- **Demonstrates:** The hand sits at the bottom with cards partly off-screen. Hovering a card brings it fully into view. **Playable cards get a blue outline.** Cards castable from graveyard or exile (Embalm and similar) appear to the right of the hand. [US-1] shows the fan with **mana costs visible**.
- **Why it works:** The hand costs little screen space until you engage with it. "What can I do now?" is answered by outlines, not by reading.
- **Borrow:** A low fan with the top band visible (name and mana cost), lift on hover, and a **playable outline that matches Fyodor's focus/selection language** (brass, not blue). A separate "castable from elsewhere" tray for cards with permission to be cast from graveyard, exile or the command zone. The commander can live there too.
- **Avoid:** Outlines as the only cue. Add a small cost-affordable pip for colour-blind users. Do not let the hand cover the player's own land row in 3D.

**H3. MTGA: anticipatory hints above the hand [US-1]**
- **Source:** [US-1] ("You will need to discard down to 7 at the end of your turn")
- **Demonstrates:** The client warns about a future forced decision before it happens.
- **Why it works:** No surprise prompt at the cleanup step, and newcomers learn the rule in context.
- **Borrow:** A single-line, dismissible **forecast line** above the hand for upcoming forced events, such as hand size or "your commander will return…". Show it once and hide it for veterans via a setting.
- **Avoid:** Stacking several hints. Show at most one, then let it fade.

**H4. MTG-in-TTS: hand-level actions (Oops table) [US-2]**
- **Source:** Oops table page (T5 URL) ; [US-2]
- **Demonstrates:** Right-clicking a hand card offers **Sort by CMC** and **Random discard**.
- **Why it works:** These are the two hand operations paper players can't do neatly online.
- **Borrow:** Sort options (cost, type, recently drawn) on the hand strip, and a **server-side random discard** whose result everyone can see as fair, because the server picks.
- **Avoid:** Hiding them in a per-card menu. They act on the whole hand, so they belong on the hand strip.

---

## 4. Controls and contextual menus

**K1. TTS: context menu (object-specific on top, generic below, global on empty table)**
- **Source:** TTS KB, *Context Menu* https://kb.tabletopsimulator.com/player-guides/context-menu/ ; Berserk Games, *UI Overview Tutorial Part 2: Contextual Menu* https://www.youtube.com/watch?v=4QKE0N9eRpo
- **Demonstrates:** "Top Section: Options that are specific to this object" and "Lower Sections: Options that are available on all objects." The transcript adds: "The contextual menu will work on all selected objects." Right-clicking empty table opens a **global** menu (camera mode, save and load camera, blindfold, paste).
- **Why it works:** One gesture works everywhere. The menu adapts to the object and applies to the whole selection.
- **Borrow:** A Fyodor context menu with that structure, where a card shows only actions relevant to its zone and state, **with the hotkey printed next to each item** so the menu teaches the shortcuts. Group actions apply to the selection. Right-clicking empty felt opens table-level actions (camera presets, pings, notes).
- **Avoid:** TTS's always-present technical items (Physics, Scripting, Save to Chest, Tint, toggles) and deep nesting. Fyodor needs no physics or scripting menus for players.

**K2. TTS: hover + key acts on the hovered object**
- **Source:** Berserk Games, *Tabletop Simulator Tutorials Part 1 - Basic Controls (2017)* https://www.youtube.com/watch?v=SGPdpGn0DCM (transcript on the KB Video Tutorials page) ; Chris Backe, *Tabletop Simulator 105*, 2021-07-01 https://entrogames.substack.com/p/tabletop-simulator-105-navigating-keyboard-shortcuts-and-saving-time
- **Demonstrates:** Hover, then press F to flip, Q/E to rotate, R to shuffle or roll, G to group, L to lock, U to place under, a number to set a die face, and +/- to scale. You don't need to pick the object up.
- **Why it works:** It is the fastest pattern in TTS. The pointer is the selection, so there's no click-then-menu.
- **Borrow:** The hover-target model for all card verbs: tap, flip or transform, counter +/-, inspect, move to graveyard or exile. Fyodor already plans "hover + R tap" and similar keys. Show a tiny key hint near the cursor the first few times.
- **Avoid:** Hover-acting on objects the player doesn't control. On a shared table, verbs on opponents' cards should require selection plus confirmation or be blocked by the server.

**K3. TTS: type a number over a deck to draw that many**
- **Source:** TTS KB, *Advanced Controls* (as above) ; TeamDman guide ; Oops chapter [10:42 Manual Draw](https://www.youtube.com/watch?v=QJEqKZZ42K4&t=642s)
- **Demonstrates:** "With the pointer over a stack/bag/deck, typing in a number will draw that many cards after 1 second." Quick presses combine, so 1 then 2 draws 12. Scripted table buttons accept a typed number in the same way (TeamDman: hover the button, type, move away to confirm).
- **Why it works:** Common Commander actions (draw 3, mill 4, scry 2) become two keystrokes.
- **Borrow:** Numeric quantity entry on the hovered library for draw, mill, scry, reveal and exile-top, with a visible pending "Draw 12…" chip and Esc to cancel during the delay.
- **Avoid:** A silent delay with no feedback. TTS gives none until the cards move.

**K4. TTS: ping (Tab)**
- **Source:** TTS KB, *Line Tool* https://kb.tabletopsimulator.com/game-tools/line-tool/ ; Berserk Games, *UI Overview Tutorial - Tools Menu Part 1a* https://www.youtube.com/watch?v=CUUin0rga5k
- **Demonstrates:** "Left-clicking will cause a rotating arrow that matches your player color to appear, along with a chime to all players." Tab clicks ping from the normal grab tool, and holding Tab measures. The transcript suggests using it "when it's someone's turn and you're trying to get their attention".
- **Why it works:** It is the digital "look here", which voice chat alone can't do, and it uses both colour and sound.
- **Borrow:** A ping on any card or spot with seat colour **plus the player's name or initial**, a soft chime, about 3 seconds of life and a rate limit. Fyodor plans Alt+click. A "nudge" variant could be aimed at a player who holds priority.
- **Avoid:** A colour-only arrow. Also avoid the measuring ruler on the same key, which Fyodor doesn't need.

**K5. TTS: Gizmo tool (precise transforms)**
- **Source:** TTS KB, *Gizmo Tool* https://kb.tabletopsimulator.com/game-tools/gizmo-tool/
- **Demonstrates:** Move, rotate and scale handles, Ctrl for 1-unit or 1° snapping, and a Transform menu with numeric fields.
- **Why it works:** It gives table builders precision.
- **Borrow:** Nothing for players. At most, a host-only layout editor later, if seat presets ever become editable.
- **Avoid:** 3D transform handles in play mode.

**K6. MTGA: a small, memorable hotkey set**
- **Source:** DoggertQBones, *Arena Hot Keys and Interface Guide*, MTG Arena Zone, 2022-08-24 https://mtgazone.com/arena-hot-keys-and-interface-guide-simplify-your-game-with-these-easy-tricks/ ; David Royale, *15 MTG Arena Keyboard Shortcuts*, Draftsim, 2024 https://draftsim.com/mtg-arena-keyboard-shortcuts/ ; OriginMD, Flipside Gaming, 2019-01-22 https://flipsidegaming.com/blogs/magic-blog/mtg-arena-hot-keys-and-using-the-interface
- **Demonstrates:** Space passes priority (the same as the large button). Enter passes until there is something to respond to. Shift+Enter passes the turn. Ctrl gives Full Control for now, and Ctrl+Shift holds it. Z undoes non-stack actions such as mana. Q+Q floats all mana, and holding Q while clicking lands quick-taps them. L shows phases.
- **Why it works:** About eight keys cover the whole priority model, and every key has an on-screen button equivalent.
- **Borrow:** The **shape**: one deliberate "pass" key, one "pass until something happens", one "pass turn", one "hold / full control", one "undo". Each is mirrored by a visible control and listed in a "?" overlay.
- **Avoid:** Arena's undiscoverable modifier chords (Ctrl+Shift with Ctrl still held). Flipside also notes "only the Shift key on the left side works for hot keys", so avoid side-specific modifiers.

**K7. TTS discoverability failures (what goes wrong)**
- **Source:** LightRanger Games, *Tabletop Simulator: What I Wish I Knew: For Beginners*, chapters [13:18 Accidentally Placing Things in Bags](https://www.youtube.com/watch?v=zpwNV1MECXM&t=798s), [18:05 Accidentally Dragging Groups](https://www.youtube.com/watch?v=zpwNV1MECXM&t=1085s), [10:50 Locking and Unlocking items](https://www.youtube.com/watch?v=zpwNV1MECXM&t=650s) ; TeamDman guide (`p` changes the camera type and "sometimes gets hit accidentally"; hiding the hand with H is "Mostly done by accident") ; Berserk Basic Controls transcript ("There are a lot of controls in Tabletop Simulator to learn and master… it may seem overwhelming at first")
- **Demonstrates:** The beginner pain points are accidental merges (objects into bags or decks), accidental group drags, lock confusion and mode keys hit by mistake. The official tutorial itself admits the control count is overwhelming.
- **Why it works:** (as a warning) Physics and modes make mistakes easy and silent.
- **Borrow:** Stacking or merging only on explicit intent. Fyodor's "Protected" objects, and confirmation before merging into a library, are the right answer. Make mode changes visible with a toast and undoable.
- **Avoid:** Single-key global mode switches (camera mode on P) near frequently used keys.

**K8. MTG-in-TTS: numpad chore hotkeys (Oops table)**
- **Source:** Oops table page (T5 URL)
- **Demonstrates:** On the numpad: 0 passes the turn; 1 untap, 2 draw, 3 scry, 4 mill, 5 reveal (fan), 6 reveal (stack); 7 moves selected cards to exile, 8 to graveyard, 9 to the bottom of the library in random order.
- **Why it works:** Bulk zone moves on the selection are the main time-savers in Commander.
- **Borrow:** "Selection → zone" keys (graveyard, exile, library bottom with a random-order option, hand), shown in the context menu and the selection toolbar.
- **Avoid:** Numpad-only bindings, since many laptops have no numpad. Also avoid "Pass turn" on a single unguarded key.

**K9. TTS: remappable keys and a help overlay**
- **Source:** TTS KB, *Help Menu* https://kb.tabletopsimulator.com/getting-started/help-menu/ ; *Controls & Movement* (as above)
- **Demonstrates:** "?" or "/" opens the help menu. Key bindings are defaults and most can be changed in Settings → Controls.
- **Borrow:** "?" opens a compact cheat sheet generated from Fyodor's central hotkey registry, so it always matches the real bindings. Allow remapping.
- **Avoid:** A help screen made of static images. The KB help page shows its control schemes only as images, which are hard to search and can drift out of date.

**K10. Cross-product key conflicts Fyodor must resolve deliberately**
- **Source:** K2, K6, CA1 and Fyodor docs (`docs/TTS_QOL_RESEARCH.md`, `docs/RESPONSE_HELPER.md`)
- **Demonstrates:** Muscle memory collides across products. **Space** is "pass priority" in MTGA, "reset camera" in TTS, and hold-to-inspect plus skip-animation in Fyodor's plans. **P** is "camera mode" in TTS and "pass" in Fyodor. **Tab** pings in TTS and previews the other face in Fyodor. **Enter** is "pass until response" in MTGA.
- **Borrow:** Make sure no key that is harmless in TTS or Arena does something irreversible in Fyodor. In particular, an Arena player tapping Space must never pass priority unless they have bound it that way. Offer an "Arena-style" key preset as an option.
- **Avoid:** Shipping defaults without a conflict audit. The hotkey unit test noted in `docs/RESPONSE_HELPER.md` stops duplicate bindings, but it can't catch cross-product muscle memory.

---

## 5. Camera

**CA1. TTS: three camera modes, reset and saved views**
- **Source:** TTS KB, *Controls & Movement*, *Camera Control* https://kb.tabletopsimulator.com/player-guides/camera-states/ , *Advanced Controls* ; Berserk Basic Controls transcript
- **Demonstrates:** Third person (the default), first person and top-down, cycled with P. Space resets. WASD pans, right-drag orbits, middle-drag pans. MMB or Z quick-zooms **toward the pointer and back**. Ctrl+1–9 saves a view and Shift+1–9 loads it. The contextual-menu transcript says Alt+number loads, which shows the documentation drifting. Ctrl+0 sets a shared default seat view.
- **Why it works:** Quick zoom to the pointer and back, plus a reliable reset, make free cameras safe to explore.
- **Borrow:** Reset (one key, smooth), quick zoom toward the cursor and back, and numbered presets. Fyodor already plans presets 1–7 plus F to focus. Make the top-down view a **preset**, not a mode.
- **Avoid:** First-person flying and mode cycling. No Fyodor action should require camera skill.

**CA2. TTS: magnify lens**
- **Source:** Berserk Advanced Controls transcript ; Backe 2021 (K2 URL)
- **Demonstrates:** Hold M for a magnifying circle that follows the cursor, with the wheel setting zoom. Backe notes it suits boards better than Alt.
- **Why it works:** It lets you read a cluster of small objects (counters, a crowded opponent board) without moving the camera.
- **Borrow:** A hold-to-magnify lens over the 3D table as a low-vision aid.
- **Avoid:** Using it as a substitute for readable default card sizes.

**CA3. MTGA: a camera that never needs managing**
- **Source:** Hipsters 2018 (T9) ; [US-1]
- **Demonstrates:** A fixed composition: own board at the bottom, opponent at the top, stack on the right, inspector on the right. The player never moves a camera.
- **Why it works:** All attention goes to the decisions.
- **Borrow:** Make the **default 3D framing** (and the 2D layout) show all four seats legibly with zero camera input. Use camera moves only as optional focus aids, such as auto-centring on combat or a stack target, set to Off / Important only / On as in the redesign brief.
- **Avoid:** A fixed two-player composition. Also avoid hiding opponents' boards behind tabs.

**CA4. SpellTable: Focus view versus all-opponents view (four-player)**
- **Source:** *Remote Magic Made Easy with SpellTable Beta*, WPN, 2021-03-16 https://wpn.wizards.com/en/news/remote-magic-made-easy-spelltable-beta
- **Demonstrates:** Wizards' own four-player webcam tool offers layouts that either **focus a single player's battlefield** or show all opponents. Clicking a card in Focus view means "it should appear in the drawer on the right of the screen for easy reading".
- **Why it works:** In four-player games you alternate between a survey of the table and close reading of one board.
- **Borrow:** A "focus seat" preset per opponent and an optional pinned **picture-in-picture** of one seat or the stack (Fyodor lists PiP as planned). Pin the inspected card to a right-side drawer.
- **Avoid:** Layouts that shrink three opponents into thumbnails by default.

---

## 6. Stack

**S1. MTGA: stack column with hover-to-show-targets**
- **Source:** *Playing a Match*, MTG Arena Zone, 2022-08-24 https://mtgazone.com/playing-a-match/ ; Flipside 2019 (K6 URL)
- **Demonstrates:** The stack is on the right. Hovering an item shows its targets, and right-clicking shows the full card. A small arrow collapses the stack if it covers the planeswalker area. A very large stack expands to the middle of the screen. Flipside notes you can move the stack and emblem icons "by clicking on the arrows above them if they are in the way", since "It might be needed if you want to target something below them."
- **Why it works:** Who targets what is shown on demand. The stack never permanently costs table space, and it scales up only when it is big.
- **Borrow:** A compact stack strip anchored at the table centre or right side, showing order, source, controller seat marker and targets. Hover draws curved target beams, as in [US-1]. Many similar triggers collapse to "×5". An expanded mode appears only when it is needed.
- **Avoid:** Overlays that cover targets. The stack must never sit on top of something you may need to click.

**S2. Stack order labels: "Resolve first" / "Resolve last"**
- **Source:** That Design Feel Side Quest, *CAN WE FIX THIS?! Biggest UI issues Magic: The Gathering Arena* https://www.youtube.com/watch?v=F4GXdrMJF0o (no chapters; the claim is from the creator's description addendum)
- **Demonstrates:** In the description, the creator revises an earlier suggestion of "Top"/"Bottom" labels for stack ordering: "'Resolve first' and 'Resolve last' is actually neater."
- **Why it works:** The label states consequences, not spatial metaphor.
- **Borrow:** Use "Resolves first / Resolves last" wording on Fyodor's stack and in trigger-ordering prompts.
- **Avoid:** "Top/Bottom", which depends on orientation and is ambiguous in 3D.

**S3. MTGA: payment feedback on the stack**
- **Source:** 2023.25.00 patch notes summary, MTG Arena Zone https://mtgazone.com/2023-25-00-patch-notes/
- **Demonstrates:** "The new Convoke VFX make little orbs fly around the card on the stack as you tap creatures."
- **Why it works:** Partial payment is shown on the spell being paid for.
- **Borrow:** While Fyodor's "Pay {1}{G}" prompt is open, show remaining cost pips on the pending spell that fill in as sources are tapped. Use flat pips, not orbs.
- **Avoid:** Particle VFX.

**S4. MTG-in-TTS: no stack, plus social "response" buttons**
- **Source:** *Mtg EDH Table of Doom! - 4 player magic* by schoob https://steamcommunity.com/sharedfiles/filedetails/?id=2278483976
- **Demonstrates:** TTS has no stack. Cards are placed in the middle and players talk. Table of Doom adds physical **"response buttons"**.
- **Why it works:** A shared "hold on, I respond" signal is the most valuable social primitive in paper Commander.
- **Borrow:** Fyodor's RESPOND / PASS / AUTO-PASS (`docs/RESPONSE_HELPER.md`) is the rules-aware version. Present it as a compact, table-anchored signal on each seat (for example a small brass "✋ responding" plate), visible to everyone.
- **Avoid:** Buttons with no game consequence that players can ignore.

---

## 7. Combat

**CB1. MTGA: bulk attack and block selection**
- **Source:** ASAP guide https://sites.google.com/view/asap-bg-to-mtga/playing-a-match ; MTG Arena Zone *Playing a Match* (S1 URL)
- **Demonstrates:** Hover the defending player to see which attackers are unblocked. Click a creature stack's number to assign the whole stack. Select several creatures, then click their target. The guide notes that multi-blocking Menace creatures is buggy.
- **Why it works:** Combat declarations are batch operations, and the UI treats them that way.
- **Borrow:** Multi-select creatures, then click a **defender** (a player's name plate, a planeswalker or a battle). The defender gets a beam from each attacker. Use pile counts for token armies. Blocking works the same way (select blockers, then click an attacker), with a running "unblocked: 3" summary per defender.
- **Avoid:** Assuming a single defender. In four-player Commander every attacker needs an explicit defender, and the UI must show which attacker goes where at a glance.

**CB2. MTGA: "combat feeling right" decides placement**
- **Source:** Ian Adams, battles article (C5 URL)
- **Demonstrates:** Playtests compared putting battles on the controller's side with putting them on the protector's side. Players could adapt to either, "but combat feeling right consistently ranked as the priority". Battles went to the protector's side.
- **Why it works:** Spatial logic follows the most frequent interaction, which is attacking.
- **Borrow:** In four-player games, put attack targets where attacks are aimed. Battles sit with their protector's seat. Planeswalkers stay on their controller's mat but get a clear "attackable" affordance during declare attackers.
- **Avoid:** Placement driven only by ownership when that makes combat targeting confusing.

**CB3. MTGA: combat step stops and icons**
- **Source:** MTG Arena Zone hotkeys guide (K6 URL)
- **Demonstrates:** The combat phase list uses icons: a sword for declare attackers, a shield for declare blockers and an explosion for damage. Stops can be set on each.
- **Why it works:** Combat substeps are small but distinct, and icons fit a narrow rail.
- **Borrow:** Distinct glyphs for combat steps on Fyodor's phase rail, plus a temporary **combat lane view** (already in the brief). It lines up attackers and their defenders and restores positions afterward.
- **Avoid:** Explosion and other action-game iconography. Use restrained engraved glyphs.

**CB4. TTS: combat is pure manual movement**
- **Source:** UberGuitarDude chapter [8:36 Rotating/Tapping](https://www.youtube.com/watch?v=QJEqKZZ42K4&t=516s) ; Draftsim TTS guide (rotate keys) https://draftsim.com/tabletop-simulator-mtg/
- **Demonstrates:** Attacking means rotating (tapping) a card and pushing it forward, and declaring verbally.
- **Why it works:** It is physical and expressive, and nothing is enforced.
- **Borrow:** In 3D, let attackers slide slightly toward the defender (Fyodor plans this) as a *presentation* of the declared state.
- **Avoid:** Declaring combat by dragging physical cards. Declarations should be rules intents. Drag-to-attack can be an input shortcut that creates the intent.

---

## 8. Prompts and decisions

**P1. MTGA: show only what is playable, and send full constraints**
- **Source:** Alex Werner, *On Whiteboards, Naps and Living Breakthrough*, Wizards, 2023-07-31 https://magic.wizards.com/en/news/mtg-arena/on-whiteboards-naps-and-living-breakthrough
- **Demonstrates:** The X-value prompt had to grow from min/max to "a list of values that are specifically not allowed". The player sees a Forest in the graveyard "highlighted and playable, but neither of their Lightning Bolts are playable."
- **Why it works:** The UI never offers an illegal choice, and it can explain why a value is missing.
- **Borrow:** Every prompt payload from the Fyodor engine carries the **legal set and the disallowed values with reasons**. The client highlights only legal candidates and greys the rest, with a reason on hover ("Can't target: hexproof").
- **Avoid:** Letting the client guess legality.

**P2. MTGA: designers choose the decision form**
- **Source:** Alex Werner, *Dev Diary: Creating Arena Powered Cube*, Wizards, 2025-10-23 https://magic.wizards.com/en/news/mtg-arena/dev-diary-creating-arena-powered-cube
- **Demonstrates:** For a choice such as "Discard a card or sacrifice a creature", the designer decides whether the player gets labelled buttons or can click the cards directly. "The Design team also decides about 'smart stops'" and whether a targeted ability should give "an 'Are you sure?' prompt if you target your own creature."
- **Why it works:** Choices are made **on the table** when the options are objects and **as buttons** when they are abstract. Confirmations are reserved for likely mistakes.
- **Borrow:** A rule for Fyodor prompts. Object choices are clicked in place, with candidates lit and a slim instruction bar ("Choose a creature to sacrifice · 0/1"). Abstract choices use a compact radial or button row. Add "Are you sure?" only for self-harm patterns such as targeting your own permanent with removal.
- **Avoid:** Modal dialogs that cover the board for object choices.

**P3. MTGA: decline expensive edge-case UI, and never ship half a card**
- **Source:** Powered Cube dev diary (P2 URL)
- **Demonstrates:** Wizards skipped a graveyard-ordering dialog because of "the cost of developing and maintaining that system", and decided they "don't want to establish a precedent of releasing partially implemented cards".
- **Why it works:** Every special dialog is permanent maintenance, and partial automation erodes trust.
- **Borrow:** This supports Fyodor's FULL / PARTIAL / MANUAL coverage. PARTIAL cards should *say so* in the inspector and hand off to manual play cleanly, rather than half-acting.
- **Avoid:** Building one-off prompt UIs for rare cards. Fall back to manual play with a clear "Manual: resolve this yourself" banner.

**P4. MTGA: optional prompts and reminders as settings**
- **Source:** Herko Kerghans, *All 15 Settings in MTG Arena Explained*, Draftsim, 2025-10-14 https://draftsim.com/mtg-arena-settings/ ; Kappolo, *Optimal MTG Arena Settings*, chapter [0:32 Gameplay Settings](https://www.youtube.com/watch?v=7n_sKGxUMIs&t=32s) ; 2023.25.00 patch notes summary (S3 URL)
- **Demonstrates:** Settings for **Keyword Reminders** (text on hover), **Enable Gameplay Warnings** (questionable plays, which the author suggests turning off if they second-guess too much), and auto-order triggers, auto-choose replacement effects and auto-assign combat damage. An Elesh Norn-specific "Do you pay the 1?" prompt was added in 2023.
- **Why it works:** Veterans switch off hand-holding and newcomers keep it. This matches Fyodor's "fast for veterans, clear for newcomers".
- **Borrow:** Per-player toggles for keyword reminders and gameplay warnings, both on by default for new players. Fyodor's "remembered answers" (ALWAYS YES THIS TURN…) already cover the auto-yield side.
- **Avoid:** Warnings that block. They should inform and never require an extra click on the common path.

**P5. TTS and MTG-in-TTS: no prompts, only social agreement**
- **Source:** TeamDman guide ("continue as if it was paper magic") ; Minimal MTG partial scry zone (T7)
- **Demonstrates:** Everything is negotiated by voice, and scripts provide shortcuts without enforcement.
- **Borrow:** The manual fallback is always present (a Fyodor hard rule).
- **Avoid:** Treating "no prompts" as acceptable for the cards Fyodor supports.

---

## 9. Automation (auto-pass, auto-tap, stops)

**A1. MTGA: stops on a phase ladder and Full Control**
- **Source:** MTG Arena Zone hotkeys guide (K6) ; ASAP guide (CB1) ; Flipside 2019 (K6) ; *How to Use Full Control | MTG Arena | What I Wish I Knew #10*, Jumpstart My MTG Heart https://www.youtube.com/watch?v=BN9KIcO0xIg (no chapters)
- **Demonstrates:** You set stops by clicking phase icons on the ladder near either player's portrait. A future stop shows as a "light circle". Stops are **orange on your turn and blue on the opponent's** (MTG Arena Zone, 2022). A stop acts like Full Control for that step and is honoured even in "Pass Turn" mode. The ASAP guide advises setting stops early because the server can run ahead of client animations.
- **Why it works:** Auto-pass is the default, and exceptions are pinned exactly where they apply, next to the player they apply to.
- **Borrow:** Fyodor already has RESPONSE OFF/AUTO/ON, stops for my turn and their turn, FULL CONTROL, FORCE STOP and PASS UNTIL… (`docs/AUTOMATION_UX.md`). What to borrow is the **presentation**: a slim phase rail at the player's seat ([US-1] shows stop icons on a rail around the avatar medallion), where clicking a step toggles a stop. Distinguish own-turn and other-turn stops by **shape** (for example a filled versus an outlined notch) as well as colour. Show the stop where it will trigger.
- **Avoid:** Colour as the only distinction between the two stop kinds. Also avoid stops whose lifetime is unclear. Fyodor should state it on the stop ("this turn" / "always"). Appendix B notes an unverified community claim that Arena stops clear after a turn.

**A2. MTGA: stops leak information, so design for bluffing**
- **Source:** MattSperlingMTG, *Bluffs, Tells, Tips, and Tricks using the Magic ARENA interface* https://www.youtube.com/watch?v=ouaTIF_gHY8 (description: "When do the stops reveal info? How do you stop that from happening?") ; MTG Arena Zone hotkeys guide, bluffing section
- **Demonstrates:** Hesitations in priority passing hint at instants. Players hold Full Control or set stops everywhere to bluff.
- **Why it works:** (as a warning) Automation timing is visible to opponents.
- **Borrow:** Fyodor's existing rules (auto-passes look exactly like passes, optional BLUFF STOPS on public conditions) are correct. Make the "waiting for…" indicator **identical** for "thinking" and "auto-pass about to fire", and keep pass latency uniform. For example, wait a minimum dwell before broadcasting any pass.
- **Avoid:** Anything such as "Player 3 has no responses" text or a different animation for auto-passes.

**A3. MTGA: auto-tapper (preview, override, undo)**
- **Source:** ASAP guide (CB1) ; Flipside 2019 (K6) ; MTG Arena Zone hotkeys guide ; PowrDragn interview with MTGA developer Ian Adams, *Creator Accounts? Autotapper Broken? Matchmaking? Arena Dev Answer All!*, chapter [6:30 How Does Autotapper REALLY Work?](https://www.youtube.com/watch?v=AcY_H74tVXg&t=390s)
- **Demonstrates:** Hovering or dragging a spell **without releasing it** highlights the lands the auto-tapper plans to tap. Z undoes an unpaid tap. Q+Q floats all mana. Guides warn the auto-tapper mishandles utility lands and colour-intensive costs ("Always double check how Auto tapper is tapping for you"). The developer interview has a chapter on how it works, which I did not watch.
- **Why it works:** Preview before commit makes automation trustworthy, and undo makes it forgiving.
- **Borrow:** Fyodor's pod rule is that players tap their own mana (`docs/AUTOMATION_UX.md`). Keep it. Borrow the **preview**: while a "Pay" prompt is open, optionally show a **suggested** set of sources as ghost highlights that the player confirms with one key ("Tap suggested"). The player still taps, the suggestion is advisory, and Z (undo) reverses taps before payment.
- **Avoid:** Silent auto-tapping, which the pod has rejected. Also avoid suggestions that tap sources with non-mana abilities without flagging them.

**A4. MTG-in-TTS: scripted chores as opt-in helpers**
- **Source:** Oops table (T5) ; Lenc table (T4) ; Encoder "Auto powtou / Auto plusone / Auto counters" chat toggles (C3) ; UberGuitarDude chapters [10:58 Scrying](https://www.youtube.com/watch?v=QJEqKZZ42K4&t=658s), [11:30 Milling](https://www.youtube.com/watch?v=QJEqKZZ42K4&t=690s), [12:17 Cascade/Discover](https://www.youtube.com/watch?v=QJEqKZZ42K4&t=737s), [12:40 Fetching Land](https://www.youtube.com/watch?v=QJEqKZZ42K4&t=760s)
- **Demonstrates:** Untap, draw, scry, mill, reveal, cascade, "reveal until type" and "get basic land" as buttons or menu actions. Auto-display of P/T and counters is switched on by chat commands.
- **Why it works:** It automates *procedures*, not rules judgements, so players stay in charge.
- **Borrow:** The procedures as manual-table macros that remain available even under FULL automation, for cards the engine doesn't cover.
- **Avoid:** Configuration through chat commands.

**A5. TableCommander: turn automation toggles (four-player Commander web app)**
- **Source:** TableCommander docs, *Life & Counters* https://tablecommander.com/docs/gameplay/life-counters
- **Demonstrates:** Turn settings for a turn alert, **auto untap, auto draw**, seating in turn order and turn hotkeys (Space and End). A phase strip and turn clock sit at the top right, and hovering the clock shows turn counts per player.
- **Borrow:** Auto untap and auto draw as engine steps that are on by default, with an explicit "your turn" alert and sound.
- **Avoid:** Space as a turn key (see K10).

---

## 10. Multiplayer and seating

**M1. TTS: colour equals seat equals identity**
- **Source:** TTS KB, *Changing Color* https://kb.tabletopsimulator.com/player-guides/changing-color/ ; *Player Roles* https://kb.tabletopsimulator.com/getting-started/player-roles/ ; *Teams* (H1 URL)
- **Demonstrates:** You pick a colour to play, and changing colour moves your seat, with a preview of where you'll go. The host can lock colour changes. There are five teams, which share hand zones, hidden zones and notebook pages, and have private chat and voice.
- **Borrow:** A seat picker in the lobby that previews the seat position on a miniature table. Seat colour is a persistent identity across games (the pod persists).
- **Avoid:** Team-based sharing of hidden information. Commander is free-for-all, and any sharing should be an explicit per-card or per-hand reveal.

**M2. TTS: turns system (star, End Turn, pass turn)**
- **Source:** TTS KB, *Turns* https://kb.tabletopsimulator.com/host-guides/turns/
- **Demonstrates:** "The player with the star next to their name (in the upper right) is used to display who's turn it is." Options include custom order, reverse order, skipping empty seats, Pass Turns, and "Disable Interactions", which "Blocks player interactions if it is not their turn." The first player gets a sound and a prompt.
- **Why it works:** It is a minimal shared turn state with an audio cue.
- **Borrow:** The audio cue and a clear "your turn" moment. An active-player marker on the **table** (for example a brass turn token or a lit edge of the active seat) instead of only a star in a player list.
- **Avoid:** Showing the active player only in a screen-corner list. Also avoid "Disable Interactions": Commander needs off-turn responses.

**M3. MTG-in-TTS: commander damage per opponent, colour matched to seat**
- **Source:** Minimal MTG author comments (T7) ; Lenc change notes (T4) ; [US-3]
- **Demonstrates:** Per-opponent commander-damage markers with coloured dots (Minimal MTG), counter colours set "according to table position" (Lenc), and per-seat counter columns ([US-3]).
- **Borrow:** On each mat, a commander-damage row ordered **by seat position** (left / across / right as seen from the owner), so the spatial mapping needs no legend. The 21 threshold shows as a fill bar with a tick at 21. The row is visible on hover and auto-expands when any value is 15 or more.
- **Avoid:** Colour dots without names. Two seat colours may be confusable for colour-blind players.

**M4. SpellTable: name bars as the player summary**
- **Source:** WPN 2021-03-16 (CA4 URL)
- **Demonstrates:** Life, infect and commander damage are tracked in one place. Clicking your name bar edits or views your commander and damage totals, and clicking another player's shows theirs. There is a turn indicator and a clock.
- **Why it works:** One compact plate per player and progressive disclosure on click.
- **Borrow:** A **seat plate** (name, life, poison when non-zero, commander chip, priority and connection state). Click to expand commander damage dealt and taken, then collapse.
- **Avoid:** Turn clocks. A private pod doesn't need them.

**M5. TableCommander: commander damage also changes life; seat-level badges**
- **Source:** TableCommander docs (A5 URL)
- **Demonstrates:** "Adding damage there also takes it off your life, so you don't record it twice." Lethal is 21 from any one commander, and "The panel shows how close each source is." The Monarch gets a crown on their seat and Initiative a ⚔️. Life changes go to the game log with who made them.
- **Borrow:** In manual mode, a single input for commander damage that updates both totals in one undoable action. Seat-level badges for Monarch, Initiative, City's Blessing and Day/Night. **Every life change is logged with its source.**
- **Avoid:** Emoji iconography. Use engraved glyphs in brass.

**M6. MTGA: the avatar medallion with life and stops [US-1]**
- **Source:** [US-1] ; Hipsters 2018 (T9) (avatar centred in the phase strip, life below, click for emotes, burning fuse when slow)
- **Demonstrates:** A player is a **medallion**: portrait, life below it, phase stops on a rail around it.
- **Why it works:** Identity, vitality and timing are compressed into one glanceable object.
- **Borrow:** A four-seat version: each seat plate is a small brass-rimmed medallion at the table edge (life, commander portrait crop, priority ring), with the phase rail on the **local player's** medallion only. Opponents get just a current-step tick.
- **Avoid:** Arena's mirrored "you bottom, them top" placement of two medallions. Also avoid emote access on the life total, where a misclick costs a game action.

**M7. MTGA has no four-player mode, so geometry must be original**
- **Source:** MTGA product page (Brawl "is most similar to Commander", and you "play 1v1 games on MTG Arena") https://magic.wizards.com/en/mtgarena ; PowrDragn interview chapter [34:43 How Far Are We Away From Commander on Arena?](https://www.youtube.com/watch?v=AcY_H74tVXg&t=2083s) ; *Beginners Guide to Brawl*, eMpTyG, chapter [0:13 What is Brawl?](https://www.youtube.com/watch?v=STKeiAY4CBg&t=13s)
- **Demonstrates:** Arena's Commander-like formats are two-player, and its UI geometry is built for that.
- **Borrow:** Arena's *interaction* grammar (stops, inspector, stack, targeting beams, on-card status) applied to a **radial four-seat table** of Fyodor's own.
- **Avoid:** Arena's top/bottom split. It cannot express "left, across, right".

**M8. MTG-in-TTS: "who goes first" and seat management**
- **Source:** Table of Doom (S4 URL) ("Who goes first!", "auto player promoter") ; TeamDman guide (the table's die updates its faces to match the player count, and the die winner starts) ; Draftsim TTS guide ("roll the die in the center of the table") ; UberGuitarDude chapter [17:28 Who goes first?](https://www.youtube.com/watch?v=QJEqKZZ42K4&t=1048s)
- **Demonstrates:** Turn order is chosen by a physical die whose faces match the seat count.
- **Borrow:** Fyodor's planned authoritative d20 roll, shown physically on the table (as in `docs/GAME_NIGHT_FLOW.md`).
- **Avoid:** Auto-promoting players to host powers (a TTS workaround). Fyodor's permission model should not need it.

---

## 11. Spectator

**SP1. TTS: Grey spectator and Black Game Master**
- **Source:** TTS KB, *Player Roles* (M1 URL) ; Tools Menu Part 1a transcript (K4 URL)
- **Demonstrates:** Spectators (Grey) "cannot interact or manipulate anything", can control their camera, chat and read the rules notebook, and can take an open seat if allowed. The Game Master (Black) has "the all-seeing eye" and sees "Hidden Zones, Card Hands and all pages in the Notebook". The transcript also says "Hidden Zones do NOT prevent other players from interacting with your pieces."
- **Why it works:** Clear roles, and spectating costs nothing.
- **Borrow:** A free spectator camera with the same presets, a public log and a "Return to live game" control (in the brief).
- **Avoid:** **An omniscient seat**, and **hiding as a visual-only effect**. In Fyodor, hidden means *never sent to that client*, and permissions are checked by the server, not just made invisible.

**SP2. Conflicting community claims about TTS spectators**
- **Source:** Draftsim, Jeff Dunn, 2026-04-28 https://draftsim.com/tabletop-simulator-mtg/ ; TeamDman guide (H1 URL)
- **Demonstrates:** Draftsim says "When you can spectate, you have access to all hidden zones in the game (basically player's hands, cards that are face-down, or exiled face-down cards)". It also says spectators take open seats: "if you want to allow spectators at a 4-player table, you'll need to set the max players to 5 or more." TeamDman says "Grey (spectator) players cannot see hands and cannot interact with the table." The KB's Spectator section does not list hidden-information access.
- **Why it matters:** Players are unsure what spectators can see. That uncertainty is a trust problem in itself.
- **Borrow:** State plainly in the spectator UI: "Spectators see public information only." Spectators do not consume seats.
- **Avoid:** Any spectator "see all hands" mode. If ever wanted, it must be explicit, host-enabled, announced to all players and limited to finished games.

**SP3. Eliminated players become spectators**
- **Source:** Fyodor brief (`docs/UI_REDESIGN_BRIEF.md`, `docs/ELIMINATION_HUB.md`) cross-checked against SP1 and CA4
- **Borrow:** After elimination, show a short "Game continues" moment, then the spectator camera with the focus-seat presets (CA4), restrained reactions, and nothing private.
- **Avoid:** TTS's Blindfold (KB *Blindfold* https://kb.tabletopsimulator.com/player-guides/blindfold/). A full-screen curtain is the wrong metaphor for elimination.

---

## 12. Game flow (start, turns, end)

**G1. MTG-in-TTS: real-world setup sequence**
- **Source:** Draftsim TTS guide (SP2 URL) ; TheFeyheart, *Magic the Gathering X Tabletop Simulator Set-Up Tutorial*, chapters [2:34 Customize Your Playmat](https://www.youtube.com/watch?v=Hx9g3n0tg5Q&t=154s), [8:50 Turn Order Card](https://www.youtube.com/watch?v=Hx9g3n0tg5Q&t=530s), [13:00 Modeling Game Flow](https://www.youtube.com/watch?v=Hx9g3n0tg5Q&t=780s) ; UberGuitarDude chapters [10:05 Mulligans](https://www.youtube.com/watch?v=QJEqKZZ42K4&t=605s), [18:04 Turn](https://www.youtube.com/watch?v=QJEqKZZ42K4&t=1084s)
- **Demonstrates:** Draftsim's steps are: open the MTG Loader bag and paste a deck URL, drag the library, commander and tokens to their zones, delete the loader, shuffle, and "roll the die in the center of the table". TeamDman adds a mulligan button that shuffles the hand back in and draws 7.
- **Why it works:** (as a warning) It is about six manual setup steps before turn 1.
- **Borrow:** One "Ready" per player in the lobby, then a short, fixed sequence: countdown, commander intro, d20 order, mulligan bar (Keep / Mulligan with London bottoming). Each step is skippable and shows who is still deciding.
- **Avoid:** Making players place their own library or commander, or delete tools.

**G2. TTS: turn hand-off**
- **Source:** TTS KB, *Turns* (M2 URL)
- **Demonstrates:** End Turn at the top of the screen, and a sound plus prompt for the next player.
- **Borrow:** A distinct turn-start chime and a brief seat highlight sweep from the old active seat to the new one, in under 600 ms with reduced motion honoured.
- **Avoid:** End Turn as a top-bar button far from the table.

**G3. MTGA: timer and "rope"**
- **Source:** ASAP guide (CB1) ; MTG Arena Zone *Playing a Match* (S1) ; Hipsters 2018 (T9)
- **Demonstrates:** A per-turn clock that extends with each action, a burning "rope" near expiry, extensions earned over time, and an hourglass with remaining timeouts.
- **Why it works:** It protects strangers from stalling.
- **Borrow:** Only a **gentle "waiting on Player N for 2:00" indicator** visible to the waiting players, optional, with no forced pass. It suits a trusted pod.
- **Avoid:** Burning ropes, forced passes or timer pressure. The MTG Rocks accessibility article (AC2) reports that timer pressure is a barrier for some players.

**G4. Victory, defeat and recap**
- **Source:** No fetched MTGA or TTS source documents end-of-game screens. Fyodor's own spec is in `docs/UI_REDESIGN_BRIEF.md` and `docs/3D_DIRECTION.md` §7a.
- **Borrow:** From TTS, by negative example: TTS has no end state, so the table just stops. Fyodor's brief already defines short end scenes that keep the board visible.
- **Avoid:** Full-screen takeovers that hide the final board.

---

## 13. Visual art direction

**V1. Warm physical tables (Lenc, Table of Doom)**
- **Source:** Lenc gallery (T4) ; Table of Doom gallery: [atmospheric full table](https://images.steamusercontent.com/ugc/1648843044115634928/B333DA8154D0730229E04B021F12C8F33BB08056/), [low angle with physical buttons and counters](https://images.steamusercontent.com/ugc/1648843044115637707/2DBBE033A2A1A0E49585F0A76468F3C1901C9CA8/), [room variant](https://images.steamusercontent.com/ugc/1678115130076911199/56BFC169A0B3B07DF77D5442EAF643344AEF5BE9/)
- **Demonstrates:** The reference pack describes these galleries as wooden tables, quadrant playmats and a room environment. The Table of Doom page lists candles, toys (monarch crown, elk token, an Ugin alter) and a "Playmat Chest with over 55 playmats". I did not view the images.
- **Why it works:** Atmosphere makes online Commander feel like game night.
- **Borrow:** A real environment around the table (a dim room and warm key light) and one optional per-seat playmat image or texture choice in the lobby.
- **Avoid:** Toys and decor inside the play space during active play. A 55-playmat chest is a cosmetics menu, not table furniture.

**V2. TTS styling to leave behind**
- **Source:** tabletopsimulator.com https://www.tabletopsimulator.com/ ; TTS KB (lighting, context menu) ; reference pack §E
- **Demonstrates:** A sandbox aesthetic: technical menus (physics, scripting), mixed mod button styles and permanent instruction boards.
- **Borrow:** Only the physicality: card thickness, shadows, lift.
- **Avoid:** Every chrome element. One coherent UI kit (dark steel, leather and brass) for menus, chips, rails and plates.

**V3. MTGA effects discipline**
- **Source:** Battles article (C5) ; 2023.25.00 patch notes (S3)
- **Demonstrates:** A large VFX library (card-side effects, Convoke orbs, Prevent Damage effects) that has to be maintained per card shape.
- **Borrow:** Arena's *consistency*: every state has one visual. Use Fyodor's quieter vocabulary for it (engraved glyphs, brass edges, subtle depth).
- **Avoid:** Particle-heavy VFX, glow and halos. Every VFX also multiplies maintenance across card shapes (C5).

**V4. User screenshots: MTGA readability patterns [US-1]**
- **Borrow:** A large right-side inspector, glyph badges and P/T boxes are legibility patterns that carry over to brass and steel styling.
- **Avoid:** Arena's saturated fantasy UI frames, avatar art and coloured beam effects as literal styling.

---

## 14. Accessibility

**AC1. MTGA: large rules text toggle**
- **Source:** 2023.25.00 patch notes summary (S3 URL)
- **Demonstrates:** An accessibility toggle "for large rules text", which raises the minimum font size and adds a scroll bar.
- **Borrow:** A minimum inspector text size setting with scroll rather than shrink, and UI scale.
- **Avoid:** Shrinking Oracle text to fit a fixed box.

**AC2. MTGA: documented gaps**
- **Source:** Jason Coles, *Will MTG Arena Get Accessibility Options?*, MTG Rocks, 2021-04-23 https://mtgrocks.com/mtg-arena-accessibility-options/
- **Demonstrates:** Hard-to-read card names and Oracle text, low colour prominence for key information, and timer pressure. The article cites a proposal to treat hand and board as **keyboard-navigable lists**, read cards aloud, and offer short and long descriptions.
- **Borrow:** Hand, each battlefield, the stack and prompts as keyboard-navigable lists (arrow keys plus Enter on the focused card), with visible focus rings. Text alternatives for every seat-colour cue.
- **Avoid:** Pointer-only interactions.

**AC3. TTS: remappable keys, Alt zoom, magnify, multi-modal ping**
- **Source:** K9, C1, CA2, K4
- **Borrow:** Remapping, the hold-to-inspect overlay, the magnify lens, and pings that combine colour, name and sound.
- **Avoid:** Colour-only signals: TTS pings, MTGA orange/blue stops and seat-colour dots.

**AC4. Reduced motion and no time pressure**
- **Source:** G3 ; Fyodor `docs/GAME_UI_MOTION_RESEARCH.md`
- **Borrow:** Every flourish (turn sweep, card travel, end scene) honours reduced motion and a global speed multiplier, and is skippable.
- **Avoid:** Any animation that game state waits on.

---

## 15. MTG inside Tabletop Simulator: dedicated review (KEEP / IMPROVE / DON'T COPY)

Priority order follows the user's reference pack. Gallery links are on the Workshop pages. The
reference pack (`/tmp/ui-research/MTG_TTS_REFERENCE_PACK.md` §C) lists direct images. I confirmed that
those image URLs appear on the fetched pages, but I did not view the images.

### 1. Oops I Baked a Pie, *MTG 4 player table - scripted* (2296042369)
https://steamcommunity.com/sharedfiles/filedetails/?id=2296042369 · video guide: UberGuitarDude https://www.youtube.com/watch?v=QJEqKZZ42K4 (chapters from 0:41 to 18:36, cited above) and DianaOfTheRose, *How to play Magic online in Tabletop Simulator!* https://youtube.com/shorts/IFYNLktZ6j4
- **What it has (page, fetched):** Context menus on the library (Cascade, Reveal until Type, Fetch Basic Land), on the hand (Sort Hand by CMC, Random Discard) and on certain cards (clone, morph, cascade). Scripted card buttons for P/T, +1/+1 and loyalty. Mulligan / Untap / Draw / Scry / Mill / Reveal buttons. Numpad hotkeys (K8). Playmats by typing "playmat imageURL" into chat. Related 6- and 8-seat versions. It credits Tipsy Hobbit's Encoder, Tyrant's Easy Modules, a sticker module and a morph module.
- **KEEP:** Four-seat distribution with each player's chores at their own seat. **Object-aware menus**: library actions on the library, hand actions on the hand. The specific Commander chores it automates (cascade, reveal-until-type, fetch basic land). Bulk selection-to-zone moves.
- **IMPROVE:** Make each chore a rules-aware or manual-macro action with a preview ("Cascade: revealing… stop at CMC < 5") and one undo step. Show hotkeys inside menus. Make scry and reveal private or public according to the rules, enforced by the server.
- **DON'T COPY:** Per the reference pack: excessive buttons and tiny text. Per the page: instruction blackboards, "ghost cache scripts", and chat-command configuration. Fragmentation across several community scripts with different styles.

### 2. Lenc, *Magic the Gathering Table - MTG EDH* (2425949312)
https://steamcommunity.com/sharedfiles/filedetails/?id=2425949312
- **What it has:** 2–4 players. A draw and an untap button per player. Infinite bags. URL playmats per player. Turn tracker. MTG Deckboxes (deckboxes act as bags for decks, cards and tokens). Ability Counters. Encoder plus Easy Modules. A per-player "black hole" zone. Commander counters colour-matched to seat. A Scryfall chat importer.
- **KEEP:** The **warm wood table with clearly separate quadrant mats** (closest to Fyodor's look). Deckboxes as physical homes for a player's deck, tokens and sideboard. Colour-to-position consistency. Generous mat space.
- **IMPROVE:** Replace the black hole (a delete zone) with a reversible "remove from game" action. Replace URL playmats with a curated, offline set of per-seat mat textures. Put the turn tracker on the table (M2).
- **DON'T COPY:** Decor and extra objects in the play area. Reliance on live Scryfall and importer services. The page's comments record Scryfall blocking UnityPlayer traffic, and the community reports importers breaking.

### 3. OTTOREIKU, *Minimal MTG* (2066242375)
https://steamcommunity.com/sharedfiles/filedetails/?id=2066242375
- **What it has:** Four seats, a GM and spectators. A scripted turn tool, deck loaders, untap and draw. A separate scry zone. Snaps for lands, companion, turn marker and City's Blessing. A zone protection tool. Tokens. The author's mat legend is in T7.
- **KEEP:** The **minimalism as a goal** ("clean and easy to use without needing all of the bells and whistles"). A fixed home on the mat for each Commander number (per-opponent commander damage, cast count, partner slot, "C" zone).
- **IMPROVE:** Make those homes live data (engine-tracked, with manual adjustment allowed). Give the scry zone a complete flow, top/bottom per card, inside a private drawer.
- **DON'T COPY:** Partially working helpers. A GM seat. Losing priority and stack clarity in the name of minimalism (pack). Fyodor needs the stack and priority indicators that TTS lacks.

### 4. schoob, *Mtg EDH Table of Doom! - 4 player magic* (2278483976)
https://steamcommunity.com/sharedfiles/filedetails/?id=2278483976
- **What it has:** A playmat chest (55+), card importer, "Who goes first!", Pirate's Cannon, auto player promoter, ability counters, infinite bags, **response buttons**, a scry zone, mill buttons, planeswalker and creature counters, a 7-card mulligan button, a monarch crown, an elk token, an Ugin alter and candles. Comments report life-counter errors and a Moxfield import failure.
- **KEEP:** **Social personality**: response buttons, the monarch crown as a physical seat badge, a who-goes-first ritual.
- **IMPROVE:** Response buttons become Fyodor's rules-aware RESPOND/PASS plates (S4). The monarch crown becomes a seat badge driven by game state (M5). Toys move to a lobby or between-games space.
- **DON'T COPY:** Novelty objects on the active table (cannon, candles, alters) and visual clutter during play (pack).

### 5a. Tipsy Hobbit and Tyrant, *Easy Modules for MTG Encoder* (2246039633)
https://steamcommunity.com/sharedfiles/filedetails/?id=2246039633 · video https://www.youtube.com/watch?v=5cwPxnI1Enw · [US-2]
- **KEEP:** **State and controls live on the card.** Left-click increments and right-click decrements. Planeswalker abilities shown as buttons. A colour-coded ownership gem. Exact Copy that keeps counters.
- **IMPROVE:** Controls appear on hover or selection only. Use a fixed chip layout that respects tapped and sideways orientation (C5). Add an ownership marker that is also non-colour, such as a seat initial. Keyboard equivalents for each stepper.
- **DON'T COPY:** Button rings and sidebars around each card. Chat-command toggles. Dependence on an online importer for oracle data. The author has also recommended another table instead, per the comments.

### 5b. V, *MTG Portable Playmat [scripted]* (3651317655)
https://steamcommunity.com/sharedfiles/filedetails/?id=3651317655
- **KEEP:** **Auto-arranged land row plus a free battlefield** (T6). Hover + one key to tap. A centred face-down library. A token spawner grid that opens on demand.
- **IMPROVE:** Collapse identical lands into piles (C6). Make the token picker searchable and show recent tokens first. Make the arrangement live and deterministic, with no "scale fix" settling.
- **DON'T COPY:** Over-rigid snapping. The pack warns against "overly rigid snapping that removes sandbox positioning".

### Secondary: Xilisys, *MTG Commander 4-player* (2681557055)
https://steamcommunity.com/sharedfiles/filedetails/?id=2681557055 . Beginner info cards, a deck loader and a scry fix. KEEP the idea of newcomer help. DON'T COPY permanent instruction cards on the table (pack). Use dismissible first-use hints instead (`docs/TTS_QOL_RESEARCH.md` P4).

### Guides

**TeamDman, *MTG / TabletopSimulator.md*** https://github.com/TeamDman/Guides/blob/master/MTG/TabletopSimulator.md
- **What it shows:** Practical play: P cycles cameras ("sometimes gets hit accidentally"), Space resets, Alt to preview, Alt+Shift to peek at a deck's bottom card, H hides the hand ("Mostly done by accident"), typing a number on a hovered button, Alt+right-click drops the bottom card of a held deck, "spread" a deck, G to group, Ctrl+C/V for tokens (loses counters, so use exact-copy), "frozen" via the encoder, L to lock, Ctrl+click to force-select, teams to show a hand, Black GM sees all hands, Grey spectators can't, Ctrl+Z rewind is slow with scripts, and "continue as if it was paper magic".
- **KEEP:** Its list is the **real verb inventory** of TTS Commander. Use it as a coverage checklist for Fyodor's hotkey registry.
- **IMPROVE:** Every workaround it teaches (teams to reveal, exact-copy versus copy, frozen counters) should become a first-class action.
- **DON'T COPY:** Rewind-based undo. Fyodor's per-action undo is already better.

**Draftsim, *How to Use and Set Up Tabletop Simulator to Play Magic: the Gathering*** (Jeff Dunn, 2026-04-28) https://draftsim.com/tabletop-simulator-mtg/
- **What it shows:** Purchase and setup, the deck loader (Archidekt, Deckstats, Frogtown, MTGGoldfish, Moxfield, Scryfall), dragging library, commander and tokens to zones, deleting the loader, shuffling, mulligan button, rolling the centre die. Pros: closeness to paper, scripted shortcuts, hotkeys. Cons: cost, no mobile, hardware demands, add-ons required.
- **KEEP:** "As close as you can get to the real thing" is the bar for feel.
- **IMPROVE:** Collapse its 5+ setup steps into Ready → countdown (G1). Deck import yields physical library and commander objects already in place.
- **DON'T COPY:** The spectator model it describes, where spectators occupy seats and may see hidden zones (SP2).

**TTS KB, *Context Menu*** https://kb.tabletopsimulator.com/player-guides/context-menu/
- **KEEP:** Object-specific actions first and common actions below. A global menu on empty table. The menu applies to the whole selection (K1).
- **IMPROVE:** Show hotkeys in the menu. Filter by legality and state. Keep it shallow.
- **DON'T COPY:** Player-facing Physics, Scripting, Tint and Toggles sections.

### Side-by-side, TTS physical tabletop versus Fyodor (to do)
The pack's checklist asks for rendered Fyodor screenshots (a normal four-player board and a crowded board)
compared against these tables. **That was not done in this pass** because the task was research only. It
is listed as a follow-up in §18.

---

## 16. User-supplied screenshots (described, not stored)

The coordinator described these. I did not view them. Nothing was saved.

**[US-1] MTG Arena, four screenshots**
- Battlefield with **lands in a back row and creatures in front**, with **P/T boxes and ability glyph badges** on cards.
- The player's **avatar in a medallion**, life below it, and **phase-stop icons on a rail around it**.
- A **large hover card inspector on the right side**.
- **Curved targeting beams** from a source to its target.
- **Identical lands stacked with an "x4" count**.
- The **hand fanned along the bottom edge** with mana costs showing.
- A big **hourglass "Pass / Next" button bottom-right** with an **"End Turn" toggle**.
- A hint above the hand: **"You will need to discard down to 7 at the end of your turn."**

*Lessons used:* T9, C4, C6, H2, H3, M6, A1, V4, and S1 and CB1 for targeting beams. **Pass / Next and End
Turn:** borrow one primary, always-in-the-same-place "advance" control near the local player's seat (for
Fyodor: PASS, plus a toggle for PASS UNTIL END OF TURN). Its label should change with context (Pass /
Resolve / Next step / Done), as Arena's does. Don't copy the giant hourglass art or the fixed bottom-right
corner if that corner sits over table space in a four-seat layout.

**[US-2] TTS "MTG Card Encoder" overlay**
- Buttons attached around a card on hover: **flip DFC, +1/+1, power/toughness toggle, counters, copy,
  re-import, get tokens and emblems**.
- Right-click on a hand card: **"Sort by CMC / Randomly discard"**. Right-click on the deck: **"Cascade for X
  / Reveal until type / Get basic land"**.

*Lessons used:* C3, H4, A4 and §15 items 1 and 5a. The pattern to keep is **object-scoped actions**. The
pattern to drop is **many always-visible buttons in a ring**.

**[US-3] TTS top-down six-seat table**
- **Three mats per side**, each **outlined in its seat colour**, with a **column of per-seat counter icons**
  (life, poison and others) along each mat's edge. **Deck boxes and a dice/token tray** at the table ends.

*Lessons used:* T8, M3. Keep the outline-plus-edge-counter-strip idea. Design for four seats and keep
the centre clear for the stack and combat.

---

## 17. Top 15 principles for Fyodor (ranked by impact)

1. **Table first: four territories, free placement, optional order.** Each seat is one fixed anchor
   (mat, hand, command zone, counters). The land row tidies itself and collapses identical lands, while
   the battlefield stays free, with ghost-slot alignment only during drag. *(T1, T2, T6, T9, Portable
   Playmat)*
2. **Always answer "what are we waiting for, and on whom?"** Put one compact indicator on the table
   (priority ring on a seat plate, "Waiting for Player 3: choosing blockers"), identical for "thinking"
   and "about to auto-pass" so it never leaks information. *(A1, A2, M2, M6)*
3. **Hidden means not sent.** The server enforces privacy and permissions. There is no omniscient seat,
   spectators see public information only and never take seats, and every legal private look shows a
   seat-and-name "peeking" marker to others. *(SP1, SP2, C1, H1)*
4. **Object-aware actions with one grammar.** Hover + key for verbs, a right-click menu that lists only
   actions relevant to the object (with hotkeys printed), the same menu applied to a multi-selection,
   table-level actions on empty felt, and hand-level actions on the hand strip. *(K1, K2, K8, H4)*
5. **State lives on the card.** P/T box, keyword glyph tray, counters, marked damage (never shown as
   lowered toughness), owner and controller marks, and modified-state chips. They are readable at rest,
   become steppers on hover, and are laid out against an oriented box so they survive tapping and sideways
   cards. *(C3, C4, C5, C7)*
6. **Preview before commit; undo after.** Legal targets lit with reasons for exclusions, a cost preview
   with a suggested-sources ghost (the player still taps), a pending "Draw 12…" chip, and one-action undo.
   *(P1, A3, K3)*
7. **Choices happen on the table.** Object choices are clicked in place with a slim instruction bar,
   abstract choices use a compact button or radial row, and "Are you sure?" is used only for likely
   self-harm. Unsupported or partial cards hand off to manual play cleanly instead of half-acting.
   *(P2, P3, T7)*
8. **A phase rail with stops, at the player's seat.** Click a step to toggle a stop. Own-turn and
   other-turn stops differ by shape and colour, the stop's lifetime is stated, and there is one primary
   "advance" control whose label changes with context. *(A1, US-1, K6)*
9. **Piles for identical things.** Lands and tokens collapse to ×N with a tapped/untapped split. The
   count is a bulk selector, and a pile splits automatically when its members diverge. *(C6, CB1)*
10. **Four-player combat as declarations with beams.** Multi-select attackers, then click a defender
    plate, planeswalker or battle. Beams run from source to defender, there is a per-defender "unblocked"
    summary, and an optional lane view. Placement serves "combat feeling right". *(CB1–CB4)*
11. **Seat identity is spatial, not just colour.** Seat colour plus name or initial plus position. A
    commander-damage row on each mat ordered left / across / right, with a 21 tick and auto-expand near
    lethal. Seat badges for Monarch, Initiative and City's Blessing. Every life change logged with its
    source. *(T4, T7, M3–M5)*
12. **No camera skill required.** A default framing that reads all four seats, smooth reset, quick zoom
    to the cursor and back, numbered seat presets, focus-seat and pinned picture-in-picture views, and a
    magnify lens. No camera modes or first-person flying. *(CA1–CA4)*
13. **Table-native social signals, rate-limited.** Ping with colour, name and chime. A "responding"
    plate. Turn chime and seat sweep. Optional "waiting 2:00" without timers. *(K4, S4, G2, G3)*
14. **One coherent card-room visual system, no clutter.** Curated walnut, felt, steel and brass lighting.
    No user-tuned LUTs, decor or toys on the active table, permanent instruction boards, glow or VFX
    particles. Consistency over spectacle. *(T10, V1–V4, §15)*
15. **Accessible and remappable by default.** A "?" cheat sheet generated from the hotkey registry,
    remapping, a cross-product key-conflict audit (Space, P, Tab, Enter), large rules text, keyboard-
    navigable hand, board and stack lists, never colour alone, and reduced motion everywhere.
    *(K9, K10, AC1–AC4)*

---

## 18. Open items and follow-ups

- Render real Fyodor screenshots (normal four-player and crowded boards, 1920×1080 and 2560×1440) and
  compare them against the Lenc and Oops galleries for table-to-screen ratio, card legibility, depth and
  clutter. This is pack checklist items 3 and 6, and was not done here.
- Watch the chaptered videos above, especially UberGuitarDude 13:44 *Card Buttons* and PowrDragn 6:30
  *Autotapper*, to confirm the visual details that the chapter titles only imply.
- Audit Fyodor's default key bindings against TTS and MTGA muscle memory (K10). Decide whether to offer an
  "Arena-style" preset.
- Find an official Wizards source for MTGA's current targeting-beam and end-of-game presentation, if one
  exists. None was found in this pass.

---

## Appendix A. Sources fetched (2026-10-31)

**Tabletop Simulator (official)**
- KB home https://kb.tabletopsimulator.com/ (and source repo https://github.com/Berserk-Games/Tabletop-Simulator-Knowledge-Base)
- Controls & Movement https://kb.tabletopsimulator.com/player-guides/basic-controls/
- Advanced Controls https://kb.tabletopsimulator.com/player-guides/advanced-controls/
- Context Menu https://kb.tabletopsimulator.com/player-guides/context-menu/
- Camera Control https://kb.tabletopsimulator.com/player-guides/camera-states/
- Player Hands https://kb.tabletopsimulator.com/host-guides/player-hands/
- Zone Tools https://kb.tabletopsimulator.com/game-tools/zone-tools/
- Flick Tool https://kb.tabletopsimulator.com/game-tools/flick-tool/
- Snap Point Tool https://kb.tabletopsimulator.com/game-tools/snap-point-tool/
- Line Tool (ping) https://kb.tabletopsimulator.com/game-tools/line-tool/
- Gizmo Tool https://kb.tabletopsimulator.com/game-tools/gizmo-tool/
- Grids https://kb.tabletopsimulator.com/host-guides/grids/
- Turns https://kb.tabletopsimulator.com/host-guides/turns/
- Permissions https://kb.tabletopsimulator.com/host-guides/permissions/
- Lighting https://kb.tabletopsimulator.com/host-guides/lighting/
- Tables https://kb.tabletopsimulator.com/host-guides/tables/
- Player Roles https://kb.tabletopsimulator.com/getting-started/player-roles/
- Changing Color https://kb.tabletopsimulator.com/player-guides/changing-color/
- Teams https://kb.tabletopsimulator.com/player-guides/teams/
- Notebook https://kb.tabletopsimulator.com/player-guides/notebook/
- Blindfold https://kb.tabletopsimulator.com/player-guides/blindfold/
- In-Game Communication https://kb.tabletopsimulator.com/getting-started/in-game-communication/
- Help Menu https://kb.tabletopsimulator.com/getting-started/help-menu/
- Custom Deck https://kb.tabletopsimulator.com/custom-content/custom-deck/
- Video Tutorials (with transcripts) https://kb.tabletopsimulator.com/getting-started/video-tutorials/
- Product site https://www.tabletopsimulator.com/

**TTS community**
- Chris Backe, *Tabletop Simulator 105* (2021-07-01) https://entrogames.substack.com/p/tabletop-simulator-105-navigating-keyboard-shortcuts-and-saving-time
- TeamDman guide https://github.com/TeamDman/Guides/blob/master/MTG/TabletopSimulator.md
- Draftsim TTS guide (2026-04-28) https://draftsim.com/tabletop-simulator-mtg/
- Workshop: 2296042369, 2425949312, 2066242375, 2278483976, 2246039633, 3651317655, 2681557055 (URLs in §15)

**MTG Arena (official)**
- Product page https://magic.wizards.com/en/mtgarena ; Alchemy https://magic.wizards.com/en/mtgarena/alchemy
- Ian Adams, battles (2023-05-29) https://magic.wizards.com/en/news/mtg-arena/we-put-battles-on-mtg-arena-what-was-that-like
- Alex Werner, Powered Cube (2025-10-23) https://magic.wizards.com/en/news/mtg-arena/dev-diary-creating-arena-powered-cube
- Alex Werner, Living Breakthrough (2023-07-31) https://magic.wizards.com/en/news/mtg-arena/on-whiteboards-naps-and-living-breakthrough

**MTG Arena (community)**
- MTG Arena Zone hotkeys (2022-08-24) https://mtgazone.com/arena-hot-keys-and-interface-guide-simplify-your-game-with-these-easy-tricks/
- MTG Arena Zone *Playing a Match* (2022-08-24) https://mtgazone.com/playing-a-match/
- MTG Arena Zone 2023.25.00 patch notes https://mtgazone.com/2023-25-00-patch-notes/
- ASAP beginner's guide https://sites.google.com/view/asap-bg-to-mtga/playing-a-match
- Beginner's guide hotkeys https://sites.google.com/view/beginners-guide-to-mtga/hotkeys-and-using-the-interface
- Flipside Gaming (2019-01-22) https://flipsidegaming.com/blogs/magic-blog/mtg-arena-hot-keys-and-using-the-interface
- Draftsim keyboard shortcuts (2024) https://draftsim.com/mtg-arena-keyboard-shortcuts/
- Draftsim settings (2025-10-14) https://draftsim.com/mtg-arena-settings/
- Hipsters of the Coast in-match screen (2018-03-23) https://www.hipstersofthecoast.com/2018/03/how-to-play-mtg-arena-the-in-match-screen/
- MTG Rocks accessibility (2021-04-23) https://mtgrocks.com/mtg-arena-accessibility-options/

**Four-player Commander comparisons**
- SpellTable beta, WPN (2021-03-16) https://wpn.wizards.com/en/news/remote-magic-made-easy-spelltable-beta
- TableCommander, Life & Counters https://tablecommander.com/docs/gameplay/life-counters

**Videos (titles and channels confirmed via oEmbed; timestamps are the creators' chapter markers; footage not viewed)**
- UberGuitarDude, *MTG Commander Online!? (Full Tutorial)* https://www.youtube.com/watch?v=QJEqKZZ42K4
- TheFeyheart, *Magic the Gathering X Tabletop Simulator Set-Up Tutorial* https://www.youtube.com/watch?v=Hx9g3n0tg5Q
- LightRanger Games, *Tabletop Simulator: What I Wish I Knew: For Beginners* https://www.youtube.com/watch?v=zpwNV1MECXM
- Berserk Games tutorials (transcripts on KB): SGPdpGn0DCM, n5JfRMava7w, CUUin0rga5k, dGFxC-ideJI, 4QKE0N9eRpo
- TyrantNomad, *Easy Modules for MTG Encoder* https://www.youtube.com/watch?v=5cwPxnI1Enw
- DianaOfTheRose, *How to play Magic online in Tabletop Simulator!* https://youtube.com/shorts/IFYNLktZ6j4
- PowrDragn, *Creator Accounts? Autotapper Broken? …* https://www.youtube.com/watch?v=AcY_H74tVXg
- That Design Feel Side Quest, *Biggest UI issues MTG Arena* https://www.youtube.com/watch?v=F4GXdrMJF0o
- Kappolo, *Optimal MTG Arena Settings* https://www.youtube.com/watch?v=7n_sKGxUMIs
- MattSperlingMTG, *Bluffs, Tells, Tips, and Tricks using the Magic ARENA interface* https://www.youtube.com/watch?v=ouaTIF_gHY8
- Jumpstart My MTG Heart, *How to Use Full Control* https://www.youtube.com/watch?v=BN9KIcO0xIg
- eMpTyG, *Beginners Guide to Brawl* https://www.youtube.com/watch?v=STKeiAY4CBg
- Magic: The Gathering, *How to Play MTG Arena* (closed-beta interface walkthrough; no chapters) https://www.youtube.com/watch?v=g0dTL9wyscQ

## Appendix B. Seen only in search results (not fetched, not relied on)

The MTGA support-site patch notes (403), the TTS nolt.io feedback board (403), the AetherHub MTGA hotkeys
article (403), the Wizards feedback forum (private), and a TTS spectator-window guide (404). Search
snippets suggested several things that this study does **not** rely on: a "View Simplified" card-frame
toggle in MTGA, MTGA stops that clear after a turn, TTS `spectator_window` console commands, and players
confusing "Spread" with "Search" on TTS decks. Each should be verified before anyone cites it.

---

## 19. Audit of the current Fyodor (2026-10-31)

Taken from the running app with the fixture card database (text cards, no art), at 1920×1080, 1600×900 and 1366×768,
on the 2D and 3D tables. Screenshots of the running app were reviewed for each item; none of this comes from mockups.

| Component | Verdict | Why (reference) | Action |
|---|---|---|---|
| 3D table shell: walnut rim, felt mats stitched in the seat colour, candles | **KEEP** | It already reads as a physical card room, like Lenc's wood EDH table, without TTS's clutter of props | Keep. Later: real card art in screenshots, mat territory labels |
| Four-seat cross layout (me at the bottom, three opponents) | **KEEP** | The four clear territories that the reference pack's "four clearly defined territories" asks for | Keep. Watch the left and right mats, which are cut at the screen edge in the seat view |
| Seat plaques (portrait, life numeral, Cmdr dmg, Poison, Hand) | **REFINE** | Like Arena's avatar medallion; TTS tables put per-seat counters at the mat edge | Side seats show only name and life (compact): fine. Make sure commander damage taken *from me* reads on hover |
| Hover inspector (big card, top right) | **KEEP** | Arena's enlarged card on hover | Keep. It overlaps the right-hand seat's mat while open: acceptable, it's transient |
| Turn dial (bottom right: phase rail, big brass action, Next turn) | **KEEP** | Arena's "Next / End Turn" plus timer; "say what a button does" ("To upkeep", "Resolve top") | Keep |
| Selection toolbar, fixed at the bottom centre | **REDESIGNED** | The TTS encoder attaches controls to the card ("controls should travel with the card", pack §B) | Now attached above the selected card, with a notch, in 2D and 3D (follows the camera) |
| Stack: cards at the table centre, numbered, "Resolves next" | **KEEP** | Arena's stack clarity, on a TTS-like table | Keep |
| Target beams (curved, ice/brass) | **KEEP** | Arena's targeting arrows | Keep. They're thin cords with no glow, per DESIGN.md |
| Hand fan (bottom arc, lifts on hover) | **KEEP + extended** | Arena's hand; the TTS encoder's "Sort by CMC" | Sorting added (as drawn, mana value, colour, type, name), display only |
| Pointing at things | **ADDED** | TTS pointer and ping | Pings: G / Alt+click, a seat-coloured ring and name for everyone, never on hidden cards |
| Identical basic lands spread across the mat | **REDESIGN (next)** | Arena stacks identical lands ("x4"); the Portable Playmat auto-arranges land rows, *optionally* | Planned: an optional "Tidy lands" helper that piles identical untapped lands, never forced |
| Tool tray (Tokens, Dice, Hand), bottom left | **KEEP** | Table toys, secondary and hideable (pack §D5) | Keep. Hidden by the minimal HUD |
| Log pill (bottom right) | **KEEP** | Quiet, expandable | Keep |
| Coach tips banner (top centre, first run) | **REFINE** | It covers the opponent's mat on first entry | Later: anchor it to the element it explains, or dock it in the top bar |
| 2D table: player panels, piles, command zone | **REFINED** | It fell apart at 768 px tall (commanders cut off) | Fixed earlier in this PR. Piles and command zone share a row on short screens |
| Settings, Play, Decks, Pod stats pages | **REFINED** | Web-app pages around the game, but in the card-room look (plaques, brass, Cinzel) | Grid, alignment and empty-state fixes in this PR. They stay "Operate" pages: precise, not decorative |
| Generic-AI signals (neon, glassmorphism, purple gradients, giant rounded cards, sidebars) | **none found** | | The theme-tile and deck-tile glows were the last glows outside the table; both removed earlier in this PR |

### Not yet comparable
- Real card art: every screenshot uses the fixture database (text cards). Art changes the table's colour balance more
  than anything else; repeat the screenshots with a real deck's cached art before judging colour and density.
- Large boards (300–500 objects): the 3D perf specs exist (`e2e/table3d-shots.spec.ts`, run with `SHOT_DIR`) but
  weren't re-run in this pass.

## 20. What this pass built, and the critique that checked it

These follow from principles 1, 4, 9 and 13 above and the user's screenshots (the TTS encoder, Arena's stacked lands).
Each was checked in the running app, 2D and 3D.

| Built | Reference | Where |
|---|---|---|
| Selection toolbar attached to its card: notch, follows the 3D camera, flips around the dial and response bar, hides when its card is off-screen. Actions depend on the card type (creatures: +1/+1 counter, Damage…; others: Counter…; Turn over for double-faced cards) | TTS encoder (US-2), principle 4 | `game/Hud.tsx`, `game/anchors.ts`, `table3d/Table3D.tsx` |
| Right-click on empty table opens a Table menu (Tidy my lands, Select, Clean up) | TTS table context menu, principle 4 | `game/selection.ts`, `game/Battlefield.tsx`, `table3d/TableScene.ts` |
| "Tidy my lands" piles identical lands along my edge, basics in WUBRG first, in one undoable `set_position` move. It's optional and never automatic | Arena "x4" lands (US-1), Portable Playmat, principles 1 and 9 | `game/tidy.ts` |
| Pings (G / Alt+click): seat colour and name, never on hidden cards, pinned to the screen edge when off-screen | TTS pointer/ping, principle 13 | `game/Pings.tsx`, `game/ping.ts`, `api/night.py` |
| Hand sorting: as drawn, mana value, colour, type, name | TTS encoder "Sort by CMC", Arena hand | `game/handSort.ts`, `game/Hand.tsx` |
| Background turn alert (tab hidden or window unfocused) | Arena's turn cue, principle 13 | `game/turnAlert.ts` |
| Selected card's edge in brass in 3D; ice kept for priority only | DESIGN.md colour rules | `table3d/TableScene.ts`, `table3d.css` |

**Impeccable critique** (dual-agent, snapshot in `.impeccable/critique/`):
- Scored 26/40 before fixes. The P1 and three of the four P2s were fixed in the same pass (listed in the snapshot).
- The detector scan came back clean.
- The browser pass found four accessibility issues; all are fixed:
  - unnamed form controls;
  - glyph-only buttons;
  - 23 px targets;
  - one 4.15:1 contrast.

## 21. Second pass: the six follow-ups

| Follow-up | Status | What |
|---|---|---|
| ×N land piles | **Done (display only)** | Identical noncreature lands overlapping in a row (Tidy builds exactly that; hand-made piles count too) show **×N** on the top card. In 2D it's a brass-edged chip; in 3D it's a plate in the card overlay. Nothing is grouped on the server, so tapping one or dragging one out just changes the count. Built in `game/piles.ts`, which is unit-tested, including against Tidy's own output |
| "My order" for the hand | **Done** | Dragging inside a sorted hand keeps what you see, with the move applied, as "in my order". It's per game, in session storage, and display only. In "as drawn", a drag still reorders the hand on the server. e2e: `pings-hand.spec.ts` |
| The 2D table | **Done (§24)** | First step: 2D player panels took the 3D seat plaque's identity (portrait in the seat colour, brass ring for the active seat, name and life numeral) and a wide, short mat stopped pushing near-edge cards off the felt. Then the rework in §24: the 3D plaque itself on every 2D seat, opponents' zones in a strip along their edge, full-width mats, readable card sizes and a Look view |
| Discoverability | **Done** | Each toolbar action shows its key (T, F), following remapping (`keyLabel`), plus a "G ping" chip. A one-time tip appears the first time you hover a public card at a LAN table |
| Key audit | **Done** | §22, plus an Arena keys preset |
| Real-art screenshots and perf | **Done** | §23 |

## 22. Key audit against Tabletop Simulator and Arena (done)

Fyodor's defaults are in `frontend/src/game/hotkeys.ts`. The TTS and Arena columns come from K10 and the sources it
cites. The question for each key: does a key that is harmless in TTS or Arena do something here that can't be undone?

| Key | Fyodor default | MTG Arena | Tabletop Simulator | Verdict |
|---|---|---|---|---|
| Space | Tap / untap the hovered or selected card | Pass priority | Reset camera | Safe: a tap is undoable and never passes priority. The **Arena keys** preset (Settings → Keys) makes Space pass priority instead, for players who want the Arena habit |
| P | Pass priority (manual play: the dial's main button) | — | Camera mode | Kept. A TTS player gets a pass, not a camera change. The dial says what P will do, and in rules mode nothing irreversible happens before the stack resolves |
| Enter | Play the focused hand card (keyboard access) | Pass until a response | — | Kept. It acts only on the keyboard-focused card, so it never fires by accident from the table |
| Tab | Moves keyboard focus | — | Pointer / ping | **Not** used for pings (WCAG 2.1.1: Tab must move focus). Fyodor pings with **G** or Alt+click |
| F | Turn over (double-faced card) | — | Flip | Same as TTS |
| T | Tap | — | — | — |
| G | Ping | — | — | Unique, so no conflict |
| S | Sort hand (cycle) | — | — | Display only, harmless |
| Ctrl+Z / Ctrl+Shift+Z | Undo / redo | — | Undo | Same habit |

Done in this pass:
- **Arena keys preset** (`KEY_PRESETS`, Settings → Keys). Space and P pass priority; T alone taps.
- **Fyodor keys** resets to the defaults.
- A unit test checks that every preset is free of collisions.
- The card toolbar prints each action's key, and follows remapping (`keyLabel`).

## 23. Real-art comparison and performance (second pass)

**Setup:**
- The real Scryfall database: 116,863 printings, downloaded with the in-app updater.
- Four decks: the two sample decks plus Meren and Edgar Markov. Every card resolved.
- Art cached for all of them: 203 images.
- About 20 permanents per seat, plus tokens, counters, damage and an attack.
- Every seat's lands were tidied.
- Shots: 1920×1080 and 2560×1440 in 3D (seat and Table cameras), and 1920×1080 and 1366×768 in 2D.

**Against the Lenc and Oops galleries** (TTS wood EDH tables):
- **Table-to-screen ratio:** the table fills the screen edge to edge in both cameras. Chrome is limited to the thin top bar, the dial (bottom right), the tray (bottom left) and the plaques, so it holds up against the TTS tables, which give more space to props and instruction boards.
- **Card legibility:** with real art, cards read by art at seat distance as they do in TTS. Names need the hover inspector or the selected-card tag, which matches Arena.
- **Land piles:** in TTS, players pile lands by hand. Here Tidy plus ×N gives the Arena count without taking away free placement.
- **Depth:** cards have edges and contact shadows, and the mats are stitched felt. There is no clutter: no dice cannons, toys or instruction cards on the table (the pack's "don't copy").
- **Gaps against TTS:**
  - The side seats' cards read sideways (true of a real table too).
  - At 1366×768 in 2D, a 30-card opponent hand becomes a long strip of card backs. Collapsing it to "30 ▮" past a dozen cards is a follow-up.

**Performance** (`e2e/table3d-shots.spec.ts` with `SHOT_DIR`, headless Chromium with software WebGL, so FPS isn't meaningful; the numbers to watch are draw calls, triangles and CPU per frame):

| Board | Draw calls | Triangles | CPU per frame |
|---|---|---|---|
| 68 cards, real art, four seats | 150 | 119k | 2.5 ms |
| 100 permanents (fixture) | 173 | 86k | 11.2 ms* |
| 300 permanents (fixture) | 277 | 222k | 5.3 ms |

\* Includes the first frames after loading. The 300-permanent board settles lower. Draw calls grow sublinearly, through instancing and shared materials (the existing `threejs-performance` work). None of this pass's additions draws every frame: the ×N plate is baked into the card's overlay texture, and the toolbar and pings are DOM, placed by the existing frame loop or once on arrival.

## 24. The 2D table rework (third pass)

**The complaint:** "2D seems extremely hard to see what's going on on an opponent's board." The cause was width. Three
opponents shared the top row, and each also gave about 150px to a panel column beside its mat, so their cards were
drawn about 50px wide at 1920×1080 and about 37px at 1366×768.

**What changed** (`game/PlayerArea.tsx`, `game/SeatPlate.tsx`, `game/geometry.ts`, `game/game.css`):
- **One plaque for both tables.** The 3D seat plaque moved to `game/SeatPlate.tsx` and is used on every 2D seat as
  well, with life steppers and the LAN connection state added in 2D.
- **Opponents: a strip, then the mat.** An opponent's plaque, library, graveyard, exile, command zone, hand count and
  a **Look** button sit in one strip along their edge (as on a real playmat), so the mat below gets the seat's full
  width. Your own plaque and zones stay in a slim rail beside your mat.
- **Height follows need.** With several opponents, their row gets more of the height (they share the width; you
  don't). In 1v1 both mats come out the same height.
- **Readable card size.** A small mat now draws its cards up to 74px wide, at most 1.45× their share of the mat. They
  overlap their neighbours a little, as cards in a crowded row do. Positions are unchanged, and it's display only.
- **Look (the 2D camera).** Look, or keys **2–6** (the same keys that turn the 3D camera), enlarges one opponent's
  board. Then **1**, **0** or "Whole table" brings the whole table back. The winner spotlight uses the same focus.
- **Slim combat band.** Combat is one line between the boards instead of a tall band.
- **Narrow seats** (container query, under 560px) drop the hand fan, since the plaque gives the count, and hide stats
  that are zero.

**Measured** (real-art boards from §23, card width in the DOM):

| Board | Viewport | Opponents' cards | Your cards |
|---|---|---|---|
| Four players | 1920×1080 | ~50px → **74px** | 85px → 74px |
| Four players | 1366×768 | ~37px → **53px** | ~48px → **63px** |
| 1v1 | 1920×1080 | **75px** | 78px |
| 1v1 | 1366×768 | **53px** | 67px |
| Four players, Look at one opponent | 1920×1080 | ~120px | (shrunk while looking) |

**Still open:** at 1366×768 a 1v1 opponent's mat is about 165px tall, so their cards stay at 53px. Look (key 2) is
the answer there for now. The 3D Table camera frames a four-seat table even in 1v1, so the two boards look small
there.


## 25. The scripted-table pass: seating, the 1v1 camera, dice and physics

**Prompt:** the user's screenshots of Oops I Baked a Pie's scripted tables (four- and six-seat, overhead) and the Card
Encoder overlay, with "take heavy inspo for how the 3D/engine works", "fix the 3D table camera for 1v1", "can I see
the dice being used", and "want the point of 3D for the physics engine". The Oops gallery's overhead and annotated
shots (T5, linked there) were viewed for reference only and are not stored in the repo.

**Seating, as on the scripted tables** (`table3d/layout.ts`):
- **Two facing rows.** 1+1, 1+2, 2+2, 2+3, 3+3. The viewer's row is at the south edge, and turn order runs clockwise:
  along your row to your left, then back along the far row. Nobody's mat is sideways any more, which closes the
  "side seats read sideways" gap in §23.
- **An aisle between the rows** (3 units wide) for the stack, combat arrows and the life plaques. As on the Oops
  table's hearts, each plaque sits in the aisle by its mat's inner edge, toward its owner's left. The stack's drop
  area is the middle of the aisle, checked after the mats so it never takes a drop meant for a mat.
- **Cameras.** The seat camera sits behind your mat and leans toward the table's middle when your seat is
  off-centre, framing the whole far row. The Table camera looks straight down the table, as the scripted tables'
  overhead view does. 1v1 now frames two close mats instead of a four-seat table with a wide gap between them.

**Dice everyone sees** (`game/dice.ts`, `table3d/dice.ts`, `table3d/physics.ts`, `game/DiceLayer.tsx`):
- **The server records each roll's numbers** on its log entry (`LogEntry.roll`: sides, results, coin). It is public,
  like the log line, and every table shows it. Rolls already in the log when a table opens aren't replayed.
- **3D, with physics.** A small rigid-body simulation, written for Fyodor rather than added as a library:
  - gravity, restitution, Coulomb friction, rolling resistance, knocks between dice (as spheres) and the table's
    edges.
  - Dice are thrown from the roller's edge across their mat toward the aisle and roll to rest on a face.
  - The throw is simulated ahead and played back. It is seeded by the roll, so every screen sees the same throw.
  - The server's number is printed on whichever face ends up on top (a d4 numbers its points, the top point shows
    the roll; a coin's up face shows heads or tails). The number also floats above the die, with a total for
    several dice.
  - Shapes: d4, d6, d8, d10 (a planar pentagonal trapezohedron), d12 and d20, plus coins. Other dice use the d20
    shape.
  - Unit-tested (`table3d/physics.test.ts`): every die rests flat on a face, on the table, in under 4 s, and the
    same seed gives the same throw.
- **2D.** The dice tumble from the roller's plaque onto the middle of their mat, in their seat colour, and settle with
  a "Bob · 2d6: 1 + 4 = 5" line. e2e: `dice.spec.ts`.
- **Reduced motion:** dice appear at rest, with no tumble.

**The Card Encoder overlay [US-2] against Fyodor:**

| Encoder control | Fyodor | Where |
|---|---|---|
| Open menu for more options | **Yes** | Right-click a card; the selection toolbar's More |
| Flip double-faced card | **Yes** | Turn over (F), toolbar and menu |
| Toggle +1/+1 counter | **Yes** | Toolbar +1/+1 on creatures; Add counter menu |
| Toggle counter (any type) | **Yes** | Add counter → any type, or a custom type |
| Counter number on the card | **Yes** | Counter chips on the card, in 2D and 3D |
| Toggle power/toughness | **Yes** (§26) | With rules on, a live P/T badge. In manual play, "Set power/toughness…" puts a P/T marker on the card |
| Left-click to increase, right-click to decrease | **Yes** (§26) | On the card's counter chips (2D) and on the card toolbar's counter chips (2D and 3D) |
| Copy card | **Yes** (§26) | Create copy, Exact copy (keeps counters, markers and choices), copy with changes, several copies |
| Re-import card | **Not needed** | Card data is the offline database. Settings → Update card database refreshes everything |
| Get tokens and emblems | **Yes** | The Tokens dialog suggests each of your cards' related tokens and emblems; "Create tokens from this…" |
| Toggle owner gem | **Yes** (§26) | A card controlled by someone other than its owner wears its owner's initial in their seat colour, in 2D and 3D |
| Library: cascade for X | **Yes** (§26) | Library → Cascade…: the server exiles down to the hit; a dialog offers cast it and the rest to the bottom in a random order |
| Library: reveal until type | **Yes** (§26) | Library → Reveal until… (a type, or any type or subtype); a dialog offers where the cards go |
| Library: get basic land | **Yes** (§26) | Library → Get a basic land: into your hand or onto the battlefield, then the library is shuffled |
| Hand: sort by CMC | **Yes** | Hand sort by mana value, colour, type, name, or your own order |
| Hand: discard at random | **Yes** (§26) | The Hand menu: Discard a card at random, or several; the server picks |
| "Only works if cards have CMC and type in their name fields" | **Better** | Fyodor reads real card data |

**Next, from the same tables** (all built in §26):
- Reveal-until and cascade as library actions (resolved on the server, which has the card data and the RNG), and
  discard at random.
- A per-seat button row: Untap, Draw, Scry, Mill, Reveal, with left-click 1, right-click 3, or type a number while
  hovering, as the Oops buttons do.
- Encoder-style steppers on the counter chips themselves (left-click +1, right-click −1), as the toolbar's +1/+1
  button already does.
- An owner marker on cards controlled by someone else.
- Exact copy, which keeps counters.

## 26. Everything from §25's list, and the physics library

The user asked for the physics library and for every open item from §25.

**The physics library: `cannon-es`** (MIT, pure JavaScript, 0.20.0, bundled into the 3D table's chunk so the table
stays offline; the 2D table never loads it):
- Dice are their real convex polyhedra; a coin is a cylinder.
- The table top, its edges and every seat's library, graveyard and exile piles are solid, so dice glance off decks.
- A throw is still simulated ahead, seeded by the roll (every screen sees the same throw), and played back. The
  server's number is printed on the face that ends up on top.
- Cards don't use it: they stay where the server puts them, and the 3D table eases them there as before.
- Tests (`table3d/physics.test.ts`): every die rests flat on a face on the table within 4 s, a coin lands flat, a deck
  stops a die, and the same seed gives the same throw.
- `fyodor-ui-design` rule 3 records this as the one exception to "no physics engine".

**The library and hand chores** (resolved on the server, which has the card data and the RNG; nobody sees a library):
- **Reveal until…** a type or subtype: the cards down to the first one stay on top, revealed to everyone.
- **Cascade…** (mana value less than X): exiles down to the first cheaper nonland card (702.85a).
- **Get a basic land**: into your hand or onto the battlefield, then the library is shuffled. Any card by name works.
- **Discard at random**, from the Hand menu (701.9b).
- After a reveal or a cascade, its owner gets a dialog: put the found card into hand, onto the battlefield, cast it
  (cascade), and the rest to the bottom in a random order or the graveyard. Everyone else sees the cards in the
  log and on top of the library (or in exile).
- The log entry carries the cards (`LogEntry.dig`), like a roll's numbers.

**The seat buttons** (bottom left, over Tokens, Dice and Hand): Untap, Draw, Scry, Mill and Reveal. Click does one,
right-click three, or hover a button and type a number, as on the Oops buttons. Digits typed over a button go to it,
not to the camera keys.

**The encoder's card controls:**
- Counter chips are steppers: click +1, right-click −1, on the card in 2D and on the card toolbar in 2D and 3D.
- An **owner gem** (the owner's initial in their seat colour) on a card someone else controls, in 2D and 3D.
- **Exact copy** keeps counters, effect markers and choices; a plain copy still starts bare, as the rules say.
- **Set power/toughness…** puts a P/T marker on the card for manual play.

**Plaques:** the aisle is wider (3.8 units), so the plaques sit clear of the card rows.

e2e: `scripted-chores.spec.ts` covers reveal until, get a basic land, the seat buttons (click, right-click and a
typed number), discard at random, counter steppers, exact copy and the owner gem.

## 27. Cards with physics, and life on the table (third scripted-table pass)

The user asked for physics on the cards, "so players can organise them as they please", and for the life total to
work as it does on the Oops table, "so it isn't just another menu".

**Flicked cards** (`table3d/cardPhysics.ts`, cannon-es, 3D table only):
- Let go of your own cards while still moving them and they slide on across your mat, slowing on the felt. They
  knock your other cards aside and stop at the mat's edge. Cards stay flat and square to the mat.
- Piles are deliberate, not collisions: cards under the flicked one, and cards already overlapping each other, are
  left where they are.
- The release speed comes from the pointer events' own timestamps, over the last 90 ms. Below 4.5 units a second
  it's a normal, exact drop.
- The slide is simulated ahead and played back at the table's animation speed (reduced motion: it jumps to the
  end). Where every moved card stops goes to the server as one `set_position`, one undo step. Other screens see
  the cards move there.
- Only your own battlefield. Settings → "Flick cards to slide them (3D)" turns it off.
- Tests: `table3d/cardPhysics.test.ts` (slides and stops, knocks a card in its way, leaves piles alone, stops at
  the edge). `table3d.spec.ts` flicks a card through the scene's own path and checks where the server keeps it.
  In this headless, software-rendered browser a real hand's pointer events arrive seconds apart, so that test
  throws the card directly; on a normal machine the hand does.

**Life on the table, as on the Oops hearts** (`game/SeatPlate.tsx`, the plaque both tables share):
- The life total is a heart in the seat's colour, and the number is the control: click +1, right-click −1, the
  wheel, ↑/↓ or +/− on the keyboard, and Shift for 5 at a time.
- Quick clicks are gathered into one change: the heart shows "−3" while you click, then it's sent once (one log
  line, one undo step).
- Beside it:
  - a commander-damage tracker for each opposing commander, in its owner's colour with their initial (click +1,
    right-click −1; it changes life too, as before);
  - a poison tracker;
  - the hand count.
- The portrait and name still open the full player panel; the counters don't need it. The +/− buttons stay
  (shown on hover) for touch and for anyone without a right-click.


## 28. Seat buttons and life hearts on the table itself

The user asked for the seat buttons to be "actual buttons by your mat like in Oops", and for life to "hover in their
seat in the air" with no name.

**The 3D table** (`table3d/seatProps.ts`):
- **Life hearts float over every seat**, in the seat's colour, with no name: whose heart it is shows by where it
  floats.
  - Each heart sits over the aisle by its mat's inner corner nearest the middle of the table, as the Oops table
    keeps its hearts in the middle, where every seat can see them.
  - Hearts turn to face you, bob gently (not with reduced motion), and cast a soft shadow on the table.
  - The number is the control: click +1, right-click −1, the wheel over the heart (otherwise the wheel zooms), and
    Shift for 5. Quick clicks are gathered into one change, shown under the number as it builds.
  - Attack arrows aimed at a player land under their heart.
- **Your seat's buttons are physical discs on the table**, in a column along your mat's left side, clear of your
  hand. Each is colour-coded with an icon (Untap, Draw, Scry, Mill, Reveal, after the Oops buttons).
  - Click does one, right-click three, or hover one and type a number (it shows on the button's face).
  - Buttons light when hovered and dip when pressed. The canvas tooltip names each one.
- The plaque in the aisle keeps the portrait, name (it opens the player panel) and the trackers. In 3D it no longer
  carries a heart.

**The 2D table:** the seat buttons are round, coloured, icon buttons in the rail by your mat, under your piles.
The piles share one row so the buttons fit. The bottom-left tray is back to Tokens, Dice and the Hand menu. Each
2D plaque keeps its heart, which is the 2D table's version of the floating one.

**Shared code:** `game/seatActions.ts` (the five actions, their icons as SVG path data, the typed count and the
click batching), used by `game/SeatButtons.tsx` and `table3d/seatProps.ts`.

**Tests:**
- `table3d.spec.ts` clicks Bob's floating heart (twice, then a right-click: 41) and the Draw button on the table.
- `layout.test.ts` checks every heart floats toward the middle, over the aisle.
- `scripted-chores.spec.ts` covers the 2D buttons (click, right-click, a typed count).

## 29. Closer to Oops: its buttons, its hearts, and the Magic card back

The user: "those life buttons are trash", "for the action buttons use the exact symbols from Oops, same location
too", and "make the backs of cards in the library look like the MTG card back". The Oops gallery's annotated and
overhead shots (T5) were zoomed in to copy the buttons and hearts. Nothing from them is stored in the repo.

**The buttons, as on the Oops mat** (`game/seatIcons.ts`):
- Glossy black discs, each with one bold coloured symbol:
  - a yellow U-turn arrow (Untap);
  - a green open hand (Draw);
  - a blue eye (Scry);
  - a red skull (Mill);
  - a beige magnifying glass (Reveal).
- **Mulligan** is added apart on the right, as on Oops: grey cards around a cyan arrow loop. It shuffles your hand
  in and draws seven, and Ctrl+Z undoes it.
- The symbols are drawn in canvas code (simple shapes, nothing copied), so the 3D buttons and the 2D buttons show
  the same picture.
- **3D:** a row just past your mat's near edge, a little left of centre, as on Oops. The seat camera was re-solved
  so that row shows above your hand at 16:9 while the far mats stay whole. The solve has to include the scene's
  view offset, which renders the lower part of a taller frame.
  - The button faces are unlit, so the black stays black under the table's warm light.
  - Click does one, right-click three, or hover and type a number.
- **2D:** the same discs in the rail by your mat, under your piles.

**Life, as the Oops heart** (`table3d/seatProps.ts`, `game/SeatPlate.tsx`):
- A black heart edged thick in the seat's colour, the total big and pale in its middle, ▼ on its left and ▲ on its
  right.
- Click the left half for −1 and the right half for +1. Right-click either half for 5, or use the wheel; quick
  clicks are gathered into one change, as before.
- **3D:** it sits at each mat's inner corner by the middle of the table, as on Oops. It hovers a little above the
  felt, unlit, and turns so every seat's number reads upright to you. (Oops prints them flat, facing their owners.)
  The +/− buttons beside the 3D plaque are gone; the heart is the control.
- **2D:** the plaque's heart has the same look and halves. Its hover +/− buttons stay for touch.

**The Magic card back:**
- The host fetches Scryfall's standard card back (`backs.scryfall.io`, card back
  `0aeebaf5-8c7d-4636-9e82-8c27447861f7`) into its image cache whenever it caches card art. It's never shipped with
  Fyodor, the same as card images.
- The host serves it at `/api/images/card-back` (404 until it's cached).
- **2D:** `cards/cardBack.ts` checks for it once and sets `has-card-back` on the page; then every back (library
  piles, opponents' hands, face-down cards) shows it.
- **3D:** library piles and face-down cards use the same image. A player's sleeve still wins. Without the cached
  image, both tables keep drawing their own back.

**Tests:**
- `test_cards.py`: the back is downloaded once, served from the host, and a bad answer leaves nothing behind.
- `table3d.spec.ts`: clicks the heart's ▲ half twice and ▼ once (41), right-clicks ▼ (36), then presses Draw on the
  table.
- `scripted-chores.spec.ts`: the 2D buttons.
