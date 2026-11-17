from pathlib import Path

import pytest

from cardgame.battle import Battle, CardRejected, UnsupportedEffect
from cardgame.loader import load_cards, load_units
from cardgame.models import Card, Effect, Unit

DATA = Path(__file__).resolve().parents[1] / "data"
ENEMY = Unit(id="slime", name="Slime", max_hp=30, max_energy=1, deck=())


def sample_cards() -> dict[str, Card]:
    cards = {card.id: card for card in load_cards(DATA / "cards.json")}
    cards["big"] = Card(id="big", name="Big", cost=4, effects=(Effect("damage", 10),))
    return cards


def player_with(deck: tuple[str, ...]) -> Unit:
    base = load_units(DATA / "units.json")[0]
    return Unit(
        id=base.id,
        name=base.name,
        max_hp=base.max_hp,
        max_energy=base.max_energy,
        deck=deck,
    )


def make_battle(deck=("strike",), *, seed=1, hand_size=1, policy=None) -> Battle:
    return Battle(
        sample_cards(),
        player_with(deck),
        ENEMY,
        seed,
        hand_size=hand_size,
        enemy_policy=policy,
    )


# --- draw step ---------------------------------------------------------------


def test_same_seed_gives_same_shuffle_order():
    deck = ("strike", "strike", "defend", "battle_trance") * 3
    first = make_battle(deck, seed=5, hand_size=12)
    second = make_battle(deck, seed=5, hand_size=12)
    first.begin_turn()
    second.begin_turn()
    assert first.player.hand == second.player.hand


def test_different_seed_gives_different_shuffle_order():
    deck = ("strike", "strike", "defend", "battle_trance") * 3
    first = make_battle(deck, seed=1, hand_size=12)
    second = make_battle(deck, seed=2, hand_size=12)
    first.begin_turn()
    second.begin_turn()
    assert first.player.hand != second.player.hand


def test_draw_reshuffles_discard_when_draw_pile_is_empty():
    battle = make_battle(("defend", "battle_trance"), hand_size=2)
    battle.begin_turn()
    battle.end_turn()
    assert sorted(battle.player.hand) == ["battle_trance", "defend"]
    assert battle.player.draw_pile == []
    assert battle.player.discard == []


def test_draw_stops_when_no_cards_are_left_anywhere():
    battle = make_battle(("strike",), hand_size=3)
    battle.begin_turn()
    assert battle.player.hand == ["strike"]


# --- begin_turn step ---------------------------------------------------------


def test_begin_turn_refills_energy_and_draws_a_hand():
    battle = make_battle(("strike", "defend"), hand_size=2)
    battle.begin_turn()
    assert battle.turn == 1
    assert battle.player.energy == 3
    assert sorted(battle.player.hand) == ["defend", "strike"]


def test_begin_turn_clears_player_shield():
    battle = make_battle(("defend",), hand_size=1)
    battle.begin_turn()
    battle.play_card("defend")
    assert battle.player.shield == 5
    battle.end_turn()
    assert battle.player.shield == 0


# --- play step ---------------------------------------------------------------


def test_playing_a_card_spends_energy_and_damages_the_enemy():
    battle = make_battle(("strike",))
    battle.begin_turn()
    battle.play_card("strike")
    assert battle.player.energy == 2
    assert battle.enemy.hp == 30 - 6


def test_card_costing_more_than_energy_is_rejected_and_nothing_changes():
    battle = make_battle(("big",))
    battle.begin_turn()
    before = list(battle.log)
    with pytest.raises(CardRejected, match="costs 4"):
        battle.play_card("big")
    assert battle.player.energy == 3
    assert battle.player.hand == ["big"]
    assert battle.enemy.hp == 30
    assert battle.log == before


def test_card_costing_exactly_the_current_energy_is_accepted():
    battle = make_battle(("big",))
    battle.begin_turn()
    battle.player.energy = 4
    battle.play_card("big")
    assert battle.player.energy == 0
    assert battle.enemy.hp == 30 - 10


def test_card_not_in_hand_is_rejected():
    battle = make_battle(("strike",))
    battle.begin_turn()
    with pytest.raises(CardRejected, match="not in hand"):
        battle.play_card("defend")


def test_unknown_target_is_rejected():
    battle = make_battle(("strike",))
    battle.begin_turn()
    with pytest.raises(CardRejected, match="unknown target"):
        battle.play_card("strike", target="ghost")


