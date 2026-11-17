import json
from pathlib import Path

import pytest

from cardgame.battle import Battle, UnsupportedEffect
from cardgame.loader import DataError, load_cards, load_statuses, load_units
from cardgame.models import Card, Effect, Move, Unit

DATA = Path(__file__).resolve().parents[1] / "data"


def data_cards() -> dict[str, Card]:
    cards = {card.id: card for card in load_cards(DATA / "cards.json")}
    return cards


def unit_by_id(units: list[Unit], unit_id: str) -> Unit:
    return next(unit for unit in units if unit.id == unit_id)


def enemy_with_moves(*moves: Move) -> Unit:
    return Unit(
        id="raider",
        name="Raider",
        max_hp=40,
        max_energy=1,
        deck=(),
        moves=tuple(moves),
    )


PLAYER = Unit(id="player", name="Player", max_hp=80, max_energy=3,
              deck=("strike", "defend", "battle_trance"))


def battle_with(enemy: Unit, seed: int = 1, **kwargs) -> Battle:
    return Battle(data_cards(), PLAYER, enemy, seed, hand_size=0, **kwargs)


# --- the enemy picks its move from its data -----------------------------------


def test_enemy_plays_a_move_from_its_data_each_turn():
    battle = battle_with(enemy_with_moves(Move("strike", 1)))
    battle.begin_turn()
    battle.end_turn()
    assert "raider picks strike" in battle.log
    assert battle.player.hp == 80 - 6


def test_enemy_move_is_chosen_only_from_its_listed_moves():
    battle = battle_with(
        enemy_with_moves(Move("strike", 1), Move("defend", 1)), seed=3
    )
    battle.begin_turn()
    for _ in range(20):
        battle.end_turn()
    picks = [line.split()[-1] for line in battle.log if line.startswith("raider picks")]
    assert len(picks) == 20
    assert set(picks) <= {"strike", "defend"}


def test_enemy_with_no_moves_still_idles():
    battle = battle_with(enemy_with_moves())
    battle.begin_turn()
    battle.enemy_act()
    assert battle.log[-1] == "enemy idles"


def test_explicit_policy_overrides_the_enemy_moves():
    calls = []

    def policy(battle: Battle) -> None:
        calls.append(battle.turn)

    battle = battle_with(enemy_with_moves(Move("strike", 1)), enemy_policy=policy)
    battle.begin_turn()
    battle.end_turn()
    assert calls == [1]
    assert battle.player.hp == 80


# --- reproducible with a fixed seed -----------------------------------------


def pick_sequence(seed: int) -> list[str]:
    battle = battle_with(
        enemy_with_moves(Move("strike", 2), Move("defend", 1), Move("battle_trance", 1)),
        seed=seed,
    )
    battle.begin_turn()
    for _ in range(12):
        battle.end_turn()
    return [line.split()[-1] for line in battle.log if line.startswith("raider picks")]


def test_same_seed_gives_the_same_enemy_move_sequence():
    assert pick_sequence(seed=11) == pick_sequence(seed=11)


def test_different_seed_can_give_a_different_enemy_move_sequence():
    assert pick_sequence(seed=11) != pick_sequence(seed=12)


# --- validation at setup -----------------------------------------------------


def test_enemy_move_naming_an_unknown_card_is_rejected():
    enemy = enemy_with_moves(Move("nope", 1))
    with pytest.raises(ValueError, match="unknown card 'nope' in moves of raider"):
        battle_with(enemy)


def test_enemy_move_with_an_unmodelled_effect_is_rejected():
    cards = data_cards()
    cards["heal"] = Card(id="heal", name="Heal", cost=0, effects=(Effect("heal", 3),))
    enemy = enemy_with_moves(Move("heal", 1))
    with pytest.raises(UnsupportedEffect, match="'heal', which is not modelled yet"):
        Battle(cards, PLAYER, enemy, seed=1, hand_size=0)


# --- a full seeded battle reaches a winner -----------------------------------


