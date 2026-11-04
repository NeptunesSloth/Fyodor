import type { IconName } from "../components/Icon";
import type { TableFormat } from "../types/game";

/**
 * A table's format, as the New game form, the lobby and the table name it. Every deck is a Commander deck; Sandbox is free
 * play with them, as in Tabletop Simulator: no deck checks, rules automation starts off (the host can turn it on at the
 * table) and test objects are allowed (app/multiplayer/lobby.py TableFormat).
 */
export const TABLE_FORMATS: { id: TableFormat; name: string; line: string; icon: IconName }[] = [
  { id: "commander", name: "Commander", line: "Deck checks, and rules automation at the level you pick.", icon: "crown" },
  { id: "sandbox", name: "Sandbox", line: "Free play: no deck checks, rules automation off.", icon: "hand" },
];

export const FORMAT_NAME: Record<TableFormat, string> = { commander: "Commander", sandbox: "Sandbox" };

/** What a Sandbox table means, in a sentence or two (the rail note, the lobby, the table's top bar). */
export const SANDBOX_HINT =
  "Free play with Commander decks: nothing is checked or enforced, and you move everything by hand. Rules automation starts off; the host can turn it on at the table.";

export const isSandbox = (format: string | undefined | null): boolean => format === "sandbox";
