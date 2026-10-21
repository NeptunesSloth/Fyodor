# Nomad Mythmaker collateral promotion validation

Exact Oracle: “{W}, {T}: Put target Aura card from a graveyard onto the battlefield under your control attached to a creature you control.”

The existing generic return grammar now carries the typed host_choice selector into attachment entries. This unexpectedly promoted Nomad Mythmaker when One Last Job added that shared capability. No additional production changes were needed.

Canonical actual activated-ability scenarios verify an opponent-owned Aura in that opponent's graveyard enters under the activator's control; only creatures that player controls are offered as attachment hosts; a shrouded creature is legal because this attachment does not target; enchant-player Curses and a Daybreak Coronet without a previously enchanted creature remain in the graveyard; Coronet enters on the one qualifying enchanted creature; a graveyard target leaving and returning is a new object and the sole-target ability fizzles; all creatures controlled by the activator leaving does not permit attaching to an opponent's creature. Costs, tapping and summoning sickness use actual game progression to the source controller's next turn. Choices and resulting states replay and round-trip through JSON save/load.
