# Additional upkeep steps and upkeep-only phases

Sources accessed 2026-10-19:
- Paradox Haze official rulings: https://api.scryfall.com/cards/09dc5495-e992-4709-b04f-7ac980b6e99f/rulings
- Obeka, Splitter of Seconds: https://api.scryfall.com/cards/03415c42-086e-4a2e-9be8-5cdcde83f134/rulings
- The Ninth Doctor: https://api.scryfall.com/cards/1b3e0b24-2bf1-451b-9f02-e3704949ae7d/rulings
- CR 500.9-10a, 502.4, 503.1, 603.3.

Paradox Haze triggers on enchanted player's FIRST upkeep each turn. Its
controller may be a different player: the enchanted active player gets the
extra upkeep. Multiple Hazes trigger together and add separate upkeeps; they
do not trigger recursively in those upkeeps. Ordinary upkeep abilities fire
in every upkeep. Echo does not repeat: the first upkeep consumes its history
condition. A skipped upkeep does not happen and cannot trigger Haze.

Obeka adds one beginning phase per additional upkeep, with untap and draw
skipped (CR 500.10 explicitly uses Obeka as its example). These phases come
after the current combat ends, then continue to the previously scheduled
phase, ordinarily postcombat main. Newer phase additions at the same boundary
occur first. Double strike produces two damage events, two triggers and the
sum of the extra upkeeps. CR 500.10a expressly says an effect saying 'you get'
adds nothing if its controller is not the active player. This matters when
another player copies Obeka's trigger with Return the Favor.

The Ninth Doctor's untap trigger occurs during untap, but no player receives
priority then. It is put on the stack in the next step (usually upkeep).
'After this step' means after the step in which it resolves, NOT after the
untap where it triggered. It must check the active controller/untap phase at
the untap EVENT, not later during resolution. Ordinary main-phase untapping
or untapping in another player's untap does not qualify. Added Sphinx untap
steps qualify, and the resulting added upkeep must not consume the Sphinx
phase's pending draw or the later ending phase.

Implemented extension: saved step queue separate from existing phase queue for
Haze/Ninth. Add typed recipient and count, retaining original following step
(e.g. upkeep/upkeep/draw). Obeka uses marked upkeep-only phase queue entries;
those phases skip untap/draw, consume the next phase after upkeep, and retain
existing phase ordering. First-upkeep gating uses saved chronological step
counts from the beginning/end-step foundation. Trigger grammar needs Haze's
first-upkeep form and Ninth's untap-during-own-untap condition.

Canonical gameplay scaffolds cover source FULL status, enchanted player vs
controller, multiple Hazes and nonrecursion, Obeka ordinary/double-strike
upkeeps without untap/draw, nonactive copied trigger, Ninth normal/added
untap timing and excluding ordinary main-phase untaps. The exact native trigger and queue paths are exercised after checkpoint release.

Untap events are processed after the engine has moved into upkeep. The generic
Event therefore captures step_phase and active_player at tap/untap emission;
Ninth's predicate reads that snapshot rather than the later phase. The ability
then schedules relative to its actual resolution step. Saved extra_steps are
independent from extra_phases, and upkeep-only phases use a phase-return
sentinel when another upkeep is inserted inside them. New turns clear both
queues and their phase flags.

Skipped steps honor both saved queues: skipping an upkeep-only phase proceeds
to the next scheduled phase, never a synthetic draw step. Skipping an inserted
upkeep consumes its scheduled step return. Skipping the draw of an added full
beginning phase resumes its phase queue, rather than a precombat main phase.
Skip iteration is bounded by the actual queued length, supporting more than
four skipped upkeeps. Real Eon Hub and Dragon Appeasement cases cover these
paths, including six skipped Obeka upkeep-only phases and saved queue replay.
