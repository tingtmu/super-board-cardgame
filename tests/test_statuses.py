import json
from pathlib import Path

import pytest

from cardgame.battle import Battle, CardRejected, UnsupportedEffect
from cardgame.loader import load_cards, load_statuses, load_units
from cardgame.models import Card, Effect, Unit

DATA = Path(__file__).resolve().parents[1] / "data"
ENEMY = Unit(id="slime", name="Slime", max_hp=30, max_energy=1, deck=())


def statuses() -> dict:
    return {status.id: status for status in load_statuses(DATA / "statuses.json")}


def cards_with(*extra: Card) -> dict[str, Card]:
    cards = {card.id: card for card in load_cards(DATA / "cards.json")}
    for card in extra:
        cards[card.id] = card
    return cards


def apply_card(card_id: str, status_id: str, stacks: int, *, cost: int = 0) -> Card:
    return Card(
        id=card_id,
        name=card_id.title(),
        cost=cost,
        effects=(Effect("apply_status", stacks, status_id=status_id),),
    )


def battle_with(deck: tuple[str, ...], *extra: Card, hand_size: int = 5) -> Battle:
    base = load_units(DATA / "units.json")[0]
    player = Unit(
        id=base.id,
        name=base.name,
        max_hp=base.max_hp,
        max_energy=base.max_energy,
        deck=deck,
    )
    return Battle(
        cards_with(*extra),
        player,
        ENEMY,
        seed=1,
        hand_size=hand_size,
        statuses=statuses(),
    )


POISON_1 = apply_card("venom", "poison", 1)
WEAK_1 = apply_card("hex", "weak", 1)


# --- applying a status ---------------------------------------------------------


def test_applying_a_status_puts_stacks_and_duration_on_the_target():
    battle = battle_with(("venom",), POISON_1)
    battle.begin_turn()
    battle.play_card("venom")
    active = battle.enemy.statuses["poison"]
    assert (active.stacks, active.turns_left) == (1, 3)


def test_applying_a_status_twice_adds_stacks_and_refreshes_duration():
    battle = battle_with(("venom", "venom"), POISON_1, hand_size=2)
    battle.begin_turn()
    battle.play_card("venom")
    battle.enemy.statuses["poison"].turns_left = 1
    battle.play_card("venom")
    active = battle.enemy.statuses["poison"]
    assert (active.stacks, active.turns_left) == (2, 3)


def test_status_card_that_names_an_unknown_status_is_rejected_before_anything_changes():
    base = load_units(DATA / "units.json")[0]
    player = Unit(
        id=base.id,
        name=base.name,
        max_hp=base.max_hp,
        max_energy=base.max_energy,
        deck=("venom",),
    )
    battle = Battle(cards_with(POISON_1), player, ENEMY, seed=1, hand_size=1)
    battle.begin_turn()
    with pytest.raises(UnsupportedEffect, match="unknown status 'poison'"):
        battle.play_card("venom")
    assert battle.enemy.statuses == {}
    assert battle.player.hand == ["venom"]


def test_status_card_can_target_the_player():
    battle = battle_with(("hex", "strike"), WEAK_1, hand_size=2)
    battle.begin_turn()
    battle.play_card("hex", target="player")
    assert "weak" in battle.player.statuses
    assert battle.enemy.statuses == {}


# --- poison ----------------------------------------------------------------------


def test_poison_deals_its_stacks_each_turn_and_expires_after_its_duration():
    battle = battle_with(("venom",), POISON_1)
    battle.begin_turn()
    battle.play_card("venom")
    hp = [battle.enemy.hp]
    for _ in range(3):
        battle.end_turn()
        hp.append(battle.enemy.hp)
    assert hp == [30, 29, 28, 27]
    assert "poison" not in battle.enemy.statuses


def test_poison_stacks_multiply_the_damage_each_tick():
    battle = battle_with(("venom", "venom"), POISON_1, hand_size=2)
    battle.begin_turn()
    battle.play_card("venom")
    battle.play_card("venom")
    battle.end_turn()
    assert battle.enemy.hp == 30 - 2


def test_poison_tick_is_absorbed_by_shield_first():
    battle = battle_with(("venom",), POISON_1)
    battle.begin_turn()
    battle.play_card("venom", target="player")
    battle.player.shield = 1
    battle.end_turn()
    assert battle.player.hp == 80
    assert battle.player.shield == 0


# --- weak ------------------------------------------------------------------------


def test_weak_reduces_outgoing_damage_by_a_quarter():
    battle = battle_with(("hex", "strike"), WEAK_1, hand_size=2)
    battle.begin_turn()
    battle.play_card("hex", target="player")
    battle.play_card("strike")
    assert battle.enemy.hp == 30 - 4


def test_weak_does_not_reduce_damage_taken():
    battle = battle_with(("hex", "strike"), WEAK_1, hand_size=2)
    battle.begin_turn()
    battle.enemy.statuses["weak"] = _weak(battle, turns=2)
    battle.play_card("strike")
    assert battle.enemy.hp == 30 - 6


def _weak(battle: Battle, turns: int):
    from cardgame.battle import ActiveStatus

    return ActiveStatus(stacks=1, turns_left=turns)


def test_weak_applies_to_enemy_policy_attacks():
    def policy(battle: Battle) -> None:
        battle.resolve(battle.cards["strike"], battle.enemy, battle.player)

    battle = battle_with(("hex",), WEAK_1)
    battle.enemy_policy = policy
    battle.begin_turn()
    battle.play_card("hex", target="player")
    battle.enemy.statuses["weak"] = _weak(battle, turns=2)
    battle.end_turn()
    assert battle.player.hp == 80 - 4


def test_weak_expires_after_its_duration():
    battle = battle_with(("hex",), WEAK_1)
    battle.begin_turn()
    battle.play_card("hex", target="player")
    battle.end_turn()
    assert battle.player.statuses["weak"].turns_left == 1
    battle.end_turn()
    assert "weak" not in battle.player.statuses


# --- status step ordering -------------------------------------------------------


def test_status_step_runs_after_enemy_phase_and_before_next_turn():
    battle = battle_with(("venom",), POISON_1)
    battle.begin_turn()
    battle.play_card("venom")
    battle.end_turn()
    log = battle.log
    assert log.index("player ends turn") < log.index("enemy idles")
    assert log.index("enemy idles") < log.index("slime takes 1 damage (0 blocked) hp 29/30")
    assert log.index("slime takes 1 damage (0 blocked) hp 29/30") < log.index("turn 2 begins energy 3")


# --- data-only status card -----------------------------------------------------


def test_new_status_card_works_through_a_data_file_change_only(tmp_path):
    path = tmp_path / "cards.json"
    path.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "id": "viper_bite",
                        "name": "Viper Bite",
                        "cost": 0,
                        "effects": [{"kind": "apply_status", "amount": 2, "status": "poison"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (viper,) = load_cards(path)
    battle = battle_with(("viper_bite",), viper)
    battle.begin_turn()
    battle.play_card("viper_bite")
    battle.end_turn()
    assert battle.enemy.hp == 28
    assert battle.enemy.statuses["poison"].stacks == 2
