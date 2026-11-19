# ChessMind — B/C/D integration notes

This upload integrates D's original evaluation and MCTS modules with the existing `chessbot` application. The original root-level `D_Evaluate_and_MCTS/` folder remains untouched for review.

- `src/evaluate.py`: D's evaluator, with an added `evaluate_white(board)` adapter for C's white-perspective search. Original `evaluate(board)` continues to score from the side-to-move perspective.
- `src/engine.py`: C's engine layer with a **one-line** change: prefer `evaluate_white` when loading the evaluator.
- `src/mcts.py`: D's MCTS with normalized UCB rewards, preserved move history for repetitions, and `MCTS.choose()` returning the agreed five fields. `choose_move()` still returns `chess.Move`. Nodes for MCTS are the number of simulations; score is a win-rate proxy, not centipawns.
- `configs/eval_weights.json`: D's original weights.
- `tests/test_integration_d.py`: compatibility, search-adapter, and micro-experiment tests.

## Review requested from C and D

Please review the adapter changes and the MCTS reward correction before final experiments or interpreting performance results. Do not treat the 2-ply G3/G5 smoke tests as chess-strength evidence.

## Run from chessbot/ in Jupyter

```python
import sys
!{sys.executable} -m pytest tests -q
```

Then optionally smoke-test G3/G5 with separate output files:

```python
from src.experiment import ExperimentRunner
for group in ("G3", "G5"):
    x = ExperimentRunner(group, games=2, max_plies=4, time_limit=0.05,
                         output_csv=f"experiments/results/smoke_{group}.csv")
    print(group, x.run())
```

Keep these short-cap smoke-test CSVs separate from official experimental data.
