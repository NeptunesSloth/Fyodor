# Fyodor — MTG inside Tabletop Simulator reference pack

Research date: 2026-10-30. These are real Steam Workshop/community references for Magic: The Gathering played inside **Tabletop Simulator**, primarily four-player Commander/EDH. They are *not* screenshots of MTG Arena. Treat these as reference links and design evidence, not licensed art/assets to copy into Fyodor.

## Design principle

**Real table first, contextual game UI second.** Cards, playmats, deck piles, tokens, life counters and dice remain the focus; controls attach to cards, decks, and individual player areas rather than taking over the display. Preserve physical freedom but surpass TTS's sometimes cluttered or fragmented scripting/UI with coherent, accessible, integrated Fyodor design.

## A. Primary reference tables

| Priority | Table / creator | Reference | Observe | Don't copy |
|---|---|---|---|---|
| 1 | **MTG 4 player table - scripted** / Oops I Baked a Pie | https://steamcommunity.com/sharedfiles/filedetails/?id=2296042369 | Four-seat distribution, scripted draw/untap/scry/mill/reveal, per-card counters and P/T, context-menu spell/card actions, custom playmats, physical objects | Excessive buttons, tiny text, community-mod scripting fragmentation |
| 2 | **Magic the Gathering Table - MTG EDH** / Lenc | https://steamcommunity.com/sharedfiles/filedetails/?id=2425949312 | Actual wooden tabletop, player mats, deckboxes, zones, counters and custom physical equipment | Unnecessary objects, decor getting in way of cards |
| 3 | **Minimal MTG** / OTTOREIKU | https://steamcommunity.com/sharedfiles/filedetails/?id=2066242375 | Four Commander seats + spectators; cleaner layout and intentionally fewer tools | Losing important priority/stack/rules clarity |
| 4 | **MTG EDH Table of Doom** / schoob | https://steamcommunity.com/sharedfiles/filedetails/?id=2278483976 | Playmat chest, response buttons, dice cannon, 'who goes first', ability counters and physical toys | Visual clutter and too many novelty objects during active play |
| 5 | **MTG Commander 4-player** / Xilisys | https://steamcommunity.com/sharedfiles/filedetails/?id=2681557055 | Beginner hints, deck importer, scry affordances, clear player-specific zones | Huge instruction cards permanently on table |
| 6 | **MTG Portable Playmat [scripted]** / V | https://steamcommunity.com/sharedfiles/filedetails/?id=3651317655 | Portable per-player zones, auto-organized land rows, manual battlefield placement, tap hotkey, counter menus | Overly rigid snapping that removes sandbox positioning |
| 7 | **MTG 6 player table - scripted** / Oops I Baked a Pie | https://steamcommunity.com/sharedfiles/filedetails/?id=2293586471 | How a scripted table scales beyond 4 seats; player-relative UI | Optimize Fyodor for six before four is usable |
| 8 | **Magic The Gathering Tables** / community collection | https://steamcommunity.com/sharedfiles/filedetails/?id=1330434940 | Compare many table environments and scripting densities | Treat every community design as equally successful |

## B. Micro-interactions and tools

| Interaction | Source | Fyodor lesson |
|---|---|---|
| Card-attached counters, +1/+1, P/T, loyalty, commander ownership | **Easy Modules for MTG Encoder:** https://steamcommunity.com/sharedfiles/filedetails/?id=2246039633 | Controls and status should travel with the card; use small overlays/markers and reveal tools only on selection/hover |
| Per-object contextual menu, object actions | **TTS Context Menu docs:** https://kb.tabletopsimulator.com/player-guides/context-menu/ | Card menu differs from library menu; right-click shows only appropriate actions |
| MTG deck importing (including Archidekt) | **Omes MTG Deck Loader / Importer:** https://steamcommunity.com/sharedfiles/filedetails/?id=2163084841 | Deck imports flow into a physical deck + commander rather than a giant deck-management overlay during games |
| Practical Commander table interaction, keys, zone management | **TeamDman MTG TTS guide:** https://github.com/TeamDman/Guides/blob/master/MTG/TabletopSimulator.md | Study hover shortcuts, hand display, tutoring, tokens, arranging and grouping |
| Multi-step real-world setup screenshots | **Draftsim MTG TTS guide:** https://draftsim.com/tabletop-simulator-mtg/ | Watch how decks are loaded, placed in zones and play begins with dice; simplify these steps in Fyodor |
| Modular manual battlefield + land-auto-arrangement | **Portable Playmat:** https://steamcommunity.com/sharedfiles/filedetails/?id=3651317655 | Never force free-placement cards into a fixed layout; offer optional organization |

## C. Workshop screenshot gallery — direct original image links

Steam's Workshop pages contain several screenshots per mod. These direct Steam image links are from the gallery thumbnails; if an image host blocks embedding, open the workshop page above and click its gallery images instead. No screenshot ownership is implied.

### C1. Oops I Baked a Pie — four-player scripted Commander table

