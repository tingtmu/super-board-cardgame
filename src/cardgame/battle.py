"""Turn flow for one battle: draw, play, resolve, enemy act, next turn.

Pure logic. Card values come from data (``cardgame.loader``). The only
randomness is the deck shuffle, drawn from a seeded RNG, so the same seed and
the same plays always produce the same ``log``.

Targeting: ``damage`` hits the chosen target (default: the enemy). ``shield``
and ``draw`` apply to the player who played the card. Shield lasts until the
start of its owner's next turn.

Status effects (``apply_status``) are data-driven: a card names a status id from
the statuses table (``data/statuses.json``) and a stack count. Rules:

- Applying a status that is already active adds its stacks and resets its
  duration to the table's duration.
- The status step (after the enemy phase, before the next turn) ticks every
  combatant: ``poison`` deals its stacks as damage (shield absorbs it), then
  each status loses one turn and is removed at zero.
- ``weak`` on the attacker cuts that attacker's outgoing card damage to 75%
  (rounded down).

A card that names an unknown status, or uses an effect the engine does not
model, is rejected before anything changes.

Enemy AI: an enemy unit may list ``moves`` in its data (``data/units.json``),
each a card id with a weight. When no ``enemy_policy`` is given, the enemy
phase picks one move per turn with the seeded RNG (weighted) and resolves
that card against the player. An enemy with no moves and no policy idles.
A new enemy is therefore a data-file change only.

``Battle.winner`` is the id of the side that reached 0 HP (``None`` while
both are alive). If both reach 0 HP the player is reported as defeated.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from cardgame.models import Card, Status, Unit
from cardgame.rng import make_rng

WEAK_DAMAGE_PERCENT = 75
POISON = "poison"
WEAK = "weak"


class CardRejected(Exception):
    """The player tried to play a card that cannot be played right now."""


class UnsupportedEffect(Exception):
    """A card uses an effect the engine does not model yet."""


@dataclass
class ActiveStatus:
    stacks: int
    turns_left: int


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
    statuses: dict[str, ActiveStatus] = field(default_factory=dict)

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
        statuses: Mapping[str, Status] | None = None,
    ) -> None:
        if player.id == enemy.id:
            raise ValueError(f"player and enemy share the id '{player.id}'")
        for unit in (player, enemy):
            for card_id in unit.deck:
                if card_id not in cards:
                    raise ValueError(f"unknown card '{card_id}' in deck of {unit.id}")
        self.cards = cards
        self.statuses: dict[str, Status] = dict(statuses or {})
        for move in enemy.moves:
            if move.card not in cards:
                raise ValueError(f"unknown card '{move.card}' in moves of {enemy.id}")
            self._check_supported(cards[move.card])
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
        self._check_supported(card)

        player.hand.remove(card_id)
        player.energy -= card.cost
        self.log.append(f"player plays {card_id} (cost {card.cost}) -> {target_id}")
        self.resolve(card, caster=player, target=self.units[target_id])
        player.discard.append(card_id)

    def resolve(self, card: Card, caster: Combatant, target: Combatant) -> None:
        """Apply a card's effects in order. Also used by enemy policies."""
        self._check_supported(card)
        for effect in card.effects:
            if effect.kind == "damage":
                amount = effect.amount
                if WEAK in caster.statuses:
                    amount = amount * WEAK_DAMAGE_PERCENT // 100
                    self.log.append(f"{caster.id} is weak: damage {effect.amount} -> {amount}")
                self._damage(target, amount)
            elif effect.kind == "shield":
                caster.shield += effect.amount
                self.log.append(f"{caster.id} gains {effect.amount} shield")
            elif effect.kind == "draw":
                self.draw(caster, effect.amount)
                self.log.append(f"{caster.id} draws {effect.amount}")
            elif effect.kind == "apply_status":
                self._apply_status(target, effect.status_id, effect.amount)

    def enemy_act(self) -> None:
        """Enemy phase. Enemy shield clears here; the policy (if any) then acts."""
        self.enemy.shield = 0
        if self.enemy_policy is not None:
            self.enemy_policy(self)
            return
        moves = self.enemy.unit.moves
        if not moves:
            self.log.append("enemy idles")
            return
        pick = self.rng.choices(moves, weights=[move.weight for move in moves])[0]
        self.log.append(f"{self.enemy.id} picks {pick.card}")
        self.resolve(self.cards[pick.card], caster=self.enemy, target=self.player)

    @property
    def winner(self) -> str | None:
        """Id of the winning side, or ``None`` while both units are alive."""
        if self.player.hp == 0:
            return self.enemy.id
        if self.enemy.hp == 0:
            return self.player.id
        return None

    def status_step(self) -> None:
        """Tick every combatant's statuses: poison damage, then duration; expired ones go."""
        for who in (self.player, self.enemy):
            for status_id in list(who.statuses):
                active = who.statuses[status_id]
                if status_id == POISON:
                    self._damage(who, active.stacks)
                active.turns_left -= 1
                if active.turns_left <= 0:
                    del who.statuses[status_id]
                    self.log.append(f"{who.id} {status_id} expires")

    def end_turn(self) -> None:
        """Discard the hand, run the enemy phase and status step, then start the next player turn."""
        self.player.discard.extend(self.player.hand)
        self.player.hand.clear()
        self.log.append("player ends turn")
        self.enemy_act()
        self.status_step()
        self.begin_turn()

    def _apply_status(self, target: Combatant, status_id: str, stacks: int) -> None:
        base = self.statuses[status_id]
        active = target.statuses.get(status_id)
        if active is None:
            active = ActiveStatus(stacks=0, turns_left=base.duration)
            target.statuses[status_id] = active
        active.stacks += stacks
        active.turns_left = base.duration
        self.log.append(
            f"{target.id} gains {stacks} {status_id} "
            f"(now {active.stacks}, {active.turns_left} turns)"
        )

    def _check_supported(self, card: Card) -> None:
        for effect in card.effects:
            if effect.kind in ("damage", "shield", "draw"):
                continue
            if effect.kind == "apply_status":
                if effect.status_id not in self.statuses:
                    raise UnsupportedEffect(
                        f"card '{card.id}' applies unknown status '{effect.status_id}'"
                    )
                continue
            raise UnsupportedEffect(
                f"card '{card.id}' uses '{effect.kind}', which is not modelled yet"
            )

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


