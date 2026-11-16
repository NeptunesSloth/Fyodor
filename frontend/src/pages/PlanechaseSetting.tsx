import type { LobbySettings } from "../types/game";

type Planechase = Pick<LobbySettings, "planechase" | "planar_deck_size" | "planar_phenomena">;

/**
 * -- planechase -- the lobby's Planechase control (CR 901, one shared planar deck; app/game/handlers/planechase.py): off by default;
 * on, the server deals the table a deck of distinct planes (and phenomena, unless planes only) when the game starts. The planar die
 * and planeswalking are automatic; what each plane does, players apply by hand. Self-contained like TablePermissionsSetting.
 */
export function PlanechaseSetting({ value, onChange }: { value: Planechase; onChange: (v: Planechase) => void }) {
  const on = !!value.planechase;
  const size = value.planar_deck_size ?? 10;
  return (
    <div className="field" data-testid="lobby-planechase">
      <label className="inline"><input type="checkbox" checked={on} onChange={(e) => onChange({ planechase: e.target.checked })} /> Planechase</label>
      {on && (
        <span className="inline">
          <label>Planar deck{" "}
            <input type="number" min={2} max={60} value={size} style={{ width: 56 }} aria-label="Cards in the planar deck"
              onChange={(e) => onChange({ planar_deck_size: Math.max(2, Math.min(60, Number(e.target.value) || 10)) })} /> cards
          </label>{" "}
          <label><input type="checkbox" checked={value.planar_phenomena !== false} onChange={(e) => onChange({ planar_phenomena: e.target.checked })} /> Include phenomena</label>
        </span>
      )}
      <span className="hint">
        {on ? "One shared planar deck, shuffled by the host's computer. The die, its cost and planeswalking are automatic; players apply each plane's effects."
          : "Off: no planar deck."}
      </span>
    </div>
  );
}
