# Table tools

Physical-table conveniences for tracking what's going on. **Nothing here enforces rules,
expires, or happens on its own** — players add and remove everything themselves.

| Tool | Where | Notes |
|---|---|---|
| Temporary effects | Card menu → Effects | Presets (+X/+X, keywords, protection from a color, can't block…) or a custom effect (name, value, text, color). Shown as small chips on the card. Remove one, or *Clear effects*. |
| Damage markers | Card menu → Damage | +1 / −1 / Set / Clear. Never checks lethal damage, never moves anything. |
| Targeting arrows | Card menu → *Target / point to…* | Pick cards and/or players (several targets allowed), Done. Everyone sees thin, translucent arrows (targets dashed brass, attacks red, blocks blue, custom grey). Arrows vanish when their ends leave the battlefield/stack. |
| Attack targets | Card menu → Attack | A player, planeswalker or battle. Blocks link one blocker to one attacker; several blockers can block the same attacker. |
| Clear combat | ⋯ → Clean up → Clear combat | Removes attacking/blocking markers and combat arrows, never touches the cards. Combat is no longer cleared automatically; a table can opt in with the `auto_clear_combat` setting. |
| Mana pool | Player plate → ◇ mana | W U B R G C: click +1, right-click −1, × clears. Nothing is spent automatically. Pools no longer empty on step changes unless the table opts in (`clear_mana_on_step`). |
| Ownership vs control | Card menu → Give control to / Return to owner | Every card keeps its owner; graveyards and hands always mean the owner's. |
| Copies | Card menu → Create copy (1 or X) · *Change copy target…* | A copy remembers its source (“COPY OF …”) and keeps its own counters, tap state, effects, controller and notes. |
| Face-down cards | Card menu → Play/Turn face down as morph, disguise, manifest, cloak… · library → manifest/cloak the top card | Opponents see a card back and the public kind label only. |
| Exile groups | Exile card menu → Exile group | Foretell, Adventure, Plot, Suspend, “Exiled with <permanent>”, or custom. Organisational only. |
| Card notes | Card menu → Add note | Small ✎ indicator; full text on hover/inspect. |
| Choices | Card menu → Choices | Chosen color, creature type, named card, player, number, mode, value, or a custom label. Shown compactly on the card. |
| Spell details | Stack card menu → Spell details | X = …, chosen modes (listed from the card's text, or typed), cast labels (Kicked, Flashed back, Cast from exile …). Changeable until it resolves. |
| Token provenance | Card menu → *Create tokens from this…* | Tokens remember their source; ⋯ → *Show token sources* displays it. |
| Arrange | Card menu → Arrange | Rotate, group (move together), lock in place, attach to…, detach. |
| Mass actions | Select several cards, right-click | Tap/untap, counters, effects, damage, move, control, arrange, lock. *Delete all tokens & copies* confirms whenever real cards are in the selection (real cards can never be deleted — move them to a zone). |
| Selection filters | ⋯ → Select | My creatures / lands / tokens / artifacts / enchantments / tapped / untapped, all tokens, everything I control, invert, clear. |
| Clean up | ⋯ → Clean up | Combat, damage, temporary effects, arrows, mana pools, response state, delete all tokens (confirmed). |

Everything above is game state: it's saved, synced to every player over the LAN, and undone
and redone like any other action.
