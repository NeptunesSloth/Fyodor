"""Construction-time native static-grant capture; no untap producer wiring."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, cast

from app.game.rules_state import ObjectRef

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics


class NativeStatic(Protocol):
    @property
    def source(self) -> str: ...

    @property
    def ability_index(self) -> int | None: ...

    @property
    def ability_path(self) -> tuple[int, ...]: ...

    @property
    def effect_key(self) -> tuple[int, int, int] | None: ...


@dataclass(frozen=True)
class GrantOrigin:
    recipient: ObjectRef
    source: ObjectRef | None
    source_card: str
    ability: int | None
    static_path: tuple[int, ...]
    ordinal: int
    expansion: tuple[int, ...]
    text: str


@dataclass
class Capture:
    state: GameState
    recipient: str
    grants: list[GrantOrigin] = field(default_factory=list)

    def record(self, state: GameState, card: CardInstance, st: NativeStatic, ordinal: int,
               expansion: tuple[int, ...], text: str) -> None:
        if state is not self.state or card.id != self.recipient or state.rules is None:
            return
        source = state.cards.get(st.source)
        authoritative = st.ability_index is not None and st.effect_key is None
        self.grants.append(GrantOrigin(
            recipient=ObjectRef(card=card.id, object_id=state.rules.object_id(card.id), zone=card.zone),
            source=(ObjectRef(card=source.id, object_id=state.rules.object_id(source.id), zone=source.zone)
                    if authoritative and source is not None else None), source_card=st.source,
            ability=st.ability_index if authoritative else None, static_path=st.ability_path, ordinal=ordinal, expansion=expansion, text=text))


def capture(state: GameState, card: CardInstance, info: CardInfo) -> tuple[Characteristics, tuple[GrantOrigin, ...]]:
    from app.rules import characteristics, layers

    if not getattr(layers, 'STATIC_GRANT_CAPTURE45', False):
        raise RuntimeError('The native grant-capture constructor is not installed')
    if state.cards.get(card.id) is not card or not card.zone.endswith(':battlefield') or layers._T.probe is not None:
        raise RuntimeError('Static-grant capture needs an actual battlefield object, not a prospective probe')
    if not layers.settled():
        raise RuntimeError('Static-grant capture needs a settled native derivation boundary')
    active = Capture(state, card.id)
    thread = cast(Any, layers._T)
    previous = (layers._T.depth, layers._T.memo, layers._T.borrow_graph, getattr(layers._T, 'grant_capture45', None))
    layers._T.depth = 0
    layers._T.memo = [state, info, None]  # Explicitly bypass read_pass derived cache; never clear it.
    thread.grant_capture45 = active
    try:
        result = layers.derive(state, card, characteristics.of(card, info), info)
        return result, tuple(active.grants)
    finally:
        layers._T.depth, layers._T.memo, layers._T.borrow_graph = previous[:3]
        thread.grant_capture45 = previous[3]
