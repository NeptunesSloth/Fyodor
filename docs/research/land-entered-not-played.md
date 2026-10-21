# Lands entering without being played

Deep Gnome Terramancer current Oracle is held in the canonical fixture and
Scryfall printing ac23a376-4b3a-4316-b3e2-2e25ca2b5e76 (accessed 2026-10-19).
The official ruling feed currently contains no individual comments. The
implementation follows CR 305.1 (playing a land), 603.2c (one-or-more events),
603.2h (the optional action has not yet been performed this turn), 603.6a
(entrants see simultaneous entries), 101.4/603.3b (APNAP), and 701.23 (search).

A played land remains played even if it is also a creature (Dryad Arbor), or
is played during resolution through an effect (Djinn of Wishes). A land put
onto the battlefield by a fetch land or reanimation was not played. Neither
the entered-from zone nor a player's aggregate land-drop count distinguishes
these actions reliably.

Both native play paths emit land_played with the NEW battlefield object ID:
engine.play_land after entry, and replacements.after_entry for an entry with
played=True from permissions.play_land_now. Generic event collection gathers
these exact object IDs before processing the event window, including markers
emitted after their entry event. Each entry fact checks its own new object ID;
a marker never exempts another land, another incarnation, or a later fetch.
Existing watcher batch windows prevent a newly reanimated Gnome from observing
earlier land entries; existing aggregate matching combines simultaneous
Scapeshift lands into one trigger.

The native private Plains tutor and optional do_once machinery are reused.
Declining the optional ability leaves the action available. Searching but
finding nothing consumes it. A forbidden search is not performed and does not
consume it. Pure optional-search do_once definitions mark their action_gate
and record_action as search actions; the gate clears the per-resolution
search_performed marker before the instruction, and the search sets it only
after prohibitions leave an actual searched zone. Compound payment/action
abilities retain their existing semantics. No casting-path changes are made.
