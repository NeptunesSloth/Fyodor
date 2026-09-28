import { memo, useEffect, useRef } from "react";
import { CardFace } from "../cards/CardFace";
import { ManaText, OracleText } from "../cards/ManaText";
import { openMenu } from "../components/ContextMenu";
import { useCard } from "../state/cardCache";
import { playerName, useCardView, useGame } from "../state/gameStore";
import { isVisible, PHASE_LABEL, type LogEntryView, type LogPartView } from "../types/game";
import { send } from "./actions";
import { cardMenu } from "./cardMenu";
import { beginPointerDrag } from "./dnd";
import { GameCardFace } from "./GameCardFace";
import { moveCards } from "./actions";
import { splitZone } from "../types/game";

/** Large preview of whatever card is hovered (board, hand, log, browser). */
export function Inspector() {
  const hover = useGame((s) => s.hover);
  const isPrint = hover?.startsWith("print:");
  const card = useCardView(!isPrint && hover ? hover : "");
  const printId = isPrint ? hover!.slice(6) : card && isVisible(card) ? card.card_id : null;
  const data = useCard(printId);
  if (!hover) {
    return (
      <div className="inspector empty">
        <span className="hint">Hover a card to inspect it</span>
      </div>
    );
  }
  const visibleCard = card && isVisible(card) ? card : null;
  const face = visibleCard?.face ?? 0;
  const faceData = data && data.faces.length ? data.faces[Math.min(face, data.faces.length - 1)] : null;
  return (
    <div className="inspector">
      <div className="insp-image">
        {card && (!visibleCard || (visibleCard.face_down && !data)) ? (
          <GameCardFace card={card} peek />
        ) : visibleCard && !visibleCard.card_id ? (
          <GameCardFace card={visibleCard} peek />
        ) : (
          <CardFace card={data} face={face} size="normal" />
        )}
      </div>
      {data && (
        <div className="insp-text">
          <div className="insp-name">
            {faceData?.name ?? data.name} <ManaText text={faceData?.mana_cost ?? data.mana_cost} />
          </div>
          <div className="hint">{faceData?.type_line ?? data.type_line}</div>
          <div className="insp-oracle"><OracleText text={faceData?.oracle_text ?? data.oracle_text} /></div>
        </div>
      )}
      {visibleCard?.copy_of && <div className="insp-note">Copy of {visibleCard.copy_of.source_name}{visibleCard.copy_of.modifications ? ` — ${visibleCard.copy_of.modifications}` : ""}</div>}
      {visibleCard?.note && <div className="insp-note">✎ {visibleCard.note}</div>}
      {visibleCard?.face_down && <div className="insp-note">Face down — only you (and anyone who saw it) know this card.</div>}
      {card?.counters && Object.keys(card.counters).length > 0 && (
        <div className="insp-note">{Object.entries(card.counters).map(([k, v]) => `${k}: ${v}`).join(" · ")}</div>
      )}
    </div>
  );
}

export function StackPanel({ me }: { me: string }) {
  const stack = useGame((s) => s.view?.stack ?? []);
  const openDialog = useGame((s) => s.openDialog);
  return (
    <div className="stack-panel" data-drop="stack">
      <div className="panel-head">
        <span>Stack {stack.length > 0 && <span className="hint">({stack.length})</span>}</span>
        <span className="spacer" />
        <button className="btn small" onClick={() => openDialog("ability", null)} title="Put an ability on the stack">+ Ability</button>
        <button className="btn small primary" disabled={!stack.length} onClick={() => void send({ type: "resolve_top" })}>Resolve top</button>
      </div>
      {stack.length === 0 && <div className="stack-empty hint">Drag spells here to cast them</div>}
      <div className="stack-list">
        {[...stack].reverse().map((id, i) => (
          <StackItem key={id} id={id} top={i === 0} me={me} />
        ))}
      </div>
    </div>
  );
}

