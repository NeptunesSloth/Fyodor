import { useMacros } from "../state/macros";
import { useState } from "react";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/Toasts";
import { api } from "../services/api";
import { seatToken } from "../services/games";
import { useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import { isVisible } from "../types/game";
import { send } from "./actions";

type Step = Record<string, unknown> & { op: string };

/** The whitelisted primitives. Each field is plain data; nothing is ever executed as code. */
const OPS: Record<string, { label: string; fields: [string, string, "text" | "number" | "select", string[]?][]; base: Step }> = {
  CREATE_TOKEN: { label: "Create token", base: { op: "CREATE_TOKEN", name: "Treasure", type_line: "Token Artifact — Treasure", count: 1 },
    fields: [["name", "Token name", "text"], ["power", "Power", "text"], ["toughness", "Toughness", "text"], ["type_line", "Type line", "text"], ["count", "How many", "number"], ["player", "For", "select", ["me", "each_opponent", "each_player"]]] },
  ADD_COUNTER: { label: "Add counter", base: { op: "ADD_COUNTER", target: "this", kind: "+1/+1", amount: 1 },
    fields: [["target", "On", "select", ["this", "selected"]], ["kind", "Counter", "text"], ["amount", "How many", "number"]] },
  REMOVE_COUNTER: { label: "Remove counter", base: { op: "REMOVE_COUNTER", target: "this", kind: "+1/+1", amount: 1 },
    fields: [["target", "From", "select", ["this", "selected"]], ["kind", "Counter", "text"], ["amount", "How many", "number"]] },
  CHANGE_LIFE: { label: "Change life", base: { op: "CHANGE_LIFE", player: "me", delta: 1 },
    fields: [["player", "Player", "select", ["me", "each_opponent", "each_player"]], ["delta", "By (±)", "number"]] },
  ADD_MANA: { label: "Add mana", base: { op: "ADD_MANA", mana: { C: 1 } }, fields: [] },
  MOVE_CARD: { label: "Move card", base: { op: "MOVE_CARD", target: "this", to: "graveyard" },
    fields: [["target", "Which", "select", ["this", "selected"]], ["to", "To", "select", ["hand", "graveyard", "exile", "library", "battlefield", "command"]]] },
  ROLL_DIE: { label: "Roll die", base: { op: "ROLL_DIE", sides: 6, count: 1 }, fields: [["sides", "Sides", "number"], ["count", "Dice", "number"]] },
  FLIP_COIN: { label: "Flip coin", base: { op: "FLIP_COIN", count: 1 }, fields: [["count", "Coins", "number"]] },
  CREATE_MARKER: { label: "Add effect marker", base: { op: "CREATE_MARKER", target: "this", name: "Flying" },
    fields: [["target", "On", "select", ["this", "selected"]], ["name", "Effect", "text"], ["value", "Value", "text"]] },
  SET_NOTE: { label: "Set note", base: { op: "SET_NOTE", text: "" }, fields: [["text", "Note", "text"]] },
  SET_CHOICE: { label: "Record a choice", base: { op: "SET_CHOICE", key: "Chosen color", value: "" }, fields: [["key", "Choice", "text"], ["value", "Value", "text"]] },
  CREATE_ARROW: { label: "Point an arrow", base: { op: "CREATE_ARROW", to: "selected" }, fields: [["to", "At", "select", ["selected", "each_opponent"]], ["label", "Label", "text"]] },
  CHANGE_CONTROLLER: { label: "Change controller", base: { op: "CHANGE_CONTROLLER", target: "this", player: "me" },
    fields: [["target", "Which", "select", ["this", "selected"]], ["player", "To", "select", ["me"]]] },
  DISPLAY_TEXT: { label: "Show text in the log", base: { op: "DISPLAY_TEXT", text: "" }, fields: [["text", "Text", "text"]] },
};

/**
 * Build a custom action for a weird card or house mechanic out of safe primitives, save it for
 * this card (all printings) or your library, and run it.
 */
export function MacroDialog({ cardId, onClose }: { cardId: string | null; onClose: () => void }) {
  const card = useGame((s) => (cardId ? s.view?.cards[cardId] : undefined));
  const data = useCardCache((s) => (card && isVisible(card) && card.card_id ? s.cards[card.card_id] : undefined));
  const [name, setName] = useState(card && isVisible(card) ? `${card.name} ability` : "My macro");
  const [scope, setScope] = useState<"card" | "library">(data ? "card" : "library");
  const [steps, setSteps] = useState<Step[]>([{ ...OPS.ADD_COUNTER!.base }]);
  const [busy, setBusy] = useState(false);
  const gameId = useGame.getState().view?.game.id ?? "";

  const definition = { name, steps: steps.map((s) => Object.fromEntries(Object.entries(s).filter(([, v]) => v !== "" && v !== undefined))) };
  const update = (i: number, patch: Partial<Step>) => setSteps((all) => all.map((s, j) => (j === i ? { ...s, ...patch } : s)));

  const run = () => void send({ type: "run_macro", macro: definition, card_id: cardId, selected: useGame.getState().selection.filter((id) => id !== cardId) });
  const save = async () => {
    setBusy(true);
    try {
      const t = seatToken(gameId);
      await api.post("/macros", { scope, oracle_id: scope === "card" ? data?.oracle_id : null, definition }, t ? { "X-Seat-Token": t } : {});
      toast(`Saved “${name}”`);
      useMacros.getState().refresh();
      onClose();
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Custom action (macro)" onClose={onClose} wide footer={
      <>
        <span className="hint">Steps run in order as one action — Undo takes back all of it.</span>
        <span className="spacer" />
        <button className="tt-btn" onClick={run} disabled={!steps.length}>Run once</button>
        <button className="tt-btn brass" data-testid="macro-save" onClick={() => void save()} disabled={busy || !steps.length || !name.trim()}>Save</button>
      </>
    }>
      <div className="macro-editor">
        <div className="settings-grid">
          <label className="field">Name<input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} data-testid="macro-name" /></label>
          <label className="field">Keep it for
            <select value={scope} onChange={(e) => setScope(e.target.value as typeof scope)}>
              {data && <option value="card">{data.name} (every copy)</option>}
              <option value="library">My macro library</option>
            </select>
          </label>
        </div>
        {steps.map((step, i) => {
          const spec = OPS[step.op]!;
          return (
            <div key={i} className="macro-step">
              <span className="hint">{i + 1}.</span>
              <select value={step.op} onChange={(e) => update(i, { ...OPS[e.target.value]!.base })}>
                {Object.entries(OPS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
              {step.op === "ADD_MANA" ? (
                ["W", "U", "B", "R", "G", "C"].map((c) => (
                  <label key={c} className="mana-field">{c}
                    <input type="number" min={0} max={20} value={Number((step.mana as Record<string, number>)[c] ?? 0)}
                      onChange={(e) => update(i, { mana: { ...(step.mana as Record<string, number>), [c]: Number(e.target.value) } })} />
                  </label>
                ))
              ) : (
                spec.fields.map(([key, label, kind, options]) => (
                  <label key={key} className="field">{label}
                    {kind === "select" ? (
                      <select value={String(step[key] ?? options![0])} onChange={(e) => update(i, { [key]: e.target.value })}>
                        {options!.map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}
                      </select>
                    ) : (
                      <input type={kind} value={String(step[key] ?? "")} onChange={(e) => update(i, { [key]: kind === "number" ? Number(e.target.value) : e.target.value })} />
                    )}
                  </label>
                ))
              )}
              <button className="tt-icon" title="Remove step" onClick={() => setSteps((all) => all.filter((_, j) => j !== i))}>✕</button>
            </div>
          );
        })}
        {steps.length < 20 && <button className="tt-btn ghost" onClick={() => setSteps((all) => [...all, { ...OPS.DISPLAY_TEXT!.base }])}>+ Add step</button>}
      </div>
    </Modal>
  );
}
