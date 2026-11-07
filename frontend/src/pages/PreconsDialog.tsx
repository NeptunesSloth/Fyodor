import { useEffect, useMemo, useState } from "react";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/Toasts";
import { addPrecons, listPrecons, type Precon } from "../services/decks";

/** Every Commander precon (bundled, offline): add one, a few or all of them to the library's Precons folder. */
export function PreconsDialog({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [list, setList] = useState<Precon[] | null>(null);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => listPrecons().then(setList, toastError);
  useEffect(() => void load(), []);
  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (list ?? []).filter((p) => !t || `${p.name} ${p.commanders.join(" ")} ${p.set}`.toLowerCase().includes(t));
  }, [list, q]);
  const add = async (ids: string[]) => {
    if (!ids.length) return;
    setBusy(true);
    try {
      const r = await addPrecons(ids);
      toast(r.added ? `Added ${r.added} precon${r.added > 1 ? "s" : ""} to the Precons folder` : "Already in the Precons folder");
      onAdded();
      await load();
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  const missing = shown.filter((p) => !p.added).map((p) => p.id);
  return (
    <Modal title="Add precons" wide onClose={onClose} footer={<>
      <span className="hint">{list ? `${list.length} Commander precons, newest first. They go in the Precons folder.` : "Loading…"}</span>
      <span className="spacer" />
      <button className="tt-btn" onClick={onClose}>Close</button>
      <button className="tt-btn brass" data-testid="precons-add-all" disabled={busy || !missing.length} onClick={() => void add(missing)}>
        {q.trim() ? `Add these ${missing.length}` : `Add all ${missing.length}`}
      </button>
    </>}>
      <input type="search" className="pc-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a precon, commander or set"
        aria-label="Find a precon, commander or set" autoFocus />
      <ul className="pc-list" data-testid="precons">
        {shown.map((p) => (
          <li key={p.id}>
            <span className="pc-name"><b>{p.name}</b><span>{p.commanders.join(" & ")}</span></span>
            <span className="pc-when">{p.set}, {p.released.slice(0, 4)}</span>
            {p.added ? <span className="pc-added">Added</span>
              : <button className="tt-btn ghost" disabled={busy} onClick={() => void add([p.id])}>Add</button>}
          </li>
        ))}
      </ul>
    </Modal>
  );
}
