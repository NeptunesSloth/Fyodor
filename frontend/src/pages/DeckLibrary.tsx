import { useCallback, useEffect, useMemo, useState } from "react";
import { ArtKeeperLine } from "./ArtKeeper";
import { CardFace } from "../cards/CardFace";
import { ColorPips } from "../components/ColorPips";
import { Icon } from "../components/Icon";
import { toast, toastError } from "../components/Toasts";
import { navigate } from "../hooks/useHashRoute";
import { askText } from "../components/Prompt";
import { createDeck, deleteDeck, duplicateDeck, listDecks, moveDeckToFolder, renameDeckFolder } from "../services/decks";
import { podResults } from "../services/pod";
import type { DeckSummary } from "../types/decks";
import type { LobbySeat } from "../types/game";
import { BulkImportDialog } from "./BulkImportDialog";
import { useCommanderPrinting } from "./CommanderArt";
import { deckFolders, deckMatches, deckRecords, playedWhen, recordText, type DeckRecord } from "./deckBits";
import { DeckArt, DeckMenu } from "./DeckParts";
import { ImportDialog } from "./ImportDialog";
import { PreconsDialog } from "./PreconsDialog";
import "./decks.css";

const NO_SEATS: LobbySeat[] = [];
const OPEN_FOLDER = "fyodor.deckFolder"; // the folder the shelf was showing (this browser only)
const EMPTY_FOLDERS = "fyodor.deckFolders.empty"; // folders made here that hold no deck yet
const DRAG_TYPE = "application/x-fyodor-deck";

function stored<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}
function store(key: string, value: unknown): void {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* not remembered */ }
}

/**
 * The deck library as a shelf: each deck stands on a steel plinth under its commander's art (both partners side by side),
 * with its colours, size and how it has done in the pod's recorded games. Play is the one loud action; Edit is quiet; Duplicate
 * and Delete wait behind the deck's menu.
 */