def test_played_card_goes_to_discard():
    battle = make_battle(("strike",))
    battle.begin_turn()
    battle.play_card("strike")
    assert battle.player.hand == []
    assert battle.player.discard == ["strike"]


def test_status_card_with_no_status_table_is_rejected_before_anything_changes():
    cards = sample_cards()
    cards["venom"] = Card(
        id="venom",
        name="Venom",
        cost=0,
        effects=(Effect("damage", 2), Effect("apply_status", 1, status_id="poison")),
    )
    battle = Battle(cards, player_with(("venom",)), ENEMY, seed=1, hand_size=1)
    battle.begin_turn()
    with pytest.raises(UnsupportedEffect, match="unknown status 'poison'"):
        battle.play_card("venom")
    assert battle.enemy.hp == 30
    assert battle.player.hand == ["venom"]


# --- resolve step ------------------------------------------------------------


def test_damage_is_absorbed_by_shield_first():
    battle = make_battle(("strike",), policy=None)
    battle.begin_turn()
    battle.enemy.shield = 4
    battle.play_card("strike")
    assert battle.enemy.shield == 0
    assert battle.enemy.hp == 30 - 2


def test_shield_card_gives_the_player_shield():
    battle = make_battle(("defend",))
    battle.begin_turn()
    battle.play_card("defend")
    assert battle.player.shield == 5


def test_draw_card_draws_into_hand():
    battle = make_battle(("strike", "defend", "strike"), hand_size=0)
    battle.begin_turn()
    battle.player.hand.append("battle_trance")
    battle.play_card("battle_trance")
    assert len(battle.player.hand) == 2
    assert len(battle.player.draw_pile) == 1


# --- enemy act step ----------------------------------------------------------


def test_enemy_idles_when_there_is_no_policy():
    battle = make_battle(("strike",))
    battle.begin_turn()
    battle.enemy_act()
    assert battle.log[-1] == "enemy idles"


def test_enemy_policy_runs_during_the_enemy_phase():
    calls = []

    def policy(battle: Battle) -> None:
        calls.append(battle.turn)
        battle.resolve(battle.cards["strike"], battle.enemy, battle.player)

    battle = make_battle(("strike",), policy=policy)
    battle.begin_turn()
    battle.end_turn()
    assert calls == [1]
    assert battle.player.hp == 80 - 6


def test_shield_absorbs_enemy_hit_and_clears_at_next_turn():
    def policy(battle: Battle) -> None:
        battle.resolve(battle.cards["strike"], battle.enemy, battle.player)

    battle = make_battle(("defend",), policy=policy)
    battle.begin_turn()
    battle.play_card("defend")
    battle.end_turn()
    assert battle.player.hp == 80 - 1
    assert battle.player.shield == 0


# --- end turn / next turn step -----------------------------------------------


def test_end_turn_discards_hand_runs_enemy_then_starts_next_turn():
    battle = make_battle(("strike", "defend"), hand_size=2)
    battle.begin_turn()
    battle.end_turn()
    assert battle.turn == 2
    assert battle.player.energy == 3
    assert len(battle.player.hand) == 2
    assert battle.log.index("player ends turn") < battle.log.index("enemy idles")
    assert battle.log.index("enemy idles") < battle.log.index("turn 2 begins energy 3")


# --- reproducibility ---------------------------------------------------------


def play_all_affordable(battle: Battle) -> None:
    for card_id in list(battle.player.hand):
        if battle.cards[card_id].cost <= battle.player.energy:
            battle.play_card(card_id)


def play_script(seed: int) -> Battle:
    deck = ("strike", "strike", "defend", "battle_trance") * 2

    def policy(battle: Battle) -> None:
        battle.resolve(battle.cards["strike"], battle.enemy, battle.player)

    battle = make_battle(deck, seed=seed, hand_size=3, policy=policy)
    battle.begin_turn()
    play_all_affordable(battle)
    battle.end_turn()
    battle.begin_turn()
    play_all_affordable(battle)
    battle.end_turn()
    return battle


def test_same_seed_and_same_plays_give_identical_log():
    first = play_script(seed=7)
    second = play_script(seed=7)
    assert first.log == second.log
    assert first.log
    assert (first.player.hp, first.enemy.hp) == (second.player.hp, second.enemy.hp)