const StackItem = memo(function StackItem({ id, top, me }: { id: string; top: boolean; me: string }) {
  const card = useCardView(id);
  const view = useGame((s) => s.view);
  if (!card || !view) return null;
  const visible = isVisible(card);
  return (
    <div
      className={`stack-item ${top ? "top" : ""}`}
      data-card-id={id}
      onPointerEnter={() => useGame.getState().setHover(id)}
      onPointerLeave={() => useGame.getState().setHover(null)}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        beginPointerDrag(e, {
          ids: [id],
          from: "stack",
          width: 90,
          onDrop: (t) => {
            if (!t) return;
            const { zone, player } = splitZone(t.zone);
            void moveCards([id], zone, { player, x: t.x, y: t.y, position: t.position, index: t.index });
          },
        });
      }}
      onContextMenu={(e) => {
        e.preventDefault();
        const { title, items } = cardMenu(card, view, me);
        openMenu(e, items, title);
      }}
    >
      <div className="stack-thumb"><GameCardFace card={card} size="small" /></div>
      <div className="stack-info">
        <div className="stack-name">{visible ? (card.ability ? card.ability.source_name ?? "Ability" : card.name) : "Face-down spell"}</div>
        <div className="hint">
          {playerName(view, card.controller)}
          {visible && card.ability ? ` · ${card.ability.text}` : ""}
          {visible && card.copy_of ? " · copy" : ""}
        </div>
        {card.stack_info && (
          <div className="stack-notes">
            {card.stack_info.x != null && <b className="stack-x">X = {card.stack_info.x}</b>}
            {card.stack_info.tags.map((t) => <span key={t} className="stack-tag">{t}</span>)}
            {card.stack_info.modes.length > 0 && <div className="stack-modes">{card.stack_info.modes.map((m) => <div key={m}>✓ {m}</div>)}</div>}
          </div>
        )}
      </div>
    </div>
  );
});

function Part({ part }: { part: LogPartView }) {
  const setHover = useGame((s) => s.setHover);
  if ("t" in part) return <>{part.t}</>;
  if ("card" in part) {
    return (
      <span className="log-card" onPointerEnter={() => part.card.card_id && setHover(`print:${part.card.card_id}`)} onPointerLeave={() => setHover(null)}>
        {part.card.name}
      </span>
    );
  }
  const names = part.group;
  const hidden = part.hidden;
  const pieces: React.ReactNode[] = names.map((n, i) => (
    <span key={i} className="log-card" onPointerEnter={() => n.card.card_id && setHover(`print:${n.card.card_id}`)} onPointerLeave={() => setHover(null)}>
      {n.card.name}
    </span>
  ));
  if (hidden) pieces.push(<span key="h" className="log-hidden">{hidden === 1 ? (names.length ? "1 other card" : "a card") : `${hidden} ${names.length ? "other " : ""}cards`}</span>);
  return (
    <>
      {pieces.map((p, i) => (
        <span key={i}>
          {i > 0 && (i === pieces.length - 1 ? " and " : ", ")}
          {p}
        </span>
      ))}
    </>
  );
}

const LogLine = memo(function LogLine({ entry }: { entry: LogEntryView }) {
  const time = new Date(entry.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return (
    <div className={`log-line log-${entry.kind}`} title={`Turn ${entry.turn} · ${PHASE_LABEL[entry.phase]} · ${time}`}>
      {entry.parts.map((p, i) => (
        <Part key={i} part={p} />
      ))}
    </div>
  );
});

export function LogPanel() {
  const log = useGame((s) => s.view?.log ?? []);
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [log]);
  return (
    <div className="log-panel">
      <div className="panel-head">Game log</div>
      <div
        className="log-scroll"
        ref={ref}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
      >
        {log.map((e, i) => {
          const prev = log[i - 1];
          return (
            <div key={`${e.seq}-${e.ts}-${i}`}>
              {(!prev || prev.turn !== e.turn) && <div className="log-turn">Turn {e.turn}</div>}
              <LogLine entry={e} />
            </div>
          );
        })}
      </div>
      <ChatBox />
    </div>
  );
}

function ChatBox() {
  return (
    <form
      className="chat"
      onSubmit={(e) => {
        e.preventDefault();
        const input = e.currentTarget.elements.namedItem("msg") as HTMLInputElement;
        const text = input.value.trim();
        if (text) void send({ type: "chat", text });
        input.value = "";
      }}
    >
      <input name="msg" placeholder="Say something…" maxLength={500} autoComplete="off" />
    </form>
  );
}
