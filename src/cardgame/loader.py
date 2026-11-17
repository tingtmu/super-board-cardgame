"""Load cards, statuses and units from JSON data files.

Every problem in a data file raises ``DataError`` naming the file and the
field at fault, so a bad card is reported clearly instead of crashing later.
"""

import json
from pathlib import Path
from typing import Any

from cardgame.models import EFFECT_KINDS, Card, Effect, Status, Unit


class DataError(ValueError):
    """Raised when a JSON data file is malformed."""


def _read_json(path: Path) -> Any:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise DataError(f"{path}: cannot read file: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataError(f"{path}: invalid JSON: {exc}") from exc


def _require(path: Path, where: str, obj: dict, key: str, types: type | tuple) -> Any:
    if key not in obj:
        raise DataError(f"{path}: {where}: missing field '{key}'")
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, types):
        raise DataError(f"{path}: {where}: field '{key}' has wrong type")
    return value


def _require_list(path: Path, obj: Any, key: str) -> list:
    if not isinstance(obj, dict) or key not in obj:
        raise DataError(f"{path}: top level must be an object with a '{key}' list")
    if not isinstance(obj[key], list):
        raise DataError(f"{path}: '{key}' must be a list")
    return obj[key]


def _parse_effect(path: Path, where: str, raw: Any) -> Effect:
    if not isinstance(raw, dict):
        raise DataError(f"{path}: {where}: effect must be an object")
    kind = _require(path, where, raw, "kind", str)
    if kind not in EFFECT_KINDS:
        raise DataError(
            f"{path}: {where}: unknown effect kind '{kind}' "
            f"(expected one of {sorted(EFFECT_KINDS)})"
        )
    amount = _require(path, where, raw, "amount", int)
    if amount < 0:
        raise DataError(f"{path}: {where}: 'amount' must not be negative")
    status_id = None
    if kind == "apply_status":
        status_id = _require(path, where, raw, "status", str)
    return Effect(kind=kind, amount=amount, status_id=status_id)


def load_cards(path: Path) -> list[Card]:
    """Load ``{"cards": [...]}`` from ``path``."""
    data = _read_json(path)
    cards = []
    for index, raw in enumerate(_require_list(path, data, "cards")):
        if not isinstance(raw, dict):
            raise DataError(f"{path}: cards[{index}] must be an object")
        card_id = _require(path, f"cards[{index}]", raw, "id", str)
        where = f"card '{card_id}'"
        effects_raw = _require(path, where, raw, "effects", list)
        cards.append(
            Card(
                id=card_id,
                name=_require(path, where, raw, "name", str),
                cost=_require(path, where, raw, "cost", int),
                effects=tuple(
                    _parse_effect(path, where, effect) for effect in effects_raw
                ),
            )
        )
    return cards


def load_statuses(path: Path) -> list[Status]:
    """Load ``{"statuses": [...]}`` from ``path``."""
    data = _read_json(path)
    statuses = []
    for index, raw in enumerate(_require_list(path, data, "statuses")):
        if not isinstance(raw, dict):
            raise DataError(f"{path}: statuses[{index}] must be an object")
        status_id = _require(path, f"statuses[{index}]", raw, "id", str)
        where = f"status '{status_id}'"
        statuses.append(
            Status(
                id=status_id,
                name=_require(path, where, raw, "name", str),
                duration=_require(path, where, raw, "duration", int),
            )
        )
    return statuses


def load_units(path: Path) -> list[Unit]:
    """Load ``{"units": [...]}`` from ``path``."""
    data = _read_json(path)
    units = []
    for index, raw in enumerate(_require_list(path, data, "units")):
        if not isinstance(raw, dict):
            raise DataError(f"{path}: units[{index}] must be an object")
        unit_id = _require(path, f"units[{index}]", raw, "id", str)
        where = f"unit '{unit_id}'"
        deck_raw = _require(path, where, raw, "deck", list)
        if not all(isinstance(card_id, str) for card_id in deck_raw):
            raise DataError(f"{path}: {where}: 'deck' must be a list of card ids")
        units.append(
            Unit(
                id=unit_id,
                name=_require(path, where, raw, "name", str),
                max_hp=_require(path, where, raw, "max_hp", int),
                max_energy=_require(path, where, raw, "max_energy", int),
                deck=tuple(deck_raw),
            )
        )
    return units
