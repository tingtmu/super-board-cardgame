# super-board-cardgame

Pure-logic turn-based card roguelike skill/battle engine. No UI. Cards and skills are data (JSON), so a new card is a data-file change only.

- Stack: Python, uv, pytest. Verify: `uv sync --quiet && uv run pytest -q`.
- Core concepts: Card (name, cost, effects), Effect (damage, shield, draw, apply status; JSON-defined), Status (poison, weak, shield; stacks and duration), Unit (player and enemies: HP, energy, deck).
- Turn flow: draw → player plays cards → resolve → enemy acts → status tick → next turn.
- Rules: fixed RNG seed (reproducible), new cards need no engine changes, every feature has unit tests.
- Milestones: 1) data structures + 3 sample cards, 2) turn flow, 3) status effects, 4) simple enemy AI.
- Source of truth: `spec.md` (Chinese). Base branch: `staging`.