def play_all_affordable(battle: Battle) -> None:
    for card_id in list(battle.player.hand):
        if battle.cards[card_id].cost <= battle.player.energy:
            battle.play_card(card_id)


def run_to_end(seed: int) -> Battle:
    units = load_units(DATA / "units.json")
    battle = Battle(
        data_cards(),
        unit_by_id(units, "player"),
        unit_by_id(units, "slime"),
        seed,
        hand_size=3,
        statuses={s.id: s for s in load_statuses(DATA / "statuses.json")},
    )
    battle.begin_turn()
    while battle.winner is None and battle.turn < 100:
        play_all_affordable(battle)
        if battle.winner is not None:
            break
        battle.end_turn()
    return battle


def test_full_seeded_battle_runs_to_a_winner():
    battle = run_to_end(seed=7)
    assert battle.winner is not None
    assert battle.winner == "player"
    assert battle.enemy.hp == 0
    assert battle.turn < 100


def test_full_seeded_battle_is_reproducible():
    first = run_to_end(seed=7)
    second = run_to_end(seed=7)
    assert first.log == second.log
    assert first.winner == second.winner


# --- a new enemy is a data-file change only -----------------------------------


def test_new_enemy_defined_only_in_data_plays_its_moves(tmp_path: Path):
    units_file = tmp_path / "units.json"
    units_file.write_text(
        json.dumps(
            {
                "units": [
                    {
                        "id": "bat",
                        "name": "Bat",
                        "max_hp": 12,
                        "max_energy": 1,
                        "deck": [],
                        "moves": [{"card": "strike", "weight": 1}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    bat = load_units(units_file)[0]
    battle = battle_with(bat)
    battle.begin_turn()
    battle.end_turn()
    assert battle.player.hp == 80 - 6


# --- winner -------------------------------------------------------------------


def test_winner_is_none_while_both_units_are_alive():
    battle = battle_with(enemy_with_moves())
    assert battle.winner is None


def test_winner_is_player_when_enemy_hp_is_zero():
    battle = battle_with(enemy_with_moves())
    battle.enemy.hp = 0
    assert battle.winner == "player"


def test_winner_is_enemy_when_player_hp_is_zero():
    battle = battle_with(enemy_with_moves())
    battle.player.hp = 0
    assert battle.winner == "raider"


# --- loader -------------------------------------------------------------------


def write_units(tmp_path: Path, unit: dict) -> Path:
    path = tmp_path / "units.json"
    path.write_text(json.dumps({"units": [unit]}), encoding="utf-8")
    return path


BASE_UNIT = {"id": "bat", "name": "Bat", "max_hp": 12, "max_energy": 1, "deck": []}


def test_loader_reads_moves_with_card_and_weight(tmp_path: Path):
    unit = dict(BASE_UNIT, moves=[{"card": "strike", "weight": 3}])
    loaded = load_units(write_units(tmp_path, unit))[0]
    assert loaded.moves == (Move("strike", 3),)


def test_loader_defaults_moves_to_empty(tmp_path: Path):
    loaded = load_units(write_units(tmp_path, dict(BASE_UNIT)))[0]
    assert loaded.moves == ()


def test_loader_rejects_a_move_without_a_card(tmp_path: Path):
    unit = dict(BASE_UNIT, moves=[{"weight": 1}])
    with pytest.raises(DataError, match="missing field 'card'"):
        load_units(write_units(tmp_path, unit))


def test_loader_rejects_a_zero_weight(tmp_path: Path):
    unit = dict(BASE_UNIT, moves=[{"card": "strike", "weight": 0}])
    with pytest.raises(DataError, match="'weight' must be positive"):
        load_units(write_units(tmp_path, unit))


def test_loader_rejects_moves_that_are_not_a_list(tmp_path: Path):
    unit = dict(BASE_UNIT, moves="strike")
    with pytest.raises(DataError, match="'moves' must be a list"):
        load_units(write_units(tmp_path, unit))
