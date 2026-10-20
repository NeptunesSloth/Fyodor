# Reveals with bound outcomes

Twelve Commander-legal canonical cards use the existing native look, selection,
entry, placement, sacrifice, damage, pump and shuffle machinery: Mind Funeral,
Mind Grind, Fathom Trawl, Madcap Experiment, Audacious Reshapers, Telemin
Performance, Shape Anew, Proteus Staff, Erratic Mutation, Stomping Slabs, Clear
the Land and Genesis Hydra.

Small preparation primitives preserve the actual reveal count and found-card
reference before anything moves. Library owner, instructed player and entry
controller remain separate. Telemin moves the noncreatures before its creature
enters; Proteus snapshots the creature's controller before bottom placement.
Clear the Land reveals everyone's cards before one simultaneous native entry
batch. Failed creature entries retain the correct remaining cards and damage
count. Mind Grind carries its printed positive-X minimum through native spell
composition into paid and free-cast preflight. Existing activation minimums and
copy decisions remain unchanged.

The shared native reveal-until matcher reads current derived library
characteristics, including Grist's creature status, rather than printed types.
Exact reveal cleanup runs after that reveal's final library placement, before
later damage can pause for replacement ordering. Private bottom ordering is
therefore hidden even during a subsequent replacement choice.

37 focused cases pass: every card's actual positive effect, no/short matches,
wrong names, zero-X atomic rejection, real paid sacrifice, stolen controller
versus owner, actual countered Hydra retaining cast X, Grafdigger's Cage failed
entries, Grist's library characteristic, three fresh-process native
choose/order/Clone-entry resumes, and a real Torbran plus Fiery Emancipation
replacement choice proving bottom-order privacy before damage. Replay/JSON
checks throughout. 235 related native library-look and cast/copy regressions PASS. A fresh
53-case run includes all37 own cases plus16 Abundance cases, now strengthened
with ordered-library privacy checks (3 failed before the native cleanup fix,
all16 pass after). Total272 unique scoped tests. Shared coverage/type/core
audit remains centralized.

Scope follows the project's Commander-legal inventory. An exploratory silver
border Little Girl case exposed existing fractional mana/PT limitations outside
that inventory; this batch does not broaden numeric schemas or claim funny-card
support. The new reveal snapshots retain object references for mana values,
without adding their own integer truncation.
