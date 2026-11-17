"""Core data structures: Effect, Status, Card and Unit.

These are plain immutable records. Their values come from JSON data files
(see ``cardgame.loader``), never from engine code.
"""

from dataclasses import dataclass, field

EFFECT_KINDS = frozenset({"damage", "shield", "draw", "apply_status"})


@dataclass(frozen=True)
class Effect:
    kind: str
    amount: int
    status_id: str | None = None


@dataclass(frozen=True)
class Status:
    id: str
    name: str
    duration: int


@dataclass(frozen=True)
class Card:
    id: str
    name: str
    cost: int
    effects: tuple[Effect, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Unit:
    id: str
    name: str
    max_hp: int
    max_energy: int
    deck: tuple[str, ...] = field(default_factory=tuple)