- [Four-seat overhead table arrangement](https://images.steamusercontent.com/ugc/1780589749097002508/E2F2EC0683DE824C14BD016B790997E5FF271C12/)
- [Angled tabletop/player controls view](https://images.steamusercontent.com/ugc/1780589749097007053/B25B3ED2DDD46AD034BC5BFB3B9CE5F0641A3F4C/)
- [Table features/instructions reference](https://images.steamusercontent.com/ugc/1838028412877586983/7E9A311D31EF84C195777E3583B0FF5A0C779DF3/)
- [Hotkey / table setup overview](https://images.steamusercontent.com/ugc/1780589749097027675/DEE0A3275404714CEC0125D8C158334BD5D11373/)
- [Creator video guide 1](https://www.youtube.com/watch?v=QJEqKZZ42K4)
- [Creator video guide 2](https://youtube.com/shorts/IFYNLktZ6j4)

### C2. Lenc — EDH wood table

- [Warm wooden table angle](https://images.steamusercontent.com/ugc/1735548673614196017/A0184293AA24AC5E4D1A95366762A2D9EA234958/)
- [Four quadrant playable mats](https://images.steamusercontent.com/ugc/1735548673614197124/C27D555810C25F2220F4C38CC8CEC15281AA0D3A/)
- [Player counters and tools close-up](https://images.steamusercontent.com/ugc/1735548673614196649/8C360A3F8C107FBB0B2B83427103779DB43A9868/)
- [In-table player zone and cards](https://images.steamusercontent.com/ugc/1735548673614197951/BB9E9C2348449B709DB07D1F3BAEC74F793FD6D0/)
- [Mat surface and table detail](https://images.steamusercontent.com/ugc/1756940404815975032/EDD937398F2BA6BE72DD72BB7F1BA07C26AD8E83/)
- [Card organization close-up](https://images.steamusercontent.com/ugc/1756940404815972923/FD8160BEE48B0E74407343D49AEE4918ABA3F3D3/)
- [Angled 3D table and played cards](https://images.steamusercontent.com/ugc/1756940689958072519/78C3EB06DC7DB5AF03CEF39B1BDCA13802931F5E/)

### C3. EDH Table of Doom — 3D game-night environment

- [3D environment / atmospheric full table](https://images.steamusercontent.com/ugc/1648843044115634928/B333DA8154D0730229E04B021F12C8F33BB08056/)
- [Playmat/table details, toys](https://images.steamusercontent.com/ugc/1648843044115635947/211AC67D5FA310D3150A05A64D25C612CF4A933F/)
- [Low-angle table with physical buttons/counters](https://images.steamusercontent.com/ugc/1648843044115637707/2DBBE033A2A1A0E49585F0A76468F3C1901C9CA8/)
- [Room/environment variant](https://images.steamusercontent.com/ugc/1678115130076911199/56BFC169A0B3B07DF77D5442EAF643344AEF5BE9/)

## D. What to borrow in Fyodor

1. **Four clearly defined territories** without caging every object into grids.
2. **Real-world card scale and occlusion**: overlaps, tap rotation, piles and pick-up elevation.
3. **Player-relative controls**: life, commander damage, graveyard, exile, library and commanders close to their owners.
4. **Object-aware right click**: deck -> shuffle/search/scry; creature -> tap/counters/copy/notes; token pile -> expand/split.
5. **Physical dice and table toys**, kept secondary and hideable.
6. **Optional helper actions** in context/shortcuts: untap, draw, mill, reveal, tidy.
7. **Deck importer** should yield real physical library/commander objects, not spawn web-app panels.
8. **Private zones and hands** with strict server-side privacy; spectators get public information only.
9. **Clear visual table scene and lighting**: dark wood, felt, quiet brass, shadowed physical cards.
10. **Coherent single UI system**: TTS workshop mods mix unrelated designs, Fyodor shouldn't.

## E. What not to copy

- Giant permanent text instructions, scattered script buttons and unrelated menu styles.
- Taking up the whole screen with a static top toolbar and status dashboard.
- Drag/physics complexity without direct, reliable precision.
- Reliance on external image/import services during a private offline LAN match.
- Copying another creator's game art, proprietary icons, or in-game models as production assets without permission.
- Replacing Fyodor's existing plain Three.js renderer with React Three Fiber.

## F. Claude checklist

1. Open the workshop page + gallery for each top-four reference; inspect at least 12 screenshots from multiple camera angles.
2. Watch the Oops scripted table video guide if accessible; otherwise state the limit and rely on workshop/guide descriptions.
3. Make side-by-side notes: TTS physical tabletop vs Fyodor current renderer.
4. Record KEEP / IMPROVE / DON'T COPY for each reference.
5. Use `frontend-design` for coherence, vanilla Three.js skills for spatial/card implementation, `impeccable` for critique.
6. Render actual Fyodor screenshots at normal four-player and crowded-board states; compare table-screen ratio, card legibility, depth, controls, and clutter.
7. Preserve manual tabletop freedom, server authority, 2D fallback, and hidden-information boundaries.
8. Keep `docs/CURRENT_STATE.md` unchanged unless explicitly requested.

## Recommended reference priority

**First:** Oops 4-player scripted table, Lenc's wood EDH table.  
**Then:** Minimal MTG (what to simplify), Table of Doom (social/tabletop personality).  
**Finally:** Encoder modules and Portable Playmat for precise interaction patterns.
