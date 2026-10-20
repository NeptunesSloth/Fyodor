# Temporary hand exile and exact delayed returns

Memory Jar and Magus of the Jar capture every player's original hand before any
draws, exile the cards face down, and use the native grouped draw path. The
replacement solver retains APNAP order and can pause for dredge. Their delayed
trigger discards the current hands and returns only the original exile objects.
Overlapping Jar activations retain separate groups.

Induced Amnesia links its targeted hand exile to the enchantment's original
incarnation and draws the frozen count through native draw replacement handling.
Only its battlefield-to-graveyard trigger returns the linked cards. If it leaves
before its ETB resolves, the earlier departure cannot return cards exiled later.

Suppress captures the target's exact hand and waits until the end step of that
player's next turn. The delayed-step matcher has an explicit `next_turn_only`
guard so a self-targeted Suppress cannot return the hand in the current turn.

Psychic Theft and Planeswalker's Mischief reuse native hand selection or random
reveal, exact-object cast permissions, and next-end-step return. Mischief grants
a free cast; Theft requires the ordinary cost. Casting changes the object, so
the original exile reference cannot return a cast card even if it is countered.
The permission survives departure of the original source.

These face-down hand effects grant nobody permission to look at the exiled cards
(CR 406.3a). Native `Move.blind`, defaulting to false like the existing mill flag,
sets the existing `unseen` state for face-down exile. Ordinary face-down moves,
including existing Gonti behavior, retain their prior semantics. Hidden-card ID
renumbering rewrites the saved exact references through the existing framework.

Canonical gameplay tests cover all six cards, real costs and effects, source
departure, owner and spectator privacy, actual paid/free stolen casts, counters,
turn timing, overlapping groups, replay, and fresh-process loading during a
native draw-replacement pause followed by the original delayed return.
