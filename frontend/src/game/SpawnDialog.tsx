import { useState } from "react";
import { CardSearchBox } from "../components/CardSearchBox";
import { Modal } from "../components/Modal";
import { toast } from "../components/Toasts";
import { useGame } from "../state/gameStore";
import { send } from "./actions";
import { spawnOwners } from "./targetDummy";

/** Solo / debug: search the local card database and put any card onto the table as a TEST OBJECT. */
export function SpawnDialog({ onClose }: { onClose: () => void }) {
  const view = useGame((s) => s.view);
  const owners = spawnOwners(view); // -- target dummy -- a test card for it: a blocker or a removal target
  const [owner, setOwner] = useState<string | null>(null);
  const forDummy = owner !== null && owners.some((o) => o.id === owner);
  return (
    <Modal title="Spawn a card (test object)" onClose={onClose}>
      <p className="hint">Spawned cards are marked TEST and are removed by Reset deck — they never become part of your deck.</p>
      {owners.length > 0 && (
        <div className="seg" role="group" aria-label="Whose battlefield" style={{ marginBottom: 12 }}>
          {owners.map((o) => (
            <button key={o.id ?? "you"} className={owner === o.id ? "on" : ""} aria-pressed={owner === o.id} onClick={() => setOwner(o.id)}
              data-testid={o.id ? "spawn-for-dummy" : "spawn-for-me"}>{o.label}</button>
          ))}
        </div>
      )}
      <CardSearchBox placeholder="Search any card…" autoFocus onPick={(card, e) => {
        const zone = e.shiftKey && !forDummy ? "hand" : "battlefield"; // (the dummy has no hand to play from)
        void send({ type: "spawn_card", card_id: card.id, zone, ...(forDummy ? { player: owner } : {}) })
          .then((ok) => ok && toast(`Spawned ${card.name}${forDummy ? " for the dummy" : ""}`));
        if (zone === "battlefield") onClose();
      }} />
      <p className="hint">{forDummy ? "Enter puts it onto the dummy's battlefield; Reset dummy removes it." : "Enter puts it on the battlefield; Shift+Enter into your hand."}</p>
    </Modal>
  );
}
