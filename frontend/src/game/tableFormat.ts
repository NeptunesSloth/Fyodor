import type { IconName } from "../components/Icon";
import type { TableFormat } from "../types/game";

/**
 * A table's format, as the New game form, the lobby and the table name it. Every deck is a Commander deck; Sandbox is free
 * play with them, as in Tabletop Simulator: no deck checks, rules automation starts off (the host can turn it on at the
 * table) and test objects are allowed (app/multiplayer/lobby.py TableFormat).
 */
export const TABLE_FORMATS: { id: TableFormat; name: string; lines: [string, string]; icon: IconName }[] = [
  { id: "commander", name: "Commander", lines: ["Checks decks against Commander's rules.", "The rules engine runs at Full automation."], icon: "crown" },
  { id: "sandbox", name: "Sandbox", lines: ["Test a deck on your own: just you at the table.", "Nothing is checked; rules automation is your choice."], icon: "hand" },
];

export const FORMAT_NAME: Record<TableFormat, string> = { commander: "Commander", sandbox: "Sandbox" };

/** What a Sandbox table means, in a sentence or two (the rail note, the lobby, the table's top bar). */
export const SANDBOX_HINT =
  "Free play: any deck, nothing is checked or enforced, and you move everything by hand. Rules automation stays off until the host turns it on at the table.";

/** The rail's short version (the Play page's front rail, beside Start). */
export const SANDBOX_RAIL = "Just you and your deck: goldfish it, try lines, test combos. Nothing is checked, and nobody joins.";

/** Why the automation choice is locked while a Sandbox table is set up. */
export const SANDBOX_LOCK =
  "Locked while you set up a Sandbox table: it starts with rules automation off. The host turns it on at the table, from the Sandbox tag in the top bar.";

/** The night's name in the lobby header: what kind of LAN night this is. */
export const nightName = (format: string | undefined | null): string => (format === "sandbox" ? "Sandbox: free play" : "Commander LAN night");

export const isSandbox = (format: string | undefined | null): boolean => format === "sandbox";
