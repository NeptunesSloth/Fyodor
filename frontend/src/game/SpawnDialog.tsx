import { CardSearchBox } from "../components/CardSearchBox";
import { Modal } from "../components/Modal";
import { toast } from "../components/Toasts";
import { send } from "./actions";

/** Solo / debug: search the local card database and put any card onto the table as a TEST OBJECT. */
export function SpawnDialog({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="Spawn a card (test object)" onClose={onClose}>
      <p className="hint">Spawned cards are marked TEST and are removed by Reset deck — they never become part of your deck.</p>
      <CardSearchBox placeholder="Search any card…" autoFocus onPick={(card, e) => {
        void send({ type: "spawn_card", card_id: card.id, zone: e.shiftKey ? "hand" : "battlefield" }).then((ok) => ok && toast(`Spawned ${card.name}`));
        if (!e.shiftKey) onClose();
      }} />
      <p className="hint">Enter puts it on the battlefield; Shift+Enter into your hand.</p>
    </Modal>
  );
}
