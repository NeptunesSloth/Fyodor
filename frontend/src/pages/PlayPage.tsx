/**
 * Play: the card room's front door. On the left the LAN night you're setting up (the pod joins from their own computers; a
 * host alone at the table is solo testing), Commander or Sandbox, its seats showing each commander; on the right the door
 * (join with a room code) and the shelf of tables in progress and saved games, each shown with its commanders. Hot-seat tables
 * from before (everyone at this computer) still open and load from the shelf; new ones aren't offered.
 */
import { activeProfile, usePrefs } from "../state/prefs";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CardFace } from "../cards/CardFace";
import { ColorPips } from "../components/ColorPips";
import { Icon } from "../components/Icon";
import { CONFIGURABLE_RULES, MULLIGAN_RULES, MulliganEditor, draftPolicy, rememberPolicy } from "../components/MulliganEditor";
import type { AutomationLevel, MulliganPolicy, TableFormat } from "../types/game";
import { FORMAT_NAME, SANDBOX_RAIL, TABLE_FORMATS, isSandbox } from "../game/tableFormat";
import { toast, toastError } from "../components/Toasts";
import { navigate, type Route } from "../hooks/useHashRoute";
import { ApiError } from "../services/api";
import { listDecks } from "../services/decks";
import {
  closeGame,
  createGame,
  tableAction,
  deleteSave,
  joinGame,
  lanInfo,
  listGames,
  listSaves,
  importPackage,
  packageUrl,
  loadSave,
  rememberSeat,
  seatToken,
  submitLobbyDeck,
  type CreatePlayer,
} from "../services/games";
import type { DeckSummary } from "../types/decks";
import type { GameSummary, SaveSummary } from "../types/game";
import { CommanderArt } from "./CommanderArt";
import { DeckPicker } from "./DeckPicker";
import { orderGames, ownName, planInvite, readInvite, tileActions, withoutInvite, type Invite } from "./lanBits";
import { NearbyGames } from "./NearbyGames";
import { deckSubtitle, deckTitle, shelfSaves } from "./playBits";
import { SEAT_COLORS, SeatChip, TableMosaic, chipStyle, whenSaved } from "./tableBits";

const COLORS = SEAT_COLORS;

/** The automation levels by the names the table uses (the rules HUD, the lobby's house rules). */
const AUTOMATION_NAME: Record<AutomationLevel, string> = { off: "Off", assisted: "Assisted", full: "Full" };
const AUTOMATION_HINT: Record<AutomationLevel, string> = {
  off: "Nothing is enforced; you move everything by hand.",
  assisted: "The rules engine checks, and asks before important steps.",
  full: "Supported rules happen by themselves.",
};

/** Join links already acted on in this page's life (a re-render or React's double effect never joins twice). */
const handledInvites = new Set<string>();

/** Take a seat (or watch) with a room code: the profile's preferred seat when it's free, otherwise any, then go to the table. */
async function joinTable(body: { code: string; name?: string; password?: string; spectate: boolean; handoff?: string | null }): Promise<void> {
  const preferred = usePrefs.getState().preferredSeat;
  const res = preferred && !body.spectate
    ? await joinGame({ ...body, seat: preferred }).catch(() => joinGame(body))
    : await joinGame(body);
  rememberSeat(res.game_id, res.token);
  navigate(`/game/${res.game_id}`);
}

