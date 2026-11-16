# super-board-cardgame

Toy project to try [super-board](https://github.com/EricTechPro/super-board) end to end.

## Goal
Build the project described in `spec.md`: a turn-based card roguelike skill/battle engine
(pure logic, no UI, cards and skills defined as data). Read `spec.md` first.

## Stack
- Python, managed with **uv**; tests with **pytest**.
- Verify command (for the merge gate): `uv sync --quiet && uv run pytest -q`
- Rules from the spec: fixed RNG seed (reproducible), new cards = data-file changes only,
  every feature has unit tests.

## Repo
- GitHub: https://github.com/tingtmu/super-board-cardgame (public, remote `origin`)
- super-board is installed at project level: real files in `.agents/`, linked from `.claude/`.
  Do not edit them; they are the pack's files.

## Where we are / next steps
1. `gh` has `project` scope; dynamic workflows enabled (check `/config` if a run complains).
2. Run `/super-board onboard` (resumable; the user is doing this step themselves).
3. After onboarding, set `verify_commands` in the super-board config to the command above.
4. Turn the four milestones in `spec.md` into cards (one per milestone): data structures +
   3 sample cards, turn flow, status effects, simple enemy AI. 1-5 tickets may go through
   `/implement-spec` instead of the board.
5. Put cards in `Ready`, then `/super-board run <slug>`.

## Working rules
- The session that runs `/super-board run` is an orchestrator, not a worker: it dispatches
  waves and reports, it does not build, test or fix cards itself.
- Don't push, merge or change board/repo settings unless the user asks.