export function DeckLibrary() {
  const [decks, setDecks] = useState<DeckSummary[] | null>(null);
  const [records, setRecords] = useState<Map<string, DeckRecord>>(() => new Map());
  const [importing, setImporting] = useState(false);
  const [bulkImporting, setBulkImporting] = useState(false);
  const [precons, setPrecons] = useState(false);
  const [q, setQ] = useState("");
  const refresh = useCallback(() => listDecks().then(setDecks, toastError), []);
  useEffect(() => void refresh(), [refresh]);
  // the pod's recorded games, for each deck's record (public: Pod stats shows the same); a device that can't read them shows none
  useEffect(() => {
    let live = true;
    podResults(1000).then((r) => live && setRecords(deckRecords(r)), () => undefined);
    return () => { live = false; };
  }, []);

  const onDelete = async (d: DeckSummary) => {
    if (!window.confirm(`Delete "${d.name}"? This cannot be undone.`)) return;
    await deleteDeck(d.id).catch(toastError);
    refresh();
  };
  const onDuplicate = async (d: DeckSummary) => {
    await duplicateDeck(d.id).then(() => toast(`Duplicated ${d.name}`), toastError);
    refresh();
  };
  const onNew = async () => {
    const deck = await createDeck({ name: "New deck", text: "" }).catch(toastError);
    if (deck) navigate(`/decks/${deck.id}`);
  };
  // -- deck folders -- null: every deck (grouped by folder); "": the decks in no folder; a name: that folder
  const [open, setOpenRaw] = useState<string | null>(() => stored<string | null>(OPEN_FOLDER, null));
  const [made, setMadeRaw] = useState<string[]>(() => stored<string[]>(EMPTY_FOLDERS, []));
  const [dropOn, setDropOn] = useState<string | null>(null);
  const setOpen = (f: string | null) => { setOpenRaw(f); store(OPEN_FOLDER, f); };
  const setMade = (list: string[]) => { setMadeRaw(list); store(EMPTY_FOLDERS, list); };
  const folders = useMemo(() => deckFolders(decks ?? [], made), [decks, made]);
  useEffect(() => { // a folder that no longer exists (renamed on another device): back to every deck
    if (decks && open && !folders.some((f) => f.name === open)) setOpen(null);
  }, [decks, folders, open]);
  const moveTo = async (d: DeckSummary, folder: string) => {
    if ((d.folder ?? "") === folder) return;
    await moveDeckToFolder(d.id, folder).then(() => toast(folder ? `Moved ${d.name} to ${folder}` : `Took ${d.name} out of ${d.folder}`), toastError);
    if (folder) setMade(made.filter((f) => f !== folder));
    refresh();
  };
  const newFolder = async (d?: DeckSummary) => {
    const name = (await askText("New folder", "", { label: "Folder name" }))?.split(/\s+/).join(" ").trim().slice(0, 60);
    if (!name) return;
    if (d) await moveTo(d, name);
    else if (!folders.some((f) => f.name === name)) setMade([...made, name]);
    if (!d) setOpen(name);
  };
  const renameFolder = async (old: string) => {
    const name = (await askText(`Rename “${old}”`, old, { label: "Folder name" }))?.split(/\s+/).join(" ").trim().slice(0, 60);
    if (!name || name === old) return;
    await renameDeckFolder(old, name).catch(toastError);
    setMade(made.map((f) => (f === old ? name : f)));
    setOpen(name);
    refresh();
  };
  const removeFolder = async (name: string) => {
    const n = decks?.filter((d) => d.folder === name).length ?? 0;
    if (n && !window.confirm(`Remove the folder “${name}”? Its ${n === 1 ? "deck stays" : `${n} decks stay`} on the shelf; nothing is deleted.`)) return;
    if (n) await renameDeckFolder(name, "").catch(toastError);
    setMade(made.filter((f) => f !== name));
    setOpen(null);
    refresh();
  };
  const dropProps = (folder: string) => ({
    onDragOver: (e: React.DragEvent) => {
      if (!e.dataTransfer.types.includes(DRAG_TYPE)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      setDropOn(folder);
    },
    onDragLeave: () => setDropOn((f) => (f === folder ? null : f)),
    onDrop: (e: React.DragEvent) => {
      setDropOn(null);
      const d = decks?.find((x) => x.id === e.dataTransfer.getData(DRAG_TYPE));
      if (d) { e.preventDefault(); void moveTo(d, folder); }
    },
  });
  const matching = useMemo(() => decks?.filter((d) => deckMatches(d, q)) ?? null, [decks, q]);
  // a search looks through every folder
  const shown = useMemo(() => (q || open === null ? matching : matching?.filter((d) => (d.folder ?? "") === open) ?? null), [matching, open, q]);
  const grouped = !q && open === null && folders.length > 0;
  const empty = decks?.length === 0;
  const tile = (d: DeckSummary) => (
    <DeckTile key={d.id} deck={d} record={records.get(d.id)} onDelete={() => void onDelete(d)} onDuplicate={() => void onDuplicate(d)}
      folders={folders.map((f) => f.name)} onMove={(f) => void moveTo(d, f)} onNewFolder={() => void newFolder(d)} />
  );
  const unfiled = decks?.filter((d) => !d.folder).length ?? 0;

  return (
    <div className="page dk-page">
      <header className="dk-head">
        <div className="dk-title">
          <h1>Decks</h1>
          {decks && decks.length > 0 && <p className="dk-count">{decks.length === 1 ? "One deck" : `${decks.length} decks`}</p>}
        </div>
        {decks && decks.length > 6 && (
          <input type="search" className="dk-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a deck or a commander"
            aria-label="Find a deck or a commander" />
        )}
        <div className="dk-head-acts">
          <button className="tt-btn ghost" onClick={onNew}><Icon name="plus" size={15} />New empty deck</button>
          <button className="tt-btn ghost" onClick={() => setBulkImporting(true)}><Icon name="cards" size={15} />Import multiple decks</button>
          <button className="tt-btn ghost" data-testid="open-precons" onClick={() => setPrecons(true)}><Icon name="folder" size={15} />Add precons</button>
          {/* with no decks yet the empty shelf carries this button */}
          {!empty && <button className="tt-btn brass dk-import" onClick={() => setImporting(true)}><Icon name="download" size={16} />Import a deck</button>}
        </div>
      </header>

      <ArtKeeperLine />
      {empty && <EmptyShelf onImport={() => setImporting(true)} />}
      {decks && decks.length > 0 && (
        <nav className="dk-folders" aria-label="Deck folders" data-testid="deck-folders">
          <button className={`dk-folder ${open === null ? "on" : ""}`} aria-pressed={open === null} onClick={() => setOpen(null)}>
            All decks <span className="n">{decks.length}</span>
          </button>
          {folders.map((f) => (
            <button key={f.name} className={`dk-folder ${open === f.name ? "on" : ""} ${dropOn === f.name ? "drop" : ""}`} aria-pressed={open === f.name}
              onClick={() => setOpen(f.name)} {...dropProps(f.name)} data-testid="deck-folder">
              <Icon name="folder" size={15} />{f.name} <span className="n">{f.count}</span>
            </button>
          ))}
          {folders.length > 0 && (
            <button className={`dk-folder loose ${open === "" ? "on" : ""} ${dropOn === "" ? "drop" : ""}`} aria-pressed={open === ""}
              onClick={() => setOpen("")} {...dropProps("")}>
              Not in a folder <span className="n">{unfiled}</span>
            </button>
          )}
          <button className="dk-folder add" onClick={() => void newFolder()} title="Make a folder, then drag decks onto it (or use a deck's ··· menu)">
            <Icon name="plus" size={14} />New folder
          </button>
          {open && (
            <span className="dk-folder-acts">
              <button className="tt-link" onClick={() => void renameFolder(open)}>Rename</button>
              <button className="tt-link" onClick={() => void removeFolder(open)}>Remove folder</button>
            </span>
          )}
        </nav>
      )}
      {grouped && shown ? (
        [...folders.map((f) => f.name), ""].map((name) => {
          const inside = shown.filter((d) => (d.folder ?? "") === name);
          if (!inside.length) return null;
          return (
            <section key={name || "-"} className={`dk-group ${dropOn === name ? "drop" : ""}`} {...dropProps(name)}>
              <h2 className="dk-group-head">
                <button className="tt-link" onClick={() => setOpen(name)}>
                  {name ? <><Icon name="folder" size={16} />{name}</> : "Not in a folder"}
                </button>
                <span className="n">{inside.length}</span>
              </h2>
              <ul className="dk-grid">{inside.map(tile)}</ul>
            </section>
          );
        })
      ) : shown && shown.length > 0 && <ul className="dk-grid">{shown.map(tile)}</ul>}
      {!q && open !== null && shown?.length === 0 && (
        <p className="dk-none">{open ? <>“{open}” is empty. Drag a deck onto its name above, or use a deck's <b>···</b> menu → <i>Move to {open}</i>.</> : "Every deck is in a folder."}</p>
      )}
      {q && shown?.length === 0 && <p className="dk-none">No deck or commander matches “{q.trim()}”.</p>}

      {precons && <PreconsDialog onClose={() => setPrecons(false)} onAdded={() => void refresh()} />}
      {bulkImporting && <BulkImportDialog onClose={() => setBulkImporting(false)} onSaved={() => void refresh()} />}
      {importing && (
        <ImportDialog
          onClose={() => setImporting(false)}
          onCreated={(id, jobId) => {
            setImporting(false);
            navigate(`/decks/${id}${jobId ? `?job=${jobId}` : ""}`);
          }}
        />
      )}
    </div>
  );
}

function DeckTile({ deck, record, onDelete, onDuplicate, folders, onMove, onNewFolder }: {
  deck: DeckSummary; record: DeckRecord | undefined; onDelete: () => void; onDuplicate: () => void;
  folders: string[]; onMove: (folder: string) => void; onNewFolder: () => void;
}) {
  const [menu, setMenu] = useState(false);
  // the cover is the first commander's printing; a partner's comes from the card database
  const partner = useCommanderPrinting(deck.commanders.length > 1 ? deck.commanders[1]! : null, NO_SEATS);
  const total = (deck.counts.main ?? 0) + (deck.counts.commander ?? 0);
  const cmdrs = deck.commanders.join(" & ");
  const href = `#/decks/${deck.id}`;
  return (
    <li className={`dk-deck ${menu ? "menu-open" : ""}`} draggable
      onDragStart={(e) => { e.dataTransfer.setData(DRAG_TYPE, deck.id); e.dataTransfer.effectAllowed = "move"; }}>
      <a className="dk-art-link" href={href} tabIndex={-1} aria-hidden>
        <DeckArt ids={deck.commanders.length > 1 ? [deck.cover_id, partner] : [deck.cover_id]} wash={deck.color_identity} label={cmdrs || deck.name} />
      </a>
      <div className="dk-text">
        <h2 className="dk-name"><a href={href}>{deck.name}</a></h2>
        {deck.commanders.length > 0 && cmdrs !== deck.name && <p className="dk-cmdr">{cmdrs}</p>}
        {deck.commanders.length === 0 && <p className="dk-cmdr none">No commander chosen</p>}
        <p className="dk-facts">
          <ColorPips colors={deck.color_identity} />
          <span>{total} cards</span>
          {deck.unresolved > 0 && <span className="dk-warn">{deck.unresolved} not found</span>}
        </p>
        {record && (
          <p className="dk-record">
            <span>{recordText(record)}</span>
            <span>Played {playedWhen(record.last)}</span>
          </p>
        )}
      </div>
      <div className="dk-acts">
        <a className="tt-btn dk-play" href={`#/play?deck=${deck.id}`} aria-label={`Play ${deck.name}`}><Icon name="swords" size={15} />Play</a>
        <a className="tt-btn ghost dk-edit" href={href} aria-label={`Edit ${deck.name}`}><Icon name="pen" size={14} />Edit</a>
        <DeckMenu label={`More for ${deck.name}`} open={menu} onOpenChange={setMenu} className="dk-more" items={[
          { label: "Duplicate", icon: "cards", onClick: onDuplicate },
          "separator",
          ...folders.filter((f) => f !== deck.folder).slice(0, 8).map((f) => ({ label: `Move to ${f}`, icon: "folder" as const, onClick: () => onMove(f) })),
          { label: "Move to a new folder…", icon: "plus", onClick: onNewFolder },
          ...(deck.folder ? [{ label: `Take out of ${deck.folder}`, onClick: () => onMove("") }] : []),
          "separator",
          { label: "Delete…", icon: "trash", danger: true, onClick: onDelete },
        ]} />
      </div>
    </li>
  );
}

/** No decks yet: three face-down cards and the way to fill the shelf. */
function EmptyShelf({ onImport }: { onImport: () => void }) {
  return (
    <section className="dk-empty" aria-labelledby="dk-empty-title">
      <div className="dk-empty-cards" aria-hidden>
        {[0, 1, 2].map((i) => <span key={i} className="dk-empty-card" style={{ "--i": i } as React.CSSProperties}><CardFace faceDown /></span>)}
      </div>
      <div className="dk-empty-text">
        <h2 id="dk-empty-title">No decks on the shelf yet</h2>
        <p>Paste an Archidekt link or a list from Moxfield, MTGGoldfish, Arena or plain text. The deck is kept on this computer, so the pod can play it without the Internet.</p>
        <button className="tt-btn brass" onClick={onImport}><Icon name="download" size={16} />Import your first deck</button>
        <p className="dk-empty-more">Bringing a whole collection? Use <b>Import multiple decks</b> above.</p>
      </div>
    </section>
  );
}
