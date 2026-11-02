import { CARD_PERMISSIONS } from "../game/cardPermissions";
import type { CardPermissions } from "../types/game";

/**
 * -- table permissions -- the lobby's "Who may change a player's cards" control (a LAN table; the server enforces it,
 * app/game/table_rights.py). Self-contained so the lobby layout can place it anywhere among the table settings.
 */
export function TablePermissionsSetting({ value, onChange }: { value: CardPermissions | undefined; onChange: (v: CardPermissions) => void }) {
  const current = CARD_PERMISSIONS.find((p) => p.id === (value ?? "everyone")) ?? CARD_PERMISSIONS[0]!;
  return (
    <label className="field">Who may change a player's cards
      <select data-testid="lobby-card-permissions" value={current.id} onChange={(e) => onChange(e.target.value as CardPermissions)}>
        {CARD_PERMISSIONS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
      </select>
      <span className="hint">{current.hint}.</span>
    </label>
  );
}