export function PlayPage({ route }: { route: Route }) {
  const [host, setHost] = useState<boolean | null>(null);
  const [games, setGames] = useState<GameSummary[] | null>(null);
  const [saves, setSaves] = useState<SaveSummary[]>([]);
  const [decks, setDecks] = useState<DeckSummary[]>([]);

  const refresh = useCallback(() => {
    listGames().then(setGames, (e) => {
      setGames((g) => g ?? []);
      toastError(e);
    });
    listSaves().then(
      (s) => {
        listDecks().then(setDecks, toastError); // the deck library lives on the host only
        setSaves(shelfSaves(s));
        setHost(true);
      },
      (e) => {
        if (e instanceof ApiError && e.status === 403) setHost(false);
        else toastError(e);
      },
    );
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);

  // A join link (#/play?code=…&name=…&join=1, or watch=1), e.g. from "Games on your network" on a player's own Fyodor: join
  // at once when the table needs no password (or open the seat this browser already holds there); otherwise fill the code and
  // the name in and ask for the password. The parameters come off the address either way.
  const invite = useMemo(() => readInvite(route.query), [route.query]);
  const [askPassword, setAskPassword] = useState(false);
  useEffect(() => {
    if (!invite || invite.action === "fill" || games === null) return;
    const key = `${invite.code}|${invite.action}|${invite.name}|${invite.handoff ?? ""}`;
    if (handledInvites.has(key)) return;
    handledInvites.add(key);
    window.history.replaceState(window.history.state, "", withoutInvite(window.location.hash));
    const plan = planInvite(invite, games, (id) => !!seatToken(id));
    if (plan.kind === "open") navigate(`/game/${plan.gameId}`);
    else if (plan.kind === "password") setAskPassword(true);
    else if (plan.kind === "join") {
      void joinTable({ code: invite.code, name: invite.name || undefined, spectate: plan.spectate, handoff: plan.spectate ? null : invite.handoff })
        .catch(toastError);
    }
  }, [invite, games]);

  // "Resume a game" on the launcher opens the shelf
  const shelf = useRef<HTMLDetailsElement>(null);
  const wantsShelf = route.query.get("tab") === "saves";
  useEffect(() => {
    if (!wantsShelf || host === null) return;
    shelf.current?.scrollIntoView({ block: "start" });
    shelf.current?.querySelector<HTMLElement>("h2")?.focus({ preventScroll: true });
  }, [wantsShelf, host]);

  return (
    <div className="page play">
      <div className="pg-grid">
        <div className="pg-main">
          {host !== false && <NewGame decks={decks} preselect={route.query.get("deck")} />}
          {host === false && (
            <section className="pg-remote" aria-labelledby="pg-remote-title">
              <Icon name="table" size={30} />
              <h1 id="pg-remote-title">You're connected to a host</h1>
              <p>Games are created on the host computer. Join one with its room code: ask the host for it, or find it among the open tables.</p>
            </section>
          )}
        </div>
        <aside className="pg-side">
          <JoinGame key={invite ? `${invite.code} ${invite.action}` : "door"} invite={invite} askPassword={askPassword} />
          {host && <NearbyGames deckCount={decks.length} />}
          <details className="pg-shelf" ref={shelf} open={wantsShelf || host === false || undefined /* a guest joins from here: open */}>
            <summary><h2 id="pg-shelf-title" tabIndex={-1}>Tables in progress <span className="pg-n">{games?.length ?? 0}</span></h2></summary>
            {!games?.length ? (
              <p className="pg-empty">No tables are open. A game shows up here while it's being played.</p>
            ) : (
              <ul className="pg-tiles">
                {orderGames(games).map((g) => <TableTile key={g.id} game={g} host={host} onClosed={refresh} />)}
              </ul>
            )}
          </details>
          {host && (
            <details className="pg-shelf" open={wantsShelf || undefined}>
              <summary className="pg-shelf-head">
                  <h2>Saved games <span className="pg-n">{saves.length}</span></h2>
                  <label className="tt-btn ghost pg-import" title="Import a .fyodor.zip game package from another pod computer">
                    Import package…
                    <input type="file" accept=".zip,application/zip" hidden data-testid="package-import" onChange={async (e) => {
                      const file = e.target.files?.[0];
                      e.target.value = "";
                      if (!file) return;
                      try {
                        const r = await importPackage(file);
                        toast(`Imported “${r.save.name}” · ${r.assets_added} image(s), ${r.macros_added} macro(s) added`);
                        refresh();
                      } catch (err) {
                        toastError(err);
                      }
                    }} />
                  </label>
              </summary>
                {saves.length === 0 ? (
                  <p className="pg-empty">Nothing saved yet. Games autosave while you play.</p>
                ) : (
                  <ul className="pg-tiles">
                    {saves.map((s) => <SaveTile key={s.id} save={s} onDeleted={refresh} />)}
                  </ul>
                )}
            </details>
          )}
          {host && <LanHint />}
        </aside>
      </div>
    </div>
  );
}

/**
 * A new game is a LAN night: the pod joins from their own computers with the room code (the host alone at the table is solo
 * testing). Its format is Commander, or Sandbox: free play with the same Commander decks.
 */
function NewGame({ decks, preselect }: { decks: DeckSummary[]; preselect: string | null }) {
  const [name, setName] = useState("Commander night");
  const [format, setFormat] = useState<TableFormat>("commander");
  const sandbox = isSandbox(format);
  const [password, setPassword] = useState("");
  const [first, setFirst] = useState<string>("random");
  const [life, setLife] = useState<string>("40");
  const [lobby, setLobby] = useState(true);
  const seats = 4; // open seats: the room sets them (Table settings, once it is open)
  const [privacy, setPrivacy] = useState<"private" | "commander_only" | "public">("commander_only");
  const [mulligan, setMulligan] = useState("commander_london");
  const [policy, setPolicy] = useState<MulliganPolicy | null>(null);
  const configurable = CONFIGURABLE_RULES.has(mulligan);
  const chooseRule = (rule: string) => {
    setMulligan(rule);
    setPolicy(CONFIGURABLE_RULES.has(rule) ? draftPolicy(rule) : null);
  };
  const [helper, setHelper] = useState<"off" | "simple">("simple");
  const [automation, setAutomation] = useState<AutomationLevel>("full"); // the pod plays Commander at Full (the API's own default stays Off)
  const useLobby = lobby;
  const level: AutomationLevel = automation; // (a Sandbox table starts manual on the server; its chosen level is switched on at once)
  const [players, setPlayers] = useState<CreatePlayer[]>([
    { name: ownName(activeProfile().name) || "Player 1", deck_id: preselect, color: COLORS[0] }, // the host's seat: their profile's name
    { name: "Seat 2", deck_id: null, color: COLORS[1] },
  ]);
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState<number | null>(null);
  // the deck the host brings to their own lobby seat: one chosen here ("Play a deck" on the launcher, or this seat's picker),
  // never a default; everyone else, and a host who chose none, brings a deck in the lobby
  const [hostDeck, setHostDeck] = useState<string | null>(preselect);
  const [pickingHost, setPickingHost] = useState(false);

  useEffect(() => {
    if (preselect) setPlayers((ps) => ps.map((p, i) => (i === 0 ? { ...p, deck_id: preselect } : p)));
    if (preselect) setHostDeck(preselect);
  }, [preselect]);
  useEffect(() => {
    // default the second player to another deck when decks load
    setPlayers((ps) => ps.map((p, i) => (p.deck_id || !decks.length ? p : { ...p, deck_id: decks[Math.min(i, decks.length - 1)]!.id })));
  }, [decks]);

  const update = (i: number, patch: Partial<CreatePlayer>) => setPlayers((ps) => ps.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  const usedBy = useMemo(() => {
    const m = new Map<string, string[]>();
    players.forEach((p, i) => {
      if (!p.deck_id || i === picking) return;
      m.set(p.deck_id, [...(m.get(p.deck_id) ?? []), p.name.trim() || `Seat ${i + 1}`]);
    });
    return m;
  }, [players, picking]);

  const start = async () => {
    setBusy(true);
    try {
      if (sandbox) {
        // -- Sandbox: test a deck on your own -- one seat, your deck dealt at once, no lobby and nobody joining
        const res = await createGame({
          name: name.trim() || "Deck test",
          format,
          mode: "lan",
          players: [{ name: players[0]?.name.trim() || "Player 1", deck_id: hostDeck, color: players[0]?.color }],
          shuffle: true,
          lobby: false,
          seats: 1,
          mulligan_rule: mulligan,
          mulligan_policy: configurable ? policy : null,
          priority_helper: helper,
          automation: "off", // (the server starts a Sandbox table manual; the level chosen here is switched on just after)
          first_player: 0,
          starting_life: life ? Number(life) : null,
          auto_untap: true,
        });
        if (configurable && policy) rememberPolicy(mulligan, policy);
        if (res.seat) rememberSeat(res.game.id, res.seat.token);
        if (automation !== "off") await tableAction(res.game.id, { type: "configure", automation }).catch(toastError);
        navigate(`/game/${res.game.id}`);
        return;
      }
      const res = await createGame({
        name: name.trim() || "Game",
        format,
        mode: "lan",
        password: password || null,
        players: useLobby ? [{ name: players[0]?.name.trim() || "Host", deck_id: null }] : players.map((p, i) => ({ ...p, name: p.name.trim() || `Seat ${i + 1}` })),
        shuffle: true,
        lobby: useLobby,
        turn_order: "pod", // the pod's own rule is the default for game nights (Table settings can change it)
        seats,
        deck_privacy: privacy,
        mulligan_rule: mulligan,
        mulligan_policy: configurable ? policy : null,
        priority_helper: helper,
        automation: level,
        first_player: first === "random" ? "random" : Number(first),
        starting_life: life ? Number(life) : null,
        auto_untap: true,
      });
      if (configurable && policy) rememberPolicy(mulligan, policy);
      if (res.seat) rememberSeat(res.game.id, res.seat.token);
      if (useLobby && hostDeck && res.seat) await submitLobbyDeck(res.game.id, { deck_id: hostDeck }).catch(toastError);
      navigate(`/game/${res.game.id}`);
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  const picked = picking !== null ? players[picking] : undefined;

  return (
    <section className="pg-new" aria-labelledby="pg-new-title">
      <div className="pg-table" data-format={format}>
        <header className="pg-head">
          <div className="pg-head-title">
            <h1 id="pg-new-title">{sandbox ? "Test a deck" : "Host a LAN night"}</h1>
            <p>{sandbox ? "Just you and your deck at the table. Nobody joins; nothing is checked." : "The pod joins from their own computers with the room code."}</p>
          </div>
        </header>

        <div className="pg-formats" role="radiogroup" aria-label="Format" data-testid="table-format">
          {TABLE_FORMATS.map((f) => (
            <label key={f.id} className={`pg-format ${format === f.id ? "on" : ""}`}>
              <input type="radio" name="table-format" value={f.id} checked={format === f.id} data-testid={`format-${f.id}`} onChange={() => {
                // the default table name follows the format until the host names the table
                const usual = (t: TableFormat) => (t === "sandbox" ? "Deck test" : `${FORMAT_NAME[t]} night`);
                if (name === usual(format)) setName(usual(f.id));
                // a deck test starts manual, free play (its level is still yours to choose); back to Commander: Full, as the pod plays
                if (f.id !== format) setAutomation(f.id === "sandbox" ? "off" : "full");
                setFormat(f.id);
              }} />
              <span className="pg-format-icon"><Icon name={f.icon} size={24} /></span>
              <span className="pg-format-text">
                <b>{f.name}</b>
                <span>{f.lines.map((l) => <span key={l} className="pg-format-line">{l}</span>)}</span>
              </span>
            </label>
          ))}
        </div>

        <div className="pg-setup">
          <label className="pg-title" title="Rename this table">
            <span className="pg-setup-label">Table name</span>
            <span className="pg-title-field">
              <input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} spellCheck={false} data-testid="table-name" />
              <Icon name="pen" size={14} className="pg-title-pen" />
            </span>
          </label>
          {!sandbox && <div className="pg-decks">
            <span className="pg-setup-label" id="pg-decks-label">Decks</span>
            <span className="pg-segs" role="radiogroup" aria-labelledby="pg-decks-label">
              <label className={lobby ? "on" : ""} title="Everyone takes a seat in the lobby and brings their own deck">
                <input type="radio" name="table-decks" checked={lobby} onChange={() => setLobby(true)} data-testid="decks-own" />Players bring their own
              </label>
              <label className={lobby ? "" : "on"} title="You give each seat a deck from your library; the pod joins and plays them">
                <input type="radio" name="table-decks" checked={!lobby} onChange={() => setLobby(false)} data-testid="decks-dealt" />You deal them
              </label>
            </span>
          </div>}
        </div>

        {sandbox ? (
          // -- Sandbox -- one seat: yours, with the deck you're testing
          <ul className="pg-seats pg-lobby pg-solo" aria-label="Your seat" data-testid="sandbox-seat">
            <li className="pg-seat host">
              <div className="pg-plate">
                <SeatChip color={COLORS[0]} text="1" />
                <label className="pg-name-field">
                  <span className="pg-name-label">Your name</span>
                  <input className="pg-name" data-testid="host-name" value={players[0]?.name ?? ""} maxLength={40} onChange={(e) => update(0, { name: e.target.value })} />
                </label>
              </div>
              <HostDeck deck={decks.find((d) => d.id === hostDeck)} canPick={decks.length > 0} onPick={() => setPickingHost(true)} onClear={() => setHostDeck(null)}
                note={decks.length ? "Choose the deck you want to test." : "No decks yet: import one on the Decks page."} />
            </li>
          </ul>
        ) : useLobby ? (
          <ul className="pg-seats pg-lobby pg-solo" aria-label="Your seat">
            <li className="pg-seat host">
              <div className="pg-plate">
                <SeatChip color={COLORS[0]} text="1" />
                <label className="pg-name-field">
                  <span className="pg-name-label">Your name</span>
                  <input className="pg-name" data-testid="host-name" value={players[0]?.name ?? ""} maxLength={40} onChange={(e) => update(0, { name: e.target.value })} />
                </label>
              </div>
              <HostDeck deck={decks.find((d) => d.id === hostDeck)} canPick={decks.length > 0} onPick={() => setPickingHost(true)} onClear={() => setHostDeck(null)} />
            </li>
            <li className="pg-seats-later">
              <p>The other seats open with the room. Friends take one from their own computers with the room code; you change how many in the room's Table settings.</p>
            </li>
          </ul>
        ) : (
          <ul className="pg-seats pg-dealt" aria-label="Seats">
            {players.map((p, i) => {
              const deck = decks.find((d) => d.id === p.deck_id);
              const label = i === 0 ? "Your name" : `Seat ${i + 1}`;
              return (
                <li key={i} className="pg-seat" style={chipStyle(p.color)}>
                  <div className="pg-plate">
                    <label className="pg-chip pg-chip-edit" title="Seat colour: click to change it">
                      <span aria-hidden>{i + 1}</span>
                      <input type="color" value={p.color} onChange={(e) => update(i, { color: e.target.value })} aria-label={`Seat ${i + 1} colour`} />
                    </label>
                    <label className="pg-name-field">
                      <span className="pg-name-label">{i === 0 ? "Your name" : "Joins with the room code"}</span>
                      <input className="pg-name" value={p.name} maxLength={40} placeholder={`Seat ${i + 1}`} onChange={(e) => update(i, { name: e.target.value })}
                        aria-label={i === 0 ? label : `${label}: player name`} data-testid={i === 0 ? "host-name" : undefined} />
                    </label>
                  </div>
                  <button className={`pg-art ${deck ? "" : "no-deck"}`} onClick={() => setPicking(i)}
                    aria-label={`${label} deck: ${deck ? `${deck.name}${deck.commanders.length ? `, ${deck.commanders.join(" & ")}` : ""}` : "none"}. Choose a deck`}>
                    {deck ? (deck.commanders.length && deck.cover_id ? <CommanderArt id={deck.cover_id} /> : <CommanderArt back />) : (
                      <span className="pg-slot"><Icon name="cards" size={26} /><span>Choose a deck</span></span>
                    )}
                  </button>
                  <div className="pg-deck">
                    {deck ? (
                      <>
                        <p className="pg-cmdr" title={deckTitle(deck)}>{deckTitle(deck)}</p>
                        <p className="pg-sub">{deckSubtitle(deck) && <span className="pg-deckname">{deckSubtitle(deck)}</span>}<ColorPips colors={deck.color_identity} /></p>
                      </>
                    ) : (
                      <p className="pg-note">{decks.length ? "No deck: an empty library." : <>No decks yet. <a href="#/decks">Import some decks</a>, or play with empty libraries.</>}</p>
                    )}
                  </div>
                  <div className="pg-seat-foot">
                    {decks.length > 0 && <button className="tt-btn" onClick={() => setPicking(i)}>{deck ? "Change deck" : "Choose deck"}</button>}
                    {players.length > 1 && (
                      <button className="tt-icon pg-remove" onClick={() => setPlayers((ps) => ps.filter((_, j) => j !== i))} aria-label="Remove a seat" title={`Remove seat ${i + 1}`}>
                        <Icon name="close" size={14} />
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
            {players.length < 6 && (
              <li className="pg-add-wrap">
                <button className="pg-add" onClick={() => setPlayers((ps) => [...ps, { name: `Seat ${ps.length + 1}`, deck_id: decks[ps.length % Math.max(1, decks.length)]?.id ?? null, color: COLORS[ps.length % COLORS.length] }])}>
                  <Icon name="plus" size={18} />Add a seat
                </button>
              </li>
            )}
          </ul>
        )}

        {configurable && policy && <div className="pg-mull"><MulliganEditor value={policy} onChange={setPolicy} /></div>}

        <footer className="pg-rail">
          <div className="pg-rules">
            {!sandbox && <label className="pg-rule pg-pass">
              <span>Password</span>
              <input type="password" value={password} maxLength={100} onChange={(e) => setPassword(e.target.value)} placeholder="None" autoComplete="new-password" />
            </label>}
            <label className="pg-rule">
              <span>Starting life</span>
              <input type="number" value={life} min={1} onChange={(e) => setLife(e.target.value)} placeholder="40" />
            </label>
            <label className="pg-rule">
              <span>Opening hands</span>
              <select value={mulligan} onChange={(e) => chooseRule(e.target.value)} data-testid="mulligan-rule">
                {MULLIGAN_RULES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            {(
              <label className="pg-rule">
                <span>Automation</span>
                <select data-testid="automation-level" value={automation} onChange={(e) => setAutomation(e.target.value as AutomationLevel)} aria-describedby="pg-auto-hint">
                  {(["off", "assisted", "full"] as const).map((lv) => <option key={lv} value={lv}>{AUTOMATION_NAME[lv]}</option>)}
                </select>
              </label>
            )}
            {!useLobby && !sandbox && (
              <label className="pg-rule">
                <span>Who starts</span>
                <select data-testid="first-player" value={first} onChange={(e) => setFirst(e.target.value)}>
                  <option value="random">Random</option>
                  {players.map((p, i) => <option key={i} value={i}>{p.name}</option>)}
                </select>
              </label>
            )}
            {useLobby && !sandbox && (
              <label className="pg-rule">
                <span>Deck privacy</span>
                <select value={privacy} onChange={(e) => setPrivacy(e.target.value as typeof privacy)} data-testid="deck-privacy">
                  <option value="private">Private</option>
                  <option value="commander_only">Commander only</option>
                  <option value="public">Public</option>
                </select>
              </label>
            )}
            {level === "off" && (
              <label className="pg-rule">
                <span>Response helper</span>
                <select value={helper} onChange={(e) => setHelper(e.target.value as typeof helper)}>
                  <option value="simple">On</option>
                  <option value="off">Off</option>
                </select>
              </label>
            )}
          </div>
          <p className="pg-rail-note">
            <span id="pg-auto-hint">{sandbox ? <><b>Sandbox.</b> {SANDBOX_RAIL}</> : <><b>Automation {AUTOMATION_NAME[level]}.</b> {AUTOMATION_HINT[level]}</>}</span>{" "}
            {sandbox ? `Automation ${AUTOMATION_NAME[level]}: ${AUTOMATION_HINT[level]}` : useLobby ? "The pod brings decks in the lobby; you start from there."
              : `The pod joins with the room code.${mulligan === "none" ? " With “None” everyone draws by hand." : ""}`}
          </p>
          <button className="pg-start" disabled={busy || (sandbox && !hostDeck)} onClick={() => void start()} data-testid="create-game"
            title={sandbox && !hostDeck ? "Choose the deck to test first" : undefined}>
            {busy ? "Setting up…" : sandbox ? "Start testing" : useLobby ? "Open the table" : "Deal and start"}
          </button>
        </footer>
      </div>

      {pickingHost && (
        <DeckPicker decks={decks} value={hostDeck} seat={players[0]?.name.trim() || "You"} usedBy={new Map()}
          onClose={() => setPickingHost(false)} onPick={(id) => { setHostDeck(id); setPickingHost(false); }} />
      )}
      {picked && picking !== null && (
        <DeckPicker decks={decks} value={picked.deck_id ?? null} seat={picked.name.trim() || `Seat ${picking + 1}`} usedBy={usedBy}
          onClose={() => setPicking(null)} onPick={(id) => { update(picking, { deck_id: id }); setPicking(null); }} />
      )}
    </section>
  );
}

/** The host's own lobby seat: the deck they bring (chosen here, or later in the lobby like everyone else). */
function HostDeck({ deck, canPick, onPick, onClear, note = "You host. Choose your deck here or in the lobby." }: { deck: DeckSummary | undefined; canPick: boolean; onPick: () => void; onClear: () => void; note?: string }) {
  return (
    <>
      <button className={`pg-art ${deck ? "" : "no-deck"}`} onClick={onPick} disabled={!canPick} data-testid="host-deck"
        aria-label={`Your deck: ${deck ? `${deck.name}${deck.commanders.length ? `, ${deck.commanders.join(" & ")}` : ""}` : "none yet"}. Choose a deck`}>
        {deck ? (deck.commanders.length && deck.cover_id ? <CommanderArt id={deck.cover_id} /> : <CommanderArt back />) : (
          // the deck this seat is waiting for, face down on the felt (the real back, as in the lobby)
          <span className="pg-slot pg-slot-waiting">
            <span className="pg-waiting" aria-hidden><CardFace faceDown /><CardFace faceDown /></span>
            {canPick && <span className="pg-slot-word"><Icon name="cards" size={16} />Choose a deck</span>}
          </span>
        )}
      </button>
      <div className="pg-deck">
        {deck ? (
          <>
            <p className="pg-cmdr" title={deckTitle(deck)}>{deckTitle(deck)}</p>
            <p className="pg-sub">{deckSubtitle(deck) && <span className="pg-deckname">{deckSubtitle(deck)}</span>}<ColorPips colors={deck.color_identity} /></p>
          </>
        ) : (
          <p className="pg-note">{note}</p>
        )}
      </div>
      {canPick && deck && (
        <div className="pg-seat-foot">
          <button className="tt-btn" onClick={onPick}>Change deck</button>
          <button className="tt-icon pg-remove" onClick={onClear} aria-label="Bring a deck in the lobby instead" title="Bring a deck in the lobby instead">
            <Icon name="close" size={14} />
          </button>
        </div>
      )}
    </>
  );
}

function JoinGame({ invite, askPassword }: { invite: Invite | null; askPassword: boolean }) {
  // an invite link (#/play?code=ABC123) fills the room code in; a join link also the name (and asks for a password here)
  const [code, setCode] = useState(() => invite?.code ?? "");
  const [name, setName] = useState(() => invite?.name || ownName(activeProfile().name));
  const [password, setPassword] = useState("");
  const passwordField = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (askPassword) passwordField.current?.focus();
  }, [askPassword]);
  const join = async (spectate: boolean) => {
    try {
      const typed = code.trim().toUpperCase();
      // the decks a join link brought come along when it's still that table's code
      const handoff = !spectate && invite?.handoff && invite.code === typed ? invite.handoff : null;
      await joinTable({ code: typed, name: name.trim() || undefined, password: password || undefined, spectate, handoff });
    } catch (e) {
      toastError(e);
    }
  };
  const ready = code.trim().length >= 4;
  return (
    <section className="pg-door" aria-labelledby="pg-join-title">
      <h2 id="pg-join-title"><Icon name="resume" size={18} />Join with a code</h2>
      <form onSubmit={(e) => { e.preventDefault(); void join(false); }}>
        <label className="pg-code">
          <span>Room code</span>
          <input data-testid="join-code" value={code} maxLength={12} onChange={(e) => setCode(e.target.value)} placeholder="The code on the host's screen" autoComplete="off" spellCheck={false} />
        </label>
        <label className="pg-field pg-field-name">
          <span>Your name</span>
          <input data-testid="join-name" value={name} maxLength={40} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="pg-field pg-field-pass">
          <span>Password</span>
          <input ref={passwordField} type="password" value={password} maxLength={100} onChange={(e) => setPassword(e.target.value)} placeholder="If the host set one"
            autoComplete="off" data-testid="join-password" />
        </label>
        <div className="pg-door-acts">
          <button className="tt-btn brass" type="submit" disabled={!ready} data-testid="join-submit" aria-describedby={ready ? undefined : "pg-door-why"}>Join</button>
          <button className="tt-btn" type="button" disabled={!ready} onClick={() => void join(true)} data-testid="join-spectate" aria-describedby={ready ? undefined : "pg-door-why"}>Watch</button>
        </div>
        {!ready && <p className="pg-door-why" id="pg-door-why">Type the room code to join a seat or watch.</p>}
      </form>
    </section>
  );
}

/** A table being played right now: its commanders, how it's played, who's there. */
function TableTile({ game: g, host, onClosed }: { game: GameSummary; host: boolean | null; onClosed: () => void }) {
  const lan = g.mode === "lan";
  const lobby = g.phase === "lobby";
  // who's there, then how many seats are still open (a count, not a list of "Seat 3 (open)" cut off at the tile's edge)
  const seated = lan ? g.players.filter((p) => p.claimed) : g.players;
  const open = lan ? g.players.length - seated.length : 0;
  const who = [...seated.map((p) => `${p.name}${lan && !p.connected ? " (away)" : ""}`), ...(open ? [`${open} open seat${open === 1 ? "" : "s"}`] : [])];
  return (
    <li className="pg-tile">
      <TableMosaic seats={g.players.map((p) => ({ ...p, open: lan && !p.claimed }))} />
      <div className="pg-tile-main">
        <h3><span className="pg-tile-name">{g.name}</span>{lan && g.has_password && <Icon name="lock" size={14} label="Password" className="pg-lock" />}</h3>
        <p className="pg-meta">
          <span>{lan ? "LAN" : "Hot-seat"}</span>
          {isSandbox(g.format) && <span>Sandbox</span>}
          {lan && g.code && <span>Room <b className="pg-room">{g.code}</b></span>}
          <span>{lobby ? "In the lobby" : `Turn ${g.turn}`}</span>
        </p>
        <p className="pg-who">{who.join(", ")}</p>
      </div>
      {host && (
        <div className="pg-tile-acts">
          <button className="tt-btn pg-go" onClick={() => navigate(`/game/${g.id}`)}>Open</button>
          <button className="tt-btn ghost" onClick={async () => {
            if (!window.confirm(`Close “${g.name}”? It is autosaved first and can be loaded later.`)) return;
            await closeGame(g.id).catch(toastError);
            onClosed();
          }}>Close</button>
        </div>
      )}
      {host === false && <TileJoin game={g} />}
    </li>
  );
}

/**
 * A device that isn't the host joins a table right from its tile (POST /api/join, as the code form does): Join while a seat
 * is open, Watch any LAN table, or Open the seat this browser already holds. A table with a password asks for it here.
 */
function TileJoin({ game: g }: { game: GameSummary }) {
  const acts = tileActions(g, !!seatToken(g.id));
  const [asking, setAsking] = useState<"join" | "watch" | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  if (!acts.open && !acts.join && !acts.watch) return null;
  const go = async (spectate: boolean) => {
    if (g.has_password && !asking) return setAsking(spectate ? "watch" : "join");
    setBusy(true);
    try {
      await joinTable({ code: g.code!, name: ownName(activeProfile().name) || undefined, password: password || undefined, spectate });
    } catch (e) {
      toastError(e); // the server has the last word: a seat taken meanwhile, a wrong password
      setBusy(false);
    }
  };
  if (asking) {
    return (
      <form className="pg-tile-acts pg-tile-pass" onSubmit={(e) => { e.preventDefault(); void go(asking === "watch"); }}>
        <label>
          <span className="sr-only">Password for “{g.name}”</span>
          <input type="password" autoFocus value={password} maxLength={100} placeholder="Password" autoComplete="off"
            onChange={(e) => setPassword(e.target.value)} data-testid="tile-password" />
        </label>
        <button className="tt-btn pg-go" type="submit" disabled={busy || !password}>{asking === "watch" ? "Watch" : "Join"}</button>
        <button className="tt-btn ghost" type="button" onClick={() => { setAsking(null); setPassword(""); }}>Cancel</button>
      </form>
    );
  }
  return (
    <div className="pg-tile-acts">
      {acts.open && <button className="tt-btn pg-go" onClick={() => navigate(`/game/${g.id}`)} aria-label={`Open “${g.name}”`}>Open</button>}
      {acts.join && (
        <button className="tt-btn pg-go" disabled={busy} onClick={() => void go(false)} aria-label={`Join “${g.name}”`} data-testid="tile-join">Join</button>
      )}
      {acts.watch && <button className="tt-btn" disabled={busy} onClick={() => void go(true)} aria-label={`Watch “${g.name}”`}>Watch</button>}
    </div>
  );
}

/** A saved game: its commanders and life totals, when it was saved, and how to bring it back. */
function SaveTile({ save: s, onDeleted }: { save: SaveSummary; onDeleted: () => void }) {
  const open = (id: string) => navigate(`/game/${id}`);
  return (
    <li className="pg-tile list-row">
      <TableMosaic seats={s.players} />
      <div className="pg-tile-main">
        <h3 title={s.name}><span className="pg-tile-name">{s.autosave ? s.game_name || s.name : s.name}</span>{s.autosave && <span className="pg-tag">Autosave</span>}</h3>
        <p className="pg-meta">
          <span>{whenSaved(s.created_at)}</span>
          <span>Turn {s.turn}</span>
        </p>
        <p className="pg-who">{s.players.map((p) => `${p.name} ${p.life}`).join(", ")}</p>
      </div>
      <div className="pg-tile-acts">
        {/* a saved game comes back as a LAN night, like every new one: the host takes their seat, the pod rejoins with the code */}
        <button className="tt-btn pg-go" title="Load as a LAN night: you take your seat, the pod joins with the room code" onClick={async () => {
          try {
            const res = await loadSave(s.id);
            if (res.seat) rememberSeat(res.game.id, res.seat.token);
            toast(`LAN room ${res.game.code} ready`);
            open(res.game.id);
          } catch (e) {
            toastError(e);
          }
        }}>Load</button>
        <span className="pg-tile-more">
          <a className="tt-icon" href={packageUrl(s.id)} download title="Download a portable package (save + custom images + macros)" aria-label={`Download “${s.name}” as a package`}>
            <Icon name="download" size={16} />
          </a>
          <button className="tt-icon pg-delete" aria-label={`Delete save “${s.name}”`} title="Delete this save" onClick={async () => {
            if (!window.confirm(`Delete save “${s.name}”?`)) return;
            await deleteSave(s.id).catch(toastError);
            onDeleted();
          }}><Icon name="trash" size={16} /></button>
        </span>
      </div>
    </li>
  );
}

/** How the rest of the pod reaches this computer, in one line. */
function LanHint() {
  const [info, setInfo] = useState<{ addresses: string[]; port: number; reachable: boolean } | null>(null);
  useEffect(() => {
    lanInfo().then(setInfo, () => setInfo(null));
  }, []);
  if (!info) return null;
  return (
    <p className={`pg-lan ${info.reachable ? "" : "local-only"}`}>
      <Icon name="table" size={16} />
      {info.reachable ? (
        <span>
          The pod opens{" "}
          {info.addresses.map((a) => <code key={a}>http://{a}:{info.port}</code>).reduce<React.ReactNode[]>((acc, el, i) => (i ? [...acc, " or ", el] : [el]), [])}
          {" "}on their own computers and joins with the room code.
        </span>
      ) : (
        <span>
          Only this computer can reach Fyodor right now. To let the pod join a LAN night, restart it with <code>FYODOR_HOST=0.0.0.0 scripts/serve.sh</code>.
        </span>
      )}
    </p>
  );
}
