import json
from pathlib import Path

import pytest

from cardgame.loader import DataError, load_cards, load_statuses, load_units
from cardgame.models import Card, Effect, Status, Unit

DATA = Path(__file__).resolve().parents[1] / "data"


def write(tmp_path: Path, name: str, payload) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_sample_cards_load_as_data():
    cards = {card.id: card for card in load_cards(DATA / "cards.json")}
    assert set(cards) == {"strike", "defend", "battle_trance"}


def test_strike_is_a_damage_card():
    cards = {card.id: card for card in load_cards(DATA / "cards.json")}
    assert cards["strike"] == Card(
        id="strike", name="Strike", cost=1, effects=(Effect(kind="damage", amount=6),)
    )


def test_defend_is_a_shield_card():
    cards = {card.id: card for card in load_cards(DATA / "cards.json")}
    assert cards["defend"].effects == (Effect(kind="shield", amount=5),)


def test_battle_trance_is_a_draw_card():
    cards = {card.id: card for card in load_cards(DATA / "cards.json")}
    assert cards["battle_trance"].effects == (Effect(kind="draw", amount=2),)


def test_statuses_and_units_load_from_json():
    statuses = load_statuses(DATA / "statuses.json")
    units = load_units(DATA / "units.json")
    assert Status(id="poison", name="Poison", duration=3) in statuses
    assert units == [
        Unit(
            id="player",
            name="Player",
            max_hp=80,
            max_energy=3,
            deck=("strike", "strike", "defend", "battle_trance"),
        )
    ]


def test_apply_status_effect_carries_status_id(tmp_path):
    path = write(
        tmp_path,
        "cards.json",
        {
            "cards": [
                {
                    "id": "venom",
                    "name": "Venom",
                    "cost": 1,
                    "effects": [{"kind": "apply_status", "amount": 2, "status": "poison"}],
                }
            ]
        },
    )
    (card,) = load_cards(path)
    assert card.effects == (Effect(kind="apply_status", amount=2, status_id="poison"),)


def test_invalid_json_raises_clear_error(tmp_path):
    path = tmp_path / "cards.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(DataError, match="invalid JSON"):
        load_cards(path)


def test_missing_field_names_the_card_and_field(tmp_path):
    path = write(tmp_path, "cards.json", {"cards": [{"id": "x", "name": "X", "effects": []}]})
    with pytest.raises(DataError, match="card 'x'.*missing field 'cost'"):
        load_cards(path)


def test_unknown_effect_kind_is_rejected(tmp_path):
    path = write(
        tmp_path,
        "cards.json",
        {"cards": [{"id": "x", "name": "X", "cost": 0, "effects": [{"kind": "explode", "amount": 1}]}]},
    )
    with pytest.raises(DataError, match="unknown effect kind 'explode'"):
        load_cards(path)


def test_wrong_type_is_rejected(tmp_path):
    path = write(
        tmp_path,
        "units.json",
        {"units": [{"id": "e", "name": "Enemy", "max_hp": "lots", "max_energy": 1, "deck": []}]},
    )
    with pytest.raises(DataError, match="field 'max_hp' has wrong type"):
        load_units(path)


def test_missing_top_level_list_is_rejected(tmp_path):
    path = write(tmp_path, "statuses.json", {"wrong": []})
    with pytest.raises(DataError, match="'statuses' list"):
        load_statuses(path)


def test_missing_file_is_a_data_error(tmp_path):
    with pytest.raises(DataError, match="cannot read file"):
        load_cards(tmp_path / "nope.json")
