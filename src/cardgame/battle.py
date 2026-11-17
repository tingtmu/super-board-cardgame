"""Turn flow for one battle: draw, play, resolve, enemy act, next turn.

Pure logic. Card values come from data (``cardgame.loader``). The only
randomness is the deck shuffle, drawn from a seeded RNG, so the same seed and
the same plays always produce the same ``log``.

Targeting: ``damage`` hits the chosen target (default: the enemy). ``shield``
and ``draw`` apply to the player who played the card. Shield lasts until the
start of its owner's next turn.

Status effects (``apply_status``) arrive with milestone 3; until then a card
that uses one is rejected before anything changes.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from cardgame.models import Card, Unit
from cardgame.rng import make_rng


class CardRejected(Exception):
    """The player tried to play a card that cannot be played right now."""


class UnsupportedEffect(Exception):
    """A card uses an effect the engine does not model yet."""


@dataclass
class Combatant:
    unit: Unit
    hp: int
    max_energy: int
    energy: int = 0
    shield: int = 0
    draw_pile: list[str] = field(default_factory=list)
    hand: list[str] = field(default_factory=list)
    discard: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.unit.id


class Battle:
    def __init__(
        self,
        cards: dict[str, Card],
        player: Unit,
        enemy: Unit,
        seed: int,
        *,
        hand_size: int = 5,
        enemy_policy: Callable[["Battle"], None] | None = None,
    ) -> None:
        if player.id == enemy.id:
            raise ValueError(f"player and enemy share the id '{player.id}'")
        for unit in (player, enemy):
            for card_id in unit.deck:
                if card_id not in cards:
                    raise ValueError(f"unknown card '{card_id}' in deck of {unit.id}")
        self.cards = cards
        self.rng = make_rng(seed)
        self.hand_size = hand_size
        self.enemy_policy = enemy_policy
        self.player = _new_combatant(player)
        self.enemy = _new_combatant(enemy)
        self.units = {self.player.id: self.player, self.enemy.id: self.enemy}
        self.turn = 0
        self.log: list[str] = []
        for who in (self.player, self.enemy):
            self.rng.shuffle(who.draw_pile)

    def begin_turn(self) -> None:
        """Start a player turn: new turn number, full energy, clear shield, draw a hand."""
        self.turn += 1
        self.player.energy = self.player.max_energy
        self.player.shield = 0
        self.log.append(f"turn {self.turn} begins energy {self.player.energy}")
        self.draw(self.player, self.hand_size)
        self.log.append(f"hand {self.player.hand}")

    def draw(self, who: Combatant, count: int) -> None:
        """Move ``count`` cards to hand, reshuffling the discard when the draw pile runs out."""
        for _ in range(count):
            if not who.draw_pile:
                if not who.discard:
                    break
                who.draw_pile, who.discard = who.discard, []
                self.rng.shuffle(who.draw_pile)
                self.log.append(f"{who.id} reshuffles discard into draw pile")
            who.hand.append(who.draw_pile.pop())

    def play_card(self, card_id: str, target: str | None = None) -> None:
        """Play a card from hand: check it, spend energy, resolve it, discard it.

        A rejected play raises ``CardRejected`` and changes nothing.
        """
        player = self.player
        if card_id not in player.hand:
            raise CardRejected(f"'{card_id}' is not in hand")
        card = self.cards[card_id]
        if card.cost > player.energy:
            raise CardRejected(
                f"'{card_id}' costs {card.cost}, energy is {player.energy}"
            )
        target_id = self.enemy.id if target is None else target
        if target_id not in self.units:
            raise CardRejected(f"unknown target '{target_id}'")
        _check_supported(card)

        player.hand.remove(card_id)
        player.energy -= card.cost
        self.log.append(f"player plays {card_id} (cost {card.cost}) -> {target_id}")
        self.resolve(card, caster=player, target=self.units[target_id])
        player.discard.append(card_id)

    def resolve(self, card: Card, caster: Combatant, target: Combatant) -> None:
        """Apply a card's effects in order. Also used by enemy policies."""
        _check_supported(card)
        for effect in card.effects:
            if effect.kind == "damage":
                self._damage(target, effect.amount)
            elif effect.kind == "shield":
                caster.shield += effect.amount
                self.log.append(f"{caster.id} gains {effect.amount} shield")
            elif effect.kind == "draw":
                self.draw(caster, effect.amount)
                self.log.append(f"{caster.id} draws {effect.amount}")

    def enemy_act(self) -> None:
        """Enemy phase. Enemy shield clears here; the policy (if any) then acts."""
        self.enemy.shield = 0
        if self.enemy_policy is None:
            self.log.append("enemy idles")
            return
        self.enemy_policy(self)

    def end_turn(self) -> None:
        """Discard the hand, run the enemy phase, then start the next player turn."""
        self.player.discard.extend(self.player.hand)
        self.player.hand.clear()
        self.log.append("player ends turn")
        self.enemy_act()
        self.begin_turn()

    def _damage(self, target: Combatant, amount: int) -> None:
        absorbed = min(target.shield, amount)
        target.shield -= absorbed
        taken = amount - absorbed
        target.hp = max(0, target.hp - taken)
        self.log.append(
            f"{target.id} takes {taken} damage ({absorbed} blocked) hp {target.hp}/{target.unit.max_hp}"
        )


def _new_combatant(unit: Unit) -> Combatant:
    return Combatant(
        unit=unit,
        hp=unit.max_hp,
        max_energy=unit.max_energy,
        draw_pile=list(unit.deck),
    )


def _check_supported(card: Card) -> None:
    for effect in card.effects:
        if effect.kind not in ("damage", "shield", "draw"):
            raise UnsupportedEffect(
                f"card '{card.id}' uses '{effect.kind}', which is not modelled yet"
            )
